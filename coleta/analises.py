"""Contas agregadas sobre a base já coletada (nada é baixado): servem de pauta para a imprensa e de conferência cruzada.
Cada função devolve um dicionário com os números e o método; sem nomes de pessoas (só contagens e totais).

    python3 -m coleta.analises c7        # ajuda de custo de deputados e senadores desde fev/2023
    python3 -m coleta.analises cadeiras  # conferência cruzada: deputados estaduais no cargo x cadeiras de cada Assembleia
    python3 -m coleta.analises interior  # vereadores do interior (PB e CE) com o valor típico acima do teto da Constituição;
                                         # grava site/dados/interior-teto.json (também refeito por coletar.py montar)
"""
import json
import statistics
import sys

import pandas as pd

from .config import PROCESSADOS, RAIZ
from .util import gravar_json


def _base():
    lanc = pd.read_csv(PROCESSADOS / "lancamentos.csv.gz")
    pol = pd.DataFrame(json.loads((PROCESSADOS / "politicos.json").read_text(encoding="utf-8")))
    return lanc, pol


def c7():
    """C7: ajuda de custo paga a deputados federais e senadores desde fev/2023.

    Fonte: lancamentos.csv.gz, categoria "ajuda_de_custo", dos contracheques detalhados da Câmara (camara_detalhe) e da folha
    do Senado (senado_folha). Na Câmara, a coluna é "verbas indenizatórias" do contracheque; todos os pagamentos
    positivos são iguais a um subsídio do mês (R$ 39.293,32 em 2023, R$ 41.650,92, R$ 44.008,52 e R$ 46.366,19 depois),
    o que confirma que é a ajuda de custo. Pagamento = lançamento positivo; devolução = lançamento negativo (acerto).
    "Suplente" e "Efetivado" são a condição eleitoral do deputado (TSE; "Efetivado" é o suplente que passou a titular) e, no
    Senado, a participação do senador no mandato (titular ou suplente)."""
    lanc, pol = _base()
    a = lanc[(lanc.categoria == "ajuda_de_custo") & lanc.fonte.isin(["camara_detalhe", "senado_folha"])]
    pol = pol.assign(condicao_eleitoral=pol.condicao_eleitoral.fillna(pol.participacao.map(lambda x: "Suplente" if isinstance(x, str) and "Suplente" in x else x)))
    a = a.merge(pol[["id", "casa", "condicao_eleitoral"]], left_on="id_politico", right_on="id")
    res = {}
    for casa, nome in (("camara", "Câmara dos Deputados"), ("senado", "Senado"), ("executivo", "licenciados para ministérios (Câmara)")):
        c = a[a.casa == casa]
        if c.empty:
            continue
        pos, neg = c[c.valor > 0], c[c.valor < 0]
        subs = pos[pos.condicao_eleitoral.isin(["Suplente", "Efetivado"])]
        res[nome] = {
            "pagamentos": int(len(pos)), "pessoas": int(pos.id_politico.nunique()),
            "total_pago": round(float(pos.valor.sum()), 2),
            "devolucoes": int(len(neg)), "total_devolvido": round(float(-neg.valor.sum()), 2),
            "total_liquido": round(float(c.valor.sum()), 2),
            "pagamentos_a_suplentes": int(len(subs)), "pessoas_suplentes": int(subs.id_politico.nunique()),
            "total_a_suplentes": round(float(subs.valor.sum()), 2),
            "por_ano": {int(ano): {"pagamentos": int(len(g)), "total": round(float(g.valor.sum()), 2)}
                        for ano, g in pos.groupby("ano")},
            "pagamentos_em_fev_2023": int(len(pos[(pos.ano == 2023) & (pos.mes == 2)])),
            "pagamentos_depois_de_fev_2023": int(len(pos[~((pos.ano == 2023) & (pos.mes == 2))])),
        }
    return res


ARQ_INTERIOR_TETO = RAIZ / "site" / "dados" / "interior-teto.json"
MARGEM = 0.01  # 1% de folga: o subsídio do deputado e o valor da folha têm arredondamentos e centavos diferentes
MESES_TIPICO = 6  # o valor típico é a mediana dos últimos 6 meses, para o 13º, as férias e os atrasados não pesarem


def _expandir(t):
    saida = []
    for valor, n in t or []:
        saida += [valor] * n
    return saida


def interior_teto(gravar=False):
    """Vereadores do interior (PB e CE, folha dos Tribunais de Contas) cujo valor bruto típico (mediana dos últimos 6 meses
    com valor, no mínimo 3) fica acima do teto da Constituição (art. 29, VI) para a faixa de população da cidade:
    percentual (20% a 75%, municipios.json meta.faixas_teto) do subsídio do deputado estadual do Estado em vigor
    (assembleias.json). Só fatos: o valor que a fonte mostra e o teto da faixa, sem dizer o motivo (pode ser verba de
    representação, população da época da fixação do subsídio ou outro pagamento que a folha não separa).

    Saída (site/dados/interior-teto.json): {"meta": {...}, "m": {"PB": {ibge: [teto, avaliados, [[i, nome, típico, maior
    mês, 1 se é o presidente da Câmara], ...]]}}}, em que i é a posição do vereador em `v` da cidade em site/dados/interior/<uf>.json."""
    mun = json.loads((RAIZ / "site" / "dados" / "municipios.json").read_text(encoding="utf-8"))
    pop = {str(r[0]): r[3] for r in mun["m"]}
    faixas = mun["meta"]["faixas_teto"]
    ass = json.loads((RAIZ / "site" / "dados" / "assembleias.json").read_text(encoding="utf-8"))
    saida = {"meta": {}, "m": {}}
    for uf in ("PB", "CE"):
        d = json.loads((RAIZ / "site" / "dados" / "interior" / f"{uf.lower()}.json").read_text(encoding="utf-8"))
        subsidio = ass["meta"]["estados"][uf]["subsidio"][-1][1]
        saida["meta"][uf] = {"subsidio_deputado_estadual": subsidio, "ultimo_mes": d["meta"]["ultimo_mes"]}
        cidades = {}
        for ibge, c in d["m"].items():
            p = pop.get(ibge)
            if p is None:
                continue
            fracao = next(f for lim, f in faixas if lim is None or p <= lim)
            teto = round(fracao * subsidio, 2)
            avaliados, acima = 0, []
            for i, v in enumerate(c.get("v", [])):
                if not v.get("x"):
                    continue
                valores = [x for x in _expandir(v.get("t"))[-MESES_TIPICO:] if x]
                if len(valores) < 3:
                    continue
                avaliados += 1
                tipico = statistics.median(valores)
                if tipico > teto * (1 + MARGEM):
                    acima.append([i, v.get("n", ""), round(tipico, 2), round(max(valores), 2), 1 if v.get("pr") else 0])
            if acima:
                cidades[ibge] = [teto, avaliados, acima]
        saida["m"][uf] = cidades
    saida["meta"]["criterio"] = ("Mediana dos últimos 6 meses com valor (mínimo 3, e mais de 1% acima do teto) do valor bruto da folha do Tribunal de Contas, "
                                 "para quem está na folha do último mês, contra o percentual do subsídio do deputado estadual "
                                 "fixado na Constituição (art. 29, VI) para a faixa de população da cidade.")
    if gravar:
        gravar_json(ARQ_INTERIOR_TETO, saida, grupo="m")
    return saida


def cadeiras():
    """Por Assembleia: deputados marcados "no cargo" (x = 1) x cadeiras (vagas), quem está no cargo sem nenhuma linha de
    pagamento nos 3 últimos meses da Assembleia, e nomes repetidos no cargo. Lê site/dados/assembleias.json."""
    d = json.loads((RAIZ / "site" / "dados" / "assembleias.json").read_text(encoding="utf-8"))
    saida = {}
    for uf, e in d["meta"]["estados"].items():
        dep = [x for x in d["p"] if x["uf"] == uf]
        no_cargo = [x for x in dep if x.get("x") == 1]
        ultimo = e.get("ultimo_mes") or 0
        recentes = sorted({t[0] for x in dep for t in (x.get("t") or [])})[-3:]
        sem_pagamento = [x["n"] for x in no_cargo if not any(t[0] in recentes and (t[1] or t[2]) for t in (x.get("t") or []))]
        nomes = [x["n"] for x in no_cargo]
        saida[uf] = {"vagas": e.get("vagas"), "no_cargo": len(no_cargo), "diferenca": len(no_cargo) - (e.get("vagas") or 0),
                     "ultimo_mes": ultimo, "no_cargo_sem_pagamento_recente": len(sem_pagamento),
                     "nomes_repetidos": sorted({n for n in nomes if nomes.count(n) > 1}), "sem_pagamento_recente": sorted(sem_pagamento)}
    return saida


if __name__ == "__main__":
    if sys.argv[1] == "interior":
        r = interior_teto(gravar="--gravar" in sys.argv)
        print({uf: (len(c), sum(len(x[2]) for x in c.values())) for uf, c in r["m"].items()}, "(cidades, vereadores)")
    else:
        print(json.dumps({"c7": c7, "cadeiras": cadeiras}[sys.argv[1]](), ensure_ascii=False, indent=1))
