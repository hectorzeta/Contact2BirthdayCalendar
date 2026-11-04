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
        raw_line = next(l for l in read_ics_lines(out) if l.startswith('SUMMARY'))
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

    def test_no_options_prints_a_hint_and_exits_one(self):
        result = self.run_script('-i', EXAMPLE_CSV)
        self.assertEqual(result.returncode, 1)
        self.assertIn('Nothing to do', result.stderr)

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


if __name__ == '__main__':
    unittest.main()
