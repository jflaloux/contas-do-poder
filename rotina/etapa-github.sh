#!/bin/bash
# Roda uma etapa da coleta no GitHub Actions com limite de tempo, sem derrubar a rodada.
#
# Uso:  rotina/etapa-github.sh <etapa> <minutos> [essencial]
#
#   <etapa>     nome da etapa do coletar.py (camara, senado, tce...)
#   <minutos>   tempo máximo desta etapa; ela para sozinha (coletar.py --tempo-max), grava o que já pegou e a rodada
#               continua; o resto é lido na próxima rodada (os robôs retomam de onde pararam)
#   essencial   etapa que não pode ser pulada nem encurtada pelo prazo geral (padronizar, site, situacao); é a única que roda
#               numa rodada retomada (RETOMAR=true)
#
# O prazo geral da rodada vem da variável PRAZO_FIM (segundos desde 1970), posta pelo workflow no começo (325 min depois
# do início): a etapa normal recebe no máximo o que sobra até esse prazo, deixando RESERVA_MIN (70) minutos para as
# etapas essenciais (padronizar 30 + site 15 + situação 5 = 50 no máximo), a conferência e o Git (~20). Conta do pior caso,
# com o job em 355 min: coleta termina em 255 min (+3 de margem do timeout), essenciais até 50 (+9 de margem), conferir e
# salvar ~20: cerca de 340. Se não sobra tempo, a etapa é pulada e fica para a próxima rodada.
#
# A etapa que acaba por tempo (código 3, ou 124 do timeout) não é erro. Qualquer outro código de saída é anotado
# em $RUNNER_TEMP/etapas.txt, e o último passo do workflow (depois de salvar) faz a rodada acabar com erro, para o GitHub avisar,
# sem ter impedido que o resto fosse salvo.
# Este script nunca termina com erro: quem decide é o passo final do workflow.
set -uo pipefail

ETAPA="${1:?etapa}"
MINUTOS="${2:?minutos}"
ESSENCIAL="${3:-}"
RESERVA_MIN="${RESERVA_MIN:-70}"
ANOTACOES="${RUNNER_TEMP:-/tmp}/etapas.txt"

# RETOMAR=true (workflow, "retomar"): o trabalho da coleta veio de uma rodada que não salvou (rotina/retomar-trabalho.sh); só as
# etapas essenciais rodam (padronizar, site, situacao), e as outras ficam como estavam
if [ "${RETOMAR:-false}" = "true" ] && [ -z "$ESSENCIAL" ]; then
  echo "Etapa $ETAPA não roda: rodada retomada (o trabalho da coleta já está aqui)."
  exit 0
fi

agora=$(date +%s)
limite=$((MINUTOS * 60))
if [ -z "$ESSENCIAL" ] && [ -n "${PRAZO_FIM:-}" ]; then
  sobra=$((PRAZO_FIM - agora - RESERVA_MIN * 60))
  if [ "$sobra" -lt 120 ]; then
    echo "::warning::Etapa $ETAPA pulada: acabou o tempo da rodada (fica para a próxima)."
    echo "$ETAPA pulada-por-tempo 0" >> "$ANOTACOES"
    exit 0
  fi
  [ "$sobra" -lt "$limite" ] && limite=$sobra
fi

echo "::group::$ETAPA (até $((limite / 60)) min)"
inicio=$(date +%s)
# --tempo-max: para sozinho entre uma consulta e outra; timeout: rede de segurança para a consulta lenta
# (o SIGTERM vira TempoEsgotado dentro do Python, que grava o que já pegou)
timeout -k 90 "$((limite + 180))" python coletar.py "$ETAPA" --tempo-max "$limite"
rc=$?
fim=$(date +%s)
echo "::endgroup::"
echo "Etapa $ETAPA: código $rc em $(((fim - inicio) / 60)) min $(((fim - inicio) % 60)) s"
echo "$ETAPA $rc $((fim - inicio))" >> "$ANOTACOES"
if [ "$rc" -eq 3 ] || [ "$rc" -eq 124 ]; then
  echo "::warning::Etapa $ETAPA parou por tempo (continua na próxima rodada)."
fi
exit 0
