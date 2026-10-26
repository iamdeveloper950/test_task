"""Tools the agent can call. Each tool takes the Store plus keyword arguments."""

from datetime import date as date_type
from .slots import SLOT_MINUTES, minutes_to_time, time_to_minutes
from .store import Store


class UnknownPersonError(ValueError):
    """Raised when a requested employee ID is not in the directory."""


def _known_person_ids(store: Store) -> set[str]:
    return {p["id"] for p in store.people
            if isinstance(p, dict) and isinstance(p.get("id"), str)}


def _validate_date(value: str) -> None:
    if not isinstance(value, str):
        raise ValueError("date must be a string in YYYY-MM-DD format")
    try:
        date_type.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("date must be a valid date in YYYY-MM-DD format") from exc


def _resolve_person(store: Store, person: str) -> None:
    if not isinstance(person, str) or person not in _known_person_ids(store):
        raise UnknownPersonError(f"Unknown employee ID: {person!r}")


def list_people(store: Store) -> list[dict]:
    """Return everyone in the directory."""
    return store.people


def get_busy_times(store: Store, person: str, date: str) -> list[dict]:
    """Return a person's busy blocks on a date (YYYY-MM-DD)."""
    _resolve_person(store, person)
    _validate_date(date)
    return store.calendars.get(person, {}).get(date, [])


def find_free_slots(store: Store, attendees: list[str], date: str,
                    duration_minutes: int, earliest: str | None = None,
                    latest: str | None = None, limit: int | None = None) -> list[dict]:
    """Find all free windows whose starts align to the slot grid.

    Busy intervals are checked at minute precision with half-open semantics.
    Candidate starts remain aligned to the 30-minute grid, while durations
    such as 45 minutes are supported without rounding the requested end time.
    """
    if not isinstance(attendees, list) or not attendees:
        raise ValueError("attendees must be a non-empty list of employee IDs")
    for person in attendees:
        _resolve_person(store, person)
    attendees = list(dict.fromkeys(attendees))
    _validate_date(date)
    if not isinstance(duration_minutes, int) or isinstance(duration_minutes, bool):
        raise ValueError("duration_minutes must be an integer")
    if duration_minutes <= 0:
        raise ValueError("duration_minutes must be positive")
    if limit is not None and (not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0):
        raise ValueError("limit must be a positive integer when provided")

    earliest_minutes = time_to_minutes(earliest) if earliest is not None else 9 * 60
    latest_minutes = time_to_minutes(latest) if latest is not None else 17 * 60
    day_start, day_end = 9 * 60, 17 * 60
    earliest_minutes = max(earliest_minutes, day_start)
    latest_minutes = min(latest_minutes, day_end)
    if earliest_minutes >= latest_minutes or duration_minutes > latest_minutes - earliest_minutes:
        return []

    # Starts are fixed-size slot boundaries. Exact interval checks avoid
    # rejecting a 13:00-13:45 meeting merely because another event starts at 13:45.
    first_start = day_start + ((earliest_minutes - day_start + SLOT_MINUTES - 1) // SLOT_MINUTES) * SLOT_MINUTES
    busy_by_attendee = [store.calendars.get(person, {}).get(date, []) for person in attendees]
    slots = []
    for start in range(first_start, latest_minutes - duration_minutes + 1, SLOT_MINUTES):
        end = start + duration_minutes
        if end > day_end:
            continue
        blocked = False
        for busy_blocks in busy_by_attendee:
            for block in busy_blocks:
                busy_start = time_to_minutes(block["start"])
                busy_end = time_to_minutes(block["end"])
                if busy_end <= busy_start:
                    raise ValueError("Busy block end must be after its start")
                # Half-open intervals: touching endpoints are not overlaps.
                if start < busy_end and busy_start < end:
                    blocked = True
                    break
            if blocked:
                break
        if not blocked:
            slots.append({"start": minutes_to_time(start), "end": minutes_to_time(end)})
    return slots[:limit] if limit is not None else slots


TOOLS = {"list_people": list_people, "get_busy_times": get_busy_times,
         "find_free_slots": find_free_slots}
