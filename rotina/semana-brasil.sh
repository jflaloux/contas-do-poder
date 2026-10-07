#!/bin/bash
# Rodada mensal do Brasil: roda num computador no Brasil, com macOS (launchd, ver rotina/instalar-mac.sh) e pega as fontes que só
# abrem de dentro do Brasil (e as que falharam de fora), depois da rodada do GitHub Actions (semanal, terça de manhã, nos EUA).
#
# O launchd chama este script todo dia às 13h07; ele só trabalha uma vez por mês, a partir da terceira terça-feira (a
# primeira terça depois do dia 14, às 11h, depois da rodada do GitHub daquela manhã: a folha do mês anterior já saiu na
# maioria das fontes), e tenta de novo nos dias seguintes se o Mac estava desligado ou se algo deu errado.
#
#   1. confere que não há mudança sem commit nos arquivos de dados (se houver, alguém está trabalhando: tenta amanhã);
#   2. git pull (traz o que o GitHub coletou) e instala o que faltar do requirements.txt no .venv;
#   3. python coletar.py brasil (coleta/onde.py diz o que rodar: pula as fontes congeladas e as que já estão em dia;
#      os arquivos do site são refeitos a partir dos CSVs);
#   4. commit só dos dados e push. Se o push conflitar com outra rodada, refaz os arquivos do site e tenta de novo.
#   5. avisa no Mac (Central de Notificações) o resultado: primeiro o que quebrou desde a rodada anterior
#      (dados/processados/rodada-resumo.json), depois as fontes com problema (dados/processados/situacao.md).
#
# Uso à mão: rotina/semana-brasil.sh --agora   (ignora o "uma vez por mês")
#            rotina/semana-brasil.sh --sem-push (faz o commit, mas não envia)
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO" || exit 1
PY="$REPO/.venv/bin/python"
ESTADO="$HOME/Library/Application Support/ContasDoPoder"
LOGS="$HOME/Library/Logs/ContasDoPoder"
mkdir -p "$ESTADO" "$LOGS"
LOG="$LOGS/semana-brasil-$(date +%Y-%m-%d).log"
exec >>"$LOG" 2>&1
export CONTAS_ONDE=brasil PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
# o que o commit leva (só dados e arquivos do site gerados a partir deles)
DADOS=(dados/municipios dados/municipios_tce dados/assembleias dados/governadores dados/processados/coletas_brasil.json
       dados/processados/situacao.md dados/processados/situacao.json dados/processados/rodada-resumo.json site/dados site/fotos)

avisar() { osascript -e "display notification \"$2\" with title \"Contas do Poder\" subtitle \"$1\"" >/dev/null 2>&1 || true; echo "AVISO: $1 — $2"; }

echo "=== $(date '+%d/%m/%Y %H:%M') ==="
AGORA=0; PUSH=1
for a in "$@"; do [ "$a" = "--agora" ] && AGORA=1; [ "$a" = "--sem-push" ] && PUSH=0; done

# uma vez por mês: a partir da terceira terça-feira (a primeira terça depois do dia 14) às 11h (a rodada do GitHub
# começa às 8h17; a primeira com o cache vazio chega a ~5h, as seguintes são bem mais curtas: se o GitHub ainda
# estiver salvando, o push é refeito sobre o que ele salvou, como abaixo)
if [ "$AGORA" = 0 ]; then
  if ! "$PY" - "$ESTADO/ultima-rodada" <<'PYEOF'
import os, sys
from datetime import datetime, timedelta

def terca(ano, mes):
    d = datetime(ano, mes, 15, 11)
    return d + timedelta(days=(1 - d.weekday()) % 7)

agora = datetime.now()
vez = terca(agora.year, agora.month)
if vez > agora:  # a deste mês ainda não chegou: vale a do mês passado
    vez = terca(agora.year - (agora.month == 1), 12 if agora.month == 1 else agora.month - 1)
ultima = datetime.fromisoformat(open(sys.argv[1]).read().strip()) if os.path.exists(sys.argv[1]) else datetime(2000, 1, 1)
sys.exit(0 if ultima < vez else 1)
PYEOF
  then echo "Já rodou neste mês (a próxima é a partir da terceira terça-feira do mês que vem)."; exit 0; fi
fi

if [ -f .git/index.lock ] || [ -n "$(git status --porcelain --untracked-files=no -- "${DADOS[@]}" coleta coletar.py)" ]; then
  avisar "Rodada adiada" "Há mudanças sem commit no projeto (alguém trabalhando nele). Tento de novo amanhã."
  exit 0
fi

git fetch --quiet || { avisar "Rodada parou" "git fetch falhou (sem internet?); veja $LOG"; exit 1; }
# commits feitos à mão que ainda esperam o push: a rodada não os envia
ESPERANDO=$(git rev-list --count origin/main..HEAD)
if [ "$ESPERANDO" -gt 0 ] && [ "$PUSH" = 1 ]; then
  PUSH=0; echo "$ESPERANDO commits esperando o push: a rodada faz o commit, mas não envia."
fi
git pull --rebase --quiet || { git rebase --abort 2>/dev/null; avisar "Rodada parou" "git pull falhou; veja $LOG"; exit 1; }
# o mesmo ambiente das duas rodadas: o que faltar do requirements.txt (em 02/10/2026 uma fonte falhou só por isso)
"$REPO/.venv/bin/pip" install --quiet --disable-pip-version-check -r requirements.txt || avisar "Aviso" "pip install falhou; a rodada segue; veja $LOG"

"$PY" coletar.py brasil
STATUS=$?
if [ $STATUS -ne 0 ]; then
  avisar "Rodada com erro" "coletar.py brasil terminou com erro $STATUS; veja $LOG"
fi

git add -- "${DADOS[@]}" 2>/dev/null
# gravações recusadas por perda de cobertura (coleta/util.py, gravar_com): só existe depois da primeira recusa
[ -f dados/processados/recusas_brasil.json ] && git add -- dados/processados/recusas_brasil.json
if git diff --cached --quiet; then
  echo "Nada mudou."
else
  git commit --quiet -m "Atualização dos dados (rodada do Brasil): $(date +%d/%m/%Y)" || { avisar "Rodada parou" "commit falhou; veja $LOG"; exit 1; }
  if [ "$PUSH" = 1 ]; then
    for tentativa in 1 2 3; do
      git push --quiet && break
      echo "push recusado (tentativa $tentativa): trazendo a outra rodada"
      if ! git pull --rebase --quiet; then
        # conflito: só pode ser nos arquivos do site gerados (os CSVs de cada rodada são de fontes diferentes); fica a
        # versão de lá, e os arquivos do site são refeitos a partir dos CSVs juntos
        CONFLITOS=$(git diff --name-only --diff-filter=U)
        if echo "$CONFLITOS" | grep -qvE '^(site/dados/|site/fotos/creditos.json|dados/processados/(situacao|rodada-resumo))'; then
          git rebase --abort; avisar "Rodada parou" "conflito do Git fora dos arquivos gerados: $CONFLITOS"; exit 1
        fi
        echo "$CONFLITOS" | xargs git checkout --ours --
        echo "$CONFLITOS" | xargs git add --
        GIT_EDITOR=true git rebase --continue || { git rebase --abort; avisar "Rodada parou" "rebase falhou; veja $LOG"; exit 1; }
        "$PY" coletar.py montar && git add -- "${DADOS[@]}" && { git diff --cached --quiet || git commit --quiet -m "Arquivos do site refeitos depois das duas rodadas"; }
      fi
    done
    git status -sb | head -1 | grep -q ahead && { avisar "Rodada sem envio" "o push não foi; veja $LOG"; exit 1; }
  fi
fi

"$PY" -c "from datetime import datetime; print(datetime.now().isoformat(timespec='seconds'))" > "$ESTADO/ultima-rodada"
# o que mudou desde a rodada anterior (vazio na primeira rodada com resumo): "título|fontes"
NOVIDADE=$("$PY" - <<'PYEOF' 2>/dev/null
import json
r = json.load(open("dados/processados/rodada-resumo.json"))
nomes = lambda l: ", ".join(i["fonte"] for i in l[:5])
q, v, c = r["quebrou"], r["voltou"], r["continua"]
if q:
    print(f"Rodada feita: {len(q)} quebraram desde a rodada anterior|{nomes(q)}")
elif r["anterior"] and c:
    print(f"Rodada feita: nada quebrou de novo, {len(c)} continuam com problema|{nomes(c)}")
elif v:
    print(f"Rodada feita: {len(v)} voltaram e nenhuma quebrou|{nomes(v)}")
PYEOF
)
PROBLEMAS=$(grep -cE '\| (falhando|atrasada) \|' dados/processados/situacao.md 2>/dev/null || echo 0)
if [ -n "$NOVIDADE" ]; then
  avisar "${NOVIDADE%%|*}" "${NOVIDADE#*|}"
elif [ "$PROBLEMAS" -gt 0 ]; then
  avisar "Rodada feita, $PROBLEMAS fontes com problema" "$(grep -E '\| (falhando|atrasada) \|' dados/processados/situacao.md | cut -d'|' -f2 | tr -s ' ' | head -5 | tr '\n' ',')"
else
  avisar "Rodada feita" "Todas as fontes em dia."
fi
[ "$PUSH" = 0 ] && [ "$ESPERANDO" -gt 0 ] && avisar "Commits esperando o push" "$ESPERANDO commits feitos à mão + a rodada. Confira e faça o git push."
exit 0
