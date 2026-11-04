# hza-scripts

Small utility scripts for HZA.

## contactsToCalendar.py

Converts a contacts export into a calendar file of yearly recurring birthday events.

It reads a semicolon-delimited CSV with `First Name`, `Last Name` and `Birthday` columns, and writes an iCalendar (`.ics`) file that most calendar apps (Google Calendar, Apple Calendar, Outlook) can import.

### Birthday formats

| Format | Example | Result |
|---|---|---|
| `--MM-DD` (no year) | `--03-31` | Yearly event on that date, title without a year |
| `DD/MM/YYYY` | `15/03/1990` | Yearly event on that date, title includes the birth year, e.g. `(1990)` |
| `YYYY-MM-DD` (ISO) | `1990-03-15` | Same as above |

- `--02-29` (Feb 29) is placed on the next leap year, so the event repeats only in leap years.
- Rows with no birthday are skipped.
- Rows with an unparseable date are skipped, and a message is printed naming the contact.

### Usage

Requires Python 3 (standard library only, no packages to install).

1. Put your contacts export in the project folder as `contacts.csv`.
2. Choose what to generate:

   ```bash
   # Birthday calendar (writes birthdays.ics)
   python3 contactsToCalendar.py --ics

   # Cleaned CSV with only First Name, Middle Name, Last Name and Birthday (writes contacts_clean.csv)
   python3 contactsToCalendar.py --csv

   # Both, with custom file names
   python3 contactsToCalendar.py -i my_contacts.csv --csv cleaned.csv --ics out.ics
   ```

3. Import the `.ics` file into your calendar app.

Run `python3 contactsToCalendar.py --help` for all options:

| Option | Meaning |
|---|---|
| `-i`, `--input FILE` | Contacts CSV to read (default `contacts.csv`) |
| `--csv [FILE]` | Write a cleaned CSV, dropping empty rows (default `contacts_clean.csv`) |
| `--ics [FILE]` | Write a birthday calendar (default `birthdays.ics`) |

### Tests

The tests use only the Python standard library. Run them from the project folder:

```bash
python3 -m unittest discover -s tests -v
```

The tests live in `tests/`:

| Path | Purpose |
|---|---|
| `tests/test_contacts_to_calendar.py` | All test cases |
| `tests/fixtures/example.csv` | Sample Google Contacts export used as test input |
| `tests/expected/clean_example.csv` | Expected output of `--csv` for the sample file |


### Files

| File | Purpose |
|---|---|
| `contactsToCalendar.py` | The script |
| `contacts.csv` | Input contacts export (personal data; see below) |
| `birthdays.ics` | Generated calendar output (personal data; see below) |
| `example_birthdays.ics` | Example of a generated calendar event, for reference |

### Privacy

`contacts.csv` and `birthdays.ics` contain personal information about real people. Keep them out of public repositories and shared locations, or add them to `.gitignore`.

### Editor setup

`.vscode/launch.json` contains a debug configuration that runs the currently open Python file from the project folder.
