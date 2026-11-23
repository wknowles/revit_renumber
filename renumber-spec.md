# Renumber Rooms - prototype spec

Status: prototype for Revit 2027.1 / Dynamo Player. Logic validated off-Revit; Revit-side
validation is in `test_cases.md`.

## 1. What it does

Renumbers the Rooms the user has selected, writing a label of the form
`prefix + zero-padded number + suffix` into the room's **Number** parameter.

The sequence comes from one of three order modes, chosen with the `Order` input:

- `rows` (default) — for drag selection. Rooms are grouped into rows by their plan
  position, then read row by row from the stated start corner.
- `click` — the selection set order, for deliberate one-by-one selection.
- `number` — ascending digits already in the Number field, for tidying up an existing
  sequence.

- Target: `BuiltInParameter.ROOM_NUMBER`
- Selection is read with `uidoc.Selection.GetElementIds()` at run time
- Nothing is written unless `Dry run` is false

Deliberately out of scope for v1: serpentine (boustrophedon) order, following a drawn
path or aisle, ordering by aisle/zone attribute, linked models, Areas/MEP spaces,
per-room suffixes, descending sequences, renumbering by level or view.

## 2. User workflow (Dynamo Player)

1. Copy the .dyn into the Player folder:
   `%appdata%\Dynamo\Dynamo Revit\<version>\player\RenumberRooms\RenumberRooms.dyn`
2. In Revit, select the booth Rooms. Either drag a selection box or click them individually.
3. Open Dynamo Player, open the graph, fill the fields, keep `Dry run = true`, press Run.
   For a drag selection, set `Start corner` to the corner the drag started from.
4. Compare the report with the booth plan, then set `Dry run = false` and run again.
5. Undo is two steps: temporary numbers, then final numbers.

## 3. Inputs

| Input | Type | Default | Validation |
|---|---|---|---|
| Order | string | `rows` | `rows`, `click` or `number` (case-insensitive) |
| Start corner | string | `BL` | `BL`, `BR`, `TL` or `TR` (rows mode only) |
| Row tolerance (m) | number | 3 | greater than 0 (rows mode only) |
| Prefix | string | (empty) | free text, include separators, e.g. `A-` |
| Start | number | 1 | integer >= 0 |
| Step | number | 1 | integer >= 1 (2 gives odd sequences from an odd start) |
| Suffix | string | (empty) | free text, include separators, e.g. `-E` |
| Digits | number | 3 | integer >= 1, widened automatically if the sequence overflows |
| Dry run | boolean | true | no writes when true |

Affixes are used verbatim. Separators, spaces and case are the user's responsibility; nothing
is trimmed or normalised. `Order`, `Start corner` and `Row tolerance` are ignored outside
`rows` mode, but stay visible in Player because it has no conditional fields.

**Row tolerance is always metres**, whatever the project units, so 3 means about 10 ft.
Rooms whose plan centres are within the tolerance vertically are treated as one row.

## 4. Algorithm

1. Read selection, keep elements in category `OST_Rooms` with a positive `ROOM_AREA` and a
   Number parameter. The `Room` type is deliberately not imported: some Dynamo Python engines
   fail to resolve `Autodesk.Revit.DB.Architecture`, which breaks the whole script at import.
2. Put the rooms in `Order` sequence:
   - `click` — leave the selection order untouched.
   - `rows` — take each room's plan centre from its bounding box, sort by Y (or reverse,
     from the `T`/`B` half of the corner), start a new row whenever the next centre is more
     than `Row tolerance` from the row's first centre, then sort each row by X (or reverse,
     from the `L`/`R` half). Rooms without a bounding box are reported and left out.
   - `number` — sort by the first run of digits in the current Number, ties broken by
     element id; rooms with no digits at all are numbered last, in id order, and listed.
3. Build `pattern = ^<escaped prefix>(\d+)<escaped suffix>$`.
4. Scan **all** Rooms in the model (not just the selection). Exclude the selected rooms
   (their current numbers are about to be freed). Any number captured by the pattern becomes
   `occupied`. This is an integer comparison, so `A3` and `A003` both occupy 3.
5. Walk the rooms in their computed order. `cursor = start`; for each room assign `cursor`,
   but while the candidate is occupied record it as skipped and advance `cursor += step`
   (without consuming a room). After assigning, `cursor = assigned + step`.
6. Compute one uniform width: `max(digits, digits of the largest assigned number)`. Widen and
   warn if needed. Example: start 998, step 2, three rooms -> `A0998`, `A1000`, `A1002`.
7. Guard: labels must be unique; the skip loop is capped at 100000 iterations.
8. Write in two transactions: all rooms to unique temporary strings, commit, then all rooms to
   final labels, commit. Individual failures are caught, reported, and do not abort the batch.
9. Emit a report (also the Player output).

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
Order: rows (corner BL, tolerance 3 m), 3 room(s)

  1  id 312345     A-001-E       -> A-001-E    row 1, pos 1
  2  id 312346     A-002-E       -> A-003-E    row 1, pos 2
  3  id 312347     B-101-E       -> A-005-E    row 2, pos 1

Skipped occupied: A-004-E
WARN digits widened from 3 to 4 for a uniform label.
SKIP unplaced or empty room (id 312350)
FAIL number for id 312351: ...
Would renumber 3 room(s).
```

## 6. Graph layout

```
Order   ──┐
Start corner ─┤
Row tolerance ─┼─► [Python Script: Renumber] ─► [Watch: Report]  (Is Output)
Prefix  ──┤       9 inputs, 1 output
Start   ──┤
Step    ──┤
Suffix  ──┤
Digits  ──┤
Dry run ──┘
```

All nine value nodes are marked **Is Input** (graph `Inputs` block and `NodeViews` both carry
the flag); the Watch is marked **Is Output**. Python engine: `PythonNet3`.

If the engine is missing in your Dynamo build, right-click the Python node, choose
`CPython3` (or `IronPython2` on older builds) and re-save. The script uses only
`clr`/`RevitAPI`/`RevitServices`, which all three engines support.

If the node reports `PythonEvaluator.Evaluate failed`, read the Report output: the script
catches every exception (including import errors) and writes the full traceback there. An
assembly or namespace error in that traceback means the engine cannot see RevitAPI; switch
the node to `CPython3` and re-save. The script no longer imports
`Autodesk.Revit.DB.Architecture`, which is the import that most often fails.

## 7. Files

| File | Role |
|---|---|
| `RenumberRooms.dyn` | The product: Player graph with the logic embedded |
| `verify_dyn.py` | Runs the graph's embedded Python offline against fake Revit objects (`python3 verify_dyn.py`) |
| `test_cases.md` | Acceptance fixtures and Revit checklist |

The logic lives only in the .dyn's Python node. `verify_dyn.py` extracts it at run time, so
there is no second copy to keep in sync.

## 8. Fallback: rebuild the graph by hand

If the .dyn fails to open in your Dynamo build, rebuild it in 5 minutes:

1. Add nine input nodes: String (`Order` = rows), String (`Start corner` = BL),
   Number (`Row tolerance (m)` = 3), String (`Prefix`), Number (`Start` = 1),
   Number (`Step` = 1), String (`Suffix`), Number (`Digits` = 3),
   Boolean (`Dry run` = true).
2. Add one Python Script node, set its engine to `PythonNet3`, paste the `Code` string from
   the .dyn node, and add inputs until it has 9 ports (IN[0]..IN[8]).
3. Add a Watch node.
4. Wire inputs to IN[0..8] in listed order, Python `OUT` to the Watch.
5. Select each input node, right-click -> **Is Input**; select the Watch -> **Is Output**.
6. Save into the Player folder.

## 9. Risks

- **Corner orientation**: corners are read in model coordinates, so a plan view rotated
  against project north will not match "bottom-left" on screen. The dry-run report shows the
  order, so a wrong corner is visible before writing.
- **Row tolerance**: too large merges neighbouring rows into one, too small splits a row.
  The report's `row N, pos M` column makes this visible in the dry run.
- **Click order** (`Order = click`): Revit preserves click order in practice but does not
  guarantee it, and a dragged selection has no meaningful order — use `rows` for drags.
  The report shows the index per room so a wrong order is visible before writing.
- **Duplicate numbers across the model**: Revit does not block duplicates via API; the skip
  logic only covers numbers that match the current affix pattern. Rooms using a different
  format are not considered occupied (by design).
- **Rooms without a bounding box** cannot be ordered in rows mode; they are reported and left
  unchanged.
- **Worksets**: writing a room in a non-owned workset throws; the run reports it and continues.
- **Undo granularity**: two undo steps, unlike a plugin which can group them into one.
