"""Gera os dados compactos que o site usa: site/dados/dados.json.

Formato (chaves curtas para o arquivo ficar pequeno):
  meta: informações gerais, categorias, tipos de despesa da cota, salário mínimo, pendências
  p: lista de políticos, cada um com
     id, k ("d" deputado / "s" senador), n (nome), nc (nome civil), g (cargo), pt (partido), uf,
     f (foto), x (em exercício), o (página oficial),
     per: {"2023": [meses, ganha, custa, {categoria: valor}, meses_com_ganha, meses_com_custa], ..., "leg": [...]}
     t: série mensal [[aaaamm, ganha, custa], ...]
     ct: {"2025": [[índice_do_tipo, valor], ...], ..., "leg": [...]}   (top 6 tipos da cota)
     im: imóvel funcional
"""
import json
from datetime import datetime

import pandas as pd

from .config import PROCESSADOS, RAIZ
from .util import ler_json, log, normalizar_nome

SAIDA = RAIZ / "site" / "dados" / "dados.json"


# Nomes curtos e em linguagem simples para os tipos de despesa da cota (Câmara e Senado usam nomes diferentes)
TIPOS_SIMPLES = [
    ("SEM DETALHE", "Passagens aéreas e itens sem detalhe*"),
    ("PASSAGE", "Passagens"),
    ("ALUGUEL DE IMOVEIS", "Escritório no estado"),
    ("MANUTENCAO DE ESCRITORIO", "Escritório no estado"),
    ("MATERIAL DE CONSUMO", "Material de escritório"),
    ("DIVULGACAO", "Divulgação do mandato"),
    ("CONSULTORIA", "Consultorias e serviços de apoio"),
    ("LOCOMOCAO", "Locomoção, hospedagem, alimentação e combustível"),
    ("COMBUSTIVE", "Combustível"),
    ("AERONAVE", "Fretamento de aviões"),
    ("EMBARCAC", "Fretamento de barcos"),
    ("VEICULOS", "Aluguel de carros"),
    ("HOSPEDAGEM", "Hospedagem"),
    ("ALIMENTACAO", "Alimentação"),
    ("TELEFONIA", "Telefone"),
    ("POSTAIS", "Correios"),
    ("SEGURANCA", "Segurança privada"),
    ("AUXILIO-MORADIA", "Complemento do auxílio-moradia"),
    ("TAXI", "Táxi, pedágio e estacionamento"),
    ("CURSO", "Cursos e eventos"),
    ("ASSINATURA", "Assinaturas de publicações"),
    ("TOKENS", "Certificados digitais"),
]


def tipo_simples(descricao):
    d = normalizar_nome(descricao)
    for chave, nome in TIPOS_SIMPLES:
        if chave in d:
            return nome
    return descricao.strip().capitalize()


def _r(v):
    return int(round(float(v)))


def executar():
    politicos = ler_json(PROCESSADOS / "politicos.json")
    meta = ler_json(PROCESSADOS / "metadados.json")
    lanc = pd.read_csv(PROCESSADOS / "lancamentos.csv.gz")
    lanc["periodo"] = lanc["ano"].astype(str)

    cota = lanc[lanc.categoria == "cota_parlamentar"].copy()
    cota["descricao"] = cota["descricao"].map(tipo_simples)
    tipos = sorted(cota["descricao"].unique())
    idx_tipo = {t: i for i, t in enumerate(tipos)}

    por_ano = lanc.groupby(["id_politico", "ano", "grupo"])["valor"].sum()
    cat_ano = lanc.groupby(["id_politico", "ano", "categoria"])["valor"].sum()
    por_leg = lanc.groupby(["id_politico", "grupo"])["valor"].sum()
    cat_leg = lanc.groupby(["id_politico", "categoria"])["valor"].sum()

    mensal = (lanc[lanc.mes.notna()].groupby(["id_politico", "ano", "mes", "grupo"])["valor"].sum()
              .unstack("grupo").fillna(0.0))
    # Meses com pagamento de cada grupo: as médias de "ganha" e de "custa" usam cada uma o seu número de meses
    # (ex.: deputado licenciado não recebe salário, mas o gabinete continua gastando).
    mm = mensal.reset_index()
    for grupo in ("ganha", "custa"):
        if grupo not in mm:
            mm[grupo] = 0.0
    mm["tem_g"] = mm["ganha"] > 0
    mm["tem_c"] = mm["custa"] > 0
    mm["tem"] = mm["tem_g"] | mm["tem_c"]
    meses_g_ano = mm[mm.tem_g].groupby(["id_politico", "ano"]).size()
    meses_c_ano = mm[mm.tem_c].groupby(["id_politico", "ano"]).size()
    meses_ano_any = mm[mm.tem].groupby(["id_politico", "ano"]).size()
    meses_g_leg = mm[mm.tem_g].groupby("id_politico").size()
    meses_c_leg = mm[mm.tem_c].groupby("id_politico").size()
    meses_leg_any = mm[mm.tem].groupby("id_politico").size()
    cota_ano = cota.groupby(["id_politico", "ano", "descricao"])["valor"].sum()
    cota_leg = cota.groupby(["id_politico", "descricao"])["valor"].sum()

    anos = sorted(lanc["ano"].unique())
    saida = []
    for p in politicos:
        pid = p["id"]
        per = {}
        for ano in anos:
            m = int(meses_ano_any.get((pid, ano), 0))
            g = por_ano.get((pid, ano, "ganha"), 0.0)
            c = por_ano.get((pid, ano, "custa"), 0.0)
            if m == 0 and g == 0 and c == 0:
                continue
            cats = {k: _r(v) for k, v in cat_ano.loc[pid, ano].items()} if (pid, ano) in cat_ano.index.droplevel(2) else {}
            per[str(ano)] = [m, _r(g), _r(c), {k: v for k, v in cats.items() if v},
                             int(meses_g_ano.get((pid, ano), 0)), int(meses_c_ano.get((pid, ano), 0))]
        cats_leg = {k: _r(v) for k, v in cat_leg.loc[pid].items()} if pid in cat_leg.index.get_level_values(0) else {}
        per["leg"] = [int(meses_leg_any.get(pid, 0)), _r(por_leg.get((pid, "ganha"), 0.0)),
                      _r(por_leg.get((pid, "custa"), 0.0)), {k: v for k, v in cats_leg.items() if v},
                      int(meses_g_leg.get(pid, 0)), int(meses_c_leg.get(pid, 0))]

        serie = []
        if pid in mensal.index.get_level_values(0):
            for (ano, mes), r in mensal.loc[pid].iterrows():
                serie.append([int(ano) * 100 + int(mes), _r(r.get("ganha", 0.0)), _r(r.get("custa", 0.0))])

        ct = {}
        for ano in anos:
            if (pid, ano) in cota_ano.index.droplevel(2):
                s = cota_ano.loc[pid, ano].sort_values(ascending=False).head(6)
                ct[str(ano)] = [[idx_tipo[d], _r(v)] for d, v in s.items() if v >= 1]
        if pid in cota_leg.index.get_level_values(0):
            s = cota_leg.loc[pid].sort_values(ascending=False).head(6)
            ct["leg"] = [[idx_tipo[d], _r(v)] for d, v in s.items() if v >= 1]

        item = {"id": pid, "k": "d" if p["casa"] == "camara" else "s", "n": p["nome"], "nc": p.get("nome_civil"),
                "g": p["cargo"], "pt": p.get("partido"), "uf": p.get("uf"), "f": p.get("foto"),
                "x": 1 if p.get("em_exercicio") else 0, "o": p.get("pagina_oficial"),
                "per": per, "t": serie, "ct": ct}
        if p["casa"] == "camara" and p.get("imovel_funcional_dias"):
            item["im"] = p["imovel_funcional_dias"]
        if p["casa"] == "senado" and p.get("imovel_funcional"):
            item["im"] = p["imovel_funcional"]
        saida.append(item)

    limites = pd.read_csv(RAIZ / "dados" / "referencia" / "limites_cota_camara.csv").set_index("uf")["limite_mensal"].to_dict()
    dados = {
        "meta": {
            "gerado_em": meta["gerado_em"],
            "atualizado": datetime.fromisoformat(meta["gerado_em"]).strftime("%d/%m/%Y"),
            "anos": [str(a) for a in anos],
            "ultimo_mes": int(lanc[lanc.mes.notna()].eval("ano*100+mes").max()),
            "salario_minimo": {str(k): v for k, v in meta["salario_minimo"].items()},
            "categorias": meta["categorias"],
            "tipos_cota": tipos,
            "limites_cota_camara": limites,
            "pendencias": meta["pendencias"],
            "fontes": meta["fontes"],
        },
        "p": saida,
    }
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log(f"Site: {SAIDA.relative_to(RAIZ)} ({SAIDA.stat().st_size / 1e6:.1f} MB, {len(saida)} políticos)")
