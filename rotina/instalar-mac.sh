#!/bin/bash
# Instala a rodada mensal do Brasil num computador com macOS (uma vez só): o ambiente Python do projeto (.venv) e um agendamento do
# launchd que chama rotina/semana-brasil.sh todo dia às 13h07 (ele só trabalha uma vez por mês, a partir da terceira
# terça-feira do mês, depois da rodada do GitHub daquela manhã). Se o Mac estiver dormindo nessa hora, o launchd roda
# quando ele acordar.
#
# Uso:          bash rotina/instalar-mac.sh
# Rodar agora:  bash rotina/semana-brasil.sh --agora
# Ver o que fez: ~/Library/Logs/ContasDoPoder/ e dados/processados/situacao.md
# Desinstalar:  launchctl bootout gui/$(id -u)/com.contasdopoder.semana-brasil && rm ~/Library/LaunchAgents/com.contasdopoder.semana-brasil.plist
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
command -v brew >/dev/null || { echo "Precisa do Homebrew (https://brew.sh)."; exit 1; }
brew list poppler >/dev/null 2>&1 || brew install poppler   # pdftotext, para as folhas em PDF da Câmara de Maceió
PYTHON="$(command -v python3.12 || command -v python3.13 || command -v python3)"
echo "Python: $PYTHON ($("$PYTHON" --version))"
[ -x .venv/bin/python ] || "$PYTHON" -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt
.venv/bin/python -c "import coleta.onde, coleta.situacao; print('Projeto importa sem erro.')"

ROTULO=com.contasdopoder.semana-brasil
PLIST="$HOME/Library/LaunchAgents/$ROTULO.plist"
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs/ContasDoPoder"
cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$ROTULO</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>$REPO/rotina/semana-brasil.sh</string></array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>13</integer><key>Minute</key><integer>7</integer></dict>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/ContasDoPoder/launchd.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/ContasDoPoder/launchd.log</string>
</dict>
</plist>
PLISTEOF
launchctl bootout "gui/$(id -u)/$ROTULO" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Instalado: todo dia às 13h07 o Mac confere se já rodou neste mês (a rodada é a partir da terceira terça-feira)."
echo "Para rodar agora: bash rotina/semana-brasil.sh --agora"
