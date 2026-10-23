"""The scheduling agent: a bounded and defensive tool-calling loop."""

import json
import re
from .model import Model
from .prompts import build_system_prompt
from .store import Store
from .tools import TOOLS, UnknownPersonError


class SchedulingAgent:
    def __init__(self, model: Model, store: Store, today: str = "2026-11-02",
                 max_turns: int = 8):
        if not isinstance(max_turns, int) or isinstance(max_turns, bool) or max_turns < 1:
            raise ValueError("max_turns must be a positive integer")
        self.model, self.store, self.today, self.max_turns = model, store, today, max_turns

    def run(self, user_request: str) -> str:
        """Handle one request and return a controlled message for invalid model output."""
        messages = [
            {"role": "system", "content": build_system_prompt(self.store.people, self.today)},
            {"role": "user", "content": user_request},
        ]
        verified_windows: set[tuple[str, str]] = set()
        availability_checked = False
        for _ in range(self.max_turns):
            try:
                raw = self.model.complete(messages)
            except Exception:
                return "Sorry, I couldn't complete the scheduling request. Please try again."
            try:
                action = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return "Sorry, I couldn't understand the scheduling response. Please try again."
            if not isinstance(action, dict):
                return "Sorry, I received an invalid scheduling response. Please try again."
            if set(action) == {"final"}:
                if not isinstance(action["final"], str):
                    return "Sorry, I received an invalid final response. Please try again."
                answer = action["final"]
                times = re.findall(r"\b(?:[01]\d|2[0-3]):[0-5]\d\b", answer)
                claims_availability = bool(re.search(
                    r"\b(available|free|works for|can meet|meeting is possible)\b",
                    answer, re.IGNORECASE
                ))
                if claims_availability and not availability_checked:
                    return "I can't confirm a meeting until I check the attendees' calendars. Please try again."
                if times and any(
                    time not in {boundary for window in verified_windows for boundary in window}
                    for time in times
                ):
                    return "I couldn't verify every time in that response against the calendar results. Please try again."
                if claims_availability and not verified_windows:
                    return "I couldn't confirm an available meeting time from the calendar results. Please try again."
                return answer
            if set(action) != {"tool", "args"}:
                return "Sorry, I received an invalid tool request. Please try again."
            tool_name, args = action["tool"], action["args"]
            if not isinstance(tool_name, str) or tool_name not in TOOLS:
                return "Sorry, the assistant requested an unsupported tool. Please try again."
            if not isinstance(args, dict):
                return "Sorry, the assistant supplied invalid tool arguments. Please try again."
            messages.append({"role": "assistant", "content": raw})
            try:
                result = TOOLS[tool_name](self.store, **args)
                if tool_name == "find_free_slots":
                    availability_checked = True
                    if isinstance(result, list):
                        verified_windows.update(
                            (window["start"], window["end"])
                            for window in result
                            if isinstance(window, dict)
                            and isinstance(window.get("start"), str)
                            and isinstance(window.get("end"), str)
                        )
            except UnknownPersonError:
                return ("I couldn't find one or more requested attendees in the employee "
                        "directory. Please check their names and try again.")
            except TypeError:
                result = {"error": "Invalid tool arguments. Check required fields and argument types."}
            except ValueError as exc:
                result = {"error": str(exc)}
            except Exception:
                result = {"error": "The tool failed unexpectedly."}
            messages.append({"role": "tool", "content": json.dumps(result)})
        return ("Sorry, I couldn't finish the scheduling request within the allowed number "
                "of steps. Please try simplifying the request.")
