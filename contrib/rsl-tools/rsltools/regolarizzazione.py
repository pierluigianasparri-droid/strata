"""Regolarizzazione dello spettro di risposta in forma NTC 2018.

Procedura dell'Appendice 1 dell'Ordinanza n. 55 del 24/04/2018 del
Commissario straordinario per la ricostruzione (sisma 2016):

a) TA = periodo del massimo di SA; SA,m = media di SA tra 0.5 TA e 1.5 TA
b) SV = SA * T / 2pi; TV = periodo del massimo di SV;
   SV,m = media di SV tra 0.8 TV e 1.2 TV
c) TC = 2pi SV,m / SA,m;  TB = TC / 3;  TD = 4 ag/g + 1.6
d) amax per estrapolazione lineare dal primo punto (T = 0.01 s):
   amax = (Se(0.01)/SA,m - 0.01/TB) * SA,m / (1 - 0.01/TB)
e) S = amax / ag;  F0 = SA,m / (amax * eta)
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass
class SpettroRegolarizzato:
    ag: float
    amax: float
    S: float
    F0: float
    TB: float
    TC: float
    TD: float
    eta: float
    TA: float
    SAm: float
    TV: float
    SVm: float

    def sa(self, T):
        """Ordinate dello spettro elastico NTC 2018 (eq. 3.2.2)."""
        T = np.asarray(T, float)
        plateau = self.amax * self.eta * self.F0
        out = np.empty_like(T)
        m1 = T < self.TB
        out[m1] = plateau * (T[m1] / self.TB + (1 - T[m1] / self.TB) / (self.eta * self.F0))
        m2 = (T >= self.TB) & (T < self.TC)
        out[m2] = plateau
        m3 = (T >= self.TC) & (T < self.TD)
        out[m3] = plateau * self.TC / T[m3]
        m4 = T >= self.TD
        out[m4] = plateau * self.TC * self.TD / T[m4] ** 2
        return out

    def punti(self, t_max: float = 4.0, n_tratto: int = 199):
        """Punti dello spettro come nelle relazioni di regolarizzazione:
        0, TB, poi n punti tra TC e TD e n punti tra TD e t_max."""
        T = np.concatenate((
            [0.0, self.TB],
            np.linspace(self.TC, self.TD, n_tratto),
            np.linspace(self.TD, t_max, n_tratto),
        ))
        return T, self.sa(T)


def _media(T, y, a, b):
    tt = np.concatenate(([a], T[(T > a) & (T < b)], [b]))
    yy = np.interp(tt, T, y)
    return float(np.trapezoid(yy, tt) / (b - a))


def regolarizza(T, Sa, ag: float, smorzamento: float = 5.0,
                decimali_ag: int | None = 3) -> SpettroRegolarizzato:
    """Regolarizza lo spettro (T [s], Sa [g]) dato ag [g] su suolo A.

    ``decimali_ag`` arrotonda ag come viene riportato dalle NTC (3 decimali),
    così S e TD coincidono con quelli dei programmi commerciali.
    """
    T = np.asarray(T, float)
    Sa = np.asarray(Sa, float)
    order = np.argsort(T)
    T, Sa = T[order], Sa[order]
    if decimali_ag is not None:
        ag = round(ag, decimali_ag)

    TA = float(T[np.argmax(Sa)])
    SAm = _media(T, Sa, 0.5 * TA, 1.5 * TA)

    Sv = Sa * T / (2 * math.pi)
    TV = float(T[np.argmax(Sv)])
    SVm = _media(T, Sv, 0.8 * TV, 1.2 * TV)

    TC = 2 * math.pi * SVm / SAm
    TB = TC / 3
    TD = 4.0 * ag + 1.6

    t0 = 0.01
    se0 = float(np.interp(t0, T, Sa))
    r = t0 / TB
    amax = (se0 / SAm - r) * (SAm / (1 - r))

    eta = max(math.sqrt(10.0 / (5.0 + smorzamento)), 0.55)
    F0 = SAm / (amax * eta)
    return SpettroRegolarizzato(ag=ag, amax=amax, S=amax / ag, F0=F0, TB=TB, TC=TC,
                                TD=TD, eta=eta, TA=TA, SAm=SAm, TV=TV, SVm=SVm)


def spettro_ntc_suolo_a(ag, f0, tc_star, T, smorzamento=5.0):
    """Spettro elastico NTC 2018 su suolo A, categoria T1 (riferimento)."""
    eta = max(math.sqrt(10.0 / (5.0 + smorzamento)), 0.55)
    TC = tc_star
    s = SpettroRegolarizzato(ag=ag, amax=ag, S=1.0, F0=f0, TB=TC / 3, TC=TC,
                             TD=4.0 * ag + 1.6, eta=eta, TA=0, SAm=0, TV=0, SVm=0)
    return s.sa(T)
