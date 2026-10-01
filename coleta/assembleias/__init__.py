"""Assembleias Legislativas: deputado estadual por deputado estadual, estado por estado.

Cada módulo desta pasta cuida de uma Assembleia: `coletar()` baixa os dados abertos e grava em
dados/assembleias/<uf>/ (vai para o Git), e `montar(tipos)` devolve (meta, pessoas) no mesmo formato dos vereadores
(coleta/vereadores/comum.py: contracheque, mês a mês, detalhe da verba, equipe). `comum.escrever()` junta tudo em
site/dados/assembleias.json. Um estado que falhar não derruba os outros: o site continua com o que já estava gravado.
O levantamento do que cada Assembleia publica está em dados/referencia/assembleias.json.
"""
from ..util import TempoEsgotado, log
from ..vereadores import comum as vc
from . import ba, ce, comum, go, ms, pb, pe, ro, sc, se, sp, to

ESTADOS = [sp, ba, pe, ce, pb, go, sc, ms, ro, to, se]


def coletar():
    for estado in ESTADOS:
        try:
            estado.coletar()
        except TempoEsgotado:
            raise
        except Exception as e:  # noqa: BLE001 — uma Assembleia fora do ar não para as outras
            log(f"Assembleia {estado.CFG['uf']}: a coleta falhou ({e}); o site usa o que já estava gravado")
    executar_site()


def executar_site(baixar_fotos=True):
    tipos = vc.Tipos()
    resultados = []
    for estado in ESTADOS:
        try:
            r = estado.montar(tipos)
        except Exception as e:  # noqa: BLE001
            import traceback
            log(f"Assembleia {estado.CFG['uf']}: não deu para montar ({e})\n{traceback.format_exc(limit=3)}")
            r = None
        if r and r[1]:
            resultados.append(r)
            log(f"  Assembleia {estado.CFG['uf']}: {len(r[1])} deputados, {sum(p['x'] for p in r[1])} no cargo")
    comum.escrever(resultados, tipos, baixar_fotos=baixar_fotos)
