# Renumber Rooms - prototype spec

Status: prototype for Revit 2027.1 / Dynamo Player. Logic validated off-Revit; Revit-side
validation is in `test_cases.md`.

## 1. What it does

Renumbers the Rooms in one selected row, in plan order along the row, writing a label of the
form `prefix + number + suffix` into the room's **Number** parameter.

- Target: `BuiltInParameter.ROOM_NUMBER`
- Selection is read with `uidoc.Selection.GetElementIds()` at run time
- Numbers are **not padded**: `A-1`, `A-2`, ... `A-12`
- Nothing is written unless `Dry run` is false

The operator drag-selects exactly one row of rooms (Ctrl-click / Ctrl-drag may add or remove
rooms afterwards; how the set was built does not matter). The tool sorts that set along the
row's dominant axis, so horizontal and vertical rows both work.

Deliberately out of scope for v1: selecting more than one row at a time, row tolerance,
serpentine order, choosing a start corner (only `Reverse` is offered), ordering by existing
number or by attribute, padding, following a drawn path, linked models, Areas/MEP spaces,
per-room suffixes, descending sequences, renumbering by level or view.

## 2. User workflow (Dynamo Player)

1. Copy the .dyn into the Player folder:
   `%appdata%\Dynamo\Dynamo Revit\<version>\player\RenumberRooms\RenumberRooms.dyn`
2. In Revit, drag-select the row of booth Rooms. Add or remove individual rooms with
   Ctrl-click / Shift-click if needed.
3. Open Dynamo Player, open the graph, fill the fields, keep `Dry run = true`, press Run.
4. Compare the report's `n of x` list with the booth plan, then set `Dry run = false` and run
   again.
5. Undo is two steps: temporary numbers, then final numbers.

## 3. Inputs

| Input | Type | Default | Validation |
|---|---|---|---|
| Reverse | boolean | false | number from the other end of the row |
| Prefix | string | (empty) | free text, include separators, e.g. `A-` |
| Start | number | 1 | integer >= 0 |
| Step | number | 1 | integer >= 1 (2 gives odd sequences from an odd start) |
| Suffix | string | (empty) | free text, include separators, e.g. `-E` |
| Dry run | boolean | true | no writes when true |

Affixes are used verbatim. Separators, spaces and case are the user's responsibility; nothing
is trimmed or normalised.

## 4. Algorithm

1. Read selection, keep elements in category `OST_Rooms` with a positive `ROOM_AREA` and a
   Number parameter. The `Room` type is deliberately not imported: some Dynamo Python engines
   fail to resolve `Autodesk.Revit.DB.Architecture`, which breaks the whole script at import.
2. Take each room's plan centre from its bounding box. If the selection's width is at least
   its height, order by X; otherwise order by Y. Ties fall back to the other axis, then to
   element id. Rooms without a bounding box are reported and left out.
3. Apply `Reverse` by flipping the ordered list.
4. Build `pattern = ^<escaped prefix>(\d+)<escaped suffix>$`.
5. Scan **all** Rooms in the model (not just the selection). Exclude the selected rooms
   (their current numbers are about to be freed). Any number captured by the pattern becomes
   `occupied`. This is an integer comparison, so `A3` and `A003` both occupy 3.
6. Walk the row. `cursor = start`; for each room assign `cursor`, but while the candidate is
   occupied record it as skipped and advance `cursor += step` (without consuming a room).
   After assigning, `cursor = assigned + step`.
7. Guard: labels must be unique; the skip loop is capped at 100000 iterations.
8. Write in two transactions: all rooms to unique temporary strings, commit, then all rooms to
   final labels, commit. Individual failures are caught, reported, and do not abort the batch.
9. Emit a report (also the Player output).

### Collision example

`A3` already exists on a room outside the selection, `prefix=A`, `start=1`, `step=2`,
three booths selected:

```
A1
A5   (A3 skipped)
A7
Skipped occupied: A3
```

## 5. Report format

```
Renumber Rooms (DRY RUN)
prefix='A-'  start=1  step=2  suffix='-E'
Order: along the row

  1  id 312345     B-101-E       -> A-1-E    1 of 3
  2  id 312346     A-2-E         -> A-3-E    2 of 3
  3  id 312347     C-9-E         -> A-5-E    3 of 3

Skipped occupied: A-4-E
SKIP unplaced or empty room (id 312350)
FAIL number for id 312351: ...
Would renumber 3 room(s).
```

## 6. Graph layout

```
Reverse ─┐
Prefix  ─┤
Start   ─┼─► [Python Script: Renumber] ─► [Watch: Report]  (Is Output)
Step    ─┤       6 inputs, 1 output
Suffix  ─┤
Dry run ─┘
```

All six value nodes are marked **Is Input** (graph `Inputs` block and `NodeViews` both carry
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

1. Add six input nodes: Boolean (`Reverse` = false), String (`Prefix`),
   Number (`Start` = 1), Number (`Step` = 1), String (`Suffix`),
   Boolean (`Dry run` = true).
2. Add one Python Script node, set its engine to `PythonNet3`, paste the `Code` string from
   the .dyn node, and add inputs until it has 6 ports (IN[0]..IN[5]).
3. Add a Watch node.
4. Wire inputs to IN[0..5] in listed order, Python `OUT` to the Watch.
5. Select each input node, right-click -> **Is Input**; select the Watch -> **Is Output**.
6. Save into the Player folder.

## 9. Risks

- **Unpadded numbers**: Revit schedules and tags sort Number as text, so `A-1`, `A-10`,
  `A-11`, `A-2` in a schedule. Accepted for this process; do not "fix" it with padding.
- **One row per run**: the tool does not detect rows. Boxing two rows, an island or an
  L-shaped group numbers everything along the long axis, interleaving them. The dry run's
  `n of x` list shows it.
- **Dominant-axis rule**: a roughly square or diagonal selection can be read on the wrong
  axis. The report shows the result before writing.
- **Duplicate numbers across the model**: Revit does not block duplicates via API; the skip
  logic only covers numbers that match the current affix pattern. Rooms using a different
  format are not considered occupied (by design).
- **Rooms without a bounding box** cannot be ordered; they are reported and left unchanged.
- **Worksets**: writing a room in a non-owned workset throws; the run reports it and continues.
- **Undo granularity**: two undo steps, unlike a plugin which can group them into one.
