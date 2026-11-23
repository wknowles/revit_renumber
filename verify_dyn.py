"""Execute the Python embedded in RenumberRooms.dyn against fake Revit objects.

The .dyn is the only product, so the graph's embedded script is the single source
of truth. This harness extracts it and runs it with stubbed Revit API modules,
so a regression shows up without opening Revit.

    python3 verify_dyn.py
"""

import json
import sys
import types

DYN = "RenumberRooms.dyn"
FEET_PER_METRE = 3.280839895013123


def metres(value):
    return value * FEET_PER_METRE


# --- state shared by the stubbed Revit modules -------------------------------

class State:
    doc = None
    writes = []


class FakeId:
    def __init__(self, value):
        self.Value = value


class FakeCategory:
    def __init__(self, name):
        self.Name = name
        self.Id = FakeId("cat-" + name)


def _categories_get_item(_category):
    return FakeCategory("Rooms")


class FakeParameter:
    def __init__(self, value, owner, name):
        self._value = value
        self._owner = owner
        self._name = name

    def AsString(self):
        return self._value if isinstance(self._value, str) else ""

    def AsDouble(self):
        return float(self._value or 0)

    def Set(self, value):
        self._value = value
        State.writes.append((self._owner.Id.Value, self._name, value))


class FakeRoom:
    def __init__(self, uid, number="", area=20.0, has_number=True, x=0.0, y=0.0,
                 has_box=True):
        self.UniqueId = uid
        self.Id = FakeId(uid)
        self.Category = FakeCategory("Rooms")
        self._number = FakeParameter(number, self, "number") if has_number else None
        self._area = FakeParameter(area, self, "area")
        self._x = x
        self._y = y
        self._has_box = has_box

    def get_Parameter(self, builtin):
        return self._number if builtin == "ROOM_NUMBER" else self._area

    def get_BoundingBox(self, _view):
        if not self._has_box:
            return None
        return types.SimpleNamespace(
            Min=types.SimpleNamespace(X=self._x - 1.5, Y=self._y - 2.0, Z=0.0),
            Max=types.SimpleNamespace(X=self._x + 1.5, Y=self._y + 2.0, Z=3.0),
        )


class FakeCollector:
    def __init__(self, doc):
        self._doc = doc

    def OfCategory(self, _category):
        return self

    def WhereElementIsNotElementType(self):
        return self

    def __iter__(self):
        return iter(list(self._doc.rooms))


class FakeTransaction:
    def __init__(self, _doc, name):
        self.name = name

    def Start(self):
        pass

    def Commit(self):
        pass


def _make_stub_modules():
    def module(name, **attrs):
        mod = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(mod, key, value)
        sys.modules[name] = mod
        return mod

    class Current:
        CurrentDBDocument = None
        CurrentUIDocument = None

        @property
        def Instance(self):
            return self

    manager = Current()

    class TransactionManagerStub:
        class Instance:
            @staticmethod
            def ForceCloseTransaction():
                pass

    autodesk = module("Autodesk")
    revit = module("Autodesk.Revit")
    autodesk.Revit = revit

    module(
        "Autodesk.Revit.DB",
        BuiltInCategory=types.SimpleNamespace(OST_Rooms="OST_Rooms"),
        BuiltInParameter=types.SimpleNamespace(
            ROOM_NUMBER="ROOM_NUMBER", ROOM_AREA="ROOM_AREA"
        ),
        FilteredElementCollector=FakeCollector,
        Transaction=FakeTransaction,
    )
    module("clr", AddReference=lambda _name: None)

    services = module("RevitServices")
    module("RevitServices.Persistence", DocumentManager=manager)
    module(
        "RevitServices.Transactions",
        TransactionManager=TransactionManagerStub,
    )
    services.Persistence = sys.modules["RevitServices.Persistence"]
    services.Transactions = sys.modules["RevitServices.Transactions"]
    return manager


INPUT_NAMES = ["Reverse", "Prefix", "Start", "Step", "Suffix", "Dry run"]


def load_dyn():
    with open(DYN, encoding="utf-8") as handle:
        graph = json.load(handle)

    python_nodes = [n for n in graph["Nodes"] if n["NodeType"] == "PythonScriptNode"]
    assert len(python_nodes) == 1, "expected exactly one Python node"
    node = python_nodes[0]
    assert node.get("Engine") == "PythonNet3", node.get("Engine")

    inputs = [n for n in graph["Nodes"] if n["NodeType"].endswith("InputNode")]
    assert len(inputs) == 6, [n["NodeType"] for n in inputs]
    assert len(node["Inputs"]) == 6, len(node["Inputs"])

    names = [entry["Name"] for entry in graph["Inputs"]]
    assert names == INPUT_NAMES, names
    views = graph["View"]["NodeViews"]
    assert sum(1 for v in views if v["IsSetAsInput"]) == 6, views
    assert sum(1 for v in views if v["IsSetAsOutput"]) == 1, views
    assert any("Watch" in n.get("ConcreteType", "") for n in graph["Nodes"]), "no Watch"
    return node["Code"]


class FakeDoc:
    def __init__(self, rooms, selected):
        self.rooms = list(rooms)
        self.Settings = types.SimpleNamespace(
            Categories=types.SimpleNamespace(get_Item=_categories_get_item)
        )
        self._by_id = {room.Id.Value: room for room in self.rooms}
        self._selected = [room.Id for room in selected]

    def GetElement(self, element_id):
        return self._by_id.get(element_id.Value)

    def make_uidoc(self):
        return types.SimpleNamespace(
            Selection=types.SimpleNamespace(GetElementIds=lambda: list(self._selected))
        )


def run(rooms, selected, inputs, manager):
    State.writes = []
    doc = FakeDoc(rooms, selected)
    manager.CurrentDBDocument = doc
    manager.CurrentUIDocument = doc.make_uidoc()

    namespace = {"IN": list(inputs)}
    exec(compile(CODE, "<RenumberRooms.dyn>", "exec"), namespace)
    return namespace["OUT"], doc, list(State.writes)


def inputs(reverse=False, prefix="A", start=1, step=1, suffix="", dry_run=True):
    return [reverse, prefix, start, step, suffix, dry_run]


def labels_of(doc):
    return [room.get_Parameter("ROOM_NUMBER").AsString() for room in doc.rooms]


def numbers(doc):
    return [room.get_Parameter("ROOM_NUMBER").AsString() for room in doc.rooms]


def assignment_order(writes, count):
    return [write[0] for write in writes[-count:]]


def check(name, condition, detail=""):
    if not condition:
        raise AssertionError("{}: {}".format(name, detail))


def row_of_four():
    return [
        FakeRoom("a", x=metres(0), y=metres(0.5)),
        FakeRoom("b", x=metres(3), y=metres(0.2)),
        FakeRoom("c", x=metres(6), y=metres(0.4)),
        FakeRoom("d", x=metres(9), y=metres(0.1)),
    ]


def main():
    manager = _make_stub_modules()

    # A row is numbered along its length, regardless of the selection order.
    rooms = row_of_four()
    scrambled = [rooms[2], rooms[0], rooms[3], rooms[1]]
    out, doc, _ = run(rooms, scrambled, inputs(), manager)
    check("row dry run", not State.writes and labels_of(doc) == [""] * 4, labels_of(doc))
    check("row order", [line.split("->")[1].split()[0] for line in out.splitlines() if "->" in line] == ["A1", "A2", "A3", "A4"], out)
    check("row header", "Order: along the row" in out, out)
    check("row position", "1 of 4" in out and "4 of 4" in out, out)
    check("dry run report", "(DRY RUN)" in out, out)

    # Live: temp numbers, then final labels.
    _, doc, writes = run(rooms, scrambled, inputs(dry_run=False), manager)
    check("live labels", labels_of(doc) == ["A1", "A2", "A3", "A4"], labels_of(doc))
    check("live temp first", all(w[2].startswith("ZZRN") for w in writes[:4]), writes)
    check("live final count", len(writes) == 8, writes)

    # Reverse numbers from the other end.
    out, doc, writes = run(rooms, scrambled, inputs(reverse=True, dry_run=False), manager)
    check("reverse first room", assignment_order(writes, 4) == ["d", "c", "b", "a"], writes)
    check("reverse header", "Order: along the row (reversed)" in out, out)

    # A vertical row is ordered by Y because the selection is taller than wide.
    column = [
        FakeRoom("p", x=metres(1), y=metres(6)),
        FakeRoom("q", x=metres(1), y=metres(0)),
        FakeRoom("r", x=metres(1), y=metres(3)),
    ]
    out, doc, writes = run(column, column, inputs(dry_run=False), manager)
    check("vertical row", assignment_order(writes, 3) == ["q", "r", "p"], writes)

    # A wide row with Y jitter is still read along X, not by the jitter.
    jittered = [
        FakeRoom("j1", x=metres(0), y=metres(0)),
        FakeRoom("j2", x=metres(20), y=metres(1.5)),
        FakeRoom("j3", x=metres(10), y=metres(0.2)),
    ]
    out, doc, writes = run(jittered, jittered, inputs(dry_run=False), manager)
    check("dominant axis", assignment_order(writes, 3) == ["j1", "j3", "j2"], writes)

    # No padding: labels are plain integers in sequence.
    twelve = [FakeRoom("n{:02d}".format(i), x=metres(3.0 * i)) for i in range(12)]
    out, doc, _ = run(twelve, twelve, inputs(), manager)
    check(
        "unpadded",
        all(label in out for label in ("A1", "A9", "A10", "A12"))
        and "A01" not in out
        and "A001" not in out,
        out,
    )

    # Start, step and affixes.
    out, doc, _ = run(rooms, rooms, inputs(prefix="A-", start=3, step=2, suffix="-E"), manager)
    check("affixes", "A-3-E" in out and "A-5-E" in out and "A-9-E" in out, out)
    check("start zero", "A0" in run(rooms, rooms, inputs(start=0), manager)[0], "no A0")

    # Occupied candidates elsewhere in the model are skipped.
    outer = [FakeRoom("x", "A2"), FakeRoom("y", "A4")]
    selected = [FakeRoom("1"), FakeRoom("2"), FakeRoom("3"), FakeRoom("4")]
    out, doc, _ = run(outer + selected, selected, inputs(), manager)
    check(
        "skip",
        all(label in out for label in ("A1", "A3", "A5", "A6")),
        out,
    )
    check("skip report", "Skipped occupied: A2, A4" in out, out)
    check("skip untouched", numbers(doc)[:2] == ["A2", "A4"], numbers(doc))

    # Selected rooms' old numbers are freed.
    numbered = [FakeRoom(str(i), "A{}".format(i)) for i in range(1, 11)]
    out, doc, _ = run(numbered, numbered, inputs(start=2), manager)
    check("reuse", out.count("-> A") == 10 and "A11" in out, out)

    # Affix digits are not mistaken for the number; regex metachars escaped.
    outer = [FakeRoom("m", "A003")]
    selected = [FakeRoom("1")]
    out, doc, _ = run(outer + selected, selected, inputs(start=3), manager)
    check("numeric match", "A4" in out, out)
    outer = [FakeRoom("m", "AX001")]
    out, doc, _ = run(outer + selected, selected, inputs(prefix="A."), manager)
    check("escape", "A.1" in out, out)

    # Validation aborts before any write.
    out, doc, writes = run(rooms, rooms, inputs(step=0, dry_run=False), manager)
    check("step validation", "Renumber aborted" in out and not writes, out)
    out, doc, writes = run(rooms, rooms, inputs(start=-1, dry_run=False), manager)
    check("start validation", "Renumber aborted" in out and not writes, out)

    # Unplaced room skipped, placed room still renumbered.
    unplaced = FakeRoom("u", "X", area=0)
    placed = FakeRoom("p")
    out, doc, _ = run([unplaced, placed], [unplaced, placed], inputs(), manager)
    check("unplaced report", "SKIP unplaced or zero-area room" in out, out)
    check("unplaced dry run", labels_of(doc) == ["X", ""], labels_of(doc))

    # A room without a bounding box cannot be ordered and is reported.
    no_box = [FakeRoom("u", has_box=False), FakeRoom("v", x=metres(1))]
    out, doc, writes = run(no_box, no_box, inputs(dry_run=False), manager)
    check("no box note", "SKIP no bounding box, cannot order (id u)" in out, out)
    check("no box excluded", assignment_order(writes, 1) == ["v"], writes)

    # Empty selection.
    out, _, writes = run([], [], inputs(dry_run=False), manager)
    check("empty", "no placed Rooms" in out and not writes, out)

    print("verify_dyn: all checks passed")


CODE = load_dyn()

if __name__ == "__main__":
    main()
