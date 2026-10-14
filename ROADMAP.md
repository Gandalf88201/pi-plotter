# π-plotter — roadmap towards a robust alternative to LabPlot and Origin

Written 2026-10-12 (version 0.2.3), updated 2026-10-14 (version 0.2.4). What π-plotter has, what LabPlot (free, GPL) and OriginPro (commercial) offer that
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
| 3 | ~~**Fit several data sets at once** (global fit, shared parameters) and a **fit report** table~~ — **done** (`analyses/global_fit.py`, `ctx.files`) | partial | ✓ | Weights from Y errors, parameters shared by some curves, fixed parameters: done. Constraints between parameters (`A2 = 2*A1`, `A[2] = 2*A[1]`), errors propagated: **done**. |
| 4 | ~~**Masking points**~~ — **done** (exclude rows / click points) (exclude outliers from fits and statistics by clicking them) | ✓ | ✓ | The mask is an operation of the edit log (`mask` in `piplotter/tables.py`): it follows inserted and deleted rows, Undo takes it back, projects rebuild it — **done** (checked by `tests/test_projects.py`). |
| 5 | ~~**Batch analysis**: the same analysis on many files, results in one table~~ — **done** (`App.batch_analysis`, *Run on all n files*) | — | ✓ (Batch Processing) | Choose the files (ticks under *Choose the files*) and run on a folder without loading it (*Run on a folder…*): **done**. |
| 6 | ~~**Layouts**: several panels with different data/kinds in one figure, insets, reference lines and bands, axis breaks~~ — **done** (`spec.compose`, `spec.inset`, `spec.refs`, `axes.xbreak` / `ybreak`) | ✓ | ✓ | Panels spanning several cells (↔ ↕ in *Layout of figures*, `layout.spans`) and a length of its own for each side of a break (`axes.xbreak_scale`): **done**. |
| 7 | ~~Signal tools: interpolation/resampling, FFT filters, convolution/deconvolution, curve arithmetic~~ — **done** (`interpolate`, `frequency_filter`, `convolution`, `curve_math`, `piplotter/signals.py`) | ✓ | ✓ | Peak-preserving decimation (`analyses/decimate.py`: LTTB, M4; long lines drawn the M4 way), 2D low-/high-pass and edge filters (`matrix_filter`): **done**. |
| 8 | ~~Statistics: more tests (paired, χ², Fisher, post-hoc), PCA, clustering, survival~~ — **done** (`compare_groups`: Friedman, Games–Howell, Dunn/Holm; `contingency`, `pca`, `clustering`, `survival`; SciPy only) | some | ✓ | Two-way / repeated-measures ANOVA (sphericity, Greenhouse–Geisser), mixed models and Cox regression (`anova_models`, `cox`; statsmodels, BSD): **done**. |
| 9 | ~~Matrices / images (2D data as a grid, image to data)~~ — **done** (`piplotter/matrices.py`, image reader, `matrix_transform`, `matrix_filter`, `matrix_profile`, `matrix_stats`) | ✓ | ✓ | Polygon regions (`matrix_stats`), spot / particle detection (`matrix_spots`: n σ, Otsu), colour images as channels (tables; *R, G, B as three files*): **done**. |
| 10 | ~~Scripting console (Python) on the open data~~ — **done** (`piplotter/console.py`, `web/console.js`, tab *Python*) | ✓ (Cantor) | ✓ (Python, LabTalk) | Completion of names (Tab), the console's code kept in projects (*Run it again*), the code run on every file into one table: **done**. |

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
5. ~~Matrices (9)~~ and ~~a console (10)~~ done: every gap of the table above is closed. ~~Autosave~~ and ~~events between the parts of the page~~ done; the "Next" items of every row done too (0.2.4).
