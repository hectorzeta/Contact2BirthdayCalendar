# Intent: skip birthdays already in the calendar

Status: confirmed by the user.

## Statement of intent

- **Outcome:** A new function that compares the generated birthday events with an exported calendar `.ics` and writes only the events that aren't already in the export. It lives in its own function, separate from the existing calendar-generation code.
- **CLI:** A new option, `--calendar FILE`, takes the exported calendar. When it's given, the tool writes both `birthdays.ics` (all generated events) and `birthdays_new.ics` (only the new events). It works with or without `--ics`, and `birthdays.ics` is still written.
- **User:** The project owner, when importing birthdays into a calendar and not wanting duplicates.
- **Why now:** Google no longer syncs birthdays to the calendar, so birthdays are imported by hand. Re-importing ones already present would clutter the calendar.
- **Success:** With `--calendar`, both files are written. `birthdays_new.ics` holds only the new events, and `birthdays.ics` matches a normal run.
- **Match rule:** An event is "already there" when the title and date match. Month and day are compared, and the year is ignored.
- **Constraint:** Standard library only. The rules in `CLAUDE.md` still apply.
- **Out of scope:** Changing `birthdays.ics` in place, deleting events from the calendar, fetching the calendar through the Google API, and fuzzy title matching.

## Open items for the spec

- Whether the match compares the title exactly or after trimming spaces.
- How the export's `DTSTART` forms (`VALUE=DATE`, date-time) are read when matching.
