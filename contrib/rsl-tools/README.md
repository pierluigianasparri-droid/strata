# RSL Tools

Programma compagno di Strata per le analisi di Risposta Sismica Locale secondo le NTC 2018:

1. legge i progetti Strata salvati con i risultati (`.json`) per SLO, SLD, SLV e SLC
   (in alternativa i file `.csv` degli spettri esportati da Strata);
2. calcola la pericolosità di base (TR, ag, F0, Tc*) dalle coordinate del sito con il
   reticolo di riferimento NTC (Allegato B al D.M. 14/01/2008), con conversione WGS84 → ED50;
3. regolarizza lo spettro medio con la procedura dell'Appendice 1 dell'Ordinanza n. 55
   del 24/04/2018 (Amax, S, F0, TB, TC, TD);
4. genera la relazione Word con tabelle e grafici, partendo da un tuo modello.

Lo spettro medio è la media geometrica degli spettri dei singoli accelerogrammi, cioè la
"Median" calcolata da Strata con distribuzione log-normale.

## Uso

Scarica `RSL-Tools.exe` dalla scheda *Actions* del repository (artefatto `RSL-Tools-win64`)
e avvialo; non serve installare Python. In alternativa:

```
pip install -r requirements.txt
python rsl_tools.py
```

In Strata, per ogni stato limite: carica gli accelerogrammi, esegui il calcolo con uno
spettro di risposta a piano campagna tra gli output e salva il progetto. In RSL Tools
indica i quattro progetti, le coordinate, VN e classe d'uso, poi premi
*Calcola regolarizzazione* o *Genera relazione Word*. Le impostazioni di un lavoro si
possono salvare in un file `.rsl.json` e riaprire.

## Modello Word

Il modello è un normale documento Word (per esempio una relazione precedente) in cui le
parti variabili sono sostituite da segnaposto. Intestazioni, piè di pagina, stili, testi
fissi e figure restano come sono.

**Segnaposto di blocco** (da soli in un paragrafo, vengono sostituiti da tabelle e grafici):

| Segnaposto | Contenuto |
|---|---|
| `{{TABELLA_STRATI}}` | modello sismostratigrafico (dal progetto Strata) |
| `{{PROFILO_VS}}` | grafico del profilo di Vs |
| `{{TABELLA_CURVE}}` | curve di decadimento per terreno |
| `{{GRAFICO_CURVE}}` | grafico delle curve G/G0 e D |
| `{{TABELLA_COORDINATE}}` | coordinate WGS84 / ED50 |
| `{{TABELLA_PERICOLOSITA}}` | TR, ag, F0, Tc* per stato limite |
| `{{FIGURE_DISAGGREGAZIONE}}` | immagini della cartella "disaggregazione" |
| `{{TABELLA_MR}}` | intervalli di distanza e magnitudo |
| `{{FIGURE_ACCELEROGRAMMI}}` | immagini della cartella "REXELite" |
| `{{TABELLA_ACCELEROGRAMMI}}` | elenco accelerogrammi con PGA |
| `{{RISULTATI_RSL}}` | per ogni SL: tabella degli spettri, grafico, spettro medio |
| `{{REGOLARIZZAZIONE}}` | metodo, punti, parametri e grafico per ogni SL |

Nelle cartelle di immagini, i file il cui nome contiene `SLO`, `SLD`, `SLV` o `SLC`
vengono raggruppati sotto lo stato limite corrispondente, in ordine alfabetico.

**Segnaposto di testo** (dentro una frase): `{{VN}}`, `{{CLASSE_USO}}`, `{{CU}}`,
`{{TR_SLO}}`…`{{TR_SLC}}`, `{{AG_SLO}}`…, `{{AMAX_SLV}}`, `{{S_SLV}}`, `{{F0_SLV}}`,
`{{TB_SLV}}`, `{{TC_SLV}}`, `{{TD_SLV}}` (e così per ogni SL), `{{LAT_WGS84}}`,
`{{LON_WGS84}}`, `{{LAT_ED50}}`, `{{LON_ED50}}`, `{{PROF_BEDROCK}}`, `{{VS_BEDROCK}}`,
`{{SMORZAMENTO}}`, `{{DATA}}`, più qualsiasi campo libero inserito nel programma
(`OGGETTO = ...` diventa `{{OGGETTO}}`).

Senza modello il programma usa una struttura di base con tutti i blocchi.

## Dati

Il reticolo `rsltools/data/reticolo_ntc.json` contiene i 10.751 nodi dell'Allegato B
(Open Data MIT, "Parametri spettrali sismici"), coordinate ED50, ag in g. Le isole
della Tabella 2 dell'Allegato B non sono gestite.
