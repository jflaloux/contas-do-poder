"""Onde cada robô roda: no GitHub Actions, nos EUA ("exterior"), ou no Mac do Jean-François, no Brasil ("brasil").

Vários portais de estados e capitais só abrem de dentro do Brasil. A rodada semanal do GitHub Actions (terça de manhã)
pega o que abre de fora; a rodada do Mac (rotina/semana-brasil.sh, depois dela) pega o resto. Para as duas não
brigarem no Git, cada uma anota as suas tentativas num arquivo só seu:

    dados/processados/coletas_exterior.json   (GitHub Actions)
    dados/processados/coletas_brasil.json     (Mac)

com, para cada fonte ("vereadores/maceio", "folhas/RN", "assembleias/df"...): a última tentativa, o último sucesso,
quantas falhas seguidas e o último erro. É daí que sai o relatório de situação (coleta/situacao.py).

Quem roda o quê:
- exterior: tudo, menos as fontes de SO_BRASIL e as que falharam nas 2 últimas tentativas de fora e funcionam do
  Brasil (essas o exterior tenta de novo uma vez por mês, para ver se voltaram a abrir de fora);
- brasil (python3 coletar.py brasil): as fontes de SO_BRASIL, as que falharam na última tentativa de fora e as que
  nunca rodaram de fora. Assim, o que deixar de abrir no exterior passa sozinho para o Mac na mesma semana.

O lugar vem da variável CONTAS_ONDE ("exterior" ou "brasil"); sem ela, é "exterior" dentro do GitHub Actions e
"brasil" no resto (o Mac e o Cowork).
"""
import json
import os
from contextlib import contextmanager
from datetime import datetime, timedelta

from .config import PROCESSADOS
from .util import TempoEsgotado, log

LUGAR = os.environ.get("CONTAS_ONDE") or ("exterior" if os.environ.get("GITHUB_ACTIONS") else "brasil")
LUGARES = ("exterior", "brasil")
# coletar.py brasil liga isto: no Brasil, só as fontes que o exterior não pega (ver precisa_brasil). Rodando uma etapa à
# mão no Mac (coletar.py vereadores), roda tudo.
SO_O_QUE_FALTA = False

# Fontes que não abrem de fora do Brasil (conferido em 01/10/2026 de um servidor nos EUA e do Mac). Em dúvida, a fonte
# fica fora daqui: se falhar no exterior, o Mac passa a rodá-la sozinho (ver precisa_brasil).
SO_BRASIL = {
    "vereadores": {"belo_horizonte", "fortaleza", "maceio", "manaus", "natal", "porto_alegre", "rio_de_janeiro", "sao_luis"},
    "prefeituras": {"natal"},
    "assembleias": {"al", "am", "ap", "df", "es", "go", "ma", "rs"},
    "folhas": {"AL", "AM", "CE", "MA", "PA", "PB", "PI", "RJ", "RN", "SE"},
    "tce": set(),
    "federal": set(),
}


def _arquivo(lugar):
    return PROCESSADOS / f"coletas_{lugar}.json"


def ler(lugar):
    arq = _arquivo(lugar)
    try:
        return json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}
    except ValueError:
        return {}


def _gravar(lugar, dados):
    _arquivo(lugar).write_text(json.dumps(dict(sorted(dados.items())), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def chave(grupo, fonte):
    """"vereadores/maceio" (módulo), "folhas/RN" (UF)."""
    nome = fonte if isinstance(fonte, str) else fonte.__name__.rsplit(".", 1)[-1]
    return f"{grupo}/{nome}"


def _so_brasil(ch):
    grupo, nome = ch.split("/", 1)
    return nome in SO_BRASIL.get(grupo, set())


def _agora():
    return datetime.now().isoformat(timespec="seconds")


def precisa_brasil(ch):
    """A rodada do Brasil deve rodar esta fonte?"""
    if _so_brasil(ch):
        return True
    fora = ler("exterior").get(ch)
    return not fora or fora.get("falhas", 0) > 0


def pular(grupo, fonte):
    """True se esta rodada deve pular a fonte (e diz por quê no log)."""
    ch = chave(grupo, fonte)
    if LUGAR == "brasil":
        return SO_O_QUE_FALTA and not precisa_brasil(ch)
    if _so_brasil(ch):
        log(f"  {ch}: só abre do Brasil, fica para a rodada do Mac")
        return True
    fora, br = ler("exterior").get(ch, {}), ler("brasil").get(ch, {})
    if fora.get("falhas", 0) >= 2 and br.get("ultimo_sucesso"):
        ultima = datetime.fromisoformat(fora.get("ultima_tentativa", "2000-01-01T00:00:00"))
        if datetime.now() - ultima < timedelta(days=28):
            log(f"  {ch}: falhou {fora['falhas']} vezes de fora e funciona do Brasil, fica para a rodada do Mac")
            return True
    return False


@contextmanager
def registrar(grupo, fonte):
    """Anota a tentativa e o resultado (o erro não sai daqui: quem chama decide se a falha para os outros)."""
    ch = chave(grupo, fonte)
    dados = ler(LUGAR)
    item = dados.setdefault(ch, {})
    item["ultima_tentativa"] = _agora()
    try:
        yield
    except TempoEsgotado:
        item["ultimo_erro"] = "tempo máximo da rodada (continua na próxima)"
        _gravar(LUGAR, dados)
        raise
    except Exception as e:  # noqa: BLE001
        item["falhas"] = item.get("falhas", 0) + 1
        item["ultimo_erro"] = f"{type(e).__name__}: {e}"[:300]
        item["ultima_falha"] = item["ultima_tentativa"]
        _gravar(LUGAR, dados)
        raise
    item["falhas"] = 0
    item["ultimo_sucesso"] = item["ultima_tentativa"]
    _gravar(LUGAR, dados)
