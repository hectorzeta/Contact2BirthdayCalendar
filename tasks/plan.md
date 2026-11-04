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


---

# Implementation Plan: Column separators (issue #4)

Branch: `feature/other-csv-separators` (from `main`)
Spec: `docs/SPEC.md`, sections "Input", "Column separator", "Cleaned CSV output", "Command line"
Task list: `tasks/todo.md` (section "Column separators (issue #4)")

## Overview

The contacts input may use `;`, `,` or tab as its column separator. The tool detects it from the header line, or the user sets it with `--delimiter`. The cleaned CSV keeps the input's separator. The `--calendar` export is not affected.

## Architecture Decisions

- **Detection is one function, `detect_delimiter(path)`.** It reads the first line with `utf-8-sig`, splits it with each candidate, and returns the one with the most columns. It raises `ValueError` with the spec's message for "could not detect" and "ambiguous", so `main` only has to print and exit.
- **The separator is resolved once in `main`.** Either `--delimiter` or `detect_delimiter` is called, and the result is passed to `build_birthday_events` and `clean_contacts_csv`. Both get a `delimiter=';'` default, so existing calls and tests keep working.
- **`--delimiter` maps names to characters in one place.** `tab` becomes `\t`. argparse `choices` rejects other values with exit code 2.
- **No new dependencies.** Standard library `csv` only.

## Task List

### Phase 1: Detection and option

- [x] Task 7: `detect_delimiter(path)` and its error messages
- [x] Task 8: `--delimiter` option and the value mapping

### Checkpoint: Detection ready
- [x] Tasks 7–8 tests pass, ruff passes

### Phase 2: Use the separator

- [x] Task 9: Pass the separator through `build_birthday_events` and `clean_contacts_csv`; resolve it in `main`

### Checkpoint: Feature complete
- [x] Every success criterion in the spec has a passing test
- [x] Comma and tab copies of `example.csv` give the same calendar as the semicolon version

### Phase 3: Docs

- [x] Task 10: README options table and usage for `--delimiter`

### Checkpoint: Ready for PR
- [x] `ruff check .` and the full suite pass
- [ ] Diff reviewed against `docs/SPEC.md`

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| A tab or comma appears inside a quoted header name, which confuses detection | Medium | Detection splits the header with the `csv` module, so quoted fields are respected |
| Changing `clean_contacts_csv` changes the default output | High | The default stays `;`; a test checks a semicolon input gives byte-identical output to the current version |
| Existing calls to `build_birthday_events` and `clean_contacts_csv` break | Medium | New parameter has a default of `';'`; existing tests stay unchanged |

## Open Questions

None.
