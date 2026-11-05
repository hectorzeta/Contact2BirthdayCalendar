# CLAUDE.md

Project rules and workflow for `contactsToCalendar.py`. These apply to every change.

The behavior and output formats (calendar, cleaned CSV, CLI, birthday formats) are in [`docs/SPEC.md`](docs/SPEC.md). Read it before changing behavior.

Repo: `hectorzeta/Contact2BirthdayCalendar` on GitHub (private).

## Privacy

- `contacts.csv`, `contacts_clean.csv` and `birthdays.ics` hold real people's data. Never commit them, never copy their contents into code, tests, README or commit messages, and keep them out of `.gitignore` exceptions.
- Tests and examples use only fictional names. Do not reuse real-looking names from any file.
- Do not delete or recreate the user's data files. If one is missing, report it and ask.

## Git and GitHub

- Commit only when the user asks. Push only when the user asks.
- Work on a feature branch. Do not push to `main` on GitHub. Code reaches `main` only through a merged PR.
- Each new feature is implemented on its own branch, created from `main`. Its PR is the way code gets into `main`.
- Commit messages end with: `Co-Authored-By: Claude <model used, e.g. Haiku 5.5>`
- PR descriptions end with: `🤖 Generated with [Claude Code] (<model used, e.g. Haiku 5.5>)`
- Do not change the user's global git config. If HTTPS auth is needed, pass the GitHub CLI credential helper for that one command:
  `git -c credential.helper= -c 'credential.helper=!gh auth git-credential' push ...`
- Ask before any action that makes something public or creates a new repository.

## Core Rules

- Always ask for confirmation when modifying CLAUDE.md
- If a task matches a skill, invoke it with the `Skill` tool before acting.
- Skills are located in `.claude/skills/<skill-name>/SKILL.md`.
- Follow the skill workflow strictly; do not partially apply it.
- Never skip required steps such as spec, plan, or test when a skill demands them.
- Standard library only. Do not add runtime dependencies.
- Python 3.10+ compatible. CI runs 3.10, 3.12 and 3.14.
- Every behavior change needs a test in `tests/test_contacts_to_calendar.py`, a change to `docs/SPEC.md` if the specified behavior changes, and a README update if the user-facing behavior changes.
- `ruff check .` must pass (ruff 0.8.4, the version CI pins). Run it before committing.

## Tests

- Run the suite: `python3 tests/run_tests.py` (writes `tests/reports/test-report.html`, exit 1 on failure).
- Or: `python3 -m unittest discover -s tests -v`.
- Fixtures live in `tests/fixtures/` (`example.csv`, fictional) and expected output in `tests/expected/`.
- `tests/reports/` is generated and git-ignored.

## CI

- `.github/workflows/ci.yml` runs on pull requests only, to save Actions minutes on the private repo.
- Jobs: ruff lint, and tests on Python 3.10, 3.12 and 3.14 with the HTML report uploaded as an artifact.

## Working style

- Each task is implemented by a subagent.
- Ask when a request is ambiguous or when an action is hard to reverse.
- Keep temporary files in the session scratchpad, not in the project.
- Report failures faithfully. If something could not be verified here (for example, another Python version), say so.
