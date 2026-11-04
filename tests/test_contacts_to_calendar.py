"""Tests for contactsToCalendar.py.

Run from the project root with:

    python3 -m unittest discover -s tests -v

No third-party packages are needed.
"""
import calendar
import csv
import datetime
import os
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(TESTS_DIR)
SCRIPT = os.path.join(PROJECT_DIR, 'contactsToCalendar.py')
FIXTURES = os.path.join(TESTS_DIR, 'fixtures')
EXPECTED = os.path.join(TESTS_DIR, 'expected')

sys.path.insert(0, PROJECT_DIR)
import contactsToCalendar as cal  # noqa: E402

EXAMPLE_CSV = os.path.join(FIXTURES, 'example.csv')
EXPECTED_CLEAN_CSV = os.path.join(EXPECTED, 'clean_example.csv')
HEADER = 'First Name;Middle Name;Last Name;Birthday'


def read_clean_rows(path):
    """Read a semicolon CSV into a list of dicts (line endings do not matter)."""
    with open(path, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f, delimiter=';'))


def read_ics_lines(path):
    """Return the logical content lines of an .ics file.

    Undoes RFC 5545 line folding (a CRLF followed by a space is a continuation)
    and fails the test if any physical line ends in something other than CRLF.
    """
    with open(path, 'rb') as f:
        raw = f.read()
    assert raw.endswith(b'\r\n'), "ics file must end with CRLF"
    assert b'\n' not in raw.replace(b'\r\n', b''), "bare LF found; RFC 5545 requires CRLF"
    text = raw.decode('utf-8').replace('\r\n ', '')
    return text.split('\r\n')[:-1]


def unescape_ics_text(value):
    """Undo RFC 5545 TEXT escapes in one pass, so '\\\\,' is read correctly."""
    mapping = {'n': '\n', 'N': '\n', ',': ',', ';': ';', '\\': '\\'}
    return re.sub(r'\\(.)', lambda m: mapping.get(m.group(1), m.group(1)), value)


def parse_ics_events(path):
    """Return a list of dicts, one per VEVENT.

    Keys are property names without parameters, so 'DTSTART;VALUE=DATE:x'
    is stored under 'DTSTART'. Values have RFC 5545 escapes undone.
    """
    events, current = [], None
    for line in read_ics_lines(path):
        if line == 'BEGIN:VEVENT':
            current = {}
        elif line == 'END:VEVENT':
            events.append(current)
            current = None
        elif current is not None and ':' in line:
            key, value = line.split(':', 1)
            key = key.split(';')[0]
            current[key] = unescape_ics_text(value)
    return events


class ScratchMixin:
    """Gives each test its own temporary directory, removed afterwards."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def write_csv(self, name, text):
        path = os.path.join(self.tmp, name)
        with open(path, 'w', encoding='utf-8', newline='') as f:
            f.write(text)
        return path


class CleanCsvExampleTests(ScratchMixin, unittest.TestCase):
    """clean_contacts_csv() run on tests/fixtures/example.csv."""

    def setUp(self):
        super().setUp()
        self.out = os.path.join(self.tmp, 'clean.csv')
        with mock.patch('builtins.print'):
            self.count = cal.clean_contacts_csv(EXAMPLE_CSV, self.out)

    def test_returns_number_of_rows_written(self):
        self.assertEqual(self.count, 7)

    def test_header_has_only_the_four_kept_columns(self):
        with open(self.out, encoding='utf-8') as f:
            header = f.readline().rstrip('\r\n')
        self.assertEqual(header, HEADER)

    def test_matches_expected_output(self):
        self.assertEqual(read_clean_rows(self.out), read_clean_rows(EXPECTED_CLEAN_CSV))

    def test_company_only_row_is_dropped(self):
        # The "ACME" row has only an Organization Name, so every kept column is empty.
        rows = read_clean_rows(self.out)
        self.assertEqual(len(rows), 7)
        for row in rows:
            self.assertTrue(any(row.values()), f"empty row kept: {row}")

    def test_first_name_is_read_despite_byte_order_mark(self):
        # example.csv starts with a UTF-8 BOM; the first column must still be found.
        first_names = [r['First Name'] for r in read_clean_rows(self.out)]
        self.assertEqual(first_names,
                         ['Robert', 'John', 'Margaret', 'Alexandra', 'Bertha', 'Leo', 'Lily'])


class IcsExampleTests(ScratchMixin, unittest.TestCase):
    """create_birthday_calendar() run on tests/fixtures/example.csv."""

    def setUp(self):
        super().setUp()
        self.out = os.path.join(self.tmp, 'birthdays.ics')
        with mock.patch('builtins.print'):  # silence the script's status messages
            cal.create_birthday_calendar(EXAMPLE_CSV, self.out)
        self.events = parse_ics_events(self.out)

    def test_calendar_wrapper_is_present(self):
        lines = read_ics_lines(self.out)
        self.assertEqual(lines[0], 'BEGIN:VCALENDAR')
        self.assertEqual(lines[-1], 'END:VCALENDAR')

    def event(self, summary):
        """Return the one event with this exact title."""
        matches = [e for e in self.events if e['SUMMARY'] == summary]
        self.assertEqual(len(matches), 1, f"expected one event titled {summary!r}")
        return matches[0]

    def test_example_has_four_usable_birthdays(self):
        # Bertha ("--01-01"), Margaret (ISO "1931-03-31"), and the two Feb 29 rows
        # ("2000-02-29" and "--02-29"). Robert, John and Alexandra have no
        # birthday; the ACME row is not a contact.
        self.assertEqual(len(self.events), 4)

    def test_feb_29_with_year_is_on_that_exact_date(self):
        event = self.event('Birthday: Leo Schmidt (2000)')
        self.assertEqual(event['DTSTART'], '20000229')
        self.assertEqual(event['RRULE'], 'FREQ=YEARLY')

    def test_feb_29_without_year_uses_a_leap_year_placeholder(self):
        event = self.event('Birthday: Lily Foster')
        self.assertEqual(event['DTSTART'][4:], '0229')
        start_year = int(event['DTSTART'][:4])
        self.assertTrue(calendar.isleap(start_year))
        self.assertGreaterEqual(start_year, datetime.date.today().year)

    def test_bertha_event_is_yearly_on_january_first(self):
        event = self.event('Birthday: Bertha Morris')
        self.assertEqual(event['RRULE'], 'FREQ=YEARLY')
        self.assertEqual(event['DTSTART'][4:], '0101')

    def test_bertha_event_title_has_no_year(self):
        # "--MM-DD" birthdays do not include a year, so none is added to the title.
        self.event('Birthday: Bertha Morris')  # exact title match, no "(year)" suffix

    def test_iso_date_birthday_is_supported(self):
        # Margaret has "1931-03-31" (ISO format) and no last name.
        margaret = self.event('Birthday: Margaret (1931)')
        self.assertEqual(margaret['DTSTART'], '19310331')


class IcsRuleTests(ScratchMixin, unittest.TestCase):
    """Behaviour of individual birthday formats, using small synthetic files."""

    HDR = 'First Name;Middle Name;Last Name;Birthday\n'

    def run_ics(self, body):
        csv_path = self.write_csv('in.csv', self.HDR + body)
        out = os.path.join(self.tmp, 'out.ics')
        with mock.patch('builtins.print') as fake_print:
            cal.create_birthday_calendar(csv_path, out)
        return parse_ics_events(out), fake_print

    def test_full_date_adds_birth_year_to_title(self):
        events, _ = self.run_ics('Cara;;Full;15/03/1990\n')
        self.assertEqual(events[0]['SUMMARY'], 'Birthday: Cara Full (1990)')
        self.assertEqual(events[0]['DTSTART'], '19900315')

    def test_name_with_missing_last_name_has_no_double_space(self):
        events, _ = self.run_ics('Solo;;;--05-05\n')
        self.assertEqual(events[0]['SUMMARY'], 'Birthday: Solo')

    def test_iso_date_adds_birth_year_to_title(self):
        events, _ = self.run_ics('Iris;;Iso;1990-03-15\n')
        self.assertEqual(events[0]['SUMMARY'], 'Birthday: Iris Iso (1990)')
        self.assertEqual(events[0]['DTSTART'], '19900315')

    def test_iso_invalid_date_is_skipped_and_reported(self):
        events, fake_print = self.run_ics('Ivy;;Bad;1990-02-30\n')
        self.assertEqual(events, [])
        fake_print.assert_any_call('Skipping invalid date: 1990-02-30 for Ivy Bad')

    def test_day_first_slash_format_is_not_read_as_iso(self):
        # "03/04/1990" must stay day/month/year (3 April), not month/day.
        events, _ = self.run_ics('Jo;;Slash;03/04/1990\n')
        self.assertEqual(events[0]['DTSTART'], '19900403')

    def test_month_day_without_year_uses_current_year_placeholder(self):
        events, _ = self.run_ics('Bob;;Plain;--07-04\n')
        self.assertEqual(events[0]['DTSTART'][4:], '0704')
        self.assertEqual(events[0]['DTSTART'][:4], str(datetime.date.today().year))

    def test_feb_29_uses_a_leap_year(self):
        events, _ = self.run_ics('Anna;;Leap;--02-29\n')
        start = events[0]['DTSTART']
        self.assertEqual(start[4:], '0229')
        self.assertTrue(calendar.isleap(int(start[:4])))
        self.assertGreaterEqual(int(start[:4]), datetime.date.today().year)

    def test_feb_29_in_a_leap_year_stays_in_the_current_leap_year(self):
        # Pin "today" to 2028 (a leap year) and check the placeholder is 2028, not 2032.
        class FakeDate(datetime.date):
            @classmethod
            def today(cls):
                return cls(2028, 1, 10)

        with mock.patch.object(cal.datetime, 'date', FakeDate):
            events, _ = self.run_ics('Anna;;Leap;--02-29\n')
        self.assertEqual(events[0]['DTSTART'], '20280229')

    def test_invalid_date_is_skipped_and_reported(self):
        events, fake_print = self.run_ics('Dan;;Bad;--13-45\n')
        self.assertEqual(events, [])
        fake_print.assert_any_call('Skipping invalid date: --13-45 for Dan Bad')

    def test_row_without_birthday_is_ignored(self):
        events, _ = self.run_ics('Eve;;NoBday;\n')
        self.assertEqual(events, [])

    def test_surrounding_spaces_in_birthday_are_ignored(self):
        events, _ = self.run_ics('Bertha;;Morris;  --01-01  \n')
        self.assertEqual(len(events), 1)

    def test_calendar_is_valid_when_there_are_no_events(self):
        out = os.path.join(self.tmp, 'empty.ics')
        csv_path = self.write_csv('in.csv', self.HDR)
        with mock.patch('builtins.print'):
            cal.create_birthday_calendar(csv_path, out)
        self.assertEqual(read_ics_lines(out),
                         ['BEGIN:VCALENDAR', 'PRODID:-//HZ//HZ//EN', 'VERSION:2.0',
                          'CALSCALE:GREGORIAN', 'END:VCALENDAR'])


class IcsValidityTests(ScratchMixin, unittest.TestCase):
    """Checks against RFC 5545 requirements for the generated calendar file."""

    HDR = 'First Name;Middle Name;Last Name;Birthday\n'

    def make_ics(self, body):
        csv_path = self.write_csv('in.csv', self.HDR + body)
        out = os.path.join(self.tmp, 'out.ics')
        with mock.patch('builtins.print'):
            cal.create_birthday_calendar(csv_path, out)
        return out

    def test_file_uses_crlf_line_endings_only(self):
        out = self.make_ics('Ann;;Lee;1990-01-02\n')
        with open(out, 'rb') as f:
            raw = f.read()
        self.assertTrue(raw.endswith(b'\r\n'))
        self.assertEqual(raw.count(b'\n'), raw.count(b'\r\n'))

    def test_every_event_has_required_uid_and_dtstamp(self):
        out = self.make_ics('Ann;;Lee;1990-01-02\nBob;;Ray;--07-04\n')
        events = parse_ics_events(out)
        self.assertEqual(len(events), 2)
        for event in events:
            self.assertIn('UID', event)
            self.assertIn('DTSTAMP', event)

    def test_uids_are_unique(self):
        out = self.make_ics('Ann;;Lee;1990-01-02\nAnn;;Lee;1990-01-02\n')
        uids = [e['UID'] for e in parse_ics_events(out)]
        self.assertEqual(len(set(uids)), 2)

    def test_dtstamp_is_utc_format(self):
        out = self.make_ics('Ann;;Lee;1990-01-02\n')
        stamp = parse_ics_events(out)[0]['DTSTAMP']
        self.assertRegex(stamp, r'^\d{8}T\d{6}Z$')

    def test_dtstart_is_declared_as_a_date(self):
        out = self.make_ics('Ann;;Lee;1990-01-02\n')
        lines = read_ics_lines(out)
        self.assertIn('DTSTART;VALUE=DATE:19900102', lines)

    def test_summary_escapes_comma_and_semicolon(self):
        out = self.make_ics('Ann;Q;Smith, Jr;01/02/1990\n')
        summary = parse_ics_events(out)[0]['SUMMARY']
        # Titles use first and last name only; the middle name is not shown
        self.assertEqual(summary, 'Birthday: Ann Smith, Jr (1990)')
        raw_line = next(line for line in read_ics_lines(out) if line.startswith('SUMMARY'))
        self.assertIn('Smith\\, Jr', raw_line)

    def test_long_summary_is_folded_to_75_octets(self):
        long_name = 'Ünïcødé' * 10
        out = self.make_ics(f'{long_name};;Zed;01/02/1990\n')
        with open(out, 'rb') as f:
            physical = f.read().split(b'\r\n')
        for line in physical:
            self.assertLessEqual(len(line), 75, line)
        # Folding must not break a UTF-8 character: the file must decode cleanly
        self.assertIn(long_name, parse_ics_events(out)[0]['SUMMARY'])

    def test_unescape_handles_escaped_backslash_before_comma(self):
        # Input text "a\b,c" escapes to "a\\b\,c" and must read back unchanged
        self.assertEqual(cal.escape_ics_text('a\\b,c'), 'a\\\\b\\,c')
        self.assertEqual(unescape_ics_text('a\\\\b\\,c'), 'a\\b,c')


class CleanCsvRuleTests(ScratchMixin, unittest.TestCase):
    """Synthetic cases for clean_contacts_csv()."""

    def clean(self, text):
        src = self.write_csv('in.csv', text)
        out = os.path.join(self.tmp, 'out.csv')
        with mock.patch('builtins.print'):
            count = cal.clean_contacts_csv(src, out)
        return count, read_clean_rows(out)

    def test_extra_columns_are_removed_and_order_is_fixed(self):
        count, rows = self.clean('Last Name;Email;First Name;Birthday;Middle Name\n'
                                 'Doe;a@x.com;Jane;01/02/1980;Q\n')
        self.assertEqual(count, 1)
        self.assertEqual(rows, [{'First Name': 'Jane', 'Middle Name': 'Q',
                                 'Last Name': 'Doe', 'Birthday': '01/02/1980'}])

    def test_rows_with_only_extra_data_are_dropped(self):
        count, rows = self.clean(HEADER + '\n' + ';;;\n' + 'Ann;;;\n')
        self.assertEqual(count, 1)
        self.assertEqual(rows[0]['First Name'], 'Ann')

    def test_whitespace_only_row_is_dropped(self):
        count, _ = self.clean(HEADER + '\n   ;  ;  ;  \n')
        self.assertEqual(count, 0)

    def test_missing_kept_column_becomes_empty(self):
        count, rows = self.clean('First Name;Last Name\nSam;Lee\n')
        self.assertEqual(count, 1)
        self.assertEqual(rows[0]['Middle Name'], '')
        self.assertEqual(rows[0]['Birthday'], '')

    def test_empty_input_gives_header_only(self):
        count, rows = self.clean(HEADER + '\n')
        self.assertEqual(count, 0)
        self.assertEqual(rows, [])


class CommandLineTests(ScratchMixin, unittest.TestCase):
    """Runs contactsToCalendar.py as a program, as a user would."""

    def run_script(self, *args, cwd=None):
        return subprocess.run([sys.executable, SCRIPT, *args], cwd=cwd or self.tmp,
                              capture_output=True, text=True)

    def test_help_lists_all_options_and_exits_zero(self):
        result = self.run_script('--help')
        self.assertEqual(result.returncode, 0)
        for option in ('--input', '--csv', '--ics'):
            self.assertIn(option, result.stdout)

    def test_no_options_defaults_to_ics(self):
        result = self.run_script('-i', EXAMPLE_CSV)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.tmp, 'birthdays.ics')))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, 'contacts_clean.csv')))
        self.assertEqual(len(parse_ics_events(os.path.join(self.tmp, 'birthdays.ics'))), 4)

    def test_missing_input_file_exits_one_with_message(self):
        result = self.run_script('-i', os.path.join(self.tmp, 'nope.csv'), '--ics')
        self.assertEqual(result.returncode, 1)
        self.assertIn('input file not found', result.stderr)

    def test_both_outputs_use_default_names_in_the_working_directory(self):
        result = self.run_script('-i', EXAMPLE_CSV, '--csv', '--ics')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.tmp, 'contacts_clean.csv')))
        self.assertTrue(os.path.exists(os.path.join(self.tmp, 'birthdays.ics')))
        self.assertEqual(read_clean_rows(os.path.join(self.tmp, 'contacts_clean.csv')),
                         read_clean_rows(EXPECTED_CLEAN_CSV))

    def test_custom_output_names(self):
        csv_out = os.path.join(self.tmp, 'my_clean.csv')
        ics_out = os.path.join(self.tmp, 'my_cal.ics')
        result = self.run_script('-i', EXAMPLE_CSV, '--csv', csv_out, '--ics', ics_out)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(os.path.exists(csv_out))
        self.assertEqual(len(parse_ics_events(ics_out)), 4)


class CalendarDedupeCliTests(ScratchMixin, unittest.TestCase):
    """Runs --calendar as a program, with a small fictional export written by the test.

    The input has Ann Lee (matches), Bob Ray (matches) and Joe Doe (date differs).
    """

    INPUT_TEXT = (
        f"{HEADER}\n"
        "Ann;;Lee;1990-03-15\n"
        "Bob;;Ray;--07-04\n"
        "Joe;;Doe;12/05/1980\n"
    )
    EXPORT_TEXT = (
        'BEGIN:VCALENDAR\r\n'
        'BEGIN:VEVENT\r\nDTSTART;VALUE=DATE:20200315\r\nSUMMARY:Ann Lee 1990\r\nEND:VEVENT\r\n'
        'BEGIN:VEVENT\r\nDTSTART;VALUE=DATE:20200704\r\nSUMMARY:Bob Ray\r\nEND:VEVENT\r\n'
        'BEGIN:VEVENT\r\nDTSTART;VALUE=DATE:20200601\r\nSUMMARY:Joe Doe\r\nEND:VEVENT\r\n'
        'END:VCALENDAR\r\n'
    )

    def setUp(self):
        super().setUp()
        self.csv = self.write_csv('contacts.csv', self.INPUT_TEXT)
        self.export = os.path.join(self.tmp, 'export.ics')
        with open(self.export, 'wb') as f:
            f.write(self.EXPORT_TEXT.encode('utf-8'))

    def run_script(self, *args, cwd=None):
        return subprocess.run([sys.executable, SCRIPT, *args], cwd=cwd or self.tmp,
                              capture_output=True, text=True)

    def path(self, name):
        return os.path.join(self.tmp, name)

    def test_both_files_are_written_and_exit_is_zero(self):
        result = self.run_script('-i', self.csv, '--calendar', self.export)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(os.path.exists(self.path('birthdays.ics')))
        self.assertTrue(os.path.exists(self.path('birthdays_new.ics')))

    def test_new_file_has_only_unmatched_events_and_message_counts(self):
        result = self.run_script('-i', self.csv, '--calendar', self.export)
        self.assertEqual(result.returncode, 0, result.stderr)
        new_events = parse_ics_events(self.path('birthdays_new.ics'))
        self.assertEqual([e['SUMMARY'] for e in new_events], ['Birthday: Joe Doe (1980)'])
        lines = result.stdout.splitlines()
        self.assertIn('Calendar file created: birthdays.ics', lines)
        self.assertIn('Calendar file created: birthdays_new.ics (1 new, 2 already in calendar)',
                      lines)

    def test_birthdays_file_matches_a_run_without_calendar(self):
        result = self.run_script('-i', self.csv, '--calendar', self.export)
        self.assertEqual(result.returncode, 0, result.stderr)
        plain = self.run_script('-i', self.csv, '--ics', 'plain.ics')
        self.assertEqual(plain.returncode, 0, plain.stderr)

        def key(event):
            return (event.get('SUMMARY'), event.get('DTSTART'), event.get('RRULE'))

        with_calendar = parse_ics_events(self.path('birthdays.ics'))
        plain_events = parse_ics_events(self.path('plain.ics'))
        self.assertEqual(len(with_calendar), 3)
        self.assertEqual([key(e) for e in with_calendar], [key(e) for e in plain_events])

    def test_calendar_without_ics_still_writes_birthdays_file(self):
        result = self.run_script('-i', self.csv, '--calendar', self.export)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(os.path.exists(self.path('birthdays.ics')))
        self.assertFalse(os.path.exists(self.path('contacts_clean.csv')))

    def test_custom_ics_name_is_used_and_new_file_keeps_its_name(self):
        result = self.run_script('-i', self.csv, '--calendar', self.export, '--ics', 'my_cal.ics')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(os.path.exists(self.path('my_cal.ics')))
        self.assertFalse(os.path.exists(self.path('birthdays.ics')))
        self.assertTrue(os.path.exists(self.path('birthdays_new.ics')))

    def test_missing_calendar_file_exits_one_and_writes_nothing(self):
        missing = self.path('no_such_export.ics')
        result = self.run_script('-i', self.csv, '--calendar', missing, '--csv', '--ics')
        self.assertEqual(result.returncode, 1)
        self.assertIn('Error: calendar file not found:', result.stderr)
        self.assertIn(missing, result.stderr)
        self.assertFalse(os.path.exists(self.path('birthdays.ics')))
        self.assertFalse(os.path.exists(self.path('birthdays_new.ics')))
        self.assertFalse(os.path.exists(self.path('contacts_clean.csv')))

    def test_export_file_is_not_modified(self):
        with open(self.export, 'rb') as f:
            before = f.read()
        result = self.run_script('-i', self.csv, '--calendar', self.export)
        self.assertEqual(result.returncode, 0, result.stderr)
        with open(self.export, 'rb') as f:
            self.assertEqual(f.read(), before)

    def test_help_lists_calendar_option(self):
        result = self.run_script('--help')
        self.assertEqual(result.returncode, 0)
        self.assertIn('--calendar', result.stdout)

    def test_csv_is_still_written_alongside_calendar(self):
        result = self.run_script('-i', EXAMPLE_CSV, '--csv', '--calendar', self.export)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(read_clean_rows(self.path('contacts_clean.csv')),
                         read_clean_rows(EXPECTED_CLEAN_CSV))
        self.assertTrue(os.path.exists(self.path('birthdays_new.ics')))


class CalendarFixtureTests(ScratchMixin, unittest.TestCase):
    """--calendar run against tests/fixtures/calendar_export.ics (fictional names).

    The input CSV is written by the test from BIRTHDAYS, so each row says what
    happens to it. Export events and their expected outcome:

    - Ann Lee 1990 on 15 March: matches Ann Lee (1990), so it is removed.
    - Bob Ray on 15 August: other date than Bob Ray (4 July), so it stays.
    - Carl Moss on 10 September: other title than Dora Vale (same date), so Dora stays.
    - Eve Gray 1985 on 20 May: other year than Eve Gray (1990), so it stays.
    - Finn Hale with a DATE-TIME DTSTART on 4 July: matches, so it is removed.
    - No Start has no DTSTART: it is skipped, so the generated No Start stays.
    - Gail Dunn (1975) on 2 November: matches, so it is removed.
    """

    FIXTURE = os.path.join(FIXTURES, 'calendar_export.ics')

    # (first name, last name, Birthday column)
    BIRTHDAYS = [
        ('Ann', 'Lee', '1990-03-15'),
        ('Bob', 'Ray', '--07-04'),
        ('Dora', 'Vale', '1992-09-10'),
        ('Eve', 'Gray', '1990-05-20'),
        ('Finn', 'Hale', '--07-04'),
        ('No', 'Start', '1999-01-01'),
        ('Gail', 'Dunn', '1975-11-02'),
    ]
    REMOVED = {'Birthday: Ann Lee (1990)', 'Birthday: Finn Hale', 'Birthday: Gail Dunn (1975)'}
    KEPT = ['Birthday: Bob Ray', 'Birthday: Dora Vale (1992)',
            'Birthday: Eve Gray (1990)', 'Birthday: No Start (1999)']

    def setUp(self):
        super().setUp()
        lines = [HEADER] + [f"{first};;{last};{birthday}" for first, last, birthday in self.BIRTHDAYS]
        self.csv = self.write_csv('contacts.csv', '\n'.join(lines) + '\n')
        # Copy the fixture so the script never runs next to it
        self.export = self.path('calendar_export.ics')
        with open(self.FIXTURE, 'rb') as src, open(self.export, 'wb') as dst:
            dst.write(src.read())

    def run_script(self, *args):
        return subprocess.run([sys.executable, SCRIPT, *args], cwd=self.tmp,
                              capture_output=True, text=True)

    def path(self, name):
        return os.path.join(self.tmp, name)

    def run_with_calendar(self):
        result = self.run_script('-i', self.csv, '--calendar', self.export)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        return result

    def test_matched_events_are_removed_from_new_file(self):
        self.run_with_calendar()
        summaries = [e['SUMMARY'] for e in parse_ics_events(self.path('birthdays_new.ics'))]
        for summary in self.REMOVED:
            self.assertNotIn(summary, summaries)

    def test_unmatched_events_stay_in_new_file(self):
        self.run_with_calendar()
        summaries = [e['SUMMARY'] for e in parse_ics_events(self.path('birthdays_new.ics'))]
        self.assertEqual(summaries, self.KEPT)

    def test_no_start_event_does_not_stop_the_run(self):
        result = self.run_with_calendar()
        self.assertIn('Calendar file created: birthdays_new.ics', result.stdout)
        self.assertEqual(len(parse_ics_events(self.path('birthdays.ics'))), len(self.BIRTHDAYS))

    def test_message_gives_new_and_already_in_calendar_counts(self):
        result = self.run_with_calendar()
        self.assertIn('Calendar file created: birthdays_new.ics (4 new, 3 already in calendar)',
                      result.stdout.splitlines())

    def test_fixture_file_is_not_modified(self):
        with open(self.FIXTURE, 'rb') as f:
            before = f.read()
        self.run_with_calendar()
        with open(self.FIXTURE, 'rb') as f:
            self.assertEqual(f.read(), before)

    def test_fixture_folder_gets_no_new_files(self):
        before = sorted(os.listdir(FIXTURES))
        self.run_with_calendar()
        self.assertEqual(sorted(os.listdir(FIXTURES)), before)


REAL_EXPORT = os.path.join(FIXTURES, 'export.ics')


class GoogleExportDedupeTests(ScratchMixin, unittest.TestCase):
    """Dedupe against a real Google Calendar export (tests/fixtures/export.ics)."""

    def test_export_titles_drop_the_birthday_prefix(self):
        self.assertEqual(cal.split_export_title('Birthday: Margaret (1931)'), ('Margaret', 1931))
        self.assertEqual(cal.split_export_title('Birthday: Lily Foster'), ('Lily Foster', None))

    def test_generated_title_matches_google_export_title(self):
        self.assertTrue(cal.titles_match('Birthday: Margaret (1931)', 'Birthday: Margaret (1931)'))
        self.assertFalse(cal.titles_match('Birthday: Ann Lee (1990)', 'Birthday: Ann Lee 1985'))

    def test_all_example_birthdays_are_detected_as_duplicates(self):
        # example.csv contains the four birthdays that are in the real export
        # (Margaret, Lily Foster, Bertha Morris, Leo Schmidt). Nothing should be new.
        with open(REAL_EXPORT, 'rb') as f:
            before = f.read()
        csv_path = os.path.join(self.tmp, 'contacts.csv')
        with open(EXAMPLE_CSV, 'rb') as src, open(csv_path, 'wb') as dst:
            dst.write(src.read())
        result = subprocess.run(
            [sys.executable, SCRIPT, '-i', csv_path, '--calendar', REAL_EXPORT],
            cwd=self.tmp, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('birthdays_new.ics (0 new, 4 already in calendar)', result.stdout)
        new_path = os.path.join(self.tmp, 'birthdays_new.ics')
        self.assertEqual(parse_ics_events(new_path), [])
        with open(REAL_EXPORT, 'rb') as f:
            self.assertEqual(f.read(), before)


class ExportReaderTests(ScratchMixin, unittest.TestCase):
    """read_export_events() on small synthetic exported calendars."""

    def write_ics(self, text, name='export.ics'):
        """Write text as UTF-8 bytes exactly as given (no newline changes)."""
        path = os.path.join(self.tmp, name)
        with open(path, 'wb') as f:
            f.write(text.encode('utf-8'))
        return path

    def test_returns_one_record_per_vevent(self):
        path = self.write_ics(
            'BEGIN:VCALENDAR\r\n'
            'BEGIN:VEVENT\r\nDTSTART;VALUE=DATE:20260212\r\nSUMMARY:Ann Lee (1990)\r\nEND:VEVENT\r\n'
            'BEGIN:VEVENT\r\nDTSTART;VALUE=DATE:19991031\r\nSUMMARY:Bob Ray\r\nEND:VEVENT\r\n'
            'END:VCALENDAR\r\n')
        self.assertEqual(cal.read_export_events(path), [
            cal.ExportEvent(summary='Ann Lee (1990)', month=2, day=12),
            cal.ExportEvent(summary='Bob Ray', month=10, day=31),
        ])

    def test_reads_value_date_dtstart(self):
        path = self.write_ics(
            'BEGIN:VEVENT\r\nDTSTART;VALUE=DATE:20260305\r\nSUMMARY:Ann Lee\r\nEND:VEVENT\r\n')
        event = cal.read_export_events(path)[0]
        self.assertEqual((event.month, event.day), (3, 5))

    def test_reads_date_time_dtstart_with_z_and_tzid_using_date_part(self):
        path = self.write_ics(
            'BEGIN:VEVENT\r\nDTSTART:20260704T230000Z\r\nSUMMARY:Ann Lee\r\nEND:VEVENT\r\n'
            'BEGIN:VEVENT\r\nDTSTART;TZID=Europe/Berlin:20261201T090000\r\n'
            'SUMMARY:Bob Ray\r\nEND:VEVENT\r\n')
        events = cal.read_export_events(path)
        self.assertEqual([(e.month, e.day) for e in events], [(7, 4), (12, 1)])

    def test_unfolds_continuation_line_in_summary(self):
        long_name = 'Maximilian Alexander Featherstonehaugh-Worthington Jr of Hilltop'
        full = 'SUMMARY:' + long_name + ' (1990)'
        self.assertGreater(len(full), 75)
        # Fold at 75 octets: CRLF followed by one space starts a continuation.
        folded = full[:75] + '\r\n ' + full[75:]
        path = self.write_ics(
            'BEGIN:VEVENT\r\nDTSTART;VALUE=DATE:20260212\r\n' + folded + '\r\nEND:VEVENT\r\n')
        self.assertEqual(cal.read_export_events(path)[0].summary, long_name + ' (1990)')

    def test_accepts_lf_only_line_endings(self):
        path = self.write_ics(
            'BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART;VALUE=DATE:20260212\n'
            'SUMMARY:Ann Lee\nEND:VEVENT\nEND:VCALENDAR\n')
        self.assertEqual(cal.read_export_events(path),
                         [cal.ExportEvent(summary='Ann Lee', month=2, day=12)])

    def test_decodes_utf8_byte_order_mark(self):
        path = self.write_ics(
            '﻿BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nDTSTART;VALUE=DATE:20260212\r\n'
            'SUMMARY:Zoë Lee\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n')
        self.assertEqual(cal.read_export_events(path),
                         [cal.ExportEvent(summary='Zoë Lee', month=2, day=12)])

    def test_skips_event_without_dtstart_and_keeps_following_event(self):
        path = self.write_ics(
            'BEGIN:VEVENT\r\nSUMMARY:No Date\r\nEND:VEVENT\r\n'
            'BEGIN:VEVENT\r\nDTSTART;VALUE=DATE:20260212\r\nSUMMARY:Ann Lee\r\nEND:VEVENT\r\n')
        self.assertEqual(cal.read_export_events(path),
                         [cal.ExportEvent(summary='Ann Lee', month=2, day=12)])

    def test_ignores_non_vevent_components(self):
        path = self.write_ics(
            'BEGIN:VCALENDAR\r\n'
            'BEGIN:VTIMEZONE\r\nTZID:Europe/Berlin\r\nEND:VTIMEZONE\r\n'
            'BEGIN:VTODO\r\nDTSTART;VALUE=DATE:20260101\r\nSUMMARY:Task Item\r\nEND:VTODO\r\n'
            'BEGIN:VEVENT\r\nDTSTART;VALUE=DATE:20260212\r\nSUMMARY:Ann Lee\r\nEND:VEVENT\r\n'
            'END:VCALENDAR\r\n')
        self.assertEqual(cal.read_export_events(path),
                         [cal.ExportEvent(summary='Ann Lee', month=2, day=12)])

    def test_unescapes_comma_semicolon_and_backslash_in_summary(self):
        path = self.write_ics(
            'BEGIN:VEVENT\r\nDTSTART;VALUE=DATE:20260212\r\n'
            'SUMMARY:Lee\\, Ann\\; the \\\\ Great\r\nEND:VEVENT\r\n')
        self.assertEqual(cal.read_export_events(path)[0].summary, 'Lee, Ann; the \\ Great')

    def test_missing_file_raises_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            cal.read_export_events(os.path.join(self.tmp, 'no_such_file.ics'))


class TitleMatchTests(unittest.TestCase):
    """split_generated_title, split_export_title and titles_match on fictional names."""

    def test_split_generated_title_gives_name_and_year(self):
        self.assertEqual(cal.split_generated_title('Birthday: Ann Lee (1990)'),
                         ('Ann Lee', 1990))

    def test_split_generated_title_without_year_gives_none(self):
        self.assertEqual(cal.split_generated_title('Birthday: Ann Lee'), ('Ann Lee', None))

    def test_matches_lowercase_generated_title_against_export_with_year(self):
        self.assertTrue(cal.titles_match('birthday: ann lee (1990)', 'Ann Lee 1990'))

    def test_generated_year_matches_export_without_year(self):
        self.assertTrue(cal.titles_match('Birthday: Ann Lee (1990)', 'Ann Lee'))

    def test_different_year_does_not_match(self):
        self.assertFalse(cal.titles_match('Birthday: Ann Lee (1990)', 'Ann Lee 1985'))

    def test_export_year_in_parentheses_and_bare_give_same_year(self):
        self.assertEqual(cal.split_export_title('Joe Doe (2000)'), ('Joe Doe', 2000))
        self.assertEqual(cal.split_export_title('Joe Doe 2000'), ('Joe Doe', 2000))

    def test_extra_spaces_are_ignored_in_names(self):
        self.assertTrue(cal.titles_match('Birthday: Ann Lee (1990)', '  Ann   Lee '))

    def test_no_year_on_either_side_matches_on_name(self):
        self.assertTrue(cal.titles_match('Birthday: Ann Lee', 'Ann Lee'))

    def test_export_title_without_year_keeps_whole_title_as_name(self):
        self.assertEqual(cal.split_export_title('  Ann   Lee '), ('Ann   Lee', None))

    def test_different_name_with_same_year_does_not_match(self):
        self.assertFalse(cal.titles_match('Birthday: Bob Ray (1990)', 'Ann Lee 1990'))

    def test_no_year_on_generated_side_and_no_year_on_export_side_match_when_names_match(self):
        self.assertTrue(cal.titles_match('Birthday: Joe Doe', 'Joe Doe'))
        self.assertFalse(cal.titles_match('Birthday: Joe Doe', 'Bob Ray'))


def make_generated(name, birth_year, month, day):
    """Build a BirthdayEvent for tests with fictional names."""
    summary = f"Birthday: {name}" + (f" ({birth_year})" if birth_year is not None else "")
    return cal.BirthdayEvent(f"{name}-{month}-{day}@test", datetime.date(2000, month, day),
                             name, birth_year, summary)


class DedupeTests(unittest.TestCase):
    """Rules for find_new_events: one-to-one matching on title and month-day."""

    def test_same_title_and_month_day_is_removed(self):
        generated = [make_generated('Ann Lee', 1990, 3, 15)]
        export = [cal.ExportEvent('Ann Lee 1990', 3, 15)]
        new_events, matched = cal.find_new_events(generated, export)
        self.assertEqual(new_events, [])
        self.assertEqual(matched, 1)

    def test_same_title_different_month_day_is_kept(self):
        generated = [make_generated('Ann Lee', 1990, 3, 15)]
        export = [cal.ExportEvent('Ann Lee 1990', 3, 16)]
        new_events, matched = cal.find_new_events(generated, export)
        self.assertEqual(new_events, generated)
        self.assertEqual(matched, 0)

    def test_same_month_day_different_title_is_kept(self):
        generated = [make_generated('Ann Lee', 1990, 3, 15)]
        export = [cal.ExportEvent('Bob Ray 1990', 3, 15)]
        new_events, matched = cal.find_new_events(generated, export)
        self.assertEqual(new_events, generated)
        self.assertEqual(matched, 0)

    def test_year_does_not_affect_date_match(self):
        generated = [make_generated('Ann Lee', 1990, 3, 15)]
        export = [cal.ExportEvent('Ann Lee', 3, 15)]
        new_events, matched = cal.find_new_events(generated, export)
        self.assertEqual(new_events, [])
        self.assertEqual(matched, 1)

    def test_two_generated_one_export_removes_one(self):
        generated = [make_generated('Ann Lee', 1990, 3, 15),
                     make_generated('Ann Lee', 1990, 3, 15)]
        export = [cal.ExportEvent('Ann Lee 1990', 3, 15)]
        new_events, matched = cal.find_new_events(generated, export)
        self.assertEqual(matched, 1)
        self.assertEqual(new_events, [generated[1]])

    def test_two_generated_two_export_removes_both(self):
        generated = [make_generated('Ann Lee', 1990, 3, 15),
                     make_generated('Ann Lee', 1990, 3, 15)]
        export = [cal.ExportEvent('Ann Lee 1990', 3, 15),
                  cal.ExportEvent('Ann Lee 1990', 3, 15)]
        new_events, matched = cal.find_new_events(generated, export)
        self.assertEqual(new_events, [])
        self.assertEqual(matched, 2)

    def test_export_events_are_not_modified(self):
        generated = [make_generated('Ann Lee', 1990, 3, 15),
                     make_generated('Bob Ray', None, 7, 4)]
        export = [cal.ExportEvent('Ann Lee 1990', 3, 15),
                  cal.ExportEvent('Joe Doe', 1, 2)]
        before = list(export)
        cal.find_new_events(generated, export)
        self.assertEqual(export, before)

    def test_new_events_keep_generated_order(self):
        generated = [make_generated('Joe Doe', 1980, 1, 2),
                     make_generated('Ann Lee', 1990, 3, 15),
                     make_generated('Bob Ray', None, 7, 4)]
        export = [cal.ExportEvent('Ann Lee', 3, 15)]
        new_events, matched = cal.find_new_events(generated, export)
        self.assertEqual(new_events, [generated[0], generated[2]])
        self.assertEqual(matched, 1)

    def test_empty_export_keeps_every_generated_event(self):
        generated = [make_generated('Ann Lee', 1990, 3, 15),
                     make_generated('Bob Ray', None, 7, 4)]
        new_events, matched = cal.find_new_events(generated, [])
        self.assertEqual(new_events, generated)
        self.assertEqual(matched, 0)

    def test_different_years_in_both_titles_prevent_match(self):
        generated = [make_generated('Ann Lee', 1990, 3, 15)]
        export = [cal.ExportEvent('Ann Lee 1985', 3, 15)]
        new_events, matched = cal.find_new_events(generated, export)
        self.assertEqual(new_events, generated)
        self.assertEqual(matched, 0)


class DelimiterDetectionTests(ScratchMixin, unittest.TestCase):
    """detect_delimiter() on small header-only files with fictional column names."""

    def test_semicolon_header_gives_semicolon(self):
        path = self.write_csv('contacts.csv', 'First Name;Last Name;Birthday\n')
        self.assertEqual(cal.detect_delimiter(path), ';')

    def test_comma_header_gives_comma(self):
        path = self.write_csv('contacts.csv', 'First Name,Last Name,Birthday\n')
        self.assertEqual(cal.detect_delimiter(path), ',')

    def test_tab_header_gives_tab(self):
        path = self.write_csv('contacts.csv', 'First Name\tLast Name\tBirthday\n')
        self.assertEqual(cal.detect_delimiter(path), '\t')

    def test_one_column_header_raises_could_not_detect(self):
        path = self.write_csv('contacts.csv', 'First Name\n')
        with self.assertRaises(ValueError) as ctx:
            cal.detect_delimiter(path)
        self.assertIn('could not detect the column separator', str(ctx.exception))

    def test_tie_for_most_columns_raises_ambiguous(self):
        path = self.write_csv('contacts.csv', 'Birthday;Name,Birthday\n')
        with self.assertRaises(ValueError) as ctx:
            cal.detect_delimiter(path)
        self.assertIn('ambiguous column separator', str(ctx.exception))

    def test_byte_order_mark_does_not_change_result(self):
        path = self.write_csv('contacts.csv', '﻿First Name;Last Name;Birthday\n')
        self.assertEqual(cal.detect_delimiter(path), ';')

    def test_quoted_comma_inside_field_does_not_win(self):
        path = self.write_csv('contacts.csv', '"Last, Name";First Name;Birthday\n')
        self.assertEqual(cal.detect_delimiter(path), ';')

    def test_error_message_uses_path_as_given(self):
        path = self.write_csv('contacts.csv', 'First Name\n')
        with self.assertRaises(ValueError) as ctx:
            cal.detect_delimiter(path)
        self.assertIn(f'in {path}; use --delimiter', str(ctx.exception))

    def test_quoted_header_with_commas_gives_semicolon(self):
        # Read as comma-separated this header has 4 fields, but no field is Birthday
        path = self.write_csv('contacts.csv', 'First Name;"Last, First, Middle, Suffix";Birthday\n')
        self.assertEqual(cal.detect_delimiter(path), ';')

    def test_comma_header_with_birthday_gives_comma(self):
        path = self.write_csv('contacts.csv', 'First Name,Last Name,Birthday\n')
        self.assertEqual(cal.detect_delimiter(path), ',')

    def test_header_without_birthday_raises_could_not_detect(self):
        # ';' gives 3 columns, but none is Birthday, so no candidate is kept
        path = self.write_csv('contacts.csv', 'Name;Surname;Date\n')
        with self.assertRaises(ValueError) as ctx:
            cal.detect_delimiter(path)
        self.assertIn('could not detect the column separator', str(ctx.exception))

    def test_two_separators_with_birthday_tie_raises_ambiguous(self):
        # ';' gives ['Birthday', 'Name,Birthday'] and ',' gives ['Birthday;Name', 'Birthday']: 2 columns each
        path = self.write_csv('contacts.csv', 'Birthday;Name,Birthday\n')
        with self.assertRaises(ValueError) as ctx:
            cal.detect_delimiter(path)
        self.assertIn('ambiguous column separator', str(ctx.exception))


class DelimiterOptionTests(ScratchMixin, unittest.TestCase):
    """The --delimiter option is parsed and validated by the command line."""

    def run_script(self, *args, cwd=None):
        return subprocess.run([sys.executable, SCRIPT, *args], cwd=cwd or self.tmp,
                              capture_output=True, text=True)

    def test_help_lists_delimiter_option(self):
        result = self.run_script('--help')
        self.assertEqual(result.returncode, 0)
        self.assertIn('--delimiter', result.stdout)

    def test_semicolon_delimiter_is_accepted(self):
        result = self.run_script('-i', EXAMPLE_CSV, '--delimiter', ';', '--ics')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_comma_delimiter_is_accepted(self):
        result = self.run_script('-i', EXAMPLE_CSV, '--delimiter', ',', '--ics')
        self.assertNotEqual(result.returncode, 2, result.stderr)

    def test_tab_delimiter_is_accepted(self):
        result = self.run_script('-i', EXAMPLE_CSV, '--delimiter', 'tab', '--ics')
        self.assertNotEqual(result.returncode, 2, result.stderr)

    def test_upper_case_tab_delimiter_is_accepted(self):
        result = self.run_script('-i', EXAMPLE_CSV, '--delimiter', 'TAB', '--ics')
        self.assertNotEqual(result.returncode, 2, result.stderr)

    def test_invalid_delimiter_exits_two_with_message(self):
        result = self.run_script('-i', EXAMPLE_CSV, '--delimiter', '|', '--ics')
        self.assertEqual(result.returncode, 2)
        self.assertIn('delimiter', result.stderr)


class SeparatorTests(ScratchMixin, unittest.TestCase):
    """The column separator is used for reading and cleaning, and failures write nothing."""

    def run_script(self, *args, cwd=None):
        return subprocess.run([sys.executable, SCRIPT, *args], cwd=cwd or self.tmp,
                              capture_output=True, text=True)

    def make_copy(self, name, delimiter):
        """Copy example.csv with another separator. The source has no commas or tabs in fields."""
        with open(EXAMPLE_CSV, newline='', encoding='utf-8-sig') as f:
            rows = list(csv.reader(f, delimiter=';'))
        path = os.path.join(self.tmp, name)
        with open(path, 'w', encoding='utf-8-sig', newline='') as f:
            csv.writer(f, delimiter=delimiter, lineterminator='\n').writerows(rows)
        return path

    def ics_summaries_and_starts(self, path):
        return [(event['SUMMARY'], event['DTSTART']) for event in parse_ics_events(path)]

    def test_comma_and_tab_copies_give_the_same_events_as_semicolon(self):
        comma_csv = self.make_copy('comma.csv', ',')
        tab_csv = self.make_copy('tab.csv', '\t')
        expected = os.path.join(self.tmp, 'semicolon.ics')
        result = self.run_script('-i', EXAMPLE_CSV, '--ics', expected)
        self.assertEqual(result.returncode, 0, result.stderr)
        for name, path in (('comma', comma_csv), ('tab', tab_csv)):
            out = os.path.join(self.tmp, f'{name}.ics')
            result = self.run_script('-i', path, '--ics', out)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.ics_summaries_and_starts(out),
                             self.ics_summaries_and_starts(expected), name)

    def test_comma_input_gives_cleaned_csv_with_comma_separator(self):
        comma_csv = self.make_copy('comma.csv', ',')
        out = os.path.join(self.tmp, 'clean.csv')
        result = self.run_script('-i', comma_csv, '--csv', out)
        self.assertEqual(result.returncode, 0, result.stderr)
        with open(out, encoding='utf-8') as f:
            header = f.readline().rstrip('\r\n')
        self.assertEqual(header, 'First Name,Middle Name,Last Name,Birthday')
        with open(out, newline='', encoding='utf-8') as f:
            rows = list(csv.DictReader(f, delimiter=','))
        self.assertEqual(rows, read_clean_rows(EXPECTED_CLEAN_CSV))
        self.assertEqual([r['First Name'] for r in rows],
                         ['Robert', 'John', 'Margaret', 'Alexandra', 'Bertha', 'Leo', 'Lily'])

    def test_semicolon_input_cleaned_csv_is_byte_identical_to_expected(self):
        out = os.path.join(self.tmp, 'clean.csv')
        result = self.run_script('-i', EXAMPLE_CSV, '--csv', out)
        self.assertEqual(result.returncode, 0, result.stderr)
        with open(out, 'rb') as f:
            produced = f.read()
        with open(EXPECTED_CLEAN_CSV, 'rb') as f:
            expected = f.read()
        self.assertEqual(produced, expected)

    def test_delimiter_option_overrides_ambiguous_detection(self):
        # The header has one ';' and one ',' after a 3-comma prefix, so both give 4 columns
        path = self.write_csv('contacts.csv',
                              'Tags,Labels,Group,Notes;First Name;Last Name;Birthday\n'
                              'x,y,z,w;Ann;Lee;1990-05-01\n')
        out = os.path.join(self.tmp, 'clean.csv')
        result = self.run_script('-i', path, '--delimiter', ';', '--csv', out)
        self.assertEqual(result.returncode, 0, result.stderr)
        with open(out, encoding='utf-8') as f:
            header = f.readline().rstrip('\r\n')
        self.assertEqual(header, HEADER)
        self.assertEqual(read_clean_rows(out),
                         [{'First Name': 'Ann', 'Middle Name': '', 'Last Name': 'Lee',
                           'Birthday': '1990-05-01'}])

    def test_no_detectable_separator_exits_one_and_writes_nothing(self):
        path = self.write_csv('contacts.csv', 'First Name\nAnn\n')
        csv_out = os.path.join(self.tmp, 'clean.csv')
        ics_out = os.path.join(self.tmp, 'birthdays.ics')
        result = self.run_script('-i', path, '--csv', csv_out, '--ics', ics_out)
        self.assertEqual(result.returncode, 1)
        self.assertIn('Error: could not detect the column separator', result.stderr)
        self.assertFalse(os.path.exists(csv_out))
        self.assertFalse(os.path.exists(ics_out))

    def test_ambiguous_separator_exits_one_and_writes_nothing(self):
        path = self.write_csv('contacts.csv', 'Birthday;Name,Birthday\nAnn;Lee,1990-05-01\n')
        csv_out = os.path.join(self.tmp, 'clean.csv')
        ics_out = os.path.join(self.tmp, 'birthdays.ics')
        result = self.run_script('-i', path, '--csv', csv_out, '--ics', ics_out)
        self.assertEqual(result.returncode, 1)
        self.assertIn('Error: ambiguous column separator', result.stderr)
        self.assertFalse(os.path.exists(csv_out))
        self.assertFalse(os.path.exists(ics_out))

    def test_ambiguous_separator_writes_nothing_with_calendar_export(self):
        path = self.write_csv('contacts.csv', 'Birthday;Name,Birthday\nAnn;Lee,1990-05-01\n')
        csv_out = os.path.join(self.tmp, 'clean.csv')
        result = self.run_script('-i', path, '--calendar', os.path.join(FIXTURES, 'export.ics'),
                                 '--csv', csv_out)
        self.assertEqual(result.returncode, 1)
        self.assertIn('Error: ambiguous column separator', result.stderr)
        for name in ('clean.csv', 'birthdays.ics', 'birthdays_new.ics'):
            self.assertFalse(os.path.exists(os.path.join(self.tmp, name)), name)

    def test_missing_input_detected_path_exits_one_with_message(self):
        result = self.run_script('-i', os.path.join(self.tmp, 'nope.csv'), '--csv')
        self.assertEqual(result.returncode, 1)
        self.assertIn('Error: input file not found', result.stderr)

    def test_missing_input_with_delimiter_exits_one_with_message(self):
        result = self.run_script('-i', os.path.join(self.tmp, 'nope.csv'), '--delimiter', ';', '--ics')
        self.assertEqual(result.returncode, 1)
        self.assertIn('Error: input file not found', result.stderr)


class MissingColumnWarningTests(ScratchMixin, unittest.TestCase):
    """A missing expected column prints one warning on stderr and the run continues."""

    def run_script(self, *args, cwd=None):
        return subprocess.run([sys.executable, SCRIPT, *args], cwd=cwd or self.tmp,
                              capture_output=True, text=True)

    def warnings(self, result):
        return [line for line in result.stderr.splitlines() if line.startswith('Warning')]

    def test_exact_header_prints_no_warning(self):
        path = self.write_csv('contacts.csv',
                              'First Name;Last Name;Birthday\nAnn;Lee;1990-05-01\n')
        result = self.run_script('-i', path, '--csv', os.path.join(self.tmp, 'clean.csv'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.warnings(result), [])

    def test_quoted_header_reports_only_last_name(self):
        path = self.write_csv('contacts.csv',
                              'First Name;"Last, First, Middle, Suffix";Birthday\n'
                              'Ann;Lee, Ann, Q, Jr;1990-05-01\n')
        result = self.run_script('-i', path, '--ics', os.path.join(self.tmp, 'birthdays.ics'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.warnings(result),
                         [f"Warning: column 'Last Name' not found in {path}; "
                          "its values will be empty"])

    def test_missing_birthday_column_prints_warning_and_exits_zero(self):
        path = self.write_csv('contacts.csv',
                              'First Name;Last Name;Nickname\nAnn;Lee;Annie\n')
        result = self.run_script('-i', path, '--delimiter', ';',
                                 '--csv', os.path.join(self.tmp, 'clean.csv'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.warnings(result),
                         [f"Warning: column 'Birthday' not found in {path}; "
                          "its values will be empty"])

    def test_missing_middle_name_prints_no_warning(self):
        path = self.write_csv('contacts.csv',
                              'First Name;Last Name;Birthday\nAnn;Lee;1990-05-01\n')
        result = self.run_script('-i', path, '--ics', os.path.join(self.tmp, 'birthdays.ics'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('Middle Name', result.stderr)
        self.assertEqual(self.warnings(result), [])

    def test_missing_input_file_keeps_error_and_no_warning(self):
        result = self.run_script('-i', os.path.join(self.tmp, 'nope.csv'), '--csv')
        self.assertEqual(result.returncode, 1)
        self.assertIn('Error: input file not found', result.stderr)
        self.assertNotIn('Warning', result.stderr)

    def test_warning_does_not_stop_csv_and_ics_output(self):
        path = self.write_csv('contacts.csv',
                              'First Name;"Last, First, Middle, Suffix";Birthday\n'
                              'Ann;Lee, Ann, Q, Jr;1990-05-01\n')
        csv_out = os.path.join(self.tmp, 'clean.csv')
        ics_out = os.path.join(self.tmp, 'birthdays.ics')
        result = self.run_script('-i', path, '--csv', csv_out, '--ics', ics_out)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.warnings(result)), 1)
        self.assertTrue(os.path.exists(csv_out))
        self.assertTrue(os.path.exists(ics_out))

    def test_warnings_are_printed_in_expected_order(self):
        path = self.write_csv('contacts.csv', 'Middle Name;Birthday\nQ;1990-05-01\n')
        result = self.run_script('-i', path, '--ics', os.path.join(self.tmp, 'birthdays.ics'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.warnings(result),
                         [f"Warning: column 'First Name' not found in {path}; "
                          "its values will be empty",
                          f"Warning: column 'Last Name' not found in {path}; "
                          "its values will be empty"])


if __name__ == '__main__':
    unittest.main()
