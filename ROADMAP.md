# π-plotter — roadmap towards a robust alternative to LabPlot and Origin

Written 2026-10-12 (version 0.2.3), updated 2026-10-19 (after version 0.2.7). What π-plotter has, what LabPlot (free, GPL) and OriginPro (commercial) offer that
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
| Front end | **Split done** (2026-10-12): `core`, `install`, `controls`, `figure`, `data`, `export`, `modules`, `app` + `table`, `files`, `analysis`, `project` — same global scope, loaded in order | **Events done** (2026-10-14): `Bus` in `core.js` — the parts announce what changed (`dataset`, `dataset:edited`, `figure:render`, `views:changed`, `lang`, `session:new`…) and listen, instead of calling each other. **State done** (2026-10-14): the keys others react to (`lang`, `spec`, `dataset`, `view`, `views`, `tab`…) change only through `setState()`, which emits `state` {keys}; a direct write is noted and the UI tests fail on it. |
| Front-end tests | **Done**: `tests/test_ui.py` (Playwright + system Chrome) — 26 paths, fails on any JS error (2026-10-19: clearing the cache, the profile on a 3D surface; 2026-10-15: a figure description and a project that do not match their schema; where a result comes from; an older description completed) | Add a path per new feature. |
| Service | **Done** (2026-10-14): `server.py` keeps the App, the HTTP handler and the start; the work is in `piplotter/service/` (`files`, `tables`, `projects`, `console`, `analyses`, `render`, `cache`), and `service/routes.py` is the one table of routes | **Schemas done** (2026-10-14): `schema.py` and `piplotter/schemas/figure-1.schema.json`, `project-1.schema.json` (JSON Schema 2020-12) — the figure description and the project carry their version; older ones are upgraded step by step (`SPEC_UPGRADES`, `PROJECT_UPGRADES`), every render and every project opened is checked, a test keeps the published files equal to what the code makes. |
| Data model | data sets live in memory, rebuilt from sources | **Done** (2026-10-15): `piplotter/sources.py` is the table of the six kinds of source (file, sample, blank, edit, analysis, batch) — the fields of each, how it is made again, what it is made from; `reopen()` reads it, `lineage()` gives the steps for `provenance.json`, the JSON Schema has `$defs/source_<kind>` (still version 1: saved projects match), and a data set made from the same source is not made again (`sources.key`). Projects saved by 0.2.3 and 0.2.4 open with the same data (`tests/golden/projects/`). |
| Analyses | plugins with params, Result, overlays; advisor rules | **Done** (2026-10-14): every built-in analysis declares `suits` (conditions on facts of the figure, score, reason EN/IT), as plugins can; `advisor.RULES` keeps only what needs several facts together or brings starting parameters; `tests/test_advisor_golden.py` holds the suggestions of 33 reference figures and of every combination of facts, unchanged by the move. |

## Proposed order

1. ~~Projects (gap 1)~~, ~~front-end split + smoke tests~~ done.
2. ~~Analyses that follow the data (2) and masking (4)~~ done.
3. ~~Global fit + fit report (3)~~ and ~~batch (5)~~ done; global-fit refinements and ~~layouts (6)~~ done; ~~signal tools (7)~~ done.
4. ~~Statistics (8)~~ and ~~axis breaks (rest of 6)~~ done.
5. ~~Matrices (9)~~ and ~~a console (10)~~ done: every gap of the table above is closed. ~~Autosave~~ and ~~events between the parts of the page~~ done; the "Next" items of every row done too (0.2.4).
6. Asked by the user on 2026-10-19: ~~clearing the cache (start from zero)~~ done (`service/cache.py`); ~~the profile line kept on the 3D figure~~ done (layers with `z`, `plotting._draw_overlays3d`, `front` lines in `web/view3d.js`); a point picker (arrow or cross) on every figure, with labels that do not cover what it reads.
