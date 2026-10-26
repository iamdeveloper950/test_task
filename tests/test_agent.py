import json

from scheduler.agent import SchedulingAgent
from scheduler.model import FakeModel, final, tool_call
from scheduler.store import Store


def test_agent_returns_final_answer():
    model = FakeModel([final("Happy to help!")])
    agent = SchedulingAgent(model, Store.load())
    assert agent.run("hello") == "Happy to help!"


def test_agent_calls_tool_and_returns_result_to_model():
    model = FakeModel([
        tool_call("find_free_slots", attendees=["priya", "sam"],
                  date="2026-11-03", duration_minutes=60, earliest="12:00"),
        final("13:00 works for both."),
    ])
    agent = SchedulingAgent(model, Store.load())

    answer = agent.run("Find an hour for Priya and Sam on Tuesday afternoon")

    assert answer.startswith("Verified available 60-minute meeting options for Priya Raman, Sam Okafor")
    assert "13:00–14:00" in answer
    second_call = model.calls[1]
    assert second_call[-1]["role"] == "tool"
    assert {"start": "13:00", "end": "14:00"} in json.loads(second_call[-1]["content"])


def test_system_prompt_includes_directory():
    model = FakeModel([final("ok")])
    SchedulingAgent(model, Store.load()).run("hi")
    system = model.calls[0][0]["content"]
    assert "Priya Raman" in system



def test_malformed_json_returns_controlled_failure():
    agent = SchedulingAgent(FakeModel(["not-json"]), Store.load())
    assert "couldn't understand" in agent.run("Find a meeting")


def test_unknown_tool_returns_controlled_failure():
    model = FakeModel(['{"tool": "launch_rockets", "args": {}}'])
    answer = SchedulingAgent(model, Store.load()).run("Find a meeting")
    assert "unsupported tool" in answer


def test_unknown_attendee_is_reported_without_calling_model_again():
    model = FakeModel([
        tool_call("find_free_slots", attendees=["not-a-person"],
                  date="2026-11-03", duration_minutes=30),
        final("A meeting is available at 09:00."),
    ])
    answer = SchedulingAgent(model, Store.load()).run("Find a meeting with an unknown person")
    assert "couldn't find" in answer
    assert len(model.calls) == 1


def test_agent_stops_after_max_turns():
    repeated_call = tool_call("list_people")
    model = FakeModel([repeated_call], loop_last=True)
    answer = SchedulingAgent(model, Store.load(), max_turns=3).run("Find a meeting")
    assert "allowed number of steps" in answer
    assert len(model.calls) == 3


def test_invalid_tool_arguments_do_not_crash_agent():
    model = FakeModel([
        tool_call("find_free_slots", attendees="priya", date="2026-11-03", duration_minutes=30),
        final("I couldn't complete that request."),
    ])
    answer = SchedulingAgent(model, Store.load()).run("Find a meeting")
    assert answer == "I couldn't complete that request."
    assert '"error"' in model.calls[1][-1]["content"]


def test_agent_does_not_confirm_availability_without_calendar_check():
    model = FakeModel([final("Bob is available at 09:00.")])
    answer = SchedulingAgent(model, Store.load()).run("Find a meeting with Bob")
    assert "can't confirm a meeting" in answer


def test_agent_rejects_time_not_present_in_verified_slots():
    model = FakeModel([
        tool_call("find_free_slots", attendees=["priya", "sam"],
                  date="2026-11-03", duration_minutes=60, earliest="12:00"),
        final("13:00 works for both, or 14:30 if you prefer."),
    ])
    answer = SchedulingAgent(model, Store.load()).run("Find an hour for Priya and Sam")
    # The model's unsupported alternative is never surfaced; output is rendered
    # from the validated availability result instead.
    assert "14:30" not in answer
    assert "13:00–14:00" in answer


def test_agent_rejects_time_range_not_returned_as_a_complete_window():
    model = FakeModel([
        tool_call("find_free_slots", attendees=["priya", "sam"],
                  date="2026-11-03", duration_minutes=60, earliest="12:00"),
        final("13:00 to 15:00 works for both."),
    ])
    answer = SchedulingAgent(model, Store.load()).run("Find an hour for Priya and Sam")
    assert "13:00–14:00" in answer
    assert "13:00–15:00" not in answer


def test_agent_rejects_invented_person_after_valid_availability_check():
    model = FakeModel([
        tool_call("find_free_slots", attendees=["priya", "sam"],
                  date="2026-11-03", duration_minutes=60, earliest="12:00"),
        final("Bob is available at 13:00."),
    ])
    answer = SchedulingAgent(model, Store.load()).run("Find an hour for Priya and Sam")
    assert "Bob" not in answer
    assert "Priya Raman, Sam Okafor" in answer


def test_agent_rejects_directory_person_not_in_checked_meeting():
    model = FakeModel([
        tool_call("find_free_slots", attendees=["priya", "sam"],
                  date="2026-11-03", duration_minutes=60, earliest="12:00"),
        final("Priya, Sam, and Dana are available at 13:00."),
    ])
    answer = SchedulingAgent(model, Store.load()).run("Find an hour for Priya and Sam")
    assert "Dana" not in answer
    assert "Priya Raman, Sam Okafor" in answer


def test_agent_rejects_start_and_end_from_different_windows():
    model = FakeModel([
        tool_call("find_free_slots", attendees=["sam"],
                  date="2026-11-03", duration_minutes=30),
        final("09:00 to 12:00 is available."),
    ])
    answer = SchedulingAgent(model, Store.load()).run("Find a meeting with Sam")
    assert "09:00 to 12:00" not in answer
    assert "09:30–10:00" in answer


def test_agent_handles_model_exception():
    class BrokenModel:
        def complete(self, messages):
            raise TimeoutError("model timed out")

    answer = SchedulingAgent(BrokenModel(), Store.load()).run("Find a meeting")
    assert "couldn't complete" in answer


def test_agent_accepts_exact_verified_start_end_pair():
    model = FakeModel([
        tool_call("find_free_slots", attendees=["priya", "sam"],
                  date="2026-11-03", duration_minutes=60, earliest="12:00"),
        final("Priya and Sam are available from 13:00 to 14:00."),
    ])
    answer = SchedulingAgent(model, Store.load()).run("Find an hour for Priya and Sam")
    assert answer == (
        "Verified available 60-minute meeting options for Priya Raman, Sam Okafor "
        "on 2026-11-03: 13:00–14:00, 16:00–17:00."
    )


def test_agent_rejects_endpoints_from_different_valid_windows():
    model = FakeModel([
        tool_call("find_free_slots", attendees=["sam"],
                  date="2026-11-03", duration_minutes=30),
        final("09:30 to 12:00 is available."),
    ])
    answer = SchedulingAgent(model, Store.load()).run("Find a meeting with Sam")
    assert "09:30–12:00" not in answer
    assert "09:30–10:00" in answer


def test_agent_rejects_unverified_attendee_even_when_time_is_valid():
    model = FakeModel([
        tool_call("find_free_slots", attendees=["priya", "sam"],
                  date="2026-11-03", duration_minutes=60, earliest="12:00"),
        final("Priya, Sam, and Dana are available from 13:00 to 14:00."),
    ])
    answer = SchedulingAgent(model, Store.load()).run("Find an hour for Priya and Sam")
    assert "Dana" not in answer
    assert "Priya Raman, Sam Okafor" in answer


def test_malformed_tool_result_is_not_used_as_availability_evidence(monkeypatch):
    from scheduler import agent as agent_module

    monkeypatch.setitem(agent_module.TOOLS, "find_free_slots", lambda store, **kwargs: [{"start": "13:00"}])
    model = FakeModel([
        tool_call("find_free_slots", attendees=["priya", "sam"],
                  date="2026-11-03", duration_minutes=60),
        final("Priya and Sam are available from 13:00 to 14:00."),
    ])
    answer = SchedulingAgent(model, Store.load()).run("Find an hour for Priya and Sam")
    assert "can't confirm a meeting" in answer


def test_agent_returns_when_model_call_hangs():
    import threading

    release = threading.Event()

    class HangingModel:
        def complete(self, messages):
            release.wait(timeout=2)
            return final("This response arrives too late.")

    agent = SchedulingAgent(HangingModel(), Store.load(), model_timeout_seconds=0.02)
    answer = agent.run("Find a meeting")
    release.set()
    assert "couldn't complete the scheduling request in time" in answer


def test_model_timeout_must_be_positive():
    import pytest

    with pytest.raises(ValueError, match="model_timeout_seconds"):
        SchedulingAgent(FakeModel([final("ok")]), Store.load(), model_timeout_seconds=0)


def test_agent_rejects_wrong_response_shape():
    model = FakeModel(['{"tool": "list_people", "args": [], "final": "ok"}'])
    answer = SchedulingAgent(model, Store.load()).run("Find a meeting")
    assert "invalid tool request" in answer


def test_agent_rejects_unknown_person_claimed_as_attending():
    model = FakeModel([
        tool_call("find_free_slots", attendees=["priya", "sam"],
                  date="2026-11-03", duration_minutes=60, earliest="12:00"),
        final("Priya and Sam are available from 13:00 to 14:00. Bob will attend."),
    ])
    answer = SchedulingAgent(model, Store.load()).run("Find an hour for Priya and Sam")
    assert "Bob" not in answer
    assert "Priya Raman, Sam Okafor" in answer


def test_failed_later_availability_query_clears_previous_evidence(monkeypatch):
    from scheduler import agent as agent_module

    calls = {"count": 0}

    def mixed_results(store, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return [{"start": "13:00", "end": "14:00"}]
        return [{"start": "13:00"}]

    monkeypatch.setitem(agent_module.TOOLS, "find_free_slots", mixed_results)
    model = FakeModel([
        tool_call("find_free_slots", attendees=["priya", "sam"],
                  date="2026-11-03", duration_minutes=60),
        tool_call("find_free_slots", attendees=["dana"],
                  date="2026-11-03", duration_minutes=60),
        final("Dana is available from 13:00 to 14:00."),
    ])
    answer = SchedulingAgent(model, Store.load()).run("Find a meeting")
    assert "can't confirm a meeting" in answer or "couldn't verify" in answer


def test_agent_never_uses_free_form_final_to_add_attendee_in_unusual_wording():
    model = FakeModel([
        tool_call("find_free_slots", attendees=["priya", "sam"],
                  date="2026-11-03", duration_minutes=60, earliest="12:00"),
        final("Priya and Sam have a slot at 13:00. Bob will be in attendance."),
    ])
    answer = SchedulingAgent(model, Store.load()).run("Find an hour for Priya and Sam")
    assert "Bob" not in answer
    assert "Priya Raman, Sam Okafor" in answer


def test_agent_rejects_tool_window_that_overlaps_busy_calendar(monkeypatch):
    from scheduler import agent as agent_module

    monkeypatch.setitem(
        agent_module.TOOLS, "find_free_slots",
        lambda store, **kwargs: [{"start": "09:00", "end": "10:00"}],
    )
    model = FakeModel([
        tool_call("find_free_slots", attendees=["sam"],
                  date="2026-11-03", duration_minutes=60),
        final("Sam is available from 09:00 to 10:00."),
    ])
    answer = SchedulingAgent(model, Store.load()).run("Find an hour with Sam")
    assert "can't confirm a meeting" in answer
    assert "09:00–10:00" not in answer
