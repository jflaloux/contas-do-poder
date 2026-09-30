"""Câmara Municipal de Goiânia: vereador por vereador.

Fontes (dados abertos da Câmara, sem cadastro; o portal é da NúcleoGov e tem uma API JSON):
- Folha de pagamento nominal, mês a mês: POST https://camaragoiania.nucleogov.com.br/api, acao=servidores_cnt/listar.
  Os vereadores aparecem com a lotação "GABINETE DE <nome>" e as datas de posse e saída; os assessores, com a
  lotação do gabinete. Guardamos só o bruto de cada vereador e, dos gabinetes, pessoas, custo bruto e cargos.
  O CPF vem mascarado e não é guardado; os descontos também não.
- CEAP (Cota para o Exercício da Atividade Parlamentar), por vereador e por mês, com o valor de cada tipo de despesa:
  mesma API, acao=modulos_personalizados/listarLinhasModulo, módulo 20. (A CEAP publica o CPF do vereador: é descartado.)
- Nome parlamentar, foto e partido: https://www.goiania.go.leg.br/institucional/parlamentares
- Nome de urna, partido e gênero: TSE (eleição de 2024).
"""
import hashlib
import html as html_lib
import json
import re
import time

import pandas as pd

from ..config import CACHE, DADOS
from ..util import _sessao, cache_valido, log, normalizar_nome, verificar_prazo
from . import comum

COD = 5208707
INICIO = 202501
API = "https://camaragoiania.nucleogov.com.br/api"
SITE = "https://www.goiania.go.leg.br/institucional/parlamentares"
PASTA = DADOS / "municipios" / "goiania"
C = CACHE / "cmgoiania"
REBAIXAR = 3
MESES_NOME = {normalizar_nome(n): i for i, n in enumerate(["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto",
                                                           "Setembro", "Outubro", "Novembro", "Dezembro"], 1)}
CFG = {
    "cod": COD, "n": "Goiânia", "uf": "GO", "casa": "Câmara Municipal de Goiânia", "vagas": 37, "inicio": INICIO,
    "verba_nome": "Cota para o Exercício da Atividade Parlamentar (CEAP)",
    "verba_regra": "Reembolso de despesas do mandato, até 75% do subsídio por mês (Lei 11.308/2024).",
    "verba_notas": ["A Câmara publica a CEAP por tipo de despesa e por mês; as notas ficam em PDF, uma prestação de contas por vez.",
                    "Quando o vereador apresenta mais que o limite, a Câmara paga só o limite: aqui cada tipo de despesa é reduzido na mesma proporção, para a soma dar o que foi pago."],
    "equipe_nota": "Assessores lotados no gabinete, pela folha de pagamento da Câmara (valor bruto, com férias e 13º).",
    "credito_foto": "Câmara Municipal de Goiânia", "pagina": SITE,
    "fontes": {"folha": "https://camaragoiania.nucleogov.com.br/", "ceap": "https://camaragoiania.nucleogov.com.br/", "vereadores": SITE},
}


def _api(params, arquivo=None, dias=None):
    if arquivo is not None and cache_valido(arquivo, dias):
        return json.loads(arquivo.read_text(encoding="utf-8"))
    verificar_prazo()
    for tentativa in range(4):
        try:
            r = _sessao().post(API, data={"multi_request": "true", "params": json.dumps({"0-a": params})}, timeout=180)
            r.raise_for_status()
            d = r.json()["0-a"]
            break
        except Exception:
            if tentativa == 3:
                raise
            time.sleep(10 * (tentativa + 1))
    time.sleep(2)
    if arquivo is not None:
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return d


def _valor(t):
    t = re.sub(r"[^\d,]", "", str(t or ""))
    return float(t.replace(",", ".")) if t else 0.0


def _eh_vereador(i):
    return normalizar_nome(i.get("cargo")) in ("VEREADOR", "PRESIDENTE DA CAMARA") or normalizar_nome(i.get("tipo_admissao")) in ("VEREADOR", "PRESIDENTE DA CAMARA")


# ---------------------------------------------------------------- coleta
def lista_site():
    """Nome parlamentar, página, foto e partido de cada vereador da legislatura, pela página da Câmara."""
    verificar_prazo()
    t = _sessao().get(SITE, timeout=90).text
    linhas = []
    for bloco in re.findall(r'<p class="col-[^"]*">(.*?)</p>', t, re.S):
        a = re.search(r'href="([^"]+)"', bloco)
        img = re.search(r'<img[^>]+src="([^"]+)"', bloco)
        nome = re.search(r"<strong>(.*?)</strong>", bloco, re.S)
        if not (a and nome):
            continue
        depois = re.sub(r"<[^>]+>", " ", bloco.split("</strong>", 1)[1])
        partido = re.sub(r"\s+", " ", html_lib.unescape(depois)).strip()
        linhas.append({"pagina": a.group(1), "foto": img.group(1) if img else "", "nome": re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", nome.group(1)))).strip(),
                       "partido": partido})
    df = pd.DataFrame(linhas).drop_duplicates("pagina")
    PASTA.mkdir(parents=True, exist_ok=True)
    df.to_csv(PASTA / "site_vereadores.csv", index=False)
    log(f"  Goiânia: {len(df)} vereadores na página da Câmara")
    return df


def folha():
    ate = comum.ultimo_mes_fechado()
    recentes = comum.menos_meses(ate, REBAIXAR)
    arq_v, arq_g, arq_c = PASTA / "folha_vereadores.csv", PASTA / "folha_gabinetes.csv", PASTA / "cargos_gabinetes.csv"
    fv = pd.read_csv(arq_v) if arq_v.exists() else pd.DataFrame(columns=["ano", "mes", "nome", "cargo", "lotacao", "admissao", "exoneracao", "folha", "valor"])
    fg = pd.read_csv(arq_g) if arq_g.exists() else pd.DataFrame(columns=["ano", "mes", "lotacao", "pessoas", "custo"])
    feitos = set(fg.ano * 100 + fg.mes) if len(fg) else set()
    ultimo = None
    for a, m in comum.meses(INICIO, ate):
        am = a * 100 + m
        if am in feitos and am <= recentes:
            continue
        d = _api({"ano": a, "mes": m, "limit": "0, 6000", "acao": "servidores_cnt/listar"})
        linhas = [i for i in d.get("dados") or [] if int(i.get("ano") or 0) == a and int(i.get("mes") or 0) == m]
        if not linhas:
            continue  # mês ainda não publicado
        v_linhas, gab, pessoas, cargos = [], {}, {}, {}
        for i in linhas:
            lot = (i.get("lotacao") or "").strip()
            if _eh_vereador(i):
                v_linhas.append({"ano": a, "mes": m, "nome": i["nome"].strip(), "cargo": i.get("cargo"), "lotacao": lot, "admissao": i.get("data_admissao") or "",
                                 "exoneracao": i.get("data_exoneracao") or "", "folha": i.get("tipo_folha") or "", "valor": _valor(i.get("total_proventos"))})
            elif normalizar_nome(lot).startswith("GABINETE DE "):
                gab[lot] = gab.get(lot, 0.0) + _valor(i.get("total_proventos"))
                if normalizar_nome(i.get("tipo_folha")) == "MENSAL":
                    pessoas.setdefault(lot, set()).add(i["nome"].strip())
                    cargos[(lot, re.sub(r"\s+[IVX]+$", "", (i.get("cargo") or "").strip()))] = cargos.get((lot, re.sub(r"\s+[IVX]+$", "", (i.get("cargo") or "").strip())), 0) + 1
        fv = pd.concat([fv[(fv.ano * 100 + fv.mes) != am], pd.DataFrame(v_linhas)], ignore_index=True)
        fg = pd.concat([fg[(fg.ano * 100 + fg.mes) != am],
                        pd.DataFrame([{"ano": a, "mes": m, "lotacao": k, "pessoas": len(pessoas.get(k, ())), "custo": round(c, 2)} for k, c in gab.items()])], ignore_index=True)
        ultimo = (a, m, cargos)
        PASTA.mkdir(parents=True, exist_ok=True)
        fv.to_csv(arq_v, index=False)
        fg.to_csv(arq_g, index=False)
        log(f"  Goiânia: folha de {m:02d}/{a} ({len(linhas)} linhas, {len(v_linhas)} de vereador)")
    if ultimo:
        a, m, cargos = ultimo
        pd.DataFrame([{"ano": a, "mes": m, "lotacao": k[0], "cargo": comum.titulo(k[1]), "pessoas": n} for k, n in cargos.items()]).to_csv(arq_c, index=False)


def _valor_livre(t):
    """Valor digitado à mão: "8.138,55", "3200.00.", "3.200" -> float."""
    t = re.sub(r"[^\d.,]", "", str(t or "")).strip(".,")
    if not t:
        return 0.0
    if "," in t:
        return float(t.replace(".", "").replace(",", "."))
    if re.search(r"\.\d{1,2}$", t):
        inteiro, dec = t.rsplit(".", 1)
        return float(inteiro.replace(".", "") + "." + dec)
    return float(t.replace(".", ""))


def _tipos_ceap(texto):
    """"<P>CONSULTORIA JURÍDICA - R$ 8.138,55</P><P>COMBUSTÍVEL - R$ 3.310,84</P>" -> [(tipo, valor)]."""
    t = html_lib.unescape(re.sub(r"<[^>]+>", "\n", texto or ""))
    saida = []
    for linha in t.split("\n"):
        m = re.match(r"\s*(.+?)\s*[-–:]\s*R\$\s*([\d.,]+)[\s.]*$", linha)
        if m:
            saida.append((m.group(1).strip(), _valor_livre(m.group(2))))
    return saida


def ceap():
    d = _api({"filtros_selects": {}, "modulo": "20", "limit": "0, 5000", "acao": "modulos_personalizados/listarLinhasModulo"})
    linhas, sem_tipo = [], 0
    for r in d.get("dados") or []:
        ref = (r.get("mes_de_referencia") or "").split("/")
        mes = MESES_NOME.get(normalizar_nome(ref[0])) if ref else None
        ano = int(ref[1]) if len(ref) > 1 and ref[1].strip().isdigit() else int(r.get("ano") or 0)
        nome = ((r.get("favorecido_multidata") or [""])[0] or "").strip()
        pago = _valor_livre(r.get("valor_pago"))
        if not (mes and ano and nome and pago):
            continue
        tipos = _tipos_ceap(r.get("descrio"))
        soma = sum(v for _, v in tipos)
        if not tipos or soma <= 0:
            tipos, soma, sem_tipo = [("Sem detalhe", pago)], pago, sem_tipo + 1
        for tipo, v in tipos:
            linhas.append({"ano": ano, "mes": mes, "nome": nome, "tipo": tipo, "apresentado": v,  # sem o nº do processo: às vezes traz um CPF
                           "valor": round(v * pago / soma, 2)})
    PASTA.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(linhas).to_csv(PASTA / "ceap.csv", index=False)
    log(f"  Goiânia: CEAP, {len(linhas)} linhas (tipo × mês){f', {sem_tipo} sem detalhe' if sem_tipo else ''}")


def coletar():
    lista = lista_site()
    folha()
    ceap()
    return lista


# ---------------------------------------------------------------- montagem
def _codigo(nome_civil, tse_linha):
    if tse_linha is not None:
        return int(tse_linha["sq"])
    return int(hashlib.md5(normalizar_nome(nome_civil).encode()).hexdigest()[:10], 16)


def _gabinete(lot):
    return comum.chave_nome(re.sub(r"^GABINETE D[AEO]S?\s+", "", normalizar_nome(lot)))


def _categorias(folha_tipo, valor):
    """[(categoria, valor)]. A folha mensal paga o subsídio mais 1/3 (R$ 27.603,83 = 4/3 de R$ 20.702,87 em 2025;
    R$ 30.169,80 = 4/3 de R$ 22.627,35 em ago/2026): o subsídio vai para "salário" e o terço, para "outros pagamentos"."""
    f = normalizar_nome(folha_tipo)
    if "13" in f:
        return [("decimo_terceiro", valor)]
    if f == "MENSAL":
        return [("salario", valor * 3 / 4), ("outros_rendimentos", valor / 4)]
    return [("outros_rendimentos", valor)]  # férias (1/3), rescisão


def montar(tipos):
    if not (PASTA / "folha_vereadores.csv").exists():
        return None
    ate = comum.ultimo_mes_fechado()
    fv = pd.read_csv(PASTA / "folha_vereadores.csv").fillna("")
    fg = pd.read_csv(PASTA / "folha_gabinetes.csv") if (PASTA / "folha_gabinetes.csv").exists() else pd.DataFrame(columns=["ano", "mes", "lotacao", "pessoas", "custo"])
    fc = pd.read_csv(PASTA / "cargos_gabinetes.csv") if (PASTA / "cargos_gabinetes.csv").exists() else pd.DataFrame(columns=["ano", "mes", "lotacao", "cargo", "pessoas"])
    site = pd.read_csv(PASTA / "site_vereadores.csv").fillna("") if (PASTA / "site_vereadores.csv").exists() else pd.DataFrame(columns=["pagina", "foto", "nome", "partido"])
    ce = pd.read_csv(PASTA / "ceap.csv") if (PASTA / "ceap.csv").exists() else None
    tse = comum.candidatos_tse("GO", "Goiânia")
    tse_civil = {normalizar_nome(n): r for n, r in zip(tse.nome, tse.to_dict("records"))}

    # uma pessoa por nome civil (a folha usa o nome completo)
    pessoas = {}
    for nome, g in fv.groupby(fv.nome.map(normalizar_nome)):
        t = tse_civil.get(nome)
        mensal = g[g.folha.map(normalizar_nome).eq("MENSAL")]
        lots = [l for l in mensal.sort_values(["ano", "mes"]).lotacao if normalizar_nome(l).startswith("GABINETE DE ")]
        pessoas[nome] = {"civil": g.nome.iloc[0], "tse": t, "gab": lots[-1] if lots else "", "codigo": _codigo(nome, t)}
    # nome parlamentar, foto e partido: a página da Câmara, pelo nome do gabinete ou pelo nome de urna
    site_k = {comum.chave_nome(n): r for n, r in zip(site.nome, site.to_dict("records"))}

    def do_site(p):
        # pelo nome de urna; o nome do gabinete só vale para o titular (o suplente ocupa o gabinete de outro)
        chaves = [comum.chave_nome(p["tse"]["nome_urna"])] if p["tse"] is not None else []
        if p["gab"] and (p["tse"] is None or p["tse"]["situacao"] == "eleito"):
            chaves.append(_gabinete(p["gab"]))
        for k in chaves:
            if k in site_k:
                return site_k[k]
        for k in chaves:  # "DR. GUSTAVO" x "Dr Gustavo"; "PROFESSOR EDWARD" x "Professor Edward"
            achados = [r for kk, r in site_k.items() if set(k.split()) <= set(kk.split()) or set(kk.split()) <= set(k.split())]
            if len(achados) == 1:
                return achados[0]
        return None
    linhas_v, fotos = [], []
    for nome, p in pessoas.items():
        s = do_site(p)
        p["site"] = s
        t = p["tse"]
        nome_parl = s["nome"] if s is not None else (comum.titulo(t["nome_urna"]) if t is not None else comum.titulo(re.sub(r"^GABINETE DE\s+", "", p["gab"], flags=re.I)) or comum.titulo(p["civil"]))
        linhas_v.append({"codigo": p["codigo"], "nome": nome_parl, "nome_civil": comum.titulo(p["civil"]),
                         "partido": (s["partido"] if s is not None and len(s["partido"]) <= 15 else "") or (t["partido"] if t is not None else ""),
                         "genero": t["genero"] if t is not None else "", "eleito": (t["situacao"] if t is not None else ""),
                         "pagina": s["pagina"] if s is not None else SITE})
        if s is not None and s["foto"]:
            fotos.append((p["codigo"], s["foto"]))
    ver = pd.DataFrame(linhas_v)
    sem = [p["civil"] for p in pessoas.values() if p["tse"] is None]
    if sem:
        log(f"  Goiânia: sem correspondência no TSE: {', '.join(sem)}")
    sem = [p["civil"] for p in pessoas.values() if p["site"] is None]
    if sem:
        log(f"  Goiânia: fora da página de vereadores da Câmara (saíram ou licenciados): {', '.join(sem)}")
    comum.fotos(COD, fotos)

    cod_de = {n: p["codigo"] for n, p in pessoas.items()}
    fv = fv.assign(codigo=fv.nome.map(lambda n: cod_de.get(normalizar_nome(n))))
    ultimo_folha = int((fv.ano * 100 + fv.mes).max()) if len(fv) else None
    ganha = pd.DataFrame([{"ano": a, "mes": m, "codigo": c, "categoria": cat, "valor": round(v, 2)}
                          for a, m, c, f, valor in zip(fv.ano, fv.mes, fv.codigo, fv.folha, fv.valor) for cat, v in _categorias(f, float(valor))],
                         columns=["ano", "mes", "codigo", "categoria", "valor"])
    pagos = fv[fv.folha.map(normalizar_nome).eq("MENSAL") & (fv.valor > 0)]
    linhas_m = []
    for cod, g in pagos.groupby("codigo"):
        for de, fim in comum.periodos_de_meses(set(g.ano * 100 + g.mes), ultimo_folha):
            linhas_m.append({"codigo": int(cod), "inicio": de, "fim": fim})
    mandatos_df = pd.DataFrame(linhas_m, columns=["codigo", "inicio", "fim"])

    # gabinetes: em cada mês, o gabinete é de quem está lotado nele como vereador (o suplente herda o do titular)
    no_mes = {}  # (ano, mês, gabinete) -> {vereador: valor}; na troca, fica com quem recebeu mais no mês
    for r in pagos.itertuples():
        if normalizar_nome(r.lotacao).startswith("GABINETE DE "):
            x = no_mes.setdefault((int(r.ano), int(r.mes), _gabinete(r.lotacao)), {})
            x[int(r.codigo)] = x.get(int(r.codigo), 0) + float(r.valor)
    fixo = {}
    for p in pessoas.values():
        if p["gab"]:
            fixo.setdefault(_gabinete(p["gab"]), set()).add(p["codigo"])
    site_por_cod = {p["codigo"]: comum.chave_nome(p["site"]["nome"]) for p in pessoas.values() if p["site"] is not None}

    def dono(ano, mes, lot):
        k = _gabinete(lot)
        if (ano, mes, k) in no_mes:
            x = no_mes[(ano, mes, k)]
            return max(x, key=x.get)
        c = fixo.get(k) or {cod for cod, kk in site_por_cod.items() if kk == k}
        return next(iter(c)) if len(c) == 1 else None
    equipe = fg.assign(codigo=[dono(int(a), int(m), l) for a, m, l in zip(fg.ano, fg.mes, fg.lotacao)])
    sem_g = sorted(set(equipe[equipe.codigo.isna()].lotacao))
    if sem_g:
        log(f"  Goiânia: gabinetes sem vereador identificado: {', '.join(sem_g)}")
    equipe = equipe[equipe.codigo.notna()].groupby(["ano", "mes", "codigo"])[["pessoas", "custo"]].sum().reset_index().astype({"codigo": int})
    cargos = fc.assign(codigo=[dono(int(a), int(m), l) for a, m, l in zip(fc.ano, fc.mes, fc.lotacao)]) if len(fc) else fc.assign(codigo=None)
    cargos = cargos[cargos.codigo.notna()].groupby(["codigo", "cargo"]).pessoas.sum().reset_index().astype({"codigo": int})

    despesas = None
    if ce is not None and len(ce):
        def pelo_nome(n):
            if normalizar_nome(n) in cod_de:
                return cod_de[normalizar_nome(n)]
            achados = {p["codigo"] for p in pessoas.values() if comum.compativel(n, p["civil"])}
            return achados.pop() if len(achados) == 1 else None
        ce = ce.assign(codigo=ce.nome.map(pelo_nome), tipo=ce.tipo.map(comum.tipo_curto), fornecedor="", cnpj_cpf="")
        sem_c = sorted(set(ce[ce.codigo.isna()].nome))
        if sem_c:
            log(f"  Goiânia: na CEAP e não na folha: {', '.join(sem_c)}")
        despesas = ce[ce.codigo.notna()].astype({"codigo": int})[["ano", "mes", "codigo", "tipo", "fornecedor", "cnpj_cpf", "valor"]]
    ultimo = min(ate, ultimo_folha or ate)
    ultimo_eq = f"{int(fc.mes.iloc[0]):02d}/{int(fc.ano.iloc[0])}" if len(fc) else ""
    cfg = dict(CFG, ultimo_mes=ultimo, equipe_em=ultimo_eq, subsidio=_subsidio(fv), salario_nota=_salario_nota(fv))
    return comum.montar(cfg, tipos, ver, mandatos_df, ganha=ganha, despesas=despesas, equipe=equipe, cargos=cargos)


def _subsidio(fv):
    """Subsídio de cada mês: 3/4 do valor mensal mais comum na folha (o de quase todos os vereadores), só quando muda."""
    m = fv[fv.folha.map(normalizar_nome).eq("MENSAL") & fv.cargo.map(normalizar_nome).eq("VEREADOR")]
    saida = []
    for (a, mes), g in m.groupby(["ano", "mes"]):
        v = round(float(g.valor.round(2).mode().iloc[0]) * 3 / 4, 2)
        if not saida or abs(saida[-1][1] - v) > 0.5:
            saida.append([int(a) * 100 + int(mes), v])
    return saida


def _salario_nota(fv):
    sub = _subsidio(fv)
    ex = f" (em {sub[-1][0] % 100:02d}/{sub[-1][0] // 100}, {_br(sub[-1][1] * 4 / 3)} para um subsídio de {_br(sub[-1][1])})" if sub else ""
    return ("Valores brutos da folha de pagamento da Câmara, com férias e 13º. Todo mês, a folha paga aos vereadores de Goiânia "
            f"um terço a mais que o subsídio{ex}. A Câmara não informa o nome dessa parcela: aqui ela aparece como “outros pagamentos”. "
            "O presidente da Câmara recebe mais.")


def _br(v):
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
