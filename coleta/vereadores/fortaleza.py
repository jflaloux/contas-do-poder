"""Câmara Municipal de Fortaleza: vereador por vereador.

Fontes (dados abertos da Câmara, sem cadastro):
- Mandatos (titulares e suplentes, com datas): SAPL, https://sapl.fortaleza.ce.leg.br/api/ — o robots.txt pede
  60 s entre pedidos, então só pedimos a lista de mandatos (2 pedidos por semana).
- Folha de pagamento: https://api.cmfor.ce.gov.br/transparencia/transparencia/servidores?ano=&mes= (quem recebeu
  como vereador em cada mês) e o detalhe de um vereador por mês (o valor do subsídio naquele mês).
- SDP (Serviço de Desempenho Parlamentar), a verba de cada vereador, nota por nota, com credor e CNPJ:
  .../transparencia/sdp?ano=&mes= (lista) e .../sdp/<ano>/<mes>/<nome> (itens)
- Nome completo, partido e gênero: TSE (eleição de 2024).
Os descontos da folha (empréstimos, impostos) não são lidos nem guardados; o CPF vem mascarado e também não.
"""
import hashlib
import json
import time
from urllib.parse import quote

import pandas as pd

from ..config import CACHE, DADOS
from ..util import TempoEsgotado, _sessao, cache_valido, gravar_csv, log, normalizar_nome, verificar_prazo
from . import comum, sapl

COD = 2304400
INICIO = 202501
BASE_SAPL = "https://sapl.fortaleza.ce.leg.br"
API = "https://api.cmfor.ce.gov.br/transparencia/transparencia"
PASTA = DADOS / "municipios" / "fortaleza"
C = CACHE / "cmfor"
REBAIXAR = 3
CFG = {
    "cod": COD, "n": "Fortaleza", "uf": "CE", "casa": "Câmara Municipal de Fortaleza", "vagas": 43, "inicio": INICIO,
    "verba_nome": "Serviço de Desempenho Parlamentar (SDP)",
    "verba_regra": "Pago a fornecedores com nota fiscal, dentro do limite do mês. Inclui vale-alimentação, vale-refeição e combustível.",
    "salario_nota": "Subsídio pela folha de pagamento da Câmara (o valor de cada mês); o 13º e as férias não entram.",
    "credito_foto": "Câmara Municipal de Fortaleza", "pagina": "https://www.cmfor.ce.gov.br/vereadores/",
    "fontes": {"mandatos": f"{BASE_SAPL}/api/parlamentares/mandato/", "sdp": "https://transparencia.cmfor.ce.gov.br/", "folha": "https://transparencia.cmfor.ce.gov.br/"},
}


def _get(caminho, arquivo=None, dias=None, params=None):
    if arquivo is not None and cache_valido(arquivo, dias):
        return json.loads(arquivo.read_text(encoding="utf-8"))
    verificar_prazo()
    for tentativa in range(4):
        try:
            r = _sessao().get(f"{API}/{caminho}", params=params, timeout=120)
            r.raise_for_status()
            d = r.json()
            break
        except Exception:
            if tentativa == 3:
                raise
            time.sleep(15 * (tentativa + 1))  # a API derruba a conexão se os pedidos vêm em sequência
    time.sleep(1.5)
    if arquivo is not None:
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return d


def folha():
    """Quem recebeu como vereador em cada mês (lista) e o subsídio do mês (detalhe de um deles)."""
    ate = comum.ultimo_mes_fechado()
    recentes = comum.menos_meses(ate, REBAIXAR)
    arq_v, arq_s = PASTA / "folha_vereadores.csv", PASTA / "subsidio_mes.csv"
    fv = pd.read_csv(arq_v) if arq_v.exists() else pd.DataFrame(columns=["ano", "mes", "nome", "admissao", "exoneracao"])
    fs = pd.read_csv(arq_s) if arq_s.exists() else pd.DataFrame(columns=["ano", "mes", "valor"])
    feitos = set(fs.ano * 100 + fs.mes) if len(fs) else set()
    for a, m in comum.meses(INICIO, ate):
        am = a * 100 + m
        if am in feitos and am <= recentes:
            continue
        linhas, pagina = [], 1
        while True:
            d = _get("servidores", params={"ano": a, "mes": m, "pageSize": 200, "page": pagina})
            linhas += d.get("data") or []
            if pagina >= (d.get("pagination") or {}).get("pageCount", 1):
                break
            pagina += 1
        ver = [x for x in linhas if normalizar_nome(x.get("categoria")) == "VEREADORES"]
        if not ver:
            continue  # mês ainda não publicado
        # o subsídio do mês: detalhe de quem estava o mês inteiro (admitido antes do mês e sem exoneração)
        cheio = [x for x in ver if not x.get("data_exoneracao") and (x.get("data_admissao") or "")[:7] < f"{a}-{m:02d}"] or ver
        valor = 0.0
        for x in cheio[:3]:
            chave = hashlib.md5(f"{x['cpf']}{x['nome']}".encode()).hexdigest()
            det = _get(f"servidores/{a}/{m}/{chave}")
            if isinstance(det, dict):
                valor = sum(float(p.get("valor") or 0) for p in det.get("proventos", []) if "SUBSID" in normalizar_nome(p.get("evento")))
                if valor:
                    break
        fv = pd.concat([fv[(fv.ano * 100 + fv.mes) != am], pd.DataFrame([{"ano": a, "mes": m, "nome": x["nome"].strip(), "admissao": (x.get("data_admissao") or "")[:10],
                                                                         "exoneracao": (x.get("data_exoneracao") or "")[:10]} for x in ver])], ignore_index=True)
        fs = pd.concat([fs[(fs.ano * 100 + fs.mes) != am], pd.DataFrame([{"ano": a, "mes": m, "valor": round(valor, 2)}])], ignore_index=True)
        PASTA.mkdir(parents=True, exist_ok=True)
        if not (gravar_csv(fv, arq_v) and gravar_csv(fs.sort_values(["ano", "mes"]), arq_s)):
            break  # recusado por perda de cobertura (util.gravar_com): fica o que estava
        log(f"  Fortaleza: folha de {m:02d}/{a} ({len(ver)} vereadores, subsídio R$ {valor:,.2f})")


def sdp():
    """Itens do SDP de cada vereador em cada mês (os meses antigos ficam no cache)."""
    ate = comum.ultimo_mes_fechado()
    recentes = comum.menos_meses(ate, REBAIXAR)
    arq = PASTA / "sdp_itens.csv"
    velhos = pd.read_csv(arq, dtype={"cnpj_cpf": str}) if arq.exists() else pd.DataFrame(columns=["ano", "mes"])
    feitos = set(velhos.ano * 100 + velhos.mes) if len(velhos) else set()
    itens = []
    for a, m in comum.meses(INICIO, ate):
        am = a * 100 + m
        do_mes = velhos[(velhos.ano * 100 + velhos.mes) == am] if len(velhos) else velhos
        # mês antigo já gravado em dados/municipios/ e sem o cache (no GitHub, por exemplo): não baixa de novo.
        # (30 vereadores ou mais: a lista completa, e não só a primeira página)
        if am in feitos and am <= recentes and not (C / f"sdp_{am}_p1.json").exists() and do_mes.nome.nunique() >= 30:
            itens += do_mes.to_dict("records")
            continue
        dias = 5 if am > recentes else None
        lista, pagina = [], 1
        while True:  # a lista vem em páginas
            d = _get("sdp", C / f"sdp_{am}_p{pagina}.json", dias, params={"ano": a, "mes": m, "page": pagina})  # pageSize dá erro na API: 20 por página
            lista += d.get("data") or []
            if pagina >= int((d.get("pagination") or {}).get("pageCount") or 1):
                break
            pagina += 1
        for v in lista:
            nome = v["nome"].strip()
            det = _get(f"sdp/{a}/{m}/{quote(nome)}", C / f"sdp_{am}_{normalizar_nome(nome).replace(' ', '_')}.json", dias)
            for i in (det.get("data") or []) if isinstance(det, dict) else []:
                itens.append({"ano": a, "mes": m, "nome": nome, "item": (i.get("especificacao") or "").strip(), "fornecedor": (i.get("credor") or "").strip(),
                              "cnpj_cpf": comum.mascarar(i.get("cnpj")), "valor": float(i.get("valor_total") or 0), "saldo": i.get("saldo")})
    PASTA.mkdir(parents=True, exist_ok=True)
    gravar_csv(pd.DataFrame(itens), arq)
    log(f"  Fortaleza: {len(itens)} itens do SDP")


def fotos_sapl(mand, maximo=None):
    """Fotos do SAPL, só as que faltam: 2 pedidos por pessoa, com 60 s entre eles (robots.txt). Quem está no cargo primeiro."""
    ordem = mand.sort_values("fim", ascending=False).parlamentar.drop_duplicates().tolist()
    faltam = [int(i) for i in ordem if not (comum.FOTOS / f"ver-{COD}-{int(i)}.webp").exists()]
    for i in faltam[:maximo]:
        try:
            p = sapl._get(BASE_SAPL, f"parlamentares/parlamentar/{i}/", None, 60)
            if p.get("fotografia"):
                comum.fotos(COD, [(i, p["fotografia"])])
                time.sleep(60)
        except TempoEsgotado:
            raise
        except Exception as e:  # noqa: BLE001 — sem foto, o site mostra as iniciais
            log(f"  Fortaleza: foto de {i} ({e})")


def coletar():
    leg = sapl.legislatura_atual(BASE_SAPL, pausa=60)
    mand = sapl.mandatos(BASE_SAPL, leg["id"], pausa=60)
    PASTA.mkdir(parents=True, exist_ok=True)
    gravar_csv(mand, PASTA / "mandatos.csv")
    folha()
    sdp()
    fotos_sapl(mand, maximo=6)  # no máximo 6 por semana: o SAPL pede 60 s entre pedidos


def montar(tipos):
    if not (PASTA / "mandatos.csv").exists():
        return None
    ate = comum.ultimo_mes_fechado()
    mand = pd.read_csv(PASTA / "mandatos.csv").fillna("")
    fv = pd.read_csv(PASTA / "folha_vereadores.csv").fillna("") if (PASTA / "folha_vereadores.csv").exists() else pd.DataFrame(columns=["ano", "mes", "nome"])
    fs = pd.read_csv(PASTA / "subsidio_mes.csv") if (PASTA / "subsidio_mes.csv").exists() else pd.DataFrame(columns=["ano", "mes", "valor"])
    itens = pd.read_csv(PASTA / "sdp_itens.csv", dtype={"cnpj_cpf": str}).fillna({"cnpj_cpf": "", "fornecedor": "", "item": ""}) if (PASTA / "sdp_itens.csv").exists() else None
    tse = comum.candidatos_tse("CE", "Fortaleza")
    # cada parlamentar do SAPL, com o TSE (nome completo, partido, gênero)
    linhas_v = []
    urnas = [(u, i) for i, u in enumerate(tse.nome_urna)] if len(tse) else []
    for pid, g in mand.groupby("parlamentar"):
        nome = g.nome.iloc[0]
        t = comum.achar_no_tse(nome, tse)
        if t is None and urnas:  # "PP Cell" x "PPCELL"
            i = comum.achar_parecido(nome, urnas, 0.9)
            t = tse.iloc[i] if i is not None else None
        linhas_v.append({"codigo": int(pid), "nome": comum.titulo(nome), "nome_civil": comum.titulo(t["nome"]) if t is not None else "",
                         "partido": t["partido"] if t is not None else "", "genero": t["genero"] if t is not None else "",
                         "eleito": "eleito" if g.titular.astype(str).eq("True").any() else "suplente", "pagina": f"{BASE_SAPL}/parlamentar/{int(pid)}",
                         "_urna": comum.chave_nome(nome), "_civil": normalizar_nome(t["nome"]) if t is not None else ""})
    ver = pd.DataFrame(linhas_v)
    sem = ver[ver.nome_civil == ""].nome.tolist()
    if sem:
        log(f"  Fortaleza: sem correspondência no TSE: {', '.join(sem)}")
    por_civil = {c: cod for c, cod in zip(ver._civil, ver.codigo) if c}
    por_urna = {u: cod for u, cod in zip(ver._urna, ver.codigo)}
    # no cargo: os meses em que recebeu como vereador (folha); sem folha, as datas do SAPL
    # nome da folha -> parlamentar: nome completo do TSE; senão, o nome mais parecido (civil ou parlamentar);
    # senão, a mesma data de posse no SAPL e na folha
    opcoes = [(c, cod) for c, cod in zip(ver._civil, ver.codigo) if c] + [(n, cod) for n, cod in zip(ver.nome, ver.codigo)]

    def da_folha(n):
        return por_civil.get(normalizar_nome(n)) or comum.achar_parecido(n, opcoes, 0.9)
    nomes_folha = {n: da_folha(n) for n in set(fv.nome)}
    usados = {c for c in nomes_folha.values() if c}
    posse_folha = fv.groupby("nome").admissao.min().to_dict() if "admissao" in fv else {}
    posse_sapl = mand.groupby("parlamentar").inicio.min().astype(str).str[:10].to_dict()
    livres = {cod: d for cod, d in posse_sapl.items() if cod not in usados}
    for n, c in list(nomes_folha.items()):
        if c is None and posse_folha.get(n):
            mesmos = [cod for cod, d in livres.items() if d == str(posse_folha[n])[:10]]
            sem_par = [x for x, cc in nomes_folha.items() if cc is None and str(posse_folha.get(x, ""))[:10] == str(posse_folha[n])[:10]]
            if len(mesmos) == 1 and len(sem_par) == 1:
                nomes_folha[n] = mesmos[0]
                livres.pop(mesmos[0])
    # ainda sem par: uma palavra do nome em comum ("Juninho Aquino" x "JULIO ROCHA AQUINO JUNIOR"), só se for o único par possível
    livres_nome = {cod: set(comum.chave_nome(n).split()) for n, cod in zip(ver.nome, ver.codigo) if cod not in set(nomes_folha.values())}
    sem_par = [n for n, c in nomes_folha.items() if c is None]
    for n in sem_par:
        palavras = {w for w in comum.chave_nome(n).split() if len(w) >= 4}
        cands = [cod for cod, ws in livres_nome.items() if palavras & {w for w in ws if len(w) >= 4}]
        outros = [x for x in sem_par if x != n and cands and {w for w in comum.chave_nome(x).split() if len(w) >= 4} & livres_nome[cands[0]]]
        if len(cands) == 1 and not outros:
            nomes_folha[n] = cands[0]
            livres_nome.pop(cands[0])
    fv["codigo"] = fv.nome.map(nomes_folha)
    civil_folha = {c: comum.titulo(n) for n, c in nomes_folha.items() if c}
    ver["nome_civil"] = [nc or civil_folha.get(cod, "") for nc, cod in zip(ver.nome_civil, ver.codigo)]
    ultimo_folha = int((fs.ano * 100 + fs.mes).max()) if len(fs) else None
    linhas_m = []
    for cod in ver.codigo:
        meses_pagos = set(fv[fv.codigo == cod].ano * 100 + fv[fv.codigo == cod].mes)
        if meses_pagos:
            fim_sapl = mand[mand.parlamentar == cod].fim.astype(str).max()
            periodos = comum.periodos_de_meses(meses_pagos, ultimo_folha, aberto=not fim_sapl or fim_sapl >= comum.hoje_iso())
            # saiu no último mês da folha: a data de exoneração fecha o período
            ult = fv[fv.codigo == cod].sort_values(["ano", "mes"]).iloc[-1]
            if periodos and not periodos[-1][1] and str(ult.exoneracao or "")[:10] >= "2025":
                periodos[-1] = (periodos[-1][0], str(ult.exoneracao)[:10])
            for de, fim in periodos:
                linhas_m.append({"codigo": cod, "inicio": de, "fim": fim})
        elif not ultimo_folha:
            for m in mand[mand.parlamentar == cod].itertuples():
                linhas_m.append({"codigo": cod, "inicio": m.inicio, "fim": m.fim})
    nao_achados = sorted(set(fv[fv.codigo.isna()].nome))
    if nao_achados:
        log(f"  Fortaleza: na folha e não no SAPL/TSE: {', '.join(nao_achados)}")
    mandatos_df = pd.DataFrame(linhas_m, columns=["codigo", "inicio", "fim"])
    # subsídio de cada mês (tabela de valores que mudam)
    subsidio, anterior = [], None
    for r in fs.sort_values(["ano", "mes"]).itertuples():
        if r.valor and r.valor != anterior:
            subsidio.append([int(r.ano) * 100 + int(r.mes), float(r.valor)])
            anterior = r.valor
    despesas = None
    verba_mes = {}
    if itens is not None and len(itens):
        pelo_sdp = {n: por_urna.get(comum.chave_nome(n)) or comum.achar_parecido(n, list(zip(ver.nome, ver.codigo))) for n in set(itens.nome)}
        itens = itens.assign(codigo=itens.nome.map(pelo_sdp), tipo=itens.item.map(comum.tipo_curto))
        sem_d = sorted(set(itens[itens.codigo.isna()].nome))
        if sem_d:
            log(f"  Fortaleza: SDP sem vereador identificado: {', '.join(sem_d)}")
        despesas = itens[itens.codigo.notna()].astype({"codigo": int})[["ano", "mes", "codigo", "tipo", "fornecedor", "cnpj_cpf", "valor"]]
    cfg = dict(CFG, ultimo_mes=min(ate, ultimo_folha or ate), subsidio=subsidio, verba_mes=verba_mes)
    return comum.montar(cfg, tipos, ver.drop(columns=["_urna", "_civil"]), mandatos_df, despesas=despesas)
