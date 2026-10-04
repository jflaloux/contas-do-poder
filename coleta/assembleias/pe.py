"""Assembleia Legislativa de Pernambuco (Alepe): deputado estadual por deputado estadual.

Fontes (as que o Portal da Transparência da Alepe, https://transparencia.alepe.pe.gov.br/, usa; sem cadastro):
- Deputados em exercício: https://dadosabertos.alepe.pe.gov.br/api/v1/parlamentares/ (nome e partido) e, para o número
  de cada um, https://www.alepe.pe.gov.br/servicos/transparencia/dep/deputados.php?leg=-16.
- Verba indenizatória, prestação por prestação (principal e complementar), com o total:
  .../servicos/transparencia/adm/verbaindenizatoria.php?ano=AAAA&mes=M; e as notas de cada prestação (rubrica, data,
  CNPJ, empresa, valor): .../adm/verbaindenizatorianotas.php?docid=N; nomes das rubricas:
  .../adm/verbaindenizatoria-rubricas.php?ano=AAAA.
- Subsídio: Lei 18.138/2023 (R$ 33.006,39 desde fev/2024 e R$ 34.774,64 desde fev/2025).
- Nome completo, gênero e eleito/suplente: TSE (eleição de 2022).
As notas de cada prestação são baixadas aos poucos (no máximo MAX_DOCS por vez, das mais recentes para as mais
antigas); enquanto não chegam, a prestação entra com o total, sem o detalhe.
"""
import json
import time

import pandas as pd

from ..config import CACHE, DADOS
from ..prefeituras.comum import feminino, num
from ..util import TempoEsgotado, _sessao, dormir, gravar_csv, log, normalizar_nome, verificar_prazo
from ..vereadores import comum as vc
from . import comum

UF = "PE"
COD = comum.CODIGOS_UF[UF]
INICIO = 202501
API = "https://www.alepe.pe.gov.br/servicos/transparencia"
ABERTOS = "https://dadosabertos.alepe.pe.gov.br/api/v1/parlamentares/"
PASTA = DADOS / "assembleias" / "pe"
C = CACHE / "assembleias" / "pe"
MAX_DOCS = 400
PAUSA = 0.5
MESES = {normalizar_nome(m): i for i, m in enumerate(["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro",
                                                      "Outubro", "Novembro", "Dezembro"], 1)}
SEM_DETALHE = "Verba indenizatória (notas ainda não baixadas)"
CFG = {
    "cod": COD, "n": "Pernambuco", "uf": UF, "casa": "Assembleia Legislativa de Pernambuco", "vagas": 49, "inicio": INICIO,
    "id_prefixo": "est", "k": "e", "cargo": ("Deputada estadual", "Deputado estadual"),
    "subsidio": [[202402, 33006.39], [202502, 34774.64]],
    "salario_nota": ("Subsídio fixado em lei (Lei 18.138/2023), proporcional aos dias no cargo. A Alepe não publica a folha nominal "
                     "dos deputados, por isso o 13º e outros pagamentos não aparecem aqui."),
    "verba_nome": "Verba indenizatória",
    "verba_regra": "Reembolso de despesas do mandato com nota fiscal, até o limite de cada rubrica.",
    "verba_notas": ["Cada mês pode ter uma prestação principal e uma complementar; as duas entram no mês."],
    "pagina": "https://transparencia.alepe.pe.gov.br/",
    "notas": ["Quem estava no cargo: os deputados em exercício hoje, nos dados abertos da Alepe, e, para quem saiu, os meses com "
              "prestação de contas da verba."],
    "fontes": {"deputados": ABERTOS, "verba": "https://transparencia.alepe.pe.gov.br/",
               "subsidio": "https://legis.alepe.pe.gov.br/texto.aspx?tiponorma=1&numero=18138&complemento=0&ano=2023&tipo=&url="},
}


def _json(url, params=None):
    verificar_prazo()
    for tentativa in range(3):
        try:
            r = _sessao().get(url, params=params, timeout=120)
            r.raise_for_status()
            dormir(PAUSA)
            return r.json()
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 2:
                raise
            dormir(15)


def _meses():
    hoje = time.localtime()
    return [am for am in (a * 100 + m for a in range(INICIO // 100, hoje.tm_year + 1) for m in range(1, 13)) if INICIO <= am <= hoje.tm_year * 100 + hoje.tm_mon]


def coletar():
    PASTA.mkdir(parents=True, exist_ok=True)
    (C / "notas").mkdir(parents=True, exist_ok=True)
    em_exercicio = _json(ABERTOS)
    todos = _json(f"{API}/dep/deputados.php", {"leg": "-16"})
    gravar_csv(pd.DataFrame(todos)[["id", "nome", "partido"]], PASTA / "deputados_alepe.csv")
    gravar_csv(pd.DataFrame(em_exercicio).rename(columns={"nomeParlamentar": "nome"}).assign(visto_em=time.strftime("%Y-%m-%d")), PASTA / "em_exercicio.csv")
    # prestações de contas, mês a mês (os meses antigos ficam no cache)
    prest_arq = PASTA / "verba_prestacoes.csv"
    antigas = pd.read_csv(prest_arq, dtype={"docid": str}) if prest_arq.exists() else pd.DataFrame(columns=["ano", "mes", "docid", "tipo", "deputado", "total"])
    feitos = set(antigas.ano * 100 + antigas.mes) if len(antigas) else set()
    meses = _meses()
    novas = []
    for am in meses:
        if am in feitos and am < meses[-3]:
            continue
        for x in _json(f"{API}/adm/verbaindenizatoria.php", {"ano": am // 100, "mes": am % 100}) or []:
            novas.append({"ano": am // 100, "mes": am % 100, "docid": str(x["docid"]), "tipo": x.get("tipo", ""), "deputado": x["deputado"].strip(),
                          "total": num(x.get("total"))})
    if novas:
        nv = pd.DataFrame(novas)
        refeitos = set(nv.ano * 100 + nv.mes)
        antigas = pd.concat([antigas[~(antigas.ano * 100 + antigas.mes).isin(refeitos)], nv], ignore_index=True)
    gravar_csv(antigas.sort_values(["ano", "mes", "deputado", "docid"]), prest_arq)
    # rubricas (nome de cada número), por ano
    rubricas = {}
    for ano in sorted({am // 100 for am in meses}):
        for r in _json(f"{API}/adm/verbaindenizatoria-rubricas.php", {"ano": ano}) or []:
            rubricas[(ano, int(r["numero_categoria"]))] = r["nome_categoria"].strip()
    # notas das prestações, das mais recentes para as mais antigas, no máximo MAX_DOCS por vez
    baixadas = 0
    try:
        for p in antigas.sort_values(["ano", "mes"], ascending=False).itertuples():
            arq = C / "notas" / f"{p.docid}.json"
            if arq.exists() or baixadas >= MAX_DOCS:
                continue
            arq.write_text(json.dumps(_json(f"{API}/adm/verbaindenizatorianotas.php", {"docid": p.docid}) or [], ensure_ascii=False), encoding="utf-8")
            baixadas += 1
    finally:
        linhas = []
        for p in antigas.itertuples():
            arq = C / "notas" / f"{p.docid}.json"
            notas = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else None
            if not notas:
                linhas.append({"ano": p.ano, "mes": p.mes, "docid": p.docid, "deputado": p.deputado, "tipo": SEM_DETALHE if notas is None else "Verba indenizatória",
                               "fornecedor": "", "cnpj_cpf": "", "data": "", "valor": p.total})
                continue
            for n in notas:
                linhas.append({"ano": p.ano, "mes": p.mes, "docid": p.docid, "deputado": p.deputado,
                               "tipo": rubricas.get((int(p.ano), int(n.get("rubrica") or 0)), "Outras despesas"),
                               "fornecedor": (n.get("empresa") or "").strip(), "cnpj_cpf": vc.mascarar(n.get("cnpj") or ""), "data": n.get("data", ""),
                               "valor": num(n.get("valor"))})
        gravar_csv(pd.DataFrame(linhas).sort_values(["ano", "mes", "deputado", "docid", "data"]), PASTA / "verba_notas.csv")
        faltam = sum(1 for p in antigas.itertuples() if not (C / "notas" / f"{p.docid}.json").exists())
        log(f"  Alepe: {len(em_exercicio)} deputados em exercício, {len(antigas)} prestações, {baixadas} com notas baixadas agora, {faltam} ainda sem notas")


def montar(tipos):
    arq_v, arq_e = PASTA / "verba_notas.csv", PASTA / "em_exercicio.csv"
    if not arq_e.exists():
        return None
    verba = pd.read_csv(arq_v, dtype={"cnpj_cpf": str, "docid": str}).fillna("") if arq_v.exists() else pd.DataFrame()
    exerc = pd.read_csv(arq_e).fillna("")
    alepe = pd.read_csv(PASTA / "deputados_alepe.csv", dtype=str).fillna("")
    ids = {normalizar_nome(n): i for n, i in zip(alepe.nome, alepe.id)}
    tse = comum.tse_2022(UF)
    ultimo = vc.ultimo_mes_fechado()
    ultimo_dado = int((verba.ano * 100 + verba.mes).max()) if len(verba) else ultimo
    partido_hoje = {normalizar_nome(n): p for n, p in zip(exerc.nome, exerc.partido)}
    partido_alepe = dict(zip(alepe.id, alepe.partido))
    nomes = sorted(set(exerc.nome) | set(verba.deputado if len(verba) else []), key=normalizar_nome)
    ver, mandatos, cods = [], [], {}
    for nome in nomes:
        n = normalizar_nome(nome)
        t = comum.achar(nome, tse) or {}
        codigo = int(ids[n]) if ids.get(n, "").isdigit() else comum.codigo_de(nome, t)
        cods[nome] = codigo
        ver.append({"codigo": codigo, "nome": nome, "nome_civil": vc.titulo(t.get("nome", "")) if t else "",
                    "partido": partido_hoje.get(n) or partido_alepe.get(str(codigo), ""),
                    "genero": t.get("genero") or ("F" if feminino(nome) else "M"), "eleito": t.get("eleito", ""),
                    "pagina": "https://www.alepe.pe.gov.br/parlamentares/"})
        meses_v = list(verba[verba.deputado == nome].ano * 100 + verba[verba.deputado == nome].mes) if len(verba) else []
        if n in partido_hoje:  # em exercício hoje
            meses_v = sorted(set(meses_v) | {ultimo_dado})
            de = min(meses_v) if meses_v else INICIO
            de = INICIO if de <= vc.mes_seguinte(INICIO) else de
            mandatos.append({"codigo": codigo, "inicio": f"{de // 100}-{de % 100:02d}-01", "fim": ""})
        else:
            for i, f in comum.periodos(meses_v, ultimo_dado, ultimo, folga=1):
                mandatos.append({"codigo": codigo, "inicio": i, "fim": f if f else f"{ultimo_dado // 100}-{ultimo_dado % 100:02d}-28"})
    desp = verba.assign(codigo=verba.deputado.map(cods)) if len(verba) else None
    cfg = dict(CFG, ultimo_mes=min(ultimo, ultimo_dado))
    return vc.montar(cfg, tipos, pd.DataFrame(ver), pd.DataFrame(mandatos),
                     despesas=desp[["ano", "mes", "codigo", "tipo", "fornecedor", "cnpj_cpf", "valor"]] if desp is not None else None)
