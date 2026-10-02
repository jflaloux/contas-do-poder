"""Tribunais de Contas: vereadores, prefeito, vice e (onde a folha diz o cargo) secretários de todos os municípios de um
estado, mês a mês, pela folha de pagamento que cada município manda ao Tribunal de Contas do estado (ver o README,
"Tribunais de Contas"). Hoje: Paraíba (TCE-PB, 223 municípios) e Ceará (TCE-CE, 184).

Cada módulo cuida de um tribunal: `coletar()` grava em dados/municipios_tce/<uf>/ (vai para o Git) só as linhas
desses cargos, dos meses que faltam (e os 2 últimos de novo); `montar()` escreve site/dados/interior/<uf>.json, um
arquivo por estado, para o site só baixar o estado da cidade aberta. Um tribunal fora do ar não para o outro: o site
usa o que já estava gravado. Cada tribunal é uma fonte em coleta/onde.py ("tce/pb", "tce/ce"): as duas abrem de fora
do Brasil (conferido em 01/10/2026), então rodam no GitHub Actions; se uma falhar de fora, a rodada do Brasil a pega na mesma semana.

Uso: python3 coletar.py tce            (os dois estados e o site)
     python3 -m coleta.tce ce 150      (um estado só, com tempo máximo, para rodar em partes)
     python3 -m coleta.tce site        (só os arquivos do site, com o que já está gravado)
"""
from .. import onde
from ..util import TempoEsgotado, log
from . import ce, comum, pb

ESTADOS = {m.UF: m for m in (pb, ce)}


def coletar():
    for uf, m in ESTADOS.items():
        if onde.pular("tce", m):
            continue
        try:
            with onde.registrar("tce", m):
                n = m.coletar()
            log(f"  TCE {uf}: {n} linhas novas ou refeitas")
        except TempoEsgotado:
            raise
        except Exception as e:  # noqa: BLE001 — um tribunal fora do ar não para o outro
            log(f"  TCE {uf}: a coleta falhou ({e}); o site usa o que já estava gravado")
    executar_site()


def executar_site():
    for uf, m in ESTADOS.items():
        try:
            saida = m.montar()
            if saida:
                comum.checar(uf, saida)
        except Exception as e:  # noqa: BLE001
            import traceback
            log(f"  TCE {uf}: não deu para montar o arquivo do site ({e})\n{traceback.format_exc(limit=3)}")
