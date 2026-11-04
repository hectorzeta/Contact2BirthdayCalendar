# Specification: contactsToCalendar.py

This file describes what the tool does and the exact output it must produce. Project rules and workflow are in `CLAUDE.md`.

## What the project is

A standard-library Python tool that turns a semicolon-delimited contacts CSV (Google Contacts export) into:
- a cleaned CSV with only First Name, Middle Name, Last Name and Birthday (empty rows dropped), and/or
- an iCalendar (`.ics`) file of yearly recurring birthday events.

## Input

- Semicolon-delimited CSV with a header row.
- Read with `utf-8-sig`, so a byte-order mark from exports is handled.
- Relevant columns: `First Name`, `Middle Name`, `Last Name`, `Birthday`. Other columns are ignored.
- A missing column is treated as empty.

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

- Semicolon-delimited, with the header `First Name;Middle Name;Last Name;Birthday`.
- Only those four columns, in that order.
- A row is dropped when all four values are empty after trimming spaces.
- Output uses the standard `csv` quoting rules.
- The tool prints the number of rows written.

## Command line

```
python3 contactsToCalendar.py [-i FILE] [--csv [FILE]] [--ics [FILE]]
```

| Option | Meaning | Default |
|---|---|---|
| `-i`, `--input FILE` | Contacts CSV to read | `contacts.csv` |
| `--csv [FILE]` | Write the cleaned CSV | `contacts_clean.csv` |
| `--ics [FILE]` | Write the calendar | `birthdays.ics` |

- `--csv` and `--ics` may both be given, and each writes its own file.
- With neither option, the calendar is written (same as `--ics`).
- `--help` lists all options and exits with code 0.
- A missing input file prints `Error: input file not found: <name>` to stderr and exits with code 1.

## Tests

The test suite checks this specification. The fixture is `tests/fixtures/example.csv` (fictional names), with expected cleaned output in `tests/expected/clean_example.csv`.
