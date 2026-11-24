"""Generazione della relazione RSL in Word.

La relazione si costruisce a partire da un *modello* .docx: un documento
Word normale (per esempio una tua relazione precedente) in cui le parti
che cambiano da un lavoro all'altro sono sostituite da segnaposto:

* segnaposto di testo, dentro una frase: ``{{VN}}``, ``{{TR_SLV}}``, ...
* segnaposto di blocco, da soli in un paragrafo: ``{{RISULTATI_RSL}}``,
  ``{{REGOLARIZZAZIONE}}``, ... vengono sostituiti da tabelle e grafici.

L'elenco completo è in ``SEGNAPOSTO`` (e nel README). Se non si indica un
modello si usa una struttura di base.
"""
from __future__ import annotations

import copy
import os
import re
import tempfile
from dataclasses import dataclass, field

import numpy as np
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from . import grafici
from .ntc import STATI_LIMITE, Pericolosita, coefficiente_ss
from .regolarizzazione import SpettroRegolarizzato, spettro_ntc_suolo_a
from .strata_io import RisultatoRSL

SEGNAPOSTO_BLOCCHI = {
    "TABELLA_STRATI": "Tabella del modello sismostratigrafico (da Strata)",
    "PROFILO_VS": "Grafico del profilo di Vs",
    "TABELLA_CURVE": "Tabella delle curve di decadimento per terreno",
    "GRAFICO_CURVE": "Grafico delle curve G/G0 e D",
    "TABELLA_COORDINATE": "Coordinate del sito WGS84 / ED50",
    "TABELLA_PERICOLOSITA": "TR, ag, F0, Tc* per stato limite",
    "FIGURE_DISAGGREGAZIONE": "Immagini della disaggregazione (cartella)",
    "TABELLA_MR": "Intervalli di magnitudo e distanza per stato limite",
    "FIGURE_ACCELEROGRAMMI": "Immagini della selezione REXELite (cartella)",
    "TABELLA_ACCELEROGRAMMI": "Elenco degli accelerogrammi per stato limite",
    "RISULTATI_RSL": "Tabelle e grafici degli spettri per stato limite",
    "REGOLARIZZAZIONE": "Regolarizzazione: metodo, punti, parametri e grafici",
    "ANALISI_RISULTATI": "Riepilogo finale: confronto NTC 2018 / RSL per SLV e SLD (ag, Ss, "
                         "St, AMAX)",
}
SEGNAPOSTO_TESTO = [
    "VN", "CLASSE_USO", "CU", "TR_SLO", "TR_SLD", "TR_SLV", "TR_SLC",
    "AG_SLO", "AG_SLD", "AG_SLV", "AG_SLC", "LAT_WGS84", "LON_WGS84",
    "LAT_ED50", "LON_ED50", "PROF_BEDROCK", "VS_BEDROCK", "SMORZAMENTO", "DATA",
    "CAT_SUOLO", "CAT_TOPOGRAFICA", "ST", "SS_NTC_SLV", "AMAX_NTC_SLV", "AMAX_RSL_SLV",
    "(e gli stessi per SLO, SLD, SLC)",
    "+ tutti i campi liberi inseriti nel programma (es. COMMITTENTE, COMUNE)",
]

_RX = re.compile(r"\{\{\s*([A-Z0-9_]+)\s*\}\}")


@dataclass
class DatiRelazione:
    vn: float
    classe_uso: str
    cu: float
    lat_wgs84: float | None
    lon_wgs84: float | None
    lat_ed50: float
    lon_ed50: float
    pericolosita: dict  # sl -> Pericolosita
    risultati: dict  # sl -> RisultatoRSL
    regolarizzati: dict  # sl -> SpettroRegolarizzato
    mr: dict = field(default_factory=dict)  # sl -> (dist, mag) testi
    cartella_disaggregazione: str = ""
    cartella_accelerogrammi: str = ""
    campi: dict = field(default_factory=dict)
    categoria_suolo: str = "B"
    categoria_topografica: str = "T1"
    st: float = 1.0
    carattere: str = ""  # font di tutta la relazione ("" = come nel modello)
    dimensione: float | None = None  # dimensione del testo normale in pt


# --------------------------------------------------------------------------- utilità docx

def _stile(doc, *nomi):
    presenti = {s.name for s in doc.styles}
    for n in nomi:
        if n in presenti:
            return n
    return None


def _iter_paragrafi(doc):
    def da_contenitore(c):
        for p in c.paragraphs:
            yield p
        for t in c.tables:
            for r in t.rows:
                for cell in r.cells:
                    yield from da_contenitore(cell)
    yield from da_contenitore(doc)
    for s in doc.sections:
        for part in (s.header, s.footer, s.first_page_header, s.first_page_footer):
            try:
                yield from da_contenitore(part)
            except Exception:  # noqa: BLE001
                pass


def _sostituisci_testo(p, valori):
    testo = p.text
    if "{{" not in testo:
        return
    nuovo = _RX.sub(lambda m: str(valori.get(m.group(1), m.group(0))), testo)
    if nuovo == testo:
        return
    runs = p.runs
    if not runs:
        return
    runs[0].text = nuovo
    for r in runs[1:]:
        r.text = ""


class _Inseritore:
    """Inserisce contenuti prima di un paragrafo segnaposto."""

    def __init__(self, doc, ancora, stile_tabella, cartella_img):
        self.doc, self.ancora = doc, ancora
        self.stile_tabella = stile_tabella
        self.img = cartella_img
        self.n_img = 0
        self.didascalia = _stile(doc, "Caption", "Didascalia")
        self.titolo = _stile(doc, "Heading 3", "Titolo 3")

    def _sposta(self, el):
        self.ancora._p.addprevious(el)

    def par(self, testo="", grassetto=False, centrato=False, stile=None, corsivo=False):
        p = self.doc.add_paragraph(style=stile)
        if testo:
            r = p.add_run(testo)
            r.bold = grassetto
            r.italic = corsivo
        if centrato:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        self._sposta(p._p)
        return p

    def caption(self, testo):
        if self.didascalia:
            return self.par(testo, stile=self.didascalia, centrato=True)
        return self.par(testo, corsivo=True, centrato=True)

    def stato_limite(self, sl):
        return self.par(f"Stato limite: {sl}", grassetto=True)

    def tabella(self, intestazione, righe, dimensione=9, larghezze=None):
        t = self.doc.add_table(rows=1, cols=len(intestazione))
        if self.stile_tabella:
            try:
                t.style = self.stile_tabella
            except Exception:  # noqa: BLE001
                pass
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        for i, h in enumerate(intestazione):
            c = t.rows[0].cells[i]
            c.text = ""
            r = c.paragraphs[0].add_run(str(h))
            r.bold = True
            r.font.size = Pt(dimensione)
            c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        for riga in righe:
            cells = t.add_row().cells
            for i, v in enumerate(riga):
                cells[i].text = ""
                r = cells[i].paragraphs[0].add_run(str(v))
                r.font.size = Pt(dimensione)
                cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        if larghezze:
            for row in t.rows:
                for c, w in zip(row.cells, larghezze):
                    c.width = Cm(w)
        self._sposta(t._tbl)
        self.par()
        return t

    def immagine(self, path, larghezza_cm=16.0):
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run().add_picture(path, width=Cm(larghezza_cm))
        self._sposta(p._p)
        return p

    def nuovo_png(self, nome):
        self.n_img += 1
        return os.path.join(self.img, f"{self.n_img:02d}_{nome}.png")


def _f(x, n=3):
    return f"{x:.{n}f}"


def _immagini_cartella(cartella):
    if not cartella or not os.path.isdir(cartella):
        return []
    est = (".png", ".jpg", ".jpeg", ".bmp", ".gif")
    return sorted(os.path.join(cartella, f) for f in os.listdir(cartella)
                  if f.lower().endswith(est))


def _per_sl(files):
    gruppi = {sl: [] for sl in STATI_LIMITE}
    altri = []
    for f in files:
        nome = os.path.basename(f).upper()
        sl = next((s for s in STATI_LIMITE if s in nome), None)
        (gruppi[sl] if sl else altri).append(f)
    return gruppi, altri


# --------------------------------------------------------------------------- blocchi

def _blocco(nome, ins: _Inseritore, d: DatiRelazione):
    sl_list = [sl for sl in STATI_LIMITE if sl in d.risultati]
    primo = d.risultati[sl_list[0]] if sl_list else None

    if nome == "TABELLA_STRATI" and primo:
        righe = [[i + 1, s.nome, _f(s.spessore, 2), f"{s.densita:.0f}", f"{s.vs:.0f}"]
                 for i, s in enumerate(primo.strati)]
        if primo.bedrock:
            b = primo.bedrock
            righe.append([len(righe) + 1, "Substrato sismico", "semisp.", f"{b.densita:.0f}",
                          f"{b.vs:.0f}"])
        ins.tabella(["Strato", "Descrizione", "S [m]", "ρ [kg/m³]", "Vs [m/s]"], righe,
                    larghezze=[1.5, 8, 2, 2.5, 2.5])

    elif nome == "PROFILO_VS" and primo:
        png = ins.nuovo_png("profilo_vs")
        grafici.profilo_vs(png, primo.strati, primo.bedrock)
        ins.immagine(png, 7.5)
        ins.caption("Profilo di velocità delle onde di taglio Vs")

    elif nome == "TABELLA_CURVE" and primo:
        righe, visti = [], set()
        for s in primo.strati:
            t = next((t for t in primo.tipi if t.nome == s.nome), None)
            if t and t.nome not in visti:
                visti.add(t.nome)
                righe.append([t.nome, t.modulo_nome, t.smorzamento_nome])
        ins.tabella(["Descrizione", "Modulo di taglio G", "Rapporto di smorzamento D"], righe,
                    larghezze=[8, 4, 4])

    elif nome == "GRAFICO_CURVE" and primo:
        png = ins.nuovo_png("curve")
        grafici.curve_decadimento(png, primo.tipi)
        ins.immagine(png)
        ins.caption("Curve di decadimento del modulo di taglio e di smorzamento utilizzate")

    elif nome == "TABELLA_COORDINATE":
        w = (_f(d.lat_wgs84, 6), _f(d.lon_wgs84, 6)) if d.lat_wgs84 is not None else ("-", "-")
        ins.tabella(["", "WGS84", "ED50"],
                    [["LATITUDINE", w[0], _f(d.lat_ed50, 6)],
                     ["LONGITUDINE", w[1], _f(d.lon_ed50, 6)]], larghezze=[4, 4, 4])

    elif nome == "TABELLA_PERICOLOSITA":
        righe = []
        for sl in STATI_LIMITE:
            p: Pericolosita = d.pericolosita[sl]
            righe.append([sl, f"{p.tr:.0f}", _f(p.ag), _f(p.f0), _f(p.tc_star)])
        ins.tabella(["Stato limite", "TR [anni]", "ag [g]", "F0 [-]", "Tc* [s]"], righe)
        ins.caption("Parametri di pericolosità di base dal reticolo di riferimento NTC 2018 "
                    f"(nodi {', '.join(map(str, d.pericolosita['SLV'].nodi))})")

    elif nome in ("FIGURE_DISAGGREGAZIONE", "FIGURE_ACCELEROGRAMMI"):
        cartella = (d.cartella_disaggregazione if nome == "FIGURE_DISAGGREGAZIONE"
                    else d.cartella_accelerogrammi)
        gruppi, altri = _per_sl(_immagini_cartella(cartella))
        for f in altri:
            ins.immagine(f)
        for sl in STATI_LIMITE:
            if gruppi[sl]:
                ins.stato_limite(sl)
                for f in gruppi[sl]:
                    ins.immagine(f)
                if nome == "FIGURE_DISAGGREGAZIONE":
                    ins.caption(f"Disaggregazione sismica per {sl}")

    elif nome == "TABELLA_MR":
        righe = [[sl, *d.mr.get(sl, ("", ""))] for sl in STATI_LIMITE]
        ins.tabella(["Stato limite", "Distanza (km)", "Magnitudo"], righe, larghezze=[4, 4, 4])

    elif nome == "TABELLA_ACCELEROGRAMMI":
        for sl in sl_list:
            r = d.risultati[sl]
            ins.stato_limite(sl)
            righe = [[i + 1, m.nome, m.descrizione, _f(m.scala, 2),
                      _f(m.pga, 4) if m.pga else "-"] for i, m in enumerate(r.moti)]
            ins.tabella(["N.", "File", "Descrizione", "Scala", "PGA [g]"], righe, dimensione=8,
                        larghezze=[1, 6, 6, 1.5, 2])

    elif nome == "RISULTATI_RSL":
        for sl in sl_list:
            r: RisultatoRSL = d.risultati[sl]
            ins.stato_limite(sl)
            nomi = [str(i + 1) for i in range(len(r.nomi_moti))]
            media = r.media
            righe = [[f"{t:.6g}", *[f"{v:.6f}" for v in r.spettri[:, j]], f"{media[j]:.6f}"]
                     for j, t in enumerate(r.periodi)]
            ins.tabella(["T", *nomi, "MEDIA"], righe, dimensione=7)
            png = ins.nuovo_png(f"spettri_{sl}")
            grafici.spettri_moti(png, sl, r.periodi, r.spettri, nomi, media)
            ins.immagine(png)
            ins.par(f"Pertanto, lo spettro medio ottenuto dallo studio di RSL in oggetto per "
                    f"lo stato limite {sl} è il seguente:")
            png = ins.nuovo_png(f"medio_{sl}")
            grafici.spettro_medio(png, sl, r.periodi, media)
            ins.immagine(png)

    elif nome == "REGOLARIZZAZIONE":
        _testo_metodo(ins)
        for sl in sl_list:
            r = d.risultati[sl]
            reg: SpettroRegolarizzato = d.regolarizzati[sl]
            ins.stato_limite(sl)
            T, sa = reg.punti(t_max=float(max(r.periodi)))
            ins.tabella(["", "T [sec]", "Sa [g]"],
                        [[i + 1, f"{t:.4f}", f"{s:.3f}"] for i, (t, s) in enumerate(zip(T, sa))],
                        dimensione=7, larghezze=[2, 4, 4])
            ins.par("Dalla procedura di regolarizzazione risulta:")
            ins.tabella(["Amax", "S", "F0", "TB [sec]", "TC [sec]", "TD [sec]"],
                        [[_f(reg.amax), _f(reg.S, 2), _f(reg.F0, 2), _f(reg.TB, 2),
                          _f(reg.TC, 2), _f(reg.TD, 2)]])
            _legenda(ins)
            p = d.pericolosita[sl]
            png = ins.nuovo_png(f"regolarizzato_{sl}")
            grafici.regolarizzazione(png, sl, r.periodi, r.media, reg, r.periodi,
                                     spettro_ntc_suolo_a(p.ag, p.f0, p.tc_star, r.periodi,
                                                         r.smorzamento))
            ins.immagine(png)

    elif nome == "ANALISI_RISULTATI":
        _analisi_risultati(ins, d)


def _testo_metodo(ins):
    ins.par("Lo spettro medio ottenuto dalle simulazioni numeriche è stato trasformato in uno "
            "spettro di forma standard secondo le NTC 2018 con la procedura di regolarizzazione "
            "riportata nell'Appendice 1 dell'Ordinanza n. 55 del 24 aprile 2018. I passi sono:")
    for t in (
        "si individua il periodo TA del massimo dello spettro di pseudoaccelerazione SA e se ne "
        "calcola il valore medio SA,m tra 0,5·TA e 1,5·TA, assunto come ordinata del tratto ad "
        "accelerazione costante;",
        "si ricava lo spettro di pseudovelocità SV = SA·T/2π, se ne individua il periodo TV del "
        "massimo e il valore medio SV,m tra 0,8·TV e 1,2·TV;",
        "si calcolano TC = 2π·SV,m/SA,m, TB = TC/3 e TD = 4,0·ag/g + 1,6;",
        "si ricava l'ancoraggio amax per estrapolazione lineare dall'ordinata a T = 0,01 s, "
        "quindi S = amax/ag e F0 = SA,m/(η·amax), con η = √(10/(5+ξ)) ≥ 0,55.",
    ):
        ins.par("- " + t)
    ins.par("Di seguito si riportano, per ciascuno stato limite, i punti dello spettro "
            "regolarizzato, i parametri ottenuti e il confronto grafico con lo spettro medio "
            "delle simulazioni e con lo spettro NTC 2018 su suolo di riferimento A.")


LEGENDA = [
    ("Amax", "punto di ancoraggio a T=0 dello spettro di output;"),
    ("S", "coefficiente che tiene conto degli effetti di amplificazione (strat. e/o "
          "topografici);"),
    ("F0", "valore massimo dello spettro in accelerazione orizzontale;"),
    ("TB", "periodo corrispondente all'inizio del tratto dello spettro ad accelerazione "
           "costante;"),
    ("Tc", "periodo corrispondente all'inizio del tratto dello spettro a velocità costante;"),
    ("TD", "periodo corrispondente all'inizio del tratto dello spettro a spostamento costante."),
]


def _legenda(ins):
    ins.par("dove:")
    for k, t in LEGENDA:
        p = ins.par(f"{k}\t: {t}")
        p.paragraph_format.tab_stops.add_tab_stop(Cm(1.25))
        p.paragraph_format.space_after = Pt(0)
    ins.par()


def _virgola(x, n):
    return f"{x:.{n}f}".replace(".", ",")


def _ombreggia(cella, colore):
    tcPr = cella._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), colore)
    tcPr.append(shd)


def valori_confronto(d: DatiRelazione, sl: str) -> dict:
    """ag, Ss e AMAX secondo NTC 2018 (categoria di suolo) e secondo la RSL."""
    p = d.pericolosita[sl]
    reg = d.regolarizzati[sl]
    ss_ntc = coefficiente_ss(d.categoria_suolo, p.ag, p.f0)
    return {"ag": p.ag, "ss_ntc": ss_ntc, "amax_ntc": p.ag * ss_ntc * d.st,
            "ss_rsl": reg.S, "amax_rsl": reg.amax * d.st, "st": d.st}


def _analisi_risultati(ins, d: DatiRelazione):
    st = _virgola(d.st, 1)
    p = ins.par("Prima di fornire il riepilogo dei risultati, si ricorda che l'elaborazione "
                "della Risposta Sismica Locale eseguita è 1D e pertanto ")
    if d.st > 1.0:
        r = p.add_run(f"vista la categoria topografica {d.categoria_topografica} tutti i "
                      "coefficienti sismici riportati nel capitolo precedente ovvero F0, Tb, Tc "
                      f"(non solo l'Amax) dovranno essere moltiplicati per il coefficiente {st}.")
    else:
        r = p.add_run(f"vista la categoria topografica {d.categoria_topografica} (St = {st}) i "
                      "coefficienti sismici riportati nel capitolo precedente (Amax, F0, Tb, Tc) "
                      "non devono essere ulteriormente amplificati.")
    r.bold = True
    p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    ins.par()

    for sl in ("SLV", "SLD"):
        if sl not in d.regolarizzati:
            continue
        v = valori_confronto(d, sl)
        t_p = ins.par()
        r = t_p.add_run(f"Confronto NTC 2018 ed Analisi RSL 1D per {sl}")
        r.bold = True
        r.underline = True
        t = ins.tabella(["", "ag(g) di base", "coeff. Ss", "coeff. St", "AMAX"], [
            ["NTC2018", _virgola(v["ag"], 3), _virgola(v["ss_ntc"], 2) + "*",
             _virgola(v["st"], 2) + " **", _virgola(v["amax_ntc"], 3)],
            ["RSL", _virgola(v["ag"], 3), _virgola(v["ss_rsl"], 2) + " ***",
             _virgola(v["st"], 2) + " **",
             _virgola(v["amax_rsl"], 3) + ("****" if sl == "SLV" else "")],
        ], dimensione=10, larghezze=[3, 3, 3, 3, 3])
        for row in t.rows:
            for c in row.cells:
                for par in c.paragraphs:
                    for run in par.runs:
                        run.bold = False
        for c in t.rows[1].cells[:1] + t.rows[2].cells[:1]:
            c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.LEFT
        for c in t.rows[2].cells:
            _ombreggia(c, "FFFF00")
        if sl == "SLV":
            r = t.rows[2].cells[4].paragraphs[0].runs[-1]
            r.bold = True
            r.font.color.rgb = RGBColor(0xFF, 0x00, 0x00)

    note = [
        (f"* categoria di suolo \"{d.categoria_suolo}\" ricavata attraverso indagini in sito "
         "NTC2018", False),
        (f"** categoria topografica {d.categoria_topografica} dovuta alla morfologia - NTC2018",
         False),
        ("*** valore di Ss ricavato dalla RSL 1D in SLV o SLD", False),
        ("**** Valore da considerare ai fini degli incrementi dovuti all'amplificazione sismica",
         True),
    ]
    for testo, rosso in note:
        p = ins.par()
        r = p.add_run(testo)
        r.italic = True
        if rosso:
            r.font.color.rgb = RGBColor(0xFF, 0x00, 0x00)
        p.paragraph_format.space_after = Pt(2)
    ins.par()


# --------------------------------------------------------------------------- font

_ATTR_FONT = ("ascii", "hAnsi", "cs", "eastAsia")
_ATTR_TEMA = ("asciiTheme", "hAnsiTheme", "cstheme", "eastAsiaTheme")


def _imposta_rfonts(rpr, nome):
    rf = rpr.find(qn("w:rFonts"))
    if rf is None:
        rf = OxmlElement("w:rFonts")
        rpr.insert(0, rf)
    for a in _ATTR_TEMA:
        rf.attrib.pop(qn(f"w:{a}"), None)
    for a in _ATTR_FONT:
        rf.set(qn(f"w:{a}"), nome)


def applica_font(doc, nome: str = "", dimensione: float | None = None):
    """Usa il carattere ``nome`` in tutta la relazione: stili, testo del
    modello con formattazione diretta, tabelle, intestazioni e piè di pagina.
    ``dimensione`` (pt) cambia il testo normale; titoli e tabelle mantengono
    le proprie dimensioni."""
    if nome:
        # stili e valori predefiniti del documento (gli stili senza carattere
        # proprio lo ereditano da questi)
        for rpr in doc.styles.element.iter(qn("w:rPr")):
            _imposta_rfonts(rpr, nome)
        parti = [doc.element.body]
        for sez in doc.sections:
            for hf in (sez.header, sez.footer, sez.first_page_header, sez.first_page_footer,
                       sez.even_page_header, sez.even_page_footer):
                if hf is not None and not hf.is_linked_to_previous:
                    parti.append(hf._element)
        for parte in parti:
            for rpr in parte.iter(qn("w:rPr")):
                if rpr.find(qn("w:rFonts")) is not None:
                    _imposta_rfonts(rpr, nome)
        # numeri degli elenchi (i simboli dei punti elenco restano invariati)
        try:
            numerazione = doc.part.numbering_part.element
        except (KeyError, NotImplementedError, AttributeError):
            numerazione = None
        if numerazione is not None:
            simboli = {"Symbol", "Wingdings", "Courier New", "OpenSymbol", "StarSymbol"}
            for rf in numerazione.iter(qn("w:rFonts")):
                if rf.get(qn("w:ascii")) not in simboli and (
                        rf.get(qn("w:ascii")) or rf.get(qn("w:cs"))):
                    _imposta_rfonts(rf.getparent(), nome)
    if dimensione:
        normale = _stile(doc, "Normal", "Normale")
        if normale is not None:
            doc.styles[normale].font.size = Pt(dimensione)


# --------------------------------------------------------------------------- modello di base

def _modello_base():
    doc = Document()
    doc.add_heading("Relazione di Risposta Sismica Locale", 0)
    sezioni = [
        ("Dati del sito e pericolosità di base",
         ["Vita nominale VN = {{VN}} anni, classe d'uso {{CLASSE_USO}} (CU = {{CU}}).",
          "{{TABELLA_COORDINATE}}", "{{TABELLA_PERICOLOSITA}}"]),
        ("Modello sismostratigrafico",
         ["{{TABELLA_STRATI}}", "Tabella - Caratteristiche meccaniche e sismostratigrafiche "
          "degli strati", "{{PROFILO_VS}}"]),
        ("Curve di decadimento", ["{{TABELLA_CURVE}}", "{{GRAFICO_CURVE}}"]),
        ("Disaggregazione", ["{{FIGURE_DISAGGREGAZIONE}}", "{{TABELLA_MR}}"]),
        ("Accelerogrammi di input", ["{{FIGURE_ACCELEROGRAMMI}}", "{{TABELLA_ACCELEROGRAMMI}}"]),
        ("Risultati della risposta sismica locale", ["{{RISULTATI_RSL}}"]),
        ("Regolarizzazione dello spettro di risposta", ["{{REGOLARIZZAZIONE}}"]),
        ("Analisi dei risultati", ["{{ANALISI_RISULTATI}}"]),
    ]
    for titolo, pars in sezioni:
        doc.add_heading(titolo, 1)
        for p in pars:
            doc.add_paragraph(p)
    return doc


# --------------------------------------------------------------------------- funzione principale

def genera(d: DatiRelazione, uscita: str, modello: str | None = None, log=print) -> str:
    doc = Document(modello) if modello else _modello_base()

    valori = {
        "VN": f"{d.vn:g}", "CLASSE_USO": d.classe_uso, "CU": f"{d.cu:.2f}",
        "LAT_ED50": _f(d.lat_ed50, 6), "LON_ED50": _f(d.lon_ed50, 6),
        "LAT_WGS84": _f(d.lat_wgs84, 6) if d.lat_wgs84 is not None else "-",
        "LON_WGS84": _f(d.lon_wgs84, 6) if d.lon_wgs84 is not None else "-",
    }
    import datetime
    valori["DATA"] = datetime.date.today().strftime("%d/%m/%Y")
    for sl, p in d.pericolosita.items():
        valori[f"TR_{sl}"] = f"{p.tr:.0f}"
        valori[f"AG_{sl}"] = _f(p.ag)
    for sl, reg in d.regolarizzati.items():
        for k in ("amax", "S", "F0", "TB", "TC", "TD"):
            valori[f"{k.upper()}_{sl}"] = _f(getattr(reg, k), 3 if k == "amax" else 2)
    valori["CAT_SUOLO"] = d.categoria_suolo
    valori["CAT_TOPOGRAFICA"] = d.categoria_topografica
    valori["ST"] = _virgola(d.st, 1)
    for sl in d.regolarizzati:
        v = valori_confronto(d, sl)
        valori[f"SS_NTC_{sl}"] = _virgola(v["ss_ntc"], 2)
        valori[f"AMAX_NTC_{sl}"] = _virgola(v["amax_ntc"], 3)
        valori[f"AMAX_RSL_{sl}"] = _virgola(v["amax_rsl"], 3)
    primo = next(iter(d.risultati.values()), None)
    if primo and primo.bedrock:
        valori["PROF_BEDROCK"] = f"{primo.bedrock.profondita:g}"
        valori["VS_BEDROCK"] = f"{primo.bedrock.vs:.0f}"
        valori["SMORZAMENTO"] = f"{primo.smorzamento:g}"
    valori.update({k.upper(): v for k, v in d.campi.items()})

    stile_tab = _stile(doc, "Table Grid", "Griglia tabella")
    if stile_tab is None and doc.tables:
        stile_tab = doc.tables[0].style

    with tempfile.TemporaryDirectory() as tmp:
        # blocchi
        trovati = []
        for p in list(doc.paragraphs):
            m = _RX.fullmatch(p.text.strip())
            if m and m.group(1) in SEGNAPOSTO_BLOCCHI:
                ins = _Inseritore(doc, p, stile_tab, tmp)
                ins.n_img = len(trovati) * 20
                _blocco(m.group(1), ins, d)
                p._p.getparent().remove(p._p)
                trovati.append(m.group(1))
        log(f"Blocchi inseriti: {', '.join(trovati) if trovati else 'nessuno'}")
        # testo
        mancanti = set()
        for p in _iter_paragrafi(doc):
            for m in _RX.finditer(p.text):
                if m.group(1) not in valori:
                    mancanti.add(m.group(1))
            _sostituisci_testo(p, valori)
        if mancanti:
            log("Segnaposto senza valore: " + ", ".join(sorted(mancanti)))
        if d.carattere or d.dimensione:
            applica_font(doc, d.carattere, d.dimensione)
            log(f"Carattere della relazione: {d.carattere or 'come nel modello'}"
                + (f", {d.dimensione:g} pt" if d.dimensione else ""))
        doc.save(uscita)
    return uscita
