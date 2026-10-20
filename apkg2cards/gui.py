"""Interface graphique Tkinter."""
import json
import os
import queue
import re
import urllib.error
import urllib.request
import webbrowser
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk

from . import __version__
from .core import ApkgError, convert, list_decks

ALL_DECKS = "(tous les paquets)"
PALETTE = ["#2563eb", "#16a34a", "#dc2626", "#ea580c", "#7c3aed", "#db2777", "#0d9488", "#475569"]
DEFAULT_COLOR = PALETTE[0]

def open_file(path):
    if sys.platform.startswith("win"):
        os.startfile(path)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


class App(ttk.Frame):
    def __init__(self, root):
        super().__init__(root, padding=14)
        self.root = root
        self.q = queue.Queue()
        self.last_pdf = None
        root.title("apkg2cards — flashcards à imprimer")
        root.minsize(520, 0)
        self.grid(sticky="nsew")
        root.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)

        self.apkg = tk.StringVar()
        self.out = tk.StringVar()
        self.deck = tk.StringVar(value=ALL_DECKS)
        self.cols = tk.IntVar(value=2)
        self.rows = tk.IntVar(value=4)
        self.margin = tk.DoubleVar(value=8)
        self.font_size = tk.DoubleVar(value=16)
        self.landscape = tk.BooleanVar(value=False)
        self.flip = tk.StringVar(value="long")
        self.reversed = tk.BooleanVar(value=False)
        self.color = tk.StringVar(value=DEFAULT_COLOR)
        

        r = 0
        ttk.Label(self, text="Paquet Anki (.apkg)").grid(row=r, column=0, sticky="w", pady=3)
        ttk.Entry(self, textvariable=self.apkg).grid(row=r, column=1, sticky="ew", padx=6)
        ttk.Button(self, text="Parcourir…", command=self.pick_apkg).grid(row=r, column=2)

        r += 1
        ttk.Label(self, text="PDF de sortie").grid(row=r, column=0, sticky="w", pady=3)
        ttk.Entry(self, textvariable=self.out).grid(row=r, column=1, sticky="ew", padx=6)
        ttk.Button(self, text="Choisir…", command=self.pick_out).grid(row=r, column=2)

        r += 1
        ttk.Label(self, text="Paquet").grid(row=r, column=0, sticky="w", pady=3)
        self.deck_box = ttk.Combobox(self, textvariable=self.deck, state="readonly",
                                     values=[ALL_DECKS])
        self.deck_box.grid(row=r, column=1, columnspan=2, sticky="ew", padx=6)

        r += 1
        box = ttk.LabelFrame(self, text="Mise en page", padding=10)
        box.grid(row=r, column=0, columnspan=3, sticky="ew", pady=10)
        for i in range(4):
            box.columnconfigure(i, weight=1)

        def spin(label, var, lo, hi, row, col, step=1):
            ttk.Label(box, text=label).grid(row=row, column=col, sticky="w", pady=3)
            ttk.Spinbox(box, from_=lo, to=hi, increment=step, textvariable=var,
                        width=6).grid(row=row, column=col + 1, sticky="w", padx=6)

        spin("Colonnes", self.cols, 1, 6, 0, 0)
        spin("Lignes", self.rows, 1, 8, 0, 2)
        spin("Marge (mm)", self.margin, 0, 30, 1, 0, 1)
        spin("Taille texte max", self.font_size, 6, 40, 1, 2, 1)

        ttk.Checkbutton(box, text="Page en paysage", variable=self.landscape).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=3)
        ttk.Label(box, text="Retournement").grid(row=2, column=2, sticky="w")
        ttk.Combobox(box, textvariable=self.flip, state="readonly", width=8,
                     values=["long", "short"]).grid(row=2, column=3, sticky="w", padx=6)

        ttk.Checkbutton(box, text="Inclure aussi les cartes inversées (doublons recto/verso)",
                        variable=self.reversed).grid(
            row=3, column=0, columnspan=4, sticky="w", pady=3)

        ttk.Label(box, text="Couleur des cartes").grid(row=4, column=0, sticky="w", pady=(6, 3))
        swatches = ttk.Frame(box)
        swatches.grid(row=4, column=1, columnspan=3, sticky="w", pady=(6, 3))
        for hexa in PALETTE:
            sw = tk.Label(swatches, bg=hexa, width=3, relief="ridge", cursor="hand2")
            sw.pack(side="left", padx=2)
            sw.bind("<Button-1>", lambda e, h=hexa: self.set_color(h))
        ttk.Button(swatches, text="Autre…", command=self.pick_color).pack(side="left", padx=(8, 2))
        self.preview = tk.Label(swatches, width=6, relief="sunken", bg=self.color.get())
        self.preview.pack(side="left", padx=4)

        r += 1
        self.btn = ttk.Button(self, text="Générer le PDF", command=self.start)
        self.btn.grid(row=r, column=0, columnspan=3, sticky="ew", ipady=4)

        r += 1
        self.bar = ttk.Progressbar(self, mode="determinate")
        self.bar.grid(row=r, column=0, columnspan=3, sticky="ew", pady=(10, 2))

        r += 1
        self.status = ttk.Label(self, text="Choisis un fichier .apkg pour commencer.",
                                wraplength=480)
        self.status.grid(row=r, column=0, columnspan=3, sticky="w")

        r += 1
        self.open_btn = ttk.Button(self, text="Ouvrir le PDF", command=self.open_pdf,
                                   state="disabled")
        self.open_btn.grid(row=r, column=0, columnspan=3, sticky="ew", pady=(8, 0))

        r += 1
        ttk.Separator(self).grid(row=r, column=0, columnspan=3, sticky="ew", pady=(12, 6))
        r += 1
        ttk.Label(self, text=f"Version {__version__}", foreground="gray").grid(
            row=r, column=0, sticky="w")
        ttk.Button(self, text="Rechercher une mise à jour", command=self.check_update).grid(
            row=r, column=1, columnspan=2, sticky="e")

        ttk.Label(self, foreground="gray", wraplength=480, text=(
            "Impression : recto-verso, retournement sur le bord long (portrait), "
            "échelle 100 %. Fais un test sur une feuille avant le paquet entier."),
        ).grid(row=r + 1, column=0, columnspan=3, sticky="w", pady=(6, 0))

        self.after(100, self.poll)

    # -- sélection de fichiers -------------------------------------------
    def pick_apkg(self):
        p = filedialog.askopenfilename(title="Choisir un paquet Anki",
                                       filetypes=[("Paquet Anki", "*.apkg"), ("Tous", "*.*")])
        if not p:
            return
        self.apkg.set(p)
        self.out.set(os.path.splitext(p)[0] + "_cartes.pdf")
        try:
            self.deck_box["values"] = [ALL_DECKS] + list_decks(p)
            self.deck.set(ALL_DECKS)
            self.set_status("Fichier chargé.")
        except ApkgError as e:
            self.set_status(f"Erreur : {e}")
            messagebox.showerror("Fichier invalide", str(e))

    def set_color(self, hexa):
        self.color.set(hexa)
        self.preview.config(bg=hexa)

    def pick_color(self):
        _, hexa = colorchooser.askcolor(color=self.color.get(), title="Couleur des cartes")
        if hexa:
            self.set_color(hexa)

    def pick_out(self):
        p = filedialog.asksaveasfilename(title="Enregistrer le PDF", defaultextension=".pdf",
                                         filetypes=[("PDF", "*.pdf")])
        if p:
            self.out.set(p)

    def set_status(self, text):
        self.status.config(text=text)

    # -- conversion en tâche de fond -------------------------------------
    def start(self):
        if not self.apkg.get():
            messagebox.showwarning("Fichier manquant", "Choisis d'abord un fichier .apkg.")
            return
        try:
            args = dict(
                apkg=self.apkg.get(), output=self.out.get() or None,
                cols=self.cols.get(), rows=self.rows.get(),
                margin=self.margin.get(), font_size=self.font_size.get(),
                landscape=self.landscape.get(), flip=self.flip.get(),
                include_reversed=self.reversed.get(),
                color=self.color.get(),
                deck=None if self.deck.get() == ALL_DECKS else self.deck.get())
        except tk.TclError:
            messagebox.showwarning("Valeur invalide", "Vérifie les valeurs numériques.")
            return
        self.btn.config(state="disabled")
        self.open_btn.config(state="disabled")
        self.bar.config(value=0)
        self.set_status("Conversion en cours…")

        def work():
            try:
                res = convert(**args, on_progress=lambda d, t: self.q.put(("p", d, t)))
                self.q.put(("ok", res))
            except ApkgError as e:
                self.q.put(("err", str(e)))
            except Exception as e:  # noqa: BLE001
                self.q.put(("err", f"Erreur inattendue : {e}"))

        threading.Thread(target=work, daemon=True).start()

    def check_update(self):
        """Cherche une nouvelle version sur GitHub."""
        self.set_status("Recherche de mise à jour…")

        def parse(v):
            return tuple(int(x) for x in re.findall(r"\d+", v)[:3])

        def work():
            link = None
            try:
                req = urllib.request.Request(
                    "https://api.github.com/repos/Loeix/apkg2cards/releases/latest",
                    headers={"User-Agent": "apkg2cards", "Accept": "application/vnd.github+json"})
                with urllib.request.urlopen(req, timeout=10) as r:
                    data = json.loads(r.read().decode("utf-8"))
                latest = data.get("tag_name", "")
                if parse(latest) > parse(__version__):
                    link = data.get("html_url")
                    msg = (f"Nouvelle version disponible : {latest}\n"
                           f"Version installée : v{__version__}")
                else:
                    msg = f"Tu as la dernière version (v{__version__})."
            except urllib.error.HTTPError as e:
                msg = ("Aucune version publiée sur GitHub pour le moment."
                       if e.code == 404 else f"Erreur GitHub (code {e.code}).")
            except Exception as e:  # noqa: BLE001
                msg = f"Impossible de vérifier les mises à jour.\n\nDétail : {e}"
            self.q.put(("update", msg, link))

        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                if msg[0] == "p":
                    self.bar.config(maximum=msg[2], value=msg[1])
                elif msg[0] == "ok":
                    r = msg[1]
                    self.last_pdf = r["output"]
                    txt = f"{r['cards']} cartes → {r['pages']} pages (recto-verso)."
                    if r["overflow"]:
                        txt += f" {r['overflow']} face(s) très longue(s) : texte fortement réduit."
                    self.set_status(txt)
                    self.btn.config(state="normal")
                    self.open_btn.config(state="normal")
                elif msg[0] == "update":
                    self.set_status(msg[1].split("\n")[0])
                    if msg[2]:
                        if messagebox.askyesno("Mise à jour", msg[1] + "\n\nOuvrir la page de téléchargement ?"):
                            webbrowser.open(msg[2])
                    else:
                        messagebox.showinfo("Mise à jour", msg[1])
                else:
                    self.set_status(f"Erreur : {msg[1]}")
                    self.btn.config(state="normal")
                    messagebox.showerror("Échec", msg[1])
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def open_pdf(self):
        if self.last_pdf and os.path.exists(self.last_pdf):
            open_file(self.last_pdf)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
