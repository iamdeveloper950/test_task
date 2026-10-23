"""Time-slot utilities for the scheduling assistant.

The working day is divided into fixed-size slots. Slot 0 starts at
DAY_START. A person's availability for one day is a list of booleans,
one entry per slot, where True means the person is free.
"""

from datetime import time

DAY_START = time(9, 0)
DAY_END = time(17, 0)
SLOT_MINUTES = 30
SLOTS_PER_DAY = 16  # 09:00 to 17:00

DAY_START_MINUTES = DAY_START.hour * 60 + DAY_START.minute
DAY_END_MINUTES = DAY_END.hour * 60 + DAY_END.minute


def time_to_minutes(clock: str) -> int:
    """Convert a valid HH:MM clock time to minutes since midnight."""
    if not isinstance(clock, str):
        raise ValueError("Time must be a string in HH:MM format")
    parts = clock.split(":")
    if len(parts) != 2 or any(not part.isdigit() for part in parts):
        raise ValueError(f"Invalid time {clock!r}; expected HH:MM")
    hours, minutes = map(int, parts)
    if not (0 <= hours <= 23 and 0 <= minutes <= 59):
        raise ValueError(f"Invalid time {clock!r}; expected HH:MM")
    return hours * 60 + minutes


def minutes_to_time(minutes: int) -> str:
    """Convert minutes since midnight to HH:MM."""
    if not isinstance(minutes, int) or isinstance(minutes, bool) or not 0 <= minutes < 24 * 60:
        raise ValueError("Minutes must be an integer within one day")
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def time_to_slot(clock: str) -> int:
    """Convert a clock time to the index of the slot containing it."""
    return (time_to_minutes(clock) - DAY_START_MINUTES) // SLOT_MINUTES


def time_to_slot_ceil(clock: str) -> int:
    """Convert a clock time to a slot index, rounding up to the next boundary."""
    offset = time_to_minutes(clock) - DAY_START_MINUTES
    return -(-offset // SLOT_MINUTES)


def slot_to_time(index: int) -> str:
    """Convert a slot index to the clock time at which the slot starts."""
    if not isinstance(index, int) or isinstance(index, bool):
        raise ValueError("Slot index must be an integer")
    return minutes_to_time(DAY_START_MINUTES + index * SLOT_MINUTES)


def availability_from_busy(busy_blocks: list[dict]) -> list[bool]:
    """Build a free/busy list; any slot partially overlapping a busy block is busy.

    Busy intervals use [start, end) semantics and are clipped to working hours.
    """
    free = [True] * SLOTS_PER_DAY
    for block in busy_blocks:
        if not isinstance(block, dict) or "start" not in block or "end" not in block:
            raise ValueError("Each busy block must contain start and end times")
        start_minutes = time_to_minutes(block["start"])
        end_minutes = time_to_minutes(block["end"])
        if end_minutes <= start_minutes:
            raise ValueError("Busy block end must be after its start")
        if end_minutes <= DAY_START_MINUTES or start_minutes >= DAY_END_MINUTES:
            continue
        start = max(0, time_to_slot(block["start"]))
        end = min(SLOTS_PER_DAY, time_to_slot_ceil(block["end"]))
        for i in range(start, end):
            free[i] = False
    return free


def combine_availability(calendars: list[list[bool]]) -> list[bool]:
    """Intersect calendars: a slot is free only if everyone is free."""
    if not calendars:
        raise ValueError("At least one attendee calendar is required")
    lengths = {len(calendar) for calendar in calendars}
    if len(lengths) != 1:
        raise ValueError("All availability lists must have the same number of slots")
    combined = [True] * len(calendars[0])
    for free in calendars:
        combined = [a and b for a, b in zip(combined, free)]
    return combined


def find_free_windows(free: list[bool], slots_needed: int, start_slot: int = 0,
                      end_slot: int | None = None) -> list[int]:
    """Return all starts of free windows, including a window ending at end_slot."""
    if not isinstance(slots_needed, int) or isinstance(slots_needed, bool) or slots_needed <= 0:
        raise ValueError("slots_needed must be a positive integer")
    if end_slot is None:
        end_slot = len(free)
    if not isinstance(start_slot, int) or isinstance(start_slot, bool):
        raise ValueError("start_slot must be an integer")
    if not isinstance(end_slot, int) or isinstance(end_slot, bool):
        raise ValueError("end_slot must be an integer")
    if not 0 <= start_slot <= len(free) or not 0 <= end_slot <= len(free):
        raise ValueError("Slot bounds are outside the availability list")
    if start_slot > end_slot:
        return []
    return [start for start in range(start_slot, end_slot - slots_needed + 1)
            if all(free[start:start + slots_needed])]
