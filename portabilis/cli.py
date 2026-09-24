# -*- coding: utf-8 -*-
"""
Portabilis CLI - alternativa sem interface grafica (util para automacao/testes).

Uso:
  python cli.py scan [--no-registry] [--no-filescan] [--json]
  python cli.py analyze "Nome do Programa"
  python cli.py clone "Nome do Programa" --out DIR [--format PASTA|SFX|ZIP|EXE]
                    [--strategy SANDBOX|LAUNCHER] [--trial-reset]
                    [--trial-mode generico|heuristica-avancada]
"""
import os
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scan
import clone


def _find(apps, needle):
    needle = needle.lower()
    exact = [a for a in apps if a.name.lower() == needle]
    if exact:
        return exact[0]
    part = [a for a in apps if needle in a.name.lower()]
    return part[0] if len(part) == 1 else None


def cmd_scan(args):
    apps = scan.full_scan(not args.no_registry, not args.no_filescan)
    if args.json:
        print(json.dumps([a.to_dict() for a in apps], indent=2, ensure_ascii=False))
        return 0
    print("%-45s %-10s %-9s %s" % ("PROGRAMA", "ORIGEM", "ESTRATEGIA", "TAMANHO"))
    print("-" * 80)
    for a in apps:
        src = "registro" if scan.is_registry_source(a.source) else ("manual" if a.source == "manual" else "varredura")
        print("%-45s %-10s %-9s %.1f MB" % (a.name[:44], src, a.strategy,
                                            a.size_bytes / 1e6))
    print("\n%d programa(s)." % len(apps))
    return 0


def cmd_analyze(args):
    apps = scan.full_scan(True, True)
    app = _find(apps, args.name)
    if not app:
        print("Programa nao encontrado ou ambiguo: %s" % args.name)
        return 2
    print(json.dumps(app.to_dict(), indent=2, ensure_ascii=False))
    return 0


def cmd_clone(args):
    apps = scan.full_scan(True, True)
    app = _find(apps, args.name)
    if not app:
        print("Programa nao encontrado ou ambiguo: %s" % args.name)
        return 2
    try:
        art = clone.clone_program(
            app, args.out, args.format, args.strategy,
            args.trial_reset, args.trial_mode,
            progress=lambda n, m: print("[%6d] %s" % (n, m)),
            registry_mode=args.registry_mode)
        print("\nARTEFATO: %s" % art)
        return 0
    except clone.CloneError as e:
        print("BLOQUEADO: %s" % e)
        return 3


def main(argv=None):
    p = argparse.ArgumentParser(prog="portabilis", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd")
    s = sub.add_parser("scan");  s.add_argument("--no-registry", action="store_true")
    s.add_argument("--no-filescan", action="store_true"); s.add_argument("--json", action="store_true")
    a = sub.add_parser("analyze"); a.add_argument("name")
    c = sub.add_parser("clone");   c.add_argument("name")
    c.add_argument("--out", required=True)
    c.add_argument("--format", choices=["PASTA", "SFX", "ZIP", "EXE"], default="PASTA")
    c.add_argument("--strategy", choices=["SANDBOX", "LAUNCHER"], default=None)
    c.add_argument("--trial-reset", action="store_true")
    c.add_argument("--trial-mode", choices=["generico", "heuristica-avancada"],
                   default="generico")
    c.add_argument("--registry-mode", choices=["VIRTUAL", "REG"], default="VIRTUAL",
                   help="VIRTUAL (padrao): registro isolado no pacote, simula 1a execucao. "
                        "REG: importa .reg no registro real do Windows.")
    args = p.parse_args(argv)
    if args.cmd == "scan":
        return cmd_scan(args)
    if args.cmd == "analyze":
        return cmd_analyze(args)
    if args.cmd == "clone":
        return cmd_clone(args)
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
