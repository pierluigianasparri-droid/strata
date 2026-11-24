"""Interfaccia grafica di RSL Tools (tkinter)."""
from __future__ import annotations

import json
import os
import threading
import tkinter as tk
import traceback
from tkinter import filedialog, messagebox, ttk

from . import __version__, ntc, relazione, strata_io
from .regolarizzazione import regolarizza

SL = ntc.STATI_LIMITE


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"RSL Tools {__version__} - regolarizzazione e relazione RSL")
        self.geometry("980x760")
        self.v = {}
        self._crea()

    # ------------------------------------------------------------------ UI
    def _var(self, k, val=""):
        self.v[k] = tk.StringVar(value=val)
        return self.v[k]

    def _riga_file(self, parent, r, etichetta, chiave, cartella=False, tipi=None):
        ttk.Label(parent, text=etichetta).grid(row=r, column=0, sticky="w", padx=4, pady=2)
        ttk.Entry(parent, textvariable=self._var(chiave), width=80).grid(
            row=r, column=1, sticky="we", padx=4)

        def scegli():
            if cartella:
                p = filedialog.askdirectory()
            else:
                p = filedialog.askopenfilename(filetypes=tipi or [("Tutti", "*.*")])
            if p:
                self.v[chiave].set(p)
        ttk.Button(parent, text="...", width=3, command=scegli).grid(row=r, column=2)

    def _crea(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=6, pady=6)

        # --- Dati
        f = ttk.Frame(nb)
        nb.add(f, text="Dati")
        f.columnconfigure(1, weight=1)
        r = 0
        ttk.Label(f, text="Progetto Strata unico con tutti gli stati limite (.json)",
                  font=("", 10, "bold")).grid(row=r, column=0, columnspan=3, sticky="w", pady=(6, 2))
        r += 1
        self._riga_file(f, r, "Tutti gli SL", "file_unico",
                        tipi=[("Strata", "*.json"), ("Tutti", "*.*")])
        r += 1
        ttk.Label(f, text="Gli accelerogrammi sono divisi per stato limite in base a SLO/SLD/"
                  "SLV/SLC nel nome del file o della sua cartella.",
                  foreground="#555").grid(row=r, column=0, columnspan=3, sticky="w", padx=4)
        r += 1
        ttk.Label(f, text="oppure un progetto per stato limite (.json) o spettri esportati (.csv)",
                  font=("", 10, "bold")).grid(row=r, column=0, columnspan=3, sticky="w", pady=(6, 2))
        r += 1
        for sl in SL:
            self._riga_file(f, r, sl, f"file_{sl}",
                            tipi=[("Strata", "*.json *.csv"), ("Tutti", "*.*")])
            r += 1

        ttk.Label(f, text="Sito e opera", font=("", 10, "bold")).grid(
            row=r, column=0, columnspan=3, sticky="w", pady=(10, 2))
        r += 1
        g = ttk.Frame(f)
        g.grid(row=r, column=0, columnspan=3, sticky="w")
        ttk.Label(g, text="Latitudine").grid(row=0, column=0, padx=4)
        ttk.Entry(g, textvariable=self._var("lat"), width=14).grid(row=0, column=1)
        ttk.Label(g, text="Longitudine").grid(row=0, column=2, padx=4)
        ttk.Entry(g, textvariable=self._var("lon"), width=14).grid(row=0, column=3)
        ttk.Label(g, text="Datum").grid(row=0, column=4, padx=4)
        ttk.Combobox(g, textvariable=self._var("datum", "WGS84"), values=["WGS84", "ED50"],
                     width=8, state="readonly").grid(row=0, column=5)
        ttk.Label(g, text="VN [anni]").grid(row=1, column=0, padx=4, pady=4)
        ttk.Entry(g, textvariable=self._var("vn", "50"), width=8).grid(row=1, column=1, sticky="w")
        ttk.Label(g, text="Classe d'uso").grid(row=1, column=2, padx=4)
        ttk.Combobox(g, textvariable=self._var("classe", "II"), values=list(ntc.CU_CLASSE),
                     width=6, state="readonly").grid(row=1, column=3, sticky="w")
        ttk.Label(g, text="Categoria di suolo").grid(row=2, column=0, padx=4, pady=4)
        ttk.Combobox(g, textvariable=self._var("cat_suolo", "B"), values=ntc.CATEGORIE_SUOLO,
                     width=6, state="readonly").grid(row=2, column=1, sticky="w")
        ttk.Label(g, text="Categoria topografica").grid(row=2, column=2, padx=4)
        ttk.Combobox(g, textvariable=self._var("cat_topo", "T1"), values=list(ntc.ST_CATEGORIA),
                     width=6, state="readonly").grid(row=2, column=3, sticky="w")
        ttk.Label(g, text="St").grid(row=2, column=4, padx=4)
        ttk.Entry(g, textvariable=self._var("st", "1.0"), width=8).grid(row=2, column=5,
                                                                         sticky="w")
        self.v["cat_topo"].trace_add(
            "write", lambda *_: self.v["st"].set(
                f"{ntc.ST_CATEGORIA.get(self.v['cat_topo'].get(), 1.0):.1f}"))
        ttk.Label(g, text="(per il capitolo \"Analisi dei risultati\": Ss NTC dalla categoria "
                  "di suolo, St modificabile per T3/T4 a quota intermedia)",
                  foreground="#555").grid(row=3, column=0, columnspan=6, sticky="w", padx=4)
        r += 1

        ttk.Label(f, text="Coppie distanza-magnitudo (per la tabella della disaggregazione)",
                  font=("", 10, "bold")).grid(row=r, column=0, columnspan=3, sticky="w",
                                              pady=(10, 2))
        r += 1
        g = ttk.Frame(f)
        g.grid(row=r, column=0, columnspan=3, sticky="w")
        ttk.Label(g, text="Distanza (km)").grid(row=0, column=1)
        ttk.Label(g, text="Magnitudo").grid(row=0, column=2)
        for i, sl in enumerate(SL, start=1):
            ttk.Label(g, text=sl).grid(row=i, column=0, padx=4)
            ttk.Entry(g, textvariable=self._var(f"dist_{sl}"), width=12).grid(row=i, column=1)
            ttk.Entry(g, textvariable=self._var(f"mag_{sl}"), width=12).grid(row=i, column=2)
        r += 1

        ttk.Label(f, text="Relazione", font=("", 10, "bold")).grid(
            row=r, column=0, columnspan=3, sticky="w", pady=(10, 2))
        r += 1
        self._riga_file(f, r, "Modello Word", "modello", tipi=[("Word", "*.docx")])
        r += 1
        g = ttk.Frame(f)
        g.grid(row=r, column=0, columnspan=3, sticky="w")
        ttk.Label(g, text="Carattere").grid(row=0, column=0, padx=4, sticky="w")
        try:
            from tkinter import font as tkfont
            famiglie = sorted({x for x in tkfont.families(self) if not x.startswith("@")})
        except Exception:  # noqa: BLE001
            famiglie = []
        ttk.Combobox(g, textvariable=self._var("carattere", ""),
                     values=["", *famiglie], width=28).grid(row=0, column=1, sticky="w")
        ttk.Label(g, text="Dimensione testo (pt)").grid(row=0, column=2, padx=(12, 4))
        ttk.Entry(g, textvariable=self._var("dimensione", ""), width=6).grid(row=0, column=3)
        ttk.Label(g, text="(vuoto = come nel modello Word)", foreground="#555").grid(
            row=0, column=4, padx=6)
        r += 1
        self._riga_file(f, r, "Immagini disaggregazione", "img_disagg", cartella=True)
        r += 1
        self._riga_file(f, r, "Immagini REXELite", "img_rexel", cartella=True)
        r += 1
        ttk.Label(f, text="Campi liberi\n(CHIAVE = valore)").grid(row=r, column=0, sticky="nw",
                                                                  padx=4)
        self.campi = tk.Text(f, height=5, width=60)
        self.campi.insert("1.0", "OGGETTO = \nINDAGINI = Re.Mi. e HVSR\nF0_HVSR = \n")
        self.campi.grid(row=r, column=1, sticky="we", padx=4, pady=2)
        r += 1

        b = ttk.Frame(f)
        b.grid(row=r, column=0, columnspan=3, pady=10)
        ttk.Button(b, text="Apri impostazioni...", command=self.apri).pack(side="left", padx=4)
        ttk.Button(b, text="Salva impostazioni...", command=self.salva).pack(side="left", padx=4)
        ttk.Button(b, text="Calcola regolarizzazione", command=self.calcola).pack(side="left",
                                                                                padx=12)
        ttk.Button(b, text="Genera relazione Word...", command=self.genera).pack(side="left",
                                                                                 padx=4)

        # --- Risultati
        f2 = ttk.Frame(nb)
        nb.add(f2, text="Risultati")
        self.out = tk.Text(f2, font=("Consolas", 10))
        self.out.pack(fill="both", expand=True)
        self.nb = nb

    # ------------------------------------------------------------------ logica
    def log(self, *testo):
        self.out.insert("end", " ".join(str(t) for t in testo) + "\n")
        self.out.see("end")

    def _campi(self):
        d = {}
        for riga in self.campi.get("1.0", "end").splitlines():
            if "=" in riga:
                k, v = riga.split("=", 1)
                if k.strip():
                    d[k.strip().upper()] = v.strip()
        return d

    def _num(self, k, nome):
        try:
            return float(self.v[k].get().replace(",", "."))
        except ValueError:
            raise ValueError(f"Valore non valido per {nome}: '{self.v[k].get()}'") from None

    def _elabora(self):
        lat, lon = self._num("lat", "latitudine"), self._num("lon", "longitudine")
        if self.v["datum"].get() == "WGS84":
            lat_w, lon_w = lat, lon
            lat_e, lon_e = ntc.wgs84_to_ed50(lat, lon)
        else:
            lat_w = lon_w = None
            lat_e, lon_e = lat, lon
        vn = self._num("vn", "VN")
        classe = self.v["classe"].get()
        cu = ntc.CU_CLASSE[classe]
        per = ntc.Reticolo().pericolosita(lat_e, lon_e, vn, cu)

        ris, reg = {}, {}
        unico = self.v["file_unico"].get().strip()
        if unico:
            ris, esclusi = strata_io.dividi_per_stato_limite(strata_io.leggi_progetto(unico))
            for sl in SL:
                if sl in ris:
                    self.log(f"{sl}: {len(ris[sl].nomi_moti)} accelerogrammi dal progetto unico")
            if esclusi:
                self.log("Accelerogrammi senza stato limite nel percorso (esclusi): "
                         + ", ".join(os.path.basename(e) for e in esclusi))
        for sl in SL:
            p = self.v[f"file_{sl}"].get().strip()
            if p:
                ris[sl] = strata_io.leggi(p)
        ris = {sl: ris[sl] for sl in SL if sl in ris}
        for sl, r in ris.items():
            reg[sl] = regolarizza(r.periodi, r.media, per[sl].ag, r.smorzamento)
        if not ris:
            raise ValueError("Indica il progetto Strata unico o almeno un progetto per stato limite")
        mr = {sl: (self.v[f"dist_{sl}"].get(), self.v[f"mag_{sl}"].get()) for sl in SL}
        st = self._num("st", "St")
        dim = self._num("dimensione", "dimensione del testo") if self.v["dimensione"].get().strip() \
            else None
        return relazione.DatiRelazione(
            vn, classe, cu, lat_w, lon_w, lat_e, lon_e, per, ris, reg, mr,
            self.v["img_disagg"].get(), self.v["img_rexel"].get(), self._campi(),
            self.v["cat_suolo"].get(), self.v["cat_topo"].get(), st,
            self.v["carattere"].get().strip(), dim)

    def _stampa(self, d):
        self.log(f"Sito ED50: {d.lat_ed50:.6f}, {d.lon_ed50:.6f}  VN={d.vn:g}  "
                 f"classe {d.classe_uso} (CU={d.cu})")
        self.log(f"{'SL':4} {'TR':>6} {'ag':>7} {'F0':>6} {'Tc*':>6} | {'Amax':>6} {'S':>5} "
                 f"{'F0':>5} {'TB':>5} {'TC':>5} {'TD':>5}  moti")
        for sl in SL:
            p = d.pericolosita[sl]
            riga = f"{sl:4} {p.tr:6.0f} {p.ag:7.3f} {p.f0:6.3f} {p.tc_star:6.3f} |"
            if sl in d.regolarizzati:
                g = d.regolarizzati[sl]
                riga += (f" {g.amax:6.3f} {g.S:5.2f} {g.F0:5.2f} {g.TB:5.2f} {g.TC:5.2f} "
                         f"{g.TD:5.2f}  {len(d.risultati[sl].nomi_moti)}")
            self.log(riga)
        self.log("")
        self.log(f"Categoria di suolo {d.categoria_suolo}, categoria topografica "
                 f"{d.categoria_topografica} (St = {d.st:g})")
        for sl in ("SLV", "SLD"):
            if sl in d.regolarizzati:
                v = relazione.valori_confronto(d, sl)
                self.log(f"{sl}: AMAX NTC = {v['ag']:.3f} x {v['ss_ntc']:.2f} x {v['st']:.2f} = "
                         f"{v['amax_ntc']:.3f}   AMAX RSL = {v['ag']:.3f} x {v['ss_rsl']:.2f} x "
                         f"{v['st']:.2f} = {v['amax_rsl']:.3f}")
        self.log("")

    def calcola(self):
        self.nb.select(1)
        try:
            self._stampa(self._elabora())
        except Exception as e:  # noqa: BLE001
            self.log("ERRORE:", e)
            messagebox.showerror("RSL Tools", str(e))

    def genera(self):
        try:
            d = self._elabora()
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("RSL Tools", str(e))
            return
        uscita = filedialog.asksaveasfilename(defaultextension=".docx",
                                              filetypes=[("Word", "*.docx")])
        if not uscita:
            return
        self.nb.select(1)
        self._stampa(d)
        self.log("Generazione della relazione in corso...")

        def lavoro():
            try:
                relazione.genera(d, uscita, self.v["modello"].get() or None,
                                 log=lambda t: self.after(0, self.log, t))
                self.after(0, self.log, f"Relazione salvata: {uscita}\n"
                           "In Word premi F9 sull'indice per aggiornarlo.")
            except Exception:  # noqa: BLE001
                self.after(0, self.log, traceback.format_exc())
                return
            if os.name == "nt":
                # os.startfile vuole il percorso con le barre di Windows
                # (necessario per le cartelle di rete \\NAS\...)
                try:
                    os.startfile(os.path.normpath(uscita))  # noqa: S606
                except OSError as e:
                    self.after(0, self.log, f"Relazione salvata ma non aperta automaticamente: {e}")
        threading.Thread(target=lavoro, daemon=True).start()

    def salva(self):
        p = filedialog.asksaveasfilename(defaultextension=".rsl.json",
                                         filetypes=[("Impostazioni RSL", "*.rsl.json")])
        if p:
            d = {k: v.get() for k, v in self.v.items()}
            d["campi"] = self.campi.get("1.0", "end")
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(d, fh, indent=2, ensure_ascii=False)

    def apri(self):
        p = filedialog.askopenfilename(filetypes=[("Impostazioni RSL", "*.rsl.json *.json")])
        if not p:
            return
        with open(p, encoding="utf-8") as fh:
            d = json.load(fh)
        for k, v in d.items():
            if k == "campi":
                self.campi.delete("1.0", "end")
                self.campi.insert("1.0", v)
            elif k in self.v:
                self.v[k].set(v)


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
