"""Gera os dados compactos que o site usa: site/dados/dados.json.

Formato (chaves curtas para o arquivo ficar pequeno):
  meta: informações gerais, categorias, tipos de despesa da cota, salário mínimo, pendências
  p: lista de políticos, cada um com
     id, k ("d" deputado / "s" senador / "e" governo federal), n (nome), nc (nome civil), g (cargo), pt (partido), uf,
     tp (só governo: "pr" presidente, "vp" vice, "mi" ministro), rel (id do mesmo político no outro cargo, se houver),
     q (só governo: [meses, total] recebido depois de deixar o cargo, fora das médias),
     f (foto: "fotos/{id}.webp" no próprio site, ou o endereço oficial se não baixou), x (em exercício), o (página oficial),
     per: {"2023": {m, mg, mc, me, g, c, e, pm, mp, pu, cats}, ..., "leg": {...}}
          m = meses com algum valor; mg/mc/me = meses com ganha/custa/equipe;
          g/c/e = totais de ganha, custa (despesas dele) e equipe;
          pm = soma de pessoas-mês da equipe; mp = meses com equipe contada; pu = pessoas no último mês
     t: série mensal [[aaaamm, ganha, custa, equipe, pessoas, rateado], ...]
        rateado = parte do mês que veio de um valor anual dividido pelos meses (aproximação)
     ct: {"2025": [[índice_do_tipo, valor], ...], ..., "leg": [...]}   (top 6 tipos da cota, total do período;
         o site divide pelos meses para mostrar a média por mês)
     im: imóvel funcional
"""
import json
from datetime import datetime

import pandas as pd

from .config import PROCESSADOS, RAIZ
from .util import ler_json, log, normalizar_nome

SAIDA = RAIZ / "site" / "dados" / "dados.json"
FOTOS = RAIZ / "site" / "fotos"


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
    equipe = pd.read_csv(PROCESSADOS / "equipe.csv")

    cota = lanc[lanc.categoria == "cota_parlamentar"].copy()
    cota["descricao"] = cota["descricao"].map(tipo_simples)
    tipos = sorted(cota["descricao"].unique())
    idx_tipo = {t: i for i, t in enumerate(tipos)}
    cota_ano = cota.groupby(["id_politico", "ano", "descricao"])["valor"].sum()
    cota_leg = cota.groupby(["id_politico", "descricao"])["valor"].sum()

    # Valores por mês e grupo; cada média usa os seus próprios meses
    # (ex.: deputado licenciado não recebe salário, mas o gabinete continua gastando).
    mensal = (lanc[lanc.mes.notna()].groupby(["id_politico", "ano", "mes", "grupo"])["valor"].sum()
              .unstack("grupo").fillna(0.0).reset_index())
    for g in ("ganha", "custa", "equipe"):
        if g not in mensal:
            mensal[g] = 0.0
    mensal = mensal.merge(equipe[["id_politico", "ano", "mes", "pessoas"]], on=["id_politico", "ano", "mes"], how="left")
    mensal["pessoas"] = mensal["pessoas"].fillna(0).astype(int)
    rateado = (lanc[lanc.rateado].groupby(["id_politico", "ano", "mes"])["valor"].sum()
               .rename("rateado").reset_index())
    mensal = mensal.merge(rateado, on=["id_politico", "ano", "mes"], how="left")
    mensal["rateado"] = mensal["rateado"].fillna(0.0)
    totais = lanc.groupby(["id_politico", "ano", "grupo"])["valor"].sum()
    cats = lanc.groupby(["id_politico", "ano", "categoria"])["valor"].sum()

    def bloco(pid, mm, anos, exe=False):
        """Resumo de um período: meses, totais por grupo, pessoas da equipe e categorias.
        Governo federal: as viagens não acontecem todo mês, então a média dos gastos usa todos os meses no cargo."""
        g = sum(totais.get((pid, a, "ganha"), 0.0) for a in anos)
        c = sum(totais.get((pid, a, "custa"), 0.0) for a in anos)
        e = sum(totais.get((pid, a, "equipe"), 0.0) for a in anos)
        # média por pessoa: só meses que têm o custo da equipe E a contagem de pessoas
        com_equipe = mm[(mm.pessoas > 0) & (mm.equipe > 0)].sort_values(["ano", "mes"])
        com_pessoas = mm[mm.pessoas > 0].sort_values(["ano", "mes"])
        cat = {}
        for a in anos:
            if (pid, a) in cats_idx:
                for k, v in cats.loc[pid, a].items():
                    cat[k] = cat.get(k, 0.0) + v
        m = int(((mm.ganha > 0) | (mm.custa > 0) | (mm.equipe > 0)).sum())
        return {
            "m": m,
            "mg": int((mm.ganha > 0).sum()), "mc": m if exe else int((mm.custa > 0).sum()), "me": int((mm.equipe > 0).sum()),
            "g": _r(g), "c": _r(c), "e": _r(e),
            "pm": int(com_equipe.pessoas.sum()), "mp": int(len(com_equipe)),
            "pu": int(com_pessoas.pessoas.iloc[-1]) if len(com_pessoas) else 0,
            "ep": _r(com_equipe.equipe.sum()),
            "cats": {k: _r(v) for k, v in cat.items() if abs(v) >= 1},
        }

    cats_idx = set(cats.index.droplevel(2))
    anos = sorted(int(a) for a in lanc["ano"].unique())
    por_pol = {pid: mm for pid, mm in mensal.groupby("id_politico")}
    saida = []
    for p in politicos:
        pid = p["id"]
        mm = por_pol.get(pid, mensal.iloc[0:0])
        exe = p["casa"] == "executivo"
        per = {}
        for ano in anos:
            b = bloco(pid, mm[mm.ano == ano], [ano], exe)
            if b["m"] or b["g"] or b["c"] or b["e"]:
                per[str(ano)] = b
        per["leg"] = bloco(pid, mm, anos, exe)
        serie = [[int(r.ano) * 100 + int(r.mes), _r(r.ganha), _r(r.custa), _r(r.equipe), int(r.pessoas), _r(r.rateado)]
                 for r in mm.sort_values(["ano", "mes"]).itertuples()]

        ct = {}
        for ano in anos:
            if (pid, ano) in cota_ano.index.droplevel(2):
                s_ = cota_ano.loc[pid, ano].sort_values(ascending=False).head(6)
                ct[str(ano)] = [[idx_tipo[d], _r(v)] for d, v in s_.items() if v >= 1]
        if pid in cota_leg.index.get_level_values(0):
            s_ = cota_leg.loc[pid].sort_values(ascending=False).head(6)
            ct["leg"] = [[idx_tipo[d], _r(v)] for d, v in s_.items() if v >= 1]

        item = {"id": pid, "k": {"camara": "d", "senado": "s", "executivo": "e"}[p["casa"]], "n": p["nome"], "nc": p.get("nome_civil"),
                "g": p["cargo"], "pt": p.get("partido"), "uf": p.get("uf"),
                "f": f"fotos/{pid}.webp" if (FOTOS / f"{pid}.webp").exists() else p.get("foto"),
                "x": 1 if p.get("em_exercicio") else 0, "o": p.get("pagina_oficial"),
                "per": per, "t": serie, "ct": ct}
        if exe:
            item["tp"] = {"presidente": "pr", "vice": "vp"}.get(p.get("tipo"), "mi")
            if p.get("quarentena"):
                item["q"] = [p["quarentena"]["meses"], _r(p["quarentena"]["total"])]
        if p.get("relacionado"):
            item["rel"] = p["relacionado"]
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
            "ultimo_mes_executivo": max((p.get("ultimo_mes_publicado") or 0) for p in politicos),
            "salario_minimo": {str(k): v for k, v in meta["salario_minimo"].items()},
            "categorias": meta["categorias"],
            "rateio": meta["rateio"],
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
