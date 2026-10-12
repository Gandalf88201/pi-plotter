# π-plotter — roadmap towards a robust alternative to LabPlot and Origin

Written 2026-10-12 (version 0.2.3). What π-plotter has, what LabPlot (free, GPL) and OriginPro (commercial) offer that
it does not, and the order in which to close the gaps. Only open-source (OSI) modules, as for everything else.

## Where π-plotter stands

Strong already: reading almost any file format; a figure suggested from the data; publication styles; Recipes that
chain analyses and answer in plain words; references to cite with every result; plugins and PyPI modules; manual in
English and Italian; several files in one graph.

Added in this round: spreadsheet editing of the data (cells, paste, rows/columns, column formulas, undo, new empty
table) with every edit kept as a replayable list of operations; analyses suggested by the figure on screen
(`piplotter/advisor.py`); fitted values written in the figure; fits of several files gathered on one copy.

## Gaps, by how much they matter to a scientist

| # | Gap | LabPlot | Origin | Notes |
|---|---|---|---|---|
| 1 | ~~**Projects**: save and reopen everything in one file~~ — **done** (.piplot, `piplotter/projects.py`, `web/project.js`) | ✓ (.lml) | ✓ (.opju) | Next: autosave / recover the last work after a crash, and streaming very large projects instead of building them in memory. |
| 2 | ~~**Analyses that follow the data**~~ — **done**: when a table is edited, the results and curves on the copies are recomputed | — | ✓ (auto recalculate) | Results remember their source; rerun them on the new version of the table, mark them as outdated meanwhile. |
| 3 | **Fit several data sets at once** (global fit, shared parameters, e.g. one lifetime for all curves) and a **fit report** table with all fits | partial | ✓ | Natural next step after "fits of every file on one copy". |
| 4 | ~~**Masking points**~~ — **done** (exclude rows / click points) (exclude outliers from fits and statistics by clicking them) | ✓ | ✓ | Store the mask as an operation of the edit log. |
| 5 | **Batch analysis**: the same analysis on many files, results in one table | — | ✓ (Batch Processing) | The analysis spec is already data; loop it over the loaded files. |
| 6 | **Layouts**: several panels with different data/kinds in one figure, insets, axis breaks, reference lines and bands | ✓ | ✓ | Today: panels only one per file. |
| 7 | Signal tools: interpolation/resampling, FFT filters, convolution/deconvolution, differentiation as data | ✓ | ✓ | SciPy covers all of them. |
| 8 | Statistics: more tests (paired, χ², Fisher, post-hoc), PCA, clustering, survival | some | ✓ | statsmodels, scikit-learn (BSD). |
| 9 | Matrices / images (2D data as a grid, image to data) | ✓ | ✓ | Heat maps exist; a matrix object does not. |
| 10 | Scripting console (Python) on the open data | ✓ (Cantor) | ✓ (Python, LabTalk) | Plugins cover part; an interactive console is missing. |

## Code structure (robustness)

| Area | Now | To do |
|---|---|---|
| Front end | **Split done** (2026-10-12): `core`, `install`, `controls`, `figure`, `data`, `export`, `modules`, `app` + `table`, `files`, `analysis`, `project` — same global scope, loaded in order | Next: one state store with explicit events (dataset-changed, spec-changed) instead of direct calls between files. |
| Front-end tests | **Done**: `tests/test_ui.py` (Playwright + system Chrome) — 4 paths, fails on any JS error | Add a path per new feature. |
| Service | one `server.py` with an if-chain of routes | A route table; one module per area (files, tables, analyses, render); a versioned JSON schema for the figure spec and the project file. |
| Data model | data sets live in memory, rebuilt from sources | Formalise "source + operations" for every data set (file, blank, edit, analysis) — already true for tables and analyses — so projects (1) and recomputation (2) come for free. |
| Analyses | plugins with params, Result, overlays; advisor rules | Keep the advisor's rules in data (one table) and let each built-in analysis declare `suits`, as plugins can. |

## Proposed order

1. ~~Projects (gap 1)~~, ~~front-end split + smoke tests~~ done.
2. ~~Analyses that follow the data (2) and masking (4)~~ done.
3. **Global fit + fit report** (3) and **batch** (5).
4. **Layouts** (6), then signal tools (7) and statistics (8).
5. Matrices (9) and a console (10).
