"""Run the test suite and write an HTML report.

Usage (from the project root):

    python3 tests/run_tests.py                     # report to tests/reports/test-report.html
    python3 tests/run_tests.py -o my-report.html   # choose the report file

The exit code is 0 when every test passed (skips and expected failures count
as passing) and 1 otherwise, so it can be used in scripts or CI.
"""
import argparse
import datetime
import html
import os
import platform
import sys
import time
import traceback
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(TESTS_DIR)
DEFAULT_REPORT = os.path.join(TESTS_DIR, 'reports', 'test-report.html')

# Outcome labels used in the report, in the order they appear in the summary
OUTCOMES = ['passed', 'failed', 'error', 'skipped', 'expected failure', 'unexpected success']
PASSING = {'passed', 'skipped', 'expected failure'}


class RecordingResult(unittest.TextTestResult):
    """A normal text result that also remembers each test's outcome and timing."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []
        self._started = None

    def startTest(self, test):
        self._started = time.perf_counter()
        super().startTest(test)

    def _record(self, test, outcome, detail=''):
        duration = time.perf_counter() - (self._started or time.perf_counter())
        self.records.append({
            'name': test.id(),
            'outcome': outcome,
            'detail': detail,
            'duration': duration,
        })

    @staticmethod
    def _format_exc(err):
        return ''.join(traceback.format_exception(*err)).rstrip()

    def addSuccess(self, test):
        super().addSuccess(test)
        self._record(test, 'passed')

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._record(test, 'failed', self._format_exc(err))

    def addError(self, test, err):
        super().addError(test, err)
        self._record(test, 'error', self._format_exc(err))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._record(test, 'skipped', reason)

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self._record(test, 'expected failure', self._format_exc(err))

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self._record(test, 'unexpected success', 'Test was marked as an expected failure but passed.')


def run_suite(verbosity):
    """Discover and run the tests in tests/. Returns (result, total_seconds)."""
    if PROJECT_DIR not in sys.path:
        sys.path.insert(0, PROJECT_DIR)
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=TESTS_DIR, top_level_dir=TESTS_DIR)
    stream = sys.stdout
    runner = unittest.TextTestRunner(stream=stream, verbosity=verbosity,
                                     resultclass=RecordingResult)
    started = time.perf_counter()
    result = runner.run(suite)
    return result, time.perf_counter() - started


def short_name(test_id):
    """'test_module.TestClass.test_name' -> 'TestClass.test_name' for display."""
    parts = test_id.split('.')
    return '.'.join(parts[-2:]) if len(parts) >= 2 else test_id


def build_html(records, total_seconds):
    counts = {label: 0 for label in OUTCOMES}
    for rec in records:
        counts[rec['outcome']] += 1
    all_passing = all(rec['outcome'] in PASSING for rec in records)
    status_text = 'ALL PASSED' if all_passing else 'FAILURES'
    status_class = 'pass' if all_passing else 'fail'
    generated = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    summary_cards = ''.join(
        f'<div class="card {label.replace(" ", "-")}"><div class="num">{counts[label]}</div>'
        f'<div class="lbl">{label}</div></div>'
        for label in OUTCOMES
    )

    rows = []
    for rec in records:
        css = rec['outcome'].replace(' ', '-')
        detail = ''
        if rec['detail']:
            detail = f'<details><summary>details</summary><pre>{html.escape(rec["detail"])}</pre></details>'
        rows.append(
            f'<tr class="{css}">'
            f'<td><span class="badge {css}">{html.escape(rec["outcome"])}</span></td>'
            f'<td class="name" title="{html.escape(rec["name"])}">{html.escape(short_name(rec["name"]))}</td>'
            f'<td class="num">{rec["duration"] * 1000:.1f} ms</td>'
            f'<td>{detail}</td>'
            '</tr>'
        )

    python_version = html.escape(platform.python_version())
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Test report: contactsToCalendar</title>
<style>
  :root {{
    --bg: #ffffff; --fg: #1d1d1f; --muted: #6e6e73; --line: #d2d2d7;
    --pass: #1a7f37; --fail: #cf222e; --warn: #9a6700; --info: #0969da;
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      --bg: #161617; --fg: #f5f5f7; --muted: #a1a1a6; --line: #3a3a3c;
      --pass: #3fb950; --fail: #ff7b72; --warn: #d29922; --info: #58a6ff;
    }}
  }}
  :root[data-theme="dark"] {{
    --bg: #161617; --fg: #f5f5f7; --muted: #a1a1a6; --line: #3a3a3c;
    --pass: #3fb950; --fail: #ff7b72; --warn: #d29922; --info: #58a6ff;
  }}
  body {{ background: var(--bg); color: var(--fg); font: 15px/1.5 system-ui, sans-serif;
         margin: 0; padding: 16px; }}
  main {{ max-width: 1000px; margin: 0 auto; }}
  h1 {{ font-size: 1.5rem; margin: 0.2em 0; }}
  .meta {{ color: var(--muted); margin-bottom: 16px; }}
  .status {{ font-weight: 700; padding: 4px 10px; border-radius: 6px; display: inline-block; }}
  .status.pass {{ color: var(--pass); border: 1px solid var(--pass); }}
  .status.fail {{ color: var(--fail); border: 1px solid var(--fail); }}
  .cards {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 16px 0; }}
  .card {{ border: 1px solid var(--line); border-radius: 8px; padding: 8px 12px; min-width: 110px; }}
  .card .num {{ font-size: 1.4rem; font-weight: 700; }}
  .card .lbl {{ color: var(--muted); font-size: 0.85rem; }}
  .card.passed .num {{ color: var(--pass); }}
  .card.failed .num, .card.error .num {{ color: var(--fail); }}
  .card.skipped .num, .card.expected-failure .num, .card.unexpected-success .num {{ color: var(--warn); }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ text-align: left; padding: 8px; border-bottom: 1px solid var(--line); vertical-align: top; }}
  th {{ color: var(--muted); font-weight: 600; font-size: 0.85rem; }}
  td.num {{ white-space: nowrap; color: var(--muted); }}
  td.name {{ word-break: break-word; }}
  .badge {{ font-size: 0.8rem; font-weight: 600; padding: 2px 8px; border-radius: 999px;
           border: 1px solid currentColor; white-space: nowrap; }}
  .badge.passed {{ color: var(--pass); }}
  .badge.failed, .badge.error {{ color: var(--fail); }}
  .badge.skipped, .badge.expected-failure, .badge.unexpected-success {{ color: var(--warn); }}
  details summary {{ cursor: pointer; color: var(--info); }}
  pre {{ white-space: pre-wrap; word-break: break-word; font-size: 0.85rem;
        background: transparent; border: 1px solid var(--line); border-radius: 6px; padding: 8px; }}
  @media (max-width: 600px) {{
    thead {{ display: none; }}
    tr {{ display: block; border-bottom: 1px solid var(--line); padding: 6px 0; }}
    td {{ display: block; border: none; padding: 2px 0; }}
  }}
</style>
</head>
<body>
<main>
  <h1>Test report: contactsToCalendar</h1>
  <div class="meta">Generated {generated} &middot; Python {python_version} &middot;
    {len(records)} tests in {total_seconds:.2f} s</div>
  <span class="status {status_class}">{status_text}</span>
  <div class="cards">{summary_cards}</div>
  <table>
    <thead><tr><th>Result</th><th>Test</th><th>Time</th><th>Details</th></tr></thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>
</main>
</body>
</html>
"""


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the tests and write an HTML report.")
    parser.add_argument('-o', '--output', default=DEFAULT_REPORT, metavar='FILE',
                        help=f"report file to write (default: {os.path.relpath(DEFAULT_REPORT, PROJECT_DIR)})")
    parser.add_argument('-v', '--verbose', action='count', default=1,
                        help="show each test name while running (use -q to hide)")
    parser.add_argument('-q', '--quiet', action='store_true', help="show only the summary")
    args = parser.parse_args(argv)

    verbosity = 0 if args.quiet else min(args.verbose, 2)
    result, total_seconds = run_suite(verbosity)
    records = result.records

    output_dir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(output_dir, exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(build_html(records, total_seconds))

    failed = [r for r in records if r['outcome'] not in PASSING]
    print(f"\nReport written to {os.path.abspath(args.output)}")
    print(f"Tests: {len(records)}  Failing: {len(failed)}")
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
