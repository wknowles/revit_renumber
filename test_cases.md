# Test cases

Two layers: logic tests that need no Revit (already passing) and Revit acceptance checks.

## 1. Offline logic tests

```bash
python3 verify_dyn.py
# verify_dyn: all checks passed
```

The harness loads `RenumberRooms.dyn`, extracts the Python from its node, and executes it
against fake Rooms, selection, collector and transactions. It also asserts the graph wiring:
nine named `Is Input` nodes, one `Is Output` Watch, `PythonNet3`.

Covers: base sequence, step, affix separators, skip-occupied, old-number reuse, padding
widening, regex escaping of affixes, numeric-only matching, input validation, dry run,
unplaced rooms, empty selection, temp-then-final writes, row ordering from all four corners,
row tolerance merge/split, existing-number ordering and the no-digits fallback.

## 2. Revit fixtures

Run on a **copy** of the model. For each fixture, select the listed rooms (clicking in the
listed order unless the fixture says to drag), then run, then check Numbers. `id` values
below are placeholders for whatever your rooms have.

Every fixture below runs with `Order = click` unless it says otherwise. Add
`Start corner = BL`, `Row tolerance = 3` for the rows fixtures.

### A. Base

5 rooms, numbers cleared or anything not matching. Click order 1..5.

| Input | Value |
|---|---|
| Prefix | `A` |
| Start / Step / Digits | 1 / 1 / 3 |
| Suffix | (empty) |

Expected: `A001 A002 A003 A004 A005` in click order.

### B. Step (odd numbers)

Same 5 rooms. Prefix `A`, Start 3, Step 2, Digits 3.

Expected: `A003 A005 A007 A009 A011`.

### C. Affixes with separators

Prefix `A-`, Suffix `-E`, Start 1, Step 1, Digits 3.

Expected: `A-001-E A-002-E ... A-005-E`.

### D. Occupied candidate skipped

Add 2 non-selected rooms numbered `A002` and `A004`. Select 4 booths only.
Prefix `A`, Start 1, Step 1, Digits 3.

All four expected: `A001 A003 A005 A006`.

Report must list `Skipped occupied: A002, A004`, and the two non-selected rooms must still be
`A002` and `A004`.

### E. Old numbers are freed

10 rooms numbered `A001`..`A010`, all selected. Prefix `A`, Start 2, Step 1, Digits 3.

Expected: `A002`..`A011`. No Revit duplicate-number warning at any point.

### F. Padding widens

3 rooms, Prefix `A`, Start 998, Step 2, Digits 3.

Expected: `A0998 A1000 A1002`, report contains
`WARN digits widened from 3 to 4`.

### G. Dry run

Any selection, Dry run = true.

Expected: report lists `old -> new`, Numbers unchanged, zero transactions (one Ctrl+Z does
nothing or undoes the previous command).

### H. Unplaced room

Select one placed booth plus one unplaced room (room not placed in a plan).

Expected: placed room renumbered, unplaced untouched, report line `SKIP unplaced or empty room`.

### I. Selection order

Select 4 rooms in reverse of the fixture A order.

Expected: report order and numbers follow the click order, not the model or view order.

### J. Undo

Run fixtures A live, then press Ctrl+Z twice.

Expected: first undo restores temporary numbers, second restores the original numbers.
(Two steps is expected in the Dynamo version; the plugin will group them into one.)

### K. Player wiring

- Nine fields appear, in order: Order, Start corner, Row tolerance (m), Prefix, Start, Step,
  Suffix, Digits, Dry run.
- Labels match the field names above.
- The report appears under Outputs.
- Running with `Step = 0` or `Start = -1` produces an `aborted` report and no changes.
- `Order = grid` produces an `aborted` report and no changes.

### L. Drag selection in rows order

3 rows of 4 booths. Drag a box around all 12, starting at the bottom-left corner.

| Input | Value |
|---|---|
| Order / Start corner | `rows` / `BL` |
| Row tolerance | 3 |
| Prefix, Start / Step / Digits | `A`, 1 / 1 / 3 |

Expected: `A001` on the bottom-left booth, then left to right along each row, `A012` top-right.
Report shows `row 1, pos 1` through `row 3, pos 4`.

### M. Other start corners

Same 12 booths, same drag, change only `Start corner`.
Expected first label: `BR` -> bottom-right booth, `TL` -> top-left booth,
`TR` -> top-right booth.

### N. Row tolerance

Two rows of booths 2 m apart, with depth differences within each row under 1 m.

- Tolerance 1 keeps the rows separate: report shows two rows.
- Tolerance 3 merges them into one: report shows a single row and the second row's booths
  continue the same left-to-right run.

The point is that the report's `row/pos` column shows which happened before anything is written.

### O. Existing numbers re-spaced

Rooms numbered `A001`, `A003`, `A007`, `B-2`, drag-selected in any order.
Order `number`, Prefix `A`, Start 1, Step 1, Digits 3.
Expected: `A001` (was 1), `A002` (was B-2), `A003` (was 3), `A004` (was 7).

### P. Existing numbers with blanks

Same as O plus one room with a blank Number and one numbered `LOBBY`.
Expected: the four readable rooms renumbered as in O; the blank and `LOBBY` rooms numbered
last, in id order, and listed under `No number to sort by (numbered last)`.

## 3. Results log

| Fixture | Pass | Notes |
|---|---|---|
| A base | | |
| B step | | |
| C affixes | | |
| D skip | | |
| E reuse | | |
| F widen | | |
| G dry run | | |
| H unplaced | | |
| I order | | |
| J undo | | |
| K player | | |
| L drag rows | | |
| M corners | | |
| N tolerance | | |
| O re-space | | |
| P blanks | | |

## 4. Failure triage

| Symptom | Likely cause |
|---|---|
| `PythonEvaluator.Evaluate failed` | Open the Report output; the script prints the real traceback there. If it is an assembly/namespace error, switch the Python node engine to `CPython3` and re-save |
| Graph opens with a broken Python node | Engine not available; switch to `CPython3`/`IronPython2` |
| Fields missing in Player | Input nodes not marked `Is Input`; re-mark and save |
| `Aborted: no placed Rooms` | Selection contained tags/areas/generic models, or nothing selected |
| Wrong order | Check `Start corner` and `Row tolerance` in the report first; in `click` mode, rooms were re-selected before running and Revit rebuilt the selection set |
| Warnings about duplicate room numbers | Pre-existing duplicates outside the pattern, unrelated to this tool |
