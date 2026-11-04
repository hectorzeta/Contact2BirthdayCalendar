# Specification: contactsToCalendar.py

This file describes what the tool does and the exact output it must produce. Project rules and workflow are in `CLAUDE.md`.

## What the project is

A standard-library Python tool that turns a semicolon-delimited contacts CSV (Google Contacts export) into:
- a cleaned CSV with only First Name, Middle Name, Last Name and Birthday (empty rows dropped), and/or
- an iCalendar (`.ics`) file of yearly recurring birthday events.

## Input

- CSV with a header row. The column separator is `;`, `,` or tab (see [Column separator](#column-separator)).
- Read with `utf-8-sig`, so a byte-order mark from exports is handled.
- Relevant columns: `First Name`, `Middle Name`, `Last Name`, `Birthday`. Other columns are ignored.
- A missing column is treated as empty.

## Column separator

The separator applies to the contacts input (`-i`) only. The calendar export read by `--calendar` is always `.ics`.

### Detection (default)

1. Read the first line (the header) of the input, after removing any byte-order mark.
2. Split that line with each candidate separator (`;`, `,`, tab) using the `csv` module.
3. Keep the candidates that give more than one column.
4. If no candidate gives more than one column, stop with `Error: could not detect the column separator in <file>; use --delimiter` on stderr, exit code 1.
5. If one candidate gives more columns than every other, use it.
6. If two or more candidates tie for the most columns, stop with `Error: ambiguous column separator in <file>; use --delimiter` on stderr, exit code 1.

### Explicit (`--delimiter`)

- `--delimiter VALUE` sets the separator and skips detection. `VALUE` is `;`, `,` or `tab` (case-insensitive).
- Any other value is rejected by the argument parser, which exits with code 2.

### Output

- The cleaned CSV (`--csv`) uses the same separator as the input. The header and the four columns are unchanged.

### Success criteria

- A comma-separated and a tab-separated copy of `tests/fixtures/example.csv` produce the same calendar as the semicolon version.
- A semicolon-separated input produces a cleaned CSV that is byte-identical to the current output (apart from the usual `csv` quoting, which is unchanged).
- A comma-separated input produces a cleaned CSV that uses `,` as the separator.
- `--delimiter` overrides detection: a file whose detection would be ambiguous is read correctly when `--delimiter` is given.
- A file with no detectable separator exits with code 1 and the message in the spec.
- An ambiguous file exits with code 1 and the message in the spec.
- An invalid `--delimiter` value exits with code 2.
- The `--calendar` export is read the same as before.

## Birthday formats

| Format | Example | Meaning |
|---|---|---|
| `DD/MM/YYYY` | `15/03/1990` | Full date, with year |
| ISO `YYYY-MM-DD` | `1990-03-15` | Full date, with year |
| `--MM-DD` | `--03-15` | Month and day only, no year |

- Leading and trailing spaces are ignored.
- Anything else is invalid (see below).

## Calendar (.ics) output

- Lines end with CRLF. Lines longer than 75 octets are folded, without splitting a UTF-8 character.
- The calendar starts with `BEGIN:VCALENDAR`, `PRODID:-//HZ//HZ//EN`, `VERSION:2.0` and `CALSCALE:GREGORIAN`.
- Each birthday is one `VEVENT` with:
  - `UID`: stable for a given row, based on the row position and its contents, with a `@contactsToCalendar` suffix.
  - `DTSTAMP`: UTC time of generation, `YYYYMMDDTHHMMSSZ`.
  - `DTSTART;VALUE=DATE:YYYYMMDD`: the all-day start date.
  - `RRULE:FREQ=YEARLY`.
  - `SUMMARY:Birthday: <First> <Last>` with ` (YYYY)` appended when a year is known.
- `SUMMARY` text is escaped: backslash, semicolon, comma and newline.
- Titles use First and Last name only; the Middle name is omitted. A missing part leaves no double space.
- Rows with no birthday are skipped without a message.

### Placeholder dates

- `--MM-DD`: the current year is used as the start date. The yearly `RRULE` repeats the event.
- Feb 29 without a year: the next leap year is used as the start date, so the event only repeats in leap years.
- Full dates keep their own year in `DTSTART` and in the title.

### Invalid dates

- A value that matches none of the formats is not an error. The tool prints `Skipping invalid date: <value> for <First> <Last>` and moves on.

## Cleaned CSV output (`--csv`)

- Uses the input's separator (see [Column separator](#column-separator)). The header is `First Name<sep>Middle Name<sep>Last Name<sep>Birthday`, for example `First Name;Middle Name;Last Name;Birthday` for a semicolon file.
- Only those four columns, in that order.
- A row is dropped when all four values are empty after trimming spaces.
- Output uses the standard `csv` quoting rules.
- The tool prints the number of rows written.

## Command line

```
python3 contactsToCalendar.py [-i FILE] [--delimiter VALUE] [--csv [FILE]] [--ics [FILE]] [--calendar FILE]
```

| Option | Meaning | Default |
|---|---|---|
| `-i`, `--input FILE` | Contacts CSV to read | `contacts.csv` |
| `--delimiter VALUE` | Column separator of the input: `;`, `,` or `tab`. Skips detection | detected |
| `--csv [FILE]` | Write the cleaned CSV | `contacts_clean.csv` |
| `--ics [FILE]` | Write the calendar | `birthdays.ics` |
| `--calendar FILE` | Exported calendar to compare against. Also writes `birthdays_new.ics` (see [Calendar dedupe](#calendar-dedupe---calendar)) | none |

- `--csv` and `--ics` may both be given, and each writes its own file.
- With neither option, the calendar is written (same as `--ics`).
- `--help` lists all options and exits with code 0.
- A missing input file prints `Error: input file not found: <name>` to stderr and exits with code 1.
- A separator that cannot be detected or is ambiguous exits with code 1 (see [Column separator](#column-separator)).

## Calendar dedupe (`--calendar`)

### Objective

Birthdays are imported into the calendar by hand, because Google no longer syncs them. Re-importing a birthday that is already in the calendar creates duplicates. When `--calendar FILE` is given, the tool also writes `birthdays_new.ics`, which holds only the generated birthdays that are not already in the exported calendar. The user is the project owner, who imports the file into their calendar app.

### Behavior

- Input: the generated events (the same events `--ics` produces) and the exported calendar file given by `--calendar`.
- Output: `birthdays.ics` is written as in a normal run. `birthdays_new.ics` is also written, containing only the generated events that have no match in the export.
- `--calendar` works with or without `--ics`. Either way `birthdays.ics` is written.
- The output file is always `birthdays_new.ics` in the current directory. It is not configurable in this version.
- The comparison runs in its own function, separate from the function that generates events.

### Matching rule

A generated event is "already there" when some event in the export has the same title and the same date:

- **Date:** compare month and day only. The year is ignored. The date is read from the `DTSTART` value of the export event, using its `YYYYMMDD` part (see Decisions for date-time values).
- **Title:** compare the name and the year, as follows.
  - Generated title: remove a leading `Birthday: ` (case-insensitive) and a trailing ` (YYYY)`. What remains is the name. The year, if present, is the year in parentheses.
  - Export title (`SUMMARY`): a leading `Birthday: ` (case-insensitive) is removed, as Google Calendar exports birthday events with that prefix. If the title then ends in a four-digit year, optionally in parentheses (for example `Joe Doe 2000` or `Joe Doe (2000)`), that year is the year of birth and the rest is the name. Otherwise the whole title is the name and there is no year.
  - Name: compared case-insensitively, after trimming surrounding spaces and collapsing repeated spaces.
  - Year: when both sides have a year, the two years must be equal. When either side has no year, the year is not compared.
- `UID`, `DTSTAMP` and all other properties are not compared.
- Matching is one-to-one: each export event matches at most one generated event. If two generated events are identical, one is removed only when the export contains two matching events.

### Export file

- Read with `utf-8-sig`, unfolded (RFC 5545 line folding) and read with CRLF or LF line endings.
- Only `VEVENT` blocks are used. Other components are ignored.
- A missing `--calendar` file exits with code 1 and prints `Error: calendar file not found: <name>` to stderr. `birthdays.ics` is not written in that case.
- A `VEVENT` with no readable `DTSTART` is skipped without stopping the run.

### Output messages

- `Calendar file created: birthdays_new.ics (<n> new, <m> already in calendar)`

### Success criteria

- With `--calendar`, both `birthdays.ics` and `birthdays_new.ics` exist after the run.
- `birthdays.ics` has the same events as the file a run without `--calendar` produces for the same input. The two files may differ only in `DTSTAMP`, which records the time of each run.
- An event whose title and month-day match an export event is absent from `birthdays_new.ics`.
- An event whose title matches but whose month and day differ stays in `birthdays_new.ics`.
- An event whose month and day match but whose title differs stays in `birthdays_new.ics`.
- The year does not affect the date: `Birthday: Ann Lee (1990)` matches an export event `Ann Lee` on the same month and day with no year.
- A different year in both titles prevents a match: `Birthday: Ann Lee (1990)` does not match an export event `Ann Lee 1985` on the same month and day.
- Name comparison ignores case: `birthday: ann lee (1990)` matches `Ann Lee 1990`.
- The export file is not modified.
- The new function has unit tests and is covered by the CLI tests.

### Boundaries

- **Always:** keep `birthdays.ics` written exactly as a normal run would. Use only fictional names in fixtures.
- **Ask first:** changing the matching rule, adding an option to choose the output file name, or changing how the export is read.
- **Never:** modify the exported calendar, delete or change events in the calendar, or call the Google API.

### Decisions

- **Export title format:** the export `SUMMARY` may start with `Birthday: `, which is removed on both sides. A trailing four-digit number is the year of birth (see Matching rule).
- **Case:** the name comparison ignores case.
- **Year:** when both titles have a year, the years must match. A title with no year matches on name and date alone.
- **Date-time values:** an export `DTSTART` with a time or `TZID` is matched on its date as written.

### Open questions

None.

## Tests

The test suite checks this specification. The fixture is `tests/fixtures/example.csv` (fictional names), with expected cleaned output in `tests/expected/clean_example.csv`.
