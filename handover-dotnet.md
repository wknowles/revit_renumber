# Handover notes: Dynamo prototype -> .NET plugin

The prototype (Dynamo graph + `renumber_core.py`) defines the behaviour. This document maps it
onto an `IExternalCommand` + WPF form. Read `renumber-spec.md` first; it is the functional
contract.

## 1. Shape of the plugin

```
IExternalCommand
  -> read selection (Room only)
  -> show WPF window: Prefix, Start, Step, Suffix, Digits, Dry run, preview grid, Run
  -> on Run: validate, compute, preview or write
  -> one TransactionGroup so the whole operation is a single undo step
```

The form is a straight upgrade over Dynamo Player: it can show the old -> new preview before
writing and can let the user reorder the list, which removes the "selection order is only a
convention" caveat.

## 2. API mapping

| Prototype | .NET |
|---|---|
| `uidoc.Selection.GetElementIds()` | same; returns `ICollection<ElementId>` |
| category filter (`OST_Rooms` + `ROOM_AREA`) | `.OfType<Room>()` / `.OfClass(typeof(Room))` (fine in C#) |
| `room.get_Parameter(BuiltInParameter.ROOM_NUMBER)` | same (`Parameter`), `.Set(string)` |
| `room.get_Parameter(BuiltInParameter.ROOM_AREA)` | `Room.Area`, or the same parameter |
| `re.escape(prefix) + (\d+) + re.escape(suffix)` | `Regex.Escape(prefix) + @"(\d+)" + Regex.Escape(suffix)` |
| `int(match.group(1))` | `int.Parse(..., CultureInfo.InvariantCulture)` |
| `"{:0{}d}".format(n, width)` | `n.ToString("D" + width, CultureInfo.InvariantCulture)` |
| `element.Id.Value` / `IntegerValue` | `element.Id.Value` (long). `IntegerValue` is obsolete since 2024 |
| two `Transaction`s | two `Transaction`s inside one `TransactionGroup` |
| Player report string | `DataGrid` + status text; copy-to-clipboard optional |

Revit 2027 API notes: keep `.Value` for `ElementId`; `Room.Number` still exists but going
through the parameter keeps the same code path as the prototype.

The prototype identifies rooms by category instead of importing
`Autodesk.Revit.DB.Architecture.Room`, because PythonNet3 in some Revit builds fails to
resolve that namespace and the Python node dies at import. A C# add-in has no such
limitation: use the `Room` type directly.

## 3. Selection

```csharp
UIDocument uidoc = commandData.Application.ActiveUIDocument;
Document doc = uidoc.Document;

List<Room> rooms = uidoc.Selection.GetElementIds()
    .Select(doc.GetElement)
    .OfType<Room>()
    .Where(r => r.IsPlaced && r.Area > 0)
    .ToList();
```

`GetElementIds()` preserves click order in practice, but it is not contractual. Since the
plugin owns the window, show `rooms` in a list and let the user confirm or reorder before
running. That is the one place where the plugin should not copy the prototype.

## 4. Occupied scan

```csharp
var selectedIds = new HashSet<ElementId>(rooms.Select(r => r.Id));
var pattern = new Regex("^" + Regex.Escape(prefix) + @"(\d+)" + Regex.Escape(suffix) + "$");
var occupied = new HashSet<int>();

foreach (Room other in new FilteredElementCollector(doc).OfClass(typeof(Room)))
{
    if (selectedIds.Contains(other.Id)) continue;               // freed by this operation
    string label = other.get_Parameter(BuiltInParameter.ROOM_NUMBER)?.AsString() ?? "";
    Match match = pattern.Match(label);
    if (match.Success)
        occupied.Add(int.Parse(match.Groups[1].Value, CultureInfo.InvariantCulture));
}
```

Integer comparison intentionally treats `A3` and `A003` as the same number.

## 5. Resolve and format

```csharp
int cursor = start;
var skipped = new List<int>();
var pairs = new List<(Room Room, string Old, int Number)>();

foreach (Room room in rooms)
{
    int number = cursor;
    int guard = 0;
    while (occupied.Contains(number))
    {
        skipped.Add(number);
        number += step;
        if (++guard > 100_000)
            throw new InvalidOperationException("Too many occupied numbers; check start and step.");
    }
    string old = room.get_Parameter(BuiltInParameter.ROOM_NUMBER).AsString() ?? "";
    pairs.Add((room, old, number));
    cursor = number + step;
}

int width = Math.Max(digits,
    pairs.Count == 0 ? digits : pairs.Max(p => p.Number.ToString(CultureInfo.InvariantCulture).Length));

string Label(int n) => prefix + n.ToString("D" + width, CultureInfo.InvariantCulture) + suffix;
```

Match the prototype: one uniform width for the whole run, widened once and reported.
Do not format per room.

## 6. Writing, undo, failures

```csharp
using (var group = new TransactionGroup(doc, "Renumber rooms"))
{
    group.Start();

    using (var temp = new Transaction(doc, "Temporary numbers"))
    {
        temp.Start();
        string token = "ZZRN" + Guid.NewGuid().ToString("N").Substring(0, 8);
        for (int i = 0; i < pairs.Count; i++)
            NumberParam(pairs[i].Room).Set(token + "-" + i.ToString(CultureInfo.InvariantCulture));
        temp.Commit();
    }

    using (var final = new Transaction(doc, "Final numbers"))
    {
        final.Start();
        foreach (var pair in pairs)
            NumberParam(pair.Room).Set(Label(pair.Number));
        final.Commit();
    }

    // one undo step
    group.Assimilate();
}

static Parameter NumberParam(Room room) =>
    room.get_Parameter(BuiltInParameter.ROOM_NUMBER);
```

Failure policy is an open decision (flagged, not assumed):

- **Default suggestion**: catch per-room `Autodesk.Revit.Exceptions.ApplicationException`,
  collect the failures, keep the successful rooms, and show a failure list.
- If any room fails and the user expects an all-or-nothing run, call `group.RollBack()`
  instead of `Assimilate()`. Rolling back a single inner `Transaction` is not enough because
  the temporary numbers are already committed.
- Worksharing: check `WorksharingUtils.GetCheckoutStatus(doc, room.Id)` before writing.
  `OwnedByOtherUser` / `OwnedByCurrentUser` need ownership; either request it explicitly or
  list the room as skipped.

## 7. Form

| Control | Type | Rules |
|---|---|---|
| Prefix | TextBox | free text, separators included |
| Start | NumericUpDown | int >= 0 |
| Step | NumericUpDown | int >= 1 |
| Suffix | TextBox | free text, separators included |
| Digits | NumericUpDown | int >= 1 |
| Dry run | CheckBox | default checked |
| Order | read-only list / DataGrid | room order, with up/down if implemented |
| Preview | DataGrid | index, ElementId, old number, new number, skipped/warn marker |
| Run | Button | disabled while validation errors exist |

Regenerate the preview on every field change; a preview over N rooms is cheap (one collector
scan and a loop). Do not write during preview.

## 8. Tests to port

`test_cases.md` fixtures A-K are the acceptance suite; they should pass identically in the
plugin. Keep the pure parts (`resolve`, `buildLabels`, `parseNumber`) in a class with no Revit
types and cover them with xUnit theory cases: base, step, affixes, skip, reuse, widening,
regex-escaped affixes, invalid settings.

## 9. Do not add yet

Spatial sorting, per-room suffix overrides, linked-model rooms, Areas/Spaces, descending
sequences, presets/profiles. They were excluded from the prototype on purpose and should be
separate decisions.
