# Engineering Notes

## Problems found

- **The final valid window was skipped.** `find_free_windows` used an exclusive upper bound that omitted a candidate ending exactly at `end_slot`. Fixed the range and updated the existing afternoon test to include the valid 16:30–17:00 option. The test change is intentional: the old expected result encoded the bug.
- **Duration checks could miss valid meetings or misrepresent conflicts.** A 45-minute request was treated as one 30-minute slot. The search now keeps candidate starts aligned to the 30-minute grid but checks actual busy intervals at minute precision using half-open intervals. The exact requested end time is returned, so a meeting ending at 13:45 is allowed when another starts at 13:45, while an event starting at 13:44 blocks it.
- **Unknown employees appeared free.** Missing calendar entries defaulted to no busy blocks, so an unknown ID could look available. Tool calls now resolve every attendee against the directory and fail explicitly for unknown IDs. Empty attendee lists are rejected.
- **Bounds and inputs were not validated.** Added validation for clock values, dates, duration, optional result limits, and inconsistent availability inputs. Earliest bounds are aligned inward so results cannot start before the requested time.
- **The agent trusted every model response.** Added checks for malformed JSON, unexpected response shapes, unknown tools, invalid arguments, and tool errors. Unknown-person errors stop the request instead of allowing a later model response to quietly proceed.
- **The agent loop was unbounded.** Added a configurable maximum number of turns and a controlled message when the limit is reached.
- **Model-generated final answers could invent people or time ranges.** Regex-based natural-language checks cannot reliably catch every possible phrasing. After a successful availability query, the agent now ignores the model's free-form confirmation and renders the response from validated attendee IDs, date, duration, and exact windows. This means an unverified name in the model's final text cannot leak into the meeting confirmation. Before using results, the agent checks the full start/end pair, requested duration and bounds, slot-grid alignment, known attendees, and exact overlap against each attendee's source calendar. If tool output fails validation, it is not used as availability evidence.
- **A model call could block indefinitely.** The agent now bounds each synchronous model call with a configurable timeout; the OpenAI-compatible HTTP adapter also passes its timeout to `urlopen`. A timed-out Python thread cannot be forcibly killed, so the worker is daemonized and further calls on that agent are rejected while the timed-out call remains stuck.

## My addition

- Added an optional `limit` argument to `find_free_slots`. It is applied only after all matching windows are computed and ordered, so default behavior still returns every valid window. This helps callers request a concise shortlist without silently truncating normal results.
- Added tests for result limiting, ordering, unknown attendees, minute-precision overlap boundaries, duration handling, malformed model/tool responses, spoofed availability results, deterministic final rendering, working-day boundaries, model-call timeouts, and loop termination.

## How I used AI tools

- Used ChatGPT to help review the implementation, identify edge cases, and draft regression tests. I ran the tests and reviewed the changed code rather than accepting suggestions blindly.
- I considered making a small default cap on returned meeting options, but rejected that approach because the assignment explicitly requires not missing valid times. The implemented limit is opt-in and is applied only when requested.

## What I would do next

- Add property-based tests for combinations of busy intervals, duration lengths, and day boundaries.
- If the product later needs richer conversational confirmations, build them from a typed verified result object rather than allowing free-form model text to assert attendees or availability.
- Add per-tool execution timeouts if tools become blocking or perform network I/O. The model-call timeout cannot forcibly terminate a synchronous Python thread; the daemon worker can continue until the underlying call returns.

## Deliberately left alone

- Did not add a UI, calendar writes, time-zone support, a real-model dependency, or other out-of-scope features.
