# Test cases

Two layers: logic tests that need no Revit (already passing) and Revit acceptance checks.

## 1. Offline logic tests

```bash
python3 renumber_core.py
# renumber_core: all self-tests passed
```

Covers: base sequence, step, affix separators, skip-occupied, old-number reuse, padding
widening, regex escaping of affixes, numeric-only matching, input validation.

The Python code embedded in `RenumberRooms.dyn` was additionally exercised against a simulated
Revit document (fake Rooms/selection/transactions) with the same cases plus dry run, unplaced
rooms, empty selection and abort-before-write. All passed.

## 2. Revit fixtures

Run on a **copy** of the model. For each fixture, select the listed rooms in the listed click
order, then run, then check Numbers. `id` values below are placeholders for whatever your
rooms have.

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

- Six fields appear, in order: Prefix, Start, Step, Suffix, Digits, Dry run.
- Labels match the field names above.
- The report appears under Outputs.
- Running with `Step = 0` or `Start = -1` produces an `aborted` report and no changes.

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

## 4. Failure triage

| Symptom | Likely cause |
|---|---|
| Graph opens with a broken Python node | Engine not available; switch to `CPython3`/`IronPython2` |
| Fields missing in Player | Input nodes not marked `Is Input`; re-mark and save |
| `Aborted: no placed Rooms` | Selection contained tags/areas/generic models, or nothing selected |
| Wrong order | Rooms were re-selected before running; Revit rebuilt the selection set |
| Warnings about duplicate room numbers | Pre-existing duplicates outside the pattern, unrelated to this tool |
