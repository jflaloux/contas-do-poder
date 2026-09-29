"""Gera os dados compactos que o site usa: site/dados/dados.json.

Formato (chaves curtas para o arquivo ficar pequeno):
  meta: informações gerais, categorias, tipos de despesa da cota, salário mínimo, pendências
  p: lista de políticos, cada um com
     id, k ("d" deputado / "s" senador / "e" governo federal), n (nome), nc (nome civil), g (cargo), pt (partido), uf,
     tp (só governo: "pr" presidente, "vp" vice, "mi" ministro), rel (id do mesmo político no outro cargo, se houver),
     q (só governo: [meses, total] recebido depois de deixar o cargo, fora das médias),
     j (quem tem dois cargos: id do registro "tudo junto"),
  Registros "tudo junto" (k "j", id "jun-..."): somam os dois cargos sem contar nada duas vezes, com
     cg: [{id, g, x, de, ate, ex}] os cargos (ex = meses exercendo) e tr: [[aaaamm_inicio, aaaamm_fim, "e"|"d"|"s"], ...]
     o cargo de cada mês.
     f (foto: "fotos/{id}.webp" no próprio site, ou o endereço oficial se não baixou), x (em exercício), o (página oficial),
     per: {"2023": {m, mg, mc, me, g, c, e, pm, mp, pu, cats}, ..., "leg": {...}}
          m = meses com algum valor; mg/mc/me = meses com ganha/custa/equipe;
          g/c/e = totais de ganha, custa (despesas dele) e equipe;
          pm = soma de pessoas-mês da equipe; mp = meses com equipe contada; pu = pessoas no último mês
     t: série mensal [[aaaamm, ganha, custa, equipe, pessoas, rateado], ...]
        rateado = parte do mês que veio de um valor anual dividido pelos meses (aproximação)
     dt: {"2025": {"cota_parlamentar": [[índice_do_tipo, valor], ...], "viagens_oficiais": [...], ...}, ..., "leg": {...}}
         detalhe de algumas categorias (até 8 tipos cada, total do período; o site divide pelos meses)
     nv: {"2025": viagens, ...} (só governo: número de viagens oficiais no período)
     im: imóvel funcional
"""
import json
import re
from datetime import datetime

import pandas as pd

from .config import BRUTOS, PROCESSADOS, RAIZ
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


def _empresa(texto):
    """'Jetons: SERVICO SOCIAL DO COMERCIO - SESC' -> 'Servico Social do Comercio (SESC)'."""
    t = texto.replace("Jetons: ", "").strip()
    sigla = ""
    if " - " in t and len(t.rsplit(" - ", 1)[1]) <= 8:
        t, sigla = t.rsplit(" - ", 1)
    pequenas = {"de", "da", "do", "das", "dos", "e", "em", "a", "o"}
    palavras = []
    for k, w in enumerate(t.split()):
        if "." in w or (w.isupper() and len(w) <= 2 and w.lower() not in pequenas):
            palavras.append(w)  # S.A., BB...
        elif k and w.lower() in pequenas:
            palavras.append(w.lower())
        else:
            palavras.append(w.capitalize())
    nome = " ".join(palavras)
    return f"{nome} ({sigla})" if sigla else nome


# categorias com detalhe por tipo -> como transformar a descrição do lançamento no nome do tipo
DETALHE = {
    "cota_parlamentar": tipo_simples,
    "outros_gastos_mandato": lambda d: re.sub(r"\s*\(ATC[^)]*\)", "", d.split(" (R$")[0]).strip(),
    "viagens_oficiais": lambda d: d.split(" (")[0].strip(),
    "jetons": _empresa,
}


def _mes_seguinte(aaaamm):
    a, m = divmod(aaaamm, 100)
    return a * 100 + m + 1 if m < 12 else (a + 1) * 100 + 1


def _item_junto(j, per, serie, dt, nv, mm):
    """Registro 'tudo junto' de quem tem dois cargos: cargos, cargo de cada mês e os totais somados."""
    e, par = j["exe"], j["par"]
    k_par = "d" if par["casa"] == "camara" else "s"
    meses_min = set(e.get("meses_no_cargo") or [])
    ultimo_portal = e.get("ultimo_mes_publicado") or 0
    ainda_ministro = bool(e.get("em_exercicio"))  # o Portal atrasa ~2 meses: quem estava no cargo segue no cargo
    ativos = {int(r.ano) * 100 + int(r.mes) for r in mm.itertuples() if r.ganha > 0 or r.custa > 0 or r.equipe > 0}
    exercendo = sorted(int(r.ano) * 100 + int(r.mes) for r in mm.itertuples() if (r.custa > 0 or r.equipe > 0)
                       and int(r.ano) * 100 + int(r.mes) not in meses_min
                       and not (ainda_ministro and int(r.ano) * 100 + int(r.mes) > ultimo_portal))
    faixas = []
    for m in sorted(ativos | meses_min):
        c = "e" if m in meses_min or (ainda_ministro and m > ultimo_portal) else k_par
        if faixas and faixas[-1][2] == c and _mes_seguinte(faixas[-1][1]) == m:
            faixas[-1][1] = m
        else:
            faixas.append([m, m, c])
    cargo_par = par["cargo"][0].lower() + par["cargo"][1:]
    foto_exe = FOTOS / f"{e['id']}.webp"
    return {
        "id": j["id"], "k": "j", "n": e["nome"], "nc": e.get("nome_civil"),
        "g": f"{e['cargo']} e {cargo_par}", "pt": par.get("partido"), "uf": par.get("uf"),
        "f": f"fotos/{e['id']}.webp" if foto_exe.exists() else par.get("foto"),
        "x": 1 if (e.get("em_exercicio") or par.get("em_exercicio")) else 0, "o": e.get("pagina_oficial"),
        "per": per, "t": serie, "dt": dt, **({"nv": nv} if nv else {}),
        "tr": faixas,
        "cg": [
            {"id": e["id"], "g": e["cargo"], "x": 1 if e.get("em_exercicio") else 0,
             "de": min(meses_min) if meses_min else None, "ate": max(meses_min) if meses_min else None, "ex": len(meses_min)},
            {"id": par["id"], "g": par["cargo"], "x": 1 if par.get("em_exercicio") else 0,
             "de": exercendo[0] if exercendo else None, "ate": exercendo[-1] if exercendo else None, "ex": len(exercendo)},
        ],
    }


def _r(v):
    return int(round(float(v)))


def executar():
    politicos = ler_json(PROCESSADOS / "politicos.json")
    meta = ler_json(PROCESSADOS / "metadados.json")
    lanc = pd.read_csv(PROCESSADOS / "lancamentos.csv.gz")
    equipe = pd.read_csv(PROCESSADOS / "equipe.csv")

    # Quem tem dois cargos (ministro que é deputado ou senador): um registro "tudo junto" que soma os dois sem
    # contar nada duas vezes. Entra tudo do Congresso e, do governo, só o que vem do Portal da Transparência
    # (o salário que o Congresso pagou nos meses como ministro já está do lado do Congresso).
    por_id = {p["id"]: p for p in politicos}
    juntos, extra_l, extra_e = [], [], []
    for e in politicos:
        par = por_id.get(e.get("relacionado")) if e["casa"] == "executivo" else None
        if not par:
            continue
        jid = "jun-" + e["id"].split("-")[1]
        extra_l.append(lanc[lanc.id_politico == par["id"]].assign(id_politico=jid))
        extra_l.append(lanc[(lanc.id_politico == e["id"]) & lanc.fonte.str.startswith("portal_")].assign(id_politico=jid))
        extra_e.append(equipe[equipe.id_politico == par["id"]].assign(id_politico=jid))
        juntos.append({"id": jid, "casa": "junto", "nome": e["nome"], "exe": e, "par": par})
    if juntos:
        lanc = pd.concat([lanc, *extra_l], ignore_index=True)
        equipe = pd.concat([equipe, *extra_e], ignore_index=True)
        # Na página só de deputado/senador, sai o salário dos meses como ministro: ele já está na página de ministro
        # (pago pelo Congresso, porque o licenciado pode escolher o salário do mandato) e não pode aparecer duas
        # vezes. Assim ministro + parlamentar = tudo junto. O "tudo junto" já foi montado acima, com tudo.
        am = lanc.ano * 100 + lanc.mes.fillna(0)
        tirar = pd.Series(False, index=lanc.index)
        for j in juntos:
            copiado = (lanc.id_politico == j["exe"]["id"]) & (lanc.grupo == "ganha") & ~lanc.fonte.str.startswith("portal_")
            meses = set(am[copiado])
            if meses:
                tirar |= (lanc.id_politico == j["par"]["id"]) & (lanc.grupo == "ganha") & ~lanc.rateado.astype(bool) & am.isin(meses)
        if tirar.any():
            log(f"Site: {int(tirar.sum())} lançamentos de salário dos meses como ministro saem da página de deputado/senador")
            lanc = lanc[~tirar]
    junto_de = {}
    for j in juntos:
        junto_de[j["exe"]["id"]] = junto_de[j["par"]["id"]] = j["id"]

    # detalhe por tipo de algumas categorias (o que aparece ao abrir cada linha do contracheque)
    det = lanc[lanc.categoria.isin(DETALHE)].copy()
    det["tipo"] = [DETALHE[c](d) for c, d in zip(det.categoria, det.descricao)]
    tipos = sorted(det["tipo"].unique())
    idx_tipo = {t: i for i, t in enumerate(tipos)}
    det_ano = det.groupby(["id_politico", "ano", "categoria", "tipo"])["valor"].sum()
    det_leg = det.groupby(["id_politico", "categoria", "tipo"])["valor"].sum()
    det_ids = set(det_ano.index.get_level_values(0))
    # número de viagens do governo federal, só nos meses no cargo
    viagens = pd.read_csv(BRUTOS / "executivo_viagens.csv") if (BRUTOS / "executivo_viagens.csv").exists() else None
    creditos = ler_json(FOTOS / "creditos.json").get("fotos", {}) if (FOTOS / "creditos.json").exists() else {}
    no_cargo = {p["id"]: set(p.get("meses_no_cargo") or []) for p in politicos if p["casa"] == "executivo"}
    for j in juntos:
        no_cargo[j["id"]] = no_cargo.get(j["exe"]["id"], set())

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

    def bloco(pid, mm, anos, exe=False, forcar=None):
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
            "mg": int((mm.ganha > 0).sum()), "me": int((mm.equipe > 0).sum()),
            "mc": m if exe else int(((mm.custa > 0) | (mm.ano * 100 + mm.mes).isin(forcar or set())).sum()),
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
    for p in politicos + juntos:
        pid = p["id"]
        mm = por_pol.get(pid, mensal.iloc[0:0])
        exe = p["casa"] == "executivo"
        forcar = no_cargo.get(pid) if p["casa"] == "junto" else None  # meses como ministro contam para a média dos gastos
        per = {}
        for ano in anos:
            b = bloco(pid, mm[mm.ano == ano], [ano], exe, forcar)
            if b["m"] or b["g"] or b["c"] or b["e"]:
                per[str(ano)] = b
        per["leg"] = bloco(pid, mm, anos, exe, forcar)
        serie = [[int(r.ano) * 100 + int(r.mes), _r(r.ganha), _r(r.custa), _r(r.equipe), int(r.pessoas), _r(r.rateado)]
                 for r in mm.sort_values(["ano", "mes"]).itertuples()]

        dt = {}
        if pid in det_ids:
            def por_categoria(serie):
                saida = {}
                for cat, g in serie.groupby(level=0):
                    g = g.droplevel(0).sort_values(ascending=False)
                    itens = [[idx_tipo[t], _r(v)] for t, v in g.head(8).items() if abs(v) >= 1]
                    if itens:
                        saida[cat] = itens
                return saida
            por_ano = det_ano.loc[pid]
            for ano in anos:
                if ano in por_ano.index.get_level_values(0):
                    dt[str(ano)] = por_categoria(por_ano.loc[ano])
            dt["leg"] = por_categoria(det_leg.loc[pid])
        nv = {}
        if (exe or p["casa"] == "junto") and viagens is not None:
            v = viagens[(viagens.id_portal == int(pid.split("-")[1]))]
            v = v[(v.ano * 100 + v.mes).isin(no_cargo.get(pid, set()))]
            nv = {str(a): int(n) for a, n in v.groupby("ano")["viagens"].sum().items()}
            if nv:
                nv["leg"] = sum(nv.values())

        if p["casa"] == "junto":
            saida.append(_item_junto(p, per, serie, dt, nv, mm))
            continue
        item = {"id": pid, "k": {"camara": "d", "senado": "s", "executivo": "e"}[p["casa"]], "n": p["nome"], "nc": p.get("nome_civil"),
                "g": p["cargo"], "pt": p.get("partido"), "uf": p.get("uf"),
                "f": f"fotos/{pid}.webp" if (FOTOS / f"{pid}.webp").exists() else p.get("foto"),
                "x": 1 if p.get("em_exercicio") else 0, "o": p.get("pagina_oficial"),
                "per": per, "t": serie, "dt": dt}
        if nv:
            item["nv"] = nv
        if exe:
            item["tp"] = {"presidente": "pr", "vice": "vp"}.get(p.get("tipo"), "mi")
            credito = creditos.get(pid)
            if credito and item["f"] and item["f"].startswith("fotos/"):
                item["fc"] = {"a": credito.get("autor"), "l": credito.get("licenca"), "u": credito.get("pagina")}
            if p.get("quarentena"):
                item["q"] = [p["quarentena"]["meses"], _r(p["quarentena"]["total"])]
        if p.get("relacionado"):
            item["rel"] = p["relacionado"]
        if pid in junto_de:
            item["j"] = junto_de[pid]
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
            "tipos": tipos,
            "limites_cota_camara": limites,
            "pendencias": meta["pendencias"],
            "fontes": meta["fontes"],
        },
        "p": saida,
    }
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log(f"Site: {SAIDA.relative_to(RAIZ)} ({SAIDA.stat().st_size / 1e6:.1f} MB, {len(saida)} políticos)")
    _municipios()


# ---------------------------------------------------------------- câmaras municipais
SUBSIDIO_DEPUTADO_FEDERAL = 46366.19  # o deputado estadual ganha no máximo 75% disso (Constituição, art. 27)
# teto do salário do vereador (Constituição, art. 29, VI): % do salário do deputado estadual, pela população
FAIXAS_TETO = [(10_000, 0.20), (50_000, 0.30), (100_000, 0.40), (300_000, 0.50), (500_000, 0.60), (float("inf"), 0.75)]


def _municipios():
    """site/dados/municipios.json (todas as cidades) e site/dados/vereadores/UF.json (nomes, lidos sob demanda).
    municipios.json -> m: [[cod_ibge, nome, uf, populacao, capital, vereadores, custo_anual, ano_do_custo], ...]"""
    pasta = RAIZ / "dados" / "municipios"
    if not (pasta / "municipios.csv").exists():
        return
    mu = pd.read_csv(pasta / "municipios.csv")
    mu = mu[mu.uf != "DF"]  # Brasília não tem câmara municipal
    custo = pd.read_csv(pasta / "camaras_custo.csv") if (pasta / "camaras_custo.csv").exists() else pd.DataFrame(columns=["cod_ibge", "ano", "legislativa", "controle_externo"])
    custo = custo[custo.legislativa.notna()].copy()
    custo["custo"] = custo.legislativa - custo.controle_externo.fillna(0)
    custo = custo[custo.custo > 0].sort_values("ano").groupby("cod_ibge").tail(1).set_index("cod_ibge")
    ver = pd.read_csv(pasta / "vereadores.csv") if (pasta / "vereadores.csv").exists() else None
    n_ver = ver.groupby("cod_ibge").size() if ver is not None else pd.Series(dtype=int)
    linhas = []
    for r in mu.itertuples():
        c = custo.loc[r.cod_ibge] if r.cod_ibge in custo.index else None
        linhas.append([int(r.cod_ibge), r.nome, r.uf, int(r.populacao or 0), int(r.capital), int(n_ver.get(r.cod_ibge, 0)),
                       _r(c.custo) if c is not None else None, int(c.ano) if c is not None else None])
    saida = RAIZ / "site" / "dados" / "municipios.json"
    saida.write_text(json.dumps({
        "meta": {"teto_deputado_estadual": round(SUBSIDIO_DEPUTADO_FEDERAL * 0.75, 2), "faixas_teto": [[f if f != float("inf") else None, pct] for f, pct in FAIXAS_TETO],
                 "fonte_custo": "Tesouro Nacional (Siconfi), Declaração de Contas Anuais, função Legislativa, despesas liquidadas",
                 "fonte_vereadores": "TSE, eleitos em 2024"},
        "m": linhas}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    if ver is not None:
        pasta_v = RAIZ / "site" / "dados" / "vereadores"
        pasta_v.mkdir(parents=True, exist_ok=True)
        uf_de = dict(zip(mu.cod_ibge, mu.uf))
        ver["uf"] = ver.cod_ibge.map(uf_de)
        for uf, g in ver[ver.uf.notna()].groupby("uf"):
            por = {str(c): [[n.title(), pt, gn] for n, pt, gn in zip(gg.nome_urna, gg.partido, gg.genero)] for c, gg in g.groupby("cod_ibge")}
            (pasta_v / f"{uf}.json").write_text(json.dumps(por, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log(f"Site: câmaras municipais — {len(linhas)} cidades, {saida.stat().st_size / 1e3:.0f} KB")
