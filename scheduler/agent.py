"""The scheduling agent: a bounded and defensive tool-calling loop."""

import json
import re
import queue
import threading

from .model import Model
from .prompts import build_system_prompt
from .store import Store
from .tools import TOOLS, UnknownPersonError

_TIME = r"(?:[01]\d|2[0-3]):[0-5]\d"
_TIME_RANGE_RE = re.compile(rf"(?P<start>\b{_TIME})\s*(?:-|–|—|\bto\b)\s*(?P<end>{_TIME}\b)", re.IGNORECASE)
_TIME_RE = re.compile(rf"\b{_TIME}\b")
_POSITIVE_AVAILABILITY_RE = re.compile(
    r"\b(available|free|works for|can meet|meeting is possible|both can meet)\b",
    re.IGNORECASE,
)


class SchedulingAgent:
    def __init__(self, model: Model, store: Store, today: str = "2026-11-02",
                 max_turns: int = 8, model_timeout_seconds: float = 30.0):
        if not isinstance(max_turns, int) or isinstance(max_turns, bool) or max_turns < 1:
            raise ValueError("max_turns must be a positive integer")
        if (not isinstance(model_timeout_seconds, (int, float))
                or isinstance(model_timeout_seconds, bool) or model_timeout_seconds <= 0):
            raise ValueError("model_timeout_seconds must be positive")
        self.model, self.store, self.today, self.max_turns = model, store, today, max_turns
        self.model_timeout_seconds = float(model_timeout_seconds)
        # A timed-out synchronous model call cannot be forcibly killed in Python.
        # A daemon worker prevents it blocking process exit; this lock prevents
        # repeated requests from accumulating additional stuck calls on this agent.
        self._model_call_lock = threading.Lock()

    def _complete_with_timeout(self, messages: list[dict]) -> str:
        """Call a synchronous model with a bounded wait."""
        if not self._model_call_lock.acquire(blocking=False):
            raise TimeoutError("A previous model call is still running")
        outcome: queue.Queue = queue.Queue(maxsize=1)

        def invoke() -> None:
            try:
                outcome.put((True, self.model.complete(messages)))
            except BaseException as exc:
                outcome.put((False, exc))
            finally:
                self._model_call_lock.release()

        threading.Thread(target=invoke, name="scheduler-model-call", daemon=True).start()
        try:
            succeeded, value = outcome.get(timeout=self.model_timeout_seconds)
        except queue.Empty as exc:
            raise TimeoutError("Model call timed out") from exc
        if not succeeded:
            raise value
        if not isinstance(value, str):
            raise TypeError("Model response must be text")
        return value

    def _directory_names(self) -> dict[str, str]:
        """Map case-folded directory names/IDs to employee IDs."""
        names: dict[str, str] = {}
        for person in self.store.people:
            if not isinstance(person, dict) or not isinstance(person.get("id"), str):
                continue
            names[person["id"].casefold()] = person["id"]
            if isinstance(person.get("name"), str):
                names[person["name"].casefold()] = person["id"]
        return names

    def _validate_final_answer(
        self,
        answer: str,
        verified_windows: dict[tuple[str, str], set[str]],
        last_verified_attendees: set[str],
        availability_checked: bool,
    ) -> str | None:
        """Return a safe failure message if the final answer overclaims evidence."""
        claims_availability = bool(_POSITIVE_AVAILABILITY_RE.search(answer))
        if claims_availability and not availability_checked:
            return "I can't confirm a meeting until I check the attendees' calendars. Please try again."
        if claims_availability and not verified_windows:
            return "I couldn't confirm an available meeting time from the calendar results. Please try again."

        # Verify complete ranges as pairs. Checking each endpoint independently is
        # insufficient: two endpoints could come from different valid windows.
        ranges = list(_TIME_RANGE_RE.finditer(answer))
        for match in ranges:
            pair = (match.group("start"), match.group("end"))
            if pair not in verified_windows:
                return "I couldn't verify that complete meeting time against the calendar results. Please try again."

        # Any other mentioned time is interpreted as a proposed start time. It
        # must be the start of at least one complete window returned by the tool.
        remainder = answer
        for match in reversed(ranges):
            remainder = remainder[:match.start()] + (" " * (match.end() - match.start())) + remainder[match.end():]
        starts = {start for start, _ in verified_windows}
        for match in _TIME_RE.finditer(remainder):
            if match.group(0) not in starts:
                return "I couldn't verify every proposed meeting time against the calendar results. Please try again."

        # Names in the directory must belong to the attendee set for the verified
        # availability query. Also catch common unsupported name claims such as
        # "Bob is available" and "meeting with Bob".
        directory_names = self._directory_names()
        mentioned_ids = {
            employee_id for name, employee_id in directory_names.items()
            if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", answer, re.IGNORECASE)
        }
        if mentioned_ids and not mentioned_ids.issubset(last_verified_attendees):
            return "I couldn't verify that every named attendee belongs to the checked meeting. Please try again."

        name_patterns = [
            re.compile(r"\bwith\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b"),
            re.compile(r"\b(?:includes?|including|invite(?:d)?|attendee(?:s)?|participants?)\s+(?:is\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b"),
            re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?:is|are|will be|will attend|will join|will participate|is attending|are attending|can meet|works|is invited)\b"),
        ]
        known_display_names = {
            person["name"].casefold() for person in self.store.people
            if isinstance(person, dict) and isinstance(person.get("name"), str)
        }
        known_ids = {employee_id.casefold() for employee_id in directory_names.values()}
        for pattern in name_patterns:
            for match in pattern.finditer(answer):
                candidate = match.group(1).casefold()
                if candidate not in known_display_names and candidate not in known_ids:
                    return "I couldn't verify a named attendee in that response. Please check the directory and try again."
                employee_id = directory_names.get(candidate)
                if employee_id is not None and employee_id not in last_verified_attendees:
                    return "I couldn't verify that every named attendee belongs to the checked meeting. Please try again."

        return None

    def run(self, user_request: str) -> str:
        """Handle one request and return a controlled message for invalid model output."""
        messages = [
            {"role": "system", "content": build_system_prompt(self.store.people, self.today)},
            {"role": "user", "content": user_request},
        ]
        verified_windows: dict[tuple[str, str], set[str]] = {}
        last_verified_attendees: set[str] = set()
        availability_checked = False
        for _ in range(self.max_turns):
            try:
                raw = self._complete_with_timeout(messages)
            except Exception:
                return "Sorry, I couldn't complete the scheduling request in time. Please try again."
            try:
                action = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return "Sorry, I couldn't understand the scheduling response. Please try again."
            if not isinstance(action, dict):
                return "Sorry, I received an invalid scheduling response. Please try again."
            if set(action) == {"final"}:
                if not isinstance(action["final"], str):
                    return "Sorry, I received an invalid final response. Please try again."
                failure = self._validate_final_answer(
                    action["final"], verified_windows, last_verified_attendees, availability_checked
                )
                return failure or action["final"]
            if set(action) != {"tool", "args"}:
                return "Sorry, I received an invalid tool request. Please try again."
            tool_name, args = action["tool"], action["args"]
            if not isinstance(tool_name, str) or tool_name not in TOOLS:
                return "Sorry, the assistant requested an unsupported tool. Please try again."
            if not isinstance(args, dict):
                return "Sorry, the assistant supplied invalid tool arguments. Please try again."
            messages.append({"role": "assistant", "content": raw})
            # Do not let evidence from an earlier successful query survive a new
            # availability query that fails validation.
            if tool_name == "find_free_slots":
                availability_checked = False
                verified_windows = {}
                last_verified_attendees = set()
            try:
                result = TOOLS[tool_name](self.store, **args)
                # Validate tool output before treating it as evidence for a final answer.
                if not isinstance(result, list):
                    raise ValueError("Tool returned an invalid response")
                if tool_name == "find_free_slots":
                    validated_windows: dict[tuple[str, str], set[str]] = {}
                    attendees = args.get("attendees")
                    if not isinstance(attendees, list) or not attendees:
                        raise ValueError("Tool returned results for invalid attendees")
                    from .slots import time_to_minutes
                    for window in result:
                        if not isinstance(window, dict) or not {"start", "end"}.issubset(window):
                            raise ValueError("Tool returned a malformed meeting window")
                        start, end = window["start"], window["end"]
                        start_minutes, end_minutes = time_to_minutes(start), time_to_minutes(end)
                        if not (9 * 60 <= start_minutes < end_minutes <= 17 * 60):
                            raise ValueError("Tool returned a meeting outside working hours")
                        validated_windows[(start, end)] = set(attendees)
                    # A new availability query replaces the previous evidence;
                    # the final answer must be grounded in one coherent result.
                    verified_windows = validated_windows
                    last_verified_attendees = set(attendees)
                    availability_checked = True
            except UnknownPersonError:
                return ("I couldn't find one or more requested attendees in the employee "
                        "directory. Please check their names and try again.")
            except TypeError:
                result = {"error": "Invalid tool arguments. Check required fields and argument types."}
            except ValueError as exc:
                result = {"error": str(exc)}
            except Exception:
                result = {"error": "The tool failed unexpectedly."}
            try:
                tool_content = json.dumps(result)
            except (TypeError, ValueError):
                tool_content = json.dumps({"error": "Tool returned a non-serializable response."})
                if tool_name == "find_free_slots":
                    availability_checked = False
                    verified_windows = {}
                    last_verified_attendees = set()
            messages.append({"role": "tool", "content": tool_content})
        return ("Sorry, I couldn't finish the scheduling request within the allowed number "
                "of steps. Please try simplifying the request.")
