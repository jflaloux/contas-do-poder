"""Câmara Municipal de Manaus: vereador por vereador.

Fontes (dados abertos da Câmara, sem cadastro):
- Mandatos, nome, sexo, foto e partido: SAPL, https://sapl.cmm.am.gov.br/api/
- Folha de pagamento nominal, mês a mês (vereadores e assessores; a lotação do assessor é "VER. <nome>"):
  https://www.cmm.am.gov.br/wp-admin/admin-ajax.php, action=cmm_remuneracao_nominal_servidores_fetch
- CEAP (Cota para o Exercício da Atividade Parlamentar), nota por nota, com fornecedor e CNPJ:
  mesmo endereço, action=cmm_cotas_ceap_parlamentares (lista do ano) e cmm_cotas_ceap_fetch (notas do ano)
O CPF dos servidores vem mascarado e não é guardado.
"""
import html
import json
import re
import time

import pandas as pd

from ..config import CACHE, DADOS
from ..util import _sessao, cache_valido, log, normalizar_nome, verificar_prazo
from . import comum, sapl

COD = 1302603
INICIO = 202501
BASE_SAPL = "https://sapl.cmm.am.gov.br"
AJAX = "https://www.cmm.am.gov.br/wp-admin/admin-ajax.php"
PASTA = DADOS / "municipios" / "manaus"
C = CACHE / "cmm"
REBAIXAR = 3  # meses mais recentes que ainda podem mudar
CFG = {
    "cod": COD, "n": "Manaus", "uf": "AM", "casa": "Câmara Municipal de Manaus", "vagas": 41, "inicio": INICIO,
    "verba_nome": "Cota para o Exercício da Atividade Parlamentar (CEAP)", "verba_mes": {"2025": 33085.85, "2026": 33085.85},
    "verba_regra": "Reembolso com nota fiscal. O que não é usado num mês fica para os meses seguintes.",
    "verba_notas": ["As notas entram no mês da emissão."],
    "salario_nota": "Subsídio pela folha de pagamento da Câmara, mês a mês. A folha publicada mostra só o subsídio: 13º e férias não aparecem aqui.",
    "equipe_nota": "Assessores lotados no gabinete, pela folha de pagamento da Câmara (salário e benefícios brutos).",
    "credito_foto": "Câmara Municipal de Manaus", "pagina": "https://www.cmm.am.gov.br/vereadores/",
    "fontes": {"mandatos": f"{BASE_SAPL}/api/parlamentares/mandato/", "folha": "https://www.cmm.am.gov.br/transparencia/",
               "ceap": "https://www.cmm.am.gov.br/transparencia/"},
}


def _ajax(dados, arquivo=None, dias=None):
    if arquivo is not None and cache_valido(arquivo, dias):
        return json.loads(arquivo.read_text(encoding="utf-8"))
    verificar_prazo()
    for tentativa in range(3):
        try:
            r = _sessao().post(AJAX, data=dados, timeout=180)
            r.raise_for_status()
            d = r.json()
            break
        except Exception:
            if tentativa == 2:
                raise
            time.sleep(10)
    time.sleep(2)
    if arquivo is not None:
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return d


def _valor(t):
    t = re.sub(r"[^\d,]", "", t or "")
    return float(t.replace(",", ".")) if t else 0.0


def _categoria(desc):
    d = normalizar_nome(desc)
    if "SUBSID" in d:
        return "salario"
    if "13" in d or "NATAL" in d:
        return "decimo_terceiro"
    if "AUX" in d or "ALIM" in d:
        return "auxilios"
    return "outros_rendimentos"


def folha():
    """Resumo mensal da folha: vereadores (por rubrica) e gabinetes (pessoas e custo); guarda só o resumo."""
    ate = comum.ultimo_mes_fechado()
    arq_v, arq_g, arq_c = PASTA / "folha_vereadores.csv", PASTA / "folha_gabinetes.csv", PASTA / "cargos_gabinetes.csv"
    fv = pd.read_csv(arq_v) if arq_v.exists() else pd.DataFrame(columns=["ano", "mes", "nome", "categoria", "valor"])
    fg = pd.read_csv(arq_g) if arq_g.exists() else pd.DataFrame(columns=["ano", "mes", "lotacao", "pessoas", "custo"])
    feitos = set(fg.ano * 100 + fg.mes) if len(fg) else set()
    recentes = comum.menos_meses(ate, REBAIXAR)
    cargos_ultimo = None
    for a, m in comum.meses(INICIO, ate):
        am = a * 100 + m
        if am in feitos and am <= recentes:
            continue
        d = _ajax({"action": "cmm_remuneracao_nominal_servidores_fetch", "ano": a, "mes": m, "page": 1, "per_page": "all"})
        infos = [json.loads(html.unescape(x)) for x in re.findall(r'data-info="([^"]+)"', (d.get("data") or {}).get("html", ""))]
        if not infos:
            continue  # mês ainda não publicado
        v_linhas, gab = [], {}
        cargos = {}
        for i in infos:
            if normalizar_nome(i.get("vinculo")) == "VEREADOR" or normalizar_nome(i.get("cargo")) == "VEREADOR":
                for v in i.get("vantagens", []) + i.get("vencimentos", []):
                    v_linhas.append({"ano": a, "mes": m, "nome": i["nome"].strip(), "categoria": _categoria(v.get("descricao")), "valor": _valor(v.get("valor"))})
            elif normalizar_nome(i.get("lotacao")).startswith("VER"):
                lot = i["lotacao"].strip()
                custo = _valor(i.get("subtotal_vantagens")) + _valor(i.get("subtotal_vencimentos"))
                x = gab.setdefault(lot, [0, 0.0])
                x[0] += 1
                x[1] += custo
                nome_cargo = f"{i.get('vinculo') or ''} ({i.get('cargo')})".strip()
                cargos[(lot, nome_cargo)] = cargos.get((lot, nome_cargo), 0) + 1
        fv = pd.concat([fv[(fv.ano * 100 + fv.mes) != am], pd.DataFrame(v_linhas)], ignore_index=True)
        fg = pd.concat([fg[(fg.ano * 100 + fg.mes) != am],
                        pd.DataFrame([{"ano": a, "mes": m, "lotacao": k, "pessoas": n, "custo": round(c, 2)} for k, (n, c) in gab.items()])], ignore_index=True)
        cargos_ultimo = (a, m, cargos)
        PASTA.mkdir(parents=True, exist_ok=True)
        fv.to_csv(arq_v, index=False)
        fg.to_csv(arq_g, index=False)
        log(f"  Manaus: folha de {m:02d}/{a} ({len(infos)} pessoas)")
    if cargos_ultimo:
        a, m, cargos = cargos_ultimo
        pd.DataFrame([{"ano": a, "mes": m, "lotacao": k[0], "cargo": k[1], "pessoas": n} for k, n in cargos.items()]).to_csv(arq_c, index=False)


def ceap():
    """Notas da CEAP de cada vereador, um pedido por vereador por ano (o ano corrente é baixado de novo)."""
    ate = comum.ultimo_mes_fechado()
    notas, resumo = [], []
    for ano in range(INICIO // 100, ate // 100 + 1):
        dias = 5 if ano == ate // 100 else None
        lista = _ajax({"action": "cmm_cotas_ceap_parlamentares", "ano": ano}, C / f"ceap_lista_{ano}.json", dias)
        for p in lista.get("data") or []:
            d = _ajax({"action": "cmm_cotas_ceap_fetch", "modo": "sigae", "ano": ano, "mes_inicial": 1, "mes_final": 12, "parlamentar_id": p["id"]},
                      C / f"ceap_{ano}_{p['id']}.json", dias)
            dd = d.get("data") or {}
            fin = dd.get("financeiro") or {}
            resumo.append({"ano": ano, "nome": p["nome"].strip(), "cota_mensal": fin.get("cota_mensal"), "total_disponivel": fin.get("total_disponivel"),
                           "despesa": fin.get("despesa_reembolsavel"), "saldo": fin.get("saldo_atual")})
            for n in dd.get("notas") or []:
                data = (n.get("data_emissao") or "")[:10]
                if not data:
                    continue
                notas.append({"ano": int(data[:4]), "mes": int(data[5:7]), "nome": p["nome"].strip(), "item": (n.get("item_despesa") or "").strip(),
                              "fornecedor": (n.get("fornecedor") or "").strip(), "cnpj_cpf": comum.mascarar(n.get("cnpj")), "documento": n.get("numero_documento"),
                              "valor": float(n.get("valor") or 0)})
    PASTA.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(notas).to_csv(PASTA / "ceap_notas.csv", index=False)
    pd.DataFrame(resumo).to_csv(PASTA / "ceap_resumo.csv", index=False)
    log(f"  Manaus: {len(notas)} notas da CEAP")


def coletar():
    leg = sapl.legislatura_atual(BASE_SAPL)
    mand = sapl.mandatos(BASE_SAPL, leg["id"])
    PASTA.mkdir(parents=True, exist_ok=True)
    mand.to_csv(PASTA / "mandatos.csv", index=False)
    par = sapl.parlamentares(BASE_SAPL, list(mand.parlamentar.unique()), PASTA / "sapl_parlamentares.csv")
    comum.fotos(COD, [(int(i), f) for i, f in zip(par["id"], par["fotografia"]) if f])
    folha()
    ceap()


def _chave_lotacao(lot):
    t = normalizar_nome(re.sub(r"^VER\.?\s*", "", lot.strip(), flags=re.I))
    return re.sub(r"^(PROFA?|DRA?|CAPITAO|SARGENTO|CORONEL|PASTOR|PASTORA)\.?\s+", "", t.replace(".", " ")).split()


def montar(tipos):
    if not (PASTA / "mandatos.csv").exists():
        return None
    ate = comum.ultimo_mes_fechado()
    mand = pd.read_csv(PASTA / "mandatos.csv").fillna("")
    par = pd.read_csv(PASTA / "sapl_parlamentares.csv", dtype=str).fillna("")
    fv = pd.read_csv(PASTA / "folha_vereadores.csv") if (PASTA / "folha_vereadores.csv").exists() else pd.DataFrame(columns=["ano", "mes", "nome", "categoria", "valor"])
    fg = pd.read_csv(PASTA / "folha_gabinetes.csv") if (PASTA / "folha_gabinetes.csv").exists() else pd.DataFrame(columns=["ano", "mes", "lotacao", "pessoas", "custo"])
    fc = pd.read_csv(PASTA / "cargos_gabinetes.csv") if (PASTA / "cargos_gabinetes.csv").exists() else pd.DataFrame(columns=["lotacao", "cargo", "pessoas"])
    notas = pd.read_csv(PASTA / "ceap_notas.csv", dtype={"cnpj_cpf": str}).fillna({"cnpj_cpf": "", "fornecedor": ""}) if (PASTA / "ceap_notas.csv").exists() else None
    info = {int(i): r for i, r in zip(par["id"], par.itertuples())}
    por_nome = {normalizar_nome(r.nome_completo): int(r.id) for r in par.itertuples() if r.nome_completo}
    opcoes = [(r.nome_completo, int(r.id)) for r in par.itertuples() if r.nome_completo] + [(r.nome_parlamentar, int(r.id)) for r in par.itertuples()]
    # quem recebe como vereador e não está nos mandatos do SAPL: entra pelo TSE (código = número do candidato)
    tse = comum.candidatos_tse("AM", "Manaus")
    extras = {}

    def cod_folha(n):
        c = por_nome.get(normalizar_nome(n)) or comum.achar_parecido(n, opcoes, 0.9)
        if c:
            return c
        t = tse[tse.nome.map(normalizar_nome) == normalizar_nome(n)]
        if len(t):
            t = t.iloc[0]
            extras[int(t["sq"])] = t
            return int(t["sq"])
        return None
    codigos = {n: cod_folha(n) for n in set(fv.nome)}
    sem_nada = sorted(n for n, c in codigos.items() if c is None)
    if sem_nada:
        log(f"  Manaus: na folha como vereador e sem SAPL nem TSE: {', '.join(sem_nada)}")
    ultimo_folha = int((fv.ano * 100 + fv.mes).max()) if len(fv) else None
    # quem estava no cargo: os meses pagos como vereador (a folha é a melhor prova); sem folha, as datas do SAPL
    fv["codigo"] = fv.nome.map(codigos)
    pagos = fv[(fv.categoria == "salario") & (fv.valor > 0) & fv.codigo.notna()]
    linhas_m = []
    for cod in extras:
        meses_pagos = set(pagos[pagos.codigo == cod].ano * 100 + pagos[pagos.codigo == cod].mes)
        for de, fim in comum.periodos_de_meses(meses_pagos, ultimo_folha):
            linhas_m.append({"codigo": cod, "inicio": de, "fim": fim})
    for m in mand.itertuples():
        cod = int(m.parlamentar)
        meses_pagos = set(pagos[pagos.codigo == cod].ano * 100 + pagos[pagos.codigo == cod].mes)
        if not meses_pagos:
            if not ultimo_folha:
                linhas_m.append({"codigo": cod, "inicio": m.inicio, "fim": m.fim})
            continue
        fim_mandato = str(m.fim)[:10] if m.fim else ""
        for de, fim in comum.periodos_de_meses(meses_pagos, ultimo_folha, aberto=not fim_mandato or fim_mandato >= comum.hoje_iso()):
            linhas_m.append({"codigo": cod, "inicio": de, "fim": fim})
    mandatos_df = pd.DataFrame(linhas_m, columns=["codigo", "inicio", "fim"])
    titular = dict(zip(mand.parlamentar.astype(int), mand.titular))
    ver = pd.DataFrame([{"codigo": cod, "nome": comum.titulo(r.nome_parlamentar or r.nome_completo), "nome_civil": comum.titulo(r.nome_completo),
                         "partido": r.partido, "genero": r.sexo, "eleito": "eleito" if str(titular.get(cod, "True")) == "True" else "suplente",
                         "pagina": f"{BASE_SAPL}/parlamentar/{cod}"} for cod, r in info.items()]
                       + [{"codigo": cod, "nome": comum.titulo(t["nome_urna"]), "nome_civil": comum.titulo(t["nome"]), "partido": t["partido"],
                           "genero": t["genero"], "eleito": t["situacao"], "pagina": CFG["pagina"]} for cod, t in extras.items()])
    ganha = fv[fv.codigo.notna()][["ano", "mes", "codigo", "categoria", "valor"]].astype({"codigo": int})
    # gabinetes: "VER. DAVID REIS" -> o vereador cujo nome parlamentar tem essas palavras
    def achar(lot):
        chave = _chave_lotacao(lot)
        candidatos = []
        nomes = [(cod, r.nome_parlamentar, r.nome_completo) for cod, r in info.items()] + [(cod, t["nome_urna"], t["nome"]) for cod, t in extras.items()]
        for cod, parl, compl in nomes:
            nome = normalizar_nome(parl).replace(".", " ").split()
            completo = normalizar_nome(compl).split()
            if chave and all(w in nome or w in completo for w in chave):
                candidatos.append(cod)
        return candidatos[0] if len(candidatos) == 1 else None
    lot_cod = {lot: achar(lot) for lot in set(fg.lotacao) | set(fc.lotacao)}
    sem = sorted(l for l, c in lot_cod.items() if c is None)
    if sem:
        log(f"  Manaus: gabinetes sem vereador identificado: {', '.join(sem)}")
    equipe = fg.assign(codigo=fg.lotacao.map(lot_cod))
    equipe = equipe[equipe.codigo.notna()].groupby(["ano", "mes", "codigo"])[["pessoas", "custo"]].sum().reset_index().astype({"codigo": int})
    cargos = fc.assign(codigo=fc.lotacao.map(lot_cod))
    cargos = cargos[cargos.codigo.notna()].groupby(["codigo", "cargo"]).pessoas.sum().reset_index().astype({"codigo": int})
    despesas = None
    if notas is not None and len(notas):
        pela_nota = {n: codigos.get(n) or cod_folha(n) for n in set(notas.nome)}
        notas = notas.assign(codigo=notas.nome.map(pela_nota), tipo=notas.item.map(comum.tipo_curto))
        sem_n = sorted(n for n, c in pela_nota.items() if c is None)
        if sem_n:
            log(f"  Manaus: CEAP sem vereador identificado: {', '.join(sem_n)}")
        despesas = notas[notas.codigo.notna()].astype({"codigo": int})[["ano", "mes", "codigo", "tipo", "fornecedor", "cnpj_cpf", "valor"]]
    ultimo = min(ate, ultimo_folha or ate)
    ultimo_eq = f"{int(fc.mes.iloc[0]):02d}/{int(fc.ano.iloc[0])}" if len(fc) and "ano" in fc else ""
    cfg = dict(CFG, ultimo_mes=ultimo, equipe_em=ultimo_eq)
    return comum.montar(cfg, tipos, ver, mandatos_df, ganha=ganha, despesas=despesas, equipe=equipe, cargos=cargos)
