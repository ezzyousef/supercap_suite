# Test report

See UPGRADE_HANDOFF.md and ../EQUATION_REGRESSION_REPORT.md.

| Command | Result |
|---|---|
| full suite | 307 passed |
| tests/test_oracle_equations.py | 24 passed |
| tests/test_hostile_files.py | 16 passed (4 failed before the fix) |
| labkit sync --apply --test | 267 passed during sync |
