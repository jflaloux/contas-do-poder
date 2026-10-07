#!/bin/bash
# Rede de segurança da rodada do GitHub: quando a rodada NÃO salvou (padronizar, site ou conferência falhou, ou o job estourou),
# guarda o trabalho da coleta num pacote que o workflow envia como artefato do GitHub (14 dias, nunca na main):
#   $RUNNER_TEMP/trabalho/trabalho.tgz   os arquivos de dados/ e site/ alterados ou novos (comparados com o último commit)
#                                        mais dados/brutos (intermediário que a Câmara gera e o padronizar lê; não vai para o Git)
#   $RUNNER_TEMP/trabalho/base.txt       o commit de partida e, de cada arquivo, o hash que ele tinha nesse commit
# O cache de downloads (dados/cache) já é guardado à parte pelo workflow. Para continuar sem coletar de novo, rode o workflow com
# "retomar" e o número desta rodada (rotina/retomar-trabalho.sh). Se a rodada salvou, não faz nada.
set -uo pipefail
TEMP="${RUNNER_TEMP:-/tmp}"
if [ -f "$TEMP/salvo" ]; then echo "A rodada salvou: nada a guardar."; exit 0; fi
DESTINO="$TEMP/trabalho"
rm -rf "$DESTINO"; mkdir -p "$DESTINO"
LISTA="$DESTINO/arquivos.txt"
# alterados e novos (não ignorados) em dados/ e site/, mais os brutos (ignorados pelo Git)
{ git ls-files -m -o --exclude-standard -- dados site; [ -d dados/brutos ] && find dados/brutos -type f; } | sort -u | while IFS= read -r f; do [ -f "$f" ] && echo "$f"; done > "$LISTA"
if [ ! -s "$LISTA" ]; then echo "Nada para guardar."; exit 0; fi
{
  echo "base $(git rev-parse HEAD)"
  while IFS= read -r f; do
    case "$f" in dados/brutos/*) continue;; esac
    echo "arquivo $(git rev-parse -q --verify "HEAD:$f" 2>/dev/null || echo -) $f"
  done < "$LISTA"
} > "$DESTINO/base.txt"
tar czf "$DESTINO/trabalho.tgz" -T "$LISTA"
echo "Trabalho guardado: $(wc -l < "$LISTA") arquivos, $(du -h "$DESTINO/trabalho.tgz" | cut -f1)."
rm -f "$LISTA"
