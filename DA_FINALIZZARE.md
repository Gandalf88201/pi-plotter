# π-plotter — punti rimanenti da finalizzare

Stato al 2026-10-14, versione 0.2.5 (tag `v0.2.5`).
Riferimento: tabella *Code structure (robustness)* di `ROADMAP.md`.

| Riga ROADMAP | Stato |
|---|---|
| Front end (divisione, eventi, stato) | fatto |
| Front-end tests | fatto, da estendere a ogni nuova funzione |
| Service (rotte, moduli per area, schemi con versione) | fatto |
| Data model | **fatto** (2026-10-15, vedi §1) |
| Analyses | **fatto** (2026-10-14, vedi §2) |

---

## 1. Data model — formalizzare "sorgente + operazioni" — **fatto**

**Fatto il 2026-10-15** (commit locale, non ancora pubblicato):

- `piplotter/sources.py`: `KINDS`, la tabella dei sei tipi (chiave che li riconosce, campi richiesti e loro schema,
  come si ricostruiscono, sorgenti genitrici, passo della provenienza). `reopen()` in `service/files.py` è ora
  `check()` + `make()` del registro; un tipo sconosciuto o un campo mancante danno un errore 400 `source` che dice
  cosa manca (es. `The data source (analysis) is not complete: source: “parent” is missing`). Profondità massima 10.
- Schema: `$defs/source` (anyOf) e `$defs/source_<tipo>` in `figure-1` e `project-1`. I progetti salvati
  corrispondono (autosalvataggi, i progetti dei test, i due progetti delle versioni precedenti), quindi la versione
  resta 1.
- `lineage(source)`: i passi file → modifiche → analisi (una serie elenca quelli di ogni file); usata in
  `provenance.json` (ora `piplotter-provenance/2`, con `steps`; `origin` e `analyses` restano).
- Cache: `sources.key()` (JSON canonico, SHA-256) → l'insieme di dati già fatto da quella sorgente, se ancora in
  memoria, ridato con un id nuovo (ogni copia ha il suo id, i dati sono condivisi in sola lettura). I risultati delle
  analisi si rifanno dopo un ricaricamento dei plugin (`PluginManager.generation`).
- Test: `tests/test_sources.py` (ogni tipo: sorgente → dati → sorgente → stessi dati in un servizio nuovo; errori;
  profondità; provenienza; cache) e `tests/golden/projects/saved-by-0_2_3/0_2_4.piplot`, salvati dal codice di quelle
  versioni: si aprono con dati identici byte per byte in tutti i 9 insiemi di dati.
- Non fatto: mostrare "da dove viene" nell'interfaccia (la funzione c'è; manca il riquadro nella pagina).

Testo originale:


**Oggi.** Ogni data set ha una `source`, ma i tipi di sorgente esistono solo come catena di `if` in
`reopen()` ([piplotter/service/files.py](piplotter/service/files.py)). I tipi sono sei:

- `file_id` + `table` + `options`: un file caricato;
- `sample`: un esempio;
- `blank`: una tabella vuota;
- `edit` + `ops`: modifiche a un'altra sorgente;
- `analysis` + `parent` (+ `overlay`): il risultato di un'analisi;
- `batch`: la stessa analisi su più file.

Nello schema del progetto la sorgente è ancora un `object` generico.

**Da fare**

1. Un modulo `piplotter/sources.py` con un registro dei tipi di sorgente. Per ogni tipo: i campi richiesti, come si
   ricostruisce, quali sorgenti genitrici ha. `reopen()` diventa una consultazione del registro, come la tabella delle
   rotte.
2. Lo schema JSON della sorgente, con un `$defs/source` per ogni tipo, in `figure-1` e `project-1`. Se i documenti
   salvati finora corrispondono, la versione resta 1; altrimenti si passa alla versione 2 con un passo in
   `PROJECT_UPGRADES`.
3. La provenienza: `lineage(source)` restituisce la catena file → modifiche → analisi. È utile per il
   `provenance.json` dell'esportazione Python e per mostrare "da dove viene" un risultato.
4. Una cache per sorgente: una chiave dal JSON canonico della sorgente evita di ricalcolare la stessa analisi più
   volte quando un progetto con molte copie si riapre.

**Verifica**

- Un test per ogni tipo: sorgente → data set → sorgente → stesso data set (stesse righe, colonne e valori).
- Un tipo sconosciuto o un campo mancante danno un messaggio chiaro.
- Profondità massima della catena rispettata, come oggi (`depth > 10`).
- Progetti salvati dalla 0.2.3 e dalla 0.2.4 si aprono uguali.
- Il test dell'interfaccia `test_last_work_recovered` e i test sui progetti passano.

---

## 2. Analyses — regole del consigliere come dati e `suits` per le analisi incluse — **fatto**

**Fatto il 2026-10-14** (commit locali, non ancora pubblicati):

- `tests/test_advisor_golden.py` + `tests/golden/advisor.json`: i consigli completi di 33 grafici di riferimento e
  l'impronta di 6720 combinazioni di fatti, registrati **prima** del cambiamento; passano senza modifiche dopo.
  Confronto in più con il codice 0.2.5 su 60 000 combinazioni: identico in tutti gli stati che `describe()` può
  produrre (differisce solo dove `decays` è vero con x di categoria o libera, cosa che `describe()` non fa mai).
- `advisor.py`: fatti derivati (`figure`, `signal`, `line`, `many`, `y_columns`), condizioni come dati (valore,
  elenco, `{'not': …}`, `{'min'/'max': n}`), `RULES` con le 12 regole a più fatti o con parametri iniziali;
  parità di punteggio risolta per ampiezza del fatto, poi per nome (riproduce l'ordine di prima).
- Le 40 analisi incluse dichiarano `suits` (29 con voci, 11 con elenco vuoto e il motivo in commento); la forma
  vecchia dei plugin (`kinds`, `x`) funziona ancora.
- `PLUGINS.md` (EN/IT) con l'esempio di *Statistica descrittiva*, ROADMAP, note di rilascio "0.2.6 (in
  preparazione)", manuali EN/IT (§7.1 e storia delle revisioni).
- 2026-10-15, su tua indicazione: suggerite anche le 6 analisi che non lo erano (`survival`, `cox`, `anova_models`,
  `contingency`, `matrix_spots`, `decimate`), con i fatti nuovi `ykind`, `hue_kind`, `events`, `rows`. Prima di
  rigenerare il golden ho verificato su 45 360 combinazioni che, tolte queste sei, i consigli restano identici.

Testo originale:


**Oggi.** [piplotter/advisor.py](piplotter/advisor.py) contiene circa 54 regole scritte come codice (`add(...)`
dentro `rules()`), divise per tipo di grafico: matrice, distribuzione, gruppi, correlazioni, xy, spettri, segnali,
decadimenti…

I plugin dell'utente possono dichiarare `PLUGIN['suits']` (vedi `PLUGINS.md`), ma nessuna delle 40 analisi incluse
lo fa (0 su 40).

**Da fare**

1. Prima di toccare qualcosa, un test "golden" che registra i consigli attuali (analisi, punteggio, parametri
   iniziali) su un insieme di grafici di riferimento: ogni tipo di grafico, x spettro/tempo/categoria, più curve,
   decadimento, matrice. Serve a dimostrare che il comportamento resta identico.
2. Le regole diventano una tabella di dati: condizioni (tipo di grafico, tipo di x, più curve, decadimento,
   matrice…) → analisi, punteggio, motivo EN/IT, parametri iniziali. `rules()` legge la tabella.
3. Ogni analisi inclusa dichiara il suo `suits`, come i plugin. La tabella del consigliere tiene solo ciò che dipende
   da più fatti insieme o che porta parametri iniziali.
4. Aggiornare `PLUGINS.md` (EN/IT) con l'esempio di un'analisi inclusa.

**Verifica**

- Il test golden passa senza modifiche.
- I test dell'interfaccia sulle analisi suggerite passano (`test_example_figure_suggestions_and_export`).

---

## 3. Altri punti emersi in questo giro

- ~~**Versione da pubblicare.**~~ Fatto: lo stato della pagina, il servizio a moduli e gli schemi con versione sono
  pubblicati come **0.2.5** (tag `v0.2.5`), con una sezione propria nelle note di rilascio.
- ~~**Test dell'interfaccia per i nuovi messaggi.**~~ Fatto il 2026-10-15: `test_schema_messages_in_the_page` in
  `tests/test_ui.py` (descrizione non valida → riquadro degli errori, poi il grafico torna; due `.piplot` non conformi,
  una sorgente senza `parent` e un `kind` sconosciuto → rifiutati con il punto, i file sullo schermo restano). Nel
  farlo: i messaggi di `anyOf` ora parlano della forma che il documento nomina (prima una sorgente di analisi senza
  `parent` diceva `“sample” is missing`). Erano due percorsi:
  - un grafico con una descrizione non valida deve mostrare l'errore `spec` nel riquadro degli errori;
  - un progetto `.piplot` non conforme deve essere rifiutato con il punto del problema.
- **Tavolozze e mappe di colore nello schema.** Oggi `style.palette` e `style.cmap` sono stringhe libere, perché
  `plotting.py` ripiega sul predefinito se un valore è sconosciuto. Si può passare a un `enum` del catalogo, sapendo
  che un progetto fatto con una tavolozza futura verrebbe rifiutato invece di ripiegare.
- **Pagina e schema.** La pagina non legge lo schema: corregge da sé le descrizioni vecchie (per esempio `inset` in
  `app.js`, "figures saved before insets"). Queste correzioni andrebbero spostate in `SPEC_UPGRADES`, così vivono in
  un posto solo.

---

## Ordine consigliato

1. Analyses: test golden, poi tabella e `suits` (il rischio è basso perché il test golden protegge).
2. Data model: registro delle sorgenti, poi schema della sorgente, poi provenienza e cache.
3. Test dell'interfaccia per i messaggi dello schema.

Per ogni passo: test Python e dell'interfaccia, documenti (ROADMAP, note di rilascio EN/IT, manuali EN/IT in
parità), commit locale, resoconto, push solo dopo il tuo OK.

— Dr. T. Francese
