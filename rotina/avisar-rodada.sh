#!/bin/bash
# Fim da rodada do GitHub: uma linha clara no resumo da execução e, se esta e a rodada anterior não salvaram, uma issue no
# repositório (uma só: as seguintes viram comentário nela).
#
# Entradas (variáveis): RUNNER_TEMP ($RUNNER_TEMP/salvo existe se a rodada salvou; $RUNNER_TEMP/motivo.txt diz por que não),
# GITHUB_RUN_ID, GITHUB_STEP_SUMMARY, GITHUB_REPOSITORY, GH_TOKEN, e o comando `gh` (opcional: sem ele, não abre issue).
set -uo pipefail
TEMP="${RUNNER_TEMP:-/tmp}"
RESUMO="${GITHUB_STEP_SUMMARY:-/dev/stdout}"
if [ -f "$TEMP/salvo" ]; then
  echo "### Rodada salva" >> "$RESUMO"
  echo "Os números novos foram enviados ao repositório (ou não havia nada novo)." >> "$RESUMO"
  exit 0
fi
MOTIVO="um passo falhou antes de salvar (veja os passos em vermelho)"
[ -s "$TEMP/motivo.txt" ] && MOTIVO="$(head -c 400 "$TEMP/motivo.txt" | tr '\n' ' ')"
LINHA="NADA FOI SALVO e o site no ar não mudou: $MOTIVO."
if [ -f "$TEMP/trabalho/trabalho.tgz" ]; then
  LINHA="$LINHA O trabalho da coleta ficou no artefato \"trabalho-da-rodada\" (14 dias) e os downloads no cache. Para continuar sem coletar de novo: Actions > Atualizar dados > Run workflow, marque \"retomar\" e ponha run_id = ${GITHUB_RUN_ID:-?}."
else
  LINHA="$LINHA Não havia trabalho de coleta para guardar (a rodada parou antes dela); rode de novo."
fi
{ echo "### Rodada NÃO salva"; echo "$LINHA"; } >> "$RESUMO"
echo "::error::$LINHA"
command -v gh >/dev/null 2>&1 || exit 0
[ -n "${GH_TOKEN:-}" ] || exit 0
# a rodada anterior que terminou (não esta): também não salvou?
ANTERIOR=$(gh run list --workflow "Atualizar dados" --status completed --limit 5 --json databaseId,conclusion \
  --jq "[.[] | select(.databaseId != ${GITHUB_RUN_ID:-0})][0].conclusion" 2>/dev/null || true)
if [ "$ANTERIOR" = "success" ] || [ -z "$ANTERIOR" ]; then exit 0; fi
TITULO="A rodada semanal de dados falhou duas vezes seguidas"
CORPO="A rodada ${GITHUB_RUN_ID:-?} não salvou: $MOTIVO. A anterior terminou com \"$ANTERIOR\". Veja a execução (https://github.com/${GITHUB_REPOSITORY:-?}/actions/runs/${GITHUB_RUN_ID:-?}); se a coleta chegou a rodar, o trabalho está no artefato trabalho-da-rodada e pode ser retomado (Run workflow, retomar=true, run_id=${GITHUB_RUN_ID:-?})."
ABERTA=$(gh issue list --state open --search "\"$TITULO\" in:title" --json number --jq '.[0].number' 2>/dev/null || true)
if [ -n "$ABERTA" ]; then
  gh issue comment "$ABERTA" --body "$CORPO" >/dev/null 2>&1 || true
else
  gh issue create --title "$TITULO" --body "$CORPO" >/dev/null 2>&1 || true
fi
exit 0
