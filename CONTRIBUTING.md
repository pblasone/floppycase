# Contributing to FloppyCase

Thanks for helping. FloppyCase is a small GPL-3.0-or-later project aimed at
making classic Amiga games easy to run on Linux with Amiberry.

## Development setup

Requirements: Ubuntu/Debian-like Linux, Python 3.10+, and `python3-tk` if you
want to exercise the GUI.

```bash
git clone https://github.com/pblasone/floppycase.git
cd floppycase
python3 -m venv .venv
source .venv/bin/activate
pip install -U -e ".[dev]"
pytest
```

For a day-to-day install that puts `floppycase` on your PATH:

```bash
sudo apt install pipx python3-tk python3-venv
pipx install .
# after pulling changes:
pipx reinstall .
```

## Pull requests

- Keep changes focused; open separate PRs for unrelated work.
- Add or update tests when behaviour changes.
- Run `pytest` before opening a PR.
- Do not commit Kickstart ROMs, game images, or personal `~/FloppyCase` data.
- Prefer clear module/CLI help text over dense inline comments.

## Code of conduct

Be respectful in issues and PRs. Harassment or bad-faith behaviour will not be
tolerated.

## Questions

Open a GitHub issue for bugs and feature ideas. For security reports, see
[SECURITY.md](SECURITY.md).
