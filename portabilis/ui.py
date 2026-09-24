# -*- coding: utf-8 -*-
"""
Portabilis - Interface grafica (tkinter, empacotada com PyInstaller).

Visual moderno dark, fluxo em 3 etapas:
  1. DETECTAR  - escolhe fontes (a) registro Uninstall e (b) varredura de .exe
  2. ANALISAR  - mostra estrategia recomendada (SANDBOX/LAUNCHER/MANUAL),
                 riscos e artefatos de trial/licenca + relatorio de viabilidade
  3. CLONAR    - escolha do formato de saida: (a) PASTA (b) SFX (c) ZIP
                 + opcoes de bypass de contadores de uso/trial
"""
import os
import sys
import threading
import traceback

import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scan          # noqa: E402
import clone         # noqa: E402

APP_TITLE = "Portabilis 1.0 MVP"

# ------------------------------------------------------------- tema
BG      = "#0f1420"   # fundo geral
BG2     = "#161d2e"   # cards
BG3     = "#1e2740"   # inputs/hover
FG      = "#e8ecf5"
MUTED   = "#8b96b3"
ACCENT  = "#4f8cff"
ACCENT2 = "#7c5cff"
OK      = "#2ecc8f"
WARN    = "#f5b942"
ERR     = "#ff5c7a"

FONT      = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_H1   = ("Segoe UI", 17, "bold")
FONT_H2   = ("Segoe UI", 12, "bold")
FONT_MONO = ("Consolas", 9)


class Card(ttk.Frame):
    def __init__(self, master, title="", **kw):
        super().__init__(master, style="Card.TFrame", **kw)
        self.pack(fill="x", padx=14, pady=7)
        if title:
            ttk.Label(self, text=title, style="CardTitle.TLabel")\
                .pack(anchor="w", padx=14, pady=(12, 2))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1024x720")
        self.minsize(880, 620)
        self.configure(bg=BG)
        self.apps = []
        self.selected = None
        self._busy = False
        self._setup_styles()
        self._build()
        self.after(300, lambda: self.do_scan())

    # ------------------------------------------------------------ estilos
    def _setup_styles(self):
        s = ttk.Style(self)
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        s.configure(".", background=BG, foreground=FG, font=FONT,
                    borderwidth=0, focuscolor=ACCENT)
        s.configure("Toplevel", background=BG)
        s.configure("Card.TFrame", background=BG2)
        s.configure("CardTitle.TLabel", background=BG2, foreground=ACCENT,
                    font=FONT_H2)
        s.configure("TLabel", background=BG, foreground=FG)
        s.configure("Muted.TLabel", background=BG, foreground=MUTED, font=FONT)
        s.configure("H1.TLabel", background=BG, foreground=FG, font=FONT_H1)
        s.configure("TCheckbutton", background=BG2, foreground=FG,
                    activebackground=BG2, activeforeground=FG)
        s.map("TCheckbutton", background=[("active", BG2)])
        s.configure("TNotebook", background=BG, tabmargins=(14, 8, 14, 0))
        s.configure("TNotebook.Tab", background=BG3, foreground=MUTED,
                    padding=(18, 8), font=FONT_BOLD)
        s.map("TNotebook.Tab", background=[("selected", ACCENT)],
              foreground=[("selected", "#ffffff")])
        s.configure("Treeview", background=BG3, fieldbackground=BG3,
                    foreground=FG, rowheight=30, font=FONT)
        s.configure("Treeview.Heading", background=BG2, foreground=MUTED,
                    font=FONT_BOLD, relief="flat")
        s.map("Treeview", background=[("selected", ACCENT)],
              foreground=[("selected", "#ffffff")])
        s.configure("TCombobox", fieldbackground=BG3, background=BG3,
                    foreground=FG, arrowcolor=FG)
        s.configure("Horizontal.TProgressbar", troughcolor=BG3,
                    background=ACCENT, lightcolor=ACCENT, thickness=8)
        s.configure("Accent.TButton", background=ACCENT, foreground="#ffffff",
                    font=FONT_BOLD, padding=(16, 9))
        s.map("Accent.TButton", background=[("active", "#3a76e8"),
                                            ("disabled", BG3)],
              foreground=[("disabled", MUTED)])
        s.configure("Ghost.TButton", background=BG3, foreground=FG,
                    padding=(14, 9))
        s.map("Ghost.TButton", background=[("active", "#2a3555")])

    def _btn(self, parent, text, cmd, accent=True):
        b = tk.Button(parent, text=text, command=cmd, bd=0, cursor="hand2",
                      font=FONT_BOLD, padx=16, pady=8,
                      bg=ACCENT if accent else BG3,
                      fg="#ffffff" if accent else FG,
                      activebackground=ACCENT2 if accent else "#2a3555",
                      activeforeground="#ffffff")
        return b

    # ------------------------------------------------------------ layout
    def _build(self):
        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", padx=18, pady=(16, 6))
        logo = tk.Canvas(header, width=40, height=40, bg=BG, highlightthickness=0)
        logo.pack(side="left", padx=(0, 12))
        logo.create_oval(3, 3, 37, 37, fill=ACCENT, outline=ACCENT2, width=3)
        logo.create_text(20, 20, text="P", fill="#fff", font=("Segoe UI", 17, "bold"))
        tbox = tk.Frame(header, bg=BG)
        tbox.pack(side="left")
        tk.Label(tbox, text="Portabilis", bg=BG, fg=FG, font=FONT_H1).pack(anchor="w")
        tk.Label(tbox, text="Clone programas instalados e execute-os como portaveis",
                 bg=BG, fg=MUTED, font=FONT).pack(anchor="w")
        self.status_var = tk.StringVar(value="Pronto")
        tk.Label(header, textvariable=self.status_var, bg=BG, fg=OK,
                 font=FONT_BOLD).pack(side="right")

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=14, pady=(6, 0))

        # ---- aba 1: deteccao ----------------------------------------
        tab1 = tk.Frame(nb, bg=BG); nb.add(tab1, text="  1 · Detectar  ")
        card = Card(tab1, "Fontes de deteccao (item 8)")
        self.inc_reg = tk.BooleanVar(value=True)
        self.inc_file = tk.BooleanVar(value=True)
        for var, txt in ((self.inc_reg,
                          "(a) Registro — HKLM/HKCU\\...\\CurrentVersion\\Uninstall "
                          "(mesma fonte do Painel de Controle)"),
                         (self.inc_file,
                          "(b) Varredura de .exe em pastas comuns "
                          "(Program Files, Desktop, Downloads, C:\\Apps...)")):
            tk.Checkbutton(card, text=txt, variable=var, bg=BG2, fg=FG,
                           selectcolor=BG3, activebackground=BG2,
                           activeforeground=FG, font=FONT, anchor="w")\
                .pack(fill="x", padx=14, pady=3)
            card.columnconfigure(0, weight=1)
        row = tk.Frame(card, bg=BG2); row.pack(fill="x", padx=14, pady=10)
        self._btn(row, "Escanear programas", lambda: self.do_scan()).pack(side="left")
        self.progress = ttk.Progressbar(card, mode="indeterminate",
                                        style="Horizontal.TProgressbar")
        self.progress.pack(fill="x", padx=14, pady=(0, 12))

        cols = ("name", "version", "publisher", "source", "strategy", "size")
        grid_wrap = tk.Frame(tab1, bg=BG); grid_wrap.pack(fill="both", expand=True,
                                                          padx=14, pady=(0, 4))
        self.tree = ttk.Treeview(grid_wrap, columns=cols, show="headings",
                                 selectmode="browse")
        heads = {"name": "Programa", "version": "Versao", "publisher": "Publicador",
                 "source": "Origem", "strategy": "Estrategia", "size": "Tamanho"}
        widths = {"name": 260, "version": 90, "publisher": 150, "source": 110,
                  "strategy": 110, "size": 100}
        for c in cols:
            self.tree.heading(c, text=heads[c])
            self.tree.column(c, width=widths[c], anchor="w")
        tagmap = [("SANDBOX", OK), ("LAUNCHER", WARN), ("MANUAL", ERR)]
        for name, color in tagmap:
            self.tree.tag_configure(name, foreground=color)
        vsb = ttk.Scrollbar(grid_wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", lambda e: self.tab2.select())

        # ---- aba 2: analise -----------------------------------------
        tab2 = tk.Frame(nb, bg=BG); nb.add(tab2, text="  2 · Analisar  ")
        self.tab2 = tab2
        info = Card(tab2, "Diagnostico de viabilidade (gerado ANTES da execucao)")
        self.detail = scrolledtext.ScrolledText(
            info, height=12, bg=BG3, fg=FG, insertbackground=FG, bd=0,
            font=FONT_MONO, state="disabled")
        self.detail.pack(fill="both", expand=True, padx=14, pady=(4, 12))

        opts = Card(tab2, "Opcoes de clonagem")
        g1 = tk.Frame(opts, bg=BG2); g1.pack(fill="x", padx=14, pady=6)
        tk.Label(g1, text="Estrategia:", bg=BG2, fg=FG, font=FONT).pack(side="left")
        self.strategy_var = tk.StringVar(value="LAUNCHER")
        for v, lbl in (("SANDBOX", "Sandbox completa"),
                       ("LAUNCHER", "Launcher pragmatico"),
                       ("MANUAL", "Manual (so relatorio)")):
            tk.Radiobutton(g1, text=lbl, value=v, variable=self.strategy_var,
                           bg=BG2, fg=FG, selectcolor=BG3, activebackground=BG2,
                           activeforeground=FG, font=FONT).pack(side="left", padx=8)
        g2 = tk.Frame(opts, bg=BG2); g2.pack(fill="x", padx=14, pady=6)
        self.trial_on = tk.BooleanVar(value=False)
        tk.Checkbutton(g2, text="(item 7) Reset de contadores de uso / trial:",
                       variable=self.trial_on, bg=BG2, fg=FG, selectcolor=BG3,
                       activebackground=BG2, activeforeground=FG, font=FONT)\
            .pack(side="left")
        self.trial_mode = tk.StringVar(value="generico")
        cb = ttk.Combobox(g2, textvariable=self.trial_mode, state="readonly",
                          values=["generico", "heuristica-avancada"], width=20)
        cb.pack(side="left", padx=10)
        tk.Label(g2, text="generico = zera contadores conhecidos (seguro) | "
                         "heuristica = padroes de trial mais agressivos",
                 bg=BG2, fg=MUTED, font=("Segoe UI", 9)).pack(side="left")
        note = tk.Label(
            opts,
            text="Atencao: use apenas em software que voce possui/licenciou. O reset "
                 "atua so sobre artefatos detectados; protecoes avancadas serao "
                 "reportadas como impossibilidade no relatorio.",
            bg=BG2, fg=MUTED, font=("Segoe UI", 9), wraplength=900, justify="left")
        note.pack(anchor="w", padx=14, pady=(2, 12))

        # ---- aba 3: clonar -------------------------------------------
        tab3 = tk.Frame(nb, bg=BG); nb.add(tab3, text="  3 · Clonar  ")
        self.tab3 = tab3
        out = Card(tab3, "Formato de saida (item 9)")
        self.fmt_var = tk.StringVar(value="PASTA")
        for v, lbl in (("PASTA", "(a) Pasta com arquivos + PortabilisLauncher.exe"),
                       ("SFX",   "(b) Arnico .exe autoextrativo (SFX)"),
                       ("ZIP",   "(c) Pacote comprimido para extrair e executar")):
            tk.Radiobutton(out, text=lbl.replace("Arnico", "Unico"), value=v,
                           variable=self.fmt_var, bg=BG2, fg=FG, selectcolor=BG3,
                           activebackground=BG2, activeforeground=FG,
                           font=FONT, anchor="w").pack(fill="x", padx=14, pady=3)
        out.columnconfigure(0, weight=1)
        row2 = tk.Frame(out, bg=BG2); row2.pack(fill="x", padx=14, pady=8)
        tk.Label(row2, text="Salvar em:", bg=BG2, fg=FG, font=FONT).pack(side="left")
        self.out_dir = tk.StringVar(value=os.path.join(
            os.path.expanduser("~"), "Desktop", "PortabilisOut"))
        tk.Entry(row2, textvariable=self.out_dir, bg=BG3, fg=FG, insertbackground=FG,
                 bd=0, font=FONT).pack(side="left", fill="x", expand=True,
                                       padx=8, ipady=6)
        self._btn(row2, "...", self._pick_dir, accent=False).pack(side="left")
        row3 = tk.Frame(out, bg=BG2); row3.pack(fill="x", padx=14, pady=(4, 14))
        self.clone_btn = self._btn(row3, "CLONAR PROGRAMA", self.do_clone)
        self.clone_btn.pack(side="left")
        self._btn(row3, "Ver relatorio", self.show_report, accent=False)\
            .pack(side="left", padx=8)
        logcard = Card(tab3, "Log de execucao")
        self.log = scrolledtext.ScrolledText(
            logcard, height=10, bg=BG3, fg=FG, insertbackground=FG, bd=0,
            font=FONT_MONO, state="disabled")
        self.log.pack(fill="both", expand=True, padx=14, pady=(4, 12))

    # ------------------------------------------------------------ helpers
    def _pick_dir(self):
        d = filedialog.askdirectory(initialdir=os.path.expanduser("~"))
        if d:
            self.out_dir.set(d)

    def _log(self, msg):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _set_status(self, text, color=OK):
        self.status_var.set(text)

    def _busy_guard(self, busy=True, label="Trabalhando..."):
        self._busy = busy
        if busy:
            self.progress.start(12)
            self._set_status(label, WARN)
        else:
            self.progress.stop()
            self._set_status("Pronto", OK)

    # ------------------------------------------------------------ acoes
    def do_scan(self):
        if self._busy:
            return
        inc_reg, inc_file = self.inc_reg.get(), self.inc_file.get()
        if not (inc_reg or inc_file):
            self._set_status("Escolha ao menos uma fonte de deteccao", ERR)
            return

        def work():
            try:
                apps = scan.full_scan(inc_reg, inc_file)
                self.after(0, lambda: self._scan_done(apps))
            except Exception:
                err = traceback.format_exc()
                self.after(0, lambda: self._log("ERRO no scan:\n" + err))
                self.after(0, lambda: self._busy_guard(False))
        self._busy_guard(True, "Escaneando...")
        threading.Thread(target=work, daemon=True).start()

    def _fmt_size(self, b):
        if b > 1e9:
            return "%.1f GB" % (b / 1e9)
        if b > 1e6:
            return "%.0f MB" % (b / 1e6)
        return "%.0f KB" % (b / 1e3)

    def _scan_done(self, apps):
        self.apps = apps
        self.tree.delete(*self.tree.get_children())
        for i, a in enumerate(apps):
            src = "Registro" if a.source == "registry" else "Varredura .exe"
            self.tree.insert("", "end", iid=str(i), values=(
                a.name, a.version, a.publisher, src, a.strategy,
                self._fmt_size(a.size_bytes)), tags=(a.strategy,))
        self._busy_guard(False)
        self._set_status("%d programa(s) encontrados" % len(apps), OK)
        self._log("[scan] %d programas detectados (%s)." % (
            len(apps),
            "+".join([f for f, on in (("registro", self.inc_reg.get()),
                                      ("varredura", self.inc_file.get())) if on])))

    def _on_select(self, _evt=None):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        self.selected = self.apps[idx]
        a = self.selected
        self.strategy_var.set(a.strategy)
        txt = ["Programa....: %s %s" % (a.name, a.version),
               "Publicador..: %s" % (a.publisher or "-"),
               "Local.......: %s" % (a.install_location or a.main_exe),
               "Origem......: %s" % ("Registro (Uninstall)" if a.source == "registry"
                                     else "Varredura de .exe"),
               "Conteudo....: %d arquivos (%s)" % (a.files_found,
                                                   self._fmt_size(a.size_bytes)),
               "Estrategia recomendada: %s" % a.strategy,
               "-" * 64, "DIAGNOSTICO:"]
        for n in a.notes:
            txt.append("  • " + n)
        if a.risks:
            txt.append("RISCOS: " + ", ".join(a.risks))
        trials = [k for k in a.reg_keys if k.startswith(("REG:", "FILE:"))]
        txt.append("-" * 64)
        txt.append("ARTEFATOS DE LICENCA/TRIAL (varredura generica): %d" % len(trials))
        txt += ["  " + t for t in trials[:30]]
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", "\n".join(txt))
        self.detail.configure(state="disabled")

    def do_clone(self):
        if self._busy:
            return
        if not self.selected:
            self._set_status("Selecione um programa na aba Detectar", ERR)
            return
        app = self.selected
        fmt = self.fmt_var.get()
        strategy = self.strategy_var.get()
        trial = self.trial_on.get()
        mode = self.trial_mode.get()
        out = self.out_dir.get()
        if strategy == "MANUAL":
            self.show_report()
            return
        try:
            os.makedirs(out, exist_ok=True)
        except OSError as e:
            self._set_status("Pasta de saida invalida: %s" % e, ERR)
            return

        def prog(n, msg):
            self.after(0, lambda: self._log("[%6d] %s" % (n, msg)))

        def work():
            try:
                art = clone.clone_program(app, out, fmt, strategy, trial, mode, prog)
                self.after(0, lambda: self._clone_done(str(art)))
            except clone.CloneError as e:
                self.after(0, lambda: self._log("BLOQUEADO: %s" % e))
                self.after(0, lambda e=str(e): self._set_status(
                    "Clonacao bloqueada: " + e.split("\n")[0][:60], ERR))
                self.after(0, lambda: self._busy_guard(False))
            except Exception:
                err = traceback.format_exc()
                self.after(0, lambda: self._log("ERRO:\n" + err))
                self.after(0, lambda: self._busy_guard(False))
        self._busy_guard(True, "Clonando %s..." % app.name)
        self.tab3.nametowidget(self.tab3.winfo_children()[0])  # noop guard
        threading.Thread(target=work, daemon=True).start()

    def _clone_done(self, artifact):
        self._busy_guard(False)
        self._set_status("Clone concluido!", OK)
        self._log("=" * 60)
        self._log("ARTEFATO GERADO: %s" % artifact)
        self._log("Abra o pacote e execute PortabilisLauncher.exe.")
        self._log("Leia RELATORIO.txt antes da primeira execucao.")
        self._log("=" * 60)

    def show_report(self):
        if not self.selected:
            return
        win = tk.Toplevel(self)
        win.title("Relatorio de viabilidade - %s" % self.selected.name)
        win.geometry("760x560"); win.configure(bg=BG)
        st = scrolledtext.ScrolledText(win, bg=BG3, fg=FG, bd=0, font=FONT_MONO)
        st.pack(fill="both", expand=True, padx=10, pady=10)
        lines = ["PORTABILIS - PRE-VISUALIZACAO DO RELATORIO (antes de clonar)",
                 "=" * 64]
        lines += self.selected.notes or ["Sem avisos."]
        if self.selected.risks:
            lines.append("Riscos: " + ", ".join(self.selected.risks))
        st.insert("1.0", "\n".join(lines))
        st.configure(state="disabled")


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
