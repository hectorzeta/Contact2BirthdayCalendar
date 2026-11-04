# Converts a contacts CSV (with a "Birthday" column) into
# an iCalendar (.ics) file containing yearly recurring birthday events, and can
# also produce a cleaned CSV that keeps only the name and birthday columns.
#
# Run "python3 contactsToCalendar.py --help" for usage.
import argparse
import calendar
import csv
import datetime
import re
import sys
import uuid
from typing import NamedTuple, Optional

DEFAULT_INPUT = 'contacts.csv'
DEFAULT_CSV_OUTPUT = 'contacts_clean.csv'
DEFAULT_ICS_OUTPUT = 'birthdays.ics'
NEW_ICS_OUTPUT = 'birthdays_new.ics'  # written with --calendar; not configurable

# Accepted --delimiter values (matched case-insensitively) and the separator each one means
DELIMITER_CHOICES = {';': ';', ',': ',', 'tab': '\t'}

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

ICS_LINE_END = '\r\n'      # RFC 5545 requires CRLF line endings
ICS_MAX_OCTETS = 75         # RFC 5545 limit for a content line, before folding

def escape_ics_text(text):
    """Escape a TEXT value as RFC 5545 requires (backslash, semicolon, comma, newline)."""
    return (text.replace('\\', '\\\\')
                .replace(';', '\\;')
                .replace(',', '\\,')
                .replace('\r\n', '\\n')
                .replace('\n', '\\n'))

def fold_ics_line(line):
    """Split a content line into chunks of at most 75 octets (RFC 5545 section 3.1).

    Continuation lines start with a single space. Splits never fall inside a
    multi-byte UTF-8 character.
    """
    if len(line.encode('utf-8')) <= ICS_MAX_OCTETS:
        return line
    chunks, current, current_len = [], '', 0
    limit = ICS_MAX_OCTETS
    for char in line:
        char_len = len(char.encode('utf-8'))
        if current_len + char_len > limit:
            chunks.append(current)
            current, current_len = '', 0
            limit = ICS_MAX_OCTETS - 1  # continuation lines carry a leading space
        current += char
        current_len += char_len
    chunks.append(current)
    return (ICS_LINE_END + ' ').join(chunks)

class BirthdayEvent(NamedTuple):
    """One birthday, ready to be written as a VEVENT.

    summary is the SUMMARY text before escaping; write_calendar escapes it.
    birth_year is an int, or None when the birthday has no year.
    """
    uid: str
    birth_date: datetime.date
    name: str
    birth_year: Optional[int]
    summary: str

def parse_birthday(birthday):
    """Return (birth_date, birth_year) for a Birthday value, or raise ValueError.

    birth_year is None when the value has no year, such as "--MM-DD".
    """
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
        return birth_date, None
    # Handle birthdays with a year: "DD/MM/YYYY" or ISO "YYYY-MM-DD"
    birth_date = parse_full_date(birthday)
    return birth_date, birth_date.year

def detect_delimiter(path):
    """Return the column separator (';', ',' or tab) of the CSV file at path.

    The first line is split with each candidate using the csv module. Only
    candidates that give more than one column and whose header has a Birthday
    column (spaces ignored, case-insensitive) are kept, and the one with the
    most columns is returned. Raises ValueError if no candidate is kept, or if
    two or more tie for the most columns.
    """
    with open(path, encoding='utf-8-sig', newline='') as f:
        line = f.readline().rstrip('\r\n')
    column_counts = {}
    for candidate in (';', ',', '\t'):
        fields = next(csv.reader([line], delimiter=candidate))
        has_birthday = any(field.strip().lower() == 'birthday' for field in fields)
        if len(fields) > 1 and has_birthday:
            column_counts[candidate] = len(fields)
    if not column_counts:
        raise ValueError(f"could not detect the column separator in {path}; use --delimiter")
    most = max(column_counts.values())
    best = [candidate for candidate, count in column_counts.items() if count == most]
    if len(best) > 1:
        raise ValueError(f"ambiguous column separator in {path}; use --delimiter")
    return best[0]

def build_birthday_events(csv_file, delimiter=';'):
    """Read birthdays from csv_file and return a list of BirthdayEvent records.

    delimiter is the column separator of csv_file. Rows without a birthday are
    skipped. Malformed dates are reported and skipped.
    """
    events = []
    # utf-8-sig also strips the byte-order mark that some exports (e.g. Google) add
    with open(csv_file, newline='', encoding='utf-8-sig') as file:
        # Each row becomes a dict keyed by header names
        reader = csv.DictReader(file, delimiter=delimiter)
        for line_no, row in enumerate(reader, start=2):  # line 1 is the header
            # Skip rows without a birthday value
            birthday = (row.get('Birthday') or '').strip()
            if not birthday:
                continue
            first = row.get('First Name') or ''
            last = row.get('Last Name') or ''
            try:
                birth_date, birth_year = parse_birthday(birthday)
            except ValueError:
                # Malformed dates are reported and skipped
                print(f"Skipping invalid date: {birthday} for {first} {last}")
                continue

            # Join only non-empty name parts so a missing last name leaves no double space
            name = ' '.join(p for p in (first, last) if p)
            # UID must be stable and unique: derived from the row position and its contents
            uid = f"{uuid.uuid5(uuid.NAMESPACE_URL, f'{line_no}|{name}|{birthday}')}@contactsToCalendar"
            # Append the birth year to the event title, e.g. " (1990)", when it is known
            year_part = f" ({birth_year})" if birth_year is not None else ""
            events.append(BirthdayEvent(uid, birth_date, name, birth_year, f"Birthday: {name}{year_part}"))
    return events

def write_calendar(events, ics_file, dtstamp):
    """Write BirthdayEvent records to ics_file as an iCalendar file.

    dtstamp is the DTSTAMP value (YYYYMMDDTHHMMSSZ) written on every event.
    """
    lines = [
        "BEGIN:VCALENDAR",
        "PRODID:-//HZ//HZ//EN",
        "VERSION:2.0",
        "CALSCALE:GREGORIAN",
    ]
    for event in events:
        lines += [
            "BEGIN:VEVENT",
            f"UID:{event.uid}",
            f"DTSTAMP:{dtstamp}",
            f"DTSTART;VALUE=DATE:{event.birth_date.strftime('%Y%m%d')}",
            "RRULE:FREQ=YEARLY",
            "SUMMARY:" + escape_ics_text(event.summary),
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")
    with open(ics_file, 'w', encoding='utf-8', newline='') as f:
        for line in lines:
            f.write(fold_ics_line(line) + ICS_LINE_END)

def unfold_ics_lines(text):
    """Split iCalendar text into logical content lines (RFC 5545 section 3.1).

    Accepts CRLF or LF. A line that starts with a space or tab continues the
    previous line; the break and that one whitespace character are removed.
    """
    lines = []
    for raw in text.split('\n'):
        raw = raw[:-1] if raw.endswith('\r') else raw
        if raw[:1] in (' ', '\t') and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines

def unescape_ics_text(value):
    """Undo RFC 5545 TEXT escapes (\\n, \\N, \\, \\; and \\\\) in one pass."""
    return re.sub(r'\\([nN\\,;])',
                  lambda m: '\n' if m.group(1) in 'nN' else m.group(1),
                  value)

def parse_export_date(value):
    """Return the date in the YYYYMMDD part of a DTSTART value, or None.

    Only the first 8 characters are read, so a time or TZID is ignored.
    """
    digits = value[:8]
    if not re.fullmatch(r'[0-9]{8}', digits):
        return None
    try:
        return datetime.date(int(digits[:4]), int(digits[4:6]), int(digits[6:]))
    except ValueError:
        return None

class ExportEvent(NamedTuple):
    """One VEVENT read from an exported calendar.

    summary is the raw SUMMARY text, unescaped. month and day come from DTSTART.
    """
    summary: str
    month: int
    day: int

def read_export_events(path):
    """Read the VEVENT blocks of an exported .ics file and return ExportEvent records.

    Other components are ignored. A VEVENT with no readable DTSTART is skipped.
    Raises FileNotFoundError if path does not exist.
    """
    with open(path, 'rb') as f:
        text = f.read().decode('utf-8-sig')
    events = []
    props = None  # properties of the VEVENT being read, or None outside one
    nested = 0    # depth of components inside the VEVENT (for example VALARM)
    for line in unfold_ics_lines(text):
        name, _, value = line.partition(':')
        name = name.split(';', 1)[0].upper()
        if props is None:
            if name == 'BEGIN' and value.upper() == 'VEVENT':
                props, nested = {}, 0
            continue
        if name == 'BEGIN':
            nested += 1
        elif name == 'END' and nested:
            nested -= 1
        elif name == 'END' and value.upper() == 'VEVENT':
            start_date = parse_export_date(props.get('DTSTART', ''))
            if start_date is not None:
                events.append(ExportEvent(
                    summary=unescape_ics_text(props.get('SUMMARY', '')),
                    month=start_date.month,
                    day=start_date.day))
            props = None
        elif nested == 0 and name in ('SUMMARY', 'DTSTART'):
            props.setdefault(name, value)  # the first occurrence wins
    return events

def strip_birthday_label(text):
    """Remove a leading 'Birthday:' label (case-insensitive) from a SUMMARY."""
    return re.sub(r'^\s*birthday:\s*', '', text, flags=re.IGNORECASE)

def split_generated_title(title):
    """Split a generated SUMMARY such as 'Birthday: Ann Lee (1990)' into (name, year).

    A leading 'Birthday:' (case-insensitive) and a trailing ' (YYYY)' are removed.
    The year is an int, or None when the title has no year.
    """
    name = strip_birthday_label(title)
    year = None
    match = re.fullmatch(r'(.*?)\s*\((\d{4})\)\s*', name)
    if match:
        name, year = match.group(1), int(match.group(2))
    return name.strip(), year

def split_export_title(summary):
    """Split an export SUMMARY such as 'Joe Doe 2000' or 'Birthday: Joe Doe (2000)' into (name, year).

    A leading 'Birthday:' (case-insensitive, as Google exports it) is removed.
    A trailing four-digit year, optionally in parentheses, is the year of birth.
    Otherwise the whole title is the name and the year is None.
    """
    text = strip_birthday_label(summary.strip()).strip()
    match = (re.fullmatch(r'(.*?\S)\s*\((\d{4})\)', text)
             or re.fullmatch(r'(.*?\S)\s+(\d{4})', text))
    if match:
        return match.group(1).strip(), int(match.group(2))
    return text, None

def titles_match(generated_title, export_summary):
    """Return True when a generated title and an export SUMMARY name the same birthday.

    Names are compared case-insensitively, with surrounding spaces trimmed and
    repeated spaces collapsed. Years are compared only when both sides have one.
    """
    gen_name, gen_year = split_generated_title(generated_title)
    exp_name, exp_year = split_export_title(export_summary)
    if gen_year is not None and exp_year is not None and gen_year != exp_year:
        return False
    return ' '.join(gen_name.split()).casefold() == ' '.join(exp_name.split()).casefold()

def is_same_birthday(generated, export):
    """Return True when a BirthdayEvent and an ExportEvent have the same month, day and name."""
    same_day = (export.month, export.day) == (generated.birth_date.month, generated.birth_date.day)
    return same_day and titles_match(generated.summary, export.summary)

def find_new_events(generated_events, export_events):
    """Return (new_events, matched_count) for generated events not yet in the export.

    Each export event matches at most one generated event. Generated events are
    checked in order; new_events keeps that order. The inputs are not modified.
    """
    used = set()  # indexes of export events already matched
    new_events = []
    matched_count = 0
    for generated in generated_events:
        for index, export in enumerate(export_events):
            if index not in used and is_same_birthday(generated, export):
                used.add(index)
                matched_count += 1
                break
        else:
            new_events.append(generated)
    return new_events, matched_count

def make_dtstamp():
    """Return the current UTC time in the YYYYMMDDTHHMMSSZ form used for DTSTAMP."""
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')

def create_birthday_calendar(csv_file, ics_file, delimiter=None):
    """Read birthdays from csv_file and write them as recurring events to ics_file.

    The column separator is detected from csv_file when delimiter is None.
    """
    if delimiter is None:
        delimiter = detect_delimiter(csv_file)
    dtstamp = make_dtstamp()
    events = build_birthday_events(csv_file, delimiter=delimiter)
    write_calendar(events, ics_file, dtstamp)
    print(f"Calendar file created: {ics_file}")

def clean_contacts_csv(csv_file, output_file, delimiter=';'):
    """Keep only the name and birthday columns from csv_file and drop empty rows.

    delimiter is the column separator of csv_file. Writes the result to
    output_file using the same separator.
    Returns the number of rows written.
    """
    keep_columns = ['First Name', 'Middle Name', 'Last Name', 'Birthday']
    rows_written = 0

    with open(csv_file, newline='', encoding='utf-8-sig') as infile, \
         open(output_file, 'w', newline='', encoding='utf-8') as outfile:
        reader = csv.DictReader(infile, delimiter=delimiter)
        writer = csv.DictWriter(outfile, fieldnames=keep_columns, delimiter=delimiter)
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

def parse_delimiter(value):
    """Map a --delimiter value to its separator character, or reject it."""
    key = value.lower()
    if key not in DELIMITER_CHOICES:
        raise argparse.ArgumentTypeError(
            f"invalid delimiter: {value!r} (choose ';', ',' or tab)")
    return DELIMITER_CHOICES[key]

def parse_args(argv=None):
    """Define and parse the command-line options."""
    parser = argparse.ArgumentParser(
        description="Work with a contacts CSV: write a cleaned CSV and/or a birthday calendar (.ics).",
        epilog=(
            "Examples:\n"
            "  python3 contactsToCalendar.py            (same as --ics)\n"
            "  python3 contactsToCalendar.py --ics\n"
            "  python3 contactsToCalendar.py --csv --ics\n"
            "  python3 contactsToCalendar.py --calendar exported.ics\n"
            "  python3 contactsToCalendar.py -i my_contacts.csv --csv cleaned.csv --ics out.ics\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        '-i', '--input', default=DEFAULT_INPUT, metavar='FILE',
        help=(f"contacts CSV to read; separator detected (';', ',' or tab) unless "
              f"--delimiter is given (default: {DEFAULT_INPUT})"),
    )
    parser.add_argument(
        '--delimiter', type=parse_delimiter, default=None, metavar='VALUE',
        help=("column separator of the input: ';', ',' or tab. "
              "Detected from the file when omitted"),
    )
    parser.add_argument(
        '--csv', nargs='?', const=DEFAULT_CSV_OUTPUT, metavar='FILE',
        help=("generate a cleaned CSV with only First Name, Middle Name, Last Name and "
              f"Birthday, and no empty rows (default output: {DEFAULT_CSV_OUTPUT})"),
    )
    parser.add_argument(
        '--ics', nargs='?', const=DEFAULT_ICS_OUTPUT, metavar='FILE',
        help=("generate an iCalendar file of yearly recurring birthday events "
              f"(default output: {DEFAULT_ICS_OUTPUT}). This is the default "
              "when neither --csv nor --ics is given."),
    )
    parser.add_argument(
        '--calendar', metavar='FILE',
        help=("exported calendar to compare against. Also writes "
              f"{NEW_ICS_OUTPUT} with only the birthdays not already in it, "
              "and writes the birthday calendar as usual"),
    )
    return parser.parse_args(argv)

def main(argv=None):
    """Entry point: run the requested outputs and return an exit code."""
    args = parse_args(argv)

    # With no output option, default to the calendar file
    if args.csv is None and args.ics is None and args.calendar is None:
        args.ics = DEFAULT_ICS_OUTPUT

    # Read the export before writing anything, so a missing file leaves no output
    export_events = None
    if args.calendar is not None:
        try:
            export_events = read_export_events(args.calendar)
        except FileNotFoundError as err:
            print(f"Error: calendar file not found: {err.filename}", file=sys.stderr)
            return 1

    # Resolve the column separator before writing anything, so a bad input leaves no output
    try:
        delimiter = args.delimiter if args.delimiter is not None else detect_delimiter(args.input)
    except FileNotFoundError as err:
        print(f"Error: input file not found: {err.filename}", file=sys.stderr)
        return 1
    except ValueError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    try:
        if args.csv is not None:
            clean_contacts_csv(args.input, args.csv, delimiter=delimiter)
        if args.calendar is not None:
            # Build the events once so birthdays.ics and birthdays_new.ics come from the same list
            dtstamp = make_dtstamp()
            events = build_birthday_events(args.input, delimiter=delimiter)
            ics_file = args.ics or DEFAULT_ICS_OUTPUT
            write_calendar(events, ics_file, dtstamp)
            print(f"Calendar file created: {ics_file}")
            new_events, matched_count = find_new_events(events, export_events)
            write_calendar(new_events, NEW_ICS_OUTPUT, dtstamp)
            print(f"Calendar file created: {NEW_ICS_OUTPUT} "
                  f"({len(new_events)} new, {matched_count} already in calendar)")
        elif args.ics is not None:
            create_birthday_calendar(args.input, args.ics, delimiter=delimiter)
    except FileNotFoundError as err:
        print(f"Error: input file not found: {err.filename}", file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(main())
