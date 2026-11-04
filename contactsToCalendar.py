# Converts a semicolon-delimited contacts CSV (with a "Birthday" column) into
# an iCalendar (.ics) file containing yearly recurring birthday events, and can
# also produce a cleaned CSV that keeps only the name and birthday columns.
#
# Run "python3 contactsToCalendar.py --help" for usage.
import argparse
import calendar
import csv
import datetime
import sys

DEFAULT_INPUT = 'contacts.csv'
DEFAULT_CSV_OUTPUT = 'contacts_clean.csv'
DEFAULT_ICS_OUTPUT = 'birthdays.ics'

# Date formats accepted for birthdays that include a year
FULL_DATE_FORMATS = ('%d/%m/%Y', '%Y-%m-%d')

def parse_full_date(value):
    """Parse a birthday with a year, trying each supported format in turn.

    Raises ValueError if none of the formats match.
    """
    for fmt in FULL_DATE_FORMATS:
        try:
            return datetime.datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unsupported date: {value}")

def create_birthday_calendar(csv_file, ics_file):
    """Read birthdays from csv_file and write them as recurring events to ics_file."""
    with open(ics_file, 'w', encoding='utf-8') as f:
        # iCalendar file header: start of calendar, product ID, and format version
        f.write("BEGIN:VCALENDAR\n")
        f.write("PRODID:-//HZ//HZ//EN\n")
        f.write("VERSION:2.0\n")

        # utf-8-sig also strips the byte-order mark that some exports (e.g. Google) add
        with open(csv_file, newline='', encoding='utf-8-sig') as file:
            # Each row becomes a dict keyed by header names; fields are separated by ';'
            reader = csv.DictReader(file,delimiter=";")
            for row in reader:
                # Skip rows without a birthday value
                birthday = row.get('Birthday', '').strip()
                if birthday:
                    birth_date = ""
                    birth_year = ""
                    try:
                        # Handle birthdays with no year (e.g., "--MM-DD")
                        # Use the current year as a placeholder so the event has a valid start date;
                        # RRULE below makes it repeat every year.
                        if birthday.startswith('--'):
                            month_day = birthday[2:]
                            year = datetime.date.today().year
                            # Feb 29 only exists in leap years, so use the next leap year as the
                            # placeholder; the yearly RRULE then only fires in leap years.
                            if month_day == '02-29':
                                while not calendar.isleap(year):
                                    year += 1
                            birth_date = datetime.datetime.strptime(f"{year}-{month_day}", '%Y-%m-%d').date()
                        else:
                            # Handle birthdays with a year: "DD/MM/YYYY" or ISO "YYYY-MM-DD"
                            birth_date = parse_full_date(birthday)
                            # Append the birth year to the event title, e.g. " (1990)"
                            birth_year = f" ({birth_date.year})"
                        # Write one VEVENT block: start date, yearly recurrence, and title
                        f.write("BEGIN:VEVENT\n")
                        f.write(f"DTSTART:{birth_date.strftime('%Y%m%d')}\n")
                        f.write("RRULE:FREQ=YEARLY\n")
                        # Join only non-empty name parts so a missing last name leaves no double space
                        name = ' '.join(p for p in (row.get('First Name') or '', row.get('Last Name') or '') if p)
                        f.write(f"SUMMARY:Birthday: {name}{birth_year}\n")
                        f.write("END:VEVENT\n")
                    except ValueError:
                        # strptime raises ValueError for malformed dates; report and skip the row
                        print(f"Skipping invalid date: {birthday} for {row.get('First Name', '')} {row.get('Last Name', '')}")

        # Close the calendar block
        f.write("END:VCALENDAR\n")
    print(f"Calendar file created: {ics_file}")

def clean_contacts_csv(csv_file, output_file):
    """Keep only the name and birthday columns from csv_file and drop empty rows.

    Writes the result to output_file as a semicolon-delimited CSV.
    Returns the number of rows written.
    """
    keep_columns = ['First Name', 'Middle Name', 'Last Name', 'Birthday']
    rows_written = 0

    with open(csv_file, newline='', encoding='utf-8-sig') as infile, \
         open(output_file, 'w', newline='', encoding='utf-8') as outfile:
        reader = csv.DictReader(infile, delimiter=";")
        writer = csv.DictWriter(outfile, fieldnames=keep_columns, delimiter=";")
        writer.writeheader()

        for row in reader:
            # Keep only the wanted columns; a missing column becomes an empty string
            kept = {col: (row.get(col) or '').strip() for col in keep_columns}
            # Skip rows where every kept column is empty
            if not any(kept.values()):
                continue
            writer.writerow(kept)
            rows_written += 1

    print(f"Cleaned contacts file created: {output_file} ({rows_written} rows)")
    return rows_written

def parse_args(argv=None):
    """Define and parse the command-line options."""
    parser = argparse.ArgumentParser(
        description="Work with a contacts CSV: write a cleaned CSV and/or a birthday calendar (.ics).",
        epilog=(
            "Examples:\n"
            "  python3 contactsToCalendar.py --ics\n"
            "  python3 contactsToCalendar.py --csv --ics\n"
            "  python3 contactsToCalendar.py -i my_contacts.csv --csv cleaned.csv --ics out.ics\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        '-i', '--input', default=DEFAULT_INPUT, metavar='FILE',
        help=f"semicolon-delimited contacts CSV to read (default: {DEFAULT_INPUT})",
    )
    parser.add_argument(
        '--csv', nargs='?', const=DEFAULT_CSV_OUTPUT, metavar='FILE',
        help=("generate a cleaned CSV with only First Name, Middle Name, Last Name and "
              f"Birthday, and no empty rows (default output: {DEFAULT_CSV_OUTPUT})"),
    )
    parser.add_argument(
        '--ics', nargs='?', const=DEFAULT_ICS_OUTPUT, metavar='FILE',
        help=("generate an iCalendar file of yearly recurring birthday events "
              f"(default output: {DEFAULT_ICS_OUTPUT})"),
    )
    return parser.parse_args(argv)

def main(argv=None):
    """Entry point: run the requested outputs and return an exit code."""
    args = parse_args(argv)

    if args.csv is None and args.ics is None:
        print("Nothing to do: choose --csv, --ics, or both. Use --help for details.", file=sys.stderr)
        return 1

    try:
        if args.csv is not None:
            clean_contacts_csv(args.input, args.csv)
        if args.ics is not None:
            create_birthday_calendar(args.input, args.ics)
    except FileNotFoundError as err:
        print(f"Error: input file not found: {err.filename}", file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(main())
