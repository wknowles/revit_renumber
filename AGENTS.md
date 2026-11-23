# AGENTS.md

Revit 2027.1 / Dynamo Player room-renumbering prototype. `RenumberRooms.dyn` is the product;
there is no .NET project and no separate library.

## Verify

- `python3 verify_dyn.py` must print `verify_dyn: all checks passed`.
- The harness extracts the Python from the `.dyn` node and runs it against fake Revit
  objects, so it tests the shipped code, not a copy. It also checks the graph wiring.
- Add new rules as `check(...)` calls in `verify_dyn.py`; there is no pytest setup.
- Delete behaviour from the harness when you remove it from the graph, or the harness will
  lie.

## The .dyn file

- Edit it as JSON and keep it valid. Everything lives in the PythonScriptNode `Code` string
  except the Revit glue.
- Keep the six value nodes in order (Reverse, Prefix, Start, Step, Suffix, Dry run) flagged in
  **both** the graph `Inputs` block and `View.NodeViews` (`IsSetAsInput`); keep the Watch
  flagged `IsSetAsOutput`. Otherwise Dynamo Player drops the field.
- Engine must stay `PythonNet3`; `CPython3` is the fallback if the node fails to open.
- `verify_dyn.py` asserts these structural invariants, so a bad hand-edit fails the check.

## Ordering invariants (easy to break)

- One row per run, by operator discipline. The tool never groups or detects rows.
- The row's dominant axis is the larger of the selection's width and height; that axis is the
  sort key. Do not add a tolerance or a corner field back in.
- `Reverse` flips the sorted list; it is the only direction control.
- Rooms without a bounding box are reported and excluded, never guessed at.
- Ordering happens before the occupied scan and numbering, so it never changes which numbers
  are considered taken.

## Behaviour invariants (easy to break)

- Never import `Autodesk.Revit.DB.Architecture` / the `Room` type in the embedded script — it
  fails at import in some engines and kills the whole node. Filter by `OST_Rooms` + positive
  `ROOM_AREA` (commit `084d0d5` fixed exactly this).
- Occupied scan covers **all** model rooms except the selected ones, matched by `UniqueId`.
  Numbers are compared as integers (`A3` == `A003`); labels not matching the current affixes
  are not occupied.
- Numbers are unpadded: `prefix + str(number) + suffix`. Do not reintroduce a digits input or
  width logic.
- Live runs write unique `ZZRN…` temp numbers, commit, then write final labels, so Revit never
  sees duplicates mid-run.
- `Dry run = true` writes nothing and starts no transaction. Validate `start >= 0` and
  `step >= 1` and abort with a report.
- Affixes are verbatim (no trim/normalise) and must be regex-escaped.
- Every exception is caught and written to `OUT`; keep it that way so Dynamo shows the real
  traceback instead of only `PythonEvaluator.Evaluate failed`.

## Docs

- `renumber-spec.md` is the functional contract; read it first. `test_cases.md` holds the
  offline checks and the Revit acceptance fixtures A–L.
- Out of scope by design — do not add without asking: multi-row or serpentine ordering, row
  tolerance, start-corner selection, ordering by existing number or attribute, padding,
  path-following order, linked models, Areas/MEP spaces, per-room suffixes, descending
  sequences, level/view renumbering, presets.
