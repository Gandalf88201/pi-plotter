# π-plotter 0.2.3

**The user manual in Italian too, and editable IR assignments.**
*Italiano più sotto.*

## What's new
- The built-in manual is now available in **Italian** as well as English, with **the same pictures** (they show the
  English interface). The **Manual** button opens it in the language the program is set to; **EN / IT** at the top
  right of the manual switches it, and `/manual?lang=it` opens the Italian one directly.
- The Italian text (`manual/MANUAL.it.md`) uses the names of the Italian interface for buttons and menus, and gives the
  English name from the pictures in brackets where it helps.
- A test checks that the two manuals keep the same sections, pictures, tables and boxes, so they stay in step when the
  manual is updated. The page of the manual is translated too (contents, back link).
- In **IR peak assignment** the table of assignments can be **edited**. Write your own **label**, **most likely**
  (vibration), **group** (the groups of the table are suggested) or **note** in any row, **add a peak** the program
  did not find (a position in cm⁻¹, with or without an assignment), or remove one with ✕. **Apply** runs the analysis
  again: your rows are highlighted and marked *you* in the new **assigned by** column, they replace the table's
  candidates (which stay under *alternatives*), and the labels on the figure and the *groups compatible with the
  peaks* follow.
- Your assignments are kept when you run the analysis again with other options, and cleared by **Restore the table's
  assignments** or **Reset**.
- For plugin authors: `r.table(..., edit={…})` makes any table editable, and `hidden: True` keeps a parameter out of
  the form (see PLUGINS.md).
- **Several files in one graph**: clicking another file in *Loaded files* (to analyse its curve) now keeps the figure
  (same kind, style and curves; each file keeps its columns and its colour, since files are drawn in the order of the list) instead of rebuilding it from that file's defaults, which
  turned Lines into a histogram with no Y column. Choosing Lines, Scatter… with no Y column now takes the first
  numeric one, instead of refusing every redraw ("Choose at least one Y column", error 422) until one was ticked.
- **Gaussian distribution of a column** fits real Gaussians again: the fit started from an upside-down peak when the
  values filled most of the histogram (e.g. MD dihedrals); it now starts from the mean and spread of the values and keeps
  the baseline C ≥ 0. With a histogram of the column on screen (other files may be in it too) the Gaussian is drawn
  **over your histogram's bars**, on a copy of the figure (option to keep the figure of its own). Run it on each file
  of a combined figure: all the Gaussians gather on **one copy**.
- **Fitted values in the figure**: every *Curve fitting* (and the Gaussian recipe) writes a box with its values (e.g.
  mean, μ, σ, FWHM, R², errors to two significant digits) above its curve, in the curve's colour; drag it, double-click
  to rewrite it (several lines), or untick *values in the figure* under *Overlays*. The y axis makes room for it.
- **Data table as a spreadsheet**: type in cells, paste blocks from Excel / LibreOffice, add or delete rows and columns,
  rename columns, fill a column with a formula (`sqrt(A) * 2`, `col("time (s)") / 60`, `A - mean(A)`…), undo. **＋ New
  table** starts from an empty one. Every change is a new version of the table (the file is never changed); its list of
  operations is kept, so the table is rebuilt after a restart. Rows are shown by pages of 200.
- **Analyses suggested for the figure**: the Analysis panel proposes the analyses that suit the figure on screen
  (histogram → Gaussian / distributions; spectrum → baseline, peaks, peak fit, IR assignment; decaying signal →
  kinetics, exponential fit; time series → mean with true error, equilibration, ACF; groups → comparison; cloud of
  points → X–Y relation), each with its reason and starting values. Plugins can declare what they suit (`'suits'`).
- **Projects (.piplot)**: *Save project* writes the whole work in one file — the data files (embedded, so the project
  opens on any computer), table edits, tables written by hand, the figure, its copies with analyses and their values,
  result figures, the analyses' parameters. *Open project* (or dropping the file on the page) rebuilds everything from
  the sources: the analyses run again with the same data and settings. The format is versioned (a newer project asks
  to update π-plotter) and checked on opening (damaged archives, paths outside the archive, size limit).
- **Excluding points**: choose rows in the Data table (*Exclude n rows*) or click points on the figure (*✕ Exclude
  points on the figure…*, click again to bring one back). Excluded rows stay in the table (struck through), are drawn
  as grey crosses (*excluded* in the legend) and are left out of every analysis — e.g. a straight-line fit pulled by a
  wild point returns to the true slope. The exclusions are part of the table's list of edits (projects, Undo).
- **Autosave**: the work on screen is kept on disk a few seconds after each change (`~/.piplotter/autosave/`,
  with a copy of the data files); after the browser, the computer or π-plotter stopped, the next start offers to
  recover it. The copy of the session before is kept too.
- **Large projects**: *Save project* writes the .piplot to disk and the browser downloads it in pieces
  through a one-off link, so a project with many GB of data is never held in memory, neither in π-plotter nor in
  the page.
- **Outdated results are marked**: after a table edit, the numbers only in the analysis panel and the analyses
  made from a result run again too; until then the tabs show ⟳. A result that cannot run on the changed table (the
  column it was made from is gone) is marked **!** with *Run again*, and never quietly takes another column. Fixed:
  renaming a column while a copy of the figure is on screen took it out of the figure and broke the original one.
- **Constraints in the global fit**: *Constraints* ties parameters together — `A2 = 2*A1` on every curve,
  `A[2] = 2*A[1]` between curves. A constrained parameter is computed, not fitted; its error is propagated from the
  covariance of the fit (checked against the same model written as a custom formula).
- **Python console**: a *Python* tab runs code on the open data — `df` (the data of the figure), `files`, `np`, `pd`,
  `plt`, `run("analysis", …)` for the analyses of π-plotter, `new_table(frame, "name")` to open a result as a table
  (plotted, edited, saved in projects). Printed text, the value of the last line (tables as tables) and Matplotlib
  figures are shown; variables stay between runs. It runs in a Python process of its own: *Stop* ends a run that
  does not finish without touching the program, *Forget variables* starts afresh.
- **Matrices and images**: a table whose columns are named by their x (the first column the y of each row — the
  "XYZ matrix" of many instruments) is recognised as a matrix and drawn as a heat map, contour or 3D surface with
  numeric axes; **images** (PNG, JPEG, TIFF 8/16 bit, BMP, GIF, WebP) open as matrices of intensities, upright. New
  analyses in *Matrices & images*: **profile** along a segment clicked on the figure (or a row, a column), **statistics
  of a region** (mean, SD, extremes with position, sum, volume, centroid), **smooth & filter** (Gaussian, median,
  moving average, background plane, normalise, 2D FFT power spectrum) and **reshape & convert** (crop, bin, resample,
  transpose, flip, rotate, matrix ↔ X, Y, Z, scattered points gridded). New example: *2D map*.
- **Axis breaks**: in *Axes & ticks*, *＋ X break / Y break on the figure* (drag across the range) or typed
  (`12 – 95; 200 – 300`, dates too) leaves out ranges of an axis: each shrinks to a narrow gap marked // on the frame,
  both sides keep the same scale and their own ticks, curves are not joined across a gap of x. Analysis curves,
  reference lines, inset, value boxes, zoom and points clicked on the figure follow the broken axis; saved with the
  figure and in projects.
- **Correlation matrix in a layout**: a *Correlation* figure among the panels of *＋ Layout* stopped the whole
  layout with “'SubFigure' object has no attribute 'get_size_inches'”; it is now drawn (as are value boxes that
  stack in a panel). A test draws every plot kind as a panel.
- **Statistics**: *Compare groups* adds the **Friedman** test (the same subjects under three or more conditions) and
  picks the pairwise comparisons that suit the test — Tukey HSD after ANOVA, **Games–Howell** after Welch's ANOVA,
  **Dunn** (Holm-corrected) after Kruskal–Wallis, Wilcoxon pairs (Holm) after Friedman. New analyses: **Contingency
  table** (χ² of independence, Fisher's exact test and odds ratio for 2×2, Cramér's V, adjusted residuals; from two
  category columns or from counts), **Principal components (PCA)** (explained variance, loadings, scores plot coloured
  by group), **Cluster analysis** (k-means or Ward, the number of clusters chosen by the silhouette, every row with its
  cluster) and **Survival** (Kaplan–Meier curves with 95 % bands, median survival, log-rank test). The Analysis panel
  suggests PCA and clustering for tables of many numeric columns.
- **Signal tools**: *Interpolation & resampling* (linear, cubic spline, PCHIP, Akima, smoothing spline; onto an even
  grid, a step, another file's x or values written), *Frequency filter* (low-, high-, band-pass, band-stop;
  zero-phase Butterworth or ideal FFT cut), *Convolution & deconvolution* (Gaussian, Lorentzian, box, exponential
  kernel; Wiener, Richardson–Lucy) and *Arithmetic of two curves* (A − B, A + B, A × B, A ÷ B, A − k·B with k fitted,
  across files with different x). Each gives a new curve on a copy of the figure and as data.
- **Layouts of several figures**: *＋ Layout* combines the figure and its copies / result figures — each with its own
  data, kind, analyses, inset and reference lines — in one figure with letters (a), (b)…; the figures included, the
  columns and the letters are chosen in *Layout of figures*; it follows changes to its figures, exports as an image,
  PDF, SVG or EPS and is saved in projects.
- **Inset**: a region of the figure magnified in a box inside the axes — chosen by dragging a box on the figure or
  typed, in a corner, with lines to the region; same series, colours, analysis curves and reference lines.
- **Reference lines and bands**: vertical or horizontal lines at a value and shaded bands over a range, placed by
  clicking on the figure or typed, with a label (draggable, rewritable), colour and line style; also on date axes and
  in every panel; saved with the figure and in projects.
- **Clicking anchor points on a histogram works**: *Baseline*, *Peak finding*, *Peak fit*, *Integral* and
  *Smoothing* now work on the histogram on screen (its bins, counts or density) instead of the column's values in
  row order, so points picked on the figure, the peaks found and the curves drawn share the figure's axes (before,
  the clicked points — value, density — did not match the signal analysed, and the baseline came out wrong).
- **Values in the figure from any analysis**: under every result, **＋ Values in the figure…** lets you tick its
  numbers (fitted parameters with errors, R², a mean with its standard error, test statistics, rows of its tables) and
  write them in a box on the figure on screen; the box can be dragged, rewritten, recoloured, hidden or removed under
  *Overlays*, and is saved with the figure and in projects.
- **Batch analysis**: with several files loaded, **Run on all n files** runs the chosen analysis, with the settings of
  the form, on every file and gives one table, one row per file (e.g. the parameters of a fit with their errors, R²);
  the X and Y columns follow each file; files where it fails are listed apart with the reason. The table opens as a
  figure (first number against the file) and is saved in projects, rebuilt from the files.
- **Typing fast in the Data table** no longer loses a value: a cell being typed in while the previous value was
  still being saved is kept when the table is redrawn.
- **Global fit of several curves**: one model on every curve of the figure (its Y columns and the other files drawn
  with it) at once, with **shared parameters** — e.g. one lifetime τ for decays at several temperatures, fitted to all
  the data, with a smaller error — or by some curves only (`tau[1,2], tau[3-5]`), **fixed** ones (`C=0`), weights
  from the Y error columns (1/σ², with χ²_red), and the others each curve's own. With nothing shared it is a **batch fit** (the
  same numbers as fitting each curve alone). A **Fit report** table gives one row per curve (parameters ± errors, R²,
  RMSE); each curve gets its line on a copy of the figure and the shared values a box in it. Suggested by the
  Analysis panel whenever the figure has more than one curve. For plugin authors: `ctx.files` lists the files of the
  figure with their columns.
- **Analyses follow the data**: after a change to the table (a value, a paste, exclusions, Undo) the analyses on the
  copies of the figure, the result figures and the panel's numbers run again by themselves with the same settings,
  keeping their colours and the place of their value boxes.
- **Customised copies that fall behind**: a copy made with *Customise…* replaces the built-in analysis; when an
  update changes the built-in one, the list now says *your copy — the built-in one is newer*. New copies record the
  version they came from. (A copy of *Curve fitting* from 6 October had kept the fixes of this version out of reach.)
- For developers: the parts of the page tell each other what changed through events (`Bus.on` / `Bus.emit` in
  `core.js`: `dataset`, `dataset:shown`, `dataset:edited`, `view:shown`, `views:changed`, `figure:render`, `lang`,
  `modules:changed`, `session:new`, `ready`) instead of calling one another; a listener that fails does not stop the
  others.
- For developers: the page script `app.js` (2 800 lines) is split into ordered scripts (`core`, `install`, `controls`,
  `figure`, `data`, `export`, `modules`, `app`) with the same code; **browser smoke tests** (`tests/test_ui.py`,
  Playwright with the system Chrome, skipped without it) drive the main paths: example → suggestions → export, two
  files → Lines → switch → Gaussians on one copy, new table → typing → formula → undo → project save/open, errors
  reported instead of a frozen page.
- Manual (English and Italian): new paragraph in the IR assignment section; its pictures still show the table as it was.
  New sentence in *2.4 Several files at once*; new paragraphs on the editable table (2.3), suggestions (5.1) and the
  Gaussian over the histogram with the values in the figure (5.7). PLUGINS.md: `note=` and `'suits'`.

## Italiano
- Il manuale integrato ora c’è anche **in italiano**, con **le stesse immagini** (che mostrano l’interfaccia in inglese).
  Il pulsante **Manuale** lo apre nella lingua del programma; **EN / IT** in alto a destra nel manuale la cambia, e
  `/manual?lang=it` apre direttamente quello italiano.
- Il testo italiano (`manual/MANUAL.it.md`) usa i nomi dell’interfaccia italiana per pulsanti e menu e, dove serve,
  riporta tra parentesi il nome inglese visibile nelle immagini.
- Un test controlla che i due manuali abbiano le stesse sezioni, immagini, tabelle e riquadri, così restano allineati
  quando si aggiorna il manuale.
- Nell’**Assegnazione dei picchi IR** la tabella delle assegnazioni si può **modificare**. In ogni riga scrivi la tua
  **etichetta**, **più probabile** (vibrazione), **gruppo** (vengono proposti i gruppi della tabella) o **nota**,
  **aggiungi un picco** che il programma non ha trovato (una posizione in cm⁻¹, con o senza assegnazione) o toglilo
  con ✕. **Applica** riesegue l’analisi: le tue righe sono evidenziate e segnate *tu* nella nuova colonna **assegnata
  da**, sostituiscono i candidati della tabella (che restano tra le *alternative*), e le etichette in figura e i
  *gruppi compatibili con i picchi* si aggiornano.
- Le tue assegnazioni restano quando riesegui l’analisi con altre opzioni, e si cancellano con **Ripristina le
  assegnazioni della tabella** o con **Azzera**.
- Per chi scrive plugin: `r.table(..., edit={…})` rende editabile qualsiasi tabella, e `hidden: True` tiene un
  parametro fuori dal modulo (vedi PLUGINS.md).
- **Più file nello stesso grafico**: cliccare un altro file in *File caricati* (per analizzarne la curva) ora mantiene
  la figura (stesso tipo, stile e curve; ogni file tiene le sue colonne e il suo colore, perché i file sono disegnati nell’ordine dell’elenco) invece di ricostruirla dalle impostazioni di
  quel file, che trasformavano le Linee in un istogramma senza colonna Y. Scegliere Linee, Dispersione… senza colonna Y
  ora prende la prima colonna numerica, invece di rifiutare ogni ridisegno ("Choose at least one Y column", errore
  422) finché non se ne spuntava una.
- **Distribuzione gaussiana di una colonna** adatta di nuovo gaussiane vere: il fit partiva da un picco rovesciato quando
  i valori riempivano quasi tutto l’istogramma (es. diedri di MD); ora parte da media e dispersione dei valori e tiene
  la linea di base C ≥ 0. Con un istogramma della colonna sullo schermo (anche con altri file) la gaussiana è disegnata
  **sopra le barre del tuo istogramma**, su una copia del grafico (con l’opzione di tenere il grafico a parte). Eseguila
  su ogni file di un grafico combinato: tutte le gaussiane si raccolgono su **una sola copia**.
- **Valori del fit nel grafico**: ogni *Fit di curve* (e la ricetta gaussiana) scrive un riquadro con i suoi valori (es.
  media, μ, σ, FWHM, R², errori con due cifre significative) sopra la sua curva, del colore della curva; trascinalo,
  doppio clic per riscriverlo (più righe), o togli la spunta a *valori nel grafico* in *Sovrapposizioni*. L’asse y fa
  spazio al riquadro.
- **Tabella dati come foglio di calcolo**: scrivi nelle celle, incolla blocchi da Excel / LibreOffice, aggiungi o
  elimina righe e colonne, rinomina colonne, riempi una colonna con una formula (`sqrt(A) * 2`, `col("tempo (s)") / 60`,
  `A - mean(A)`…), annulla. **＋ Nuova tabella** parte da una tabella vuota. Ogni modifica è una nuova versione della
  tabella (il file non viene mai cambiato); l’elenco delle operazioni è conservato, così la tabella si ricostruisce dopo
  un riavvio. Le righe sono mostrate a pagine di 200.
- **Analisi suggerite per il grafico**: il riquadro Analisi propone le analisi adatte al grafico sullo schermo
  (istogramma → gaussiana / distribuzioni; spettro → linea di base, picchi, fit dei picchi, assegnazione IR; segnale
  che decade → cinetica, fit esponenziale; serie temporale → media con vero errore, equilibratura, ACF; gruppi →
  confronto; nuvola di punti → relazione X–Y), ognuna con il motivo e valori iniziali. I plugin possono dichiarare per
  quali grafici sono adatti (`'suits'`).
- **Progetti (.piplot)**: *Salva progetto* scrive tutto il lavoro in un file — i file di dati (incorporati, così il
  progetto si apre su qualsiasi computer), le modifiche alle tabelle, le tabelle scritte a mano, il grafico, le sue
  copie con le analisi e i loro valori, i grafici dei risultati, i parametri delle analisi. *Apri progetto* (o
  trascinando il file sulla pagina) ricostruisce tutto dalle origini: le analisi sono rieseguite con gli stessi dati e
  impostazioni. Il formato ha una versione (un progetto più recente chiede di aggiornare π-plotter) ed è controllato
  all’apertura (archivi danneggiati, percorsi fuori dall’archivio, limite di dimensione).
- **Escludere punti**: scegli righe nella Tabella dati (*Escludi n righe*) o clicca punti sul grafico (*✕ Escludi
  punti dal grafico…*, di nuovo per riportarne uno). Le righe escluse restano nella tabella (barrate), sono disegnate
  come croci grigie (*esclusi* nella legenda) e restano fuori da ogni analisi — es. un fit lineare tirato da un punto
  anomalo torna alla pendenza vera. Le esclusioni fanno parte dell’elenco delle modifiche della tabella (progetti,
  Annulla).
- **Salvataggio automatico**: il lavoro sullo schermo viene tenuto su disco pochi secondi dopo ogni modifica
  (`~/.piplotter/autosave/`, con una copia dei file di dati); se il browser, il computer o π-plotter si fermano,
  all’avvio successivo viene proposto di recuperarlo. Viene tenuta anche la copia della sessione precedente.
- **Progetti grandi**: *Salva progetto* scrive il .piplot su disco e il browser lo scarica a pezzi tramite un
  link usabile una volta sola, così un progetto con molti GB di dati non sta mai tutto in memoria, né in π-plotter né
  nella pagina.
- **Risultati superati segnalati**: dopo una modifica della tabella vengono rieseguiti anche i numeri presenti solo
  nel riquadro delle analisi e le analisi fatte su un risultato; nel frattempo le schede mostrano ⟳. Un risultato che
  non si può eseguire sulla tabella cambiata (la colonna da cui è fatto non c’è più) è segnato **!** con *Riesegui*, e
  non prende mai un’altra colonna di nascosto. Corretto: rinominare una colonna con una copia del grafico sullo schermo
  la toglieva dal grafico e rompeva quello originale.
- **Vincoli nel fit globale**: *Vincoli* lega i parametri tra loro — `A2 = 2*A1` su ogni curva, `A[2] = 2*A[1]`
  tra curve. Un parametro vincolato è calcolato, non adattato; il suo errore è propagato dalla covarianza del fit
  (verificato con lo stesso modello scritto come formula personalizzata).
- **Console Python**: una scheda *Python* esegue codice sui dati aperti — `df` (i dati del grafico), `files`, `np`,
  `pd`, `plt`, `run("analisi", …)` per le analisi di π-plotter, `new_table(frame, "nome")` per aprire un risultato
  come tabella (tracciata, modificata, salvata nei progetti). Mostra il testo stampato, il valore dell’ultima riga
  (le tabelle come tabelle) e le figure di Matplotlib; le variabili restano tra un’esecuzione e l’altra. Gira in un
  processo Python a parte: *Ferma* interrompe un’esecuzione che non finisce senza toccare il programma, *Dimentica le
  variabili* ricomincia da capo.
- **Matrici e immagini**: una tabella con le colonne intitolate alla loro x (la prima colonna la y di ogni riga — la
  “matrice XYZ” di molti strumenti) viene riconosciuta come matrice e disegnata come mappa di calore, contorni o
  superficie 3D con assi numerici; le **immagini** (PNG, JPEG, TIFF 8/16 bit, BMP, GIF, WebP) si aprono come matrici di
  intensità, dritte. Nuove analisi in *Matrici e immagini*: **profilo** lungo un segmento cliccato sul grafico (o una
  riga, una colonna), **statistiche di una regione** (media, SD, estremi con posizione, somma, volume, baricentro),
  **smussa e filtra** (gaussiano, mediano, media mobile, piano di fondo, normalizza, spettro FFT 2D) e **trasforma e
  converti** (ritaglia, raggruppa, ricampiona, trasposta, ribalta, ruota, matrice ↔ X, Y, Z, punti sparsi su
  griglia). Nuovo esempio: *Mappa 2D*.
- **Interruzioni d’asse**: in *Assi e tacche*, *＋ Interruzione X / Y sul grafico* (trascinando sul tratto) o
  scritte (`12 – 95; 200 – 300`, anche date) tolgono tratti di un asse: ognuno si riduce a uno stretto spazio segnato
  // sulla cornice, i due lati mantengono la stessa scala e le loro tacche, le curve non vengono unite attraverso
  un’interruzione di x. Curve delle analisi, linee di riferimento, riquadro ingrandito, riquadri di valori, zoom e
  punti cliccati sul grafico seguono l’asse interrotto; salvate con il grafico e nei progetti.
- **Matrice di correlazione in un layout**: una figura *Correlazione* tra i pannelli di *＋ Layout* bloccava
  tutto il layout con «'SubFigure' object has no attribute 'get_size_inches'»; ora viene disegnata (come i
  riquadri di valori impilati in un pannello). Un test disegna ogni tipo di grafico come pannello.
- **Statistica**: *Confronto tra gruppi* aggiunge il test di **Friedman** (gli stessi soggetti in tre o più
  condizioni) e sceglie i confronti a coppie adatti al test — Tukey HSD dopo l’ANOVA, **Games–Howell** dopo l’ANOVA di
  Welch, **Dunn** (corretto con Holm) dopo Kruskal–Wallis, coppie di Wilcoxon (Holm) dopo Friedman. Nuove analisi:
  **Tabella di contingenza** (χ² di indipendenza, test esatto di Fisher e odds ratio per 2×2, V di Cramér, residui
  corretti; da due colonne di categorie o da conteggi), **Componenti principali (PCA)** (varianza spiegata, loadings,
  grafico degli score colorato per gruppo), **Analisi dei cluster** (k-means o Ward, numero di cluster scelto dalla
  silhouette, ogni riga con il suo cluster) e **Sopravvivenza** (curve di Kaplan–Meier con bande al 95 %, sopravvivenza
  mediana, test log-rank). Il pannello Analisi suggerisce PCA e cluster per tabelle con molte colonne numeriche.
- **Strumenti sui segnali**: *Interpolazione e ricampionamento* (lineare, spline cubica, PCHIP, Akima, spline di
  smoothing; su griglia regolare, un passo, le x di un altro file o valori scritti), *Filtro in frequenza*
  (passa-basso, passa-alto, passa-banda, elimina-banda; Butterworth a fase nulla o taglio ideale nella FFT),
  *Convoluzione e deconvoluzione* (nucleo gaussiano, lorentziano, rettangolare, esponenziale; Wiener, Richardson–Lucy)
  e *Operazioni tra due curve* (A − B, A + B, A × B, A ÷ B, A − k·B con k adattato, anche tra file con x diverse).
  Ognuno dà una nuova curva su una copia del grafico e come dati.
- **Composizioni di più figure**: *＋ Composizione* riunisce la figura e le sue copie / grafici dei risultati — ognuno
  con i suoi dati, tipo, analisi, riquadro ingrandito e linee di riferimento — in un’unica figura con lettere (a),
  (b)…; figure incluse, colonne e lettere si scelgono in *Composizione di figure*; segue le modifiche alle sue figure,
  si esporta come immagine, PDF, SVG o EPS e si salva nei progetti.
- **Riquadro ingrandito**: una regione del grafico ingrandita in un riquadro dentro gli assi — scelta trascinando un
  rettangolo sul grafico o scritta, in un angolo, con linee verso la regione; stesse serie, colori, curve delle analisi
  e linee di riferimento.
- **Linee e bande di riferimento**: linee verticali od orizzontali a un valore e bande ombreggiate su un intervallo,
  posizionate con un clic sul grafico o scritte, con etichetta (trascinabile, riscrivibile), colore e tipo di linea;
  anche su assi di date e in ogni pannello; si salvano con il grafico e nei progetti.
- **I punti di ancoraggio cliccati su un istogramma funzionano**: *Linea di base*, *Ricerca dei picchi*, *Fit dei
  picchi*, *Integrale* e *Filtro* lavorano ora sull’istogramma sullo schermo (i suoi intervalli, conteggi o densità)
  invece che sui valori della colonna in ordine di riga, così i punti scelti sul grafico, i picchi trovati e le curve
  disegnate condividono gli assi del grafico (prima i punti cliccati — valore, densità — non corrispondevano al segnale
  analizzato e la linea di base risultava sbagliata).
- **Valori nel grafico da qualsiasi analisi**: sotto ogni risultato, **＋ Valori nel grafico…** permette di spuntarne
  i numeri (parametri adattati con errori, R², una media con il suo errore standard, statistiche dei test, righe delle
  sue tabelle) e scriverli in un riquadro sul grafico sullo schermo; il riquadro si trascina, si riscrive, si ricolora,
  si nasconde o si toglie in *Sovrapposizioni*, e si salva con il grafico e nei progetti.
- **Analisi in serie**: con più file caricati, **Esegui su tutti i n file** esegue l’analisi scelta, con le
  impostazioni del modulo, su ogni file e dà una tabella con una riga per file (es. i parametri di un fit con gli
  errori, R²); le colonne X e Y seguono ogni file; i file su cui non riesce sono elencati a parte con il motivo. La
  tabella si apre come grafico (il primo numero in funzione del file) e si salva nei progetti, ricostruita dai file.
- **Scrivere velocemente nella Tabella dati** non perde più un valore: la cella in cui si scrive mentre il valore
  precedente viene ancora salvato resta aperta quando la tabella viene ridisegnata.
- **Fit globale di più curve**: un modello su tutte le curve del grafico (le sue colonne Y e gli altri file disegnati
  con esso) insieme, con **parametri condivisi** — es. una sola vita media τ per decadimenti a più temperature,
  adattata su tutti i dati, con un errore più piccolo — o solo da alcune curve (`tau[1,2], tau[3-5]`), parametri
  **fissi** (`C=0`), pesi dalle colonne di errore Y (1/σ², con χ²_red), e gli altri propri di ogni curva. Senza parametri condivisi è
  un **fit in serie** (gli stessi numeri del fit di ogni curva da sola). Una tabella **Riepilogo dei fit** dà una riga
  per curva (parametri ± errori, R², RMSE); ogni curva ha la sua linea su una copia del grafico e i valori condivisi un
  riquadro nel grafico. Suggerito dal riquadro Analisi quando il grafico ha più di una curva. Per chi scrive plugin:
  `ctx.files` elenca i file del grafico con le loro colonne.
- **Le analisi seguono i dati**: dopo una modifica della tabella (un valore, un incolla, esclusioni, Annulla) le
  analisi sulle copie del grafico, i grafici dei risultati e i numeri del riquadro sono rieseguiti da soli con le
  stesse impostazioni, mantenendo colori e posizione dei riquadri dei valori.
- **Copie personalizzate rimaste indietro**: una copia fatta con *Personalizza…* sostituisce l’analisi inclusa; quando
  un aggiornamento cambia quella inclusa, l’elenco ora dice *tua copia — quella incorporata è più nuova*. Le nuove copie
  registrano la versione da cui provengono. (Una copia di *Fit di curve* del 6 ottobre teneva fuori portata le
  correzioni di questa versione.)
- Per gli sviluppatori: lo script della pagina `app.js` (2 800 righe) è diviso in script ordinati (`core`, `install`,
  `controls`, `figure`, `data`, `export`, `modules`, `app`) con lo stesso codice; **test di fumo nel browser**
  (`tests/test_ui.py`, Playwright con il Chrome di sistema, saltati se manca) percorrono i cammini principali.
- Manuale (inglese e italiano): nuovo paragrafo nella sezione sull’assegnazione IR; le sue immagini mostrano ancora la tabella com’era.
  Nuova frase in *2.4 Più file insieme*; nuovi paragrafi sulla tabella modificabile (2.3), sui suggerimenti (5.1) e
  sulla gaussiana sopra l’istogramma con i valori nel grafico (5.7). PLUGINS.md: `note=` e `'suits'`.

---

# π-plotter 0.2.2

**The corrected spectrum on its own, and transmittance divided by its baseline.**
*Italiano più sotto.*

## What's new
- *Baseline* no longer draws the corrected signal over the original one (it looked like the curve had split in
  two). **Plot the result** opens the **corrected spectrum alone**, with the corrected baseline as a dotted line.
- **Also show the spectrum before the correction, with its baseline** (off by default) draws, on a copy of the
  figure, the original spectrum, its baseline and anchor points, and the corrected spectrum, to compare them.
- **Correction**: transmittance (or reflectance) is now **divided** by its baseline, T / T₀ × 100, the standard
  correction: the corrected spectrum stays in %, flat at 100 % between the bands, which keep their depth. Other
  signals have the baseline subtracted (flat at 0). *Subtract* or *divide* can be forced.
- Manual: the baseline section explains both views and the correction, with new pictures.

## Italiano
- *Linea di base* non sovrappone più il segnale corretto a quello originale (sembrava che la curva si sdoppiasse):
  **Traccia il risultato** apre **solo lo spettro corretto**, con la linea di base corretta punteggiata.
- **Mostra anche lo spettro prima della correzione** (facoltativo) li disegna insieme su una copia della figura.
- **Correzione**: la trasmittanza ora è **divisa** per la linea di base (T / T₀ × 100) e resta in %, piatta a 100 %;
  gli altri segnali sono sottratti (piatti a 0). Si può forzare *sottrai* o *dividi*.
- Manuale aggiornato con le nuove immagini.

---

# π-plotter 0.2.1

**A baseline that stays flat: straight line under the signal, dips handled, clicked points kept where clicked.**
*Italiano più sotto.*

## What's new
- **New default baseline: a straight line under the signal** (*Baseline*, *Peak finding*, *Peak fit*). Points higher
  than the line by more than three times the noise — the peaks — do not pull it up (asymmetric truncated quadratic
  cost, Mazet et al. 2005), so where the signal has no peaks the corrected signal is flat at zero. **Shape** 0 gives
  a flat level, 1 a straight line, 2–6 a gently curved polynomial. arPLS, AsLS, SNIP and rubber band stay available
  for curved backgrounds.
- **Peaks pointing down** (transmittance, dips): every automatic method now puts the baseline **above** them, along
  the top of the spectrum. Before, it was drawn under the signal and sank into the bands (the example in the manual
  showed it). *The peaks point* is recognised from the signal, or chosen (up / down). *Peak finding* with *Find
  minima* uses it too.
- **Clicked anchor points keep their y.** Before, a click kept only x and the height was read from the signal, so a
  point clicked next to a spike (or before the first point) jumped to the spike. Now every click writes `x y` and
  the point stays where it was clicked; a point written with x alone still takes the height of the signal.
- The results say which way the peaks point and warn when more than 5 % of the points lie on the wrong side of the
  baseline. SNIP's default window is wider (1/6 of the range), so it no longer cuts broad peaks.
- Manual updated (baseline section, pictures).

## Italiano
- **Nuova linea di base predefinita: una retta sotto il segnale.** I picchi non la sollevano (Mazet et al. 2005): dove
  non ci sono picchi il segnale corretto è piatto a zero. **Forma** 0 = livello piatto, 1 = retta, 2–6 = polinomio.
- **Picchi in giù** (trasmittanza): la linea di base va sopra gli avvallamenti, lungo il bordo superiore dello spettro;
  il verso dei picchi si riconosce dal segnale o si sceglie.
- **I punti cliccati tengono la loro y**: il punto resta dove l’hai cliccato (prima veniva spostato sull’altezza del
  segnale, per esempio su un picco vicino).

---

# π-plotter 0.2.0

**A new name, a signature, and a built-in user manual with pictures.**
*Italiano più sotto.*

## What's new

### The program is now π-plotter
- PyPlotter's name was already in use, so the program is **π-plotter** from now on. The window, the
  terminal banner, the exports and the documents say so; the launchers are `start_piplotter.command`,
  `start_piplotter.bat` and `start_piplotter.py`, the Python package is `piplotter`, and the environment
  variables start with `PIPLOTTER_`.
- Nothing is lost: the first start copies your plugins, your module list and the session token from
  `~/.pyplotter` to `~/.piplotter` (the old folder is left alone); plugins that still say
  `from pyplotter import baselines` keep working; saved style templates and module lists of the old name
  are still read.
- The GitHub repository is now `Gandalf88201/pi-plotter` (GitHub names cannot contain π); the old address
  redirects to it. The folder of the project on disk keeps its name.

### Signature
- **Dr. T. Francese** appears under the name in the top bar (as in MONET), in the *About* window, on the
  welcome page, in the terminal banner and in the manual.

### User manual
- A **Manual** button in the top bar opens the manual in a new tab. It follows the order of the work: open
  data, choose variables and plot, style the figure (size, colours, text, axes, zoom, 3D), analyse
  (fitting, kinetics, baseline and peaks, peak fit, IR assignment, equilibration and correlated errors,
  group tests, relations), export, plugins and modules, troubleshooting. 43 pictures are taken from the
  program itself.
- The text is `manual/MANUAL.md`; the pictures are `manual/img/`. `tools/make_manual_images.py` redraws all
  of them (or just some) after a change of the interface, so the manual can be kept up to date.
- The manual prints cleanly (print / save as PDF from the browser) and follows light and dark mode.

---

## Italiano

### Il programma ora si chiama π-plotter
- Il nome PyPlotter era già in uso: da ora il programma è **π-plotter**. Cambiano i file di avvio
  (`start_piplotter.*`), il pacchetto Python (`piplotter`) e le variabili d'ambiente (`PIPLOTTER_`).
- Non si perde nulla: al primo avvio plugin, elenco dei moduli e token passano da `~/.pyplotter` a
  `~/.piplotter` (la vecchia cartella resta com'è); i plugin che importano `pyplotter` continuano a
  funzionare, e i modelli di stile e gli elenchi di moduli salvati col vecchio nome si leggono ancora.

### Firma
- **Dr. T. Francese** compare sotto il nome nella barra in alto (come in MONET), nella finestra
  *Informazioni*, nella pagina di benvenuto, nel terminale e nel manuale.

### Manuale d'uso
- Il pulsante **Manuale** apre il manuale (in inglese) in una nuova scheda: dall'apertura dei dati
  all'esportazione, passando per stile, zoom, 3D, fit, cinetica, linea di base e picchi, assegnazione IR,
  errori di dati correlati, test tra gruppi, plugin e moduli. Il testo è `manual/MANUAL.md` e le immagini
  si rigenerano con `tools/make_manual_images.py`.

---

# π-plotter 0.1.4

**Modules from PyPI that are checked for real, with an icon for their functions — and IR peak assignment.**
*Italiano più sotto.*

## What's new

### IR peak assignment
- A new analysis, **IR peak assignment** (*Analysis › Signal*), for mid-IR spectra in absorbance or
  transmittance (recognised from the column name and the shape), against cm⁻¹, µm or nm.
- It finds the peaks above the baseline and lists, for each, the **candidate groups** from a table of
  **111 characteristic bands**:
  - organic groups (O–H, N–H, C–H, C=O of esters, acids, ketones, aldehydes, amides…, C–O, aromatic and
    alkene bands, nitro, nitrile and more);
  - inorganic anions and minerals for materials and conservation science: carbonates, sulfates, nitrates,
    phosphates, silicates and quartz, clays, metal oxalates, carboxylates and metal soaps, Prussian blue;
  - water, and atmospheric CO₂ flagged as an artefact.
- Candidates are ranked by how narrow the range is, how well intensity and width match, and by the
  **companion bands** a group needs: an ester C–O only with an ester C=O, an aldehyde only with its
  C–H doublet, an aryl ether only with an aromatic ring, carbonate bends only with a strong carbonate
  band, organic groups only with C–H bands.
- Each peak gets a **confidence** (high, medium, low). The figure shows “1738 C=O” above the peaks,
  or “860 ?” when uncertain. A table lists the **groups that explain the most peaks**, and notes say
  what missing bands rule out (no strong band at 1850–1650 cm⁻¹: no C=O).
- Groups with S, P, Si or halogens are included on request: their broad ranges fit almost any peak.
- They are candidates, not proofs. The table (`BANDS` in `ir_assign.py`, editable with *Customise*)
  holds standard values compiled from the references listed in REFERENCES.md.
- *Examples › IR spectrum*: a synthetic spectrum to try it on.

### Your modules from PyPI
- **Deeper import check.** Each module you added is imported with its submodules. A package whose
  `import` works but whose working parts fail is shown as **cannot be used** (red), e.g. uvvispy 0.1.1
  with setuptools 84 (`No module named 'pkg_resources'`). When only a few parts fail, usually optional
  ones, it **works in part** (amber). The failing parts are listed, grouped by cause.
- **An install that cannot be used is undone.** Right after installing, the module is checked. If it
  cannot be used, the packages it added are removed and the ones it upgraded go back to their
  versions; the environment stays as it was and the reason is shown.
- **Integrations.** A module does something in π-plotter through the plugins that list it in
  `requires`.
  - A module that no plugin uses says so, with **Create integration**: a first, working analysis that
    uses it, opened in the editor.
  - A module that imports and is used gets **its own icon at the end of the bar of plot types**. The
    icon lists its functions; choosing one opens it in *Analysis*, ready for the open data.
  - Analyses that import a part of a module that fails are disabled, with the reason.

## Changes in behaviour
- Modules you added that showed “import OK” may now show *cannot be used* or *works in part*: they are
  checked again, more strictly, at the next start.
- The red badge on *Modules* and the line at the top of the Modules window count your modules too.
- Installing a module that cannot be used now leaves nothing behind.

## Updating
Download the source of this release and replace the old folder. Your settings and plugins in
`~/.piplotter/` are kept. Restart π-plotter after updating.

---

## Italiano

**Moduli da PyPI controllati davvero, con un’icona per le loro funzioni — e l’assegnazione dei picchi IR.**

### Novità
- **Assegnazione dei picchi IR** (*Analisi › Segnale*), per spettri IR medi in assorbanza o trasmittanza,
  in cm⁻¹, µm o nm:
  - trova i picchi ed elenca per ognuno i **gruppi candidati** da una tabella di **111 bande
    caratteristiche**: gruppi organici, anioni inorganici e minerali (carbonati, solfati, nitrati,
    fosfati, silicati e quarzo, argille, ossalati, saponi metallici, blu di Prussia), acqua e CO₂
    atmosferica come artefatto;
  - i candidati sono ordinati per intervallo, intensità, larghezza e **bande compagne** (il C–O di un
    estere solo con il suo C=O, un’aldeide solo con il doppietto C–H, i gruppi organici solo con bande C–H);
  - ogni picco ha un’**affidabilità**; il grafico mostra «1738 C=O» sopra i picchi, o «860 ?» se
    incerto; una tabella elenca i **gruppi che spiegano più picchi**;
  - i gruppi con S, P, Si o alogeni si includono su richiesta;
  - sono candidati, non prove: la tabella (`BANDS` in `ir_assign.py`, modificabile con *Personalizza*)
    contiene valori standard dai riferimenti di REFERENCES.md;
  - *Esempi › Spettro IR* per provarla.
- **I tuoi moduli da PyPI:**
  - **controllo più severo**: ogni modulo viene importato con i suoi sottomoduli; se le parti che fanno
    il lavoro non si importano è **non utilizzabile** (rosso), se ne falliscono poche **funziona in
    parte** (arancione); le parti che falliscono sono elencate per causa;
  - **un’installazione non utilizzabile viene annullata**: i pacchetti aggiunti vengono tolti e quelli
    aggiornati tornano alla versione precedente;
  - **integrazioni**: un modulo che nessun plugin usa lo dice, con **Crea integrazione**; un modulo
    usato ha **la sua icona in fondo alla barra dei tipi di grafico**, con l’elenco delle sue funzioni;
    le analisi che usano una parte rotta sono disattivate.

### Cambiamenti di comportamento
- Moduli che risultavano «import OK» possono ora risultare *non utilizzabili* o *funziona in parte*.
- Il contatore rosso su *Moduli* conta anche i tuoi moduli.

### Aggiornare
Sostituisci la cartella con quella di questa versione e riavvia π-plotter. Impostazioni e plugin in
`~/.piplotter/` restano.

Licenza MIT · © 2026 Tommaso Francese

---

# π-plotter 0.1.3

**Zoom, move and rewrite on the figure itself — and peak labels that never overlap.**
*Italiano più sotto.*

## What's new

### Zoom
- **Drag a box** on the axes: its corners become the axis limits (the X/Y min/max fields of the Axes
  panel) and the figure is drawn again with ticks for the new range. Works on every plot with axes: lines,
  scatter, bars, box and violin plots, histograms, heat maps, contours, hexbin…
- A **thin box** zooms one axis only. Zoomed on x alone, **y follows the data in that range**: one small
  band of a spectrum fills the plot.
- The **mouse wheel** zooms around the pointer (Shift + wheel: x only). On **polar** figures it zooms the
  radius, on **3D** figures the three ranges; what falls outside a 3D box is clipped.
- *↶ Previous zoom*, *⤢ Whole figure* or a double-click on the plot go back. Pie charts and pair plots
  have no zoom.

### Move and rewrite every text
- **Drag** titles, axis labels (z too), the colour-bar label, the legend, pie slice names and shares,
  pair-plot labels and value labels, on every kind of plot.
- **Double-click a text to rewrite it.** Formulas go between `$…$`, e.g. `cm$^{-1}$`, `$\mu$g`,
  `H$_2$O`. Titles and axis labels are written in their fields of the Text panel; the legend's title in
  its own; the other texts are kept with the figure.
- *Original text* and *Original position* undo one text; *↺ Texts back in place* moves them all back.
- What you move and rewrite is kept in every export (PNG, TIFF, PDF, SVG, EPS, Python script) and in
  templates.

### Peak labels
- Labels that would cover another label, a curve or the legend move up or aside, joined to their peak by
  a thin **leader line**.
- The y axis grows to make room above the tallest peak, unless you fixed that limit.
- Labels are placed in points, so the preview and the export at any DPI match.

### 3D figures
- **Drag a 3D figure to rotate it**: a light copy of the data turns smoothly in the page, with
  Matplotlib's own projection. On release the angles are kept and the figure is drawn again.
  Double-click restores the default view.

### Fixes
- Setting the Y limits of a heat map no longer turns it upside down.

## Changes in behaviour
- With **only the X limits** set (by zoom or in the Axes panel), the Y axis now spans the data in that
  range instead of all the data.
- Peak labels may sit beside their peak, with a leader line, and the y axis may be taller to make room for
  them.

## Updating
Download the source of this release and replace the old folder. Your settings and plugins in
`~/.piplotter/` are kept. Restart π-plotter after updating.

---

## Italiano

**Zoom, spostamento e modifica dei testi direttamente sulla figura — e etichette dei picchi che non si
sovrappongono.**

### Novità
- **Zoom:**
  - trascina un riquadro sugli assi: diventa i limiti degli assi e la figura viene ridisegnata con le
    tacche del nuovo intervallo, su ogni grafico con assi;
  - un riquadro sottile ingrandisce un solo asse; ingrandendo solo x, **y segue i dati visibili**;
  - la **rotella** ingrandisce attorno al puntatore (Maiusc: solo x), nei grafici polari il raggio, nei
    3D i tre assi;
  - *↶ Zoom precedente*, *⤢ Figura intera* o doppio clic sul grafico per tornare indietro.
- **Testi:** titoli, etichette degli assi, barra dei colori, legenda, fette della torta, etichette del
  grafico a coppie e valori dei picchi si **spostano trascinandoli** e si **riscrivono con un doppio
  clic** (formule tra `$…$`). Restano in ogni esportazione; *Testo originale*, *Posizione originale* e
  *↺ Testi al loro posto* li ripristinano.
- **Etichette dei picchi** senza sovrapposizioni: si spostano in alto o di lato con una sottile linea di
  richiamo, e l’asse y si allunga per farle stare.
- **Grafici 3D:** trascina la figura per ruotarla; doppio clic per la vista predefinita.
- **Correzione:** i limiti Y non capovolgono più una mappa di calore.

### Cambiamenti di comportamento
- Con **solo i limiti X** impostati, l’asse Y copre i dati di quell’intervallo e non più tutti i dati.
- Le etichette dei picchi possono stare accanto al picco, con una linea di richiamo.

### Aggiornare
Sostituisci la cartella con quella di questa versione e riavvia π-plotter. Impostazioni e plugin in
`~/.piplotter/` restano.

Licenza MIT · © 2026 Tommaso Francese

---

# π-plotter 0.1.2

**3D figures, JCAMP-DX spectra and modules of your choice from PyPI.**
*Italiano più sotto.*

## What's new

### 3D figures
- **3D surface** z(x, y) from X, Y, Z columns: a grid, or scattered points (triangulated). Optionally a
  wire frame only. Colour map, colour bar and colour limits as for contour plots.
- **3D scatter** of X, Y, Z, one colour per series or group, or the points joined by a 3D line.
- **Waterfall** of spectra: each Y column is a curve at its own depth, given by the column name when it
  is a number (a time, a temperature) or by its position.
- View elevation and azimuth, Z limits and a Z label. Interactive HTML export with rotatable 3D (Plotly).

### Files
- **JCAMP-DX** spectra (`.jdx`, `.dx`), plain or compressed (AFFN, PAC, SQZ, DIF, DUP), as exported by
  instruments and the NIST WebBook. A file whose point count does not match its header is refused.

### Your modules from PyPI
- *Modules › Your modules*: type the name of any package on PyPI and press *Check*. pip lists what it
  would install, nothing is changed yet, and every package is shown with its **licence**.
  - Open-source (OSI-approved) packages install normally.
  - A licence that is not OSI-approved, proprietary or not recognised is marked. *Install* stays
    disabled until you tick *“I have read the licence terms…”*.
- Only plain package names are accepted, and the version shown is the version installed.
- Each module you added is listed with:
  - its licence and the packages installed with it;
  - a reference to cite, added to the results of analyses that use it;
  - an *Uninstall* button.
- They are recorded in `~/.piplotter/user-modules.json`. In a new environment they appear as *not
  installed*, with *Install again*.
- These are third-party code that π-plotter does not check: install only what you trust.

---

## Italiano

- **Grafici 3D:**
  - superficie z(x, y), da una griglia o da punti sparsi, anche solo come reticolo;
  - dispersione o linea 3D;
  - **cascata** di spettri: una curva per colonna, alla profondità data dal nome della colonna;
  - angoli di vista, limiti e etichetta Z, esportazione HTML interattiva.
- **JCAMP-DX** (`.jdx`, `.dx`), anche compressi.
- **I tuoi moduli da PyPI** (*Moduli › I tuoi moduli*):
  - scrivi il nome di un pacchetto e premi *Controlla*: vedi il pacchetto e ogni dipendenza con la sua
    licenza;
  - una licenza non approvata OSI, proprietaria o non riconosciuta richiede la tua conferma esplicita;
  - per ogni modulo: riferimento da citare e *Disinstalla*;
  - dopo la perdita dell’ambiente, *Installa di nuovo*.
  - Sono codice di terze parti non controllato da π-plotter.

Licenza MIT · © 2026 Tommaso Francese

---

# π-plotter 0.1.1

**Baseline first, then the analysis** — and tables with tens of thousands of columns.
*Italiano più sotto.*

## What's new

### Baseline of spectra and signals
- A new **Baseline** analysis (*Analysis › Signal*). **Click anchor points on the figure** where the signal
  lies on its baseline (a readout shows x and y under the cursor), or type them. They are joined by
  straight lines or by a smooth monotone curve (PCHIP). Automatic methods are also available: arPLS,
  asymmetric least squares, SNIP and rubber band.
- The baseline, the anchor points and the corrected signal are drawn on a copy of the figure. A
  warning appears when more than 5 % of the points fall under the baseline.
- **Peak finding**, **Peak fit** and **Integral** offer the baseline you defined, already selected:
  - heights, FWHM and areas are measured above it;
  - each peak's area runs between the minima that separate it from its neighbours (perpendicular drop);
  - an x range can be chosen.
- **Peak fit** keeps every peak inside its own region (height ≥ 0, centre between its neighbours). The
  joint fit of many overlapping peaks now converges. When it doesn't, the message says what to change.
- **Curve fitting** has a new **Limits** field (e.g. `a=0..inf, tau=1..100`).

### Wide tables
- Every list of columns has **All / None** and a filter. The filter also takes ranges: of numeric names
  (`19600-19840`) or of positions (`#1-500`). **Shift+click** ticks a whole block.
- Opening a 20 000-column table takes well under a second of analysis instead of about 45 s.
- A **heat map** draws all the columns, anti-aliased, so no column is skipped. A **correlation matrix**
  takes up to 2 000 columns. Beyond these limits π-plotter explains why and suggests a block or a heat map.

### Figures
- Analysis layers (e.g. **peak markers**) have their own **marker shape and size** in *Overlays*.
- The automatic legend is left out when it does not fit in the axes. One curve per fitted peak no
  longer adds a legend entry.
- Matrix tick labels fit the axes. Messages about figures that cannot be drawn follow the interface
  language.

### Fixes
- SQLite files are closed after reading. Before, they stayed open, which locks the file on Windows.

## Changes in behaviour
- **Peak finding:** areas are now measured above the chosen baseline (automatic arPLS by default). They
  used to be measured above a straight line under each peak, which could reach a distant minimum. Areas
  of overlapping peaks therefore differ from 0.1.0; they are now consistent.
- **Peak fit:** the default baseline is arPLS, subtracted before the fit. The straight line or constant
  fitted together with the peaks is still available. Up to 20 peaks are fitted by default.
- **Integral:** “Subtract the straight baseline between the ends” is now the *Baseline* choice
  *straight line between the ends of the range*.

## Updating
Download the source of this release and replace the old folder. Your settings and plugins in
`~/.piplotter/` are kept. A **customised copy** of a built-in analysis stays as you wrote it, so it does
not get these changes. To use the new version, disable your copy in the plugin editor.

---

## Italiano

**Prima la linea di base, poi l’analisi** — e tabelle con decine di migliaia di colonne.

### Novità
- **Linea di base** (*Analisi › Segnale*):
  - **clicca i punti di ancoraggio sulla figura** (o scrivili), uniti da segmenti o da una curva liscia;
  - oppure scegli un metodo automatico: arPLS, minimi quadrati asimmetrici, SNIP o elastico;
  - linea, punti e segnale corretto compaiono su una copia della figura, con un avviso se la linea è
    troppo alta.
- **Ricerca dei picchi**, **Fit dei picchi** e **Integrale** propongono la linea già definita:
  - altezze, FWHM e aree sono misurate sopra di essa;
  - l’area di ogni picco va dai minimi che lo separano dai vicini;
  - si può scegliere un intervallo di x.
- Il **fit dei picchi** tiene ogni picco nella sua regione e converge anche con molti picchi
  sovrapposti. *Fit di curve* ha il nuovo campo **Limiti**.
- **Tabelle larghe:**
  - *Tutte* / *Nessuna*, filtro con intervalli (`19600-19840`, `#1-500`) e Maiusc+clic per i blocchi;
  - apertura di 20 000 colonne in meno di un secondo di analisi;
  - mappa di calore di tutte le colonne, correlazione fino a 2000 colonne.
- **Marcatori dedicati** (forma e dimensione) per i livelli delle analisi, come i picchi.
- La legenda automatica si omette se non sta negli assi.
- I file SQLite vengono chiusi dopo la lettura.

### Cambiamenti di comportamento
- **Ricerca dei picchi:** aree sopra la linea di base scelta (arPLS automatica di default). Le aree di
  picchi sovrapposti cambiano rispetto alla 0.1.0.
- **Fit dei picchi:** linea di base arPLS sottratta di default; fino a 20 picchi.
- **Integrale:** la retta tra gli estremi è ora una scelta di *Linea di base*.

### Aggiornare
Sostituisci la cartella con quella di questa versione. Impostazioni e plugin in `~/.piplotter/`
restano. Una **copia personalizzata** di un’analisi inclusa non riceve queste modifiche.

Licenza MIT · © 2026 Tommaso Francese
