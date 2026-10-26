from scheduler.store import Store
from scheduler.tools import find_free_slots, get_busy_times


def test_get_busy_times():
    store = Store.load()
    busy = get_busy_times(store, "sam", "2026-11-04")
    assert busy == [{"start": "09:00", "end": "09:30", "title": "Standup"}]


def test_find_free_slots_for_two_people_in_the_afternoon():
    store = Store.load()
    slots = find_free_slots(
        store,
        attendees=["priya", "sam"],
        date="2026-11-03",
        duration_minutes=30,
        earliest="13:00",
    )
    assert slots == [
        {"start": "13:00", "end": "13:30"},
        {"start": "13:30", "end": "14:00"},
        {"start": "15:00", "end": "15:30"},
        {"start": "16:00", "end": "16:30"},
        {"start": "16:30", "end": "17:00"},
    ]


def test_find_free_slots_hour_long_meeting():
    store = Store.load()
    slots = find_free_slots(
        store, attendees=["priya", "sam"], date="2026-11-03", duration_minutes=60
    )
    assert {"start": "13:00", "end": "14:00"} in slots


def test_unknown_attendee_is_rejected():
    import pytest
    from scheduler.tools import UnknownPersonError

    with pytest.raises(UnknownPersonError):
        find_free_slots(Store.load(), ["priya", "not-a-person"], "2026-11-03", 30)


def test_duration_is_not_rounded_down():
    slots = find_free_slots(Store.load(), ["priya", "sam"], "2026-11-03", 45,
                            earliest="13:00", latest="14:00")
    assert slots == [{"start": "13:00", "end": "13:45"}]


def test_non_positive_duration_is_rejected():
    import pytest

    with pytest.raises(ValueError, match="positive"):
        find_free_slots(Store.load(), ["priya"], "2026-11-03", 0)


def test_limit_is_opt_in_and_applied_after_search():
    store = Store.load()
    all_slots = find_free_slots(store, ["sam"], "2026-11-03", 30)
    limited = find_free_slots(store, ["sam"], "2026-11-03", 30, limit=2)
    assert len(all_slots) > 2
    assert limited == all_slots[:2]


def test_earliest_bound_does_not_return_earlier_start():
    slots = find_free_slots(Store.load(), ["sam"], "2026-11-03", 30,
                            earliest="13:15", latest="14:00")
    assert slots
    assert all(slot["start"] >= "13:30" for slot in slots)


def test_latest_working_day_boundary_includes_final_half_hour():
    slots = find_free_slots(Store.load(), ["priya", "sam"], "2026-11-03", 30,
                            earliest="16:30", latest="17:00")
    assert slots == [{"start": "16:30", "end": "17:00"}]


def test_latest_before_earliest_returns_no_slots():
    assert find_free_slots(Store.load(), ["sam"], "2026-11-03", 30,
                           earliest="14:00", latest="13:00") == []


def test_malformed_date_is_rejected():
    import pytest

    with pytest.raises(ValueError, match="valid date"):
        find_free_slots(Store.load(), ["sam"], "2026-02-30", 30)
