"""Lettura dei progetti Strata (.json) e dei file CSV esportati da Strata."""
from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass, field

import numpy as np

G = 9.80665


@dataclass
class Strato:
    nome: str
    spessore: float
    profondita: float
    gamma: float  # kN/m3
    vs: float

    @property
    def densita(self):  # kg/m3
        return self.gamma / G * 1000.0


@dataclass
class TipoTerreno:
    nome: str
    modulo_nome: str
    smorzamento_nome: str
    deformazioni: list = field(default_factory=list)
    g_g0: list = field(default_factory=list)
    deformazioni_d: list = field(default_factory=list)
    d: list = field(default_factory=list)


@dataclass
class Moto:
    nome: str
    file: str
    descrizione: str
    scala: float
    pga: float | None = None


@dataclass
class RisultatoRSL:
    titolo: str
    periodi: np.ndarray
    spettri: np.ndarray  # (n_moti, n_periodi)
    nomi_moti: list
    smorzamento: float = 5.0
    strati: list = field(default_factory=list)
    bedrock: Strato | None = None
    tipi: list = field(default_factory=list)
    moti: list = field(default_factory=list)

    @property
    def media(self):
        """Spettro medio: media geometrica (= mediana log-normale di Strata).

        È il valore che Strata riporta come "Median" e che nelle relazioni
        compare come colonna MEDIA."""
        return np.exp(np.log(self.spettri).mean(axis=0))

    @property
    def media_aritmetica(self):
        return self.spettri.mean(axis=0)


def _assi(dim: dict) -> np.ndarray:
    lo, hi, n = float(dim["min"]), float(dim["max"]), int(dim["size"])
    if int(dim.get("spacing", 1)) == 1:
        return np.logspace(np.log10(lo), np.log10(hi), n)
    return np.linspace(lo, hi, n)


def _modello(m: dict):
    strain = m.get("strain") or []
    avg = m.get("average") or []
    return list(strain), list(avg)


def leggi_progetto(path: str, profondita: float = 0.0) -> RisultatoRSL:
    """Legge un progetto Strata salvato con i risultati.

    Usa lo spettro di risposta calcolato alla profondità ``profondita``
    (0 = piano campagna)."""
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    if not d.get("hasResults"):
        raise ValueError(f"{os.path.basename(path)}: il progetto non contiene risultati. "
                         "Esegui il calcolo in Strata e salva il progetto.")
    oc = d["outputCatalog"]
    periodi = _assi(oc["period"])

    spettri = [s for s in oc.get("spectraOutputCatalog", [])
               if s.get("className") == "ResponseSpectrumOutput" and s.get("data")]
    if not spettri:
        raise ValueError(f"{os.path.basename(path)}: nessuno spettro di risposta tra i risultati. "
                         "In Strata, scheda Output, aggiungi uno spettro di risposta a piano campagna.")
    spettri.sort(key=lambda s: abs(float(s.get("depth", 0)) - profondita))
    data = spettri[0]["data"]  # [sito][moto][periodo]
    sito = np.array(data[0], float)

    moti_json = d["motionLibrary"]["motions"]
    moti = []
    for m in moti_json:
        nome = os.path.splitext(os.path.basename(m.get("fileName", "")))[0]
        accel = m.get("accel") or []
        pga = max((abs(a) for a in accel), default=None) if accel else None
        moti.append(Moto(nome, m.get("fileName", ""), (m.get("description") or "").strip(),
                         float(m.get("scale", 1.0)), pga))
    attivi = [mo for mo, mj in zip(moti, moti_json) if mj.get("enabled", True)]
    nomi = [mo.nome for mo in attivi] if len(attivi) == sito.shape[0] else \
        [f"{i + 1}" for i in range(sito.shape[0])]

    sp = d["siteProfile"]
    catalogo = sp.get("soilTypeCatalog", [])
    tipi = []
    for t in catalogo:
        gs, gv = _modello(t.get("modulusModel", {}))
        ds, dv = _modello(t.get("dampingModel", {}))
        tipi.append(TipoTerreno(t.get("name", ""), t.get("modulusModel", {}).get("name", ""),
                                t.get("dampingModel", {}).get("name", ""), gs, gv, ds, dv))
    strati = []
    for l in sp.get("soilLayers", []):
        idx = int(l.get("soilType", 0))
        tipo = catalogo[idx] if 0 <= idx < len(catalogo) else {}
        strati.append(Strato(tipo.get("name", f"Strato {len(strati) + 1}"),
                             float(l["thickness"]), float(l.get("depth", 0)),
                             float(tipo.get("untWt", 0)), float(l["avg"])))
    b = sp.get("bedrock", {})
    bedrock = Strato("Bedrock", 0.0, float(b.get("depth", 0)), float(b.get("untWt", 0)),
                     float(b.get("avg", 0))) if b else None

    return RisultatoRSL(oc.get("title", ""), periodi, sito, nomi,
                        float(oc.get("damping", 5.0)), strati, bedrock, tipi, moti)


def leggi_csv(path: str) -> RisultatoRSL:
    """Legge lo spettro di risposta esportato da Strata (Output > Export)."""
    header, rows = None, []
    with open(path, encoding="utf-8", newline="") as fh:
        for line in fh:
            if line.startswith("#"):
                cols = [c.strip() for c in line[1:].split(",")]
                if cols and cols[0].lower().startswith("period"):
                    header = cols
                continue
            if line.strip():
                rows.append([c.strip() for c in line.split(",")])
    if header is None:
        raise ValueError(f"{os.path.basename(path)}: intestazione Strata non trovata")
    keep = [i for i, h in enumerate(header)
            if i > 0 and h and h not in ("Median", "Mean", "Log Stdev", "Stdev")
            and "(disabled)" not in h]
    arr = np.array([[float(r[0])] + [float(r[i]) for i in keep] for r in rows if len(r) > max(keep)])
    nomi = [header[i].removeprefix("M-").split("-M-")[-1] for i in keep]
    return RisultatoRSL(os.path.splitext(os.path.basename(path))[0], arr[:, 0], arr[:, 1:].T, nomi)


def leggi(path: str) -> RisultatoRSL:
    return leggi_csv(path) if path.lower().endswith(".csv") else leggi_progetto(path)
