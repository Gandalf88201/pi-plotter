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
| 1 | ~~**Projects**: save and reopen everything in one file~~ — **done** (.piplot, `piplotter/projects.py`, `web/project.js`) | ✓ (.lml) | ✓ (.opju) | Autosave and recovery after a crash: **done** (`piplotter/autosave.py`). Very large projects written to disk and streamed, never built in memory: **done** (`App.save_project_file`, one-off `/download/` links). |
| 2 | ~~**Analyses that follow the data**~~ — **done**: when a table is edited, the results and curves on the copies are recomputed | — | ✓ (auto recalculate) | Results remember their source (`source` of every result), run again on the last version of the table — also numbers only in the panel and analyses of results — and are marked outdated meanwhile (⟳) or when they cannot run (!, *Run again*): **done**. |
| 3 | ~~**Fit several data sets at once** (global fit, shared parameters) and a **fit report** table~~ — **done** (`analyses/global_fit.py`, `ctx.files`) | partial | ✓ | Weights from Y errors, parameters shared by some curves, fixed parameters: done. Next: constraints between parameters (e.g. A₂ = 2·A₁). |
| 4 | ~~**Masking points**~~ — **done** (exclude rows / click points) (exclude outliers from fits and statistics by clicking them) | ✓ | ✓ | Store the mask as an operation of the edit log. |
| 5 | ~~**Batch analysis**: the same analysis on many files, results in one table~~ — **done** (`App.batch_analysis`, *Run on all n files*) | — | ✓ (Batch Processing) | Next: choose the files (not all loaded ones), files from a folder without loading them one by one. |
| 6 | ~~**Layouts**: several panels with different data/kinds in one figure, insets, reference lines and bands, axis breaks~~ — **done** (`spec.compose`, `spec.inset`, `spec.refs`, `axes.xbreak` / `ybreak`) | ✓ | ✓ | Next: panels of different sizes (spanning cells); a different scale on each side of a break. |
| 7 | ~~Signal tools: interpolation/resampling, FFT filters, convolution/deconvolution, curve arithmetic~~ — **done** (`interpolate`, `frequency_filter`, `convolution`, `curve_math`, `piplotter/signals.py`) | ✓ | ✓ | Next: peak-preserving resampling of very long signals (decimation), 2D filters for matrices (with 9). |
| 8 | ~~Statistics: more tests (paired, χ², Fisher, post-hoc), PCA, clustering, survival~~ — **done** (`compare_groups`: Friedman, Games–Howell, Dunn/Holm; `contingency`, `pca`, `clustering`, `survival`; SciPy only) | some | ✓ | Next: two-way / repeated-measures ANOVA, mixed models (statsmodels, BSD), Cox regression. |
| 9 | ~~Matrices / images (2D data as a grid, image to data)~~ — **done** (`piplotter/matrices.py`, image reader, `matrix_transform`, `matrix_filter`, `matrix_profile`, `matrix_stats`) | ✓ | ✓ | Next: region of interest of any shape, particle / spot detection, colour images as three channels at once. |
| 10 | ~~Scripting console (Python) on the open data~~ — **done** (`piplotter/console.py`, `web/console.js`, tab *Python*) | ✓ (Cantor) | ✓ (Python, LabTalk) | Next: completion of names, keeping the console's code in projects, a script run on every file (with batch). |

## Code structure (robustness)

| Area | Now | To do |
|---|---|---|
| Front end | **Split done** (2026-10-12): `core`, `install`, `controls`, `figure`, `data`, `export`, `modules`, `app` + `table`, `files`, `analysis`, `project` — same global scope, loaded in order | **Events done** (2026-10-14): `Bus` in `core.js` — the parts announce what changed (`dataset`, `dataset:edited`, `figure:render`, `views:changed`, `lang`, `session:new`…) and listen, instead of calling each other. Next: the state itself (`state`) behind setters that emit, so no part changes it unseen. |
| Front-end tests | **Done**: `tests/test_ui.py` (Playwright + system Chrome) — 17 paths, fails on any JS error | Add a path per new feature. |
| Service | one `server.py` with an if-chain of routes | A route table; one module per area (files, tables, analyses, render); a versioned JSON schema for the figure spec and the project file. |
| Data model | data sets live in memory, rebuilt from sources | Formalise "source + operations" for every data set (file, blank, edit, analysis) — already true for tables and analyses — so projects (1) and recomputation (2) come for free. |
| Analyses | plugins with params, Result, overlays; advisor rules | Keep the advisor's rules in data (one table) and let each built-in analysis declare `suits`, as plugins can. |

## Proposed order

1. ~~Projects (gap 1)~~, ~~front-end split + smoke tests~~ done.
2. ~~Analyses that follow the data (2) and masking (4)~~ done.
3. ~~Global fit + fit report (3)~~ and ~~batch (5)~~ done; global-fit refinements and ~~layouts (6)~~ done; ~~signal tools (7)~~ done.
4. ~~Statistics (8)~~ and ~~axis breaks (rest of 6)~~ done.
5. ~~Matrices (9)~~ and ~~a console (10)~~ done: every gap of the table above is closed. ~~Autosave~~ and ~~events between the parts of the page~~ done; next: the "Next" items of each row.
