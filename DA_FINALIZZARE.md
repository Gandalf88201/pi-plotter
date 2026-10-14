# π-plotter — punti rimanenti da finalizzare

Stato al 2026-10-14, versione 0.2.5 (tag `v0.2.5`).
Riferimento: tabella *Code structure (robustness)* di `ROADMAP.md`.

| Riga ROADMAP | Stato |
|---|---|
| Front end (divisione, eventi, stato) | fatto |
| Front-end tests | fatto, da estendere a ogni nuova funzione |
| Service (rotte, moduli per area, schemi con versione) | fatto |
| **Data model** | **da fare** |
| **Analyses** | **da fare** |

---

## 1. Data model — formalizzare "sorgente + operazioni"

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

## 2. Analyses — regole del consigliere come dati e `suits` per le analisi incluse

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
- **Test dell'interfaccia per i nuovi messaggi.** Mancano due percorsi:
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
