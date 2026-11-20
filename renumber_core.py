"""Core renumbering logic for exhibition booth rooms.

This module has no Revit dependencies. It is the reference implementation for
the .NET plugin and is mirrored inside the Dynamo graph (RenumberRooms.dyn).

Run `python3 renumber_core.py` to execute the self-test.
"""

import re

MAX_ITERATIONS = 100000


def format_label(prefix, number, width, suffix):
    """Return prefix + zero-padded number + suffix. Separators live in the affixes."""
    return "{}{:0{}d}{}".format(prefix, number, width, suffix)


def affix_pattern(prefix, suffix):
    """Match a full label and capture its numeric part (e.g. A-003-E -> 3)."""
    return re.compile("^" + re.escape(prefix) + r"(\d+)" + re.escape(suffix) + "$")


def parse_number(label, pattern):
    match = pattern.match(label or "")
    return int(match.group(1)) if match else None


def occupied_numbers(labels, pattern):
    """Set of integers already used by labels that follow the current affixes."""
    numbers = set()
    for label in labels:
        number = parse_number(label, pattern)
        if number is not None:
            numbers.add(number)
    return numbers


def validate_settings(start, step, digits):
    errors = []
    if step < 1:
        errors.append("Step must be at least 1, got {}.".format(step))
    if start < 0:
        errors.append("Start must be 0 or greater, got {}.".format(start))
    if digits < 1:
        errors.append("Digits must be at least 1, got {}.".format(digits))
    return errors


def resolve_numbers(count, start, step, occupied):
    """Assign `count` numbers in selection order, skipping occupied candidates.

    Returns (numbers, skipped). The cursor advances by `step` from the last
    assigned number; an occupied candidate is reported and skipped without
    consuming a room.
    """
    numbers = []
    skipped = []
    cursor = start
    for _ in range(count):
        number = cursor
        iterations = 0
        while number in occupied:
            skipped.append(number)
            number += step
            iterations += 1
            if iterations > MAX_ITERATIONS:
                raise ValueError(
                    "Too many consecutive occupied numbers; check start and step."
                )
        numbers.append(number)
        cursor = number + step
    return numbers, skipped


def build_labels(numbers, prefix, suffix, digits):
    """Format all numbers with one uniform width, widening past `digits` if needed.

    Returns (labels, width).
    """
    width = max([digits] + [len(str(n)) for n in numbers]) if numbers else digits
    return [format_label(prefix, n, width, suffix) for n in numbers], width


def _selftest():
    # Base: 3 rooms, prefix A, start 1, step 1
    pattern = affix_pattern("A", "")
    numbers, skipped = resolve_numbers(3, 1, 1, occupied_numbers([], pattern))
    labels, width = build_labels(numbers, "A", "", 3)
    assert labels == ["A001", "A002", "A003"], labels
    assert width == 3 and skipped == []

    # Step: odd numbers
    numbers, _ = resolve_numbers(3, 3, 2, set())
    assert build_labels(numbers, "A", "", 3)[0] == ["A003", "A005", "A007"]

    # Affixes carry their separators
    labels, _ = build_labels([1, 2], "A-", "-E", 3)
    assert labels == ["A-001-E", "A-002-E"], labels

    # Skip occupied candidates: A003 occupied -> A001, A005, A007
    pattern = affix_pattern("A", "")
    occupied = occupied_numbers(["A003"], pattern)
    numbers, skipped = resolve_numbers(3, 1, 2, occupied)
    assert numbers == [1, 5, 7], numbers
    assert skipped == [3], skipped

    # Old numbers of the rooms being renumbered are treated as free
    pattern = affix_pattern("A", "")
    occupied = occupied_numbers([], pattern)  # selected rooms excluded by caller
    numbers, _ = resolve_numbers(10, 2, 1, occupied)
    assert numbers == list(range(2, 12)), numbers

    # Overflow widens the padding uniformly and is reported
    numbers, _ = resolve_numbers(3, 998, 2, set())
    labels, width = build_labels(numbers, "A", "", 3)
    assert labels == ["A0998", "A1000", "A1002"], labels
    assert width == 4

    # Affix digits are not mistaken for the number
    pattern = affix_pattern("A-", "-E")
    assert parse_number("A-012-E", pattern) == 12
    assert parse_number("A12-E", pattern) is None

    # Regex metacharacters in affixes are escaped
    pattern = affix_pattern("A.", "")
    assert parse_number("A.001", pattern) == 1
    assert parse_number("AX001", pattern) is None

    # Numeric labels only when both affixes are empty
    pattern = affix_pattern("", "")
    assert occupied_numbers(["12", "013", "A14"], pattern) == {12, 13}

    # Validation
    assert validate_settings(1, 1, 3) == []
    assert len(validate_settings(1, 0, 3)) == 1
    assert len(validate_settings(-1, 1, 0)) == 2


if __name__ == "__main__":
    _selftest()
    print("renumber_core: all self-tests passed")
