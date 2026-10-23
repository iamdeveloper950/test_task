"""Tools the agent can call. Each tool takes the Store plus keyword arguments."""

from datetime import date as date_type
from .slots import (SLOT_MINUTES, SLOTS_PER_DAY, availability_from_busy,
                    combine_availability, find_free_windows, minutes_to_time,
                    slot_to_time, time_to_minutes, time_to_slot, time_to_slot_ceil)
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
    """Find windows when everyone is free. Optional limit is applied after search."""
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
    if earliest_minutes >= latest_minutes:
        return []
    earliest_clock = f"{earliest_minutes // 60:02d}:{earliest_minutes % 60:02d}"
    latest_clock = f"{latest_minutes // 60:02d}:{latest_minutes % 60:02d}"
    start_slot = max(0, min(SLOTS_PER_DAY, time_to_slot_ceil(earliest_clock)))
    end_slot = max(0, min(SLOTS_PER_DAY, time_to_slot(latest_clock)))

    calendars = [availability_from_busy(store.calendars.get(person, {}).get(date, []))
                 for person in attendees]
    free = combine_availability(calendars)
    # Slots are the availability granularity, so reserve every slot touched by
    # the requested duration. Return the exact requested end time, not a rounded
    # duration, after the conservative slot check succeeds.
    slots_needed = (duration_minutes + SLOT_MINUTES - 1) // SLOT_MINUTES
    starts = find_free_windows(free, slots_needed, start_slot, end_slot)
    slots = [{"start": slot_to_time(start),
              "end": minutes_to_time(9 * 60 + start * SLOT_MINUTES + duration_minutes)}
             for start in starts]
    return slots[:limit] if limit is not None else slots


TOOLS = {"list_people": list_people, "get_busy_times": get_busy_times,
         "find_free_slots": find_free_slots}
