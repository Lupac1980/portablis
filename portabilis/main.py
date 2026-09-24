# -*- coding: utf-8 -*-
"""Portabilis - ponto de entrada (empacotado como Portabilis.exe pelo PyInstaller)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    try:
        from ui import App
        app = App()
        app.mainloop()
    except Exception as e:  # fallback CLI se nao houver display/tkinter
        print("Interface grafica indisponivel (%s). Modo linha de comando:" % e)
        import cli
        sys.exit(cli.main(["--help"]))


if __name__ == "__main__":
    main()
