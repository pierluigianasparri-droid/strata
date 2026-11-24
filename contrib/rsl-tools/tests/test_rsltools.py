"""Test di base (eseguibili con: python -m pytest contrib/rsl-tools/tests)."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rsltools import ntc, strata_io  # noqa: E402
from rsltools.regolarizzazione import SpettroRegolarizzato, regolarizza  # noqa: E402


def test_periodi_ritorno():
    trs = [round(ntc.periodo_ritorno(50, 1.5, sl)) for sl in ntc.STATI_LIMITE]
    assert trs == [45, 75, 712, 1462]


def test_wgs84_ed50():
    lat, lon = ntc.wgs84_to_ed50(45.414994, 11.169154)
    assert abs(lat - 45.415911) < 2e-6 and abs(lon - 11.170167) < 2e-6


def test_reticolo_nodo_esatto():
    r = ntc.Reticolo()
    i = 1234
    lat, lon = r.lat[i], r.lon[i]
    p = r.parametri(lat, lon, 475.0)
    j = list(r.tr).index(475)
    assert abs(p["ag"] - r.par["ag"][j][i]) < 1e-9


def test_regolarizzazione_spettro_ntc():
    # Su uno spettro già in forma NTC il metodo restituisce parametri vicini
    # (non identici: le medie su 0.5-1.5 TA includono parte del ramo crescente)
    ref = SpettroRegolarizzato(ag=0.15, amax=0.30, S=2.0, F0=2.5, TB=0.15, TC=0.45,
                               TD=2.2, eta=1.0, TA=0, SAm=0, TV=0, SVm=0)
    T = np.logspace(-2, np.log10(4), 400)
    reg = regolarizza(T, ref.sa(T), ag=0.15)
    assert abs(reg.TC - 0.45) / 0.45 < 0.15
    assert abs(reg.amax - 0.30) / 0.30 < 0.05
    assert abs(reg.TB - reg.TC / 3) < 1e-12
    assert abs(reg.TD - 2.2) < 1e-9


def test_csv(tmp_path):
    T = np.logspace(-2, 0, 5)
    p = tmp_path / "spettri.csv"
    with open(p, "w") as fh:
        fh.write("# Strata Output: Location -- Surface -- Response Spectrum\n# Project:x\n")
        fh.write("# Period (s),M-a,M-b,Median,Log Stdev,\n")
        for t in T:
            fh.write(f"{t},{0.1},{0.4},{0.2},{0.1}\n")
    r = strata_io.leggi_csv(str(p))
    assert r.nomi_moti == ["a", "b"]
    assert np.allclose(r.media, 0.2)  # media geometrica di 0.1 e 0.4


def test_coefficiente_ss_ntc():
    from rsltools import ntc
    assert ntc.coefficiente_ss("A", 0.3, 2.5) == 1.0
    assert abs(ntc.coefficiente_ss("B", 0.178, 2.4) - 1.20) < 1e-9  # limite superiore
    assert abs(ntc.coefficiente_ss("C", 0.25, 2.5) - (1.70 - 0.60 * 2.5 * 0.25)) < 1e-9
    assert ntc.coefficiente_ss("D", 0.5, 2.6) == 0.90  # limite inferiore
    assert ntc.ST_CATEGORIA["T2"] == 1.2


def test_legenda_testo_utente():
    from rsltools import relazione
    nomi = [k for k, _ in relazione.LEGENDA]
    assert nomi == ["Amax", "S", "F0", "TB", "Tc", "TD"]


def test_applica_font():
    from docx import Document
    from rsltools import relazione
    doc = Document()
    p = doc.add_paragraph()
    r = p.add_run("testo")
    r.font.name = "Cambria"
    relazione.applica_font(doc, "Arial", 10)
    assert doc.styles["Normal"].font.name == "Arial"
    assert doc.styles["Normal"].font.size.pt == 10
    assert r.font.name == "Arial"
