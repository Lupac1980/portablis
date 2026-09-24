# -*- coding: utf-8 -*-
"""
Portabilis - nucleo de clonagem (MVP).

Estrategias:
  SANDBOX  - copia arquivos para Data\\Sandbox, exporta chaves de registro para
             Data\\Registry (*.reg) e gera launcher que aplica o contexto antes de executar.
  LAUNCHER - mesma base pragmatica: copia + registro exportado + loader de ambiente
             (redirects de APPDATA/LOCALAPPDATA/TEMP para dentro do pacote).
  MANUAL   - apenas relatorio; usuario decide os passos.

Formatos de saida (item 9):
  (a) PASTA : pasta com todos os arquivos + PortabilisLauncher.exe
  (b) SFX   : unico .exe autoextrativo (gerado com iexpress, se disponivel)
  (c) ZIP   : pacote comprimido pronto para extrair e executar
  (d) EXE   : unico .exe "onefile" no estilo build_exe.bat (PyInstaller);
              ao executar, extrai o pacote para uma pasta ao lado do .exe
              (ou %TEMP%) e lanca o PortabilisLauncher automaticamente.
"""
import os
import sys
import json
import shutil
import zipfile
import subprocess
import datetime
from pathlib import Path
from typing import List, Optional

def _fmt_source(src):
    """Rotulo amigavel da origem do app no relatorio de clone."""
    if src == 'manual':
        return 'Selecao manual'
    if str(src).lower().startswith('registro'):
        return str(src) + ' - Painel de Controle'
    return 'Varredura de .exe'


IS_WIN = sys.platform == "win32"
if IS_WIN:
    import winreg

LAUNCHER_SRC = r'''# -*- coding: utf-8 -*-
"""Portabilis Launcher - prepara o ambiente virtual e executa o programa clonado."""
import os, sys, subprocess, json, shutil

def here():
    return os.path.dirname(os.path.abspath(sys.argv[0]))

BASE = here()
DATA = os.path.join(BASE, "Data")
SANDBOX = os.path.join(DATA, "Sandbox")
REGDIR = os.path.join(DATA, "Registry")
MANIFEST = os.path.join(DATA, "manifest.json")

def load_manifest():
    try:
        with open(MANIFEST, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def apply_registry_once(m):
    """Importa os .reg exportados na primeira execucao (contexto inicial)."""
    stamp = os.path.join(DATA, ".registry_applied")
    if os.path.exists(stamp) or not m.get("apply_registry_on_first_run", True):
        return
    ok = 0
    for root, _, files in os.walk(REGDIR):
        for f in files:
            if f.lower().endswith(".reg"):
                p = os.path.join(root, f)
                try:
                    subprocess.run(["regedit", "/s", p], check=False,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    ok += 1
                except FileNotFoundError:
                    pass
    try:
        open(stamp, "w").close()
    except OSError:
        pass
    print("[Portabilis] %d arquivo(s) de registro aplicados." % ok)

def redirect_env(m):
    """Redireciona AppData/Temp para dentro do pacote (isolamento basico)."""
    links = os.path.join(SANDBOX, "_portabilis")
    for var in ("APPDATA", "LOCALAPPDATA", "TEMP", "TMP"):
        target = os.path.join(links, var.lower())
        os.makedirs(target, exist_ok=True)
        os.environ[var] = target
    # semeia com a config existente na 1a execucao (preserva licencas/settings)
    seed = m.get("seed_from_real_appdata", True)
    marker = os.path.join(links, ".seeded")
    if seed and not os.path.exists(marker):
        real = {"APPDATA": os.path.expandvars(r"%APPDATA%"),
                "LOCALAPPDATA": os.path.expandvars(r"%LOCALAPPDATA%")}
        appname = m.get("app_name", "")
        for var, base in real.items():
            src = os.path.join(base, appname) if appname else ""
            if src and os.path.isdir(src):
                dst = os.path.join(links, var.lower(), appname)
                try:
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                except Exception:
                    pass
        try:
            open(marker, "w").close()
        except OSError:
            pass

def reset_trial_counters(m):
    """(Item 7) Reset dos contadores/trial capturados no snapshot do clone."""
    snap_path = os.path.join(DATA, "trial_snapshot.json")
    if not os.path.exists(snap_path):
        return
    try:
        with open(snap_path, "r", encoding="utf-8") as f:
            snap = json.load(f)
    except Exception:
        return
    mode = m.get("trial_reset_mode", "generico")
    try:
        import winreg
    except ImportError:
        print("[Portabilis] winreg indisponivel; pulando reset.")
        return
    n = 0
    for item in snap.get("registry_values", []):
        try:
            hive = getattr(winreg, item["hive"])
            if mode == "generico":
                with winreg.OpenKey(hive, item["path"], 0, winreg.KEY_SET_VALUE) as k:
                    v, t = winreg.QueryValueEx(k, item["name"])
                    if t == winreg.REG_DWORD and isinstance(v, int) and v != 0:
                        winreg.SetValueEx(k, item["name"], 0, t, 0); n += 1
                    elif t == winreg.REG_SZ and str(v).strip().isdigit():
                        winreg.SetValueEx(k, item["name"], 0, t, "0"); n += 1
            else:  # 'snapshot': restaura valores limpos tirados durante a clonagem
                with winreg.OpenKey(hive, item["path"], 0, winreg.KEY_SET_VALUE) as k:
                    winreg.SetValueEx(k, item["name"], 0, item["type"],
                                      item["clean_value"]); n += 1
        except OSError:
            continue
    print("[Portabilis] %d contador(es)/artefato(s) de trial tratados (modo=%s)." % (n, mode))

def main():
    m = load_manifest()
    print("=" * 60)
    print("Portabilis Launcher - %s %s" % (m.get("app_name", "?"), m.get("app_version", "")))
    print("Estrategia: %s | Clonado em: %s" % (m.get("strategy", "?"), m.get("cloned_at", "")))
    print("=" * 60)
    rpt = os.path.join(BASE, m.get("report", "RELATORIO.txt"))
    if os.path.exists(rpt):
        with open(rpt, "r", encoding="utf-8", errors="replace") as f:
            txt = f.read()
        print("\n--- RELATORIO DE VIABILIDADE (leia antes de executar) ---")
        print(txt[:4000])
        print("--- resumo acima; relatorio completo em RELATORIO.txt ---\n")
        if "[BLOQUEADO]" in txt:
            ans = input("O relatorio aponta bloqueios. Continuar mesmo assim? [s/N] ").strip().lower()
            if ans != "s":
                sys.exit(1)
    apply_registry_once(m)
    redirect_env(m)
    if m.get("trial_bypass_enabled", False):
        try:
            reset_trial_counters(m)
        except Exception as e:
            print("[Portabilis] Aviso: falha no reset de trial (%s)." % e)
    exe = m.get("main_exe", "")
    target = os.path.join(SANDBOX, exe) if exe else ""
    if not target or not os.path.exists(target):
        cands = []
        for root, _, files in os.walk(SANDBOX):
            cands += [os.path.join(root, f) for f in files
                      if f.lower().endswith(".exe") and "portabilislauncher" not in f.lower()]
        target = max(cands, key=os.path.getsize) if cands else ""
    if not target:
        print("[Portabilis] ERRO: executavel alvo nao encontrado em Data\\Sandbox.")
        sys.exit(2)
    print("[Portabilis] Executando: %s" % target)
    env = dict(os.environ)
    env["PATH"] = os.path.dirname(target) + os.pathsep + env.get("PATH", "")  # ponte p/ DLLs
    proc = subprocess.Popen([target], cwd=os.path.dirname(target), env=env)
    sys.exit(proc.wait())

if __name__ == "__main__":
    main()
'''


class CloneError(Exception):
    pass


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def run(cmd, **kw):
    return subprocess.run(cmd, **kw)


# ---------------------------------------------------------------- registro
def export_registry_keys(keys: List[str], out_dir: Path, log: List[str]) -> int:
    """Exporta chaves ('HKLM\\SOFTWARE\\...' ou prefixo 'REG:') via reg.exe."""
    out_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for key in keys:
        k = key[4:] if key.startswith("REG:") else key
        if not k.upper().startswith(("HKLM\\", "HKCU\\", "HKCR\\", "HKU\\", "HKCC\\")):
            continue
        safe = "".join(c if c.isalnum() else "_" for c in k)[:120]
        dest = out_dir / (safe + ".reg")
        try:
            r = run(["reg", "export", k, str(dest), "/y"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if r.returncode == 0 and dest.exists():
                count += 1
                log.append("OK  exportado: %s" % k)
            else:
                log.append("FALHA ao exportar: %s (sem acesso?)" % k)
        except FileNotFoundError:
            log.append("reg.exe indisponivel")
            break
    return count


def collect_app_reg_keys(app_name: str) -> List[str]:
    """Heuristica: chaves sob HKLM/HKCU Software cujo nome casa o aplicativo."""
    found: List[str] = []
    if not IS_WIN:
        return found
    needle = app_name.lower()
    words = [w for w in needle.split() if len(w) > 3]
    pairs = [(winreg.HKEY_LOCAL_MACHINE, "HKLM"), (winreg.HKEY_CURRENT_USER, "HKCU")]
    for hive_id, hive in pairs:
        for base in (r"SOFTWARE", r"SOFTWARE\WOW6432Node"):
            try:
                root = winreg.OpenKey(hive_id, base)
            except OSError:
                continue
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(root, i)
                except OSError:
                    break
                i += 1
                s = sub.lower()
                if needle in s or any(w in s for w in words):
                    found.append("%s\\%s\\%s" % (hive, base, sub))
            winreg.CloseKey(root)
    return found


TRIAL_VALUE_NAMES = ["trial", "licen", "regist", "activ", "count", "usage",
                     "expire", "serial", "evaluation", "days", "runs", "oobe"]


def capture_trial_snapshot(app_name: str, reg_keys: List[str], out_file: Path,
                           log: List[str]) -> dict:
    """Snapshot de valores suspeitos de controle de trial/uso (item 7)."""
    snapshot = {"registry_values": [], "files": []}
    if not IS_WIN:
        return snapshot
    for key in reg_keys:
        k = key[4:] if key.startswith("REG:") else key
        for hive_id, hive in ((winreg.HKEY_LOCAL_MACHINE, "HKLM"),
                              (winreg.HKEY_CURRENT_USER, "HKCU")):
            if not k.upper().startswith(hive + "\\"):
                continue
            kk = k[len(hive) + 1:]
            try:
                h = winreg.OpenKey(hive_id, kk, 0, winreg.KEY_READ)
            except OSError:
                continue
            j = 0
            while True:
                try:
                    name, value, typ = winreg.EnumValue(h, j)
                except OSError:
                    break
                j += 1
                low = name.lower()
                if any(t in low for t in TRIAL_VALUE_NAMES):
                    entry = {"hive": hive, "path": kk, "name": name, "type": int(typ)}
                    if isinstance(value, int):
                        entry["current"] = value
                        entry["clean_value"] = 0
                    elif isinstance(value, str):
                        entry["current"] = value[:200]
                        entry["clean_value"] = "0" if value.strip().isdigit() else value
                    else:
                        continue
                    snapshot["registry_values"].append(entry)
                    log.append("TRIAL: %s -> %s = %s" % (k, name, value))
            winreg.CloseKey(h)
    # arquivos suspeitos de licenca em AppData/ProgramData
    import re as _re
    first_word = _re.escape(app_name.split()[0]) if app_name.split() else ""
    pat = _re.compile(first_word, _re.I)
    for env in ("%APPDATA%", "%LOCALAPPDATA%", "%PROGRAMDATA%"):
        base = os.path.expandvars(env)
        if not os.path.isdir(base):
            continue
        for dp, dn, fn in os.walk(base):
            if dp[len(base):].count(os.sep) > 3:
                dn[:] = []
                continue
            for f in fn:
                low = f.lower()
                if (pat.search(dp) or pat.search(f)) and any(
                        x in low for x in ("lic", "trial", "regist", "activ",
                                           ".dat", ".ini", ".xml", ".json")):
                    p = os.path.join(dp, f)
                    try:
                        if os.path.getsize(p) <= 64 * 1024:
                            snapshot["files"].append({
                                "path": p,
                                "note": "arquivo suspeito de licenca/contadores"})
                            log.append("TRIAL(file): %s" % p)
                    except OSError:
                        pass
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    return snapshot


# ---------------------------------------------------------------- build
def copy_tree(src: Path, dst: Path, progress=None) -> int:
    n = 0
    for item in sorted(src.rglob("*")):
        if item.is_file():
            rel = item.relative_to(src)
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(item, target)
                n += 1
            except OSError as e:
                if progress:
                    progress(n, "AVISO: nao copiei %s (%s)" % (rel, e))
            if progress and n % 50 == 0:
                progress(n, str(rel))
    return n


def build_report(app, strategy, output_format, trial_info, warnings, blocked) -> str:
    lines = []
    lines.append("PORTABILIS - RELATORIO DE CLONAGEM")
    lines.append("Gerado em: %s" % _now())
    lines.append("=" * 60)
    lines.append("Programa.....: %s %s" % (app.name, app.version))
    lines.append("Publicador...: %s" % (app.publisher or "-"))
    lines.append("Origem.......: %s" % _fmt_source(app.source))
    lines.append("Local........: %s" % (app.install_location or app.main_exe))
    lines.append("Tamanho......: %.1f MB em %d arquivos"
                 % (app.size_bytes / 1e6, app.files_found))
    lines.append("Estrategia...: %s" % strategy)
    lines.append("Saida........: %s" % output_format)
    lines.append("-" * 60)
    lines.append("DIAGNOSTICO DE VIABILIDADE")
    if not app.risks:
        lines.append("[OK] Nenhuma dependencia profunda detectada "
                     "(servicos/drivers/shell extensions).")
    for r in app.notes:
        lines.append("[INFO] " + r)
    for w in warnings:
        lines.append("[AVISO] " + w)
    for b in blocked:
        lines.append("[BLOQUEADO] " + b)
    lines.append("-" * 60)
    lines.append("ARTEFATOS DE LICENCA/TRIAL DETECTADOS (varredura generica)")
    if trial_info.get("registry_values"):
        for e in trial_info["registry_values"]:
            lines.append("  REG %s\\%s -> %s (valor atual: %s)"
                         % (e["hive"], e["path"], e["name"], e["current"]))
    if trial_info.get("files"):
        for e in trial_info["files"]:
            lines.append("  ARQ %s (%s)" % (e["path"], e.get("note", "")))
    if not trial_info.get("registry_values") and not trial_info.get("files"):
        lines.append("  Nenhum padrao conhecido de trial/contador foi identificado.")
    lines.append("")
    lines.append("LIMITACOES CONHECIDAS DO MVP")
    lines.append("- DLLs compartilhadas sao resolvidas por 'ponte': o launcher adiciona a")
    lines.append("  pasta do pacote ao PATH; se o programa exigir uma DLL de sistema")
    lines.append("  especifica, copie-a manualmente para Data\\Sandbox.")
    lines.append("- Chaves HKLM protegidas exigem executar o launcher como administrador")
    lines.append("  na primeira execucao.")
    lines.append("- Servicos, drivers e integracoes de shell nao podem ser clonados (MANUAL).")
    lines.append("- O reset de contadores de uso atua apenas sobre os artefatos listados")
    lines.append("  acima; protecoes avancadas (dongle, licenca por servidor, time-bomb")
    lines.append("  criptografada) vao alem do escopo deste MVP.")
    lines.append("=" * 60)
    return "\n".join(lines)


def clone_program(app, output_dir: str, output_format: str = "PASTA",
                  force_strategy: Optional[str] = None,
                  trial_bypass: bool = False, trial_mode: str = "generico",
                  progress=None) -> Path:
    """Executa a clonagem completa. Retorna o caminho do artefato final."""
    strategy = force_strategy or app.strategy
    warnings: List[str] = []
    blocked: List[str] = []
    src = Path(app.install_location or os.path.dirname(app.main_exe or ""))
    if not src.is_dir():
        raise CloneError("Pasta de origem invalida: %s" % src)
    if "service" in app.risks or "driver" in app.risks:
        blocked.append("Dependencia de servico/driver detectada - o programa pode nao "
                       "funcionar fora da instalacao original.")
    if strategy == "MANUAL":
        raise CloneError("Estrategia MANUAL exige intervencao humana; escolha "
                         "SANDBOX ou LAUNCHER para prosseguir.")

    safe_name = "".join(c if c.isalnum() or c in " ._-_" else "_" for c in app.name).strip()
    pkg = Path(output_dir) / ("%s.Portable" % safe_name)
    if pkg.exists():
        shutil.rmtree(pkg, ignore_errors=True)
    data = pkg / "Data"
    sandbox = data / "Sandbox"
    regdir = data / "Registry"
    sandbox.mkdir(parents=True)

    # 1) copia de arquivos
    if progress:
        progress(0, "Copiando arquivos de %s ..." % src)
    nfiles = copy_tree(src, sandbox, progress)
    if nfiles == 0:
        raise CloneError("Nenhum arquivo copiado - nada para clonar.")

    # 2) registro
    reglog: List[str] = []
    keys = list(app.reg_keys) + collect_app_reg_keys(app.name)
    seen = set()
    keys = [k for k in keys if not (k in seen or seen.add(k))]
    nreg = export_registry_keys(keys, regdir, reglog) if IS_WIN else 0
    if not keys:
        warnings.append("Nenhuma chave de registro correspondente foi localizada.")

    # 3) snapshot de trial (item 7)
    trial_info = {"registry_values": [], "files": []}
    if trial_bypass:
        trial_info = capture_trial_snapshot(app.name, keys,
                                            data / "trial_snapshot.json", reglog)

    # 4) manifest + launcher
    rel_exe = ""
    if app.main_exe and Path(app.main_exe).exists():
        try:
            rel_exe = str(Path(app.main_exe).resolve().relative_to(src.resolve()))
        except ValueError:
            rel_exe = Path(app.main_exe).name
    manifest = {
        "app_name": app.name,
        "app_version": app.version,
        "publisher": app.publisher,
        "main_exe": rel_exe,
        "strategy": strategy,
        "output_format": output_format,
        "cloned_at": _now(),
        "portabilis_version": "1.0.0-MVP",
        "files_copied": nfiles,
        "reg_files": nreg,
        "trial_bypass_enabled": trial_bypass,
        "trial_reset_mode": trial_mode if trial_bypass else None,
        "apply_registry_on_first_run": True,
        "seed_from_real_appdata": True,
        "report": "RELATORIO.txt",
    }
    (data / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    launcher_src = pkg / "launcher_source.py"
    launcher_src.write_text(LAUNCHER_SRC, encoding="utf-8")
    _build_launcher_exe(launcher_src, pkg / "PortabilisLauncher.exe", warnings)

    # 5) relatorios
    report = build_report(app, strategy, output_format, trial_info, warnings, blocked)
    (pkg / "RELATORIO.txt").write_text(report, encoding="utf-8")
    (data / "clone_log.txt").write_text("\n".join(reglog), encoding="utf-8")
    (pkg / "LEIA-ME.txt").write_text(
        "Para executar o programa clonado:\r\n"
        "  1. Abra esta pasta.\r\n"
        "  2. Execute PortabilisLauncher.exe (como administrador na 1a vez,\r\n"
        "     se houver chaves HKLM).\r\n\r\n"
        "Leia RELATORIO.txt antes: ele lista dificuldades/impossibilidades\r\n"
        "da clonagem ANTES da execucao.\r\n", encoding="utf-8")

    # 6) formato de saida (item 9)
    if output_format == "SFX":
        artifact = _make_sfx(pkg, Path(output_dir), safe_name, warnings)
    elif output_format == "EXE":
        artifact = _make_onefile_exe(pkg, Path(output_dir), safe_name, warnings)
    elif output_format == "ZIP":
        artifact = _make_zip(pkg, Path(output_dir), safe_name)
        shutil.rmtree(pkg, ignore_errors=True)
    else:
        artifact = pkg
    if progress:
        progress(nfiles, "Concluido: %s" % artifact)
    return artifact


def _build_launcher_exe(py_src: Path, exe_out: Path, warnings: List[str]):
    """Compila o launcher para .exe com PyInstaller (usa o proprio interpretador)."""
    py = sys.executable
    try:
        r = run([py, "-m", "PyInstaller", "--onefile", "--console", "--name",
                 "PortabilisLauncher", "--distpath", str(exe_out.parent),
                 "--workpath", str(exe_out.parent / "_build"),
                 "--specpath", str(exe_out.parent / "_build"),
                 "--noconfirm", str(py_src)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=900)
        produced = exe_out.parent / "PortabilisLauncher.exe"
        if r.returncode == 0 and produced.exists():
            if produced != exe_out and exe_out.exists():
                exe_out.unlink()
            produced.rename(exe_out)
            shutil.rmtree(exe_out.parent / "_build", ignore_errors=True)
            py_src.unlink(missing_ok=True)
            return
    except Exception:
        pass
    warnings.append("PyInstaller indisponivel: launcher distribuindo como "
                    "launcher_source.py + PortabilisLauncher.bat (requer Python). "
                    "Instale 'pip install pyinstaller' para gerar .exe nativo.")
    bat = exe_out.with_suffix(".bat")
    bat.write_text('@echo off\r\npython "%~dp0launcher_source.py" %*\r\n',
                   encoding="ascii")


def _make_sfx(pkg: Path, out_dir: Path, name: str, warnings: List[str]) -> Path:
    """SFX unico via iexpress (nativo do Windows). Fallback: ZIP + aviso."""
    sfx = out_dir / ("%s.Portable.exe" % name)
    sed = out_dir / (name + ".sed")
    sed.write_text(
        "[Version]\r\n"
        "Class=IEXPRESS\r\n"
        "TargetName=%s\r\n"
        "FriendlyName=%s Portable\r\n"
        "SetupType=0\r\n"
        "Package=1\r\n"
        "[Options]\r\n"
        "WindowTitle=%s\r\n"
        "ButtonText=Instalar\r\n"
        "RunProgram=Internal\\%%PACKAGEDIR%%\\PortabilisLauncher.exe\r\n"
        "RebootNo\r\n"
        "[SourceFiles]\r\n"
        "SourceFiles0=%%PACKAGEDIR%%\r\n"
        "SourceFiles00=\r\n" % (name, name, name), encoding="ascii")
    try:
        r = run(["iexpress", "/N", str(sed), "/Q"], timeout=900)
        if sfx.exists() and r.returncode == 0:
            sed.unlink(missing_ok=True)
            shutil.rmtree(pkg, ignore_errors=True)
            return sfx
    except Exception:
        pass
    warnings.append("iexpress nao produziu o SFX nesta maquina; fallback para ZIP.")
    try:
        sed.unlink(missing_ok=True)
    except OSError:
        pass
    z = _make_zip(pkg, out_dir, name)
    shutil.rmtree(pkg, ignore_errors=True)
    return z


ONEFILE_WRAPPER_SRC = r'''# -*- coding: utf-8 -*-
"""Portabilis OneFile - extrai o pacote embutido e lanca o programa clonado.

Compilado com PyInstaller --onefile (mesmo estilo do build_exe.bat do
Portabilis). Ao executar:
  1. Extrai os arquivos empacotados para "<nome-do-exe>.Data" ao lado do .exe
     (se a pasta de destino permitir escrita; senao usa %TEMP%).
  2. Executa PortabilisLauncher.exe de la (que prepara registro/AppData e roda
     o programa clonado).
Na segunda execucao em diante a extracao e pulada (usa a pasta existente),
entao dados salvos pelo programa sao preservados entre execucoes - igual a um
aplicativo portable de pendrive.
"""
import os
import sys
import subprocess

APP_NAME = "@@NAME@@"

def is_bundle():
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")

def payload_root():
    if is_bundle():
        base = os.path.join(sys._MEIPASS, "payload")
        if os.path.isdir(base):
            return base
    # modo desenvolvimento: payload ao lado deste script
    here = os.path.dirname(os.path.abspath(__file__))
    cand = os.path.join(here, "payload")
    if os.path.isdir(cand):
        return cand
    raise SystemExit("ERRO: pacote interno 'payload' nao encontrado.")

def exe_dir():
    if is_bundle():
        return os.path.dirname(os.path.abspath(sys.argv[0]))
    return os.path.dirname(os.path.abspath(__file__))

def target_dir():
    """Pasta destino da extracao: ao lado do .exe se gravavel, senao TEMP."""
    dest = os.path.join(exe_dir(), APP_NAME + ".Data")
    try:
        os.makedirs(dest, exist_ok=True)
        probe = os.path.join(dest, ".write_test")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        return dest
    except OSError:
        tmp = os.path.join(os.environ.get("TEMP", "."), APP_NAME + ".Portable")
        os.makedirs(tmp, exist_ok=True)
        return tmp

def extract(src_root, dst):
    import shutil
    marker = os.path.join(dst, ".extracted_ok")
    stamp = os.path.join(dst, ".stamp")
    src_stamp = os.path.join(src_root, ".stamp")
    want = str(_payload_count(src_root))
    try:
        have = open(stamp).read().strip() if os.path.exists(stamp) else ""
    except OSError:
        have = ""
    if os.path.exists(marker) and have == want:
        return  # ja extraido anteriormente
    for dirpath, dirnames, filenames in os.walk(src_root):
        rel = os.path.relpath(dirpath, src_root)
        outdir = os.path.normpath(os.path.join(dst, rel))
        os.makedirs(outdir, exist_ok=True)
        for fn in filenames:
            if fn == ".stamp":
                continue
            s = os.path.join(dirpath, fn)
            d = os.path.join(outdir, fn)
            if not os.path.exists(d) or os.path.getmtime(s) > os.path.getmtime(d):
                shutil.copy2(s, d)
    with open(stamp, "w") as f:
        f.write(want)
    with open(marker, "w") as f:
        f.write("ok")

def _payload_count(root):
    n = 0
    for _, _, files in os.walk(root):
        n += len(files)
    return n

def main():
    src = payload_root()
    dst = target_dir()
    print("Portabilis OneFile - %s" % APP_NAME)
    print("Extraindo/atualizando pacote portavel em: %s" % dst)
    extract(src, dst)
    launcher = os.path.join(dst, "PortabilisLauncher.exe")
    if os.path.exists(launcher):
        subprocess.Popen([launcher], cwd=dst)
        return 0
    fallback_py = os.path.join(dst, "launcher_source.py")
    if os.path.exists(fallback_py):
        subprocess.Popen([sys.executable, fallback_py], cwd=dst)
        return 0
    print("ERRO: PortabilisLauncher.exe nao foi gerado (PyInstaller ausente na "
          "clone?). Use o formato PASTA ou instale 'pip install pyinstaller'.")
    return 1

if __name__ == "__main__":
    rc = main()
    if is_bundle() and rc:
        input("Pressione Enter para sair...")
    sys.exit(rc)
'''


def _make_onefile_exe(pkg: Path, out_dir: Path, name: str,
                      warnings: List[str]) -> Path:
    """Unico .exe onefile (estilo build_exe.bat): empacota a pasta inteira do
    clone dentro de um executavel que extrai e roda o launcher ao ser aberto."""
    ext = ".exe" if IS_WIN else ""
    exe_out = out_dir / ("%s.Portable%s" % (name, ext))
    work = pkg / "_onefile_build"
    work.mkdir(exist_ok=True)
    payload = work / "payload"
    # move o conteudo do pacote para dentro de payload/ (sem o diretorio raiz)
    payload.mkdir(exist_ok=True)
    for child in list(pkg.iterdir()):
        if child != work:
            shutil.move(str(child), str(payload / child.name))
    # carimbo para detectar reextracao quando o conteudo mudar
    (payload / ".stamp").write_text(str(sum(1 for _ in payload.rglob("*") if _.is_file())),
                                    encoding="ascii")
    wrapper = work / ("onefile_%d.py" % (abs(hash(name)) % 9999))
    wrapper.write_text(ONEFILE_WRAPPER_SRC.replace("@@NAME@@", name),
                           encoding="utf-8")
    py = sys.executable
    try:
        r = run([py, "-m", "PyInstaller", "--onefile", "--console",
                 "--name", "%s.Portable" % name,
                 "--distpath", str(out_dir),
                 "--workpath", str(work / "build"),
                 "--specpath", str(work),
                 "--add-data", "%s%spayload" % (payload, os.pathsep),
                 "--noconfirm", str(wrapper)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1800)
        produced = out_dir / ("%s.Portable%s" % (name, ext))
        if r.returncode == 0 and produced.exists():
            shutil.rmtree(pkg, ignore_errors=True)
            return produced
    except Exception:
        pass
    warnings.append("PyInstaller indisponivel: nao foi possivel gerar o EXE "
                    "onefile; fallback para ZIP.")
    shutil.rmtree(work, ignore_errors=True)
    z = _make_zip(pkg, out_dir, name)
    shutil.rmtree(pkg, ignore_errors=True)
    return z


def _make_zip(pkg: Path, out_dir: Path, name: str) -> Path:
    zp = out_dir / ("%s.Portable.zip" % name)
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(pkg.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(pkg.parent))
    return zp
