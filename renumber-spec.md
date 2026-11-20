# Renumber Rooms - prototype spec

Status: prototype for Revit 2027.1 / Dynamo Player. Logic validated off-Revit; Revit-side
validation is in `test_cases.md`.

## 1. What it does

Renumbers the Rooms the user has selected, in the order they were selected, writing a label
of the form `prefix + zero-padded number + suffix` into the room's **Number** parameter.

- Target: `BuiltInParameter.ROOM_NUMBER`
- Selection is read with `uidoc.Selection.GetElementIds()` at run time
- Nothing is written unless `Dry run` is false

Deliberately out of scope for v1: spatial ordering, linked models, Areas/MEP spaces,
per-room suffixes, descending sequences, renumbering by level or view.

## 2. User workflow (Dynamo Player)

1. Copy the .dyn into the Player folder:
   `%appdata%\Dynamo\Dynamo Revit\<version>\player\RenumberRooms\RenumberRooms.dyn`
2. In Revit, select the booth Rooms. Click them in the intended numbering order.
3. Open Dynamo Player, open the graph, fill the fields, keep `Dry run = true`, press Run.
4. Compare the report with the booth plan, then set `Dry run = false` and run again.
5. Undo is two steps: temporary numbers, then final numbers.

## 3. Inputs

| Input | Type | Default | Validation |
|---|---|---|---|
| Prefix | string | (empty) | free text, include separators, e.g. `A-` |
| Start | number | 1 | integer >= 0 |
| Step | number | 1 | integer >= 1 (2 gives odd sequences from an odd start) |
| Suffix | string | (empty) | free text, include separators, e.g. `-E` |
| Digits | number | 3 | integer >= 1, widened automatically if the sequence overflows |
| Dry run | boolean | true | no writes when true |

Affixes are used verbatim. Separators, spaces and case are the user's responsibility; nothing
is trimmed or normalised.

## 4. Algorithm

1. Read selection, keep placed `Room` elements with `Area > 0` and a Number parameter.
2. Build `pattern = ^<escaped prefix>(\d+)<escaped suffix>$`.
3. Scan **all** Rooms in the model (not just the selection). Exclude the selected rooms
   (their current numbers are about to be freed). Any number captured by the pattern becomes
   `occupied`. This is an integer comparison, so `A3` and `A003` both occupy 3.
4. Walk the selection in order. `cursor = start`; for each room assign `cursor`, but while the
   candidate is occupied record it as skipped and advance `cursor += step` (without consuming
   a room). After assigning, `cursor = assigned + step`.
5. Compute one uniform width: `max(digits, digits of the largest assigned number)`. Widen and
   warn if needed. Example: start 998, step 2, three rooms -> `A0998`, `A1000`, `A1002`.
6. Guard: labels must be unique; the skip loop is capped at 100000 iterations.
7. Write in two transactions: all rooms to unique temporary strings, commit, then all rooms to
   final labels, commit. Individual failures are caught, reported, and do not abort the batch.
8. Emit a report (also the Player output).

### Collision example

`A003` already exists on a room outside the selection, `prefix=A`, `start=1`, `step=2`,
three booths selected:

```
1  -> A001
2  -> A005   (A003 skipped)
3  -> A007
Skipped occupied: A003
```

## 5. Report format

```
Renumber Rooms (DRY RUN)
prefix='A-'  start=1  step=2  suffix='-E'  digits=3
Order: selection order, 3 room(s)

  1  id 312345     A-001-E       -> A-001-E
  2  id 312346     A-002-E       -> A-003-E
  3  id 312347     B-101-E       -> A-005-E

Skipped occupied: A-004-E
WARN digits widened from 3 to 4 for a uniform label.
SKIP unplaced or empty room (id 312350)
FAIL number for id 312351: ...
Would renumber 3 room(s).
```

## 6. Graph layout

```
Prefix  ─┐
Start   ─┤
Step    ─┼─► [Python Script: Renumber] ─► [Watch: Report]  (Is Output)
Suffix  ─┤       6 inputs, 1 output
Digits  ─┤
Dry run ─┘
```

All six value nodes are marked **Is Input** (graph `Inputs` block and `NodeViews` both carry
the flag); the Watch is marked **Is Output**. Python engine: `PythonNet3`.

If the engine is missing in your Dynamo build, right-click the Python node, choose
`CPython3` (or `IronPython2` on older builds) and re-save. The script uses only
`clr`/`RevitAPI`/`RevitServices`, which all three engines support.

## 7. Files

| File | Role |
|---|---|
| `RenumberRooms.dyn` | Player graph; contains an embedded copy of the logic |
| `renumber_core.py` | Canonical, dependency-free logic + self-test (`python3 renumber_core.py`) |
| `test_cases.md` | Acceptance fixtures and Revit checklist |
| `handover-dotnet.md` | Porting guide for the plugin team |

The .dyn copy and `renumber_core.py` are intentionally equivalent; change both together.

## 8. Fallback: rebuild the graph by hand

If the .dyn fails to open in your Dynamo build, rebuild it in 5 minutes:

1. Add six input nodes: String (`Prefix`), Number (`Start` = 1), Number (`Step` = 1),
   String (`Suffix`), Number (`Digits` = 3), Boolean (`Dry run` = true).
2. Add one Python Script node, set its engine to `PythonNet3`, paste the `Code` string from
   the .dyn node (or run `renumber_core.py`'s logic with the Revit glue), and add inputs
   until it has 6 ports (IN[0]..IN[5]).
3. Add a Watch node.
4. Wire inputs to IN[0..5] in listed order, Python `OUT` to the Watch.
5. Select each input node, right-click -> **Is Input**; select the Watch -> **Is Output**.
6. Save into the Player folder.

## 9. Risks

- **Selection order**: Revit preserves click order in practice but does not guarantee it.
  Deselecting and re-selecting rooms can reorder the set. The report shows the index per room
  so a wrong order is visible before writing.
- **Duplicate numbers across the model**: Revit does not block duplicates via API; the skip
  logic only covers numbers that match the current affix pattern. Rooms using a different
  format are not considered occupied (by design).
- **Worksets**: writing a room in a non-owned workset throws; the run reports it and continues.
- **Undo granularity**: two undo steps, unlike a plugin which can group them into one.
