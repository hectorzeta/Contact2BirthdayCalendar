# Tasks: Calendar dedupe (`--calendar`)

Branch: `feature/calendar-dedupe`. Spec: `docs/SPEC.md`. Plan: `tasks/plan.md`.

Each task is implemented by a subagent, one at a time. After each task the main agent runs the verification steps before ticking the box.

---

## Task 1: Extract `build_birthday_events` and `write_calendar`

**Description:** Split `create_birthday_calendar` into three parts: `build_birthday_events(csv_file)` returns a list of event records (UID, date, name, birth year or None, summary text); `write_calendar(events, path, dtstamp)` writes the calendar file from those records; `create_birthday_calendar(csv_file, ics_file)` keeps its current signature and calls the two. No change in output apart from the new function boundaries.

**Acceptance criteria:**
- [ ] `build_birthday_events` and `write_calendar` exist as module-level functions
- [ ] `create_birthday_calendar` keeps its signature and produces the same events, UIDs and line format as before
- [ ] Skipped-date messages are printed as before
- [ ] No new public behaviour

**Verification:**
- [ ] `python3 tests/run_tests.py` passes with no test changes
- [ ] `ruff check .` passes
- [ ] Output of `create_birthday_calendar` on `tests/fixtures/example.csv` is identical to the output from `main` apart from `DTSTAMP`

**Dependencies:** None

**Files likely touched:**
- `contactsToCalendar.py`

**Estimated scope:** Small

---

## Task 2: Export reader `read_export_events`

**Description:** Add `read_export_events(path)` that reads an exported calendar `.ics` and returns one record per `VEVENT`: name, year or None, month, day. Title parsing uses the splitter from Task 3 once available; this task returns the raw `SUMMARY` text and the date only. It reads with `utf-8-sig`, unfolds RFC 5545 lines, accepts CRLF or LF, ignores non-`VEVENT` components, and skips an event with no readable `DTSTART` (without stopping).

**Acceptance criteria:**
- [ ] Returns one record per `VEVENT` with `summary`, `month`, `day`
- [ ] Reads `DTSTART;VALUE=DATE:YYYYMMDD` and date-time `DTSTART` (taking the date part, ignoring time and `TZID`)
- [ ] Unfolds continuation lines
- [ ] Accepts LF-only files
- [ ] Skips an event with no `DTSTART` and continues
- [ ] Missing file raises `FileNotFoundError`

**Verification:**
- [ ] Unit tests in `tests/test_contacts_to_calendar.py` for each criterion, using small fictional `.ics` files written to a temp directory
- [ ] `python3 tests/run_tests.py` passes
- [ ] `ruff check .` passes

**Dependencies:** Task 1

**Files likely touched:**
- `contactsToCalendar.py`
- `tests/test_contacts_to_calendar.py`

**Estimated scope:** Small

---

## Task 3: Title matching `titles_match`

**Description:** Add `split_generated_title(title)` (removes leading `Birthday: ` case-insensitively and a trailing ` (YYYY)`, returns name and year or None), `split_export_title(summary)` (a trailing four-digit year, optionally in parentheses, becomes the year; the rest is the name), and `titles_match(generated_title, export_summary)` applying the spec rules: name compared case-insensitively after trimming and collapsing spaces; years compared only when both sides have one.

**Acceptance criteria:**
- [ ] `Birthday: Ann Lee (1990)` splits to name `Ann Lee`, year 1990
- [ ] `birthday: ann lee (1990)` matches `Ann Lee 1990`
- [ ] `Birthday: Ann Lee (1990)` matches `Ann Lee` (no year on export side)
- [ ] `Birthday: Ann Lee (1990)` does not match `Ann Lee 1985`
- [ ] `Joe Doe (2000)` and `Joe Doe 2000` both give year 2000
- [ ] Repeated spaces and surrounding spaces are ignored in names
- [ ] A title with no year on either side matches on name alone

**Verification:**
- [ ] Unit tests for each criterion
- [ ] `python3 tests/run_tests.py` passes
- [ ] `ruff check .` passes

**Dependencies:** Task 1 (module layout only)

**Files likely touched:**
- `contactsToCalendar.py`
- `tests/test_contacts_to_calendar.py`

**Estimated scope:** Small

---

## Checkpoint: Building blocks

- [ ] Tasks 1–3 complete
- [ ] All existing tests pass
- [ ] `ruff check .` passes

---

## Task 4: One-to-one dedupe `find_new_events`

**Description:** Add `find_new_events(generated_events, export_events)` returning `(new_events, matched_count)`. For each generated event in order, find the first unused export event with the same month and day and a matching title (via `titles_match`). If found, mark that export event used and count a match; otherwise the generated event is new. Identical generated events are removed only as many times as the export contains matches.

**Acceptance criteria:**
- [ ] Same title and month-day: generated event removed
- [ ] Same title, different month-day: kept
- [ ] Same month-day, different title: kept
- [ ] Year does not affect date match
- [ ] Two identical generated events and one matching export event: one removed, one kept
- [ ] Two identical generated events and two matching export events: both removed
- [ ] Export events are not modified

**Verification:**
- [ ] Unit tests for each criterion
- [ ] `python3 tests/run_tests.py` passes
- [ ] `ruff check .` passes

**Dependencies:** Tasks 2, 3

**Files likely touched:**
- `contactsToCalendar.py`
- `tests/test_contacts_to_calendar.py`

**Estimated scope:** Small

---

## Checkpoint: Logic complete

- [ ] Tasks 1–4 complete
- [ ] All unit tests pass
- [ ] `ruff check .` passes

---

## Task 5: `--calendar` option, output files, errors, messages

**Description:** Add `--calendar FILE` to the argument parser and its help text. In `main`: if `--calendar` is given, read and validate the export first (missing file → `Error: calendar file not found: <name>` on stderr, exit 1, nothing written). Then build events, write `birthdays.ics` as a normal run would, and write `birthdays_new.ics` with only the new events. `--calendar` works with or without `--ics`. Print `Calendar file created: birthdays_new.ics (<n> new, <m> already in calendar)`. The output file name is fixed to `birthdays_new.ics` in the current directory. `--csv` still works alongside it.

**Acceptance criteria:**
- [ ] `--calendar FILE` appears in `--help`
- [ ] With `--calendar`, both `birthdays.ics` and `birthdays_new.ics` exist after the run
- [ ] `birthdays.ics` has the same events as a run without `--calendar`, differing at most in `DTSTAMP`
- [ ] `birthdays_new.ics` contains only the new events
- [ ] Missing calendar file: exit 1, error message, `birthdays.ics` not written
- [ ] Works with and without `--ics`
- [ ] Message text matches the spec
- [ ] The export file is not modified

**Verification:**
- [ ] CLI tests using subprocess, in a temp directory, with the fixture from Task 6 (or a temporary export created in the test until Task 6 is done)
- [ ] `python3 tests/run_tests.py` passes
- [ ] `ruff check .` passes

**Dependencies:** Tasks 1, 2, 4

**Files likely touched:**
- `contactsToCalendar.py`
- `tests/test_contacts_to_calendar.py`

**Estimated scope:** Medium

---

## Checkpoint: Feature complete

- [ ] Task 5 complete
- [ ] Every success criterion in `docs/SPEC.md` (Calendar dedupe) has a passing test
- [ ] `birthdays.ics` comparison with a plain run passes apart from `DTSTAMP`
- [ ] `ruff check .` and full suite pass

---

## Task 6: Fictional export fixture and README usage

**Description:** Add `tests/fixtures/calendar_export.ics`, a small Google-style export with fictional names covering: a match, a date mismatch, a title mismatch, a year mismatch, a date-time `DTSTART`, and an event with no `DTSTART`. Use it in the CLI tests. Update `README.md` with a `--calendar` usage example and a short note on what `birthdays_new.ics` is for. Also add the fixture to `tests/` documentation in `CLAUDE.md` only if the user confirms (CLAUDE.md changes need confirmation).

**Acceptance criteria:**
- [ ] Fixture uses only fictional names, and reuses names from `tests/fixtures/example.csv` where it matches
- [ ] CLI test runs `--calendar` against the fixture and checks the counts
- [ ] README has a usage example for `--calendar`
- [ ] README links the workflow to the new step (export contacts → run script with `--calendar` → import `birthdays_new.ics`)

**Verification:**
- [ ] `python3 tests/run_tests.py` passes
- [ ] `ruff check .` passes
- [ ] Manual read of the README section

**Dependencies:** Task 5

**Files likely touched:**
- `tests/fixtures/calendar_export.ics`
- `tests/test_contacts_to_calendar.py`
- `README.md`

**Estimated scope:** Small

---

## Checkpoint: Ready for PR

- [ ] All tasks complete
- [ ] `ruff check .` passes
- [ ] `python3 tests/run_tests.py` passes
- [ ] Diff reviewed against `docs/SPEC.md`
- [ ] No real names or personal data in any new file
