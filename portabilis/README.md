# Portabilis 🧉

Clone programas instalados no Windows e execute-os como **portáteis** — MVP focado
funciona para a maioria dos programas
*standalone* (sem dependências profundas de sistema).

## O que o Portabilis faz

| Etapa | Descrição |
|---|---|
| **1 · Detectar** | Lista programas via **(a)** Registro (`HKLM/HKCU\...\CurrentVersion\Uninstall`, a mesma fonte do Painel de Controle) e **(b)** varredura de `.exe` em pastas comuns (Program Files, Desktop, Downloads, `C:\Apps`…) |
| **2 · Analisar** | Gera um **relatório de viabilidade ANTES da execução**: estratégia recomendada (SANDBOX / LAUNCHER / MANUAL), riscos (serviços, drivers, shell extensions), tamanho, e artefatos de licença/trial encontrados |
| **3 · Clonar** | Copia os arquivos do programa, exporta as chaves de registro relevantes (`reg export → *.reg`) e gera um **launcher** que aplica esse contexto antes de executar o programa |

### Estratégias (item 6)
- **SANDBOX (nível ThinApp, pragmática)** – arquivos em `Data\Sandbox`, registro em
  `Data\Registry`, launcher redireciona `APPDATA/LOCALAPPDATA/TEMP` para dentro do pacote.
- **LAUNCHER (fallback)** – cópia + registro exportado + loader de ambiente; é o plano B
  quando a sandbox completa não é suficiente.
- **MANUAL** – apenas relatório (serviços/drivers/kernel não são clonáveis no MVP).

### Reset de contadores de uso / trial (item 7)
- Varredura **genérica** por chaves/arquivos conhecidos (`TrialDays`, `RunCount`,
  `LaunchCount`, `licen*`, `regist*`, `activ*` em Registre + AppData/ProgramData).
- Modo **heurística avançada** opcional (detecta padrões de trial por nome de valor).
- O snapshot é salvo em `Data\trial_snapshot.json`; o launcher zera/restaura na execução.
- ⚠️ Use somente em software que você possui/licenciou. Proteções avançadas
  (dongle, ativação por servidor, time-bomb criptografada) são reportadas como
  impossibilidade no relatório — o MVP não as contorna.

### Formatos de saída (item 9) — escolha na aba "Clonar"
1. **(a) PASTA** – pasta com tudo + `PortabilisLauncher.exe`
2. **(b) SFX** – único `.exe` autoextrativo (via `iexpress` nativo; fallback ZIP)
3. **(c) ZIP** – pacote comprimido para extrair e executar

## Estrutura do código

```
portabilis/
├── main.py            # entrada da GUI (vira Portabilis.exe)
├── ui.py              # interface tkinter dark moderna (3 abas)
├── scan.py            # detecção: registro (a) + varredura .exe (b) + análise de riscos
├── clone.py           # cópia, exportação de registro, trial snapshot, launcher, SFX/ZIP
├── cli.py             # alternativa sem GUI (scan/analyze/clone) p/ automação
├── Portabilis.spec    # spec PyInstaller
├── build_exe.bat      # build com um clique no Windows
└── assets/portabilis.ico
```

O **launcher embutido nos clones** (`launcher_source.py` → compilado como
`PortabilisLauncher.exe`) executa nesta ordem: imprime o relatório de viabilidade
(exige confirmação se houver `[BLOQUEADO]`) → importa os `.reg` na 1ª execução →
redireciona AppData/Temp para o pacote → semeia a config existente → reseta contadores
de trial (se habilitado) → adiciona a pasta do pacote ao `PATH` (**ponte para DLLs**)
e executa o programa alvo.

## Como gerar o Portabilis.exe (portable)

No Windows, com Python 3.10+ instalado:

```bat
cd portabilis
build_exe.bat
```

ou manualmente:

```bat
pip install pyinstaller
pyinstaller Portabilis.spec --noconfirm
```

Resultado: **`dist\Portabilis.exe`** — um único arquivo executável, sem instalação,
copiável para pen-drive.

## Uso

1. Execute `Portabilis.exe` → aba **1 · Detectar** → *Escanear programas*.
2. Selecione o programa desejado na lista (duplo clique vai para a aba 2). A lista é idêntica à do Painel de Controle > "Desinstalar um programa" (inclui apps de 32 bits via WOW6432Node), além da varredura opcional de .exe e da seleção manual do executável.
3. Leia o diagnóstico; escolha SANDBOX ou LAUNCHER; habilite o reset de trial se desejar.
4. Aba **3 · Clonar** → formato de saída → **CLONAR PROGRAMA**.
5. Abra o pacote gerado e execute `PortabilisLauncher.exe`
   (como administrador na 1ª vez, se houver chaves HKLM).

### CLI equivalente

```bat
python cli.py scan
python cli.py analyze "Nome do Programa"
python cli.py clone "Nome do Programa" --out D:\portatil --format PASTA ^
       --strategy LAUNCHER --trial-reset --trial-mode generico
```

## Limitações conhecidas (MVP)

- Não virtualiza serviços NT, drivers nem integrações de shell (reporta MANUAL).
- Chaves HKLM protegidas exigem elevação na primeira execução.
- DLLs compartilhadas: resolvidas pela ponte de `PATH`; DLL de sistema específica
  deve ser copiada manualmente para `Data\Sandbox`.
- Clone 100% fiel nível ThinApp/Cameyo exige monitoramento em tempo real de
  filesystem/registro (minifilter + API hooking) — fora do escopo deste MVP.
