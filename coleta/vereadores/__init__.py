"""Vereador por vereador, cidade por cidade.

Cada módulo desta pasta cuida de uma Câmara Municipal: `coletar()` baixa os dados abertos e grava em
dados/municipios/<cidade>/ (vai para o Git), e `montar(tipos)` devolve (meta, pessoas) no formato comum
(ver comum.py). Uma cidade que falhar não derruba as outras: o site continua com o que já estava gravado.
"""
from ..util import TempoEsgotado, log
from . import belo_horizonte, comum, fortaleza, goiania, maceio, manaus, natal, porto_alegre, recife, rio_de_janeiro, sao_luis, sp

CIDADES = [sp, rio_de_janeiro, belo_horizonte, fortaleza, goiania, maceio, manaus, natal, porto_alegre, recife, sao_luis]


def coletar():
    for cidade in CIDADES:
        try:
            cidade.coletar()
        except TempoEsgotado:
            raise
        except Exception as e:  # noqa: BLE001 — uma cidade fora do ar não para as outras
            log(f"Vereadores de {cidade.CFG['n']}: a coleta falhou ({e}); o site usa o que já estava gravado")
    executar_site()


def executar_site():
    tipos = comum.Tipos()
    resultados = []
    for cidade in CIDADES:
        try:
            r = cidade.montar(tipos)
        except Exception as e:  # noqa: BLE001
            import traceback
            log(f"Vereadores de {cidade.CFG['n']}: não deu para montar ({e})\n{traceback.format_exc(limit=3)}")
            r = None
        if r and r[1]:
            resultados.append(r)
            log(f"  {cidade.CFG['n']}: {len(r[1])} vereadores, {sum(p['x'] for p in r[1])} no cargo")
    comum.escrever(resultados, tipos)
