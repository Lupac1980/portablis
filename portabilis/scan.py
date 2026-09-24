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

# Fontes de registro usadas pelo Painel de Controle ("Desinstalar um programa"):
#   - HKLM\SOFTWARE\...\Uninstall          -> visao nativa (64 bits no Windows 64)
#   - HKLM\SOFTWARE\...\Uninstall (32-bit) -> visão WOW6432Node: apps 32 bits
#     (aplicativos legados de 32 bits). Enumerada explicitamente com KEY_WOW64_32KEY para
#     funcionar igual ao Painel de Controle independentemente da arquitetura do
#     processo do Portabilis.
#   - HKCU\SOFTWARE\...\Uninstall          -> installs por usuario
UNINSTALL_BASE = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"

def _uninstall_scopes():
    """Retorna [(hive, path, access_flag, rotulo_origem), ...] cobrindo todas
    as origens que o Painel de Controle lista."""
    if not HAS_WINREG:
        return []
    k64 = getattr(winreg, "KEY_WOW64_64KEY", 0x0100)
    k32 = getattr(winreg, "KEY_WOW64_32KEY", 0x0200)
    scopes = [
        (winreg.HKEY_LOCAL_MACHINE, UNINSTALL_BASE, k64, "Registro (HKLM 64-bit)"),
        (winreg.HKEY_LOCAL_MACHINE, UNINSTALL_BASE, k32, "Registro (HKLM 32-bit/WOW64)"),
        (winreg.HKEY_CURRENT_USER,  UNINSTALL_BASE, k64, "Registro (HKCU)"),
    ]
    # fallback historico: chave fisica WOW6432Node
    scopes.append((winreg.HKEY_LOCAL_MACHINE,
                   r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
                   0, "Registro (WOW6432Node)"))
    return scopes

def is_registry_source(source: str) -> bool:
    """True para qualquer origem vinda do registro Uninstall (HKLM 64,
    HKLM 32/WOW64, HKCU ou WOW6432Node)."""
    return (source or "").lower().startswith("registro")


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
    source: str = "registry"          # Registro (Painel de Controle) | varredura .exe | manual
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


def _resolve_app_exe(name, loc, icon, uninstall):
    """Determina o executavel principal do app, imitando a resolucao do
    Painel de Controle: InstallLocation + atalhos do Menu Iniciar ->
    DisplayIcon -> pasta de instalacao."""
    # 1) atalhos .lnk do Menu Iniciar apontando para o programa
    lnk = _find_startmenu_target(name)
    if lnk:
        return lnk
    # 2) DisplayIcon / UninstallString quando forem um .exe valido existente
    for cand in (_clean_icon_path(icon), uninstall):
        p = _expand(cand)
        if p and p.lower().endswith(".exe") and os.path.isfile(p):
            return p
    # 3) maior .exe dentro de InstallLocation
    base = _expand(loc)
    if base and os.path.isdir(base):
        best, best_sz = "", -1
        for dp, dn, fn in os.walk(base):
            for f in fn:
                if f.lower().endswith(".exe") and "unins" not in f.lower():
                    fp = os.path.join(dp, f)
                    try:
                        sz = os.path.getsize(fp)
                    except OSError:
                        continue
                    if sz > best_sz:
                        best, best_sz = fp, sz
        if best:
            return best
    return _clean_icon_path(icon)


def _expand(p):
    return os.path.expandvars(p.strip().strip('"')) if p else ""


def _find_startmenu_target(name):
    """Procura atalhos .lnk no Menu Iniciar cujo destino seja um .exe da pasta
    do programa com o nome pesquisado (igual faz o Painel de Controle ao
    exibir 'Abrir local de arquivo')."""
    import glob
    bases = [os.path.join(os.environ.get("ProgramData", ""), r"Microsoft\Windows\Start Menu\Programs"),
             os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs")]
    needle = re.sub(r"[^a-z0-9]", "", (name or "").lower())
    if len(needle) < 4:
        return ""
    for base in filter(os.path.isdir, bases):
        for lnk in glob.glob(os.path.join(base, "**", "*.lnk"), recursive=True):
            target = _lnk_target(lnk)
            if not target:
                continue
            tkey = re.sub(r"[^a-z0-9]", "", os.path.splitext(os.path.basename(target))[0].lower())
            if tkey and (needle in tkey or tkey in needle):
                return target
    return ""


def _lnk_target(path):
    """Extrai o caminho do destino de um atalho .lnk sem dependencias externas
    (parse minimo da estrutura Shell Link, bloco TARGET/Distributed Link)."""
    try:
        with open(path, "rb") as fh:
            data = fh.read(2048)
        if len(data) < 76 or data[:4] != b"\x4c\x00\x00\x00":
            return ""
        flags = int.from_bytes(data[20:24], "little")
        pos = 76
        if flags & 0x01:      # HasLinkTargetIDList
            n = int.from_bytes(data[pos:pos + 2], "little")
            pos += 2 + n
        if not (flags & 0x02):  # sem TargetPath
            return ""
        off = int.from_bytes(data[pos:pos + 4], "little")
        s, e = pos + off, data.find(b"\x00\x00", pos + off)
        target = data[pos + off:e].decode("utf-16-le", "ignore").split("\x00")[0]
        return target if target.lower().endswith(".exe") and os.path.isfile(target) else ""
    except Exception:
        return ""


def enumerate_registry_apps() -> List[InstalledApp]:
    """Lista exatamente os programas que o Painel de Controle exibe em
    'Desinstalar um programa': percorre HKLM (visao 64-bit E 32-bit/WOW64,
    para pegar aplicativos de 32 bits) e HKCU, ignorando
    componentes de sistema e entradas sem DisplayName — mesma regra do shell.
    """
    apps = []
    seen = set()
    if not HAS_WINREG:
        return apps
    for hive, path, access, origin in _uninstall_scopes():
        try:
            root = winreg.OpenKey(hive, path, 0,
                                  winreg.KEY_READ | access) if access \
                else winreg.OpenKey(hive, path)
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
                sk = winreg.OpenKey(root, subname, 0,
                                    winreg.KEY_READ | access) if access \
                    else winreg.OpenKey(root, subname)
            except OSError:
                continue
            name = _reg_read_value(sk, "DisplayName")
            syscomp = _reg_read_value(sk, "SystemComponent")
            parent = _reg_read_value(sk, "ParentKeyName")     # updates de Windows
            release = _reg_read_value(sk, "ReleaseType")      # hotfixes/QFE
            wininstaller = _reg_read_value(sk, "WindowsInstaller")
            loc = _reg_read_value(sk, "InstallLocation")
            icon = _reg_read_value(sk, "DisplayIcon")
            uninstall = _reg_read_value(sk, "UninstallString")
            hidden = _reg_read_value(sk, "Hidden")
            exe = icon or uninstall
            key_id = (name.lower(), loc.lower())
            ok_name = bool(name) and syscomp != "1" and not parent and \
                release not in ("Security Update", "Update Rollups", "hotfix") and \
                hidden != "1"
            # Assim como o Painel, exibimos mesmo sem .exe aparente; mas se nao
            # houver NENHUMA pista de executavel/pasta e for apenas um MSI sem
            # InstallLocation, ainda listamos (clone pode usar Menu Iniciar).
            has_body = (".exe" in (exe.lower() + loc.lower())
                        or bool(_find_startmenu_target(name))
                        or (bool(loc) and os.path.isdir(_expand(loc))))
            if ok_name and has_body and key_id not in seen:
                seen.add(key_id)
                full_key = "%s\\%s\\%s" % (
                    "HKLM" if hive == winreg.HKEY_LOCAL_MACHINE else "HKCU", path, subname)
                apps.append(InstalledApp(
                    name=name,
                    version=_reg_read_value(sk, "DisplayVersion"),
                    publisher=_reg_read_value(sk, "Publisher"),
                    install_location=_expand(loc),
                    uninstall_string=uninstall,
                    main_exe=_resolve_app_exe(name, loc, icon, uninstall),
                    source=origin,
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
    if not app.risks and is_registry_source(app.source) and app.size_bytes < 500 * 1024 * 1024:
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
