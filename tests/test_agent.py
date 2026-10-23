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

    assert answer == "13:00 works for both."
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
    assert "couldn't verify every time" in answer
