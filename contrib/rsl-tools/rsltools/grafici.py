"""Grafici per la relazione (PNG ad alta risoluzione)."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

DPI = 200
GRIGI = "#9aa0a6"
MEDIA = "#c0392b"
REG = "#1f4e79"
NTC_A = "#2e7d32"


def _stile(ax, titolo, xlabel="Periodo T [s]", ylabel="Sa [g]"):
    ax.set_title(titolo, fontsize=11)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(True, which="both", color="#e0e0e0", linewidth=0.6)
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)


def spettri_moti(path, sl, T, spettri, nomi, media):
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    cmap = plt.get_cmap("tab10")
    for i, (s, n) in enumerate(zip(spettri, nomi)):
        ax.plot(T, s, color=cmap(i % 10), linewidth=0.9, alpha=0.8, label=n)
    ax.plot(T, media, color="black", linewidth=2.2, label="MEDIA")
    _stile(ax, f"Spettri di risposta in accelerazione a piano campagna - {sl}")
    ax.legend(fontsize=7, ncol=2, frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=DPI)
    plt.close(fig)


def spettro_medio(path, sl, T, media):
    fig, ax = plt.subplots(figsize=(7.5, 4.0))
    ax.plot(T, media, color=MEDIA, linewidth=2.0, label="Spettro medio RSL")
    _stile(ax, f"Spettro medio di risposta - {sl}")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=DPI)
    plt.close(fig)


def regolarizzazione(path, sl, T, media, reg, T_ntc=None, sa_ntc=None):
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    ax.plot(T, media, color=MEDIA, linewidth=1.6, label="Spettro medio RSL")
    tr, sr = reg.punti(t_max=float(max(T)))
    ax.plot(tr, sr, color=REG, linewidth=2.2, label="Spettro regolarizzato")
    if T_ntc is not None:
        ax.plot(T_ntc, sa_ntc, color=NTC_A, linewidth=1.2, linestyle="--",
                label="NTC 2018 suolo A")
    for t, lab in ((reg.TB, "TB"), (reg.TC, "TC"), (reg.TD, "TD")):
        ax.axvline(t, color=GRIGI, linewidth=0.8, linestyle=":")
        ax.annotate(lab, (t, 0), xytext=(2, 4), textcoords="offset points", fontsize=8,
                    color="#555")
    _stile(ax, f"Regolarizzazione dello spettro di risposta - {sl}")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=DPI)
    plt.close(fig)


def curve_decadimento(path, tipi):
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.5, 3.6))
    visti = set()
    cmap = plt.get_cmap("tab10")
    k = 0
    for t in tipi:
        chiave = (t.modulo_nome, t.smorzamento_nome, tuple(t.g_g0))
        if chiave in visti or not t.deformazioni:
            continue
        visti.add(chiave)
        c = cmap(k % 10)
        k += 1
        a1.semilogx(t.deformazioni, t.g_g0, color=c, label=t.modulo_nome)
        if t.deformazioni_d:
            a2.semilogx(t.deformazioni_d, t.d, color=c, label=t.smorzamento_nome)
    a1.set_title("Curve G/G0")
    a1.set_xlabel("Deformazione di taglio γ [%]")
    a1.set_ylabel("G/G0")
    a2.set_title("Curve di smorzamento D")
    a2.set_xlabel("Deformazione di taglio γ [%]")
    a2.set_ylabel("D [%]")
    for a in (a1, a2):
        a.grid(True, which="both", color="#e0e0e0", linewidth=0.6)
        a.legend(fontsize=7, frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=DPI)
    plt.close(fig)


def profilo_vs(path, strati, bedrock):
    fig, ax = plt.subplots(figsize=(3.6, 5.0))
    z, v = [], []
    for s in strati:
        z += [s.profondita, s.profondita + s.spessore]
        v += [s.vs, s.vs]
    if bedrock is not None:
        zb = bedrock.profondita
        z += [zb, zb * 1.1 + 5]
        v += [bedrock.vs, bedrock.vs]
    ax.plot(v, z, color=REG, linewidth=2)
    ax.invert_yaxis()
    ax.set_xlabel("Vs [m/s]")
    ax.set_ylabel("Profondità [m]")
    ax.set_title("Profilo di Vs")
    ax.grid(True, color="#e0e0e0", linewidth=0.6)
    ax.set_xlim(left=0)
    fig.tight_layout()
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
