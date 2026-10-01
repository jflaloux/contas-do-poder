"""Prefeituras: prefeito, vice, secretários (e, em São Paulo, subprefeitos), mês a mês, pela folha de pagamento
que cada Prefeitura publica com o nome de cada servidor.

Cada módulo desta pasta cuida de uma cidade: `coletar()` baixa a folha e grava só as linhas desses cargos em
dados/municipios/<cidade>/ (vai para o Git), e `montar()` devolve (meta, pessoas) no formato comum (comum.py).
Uma cidade que falhar não derruba as outras: o site continua com o que já estava gravado.
"""
from ..util import TempoEsgotado, log
from . import comum, curitiba, fortaleza, natal, porto_alegre, recife, rio, salvador, sp, vitoria

# ordem do site: a primeira é a cidade que abre a seção
CIDADES = [sp, rio, recife, fortaleza, vitoria, porto_alegre, salvador, curitiba, natal]


def coletar():
    for cidade in CIDADES:
        try:
            cidade.coletar()
        except TempoEsgotado:
            raise
        except Exception as e:  # noqa: BLE001 — uma cidade fora do ar não para as outras
            log(f"Prefeitura {cidade.CFG['de']}: a coleta falhou ({e}); o site usa o que já estava gravado")
    executar_site()


def executar_site(baixar_fotos=True):
    resultados = []
    for cidade in CIDADES:
        try:
            r = cidade.montar()
        except Exception as e:  # noqa: BLE001
            import traceback
            log(f"Prefeitura {cidade.CFG['de']}: não deu para montar ({e})\n{traceback.format_exc(limit=3)}")
            r = None
        if r and r[1]:
            resultados.append(r)
    comum.escrever(resultados, baixar_fotos=baixar_fotos)
