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


INPUT_NAMES = [
    "Order",
    "Start corner",
    "Row tolerance (m)",
    "Prefix",
    "Start",
    "Step",
    "Suffix",
    "Digits",
    "Dry run",
]


def load_dyn():
    with open(DYN, encoding="utf-8") as handle:
        graph = json.load(handle)

    python_nodes = [n for n in graph["Nodes"] if n["NodeType"] == "PythonScriptNode"]
    assert len(python_nodes) == 1, "expected exactly one Python node"
    node = python_nodes[0]
    assert node.get("Engine") == "PythonNet3", node.get("Engine")

    inputs = [n for n in graph["Nodes"] if n["NodeType"].endswith("InputNode")]
    assert len(inputs) == 9, [n["NodeType"] for n in inputs]
    assert len(node["Inputs"]) == 9, len(node["Inputs"])

    names = [entry["Name"] for entry in graph["Inputs"]]
    assert names == INPUT_NAMES, names
    views = graph["View"]["NodeViews"]
    assert sum(1 for v in views if v["IsSetAsInput"]) == 9, views
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


def inputs(order="click", corner="BL", tolerance=3.0, prefix="A", start=1, step=1,
           suffix="", digits=3, dry_run=True):
    return [order, corner, tolerance, prefix, start, step, suffix, digits, dry_run]


def labels_of(doc):
    return [room.get_Parameter("ROOM_NUMBER").AsString() for room in doc.rooms]


def numbers(doc):
    return [room.get_Parameter("ROOM_NUMBER").AsString() for room in doc.rooms]


def assignment_order(writes, count):
    return [write[0] for write in writes[-count:]]


def check(name, condition, detail=""):
    if not condition:
        raise AssertionError("{}: {}".format(name, detail))


def grid_rooms():
    rooms = []
    for row in range(3):
        for column in range(4):
            index = row * 4 + column
            rooms.append(
                FakeRoom("r{:02d}".format(index), x=metres(3.0 * column),
                         y=metres(4.0 * row))
            )
    return rooms


def main():
    manager = _make_stub_modules()

    # Base: click order, padded to 3 digits.
    rooms = [FakeRoom("a"), FakeRoom("b"), FakeRoom("c")]
    out, doc, _ = run(rooms, rooms, inputs(), manager)
    check("base dry run", not State.writes and labels_of(doc) == ["", "", ""], labels_of(doc))
    check("base report", "A001" in out and "A003" in out, out)
    check("dry run report", "(DRY RUN)" in out, out)
    check("click order header", "Order: click order, 3 room(s)" in out, out)

    # Base, live: temp numbers then final labels, no writes in dry run.
    _, doc, writes = run(rooms, rooms, inputs(dry_run=False), manager)
    check("live", labels_of(doc) == ["A001", "A002", "A003"], labels_of(doc))
    check("live temp first", all(w[2].startswith("ZZRN") for w in writes[:3]), writes)
    check("live final count", len(writes) == 6, writes)

    # Step.
    out, doc, _ = run(rooms, rooms, inputs(start=3, step=2), manager)
    check("step report", "A003" in out and "A005" in out and "A007" in out, out)

    # Affixes carry separators.
    out, doc, _ = run(rooms, rooms, inputs(prefix="A-", suffix="-E"), manager)
    check("affixes", "A-001-E" in out and "A-003-E" in out, out)

    # Occupied candidates on non-selected rooms are skipped.
    outer = [FakeRoom("x", "A002"), FakeRoom("y", "A004")]
    selected = [FakeRoom("1"), FakeRoom("2"), FakeRoom("3"), FakeRoom("4")]
    out, doc, _ = run(outer + selected, selected, inputs(), manager)
    check(
        "skip",
        all(label in out for label in ("A001", "A003", "A005", "A006")),
        out,
    )
    check("skip report", "Skipped occupied: A002, A004" in out, out)
    check("skip dry run", numbers(doc)[2:] == ["", "", "", ""], numbers(doc))
    check("skip untouched", numbers(doc)[:2] == ["A002", "A004"], numbers(doc))

    # Selected rooms' old numbers are freed.
    rooms = [FakeRoom(str(i), "A{:03d}".format(i)) for i in range(1, 11)]
    out, doc, _ = run(rooms, rooms, inputs(start=2), manager)
    check("reuse", out.count("-> A") == 10 and "A011" in out, out)

    # Overflow widens the whole run and warns.
    three = [FakeRoom("p"), FakeRoom("q"), FakeRoom("r")]
    out, doc, _ = run(three, three, inputs(start=998, step=2), manager)
    check("widen", "A0998" in out and "A1000" in out and "A1002" in out, out)
    check("widen warn", "WARN digits widened from 3 to 4" in out, out)

    # Affix digits are not mistaken for the number; regex metachars escaped.
    outer = [FakeRoom("m", "A003")]
    selected = [FakeRoom("1")]
    out, doc, _ = run(outer + selected, selected, inputs(start=3), manager)
    check("numeric match", "A004" in out, out)
    outer = [FakeRoom("m", "AX001")]
    out, doc, _ = run(outer + selected, selected, inputs(prefix="A."), manager)
    check("escape", "A.001" in out, out)

    # Validation aborts before any write.
    out, doc, writes = run(rooms, rooms, inputs(step=0, dry_run=False), manager)
    check("step validation", "Renumber aborted" in out and not writes, out)
    out, doc, writes = run(rooms, rooms, inputs(start=-1, dry_run=False), manager)
    check("start validation", "Renumber aborted" in out and not writes, out)
    out, doc, writes = run(rooms, rooms, inputs(digits=0, dry_run=False), manager)
    check("digits validation", "Renumber aborted" in out and not writes, out)

    out, doc, writes = run(rooms, rooms, inputs(order="grid", dry_run=False), manager)
    check("order validation", "Order must be click, rows or number" in out and not writes, out)
    out, doc, writes = run(rooms, rooms, inputs(order="rows", corner="XX", dry_run=False), manager)
    check("corner validation", "Start corner must be BL, BR, TL or TR" in out and not writes, out)
    out, doc, writes = run(rooms, rooms, inputs(order="rows", tolerance=0, dry_run=False), manager)
    check("tolerance validation", "Row tolerance must be greater than 0" in out and not writes, out)

    # Order and geometric fields are ignored outside rows mode.
    out, doc, _ = run(rooms, rooms, inputs(order="click", corner="XX", tolerance=0), manager)
    check("click ignores geometry", "A001" in out and "Renumber aborted" not in out, out)

    # Unplaced room skipped, placed room still renumbered.
    unplaced = FakeRoom("u", "X", area=0)
    placed = FakeRoom("p")
    out, doc, _ = run([unplaced, placed], [unplaced, placed], inputs(), manager)
    check("unplaced report", "SKIP unplaced or zero-area room" in out, out)
    check("unplaced dry run", labels_of(doc) == ["X", ""], labels_of(doc))

    # Empty selection.
    out, _, writes = run([], [], inputs(dry_run=False), manager)
    check("empty", "no placed Rooms" in out and not writes, out)

    # --- rows mode: 3 rows of 4 booths, one metre of slack each way ----------

    expected = {
        "BL": ["r00", "r01", "r02", "r03",
               "r04", "r05", "r06", "r07",
               "r08", "r09", "r10", "r11"],
        "BR": ["r03", "r02", "r01", "r00",
               "r07", "r06", "r05", "r04",
               "r11", "r10", "r09", "r08"],
        "TL": ["r08", "r09", "r10", "r11",
               "r04", "r05", "r06", "r07",
               "r00", "r01", "r02", "r03"],
        "TR": ["r11", "r10", "r09", "r08",
               "r07", "r06", "r05", "r04",
               "r03", "r02", "r01", "r00"],
    }
    for corner, order in expected.items():
        rooms = grid_rooms()
        out, doc, writes = run(
            rooms, rooms, inputs(order="rows", corner=corner, dry_run=False), manager
        )
        check(
            "rows " + corner,
            assignment_order(writes, 12) == order,
            "{} != {}".format(assignment_order(writes, 12), order),
        )

    rooms = grid_rooms()
    out, doc, _ = run(rooms, rooms, inputs(order="rows", corner="BL"), manager)
    check(
        "rows header",
        "Order: rows (corner BL, tolerance 3 m), 12 room(s)" in out,
        out,
    )
    check("rows position", "row 1, pos 1" in out and "row 3, pos 4" in out, out)
    check("rows labels", "A001" in out and "A012" in out, out)

    # Tolerance merges rows within the distance and splits them when tight.
    merged = [
        FakeRoom("a", x=metres(0), y=metres(0)),
        FakeRoom("b", x=metres(5), y=metres(0.5)),
        FakeRoom("c", x=metres(0), y=metres(1)),
    ]
    out, doc, writes = run(
        merged, merged, inputs(order="rows", corner="BL", tolerance=3, dry_run=False),
        manager,
    )
    check("tolerance merge", assignment_order(writes, 3) == ["a", "c", "b"],
          assignment_order(writes, 3))
    out, doc, writes = run(
        merged, merged, inputs(order="rows", corner="BL", tolerance=0.5, dry_run=False),
        manager,
    )
    check("tolerance split", assignment_order(writes, 3) == ["a", "b", "c"],
          assignment_order(writes, 3))

    # A room without a bounding box cannot be ordered and is reported.
    no_box = [FakeRoom("u", has_box=False), FakeRoom("v", x=metres(1))]
    out, doc, writes = run(
        no_box, no_box, inputs(order="rows", dry_run=False), manager
    )
    check("no box note", "SKIP no bounding box, cannot order (id u)" in out, out)
    check("no box excluded", assignment_order(writes, 1) == ["v"], writes)

    # --- number mode: sort by the digits already in the Number field ---------

    numbered = [
        FakeRoom("p", "B-2"),
        FakeRoom("q", "A010"),
        FakeRoom("r", ""),
        FakeRoom("s", "LOBBY"),
        FakeRoom("t", "A003"),
    ]
    out, doc, writes = run(
        numbered, numbered, inputs(order="number", dry_run=False), manager
    )
    check(
        "number order",
        assignment_order(writes, 5) == ["p", "t", "q", "r", "s"],
        assignment_order(writes, 5),
    )
    check("number header", "Order: existing number, 5 room(s)" in out, out)
    check(
        "number no digits",
        "No number to sort by (numbered last): id r, id s" in out,
        out,
    )

    print("verify_dyn: all checks passed")


CODE = load_dyn()

if __name__ == "__main__":
    main()
