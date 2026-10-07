#!/bin/bash
# Fim da rodada do GitHub: uma linha clara no resumo da execução e, se a rodada não salvou e já faz mais de 9 dias que o robô não
# salva nada (a rodada é semanal: a anterior também não salvou), uma issue no repositório (uma só: as seguintes viram
# comentário nela). Falha do `gh` não cala o aviso nem duplica a issue: vira ::warning:: na execução.
#
# Variáveis: RUNNER_TEMP ($RUNNER_TEMP/salvo existe se a rodada salvou; $RUNNER_TEMP/motivo.txt diz por que não),
# TRABALHO_GUARDADO (sim/nao: o pacote da coleta foi para o cache), GITHUB_RUN_ID, GITHUB_STEP_SUMMARY, GITHUB_REPOSITORY, GH_TOKEN,
# e o comando `gh` (opcional: sem ele, não abre issue).
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
if [ "${TRABALHO_GUARDADO:-nao}" = "sim" ]; then
  LINHA="$LINHA O trabalho da coleta foi guardado no cache do repositório (chave trabalho-${GITHUB_RUN_ID:-?}; privado, some se ficar 7 dias sem uso) e os downloads no cache de downloads. Para continuar sem coletar de novo, depois de consertar o que falhou: Actions > Atualizar dados > Run workflow, marque \"retomar\" e ponha run_id = ${GITHUB_RUN_ID:-?}."
else
  LINHA="$LINHA O trabalho da coleta não foi guardado (a rodada parou antes dela ou o pacote não pôde ser feito); rode de novo."
fi
{ echo "### Rodada NÃO salva"; echo "$LINHA"; } >> "$RESUMO"
echo "::error::$LINHA"
command -v gh >/dev/null 2>&1 || exit 0
[ -n "${GH_TOKEN:-}" ] || exit 0
# faz mais de 9 dias que o robô não envia nada? (a rodada anterior também não salvou). Medido pelos commits "Atualização dos
# dados" do robô, e não pela conclusão da rodada anterior (que pode ser vermelha por causa do aviso final, mesmo tendo salvo).
DESDE=$(date -u -d "9 days ago" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -v-9d +%Y-%m-%dT%H:%M:%SZ)
if ! RECENTES=$(gh api "repos/${GITHUB_REPOSITORY:-?}/commits?since=$DESDE&per_page=100" --jq '[.[] | select(.commit.message | startswith("Atualização dos dados"))] | length' 2>&1); then
  echo "::warning::Não deu para consultar os commits do robô (gh api: ${RECENTES:0:120}); nenhuma issue foi aberta."
  exit 0
fi
[ "$RECENTES" = "0" ] || exit 0
TITULO="A rodada semanal de dados não salva nada há mais de uma semana"
CORPO="A rodada ${GITHUB_RUN_ID:-?} não salvou: $MOTIVO. O robô não envia dados ao repositório desde antes de $DESDE. Veja a execução (https://github.com/${GITHUB_REPOSITORY:-?}/actions/runs/${GITHUB_RUN_ID:-?}). Se a coleta chegou a rodar, o trabalho pode ser retomado (Run workflow, retomar, run_id=${GITHUB_RUN_ID:-?})."
if ! ABERTA=$(gh issue list --state open --search "\"$TITULO\" in:title" --json number --jq '.[0].number' 2>&1); then
  echo "::warning::Não deu para listar as issues (gh issue list: ${ABERTA:0:120}); nenhuma issue foi aberta, para não duplicar."
  exit 0
fi
if [ -n "$ABERTA" ] && [ "$ABERTA" != "null" ]; then
  gh issue comment "$ABERTA" --body "$CORPO" >/dev/null 2>&1 || echo "::warning::Não deu para comentar na issue $ABERTA."
else
  gh issue create --title "$TITULO" --body "$CORPO" >/dev/null 2>&1 || echo "::warning::Não deu para abrir a issue."
fi
exit 0
