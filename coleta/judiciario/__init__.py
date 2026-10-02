"""Judiciário: o pagamento, mês a mês, de quem está no topo da Justiça — os ministros do STF, STJ, TST, STM e TSE, os
conselheiros do CNJ e o Procurador-Geral da República (ver o README, "Judiciário").

Cada fonte é um módulo desta pasta: stj, tst, cnj e pgr leem a fonte oficial; dadosjusbr lê o STF, o STM e o TSE pelo
DadosJusBr (CC BY 4.0), enquanto a fonte oficial não abre para o robô. `coletar()` de cada um grava em
dados/judiciario/<orgao>/ (vai para o Git) só os meses que faltam (e os 2 últimos de novo). `executar_site()` junta
tudo com a composição (dados/judiciario/composicao.json, mantida à mão) em site/dados/judiciario.json. Uma fonte fora
do ar não para as outras: o site usa o que já estava gravado. Cada fonte é uma chave em coleta/onde.py
("judiciario/stj", "judiciario/stf"...).

Uso: python3 coletar.py judiciario         (as sete fontes e o site)
     python3 -m coleta.judiciario stj 70   (uma fonte só, com tempo máximo, para rodar em partes)
     python3 -m coleta.judiciario site     (só o arquivo do site, com o que já está gravado)
"""
from .. import onde
from ..util import TempoEsgotado, log
from . import cnj, dadosjusbr, pgr, site, stj, tst


class _Fonte:
    """Uma fonte com nome (a chave em coleta/onde.py) e a função que coleta."""
    def __init__(self, nome, coletar):
        self.__name__, self.coletar = nome, coletar


FONTES = [_Fonte("stj", stj.coletar), _Fonte("tst", tst.coletar), _Fonte("cnj", cnj.coletar), _Fonte("pgr", pgr.coletar),
          _Fonte("stf", lambda: dadosjusbr.coletar("STF")), _Fonte("stm", lambda: dadosjusbr.coletar("STM")),
          _Fonte("tse", lambda: dadosjusbr.coletar("TSE"))]
POR_NOME = {f.__name__: f for f in FONTES}


def coletar():
    for m in FONTES:
        if onde.pular("judiciario", m):
            continue
        try:
            with onde.registrar("judiciario", m):
                n = m.coletar()
            log(f"  Judiciário {m.__name__.upper()}: {n} linhas novas ou refeitas")
        except TempoEsgotado:
            raise
        except Exception as e:  # noqa: BLE001 — uma fonte fora do ar não para as outras
            log(f"  Judiciário {m.__name__.upper()}: a coleta falhou ({e}); o site usa o que já estava gravado")
    executar_site()


def executar_site(baixar_fotos=True):
    try:
        site.escrever(baixar_fotos=baixar_fotos)
    except TempoEsgotado:
        raise
    except Exception as e:  # noqa: BLE001
        import traceback
        log(f"  Judiciário: não deu para montar o arquivo do site ({e})\n{traceback.format_exc(limit=3)}")
