# Handoff: supercap_suite upgrade (repository 03)

| | |
|---|---|
| Local path | `E:\Lab Apps\supercap_suite\supercap_suite` |
| Branch | `upgrade/03-supercap`, from `feature/licensing` at `c3ce665` |
| Version | 2.2.1 → 2.3.0 |
| Tests | `py -3 -m pytest -q -p no:cacheprovider` (QT_QPA_PLATFORM=offscreen): **307 passed** (260 at baseline without the licence tests, 267 with labkit 1.2.0, +24 oracle, +16 hostile-file) |
| Installer | Not rebuilt in this round (`build_installer.ps1` / CI workflow unchanged) |

## Audit summary (prompt milestones against the code)

| # | Milestone | State before | This round |
|---|---|---|---|
| 1 | Scientific QA: conventions, units, assumptions | **Largely DONE** in an earlier review (`docs/REVIEW_LOG.md`): integral GCD offset, IR exclusion, ESR 2I/I, energy blocked for 3-electrode data, Coulombic efficiency, EIS weighting/AICc/KK, DSC units | Added the missing acceptance item: **independent numerical oracles** for every equation (24 tests) and `docs/EQUATION_REGRESSION_REPORT.md` with worked numbers. All agreed with the physics; one documented weakness confirmed with numbers (KK % test passes 30 % drift; the trend flag catches it) |
| 2 | Project Workspace | MISSING | **Not started.** A new project format with migrations, archives and replicate grouping is a multi-day feature; it needs its own design round and the owner's input on what a "project" holds |
| 3 | Advanced analysis | PARTIAL: KK, DRT, DCT, AICc auto-fit, Coulombic efficiency, retention, Ragone exist | Not extended. Bootstrap uncertainties, topology editor, self-discharge fitting: not started |
| 4 | Publishable workflows | PARTIAL: house-style figures, Excel/Origin export | Not extended |
| 5 | UX | PARTIAL: 2.2.0 accessibility round, Cancel for long fits | Not extended; labkit 1.2.0 (DataTable, show_error, History.transaction) is now available to adopt |
| 6 | Security/performance: hostile files | MISSING | **DONE for the text importer**: 16 tests. Found and fixed a silent data-corruption bug |

## Defect fixed

A CSV whose first data row has more values than the header was loaded with the extra leading values as row labels, so `1,2,3,4,5` became t = 4, v = 5 and the other rows vanished as "blank". Values that do not exist in the file reached the analysis without any warning. Now refused with the line number; a mid-file extra value names its line; UTF-16 exports load; an empty file says so. Regression tests failed first, as the project's rule requires.

## Not verified

Real anonymised instrument exports (none supplied); the installed .exe; Excel/Origin round-trip of the new code paths (none of the export code changed).

## Next steps (for a later round on this repo)

1. Adopt `labkit.io.preview_table` in the import path so users see decimal-comma, unit and missing-value warnings before analysis.
2. `Provenance(...).write_beside(export)` on Excel and Origin exports.
3. Design the Project Workspace (owner input needed on scope).

## Rollback

`git switch feature/licensing`. labkit can be returned to 1.1.0 with `py -3 sync.py --restore supercap_suite` from the labkit folder (backup kept in `.labkit-backup/`).
