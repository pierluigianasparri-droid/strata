"""Pericolosità di base NTC 2018 dal reticolo di riferimento (Allegato B, D.M. 14/01/2008).

Il file ``data/reticolo_ntc.json`` contiene i 10.751 nodi del reticolo
(coordinate ED50, ag in g, F0, Tc*) per i 9 periodi di ritorno tabulati.
Fonte: Open Data MIT, "Parametri spettrali sismici" (spettri2008.xls).
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field

import numpy as np

STATI_LIMITE = ("SLO", "SLD", "SLV", "SLC")
# NTC 2018 Tab. 3.2.I
PVR = {"SLO": 0.81, "SLD": 0.63, "SLV": 0.10, "SLC": 0.05}
# NTC 2018 Tab. 2.4.II
CU_CLASSE = {"I": 0.7, "II": 1.0, "III": 1.5, "IV": 2.0}

_GRID_PATH = os.path.join(os.path.dirname(__file__), "data", "reticolo_ntc.json")


def periodo_ritorno(vn: float, cu: float, stato_limite: str) -> float:
    """TR = -VR / ln(1 - PVR), con VR = VN * CU (NTC 2018 §2.4.3, §3.2.1)."""
    return -vn * cu / math.log(1.0 - PVR[stato_limite])


def wgs84_to_ed50(lat: float, lon: float) -> tuple[float, float]:
    """Conversione WGS84 -> ED50 (Molodensky ridotta, parametri medi per l'Italia).

    Precisione dell'ordine di qualche metro, ampiamente sufficiente per
    individuare i nodi del reticolo (passo circa 5,5 km).
    """
    # WGS84 -> ED50 (International 1924): dX=+87, dY=+98, dZ=+121 m
    dx, dy, dz = 87.0, 98.0, 121.0
    a, f = 6378137.0, 1 / 298.257223563
    a2, f2 = 6378388.0, 1 / 297.0
    da, df = a2 - a, f2 - f
    phi, lam = math.radians(lat), math.radians(lon)
    e2 = 2 * f - f * f
    sp, cp, sl, cl = math.sin(phi), math.cos(phi), math.sin(lam), math.cos(lam)
    rn = a / math.sqrt(1 - e2 * sp * sp)
    rm = a * (1 - e2) / (1 - e2 * sp * sp) ** 1.5
    dphi = (-dx * sp * cl - dy * sp * sl + dz * cp
            + (a * df + f * da) * math.sin(2 * phi)) / rm
    dlam = (-dx * sl + dy * cl) / (rn * cp)
    return lat + math.degrees(dphi), lon + math.degrees(dlam)


@dataclass
class Pericolosita:
    stato_limite: str
    tr: float
    ag: float
    f0: float
    tc_star: float
    nodi: list = field(default_factory=list)


class Reticolo:
    def __init__(self, path: str = _GRID_PATH):
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        self.tr = np.array(d["meta"]["trValues"], float)
        self.id = np.array(d["id"])
        self.lat = np.array(d["lat"], float)
        self.lon = np.array(d["lon"], float)
        self.par = {k: np.array(d[k], float) for k in ("ag", "F0", "Tc")}

    def parametri(self, lat_ed50: float, lon_ed50: float, tr: float) -> dict:
        """ag, F0, Tc* nel sito per il periodo di ritorno tr.

        Interpolazione logaritmica in TR tra i due periodi tabulati
        (Allegato A, eq. 2) e media pesata sull'inverso della distanza
        dei 4 nodi più vicini (Allegato A, eq. 3).
        """
        coslat = math.cos(math.radians(lat_ed50))
        dist = np.hypot(self.lat - lat_ed50, (self.lon - lon_ed50) * coslat)
        idx = np.argsort(dist)[:4]
        if dist[idx[0]] > 0.1:
            raise ValueError("Il sito è fuori dal reticolo di riferimento NTC")
        if dist[idx[0]] < 1e-9:
            w = np.array([1.0, 0.0, 0.0, 0.0])
        else:
            w = 1.0 / dist[idx]

        tr = min(max(tr, self.tr[0]), self.tr[-1])
        j = int(np.searchsorted(self.tr, tr))
        j = min(max(j, 1), len(self.tr) - 1)
        t1, t2 = self.tr[j - 1], self.tr[j]
        out = {}
        for k, v in self.par.items():
            p1, p2 = v[j - 1][idx], v[j][idx]
            pv = np.exp(np.log(p1) + np.log(p2 / p1) * math.log(tr / t1) / math.log(t2 / t1))
            out[k] = float(np.sum(pv * w) / np.sum(w))
        out["nodi"] = [int(i) for i in self.id[idx]]
        return out

    def pericolosita(self, lat_ed50, lon_ed50, vn, cu) -> dict[str, Pericolosita]:
        res = {}
        for sl in STATI_LIMITE:
            tr = periodo_ritorno(vn, cu, sl)
            p = self.parametri(lat_ed50, lon_ed50, tr)
            res[sl] = Pericolosita(sl, tr, p["ag"], p["F0"], p["Tc"], p["nodi"])
        return res


# --------------------------------------------------------------------------- NTC 2018 §3.2.3.2.1

#: Coefficiente di amplificazione topografica St (NTC 2018 Tab. 3.2.V, valore
#: massimo: per T3 e T4 vale in cresta e si riduce linearmente fino a 1 alla base)
ST_CATEGORIA = {"T1": 1.0, "T2": 1.2, "T3": 1.2, "T4": 1.4}

#: Ss = a - b·F0·ag/g limitato tra min e max (NTC 2018 Tab. 3.2.IV)
_SS = {"A": None, "B": (1.40, 0.40, 1.00, 1.20), "C": (1.70, 0.60, 1.00, 1.50),
       "D": (2.40, 1.50, 0.90, 1.80), "E": (2.00, 1.10, 1.00, 1.60)}
CATEGORIE_SUOLO = list(_SS)


def coefficiente_ss(categoria: str, ag: float, f0: float) -> float:
    """Coefficiente di amplificazione stratigrafica Ss delle NTC 2018."""
    c = _SS[categoria.upper()]
    if c is None:
        return 1.0
    a, b, lo, hi = c
    return min(max(a - b * f0 * ag, lo), hi)
