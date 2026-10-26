# Engineering Notes

## Problems found

- **The final valid window was skipped.** `find_free_windows` used an exclusive upper bound that omitted a candidate ending exactly at `end_slot`. Fixed the range and updated the existing afternoon test to include the valid 16:30–17:00 option. The test change is intentional: the old expected result encoded the bug.
- **Durations were rounded down.** A 45-minute request was treated as one 30-minute slot. Durations are now validated as positive integers, the availability check conservatively reserves every 30-minute slot touched, and the returned end time reflects the requested duration.
- **Unknown employees appeared free.** Missing calendar entries defaulted to no busy blocks, so an unknown ID could look available. Tool calls now resolve every attendee against the directory and fail explicitly for unknown IDs. Empty attendee lists are rejected.
- **Bounds and inputs were not validated.** Added validation for clock values, dates, duration, optional result limits, and inconsistent availability inputs. Earliest bounds are aligned inward so results cannot start before the requested time.
- **The agent trusted every model response.** Added checks for malformed JSON, unexpected response shapes, unknown tools, invalid arguments, and tool errors. Unknown-person errors stop the request instead of allowing a later model response to quietly proceed.
- **The agent loop was unbounded.** Added a configurable maximum number of turns and a controlled message when the limit is reached.
- **Final answers could claim unverified times or attendees.** The agent now validates complete start/end pairs against an exact window returned by the most recent availability query, checks proposed start times, and rejects known or likely named attendees who were not in the verified attendee set. Malformed tool results are not accepted as availability evidence. These checks are deliberately conservative: ambiguous phrasing returns a safe failure rather than an unsupported confirmation.
- **A model call could block indefinitely.** The agent now bounds each synchronous model call with a configurable timeout; the OpenAI-compatible HTTP adapter also passes its timeout to `urlopen`. A timed-out Python thread cannot be forcibly killed, so the worker is daemonized and further calls on that agent are rejected while the timed-out call remains stuck.

## My addition

- Added an optional `limit` argument to `find_free_slots`. It is applied only after all matching windows are computed and ordered, so default behavior still returns every valid window. This helps callers request a concise shortlist without silently truncating normal results.
- Added tests for result limiting, ordering, unknown attendees, duration handling, malformed model/tool responses, exact time-range verification, unverified attendee claims, working-day boundaries, model-call timeouts, and loop termination.

## How I used AI tools

- Used ChatGPT to help review the implementation, identify edge cases, and draft regression tests. I ran the tests and reviewed the changed code rather than accepting suggestions blindly.
- I considered making a small default cap on returned meeting options, but rejected that approach because the assignment explicitly requires not missing valid times. The implemented limit is opt-in and is applied only when requested.

## What I would do next

- Add property-based tests for combinations of busy intervals, duration lengths, and day boundaries.
- Improve natural-language entity detection beyond common attendee-claim patterns; free-text name detection cannot guarantee perfect coverage for every phrasing.
- Add per-tool execution timeouts if tools become blocking or perform network I/O.

## Deliberately left alone

- Did not add a UI, calendar writes, time-zone support, a real-model dependency, or other out-of-scope features.
