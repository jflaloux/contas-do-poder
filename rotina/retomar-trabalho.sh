#!/bin/bash
# Restaura o trabalho guardado por rotina/guardar-trabalho.sh (artefato "trabalho-da-rodada" de uma rodada que não salvou),
# para o workflow rodar só padronizar → site → conferir → salvar, com a mesma conferência final.
#
# Uso: rotina/retomar-trabalho.sh <pasta com trabalho.tgz e base.txt>
#
# Recusa (código 1) se algum arquivo de dados/ que o pacote traz mudou na main desde o commit de partida da rodada que falhou
# (por exemplo, a rodada do Brasil enviou outra versão dele): o pacote sobrescreveria o trabalho mais novo. Os arquivos que
# o padronizar/montar refazem de qualquer jeito (site/dados/, dados/processados/, creditos de fotos) não contam como conflito.
set -uo pipefail
PASTA="${1:?pasta do trabalho}"
[ -f "$PASTA/trabalho.tgz" ] && [ -f "$PASTA/base.txt" ] || { echo "Faltam trabalho.tgz e base.txt em $PASTA."; exit 1; }
CONFLITOS=""
while read -r tipo hash arq; do
  [ "$tipo" = "arquivo" ] || continue
  case "$arq" in site/dados/*|dados/processados/*|site/fotos/creditos.json) continue;; esac
  atual=$(git rev-parse -q --verify "HEAD:$arq" 2>/dev/null || echo -)
  [ "$atual" = "$hash" ] || CONFLITOS="$CONFLITOS $arq"
done < "$PASTA/base.txt"
if [ -n "$CONFLITOS" ]; then
  echo "O trabalho guardado não pode ser aplicado: estes arquivos mudaram na main desde a rodada que falhou:$CONFLITOS"
  echo "Rode a rodada completa de novo (sem retomar)."
  exit 1
fi
tar xzf "$PASTA/trabalho.tgz"
echo "Trabalho restaurado (partida $(grep '^base ' "$PASTA/base.txt" | cut -d' ' -f2 | cut -c1-8)): $(grep -c '^arquivo ' "$PASTA/base.txt") arquivos de dados e site, mais os brutos."
