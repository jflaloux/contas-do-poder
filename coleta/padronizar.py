"""Junta Câmara e Senado numa base única.

Saídas em dados/processados/:
- politicos.json    — quem é quem (um registro por político)
- lancamentos.csv.gz — uma linha por político · ano · mês · grupo · categoria · descrição · valor
- equipe.csv        — quantas pessoas trabalharam no gabinete em cada mês
- resumo.json       — totais prontos para o site (por político, por ano e na legislatura)
- metadados.json    — data da coleta, fontes, regras e pendências conhecidas

Grupos:
- "ganha": o que vai para o bolso do parlamentar (salário, 13º, auxílios, ajuda de custo)
- "custa": despesas dele pagas com dinheiro público (cota: passagens, combustível, alimentação,
           escritório, divulgação...; diárias; outros gastos do mandato)
  -> "ganha" + "custa" = o custo do parlamentar
- "equipe": salários das pessoas que trabalham no gabinete (dinheiro que vai para outras pessoas)
"""
from datetime import datetime

import pandas as pd

from .config import BRUTOS, CACHE, INICIO_LEGISLATURA, LEGISLATURA, PROCESSADOS, REFERENCIA
from .util import ler_json, log, salvar_json

SALARIO_MINIMO = {2023: 1320.00, 2024: 1412.00, 2025: 1518.00, 2026: 1621.00}

CATEGORIAS = {
    # grupo "ganha"
    "salario": ("ganha", "Salário (subsídio bruto)"),
    "decimo_terceiro": ("ganha", "13º salário"),
    "auxilio_moradia": ("ganha", "Auxílio-moradia"),
    "auxilios": ("ganha", "Auxílios (inclui auxílio-moradia)"),
    "ajuda_de_custo": ("ganha", "Ajuda de custo e outras verbas indenizatórias"),
    "outros_rendimentos": ("ganha", "Outros pagamentos"),
    # grupo "custa" (despesas do próprio parlamentar)
    "cota_parlamentar": ("custa", "Cota parlamentar"),
    "diarias": ("custa", "Diárias de viagens oficiais"),
    "outros_gastos_mandato": ("custa", "Outros gastos do mandato"),
    # grupo "equipe" (vai para outras pessoas)
    "assessores_gabinete": ("equipe", "Equipe do gabinete"),
}


def _na_legislatura(df):
    inicio = INICIO_LEGISLATURA[0] * 100 + INICIO_LEGISLATURA[1]
    return df[(df["ano"] * 100 + df["mes"].fillna(12)) >= inicio]


def _linha(id_, ano, mes, categoria, descricao, valor, fonte):
    grupo, _ = CATEGORIAS[categoria]
    return {"id_politico": id_, "ano": int(ano), "mes": (int(mes) if pd.notna(mes) else None),
            "grupo": grupo, "categoria": categoria, "descricao": descricao,
            "valor": round(float(valor), 2), "fonte": fonte}


# ---------------------------------------------------------------- Câmara
def _camara():
    deps = ler_json(BRUTOS / "camara_deputados.json")
    pid = {d["id"]: f"dep-{d['id']}" for d in deps}
    L = []

    rem = _na_legislatura(pd.read_csv(BRUTOS / "camara_remuneracao.csv"))
    for r in rem.itertuples():
        if r.id_deputado in pid and r.valor:
            L.append(_linha(pid[r.id_deputado], r.ano, r.mes, "salario", "Salário mensal bruto", r.valor,
                            "camara_remuneracao"))

    verba = _na_legislatura(pd.read_csv(BRUTOS / "camara_verba_gabinete.csv"))
    for r in verba.itertuples():
        if r.id_deputado in pid and r.gasto:
            L.append(_linha(pid[r.id_deputado], r.ano, r.mes, "assessores_gabinete",
                            "Verba de gabinete usada (salários de secretários parlamentares)", r.gasto,
                            "camara_verba_gabinete"))

    cota = pd.read_csv(BRUTOS / "camara_cota.csv")
    for r in cota.itertuples():
        if r.id_deputado in pid and r.valor:
            L.append(_linha(pid[r.id_deputado], r.ano, r.mes, "cota_parlamentar", r.tipo.strip().capitalize(), r.valor,
                            "camara_cota"))

    # Lacuna dos dados abertos (desde ago/2025): completa com a diferença para o total mensal do site oficial.
    site = pd.read_csv(BRUTOS / "camara_cota_site.csv")
    soma_csv = cota.groupby(["id_deputado", "ano", "mes"])["valor"].sum()
    for r in site.itertuples():
        if r.id_deputado not in pid or pd.isna(r.total_site):
            continue
        dif = round(r.total_site - soma_csv.get((r.id_deputado, r.ano, r.mes), 0.0), 2)
        if dif >= 1:
            L.append(_linha(pid[r.id_deputado], r.ano, r.mes, "cota_parlamentar",
                            "Passagens aéreas e outros itens sem detalhe nos dados abertos (diferença para o site oficial)",
                            dif, "camara_cota"))

    mor = pd.read_csv(BRUTOS / "camara_moradia.csv")
    for r in mor.itertuples():
        if r.id_deputado in pid and r.auxilio_moradia:
            L.append(_linha(pid[r.id_deputado], r.ano, None, "auxilio_moradia", "Auxílio-moradia recebido no ano",
                            r.auxilio_moradia, "camara_moradia"))

    dias_imovel = {(pid[r.id_deputado], int(r.ano)): int(r.dias_imovel_funcional)
                   for r in mor.itertuples() if r.id_deputado in pid}

    politicos = []
    for d in deps:
        feminino = d.get("sexo") == "F"
        politicos.append({
            "id": pid[d["id"]], "casa": "camara",
            "cargo": "Deputada federal" if feminino else "Deputado federal",
            "nome": d["nome"], "nome_civil": d.get("nome_civil"), "sexo": d.get("sexo"),
            "partido": d.get("partido"), "uf": d.get("uf"), "foto": d.get("foto"),
            "em_exercicio": d["em_exercicio"], "pagina_oficial": d["pagina_oficial"],
            "data_nascimento": d.get("data_nascimento"),
            "naturalidade": ", ".join(x for x in (d.get("municipio_nascimento"), d.get("uf_nascimento")) if x) or None,
            "escolaridade": d.get("escolaridade"),
            "condicao_eleitoral": d.get("condicao_eleitoral"),
            "imovel_funcional_dias": {str(a): v for (p, a), v in dias_imovel.items() if p == pid[d["id"]] and v},
        })
    return politicos, L


# ---------------------------------------------------------------- Senado
def _senado():
    sens = [s for s in ler_json(CACHE / "senado" / "senadores_v2.json") if s["exerceu_na_legislatura"]]
    pid = {s["id"]: f"sen-{s['id']}" for s in sens}
    L = []

    folha = _na_legislatura(pd.read_csv(BRUTOS / "senado_folha.csv"))
    colunas = [
        ("remuneracao_basica", "salario", "Salário mensal bruto"),
        ("vantagens_pessoais", "outros_rendimentos", "Vantagens pessoais"),
        ("funcao_comissionada", "outros_rendimentos", "Função comissionada"),
        ("gratificacao_natalina", "decimo_terceiro", "Gratificação natalina (13º)"),
        ("horas_extras", "outros_rendimentos", "Horas extras"),
        ("outras_eventuais", "outros_rendimentos", "Outras remunerações eventuais"),
        ("abono_permanencia", "outros_rendimentos", "Abono de permanência"),
        ("auxilios", "auxilios", "Auxílios (inclui auxílio-moradia)"),
        ("vantagens_indenizatorias", "ajuda_de_custo", "Vantagens indenizatórias (ex.: ajuda de custo)"),
        ("diarias", "diarias", "Diárias de viagens oficiais"),
    ]
    liquido = []
    for r in folha.itertuples():
        if r.id_senador not in pid:
            continue
        fonte = "senado_folha"
        for col, cat, desc in colunas:
            v = getattr(r, col)
            if v:
                L.append(_linha(pid[r.id_senador], r.ano, r.mes, cat, f"{desc} — folha {r.tipo_folha.lower()}", v, fonte))
        liquido.append({"id_politico": pid[r.id_senador], "ano": r.ano, "mes": r.mes, "liquido": r.remuneracao_liquida})

    ceaps = pd.read_csv(BRUTOS / "senado_ceaps.csv")
    ceaps = ceaps[ceaps["ano"] * 100 + ceaps["mes"] >= INICIO_LEGISLATURA[0] * 100 + INICIO_LEGISLATURA[1]]
    for r in ceaps.itertuples():
        if r.id_senador in pid and r.valor:
            L.append(_linha(pid[r.id_senador], r.ano, r.mes, "cota_parlamentar", r.tipo, r.valor,
                            "senado_transparencia"))

    outros = pd.read_csv(BRUTOS / "senado_outros_gastos.csv")
    # Diárias já vêm da folha de pagamento; não somar duas vezes.
    outros = outros[~outros["tipo"].str.contains("Diárias", case=False)]
    for r in outros.itertuples():
        if r.id_senador in pid and r.valor:
            L.append(_linha(pid[r.id_senador], r.ano, None, "outros_gastos_mandato", r.tipo, r.valor,
                            "senado_transparencia"))

    gab = _na_legislatura(pd.read_csv(BRUTOS / "senado_assessores_gabinete.csv"))
    for r in gab.itertuples():
        if r.id_senador in pid and r.valor:
            L.append(_linha(pid[r.id_senador], r.ano, r.mes, "assessores_gabinete",
                            f"Salários de {r.pessoas} assessores comissionados do gabinete e escritórios (estimativa)",
                            r.valor, "senado_folha"))

    ben = pd.read_csv(BRUTOS / "senado_beneficios.csv")
    imovel = {(pid[r.id_senador], str(r.ano)): r.utilizacao for r in ben.itertuples()
              if r.id_senador in pid and r.beneficio == "Imóvel Funcional"}

    politicos = []
    for s in sens:
        feminino = s.get("sexo") == "F"
        politicos.append({
            "id": pid[s["id"]], "casa": "senado",
            "cargo": "Senadora" if feminino else "Senador",
            "nome": s["nome"], "nome_civil": s.get("nome_civil"), "sexo": s.get("sexo"),
            "partido": s.get("partido"), "uf": s.get("uf"), "foto": s.get("foto"),
            "em_exercicio": s["em_exercicio"], "pagina_oficial": s["pagina_oficial"],
            "data_nascimento": s.get("data_nascimento"),
            "naturalidade": ", ".join(x for x in (s.get("municipio_nascimento"), s.get("uf_nascimento")) if x) or None,
            "participacao": s.get("participacao"),
            "exercicios": s.get("exercicios"),
            "imovel_funcional": {a: u for (p, a), u in imovel.items() if p == pid[s["id"]]},
        })
    return politicos, L, liquido


# ---------------------------------------------------------------- tamanho da equipe
def _equipe(ids):
    """Pessoas no gabinete por mês. Câmara: secretários parlamentares (pagos pela verba de gabinete);
    CNE aparece à parte. Senado: comissionados do gabinete e escritórios encontrados na folha (estimativa)."""
    partes = []
    arq = BRUTOS / "camara_pessoal.csv"
    if arq.exists():
        c = pd.read_csv(arq)
        c["id_politico"] = "dep-" + c["id_deputado"].astype(str)
        partes.append(c.rename(columns={"secretarios": "pessoas"})[["id_politico", "ano", "mes", "pessoas", "cne"]])
    s_ = pd.read_csv(BRUTOS / "senado_assessores_gabinete.csv")
    s_["id_politico"] = "sen-" + s_["id_senador"].astype(str)
    s_["cne"] = 0
    partes.append(s_[["id_politico", "ano", "mes", "pessoas", "cne"]])
    eq = _na_legislatura(pd.concat(partes, ignore_index=True))
    eq = eq[eq["id_politico"].isin(ids) & ((eq["pessoas"] > 0) | (eq["cne"] > 0))]
    return eq.sort_values(["id_politico", "ano", "mes"])


# ---------------------------------------------------------------- resumo
def _resumo(politicos, lanc, equipe):
    df = pd.DataFrame(lanc)
    limites = pd.read_csv(REFERENCIA / "limites_cota_camara.csv").set_index("uf")["limite_mensal"].to_dict()
    mensal = (df[df.mes.notna()].groupby(["id_politico", "ano", "mes", "grupo"])["valor"].sum().unstack("grupo").fillna(0.0))
    for g in ("ganha", "custa", "equipe"):
        if g not in mensal:
            mensal[g] = 0.0
    mensal = mensal.reset_index()
    saida = {}

    def bloco(d, mm, eq, ano=None):
        g = round(d.loc[d.grupo == "ganha", "valor"].sum(), 2)
        c = round(d.loc[d.grupo == "custa", "valor"].sum(), 2)
        e = round(d.loc[d.grupo == "equipe", "valor"].sum(), 2)
        mg, mc, me = int((mm.ganha > 0).sum()), int((mm.custa > 0).sum()), int((mm.equipe > 0).sum())
        meses_e = mm[mm.equipe > 0][["ano", "mes"]]
        eq_ok = eq.merge(meses_e, on=["ano", "mes"])          # meses com custo e com contagem de pessoas
        pessoa_meses = int(eq_ok["pessoas"].sum())
        e_ok = float(mm.merge(eq_ok[["ano", "mes"]], on=["ano", "mes"]).equipe.sum())
        out = {
            "meses_com_salario": mg, "meses_com_despesas": mc, "meses_com_equipe": me,
            "ganha": g, "despesas": c, "equipe": e,
            "ganha_por_mes": round(g / mg, 2) if mg else None,
            "despesas_por_mes": round(c / mc, 2) if mc else None,
            "custo_dele_por_mes": round((g / mg if mg else 0) + (c / mc if mc else 0), 2),
            "equipe_por_mes": round(e / me, 2) if me else None,
            "pessoas_na_equipe_media": round(pessoa_meses / len(eq_ok), 1) if len(eq_ok) else None,
            "media_por_pessoa_por_mes": round(e_ok / pessoa_meses, 2) if pessoa_meses else None,
            "categorias": {k: round(v, 2) for k, v in d.groupby("categoria")["valor"].sum().items()},
        }
        if ano:
            out["salarios_minimos_ganha_por_mes"] = round(g / mg / SALARIO_MINIMO[ano], 1) if mg else None
        return out

    for p in politicos:
        pid = p["id"]
        d, mm, eq = df[df.id_politico == pid], mensal[mensal.id_politico == pid], equipe[equipe.id_politico == pid]
        por_ano = {str(int(a)): bloco(d[d.ano == a], mm[mm.ano == a], eq[eq.ano == a], int(a)) for a in sorted(d.ano.unique())}
        cota_por_tipo = (d[d.categoria == "cota_parlamentar"].groupby("descricao")["valor"].sum()
                         .sort_values(ascending=False).round(2))
        leg = bloco(d, mm, eq)
        leg["cota_por_tipo"] = cota_por_tipo.head(12).to_dict()
        item = {"legislatura": leg, "por_ano": por_ano}
        if p["casa"] == "camara" and p.get("uf") in limites:
            item["limite_mensal_cota_atual"] = limites[p["uf"]]
        saida[pid] = item
    return saida


def executar():
    log("Padronizando...")
    pc, lc = _camara()
    ps, ls, liquido = _senado()
    politicos = pc + ps
    lanc = lc + ls

    # Deixa de fora quem não tem nenhum pagamento na legislatura (ex.: suplente que só aparece na lista)
    com_dados = {l["id_politico"] for l in lanc}
    politicos = [p for p in politicos if p["id"] in com_dados]
    ids = {p["id"] for p in politicos}
    lanc = [l for l in lanc if l["id_politico"] in ids]

    PROCESSADOS.mkdir(parents=True, exist_ok=True)
    salvar_json(PROCESSADOS / "politicos.json", politicos)
    pd.DataFrame(lanc).sort_values(["id_politico", "ano", "mes", "grupo", "categoria"], na_position="last") \
        .to_csv(PROCESSADOS / "lancamentos.csv.gz", index=False)
    pd.DataFrame(liquido).to_csv(PROCESSADOS / "senado_salario_liquido.csv", index=False)
    equipe = _equipe(ids)
    equipe.to_csv(PROCESSADOS / "equipe.csv", index=False)
    salvar_json(PROCESSADOS / "resumo.json", _resumo(politicos, lanc, equipe))
    salvar_json(PROCESSADOS / "metadados.json", {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "legislatura": LEGISLATURA,
        "periodo": f"{INICIO_LEGISLATURA[1]:02d}/{INICIO_LEGISLATURA[0]} até hoje",
        "salario_minimo": SALARIO_MINIMO,
        "categorias": {k: {"grupo": g, "nome": n} for k, (g, n) in CATEGORIAS.items()},
        "grupos": {
            "ganha": "Vai para o bolso do parlamentar: salário, 13º, auxílios, ajuda de custo.",
            "custa": "Despesas do próprio parlamentar pagas com dinheiro público: cota, diárias, outros gastos.",
            "equipe": "Salários das pessoas que trabalham no gabinete.",
        },
        "fontes_por_lancamento": {
            "_como_usar": "troque {id} pelo número do político (sem 'dep-'/'sen-'), {ano} e {mes}",
            "camara_remuneracao": "https://www.camara.leg.br/deputados/{id}/remuneracao?ano={ano}",
            "camara_verba_gabinete": "https://www.camara.leg.br/deputados/{id}/verba-gabinete?ano={ano}",
            "camara_cota": "https://www.camara.leg.br/cota-parlamentar/consulta-cota-parlamentar?ideDeputado={id}&dataInicio=01{ano}&dataFim=12{ano}",
            "camara_moradia": "https://www.camara.leg.br/moradia/detalhamento",
            "senado_folha": "https://adm.senado.gov.br/adm-dadosabertos/api/v1/servidores/remuneracoes/{ano}/{mes}/csv",
            "senado_transparencia": "https://www6g.senado.leg.br/transparencia/sen/{id}/?ano={ano}",
        },
        "fontes": {
            "camara_api": "https://dadosabertos.camara.leg.br/swagger/api.html",
            "camara_cota": "https://www.camara.leg.br/cotas/",
            "camara_paginas": "https://www.camara.leg.br/deputados/{id}/remuneracao e /verba-gabinete",
            "camara_moradia": "https://www.camara.leg.br/moradia/detalhamento",
            "senado_legis": "https://legis.senado.leg.br/dadosabertos/docs/",
            "senado_adm": "https://adm.senado.gov.br/adm-dadosabertos/swagger-ui/index.html",
        },
        "pendencias": [
            "Câmara: 13º salário e ajuda de custo dos deputados ainda não coletados (no Senado já estão).",
            "Câmara: diárias de viagens oficiais (missão oficial) ainda não coletadas.",
            "Senado: 'outros gastos do mandato' (passagens, correios, impulsionamento) só existem na API para quem está em exercício hoje.",
            "Câmara: limites da cota por estado valem para o ano atual; faltam os valores históricos.",
            "Senado: custo dos assessores é ESTIMADO ligando a folha de pagamento à lotação atual (ou última) de cada "
            "servidor comissionado, pelo nome. É mais preciso para os meses recentes; homônimos são descartados.",
            "Cota parlamentar: os 3 últimos meses ainda podem receber notas (prazo de 90 dias).",
            "Câmara: desde ago/2025 as passagens compradas pelo sistema da Câmara (SIGEPA) não aparecem nos arquivos de "
            "dados abertos. Completamos com a diferença para o total mensal do site oficial, sem detalhe por tipo.",
            "Câmara 2023–2024: em ~2% dos meses a soma dos arquivos fica um pouco ACIMA do total do site; mantivemos os arquivos.",
        ],
    })
    n_dep = sum(p["casa"] == "camara" for p in politicos)
    n_sen = sum(p["casa"] == "senado" for p in politicos)
    log(f"Base pronta: {n_dep} deputados, {n_sen} senadores, {len(lanc)} lançamentos.")
