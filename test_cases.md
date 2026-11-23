# Test cases

Two layers: logic tests that need no Revit (already passing) and Revit acceptance checks.

## 1. Offline logic tests

```bash
python3 verify_dyn.py
# verify_dyn: all checks passed
```

The harness loads `RenumberRooms.dyn`, extracts the Python from its node, and executes it
against fake Rooms, selection, collector and transactions. It also asserts the graph wiring:
six named `Is Input` nodes, one `Is Output` Watch, `PythonNet3`.

Covers: ordering along a row in both orientations, scrambled selection order, reverse,
dominant-axis choice, unpadded labels, start/step, affix separators, skip-occupied,
old-number reuse, regex escaping of affixes, numeric-only matching, input validation,
dry run, unplaced rooms, rooms without a bounding box, empty selection, temp-then-final
writes.

## 2. Revit fixtures

Run on a **copy** of the model. For each fixture, drag-select the listed row (adding
individual rooms with Ctrl-click where noted), then run, then check Numbers. `id` values
below are placeholders for whatever your rooms have.

### A. Base

5 rooms in a straight row.

| Input | Value |
|---|---|
| Reverse | off |
| Prefix | `A` |
| Start / Step | 1 / 1 |
| Suffix | (empty) |

Expected: `A1 A2 A3 A4 A5` left to right, regardless of how the selection was built.

### B. Step (odd numbers)

Same 5 rooms. Prefix `A`, Start 3, Step 2.

Expected: `A3 A5 A7 A9 A11`.

### C. Affixes with separators

Prefix `A-`, Suffix `-E`, Start 1, Step 1.

Expected: `A-1-E A-2-E ... A-5-E`, no zero padding.

### D. Occupied candidate skipped

Add 2 non-selected rooms numbered `A2` and `A4`. Select 4 booths only.
Prefix `A`, Start 1, Step 1.

Expected: `A1 A3 A5 A6`.
Report must list `Skipped occupied: A2, A4`, and the two non-selected rooms must be unchanged.

### E. Old numbers are freed

10 rooms numbered `A1`..`A10`, all selected. Prefix `A`, Start 2, Step 1.

Expected: `A2`..`A11`. No Revit duplicate-number warning at any point.

### F. Reverse

Same 5-room row as A, Reverse on.

Expected: `A1` on the rightmost booth, `A5` on the leftmost, and the report header reads
`Order: along the row (reversed)`.

### G. Dry run

Any row, Dry run = true.

Expected: report lists `old -> new` with `n of x`, Numbers unchanged, zero transactions
(one Ctrl+Z does nothing or undoes the previous command).

### H. Unplaced room

Select one placed booth plus one unplaced room (room not placed in a plan).

Expected: placed room renumbered, unplaced untouched, report line `SKIP unplaced or zero-area room`.

### I. Vertical row

A column of booths, taller than it is wide, selected with one drag.

Expected: numbers run bottom to top; with Reverse on, top to bottom.

### J. Undo

Run fixture A live, then press Ctrl+Z twice.

Expected: first undo restores temporary numbers, second restores the original numbers.
(Two steps is expected in the Dynamo version; the plugin will group them into one.)

### K. Player wiring

- Six fields appear, in order: Reverse, Prefix, Start, Step, Suffix, Dry run.
- Labels match the field names above.
- The report appears under Outputs.
- Running with `Step = 0` or `Start = -1` produces an `aborted` report and no changes.

### L. Adding rooms after the drag

Drag-select 4 booths of a 5-booth row, then Ctrl-click the fifth booth from another spot.

Expected: all 5 numbered in plan order; the added booth takes the number its position
deserves, not the last one. Ctrl-clicking a room from a *neighbouring* row would slot it by
position too — the `n of x` list is the check for that mistake.

## 3. Results log

| Fixture | Pass | Notes |
|---|---|---|
| A base | | |
| B step | | |
| C affixes | | |
| D skip | | |
| E reuse | | |
| F reverse | | |
| G dry run | | |
| H unplaced | | |
| I vertical | | |
| J undo | | |
| K player | | |
| L add after drag | | |

## 4. Failure triage

| Symptom | Likely cause |
|---|---|
| `PythonEvaluator.Evaluate failed` | Open the Report output; the script prints the real traceback there. If it is an assembly/namespace error, switch the Python node engine to `CPython3` and re-save |
| Graph opens with a broken Python node | Engine not available; switch to `CPython3`/`IronPython2` |
| Fields missing in Player | Input nodes not marked `Is Input`; re-mark and save |
| `Aborted: no placed Rooms` | Selection contained tags/areas/generic models, or nothing selected |
| Wrong order | Check the `Order` line and the `n of x` list: `Reverse` is on, the selection spans more than one row, or the selection is roughly square so the dominant axis was misread |
| Scheduled numbers look out of order (`A1`, `A10`, `A2`) | Expected: labels are unpadded and Number sorts as text |
| Warnings about duplicate room numbers | Pre-existing duplicates outside the pattern, unrelated to this tool |
