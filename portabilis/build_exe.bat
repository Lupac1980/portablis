@echo off
REM ============================================================
REM  Portabilis - gera o Portabilis.exe portable
REM  Requisitos no Windows: Python 3.10+ no PATH
REM ============================================================
cd /d "%~dp0"
echo [1/3] Verificando Python...
python --version || (echo Python nao encontrado no PATH & exit /b 1)

echo [2/3] Instalando dependencias (pyinstaller)...
python -m pip install --upgrade pip >nul
python -m pip install pyinstaller || (echo Falha ao instalar pyinstaller & exit /b 1)

echo [3/3] Construindo Portabilis.exe ...
python -m PyInstaller Portabilis.spec --noconfirm
if errorlevel 1 (
  echo Falha no build. Tente: python -m PyInstaller --onefile --windowed main.py
  exit /b 1
)

echo.
echo ============================================================
echo  OK! Executavel portable gerado em: dist\Portabilis.exe
echo  Basta copiar esse unico .exe para qualquer pasta/pen-drive.
echo ============================================================
pause
