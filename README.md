# Portabilis

Clone programas instalados no Windows em versões **portáteis** — sem instalação, com registro e ambiente isolados. Funciona para a maioria dos programas standalone.

![Plataforma](https://img.shields.io/badge/plataforma-Windows-blue) ![Python](https://img.shields.io/badge/Python-3.8%2B-green) ![Licença](https://img.shields.io/badge/licença-MIT-lightgrey)

## Recursos

- **Detecção de programas**: lista exatamente os mesmos programas do **Painel de Controle > Desinstalar um programa** — percorre `HKLM\SOFTWARE\...\Uninstall` nas visões 64-bit **e** 32-bit/WOW64 (pega aplicativos de 32 bits) mais `HKCU`, resolvendo o executável principal via atalhos do Menu Iniciar (`.lnk`), `DisplayIcon` ou pasta de instalação. Opcionalmente também busca `.exe` soltos em pastas comuns (Desktop, Downloads, C:\Apps...).
- **Análise de viabilidade**: antes de clonar, o Portabilis gera um relatório apontando dependências críticas (serviços, drivers, DLLs em System32, complementos shell) e recomenda a melhor estratégia: `SANDBOX`, `LAUNCHER` ou `MANUAL`.
- **Clonagem pragmática**: copia os arquivos do programa, exporta as chaves de registro relevantes para `.reg` e embute um **launcher** que prepara o contexto (registro local, AppData/ProgramData redirecionados, ponte de DLLs via `PATH`) e executa o programa.
- **Reset de contadores de trial** (opcional): varredura genérica de chaves/valores conhecidos + modo heurístico avançado para detectar padrões de licença/timestamp.
- **3 formatos de saída**:
  - **(a) PASTA** — pasta com todos os arquivos + `Launch_<App>.exe/.bat`;
  - **(b) SFX** — único `.exe` autoextraível (gerado com IExpress nativo do Windows);
  - **(c) ZIP** — pacote comprimido pronto para extrair e usar.
- **Interface gráfica moderna** (dark theme, tkinter) e **CLI** para automação.

## Como gerar o `Portabilis.exe` portable

No Windows, com Python 3.8+ instalado:

```bat
cd portabilis
build_exe.bat
```

O script instala o PyInstaller e gera `dist\Portabilis\Portabilis.exe` — um executável portátil (pasta `dist` completa, copie para um pendrive e execute direto).

## Uso rápido

**GUI:** dê dois cliques em `Portabilis.exe` (ou `python main.py`). A janela tem 3 etapas: **Detectar → Analisar → Clonar**.

**CLI:**

```bat
:: Listar programas detectados
python cli.py --scan

:: Análise + clonagem completa (formato pasta)
python cli.py --clone "Nome do Programa" --out D:\Portable --format pasta

:: Formatos alternativos
python cli.py --clone "Nome do Programa" --out D:\Portable --format sfx
python cli.py --clone "Nome do Programa" --out D:\Portable --format zip

:: Com reset de trial (genérico ou heurístico avançado)
python cli.py --clone "Nome do Programa" --out D:\Portable --reset-trial advanced
```

## Estrutura do projeto

```
portabilis/
├── main.py            # entrada da GUI
├── ui.py              # interface dark em 3 etapas
├── scan.py            # detecção (registro Uninstall + .exe portáteis)
├── clone.py           # análise de viabilidade + motor de clonagem + launcher
├── cli.py             # linha de comando
├── build_exe.bat      # build do executável portable (PyInstaller)
├── Portabilis.spec    # spec do PyInstaller
└── assets/portabilis.ico
```

## Saída da clonagem

```
<App>_Portable/
├── app/                 # arquivos copiados do programa
├── registry/            # chaves exportadas (.reg)
├── data/                # AppData/ProgramData redirecionados
├── Launch_<App>.bat     # launcher (fonte)
├── Launch_<App>.exe     # launcher compilado (se houver PyInstaller)
└── RELATORIO.txt        # log detalhado da clonagem
```

## Limitações conhecidas

Ferramentas comerciais como VMware ThinApp, Cameyo e Spoon Studio levam anos de desenvolvimento para capturar 100% do comportamento de um sistema. O Portabilis entrega uma solução pragmática que cobre bem programas standalone; softwares com drivers, serviços ou integrações profundas de shell podem exigir tratamento manual (o relatório de análise indica exatamente isso).

## Requisitos

- Windows 7/8/10/11 (execução)
- Python 3.8+ apenas para gerar o `.exe` via `build_exe.bat` (tkinter já incluído no instalador padrão do Python)
- Executar preferencialmente como administrador para exportar todo o registro

## Licença

MIT — use por sua conta e risco. Respeite as licenças de software dos programas que você clona.
