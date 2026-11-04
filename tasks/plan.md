# Implementation Plan: Calendar dedupe (`--calendar`)

Branch: `feature/calendar-dedupe` (from `main`)
Spec: `docs/SPEC.md`, section "Calendar dedupe (`--calendar`)"
Task list: `tasks/todo.md`

## Overview

When `--calendar FILE` is given, the tool writes `birthdays_new.ics` containing only the generated birthday events that are not already in the exported calendar. `birthdays.ics` is written as before. Matching uses month and day, and a title made of name and year, following the spec.

## Architecture Decisions

- **Split event building from writing.** Today `create_birthday_calendar` parses the CSV and writes the file in one function. Extract `build_birthday_events(csv_file)`, which returns a list of event records. Both `birthdays.ics` and `birthdays_new.ics` are written from those records by one writer, `write_calendar(events, path)`. This keeps the two outputs consistent and lets the dedupe step work on records, not text.
- **Keep the existing output byte-compatible apart from `DTSTAMP`.** Existing tests guard the event content and format. The refactor must not change them.
- **Export parsing is its own function, `read_export_events(path)`.** It returns simple records (name, year or None, month, day) from `VEVENT` blocks. It handles `utf-8-sig`, RFC 5545 unfolding, CRLF or LF, and skips events with no readable `DTSTART`.
- **Title matching is a pure function.** `titles_match(generated, export)` applies the rules in the spec: name case-insensitive with spaces normalised; year compared only when both sides have one. It is tested on its own.
- **Matching is one-to-one, greedy, in input order.** For each generated event, the first unused export event that matches is consumed. This satisfies the spec's rule for identical events. The year rule is not transitive, so greedy matching is the defined behaviour.
- **Validate the export file before writing anything.** A missing `--calendar` file exits with code 1 before `birthdays.ics` is written, as the spec requires.
- **No new dependencies.** Standard library only.

## Task List

### Phase 1: Refactor (no behaviour change)

- [x] Task 1: Extract `build_birthday_events` and `write_calendar`

### Phase 2: New pieces (independent of each other, both depend on Task 1 only for shared types)

- [x] Task 2: Export reader `read_export_events`
- [x] Task 3: Title matching `titles_match` and title splitters

### Checkpoint: Building blocks
- [x] All existing tests pass
- [x] Ruff passes
- [x] Unit tests for Tasks 2 and 3 pass

### Phase 3: Dedupe logic

- [x] Task 4: One-to-one dedupe `find_new_events`

### Phase 4: CLI integration

- [x] Task 5: `--calendar` option, output files, error handling, messages

### Checkpoint: Feature complete
- [x] All spec success criteria have a passing test
- [x] `birthdays.ics` from a `--calendar` run matches a plain run apart from `DTSTAMP`
- [x] Ruff passes; full suite passes

### Phase 5: Docs and fixture

- [x] Task 6: Fictional export fixture and README usage

### Checkpoint: Ready for PR
- [x] Run `ruff check .` and `python3 tests/run_tests.py`
- [ ] Review diff against the spec

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Refactor changes existing `birthdays.ics` output | High | Task 1 is a pure refactor, guarded by existing tests; compare output of old and new code on the example fixture before and after |
| Google export format differs from the fixture (for example `DTSTART` as date-time with `TZID`) | Medium | Reader handles both `VALUE=DATE` and date-time values by taking the `YYYYMMDD` part; a test covers a date-time export |
| Greedy one-to-one matching gives a different result from the spec's wording in an edge case | Low | Tests cover identical events, partial matches, and export with more copies than generated |
| Real personal data ends up in fixtures or tests | High | Fixtures use only the fictional names already in `tests/fixtures/`; reviewed in Task 6 |

## Open Questions

None. Spec decisions are recorded in `docs/SPEC.md` under "Decisions".
