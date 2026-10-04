"""Onde cada robô roda: no GitHub Actions, nos EUA ("exterior"), ou num computador no Brasil ("brasil").

Vários portais de estados e capitais só abrem de dentro do Brasil. A rodada semanal do GitHub Actions (terça de manhã)
pega o que abre de fora; a rodada do Brasil (rotina/semana-brasil.sh, depois dela) pega o resto. Para as duas não
brigarem no Git, cada uma anota as suas tentativas num arquivo só seu:

    dados/processados/coletas_exterior.json   (GitHub Actions)
    dados/processados/coletas_brasil.json     (rodada do Brasil)

com, para cada fonte ("vereadores/maceio", "folhas/RN", "assembleias/df"...): a última tentativa, o último sucesso,
quantas falhas seguidas e o último erro. É daí que sai o relatório de situação (coleta/situacao.py).

Quem roda o quê:
- exterior: tudo, menos as fontes de SO_BRASIL e as que falharam nas 2 últimas tentativas de fora e funcionam do
  Brasil (essas o exterior tenta de novo uma vez por mês, para ver se voltaram a abrir de fora);
- brasil (python3 coletar.py brasil, uma vez por mês: ver rotina/semana-brasil.sh): as fontes de SO_BRASIL, as que
  falharam na última tentativa de fora e as que nunca rodaram de fora, menos as que já estão em dia (o último mês
  fechado já está no site: não há nada novo até o mês seguinte fechar). Assim, o que deixar de abrir no exterior passa
  sozinho para a rodada do Brasil seguinte.
- congeladas (CONGELADAS): nenhuma das duas rodadas, a não ser uma tentativa a cada 90 dias, para ver se a fonte voltou.

O lugar vem da variável CONTAS_ONDE ("exterior" ou "brasil"); sem ela, é "exterior" dentro do GitHub Actions e
"brasil" no resto (o computador no Brasil e o Cowork).
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
# mão no Brasil (coletar.py vereadores), roda tudo.
SO_O_QUE_FALTA = False

# Fontes que não abrem de fora do Brasil (conferido em 01/10/2026 de um servidor nos EUA e de um computador no Brasil). Em dúvida, a fonte
# fica fora daqui: se falhar no exterior, a rodada do Brasil passa a rodá-la sozinha (ver precisa_brasil).
SO_BRASIL = {
    "vereadores": {"belo_horizonte", "fortaleza", "maceio", "manaus", "natal", "porto_alegre", "rio_de_janeiro", "sao_luis"},
    "prefeituras": {"natal"},
    "assembleias": {"al", "am", "ap", "df", "es", "go", "ma", "rs"},  # pr, rn, pi, pa, ac, rr, mt abrem de fora
    "folhas": {"AL", "AM", "CE", "MA", "PA", "PB", "PI", "RJ", "RN", "SE"},
    "tce": set(),
    "viagens": {"AM", "PB", "SE"},  # viagens dos governadores (coleta/viagens_governadores); MG e SP abrem de fora
    "judiciario": set(),  # as sete fontes abrem de fora (conferido em 02/10/2026)
    "federal": set(),
}


# Fontes congeladas: a fonte parou de publicar o que o site mostra. O site fica com o último dado ("dados até"), a
# situação diz "congelada" com o motivo, e o robô só tenta de novo a cada REVER_CONGELADA_DIAS dias, para ver se voltou
# (se voltar, a situação avisa, e a fonte sai daqui à mão).
# Regra das folhas dos governadores: a folha é complemento do subsídio fixado em lei, que o site mostra sempre. Folha
# que quebrar e cujo conserto passar de cerca de 1 hora entra aqui, e o site fica com o valor da lei.
# O que fazer quando cada fonte de risco alto quebra: dados/referencia/plano-de-queda.json.
CONGELADAS = {
    "folhas/PA": {"desde": "2026-10-03", "ate": 202603,
                  "motivo": "desde abr/2026 a consulta pública da folha do Estado não mostra quem tem mandato eletivo"},
    "folhas/RJ": {"desde": "2026-10-03", "ate": 202603,
                  "motivo": "desde mar/2026 o governador em exercício é o presidente do Tribunal de Justiça, pago pelo "
                            "Tribunal, e o cargo de vice está vago"},
    "prefeituras/campo_grande": {"desde": "2026-10-03", "ate": 202602,
                                 "motivo": "a consulta da Prefeitura não traz a folha depois de fev/2026"},
}
REVER_CONGELADA_DIAS = 90


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


def _ultima_tentativa(ch):
    datas = [c.get("ultima_tentativa") for c in (ler(lugar).get(ch, {}) for lugar in LUGARES) if c.get("ultima_tentativa")]
    return datetime.fromisoformat(max(datas)) if datas else None


def congelada(ch):
    """True se a fonte está congelada e não é a vez de tentar de novo (uma vez a cada REVER_CONGELADA_DIAS dias)."""
    if ch not in CONGELADAS:
        return False
    ultima = _ultima_tentativa(ch)
    return bool(ultima) and datetime.now() - ultima < timedelta(days=REVER_CONGELADA_DIAS)


_meses_no_site = None


def em_dia(ch):
    """True se o último mês fechado já está no site para esta fonte (até o mês seguinte fechar, não há nada novo)."""
    global _meses_no_site
    if _meses_no_site is None:
        from .situacao import _ultimos_meses
        from .vereadores.comum import ultimo_mes_fechado
        _meses_no_site = (_ultimos_meses(), ultimo_mes_fechado())
    meses, fechado = _meses_no_site
    return bool(meses.get(ch)) and meses[ch] >= fechado


def pular(grupo, fonte):
    """True se esta rodada deve pular a fonte (e diz por quê no log)."""
    ch = chave(grupo, fonte)
    if congelada(ch):
        log(f"  {ch}: congelada ({CONGELADAS[ch]['motivo']}); tenta de novo a cada {REVER_CONGELADA_DIAS} dias")
        return True
    if LUGAR == "brasil":
        if not SO_O_QUE_FALTA:
            return False
        if not precisa_brasil(ch):
            return True
        if em_dia(ch):
            log(f"  {ch}: já está em dia (o último mês fechado já está no site); fica para a rodada do mês que vem")
            return True
        return False
    if _so_brasil(ch):
        log(f"  {ch}: só abre do Brasil, fica para a rodada do Brasil")
        return True
    fora, br = ler("exterior").get(ch, {}), ler("brasil").get(ch, {})
    if fora.get("falhas", 0) >= 2 and br.get("ultimo_sucesso"):
        ultima = datetime.fromisoformat(fora.get("ultima_tentativa", "2000-01-01T00:00:00"))
        if datetime.now() - ultima < timedelta(days=28):
            log(f"  {ch}: falhou {fora['falhas']} vezes de fora e funciona do Brasil, fica para a rodada do Brasil")
            return True
    return False


def _falhou(item, erro):
    if not item.get("falhas"):  # a primeira falha depois de um sucesso: "a coleta falhou desde" na página pública
        item["primeira_falha"] = item["ultima_tentativa"]
    item["falhas"] = item.get("falhas", 0) + 1
    item["ultimo_erro"] = erro[:300]
    item["ultima_falha"] = item["ultima_tentativa"]


@contextmanager
def registrar(grupo, fonte):
    """Anota a tentativa e o resultado (o erro não sai daqui: quem chama decide se a falha para os outros). Uma gravação
    recusada por perda de cobertura (util.gravar_com) durante a coleta conta como falha da fonte, sem erro: o arquivo
    anterior fica e a rodada segue."""
    from . import util
    ch = chave(grupo, fonte)
    dados = ler(LUGAR)
    item = dados.setdefault(ch, {})
    item["ultima_tentativa"] = _agora()
    antes, util._fonte_atual = util._fonte_atual, ch
    marca = len(util._recusas)
    try:
        yield
    except TempoEsgotado:
        item["ultimo_erro"] = "tempo máximo da rodada (continua na próxima)"
        _gravar(LUGAR, dados)
        raise
    except Exception as e:  # noqa: BLE001
        _falhou(item, f"{type(e).__name__}: {e}")
        _gravar(LUGAR, dados)
        raise
    finally:
        util._fonte_atual = antes
    recusas = util.recusas_desde(marca, ch)
    if recusas:
        _falhou(item, "Recusado por perda de cobertura (fica o arquivo anterior): "
                + "; ".join(f"{r['arquivo']}: {r['texto']}" for r in recusas))
        log(f"  {ch}: falha anotada (gravação recusada por perda de cobertura)")
    else:
        item["falhas"] = 0
        item.pop("primeira_falha", None)
        item["ultimo_sucesso"] = item["ultima_tentativa"]
    _gravar(LUGAR, dados)
