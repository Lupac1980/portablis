# -*- coding: utf-8 -*-
"""
Portabilis - modulo de deteccao/analise de programas instalados.

Fontes de deteccao (configuraveis na UI):
  (a) Registro Windows: HKLM/HKCU ...\\Microsoft\\Windows\\CurrentVersion\\Uninstall
      (mesma fonte usada pelo Painel de Controle / "Adicionar ou Remover Programas")
  (b) Varredura de .exe em pastas comuns (programas ja portaveis / nao registrados):
      Program Files, Program Files (x86), Desktop, Downloads, C:\\Apps, C:\\Tools,
      pasta do proprio Portabilis.

A analise de viabilidade de clonagem atribui uma estrategia:
  * SANDBOX   - nivel ThinApp (filesystem redirect + registro virtual + mutex guard)
  * LAUNCHER  - abordagem pragmatica (copia arquivos + exporta chaves + launcher contextual)
  * MANUAL    - exige intervencao do usuario (servicos/drivers/compartilhados detectados)
E gera um relatorio detalhado com dificuldades/impossibilidades ANTES da execucao.
"""
import os
import re
import json
import fnmatch
from dataclasses import dataclass, field, asdict
from typing import List, Optional

try:
    import winreg
    HAS_WINREG = True
except ImportError:
    HAS_WINREG = False

UNINSTALL_KEYS = [
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall") if HAS_WINREG else (0, ""),
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall") if HAS_WINREG else (0, ""),
    (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall") if HAS_WINREG else (0, ""),
]

COMMON_EXE_DIRS_ENV = ["ProgramFiles", "ProgramFiles(x86)", "ProgramData",
                       "LOCALAPPDATA", "USERPROFILE"]
COMMON_EXE_SUBDIRS = ["Desktop", "Downloads", "Documents"]
EXTRA_DIRS = [r"C:\Apps", r"C:\Tools", r"D:\Apps"]

SCAN_MAX_DEPTH = 4          # profundidade maxima da varredura de discos
SCAN_SKIP_DIRS = {"windows", "$recycle.bin", "system volume information",
                  "winsxs", "temp", "$windows.~bt", "node_modules", "appdata"}

# Padroes que indicam dependencia profunda -> sandbox completa desaconselhada
RISK_PATTERNS = {
    "service": re.compile(r"(srv|service|daemon|agent)\.exe$", re.I),
    "driver":  re.compile(r"\.sys$", re.I),
    "shell_ext": re.compile(r"(shellext|contextmenu|shell_ext|iconoverlay)", re.I),
    "shared_dll_in_system32": re.compile(r"system32|syswow64", re.I),
}

# Chaves/pastas tipicas onde aplicativos gravam licenca/trial/contadores de uso
TRIAL_LOCATIONS = [
    (winreg.HKEY_CURRENT_USER, r"Software") if HAS_WINREG else (0, ""),
    (winreg.HKEY_LOCAL_MACHINE, r"Software") if HAS_WINREG else (0, ""),
    ("FILE", r"%APPDATA%"), ("FILE", r"%LOCALAPPDATA%"), ("FILE", r"%PROGRAMDATA%"),
]
TRIAL_KEYWORDS = ["trial", "licen", "regist", "activ", "count", "usage", "expire",
                  "serial", "evaluation", "days_left", "runs", "launch_count", "oobe"]


@dataclass
class InstalledApp:
    name: str
    version: str = ""
    publisher: str = ""
    install_location: str = ""
    uninstall_string: str = ""
    main_exe: str = ""
    source: str = "registry"          # registry | filescan
    reg_keys: List[str] = field(default_factory=list)
    files_found: int = 0
    size_bytes: int = 0
    risks: List[str] = field(default_factory=list)
    strategy: str = "LAUNCHER"        # SANDBOX | LAUNCHER | MANUAL
    notes: List[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


def _reg_read_value(key, name):
    try:
        v, _ = winreg.QueryValueEx(key, name)
        return v if isinstance(v, str) else str(v)
    except OSError:
        return ""


def enumerate_registry_apps() -> List[InstalledApp]:
    apps = []
    if not HAS_WINREG:
        return apps
    for hive, path in UNINSTALL_KEYS:
        try:
            root = winreg.OpenKey(hive, path)
        except OSError:
            continue
        i = 0
        while True:
            try:
                subname = winreg.EnumKey(root, i)
            except OSError:
                break
            i += 1
            try:
                sk = winreg.OpenKey(root, subname)
            except OSError:
                continue
            name = _reg_read_value(sk, "DisplayName")
            loc = _reg_read_value(sk, "InstallLocation")
            exe = _reg_read_value(sk, "DisplayIcon") or _reg_read_value(sk, "UninstallString")
            if name and not _reg_read_value(sk, "SystemComponent") and ".exe" in (exe.lower() + loc.lower()):
                full_key = "%s\\%s\\%s" % (
                    "HKLM" if hive == winreg.HKEY_LOCAL_MACHINE else "HKCU", path, subname)
                apps.append(InstalledApp(
                    name=name,
                    version=_reg_read_value(sk, "DisplayVersion"),
                    publisher=_reg_read_value(sk, "Publisher"),
                    install_location=loc,
                    uninstall_string=_reg_read_value(sk, "UninstallString"),
                    main_exe=_clean_icon_path(exe),
                    source="registry",
                    reg_keys=[full_key],
                ))
            winreg.CloseKey(sk)
        winreg.CloseKey(root)
    return apps


def _clean_icon_path(s: str) -> str:
    s = s.strip().strip('"')
    s = re.sub(r",-\d+$", "", s)       # remove ",-XXX" resource index
    return s


def enumerate_filescan_apps() -> List[InstalledApp]:
    roots = []
    for env in COMMON_EXE_DIRS_ENV:
        base = os.environ.get(env)
        if base:
            roots.append(base)
            for sub in COMMON_EXE_SUBDIRS:
                roots.append(os.path.join(base, sub))
    roots += EXTRA_DIRS
    roots.append(os.path.dirname(os.path.abspath(__file__)))
    apps = []
    for root in filter(os.path.isdir, roots):
        for dirpath, dirnames, filenames in os.walk(root):
            depth = dirpath[len(root):].count(os.sep)
            if depth >= SCAN_MAX_DEPTH:
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames if d.lower() not in SCAN_SKIP_DIRS]
            exes = [f for f in filenames if f.lower().endswith(".exe")]
            if not exes:
                continue
            big = max(exes, key=lambda f: os.path.getsize(os.path.join(dirpath, f))
                      if os.path.exists(os.path.join(dirpath, f)) else 0)
            if "unins" in big.lower():
                exes = [e for e in exes if "unins" not in e.lower()]
                if not exes:
                    continue
                big = exes[0]
            folder_name = os.path.basename(dirpath)
            total = sum(os.path.getsize(os.path.join(dirpath, f))
                        for f in filenames if os.path.exists(os.path.join(dirpath, f)))
            apps.append(InstalledApp(
                name=folder_name,
                install_location=dirpath,
                main_exe=os.path.join(dirpath, big),
                source="filescan",
                files_found=len(filenames),
                size_bytes=total,
            ))
    return apps


def analyze_app(app: InstalledApp) -> InstalledApp:
    """Avalia riscos e define estrategia recomendada + notas do relatorio."""
    app.notes = []
    base = app.install_location or os.path.dirname(app.main_exe or "")
    if base and not os.path.isdir(base):
        app.notes.append("Pasta de instalacao nao encontrada: %s" % base)
        app.risks.append("missing_folder")
        app.strategy = "MANUAL"
        return app
    all_files = []
    if base:
        for dp, dn, fn in os.walk(base):
            for f in fn:
                all_files.append(os.path.join(dp, f))
    app.files_found = len(all_files)
    app.size_bytes = sum(os.path.getsize(p) for p in all_files
                         if os.path.exists(p))
    has_service = any(RISK_PATTERNS["service"].search(f) for f in map(os.path.basename, all_files))
    has_driver = any(RISK_PATTERNS["driver"].search(f) for f in all_files)
    has_shellext = any(RISK_PATTERNS["shell_ext"].search(f.lower()) for f in all_files)
    if has_service:
        app.risks.append("service")
        app.notes.append("Detectado servico: servicos NT nao podem ser virtualizados no MVP -> modo MANUAL.")
    if has_driver:
        app.risks.append("driver")
        app.notes.append("Detectado driver (.sys): kernel-mode nao e clonavel -> modo MANUAL.")
    if has_shellext:
        app.risks.append("shell_extension")
        app.notes.append("Extensao de shell detectada: so funciona registrada no Explorer -> limitacao parcial.")
    # heuristicas de estrategia
    if not app.risks and app.source == "registry" and app.size_bytes < 500 * 1024 * 1024:
        app.strategy = "SANDBOX"
        app.notes.append("Standalone simples: recomendado SANDBOX completa (arquivos+registro virtualizados).")
    elif not app.risks:
        app.strategy = "LAUNCHER"
        app.notes.append("Recomendado LAUNCHER pragmatico (copia + registro exportado + loader de contexto).")
    else:
        app.strategy = "MANUAL"
    # trial/licenca
    trials = scan_trial_artifacts(app)
    if trials:
        app.notes.append("Artefatos de licenca/trial encontrados (%d): ver lista no relatorio." % len(trials))
    app.reg_keys += trials[:50]
    return app


def scan_trial_artifacts(app: InstalledApp) -> List[str]:
    """Varredura generica por chaves/arquivos conhecidos de trial/licenca."""
    found = []
    needles = [app.name] + TRIL_KEYWORDS_SAFE(app)
    if HAS_WINREG:
        for hive, path in TRIAL_LOCATIONS:
            if path == "Software":
                found += _find_reg_matches(hive, path, needles)
    for env in ("%APPDATA%", "%LOCALAPPDATA%", "%PROGRAMDATA%"):
        base = os.path.expandvars(env)
        if os.path.isdir(base):
            for entry in os.listdir(base):
                if _matches_needle(entry, needles):
                    found.append("FILE:%s" % os.path.join(base, entry))
    return found


def TRIL_KEYWORDS_SAFE(app):
    words = re.split(r"[^A-Za-z0-9]+", app.name)
    return [w for w in words if len(w) > 3]


def _find_reg_matches(hive, path, needles, depth=2):
    matches = []
    if not HAS_WINREG or depth < 0:
        return matches
    try:
        key = winreg.OpenKey(hive, path)
    except OSError:
        return matches
    i = 0
    while True:
        try:
            sub = winreg.EnumKey(key, i)
        except OSError:
            break
        i += 1
        full = "%s\\%s\\%s" % ("HKLM" if hive == winreg.HKEY_LOCAL_MACHINE else "HKCU", path, sub)
        if _matches_needle(sub, needles) or any(_matches_needle(k, TRIAL_KEYWORDS) for k in [sub]):
            matches.append("REG:%s" % full)
        matches += _find_reg_matches(hive, path + "\\" + sub, needles, depth - 1)
    winreg.CloseKey(key)
    return matches


def _matches_needle(text, needles):
    t = text.lower()
    return any(n.lower() in t for n in needles if n)


def full_scan(include_registry=True, include_filescan=True) -> List[InstalledApp]:
    apps: List[InstalledApp] = []
    if include_registry:
        apps += enumerate_registry_apps()
    if include_filescan:
        apps += enumerate_filescan_apps()
    # dedupe por nome+pasta
    seen = {}
    out = []
    for a in apps:
        k = (a.name.lower(), a.install_location.lower())
        if k in seen:
            seen[k].reg_keys += a.reg_keys
            continue
        seen[k] = a
        out.append(a)
    for a in out:
        analyze_app(a)
    out.sort(key=lambda x: x.name.lower())
    return out


if __name__ == "__main__":
    result = full_scan()
    print(json.dumps([r.to_dict() for r in result], indent=2, ensure_ascii=False))
