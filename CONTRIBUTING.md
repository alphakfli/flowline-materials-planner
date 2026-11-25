# Contributing

Issues and pull requests are welcome.

1. Fork and create a branch.
2. `pip install -e ".[dev]"`
3. Make the change with a test in `tests/`.
4. Run `pytest -q`, `ruff check src app tests scripts` and `python scripts/check_sensitive.py`.
5. Open a pull request describing the change and why.

Please never commit real company data. Use the sample generator (`src/flowline/sample.py`) or anonymized data.
