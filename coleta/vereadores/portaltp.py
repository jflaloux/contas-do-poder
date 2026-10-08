"""Câmaras com o Portal da Transparência da empresa "portaltp" (<câmara>.portaltp.com.br): o robô comum.

Usado por Rio Branco (rio_branco.py) e Porto Velho (porto_velho.py). Cada cidade tem um módulo curto com o CFG (o endereço
do portal, o do SAPL da Câmara e o jeito de achar o gabinete na folha) e chama coletar(CFG) e montar(CFG, tipos).

Fontes (abrem de fora do Brasil, conferido em 08/10/2026; o robots.txt do portal pedia que robôs não usassem /api/, o que
é uma convenção e não lei: lemos com pausa, ver o README, "Robôs e robots.txt"):
- Folha mensal, nome por nome: a página "Dados Abertos > Servidores" do portal (/api/pessoal/api-servidores.aspx), com a
  exportação em JSON do mês (o formulário da própria página: ano, mês e formato). Cada servidor traz cargo, centro de
  custo, lotação e as rubricas (nome_remNN e valor_remNN): salário base, férias, 13º, outros vencimentos, alimentação... e
  o salário bruto, que é a soma delas. Lemos só as parcelas pagas: nunca o documento (CPF mascarado), os descontos, o
  abate-teto nem o líquido.
  - Vereadores: o cargo (VEREADOR ou VEREADORES). Guardamos as parcelas de cada um, por mês.
  - Equipe: os servidores lotados no gabinete de cada vereador (centro de custo ou lotação "GAB ... <nome>", conforme a
    cidade). Guardamos só quantas pessoas e o custo bruto por gabinete e mês, e os cargos do último mês: sem nomes.
- Verba (onde a Câmara paga verba indenizatória ao vereador): as liquidações do mês (/api/despesas/api-liquidacoes.aspx,
  a mesma exportação em JSON) no elemento 3.3.90.93.01 (indenizações) com o vereador como favorecido. Sem notas nem
  fornecedor (o portal não traz o histórico na exportação): só o valor, no mês da liquidação.
- Nome parlamentar, nome civil, foto e o mandato: o SAPL da Câmara (/api/, a lista de mandatos da legislatura e os dados
  de cada parlamentar; ver sapl.py). Partido, gênero e nome de urna: TSE (eleição de 2024).
Quem estava no cargo em cada mês: quem está na folha do mês com o salário base (ou as férias). Quem está em exercício hoje: quem está na
folha do último mês e tem mandato em vigor no SAPL.
"""
import json
import re

import pandas as pd

from ..config import CACHE
from ..util import TempoEsgotado, _sessao, cache_valido, dormir, gravar_csv, log, normalizar_nome, verificar_prazo
from ..assembleias import comum as acomum
from . import comum, sapl

REBAIXAR = 3  # os últimos meses da folha são baixados de novo
PAUSA = 1.5
# parcelas pagas (nome da rubrica, sem acento) -> categoria do site; o resto (bruto, descontos, abate-teto, líquido) não é lido
PARCELAS = {"SALARIO BASE": "salario", "FERIAS": "ferias", "13 SALARIO": "decimo_terceiro", "ADIANTAMENTO 13": "decimo_terceiro",
            "OUTROS VENCIMENTOS": "outros_rendimentos", "VANTAGENS PESSOAIS": "outros_rendimentos",
            "OUTRAS REMUNERACOES": "outros_rendimentos", "ALIMENTACAO": "auxilios", "INDENIZACOES": "auxilios"}
COLUNAS_VER = ["ano", "mes", "matricula", "nome", "admissao", "demissao", "lotacao", "categoria", "valor"]
COLUNAS_EQ = ["ano", "mes", "gabinete", "pessoas", "custo"]
COLUNAS_CARGOS = ["ano", "mes", "gabinete", "cargo", "pessoas"]
COLUNAS_VERBA = ["ano", "mes", "nome", "liquidacao", "valor"]


def _chave_rubrica(nome):
    return re.sub(r"[^A-Z0-9 ]", "", normalizar_nome(nome).replace("º", "").replace("°", "")).strip()


def _parcelas(x):
    """{categoria: valor} das parcelas pagas de um servidor (sem o bruto, os descontos e o líquido)."""
    saida = {}
    for i in range(1, 41):
        nome, valor = x.get(f"nome_rem{i:02d}"), x.get(f"valor_rem{i:02d}")
        if not nome or not valor:
            continue
        k = _chave_rubrica(nome)
        cat = next((c for p, c in PARCELAS.items() if k == p or k.startswith(p)), None)
        if cat:
            saida[cat] = round(saida.get(cat, 0.0) + float(valor), 2)
    return saida


def _exportar(cfg, caminho, am, arquivo, dias):
    """A exportação em JSON de uma página de dados abertos do portal (o formulário: ano, mês, formato), com cache."""
    if arquivo.exists() and cache_valido(arquivo, dias):
        return json.loads(arquivo.read_text(encoding="utf-8"))
    url = f"{cfg['portal']}{caminho}"
    s = _sessao()
    for tentativa in range(3):
        try:
            verificar_prazo()
            pagina = s.get(url, timeout=120)
            pagina.raise_for_status()
            dados = {n: v for n, v in re.findall(r'<input[^>]*name="(__\w+)"[^>]*value="([^"]*)"', pagina.text)}
            dados.update({"ctl00$containerCorpo$cbxAno": str(am // 100), "ctl00$containerCorpo$cbxMes": f"{am % 100:02d}",
                          "ctl00$containerCorpo$cbxFormato": "JSON", "ctl00$containerCorpo$btnAplicFiltro": "Exportar"})
            dormir(PAUSA)
            r = s.post(url, data=dados, timeout=300)
            r.raise_for_status()
            if "json" not in (r.headers.get("content-type") or ""):
                raise RuntimeError(f"a exportação de {caminho} ({am}) não veio em JSON")
            saida = r.json()
            break
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 2:
                raise
            dormir(10 + 10 * tentativa)
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(json.dumps(saida, ensure_ascii=False), encoding="utf-8")
    dormir(PAUSA)
    return saida


def _eh_vereador(x):
    return normalizar_nome(x.get("cargo") or "").startswith("VEREADOR")


def folha(cfg):
    """Vereadores (parcelas de cada um), equipe dos gabinetes (pessoas e custo) e cargos do último mês, mês a mês."""
    pasta, cache = cfg["pasta"], CACHE / cfg["cache"]
    ate = comum.ultimo_mes_fechado()
    recentes = comum.menos_meses(ate, REBAIXAR)
    arq_v, arq_e, arq_c = pasta / "folha_vereadores.csv", pasta / "equipe.csv", pasta / "equipe_cargos.csv"
    velha_v = pd.read_csv(arq_v, dtype={"matricula": str}) if arq_v.exists() else pd.DataFrame(columns=COLUNAS_VER)
    velha_e = pd.read_csv(arq_e) if arq_e.exists() else pd.DataFrame(columns=COLUNAS_EQ)
    feitos = set(velha_v.ano * 100 + velha_v.mes) if len(velha_v) else set()
    lv, le, cargos_ult = [], [], None
    for a, m in comum.meses(cfg["inicio"], ate):
        am = a * 100 + m
        if am in feitos and am < recentes:
            lv += velha_v[(velha_v.ano * 100 + velha_v.mes) == am].to_dict("records")
            le += velha_e[(velha_e.ano * 100 + velha_e.mes) == am].to_dict("records")
            continue
        regs = _exportar(cfg, "/api/pessoal/api-servidores.aspx", am, cache / f"servidores_{am}.json", 5 if am >= recentes else None)
        if not regs:
            if am in feitos:
                lv += velha_v[(velha_v.ano * 100 + velha_v.mes) == am].to_dict("records")
                le += velha_e[(velha_e.ano * 100 + velha_e.mes) == am].to_dict("records")
            continue
        pessoas, custo, cargos = {}, {}, {}
        for x in regs:
            if _eh_vereador(x):
                for cat, v in _parcelas(x).items():
                    lv.append({"ano": a, "mes": m, "matricula": str(x.get("matricula") or "").strip(),
                               "nome": " ".join(str(x.get("nome") or "").split()), "admissao": (x.get("data_admissao") or "")[:10],
                               "demissao": (x.get("data_demissao") or "")[:10], "lotacao": cfg["gabinete"](x) or "",
                               "categoria": cat, "valor": v})
                continue
            gab = cfg["gabinete"](x)
            if not gab:
                continue
            nome = normalizar_nome(x.get("nome") or "")
            pessoas.setdefault(gab, set()).add(nome)
            custo[gab] = custo.get(gab, 0.0) + sum(_parcelas(x).values())
            cargos.setdefault((gab, " ".join(str(x.get("cargo") or "").split()).upper()), set()).add(nome)
        le += [{"ano": a, "mes": m, "gabinete": g, "pessoas": len(q), "custo": round(custo.get(g, 0.0), 2)} for g, q in sorted(pessoas.items())]
        if pessoas:
            cargos_ult = (a, m, cargos)
    dv = pd.DataFrame(lv, columns=COLUNAS_VER)
    de = pd.DataFrame(le, columns=COLUNAS_EQ)
    if not len(dv):
        log(f"  {cfg['n']}: a folha veio vazia; fica o que estava gravado")
        return
    pasta.mkdir(parents=True, exist_ok=True)
    if gravar_csv(dv.sort_values(["ano", "mes", "nome", "categoria"]), arq_v) and len(de):
        gravar_csv(de.sort_values(["ano", "mes", "gabinete"]), arq_e)
        if cargos_ult:
            a, m, cargos = cargos_ult
            gravar_csv(pd.DataFrame([{"ano": a, "mes": m, "gabinete": k[0], "cargo": k[1], "pessoas": len(q)} for k, q in sorted(cargos.items())],
                                    columns=COLUNAS_CARGOS), arq_c)
    log(f"  {cfg['n']}: folha de {dv.nome.nunique()} vereadores e {de.gabinete.nunique()} gabinetes, até {int((dv.ano * 100 + dv.mes).max())}")


def verba(cfg):
    """As liquidações de indenização (3.3.90.93.01) a vereadores, mês a mês (só nomes que estão na folha dos vereadores)."""
    if not cfg.get("verba_liquidacoes"):
        return
    pasta, cache = cfg["pasta"], CACHE / cfg["cache"]
    arq_v = pasta / "folha_vereadores.csv"
    if not arq_v.exists():
        return
    nomes = {normalizar_nome(n) for n in pd.read_csv(arq_v).nome}
    ate = comum.ultimo_mes_fechado()
    recentes = comum.menos_meses(ate, REBAIXAR)
    arq = pasta / "verba.csv"
    velha = pd.read_csv(arq) if arq.exists() else pd.DataFrame(columns=COLUNAS_VERBA)
    feitos = set(velha.ano * 100 + velha.mes) if len(velha) else set()
    linhas = []
    for a, m in comum.meses(cfg["inicio"], ate):
        am = a * 100 + m
        if am in feitos and am < recentes:
            linhas += velha[(velha.ano * 100 + velha.mes) == am].to_dict("records")
            continue
        regs = _exportar(cfg, "/api/despesas/api-liquidacoes.aspx", am, cache / f"liquidacoes_{am}.json", 5 if am >= recentes else None)
        for x in regs or []:
            if not str(x.get("elemento_despesa") or "").startswith("33909301"):
                continue
            nome = " ".join(str(x.get("nome_favorecido") or "").split())
            if normalizar_nome(nome) not in nomes:
                continue
            v = float(x.get("valor") or 0)
            if "ANULA" in normalizar_nome(x.get("especie") or "") and v > 0:
                v = -v
            linhas.append({"ano": a, "mes": m, "nome": nome, "liquidacao": str(x.get("liquidacao") or ""), "valor": round(v, 2)})
    df = pd.DataFrame(linhas, columns=COLUNAS_VERBA)
    if not len(df):
        log(f"  {cfg['n']}: nenhuma liquidação de verba a vereador; fica o que estava gravado")
        return
    gravar_csv(df.sort_values(["ano", "mes", "nome", "liquidacao"]), arq)
    log(f"  {cfg['n']}: verba de {df.nome.nunique()} vereadores, até {int((df.ano * 100 + df.mes).max())}")


def lista(cfg):
    """Mandatos da legislatura e os dados de cada parlamentar no SAPL da Câmara."""
    pasta = cfg["pasta"]
    leg = sapl.legislatura_atual(cfg["sapl"], pausa=PAUSA)
    m = sapl.mandatos(cfg["sapl"], leg["id"], pausa=PAUSA)
    if not 0.8 * cfg["vagas"] <= m.titular.sum() <= 2 * cfg["vagas"]:
        log(f"  {cfg['n']}: o SAPL veio com {m.titular.sum()} mandatos de titular; fica a lista gravada")
        return
    pasta.mkdir(parents=True, exist_ok=True)
    gravar_csv(m, pasta / "sapl_mandatos.csv")
    # os dados de todos os parlamentares numa lista só (o SAPL pede 60 s entre os pedidos: um pedido por parlamentar
    # levaria quase uma hora); o partido vem do TSE
    ids = {int(x) for x in m.parlamentar}
    todos = sapl._todas(cfg["sapl"], "parlamentares/parlamentar/", {}, PAUSA)
    linhas = [{"id": str(x["id"]), "nome_parlamentar": (x.get("nome_parlamentar") or "").strip(),
               "nome_completo": (x.get("nome_completo") or "").strip(), "sexo": x.get("sexo") or "",
               "fotografia": x.get("fotografia") or ""} for x in todos if int(x["id"]) in ids]
    if linhas:
        gravar_csv(pd.DataFrame(linhas), pasta / "sapl_parlamentares.csv")
    log(f"  {cfg['n']}: {len(m)} mandatos no SAPL, {len(linhas)} parlamentares")


def coletar(cfg):
    folha(cfg)
    verba(cfg)
    try:
        lista(cfg)
    except TempoEsgotado:
        raise
    except Exception as e:  # noqa: BLE001 — sem o SAPL, o "no cargo" sai só da folha
        log(f"  {cfg['n']}: o SAPL não abriu ({type(e).__name__}); fica a lista gravada")
    # fotos do SAPL só aqui na coleta (o SAPL pede 60 s entre os pedidos): só as que faltam, no máximo FOTOS_POR_VEZ
    try:
        montar(cfg, comum.Tipos(), baixar_fotos=True)
    except TempoEsgotado:
        raise
    except Exception as e:  # noqa: BLE001 — foto é complemento
        log(f"  {cfg['n']}: fotos do SAPL não baixadas ({type(e).__name__})")


# ---------------------------------------------------------------- montagem
FOTOS_POR_VEZ = 30


def montar(cfg, tipos, baixar_fotos=False):
    pasta = cfg["pasta"]
    arq = pasta / "folha_vereadores.csv"
    if not arq.exists():
        return None
    fol = pd.read_csv(arq, dtype={"matricula": str}).fillna({"matricula": "", "admissao": "", "demissao": "", "lotacao": ""})
    if not len(fol):
        return None
    eq = pd.read_csv(pasta / "equipe.csv") if (pasta / "equipe.csv").exists() else pd.DataFrame(columns=COLUNAS_EQ)
    fc = pd.read_csv(pasta / "equipe_cargos.csv") if (pasta / "equipe_cargos.csv").exists() else pd.DataFrame(columns=COLUNAS_CARGOS)
    vb = pd.read_csv(pasta / "verba.csv") if (pasta / "verba.csv").exists() else pd.DataFrame(columns=COLUNAS_VERBA)
    mand = pd.read_csv(pasta / "sapl_mandatos.csv").fillna("") if (pasta / "sapl_mandatos.csv").exists() else pd.DataFrame()
    parl = pd.read_csv(pasta / "sapl_parlamentares.csv", dtype=str).fillna("") if (pasta / "sapl_parlamentares.csv").exists() else pd.DataFrame()
    tse = comum.candidatos_tse(cfg["uf"], cfg["n"])
    por_civil = [(n, i) for i, n in enumerate(tse.nome)] if len(tse) else []

    # quem é quem: a matrícula liga os meses; o nome da folha (civil) casa com o TSE; o código é o SQ da candidatura
    fol["chave"] = [m if m else normalizar_nome(n) for m, n in zip(fol.matricula, fol.nome)]
    nome_da = {k: g.sort_values(["ano", "mes"]).nome.iloc[-1] for k, g in fol.groupby("chave")}
    codigos, info = {}, {}
    for k, nome in sorted(nome_da.items()):
        i = comum.achar_parecido(nome, por_civil, 0.9) if por_civil else None
        t = tse.iloc[i].to_dict() if i is not None else None
        cod = int(t["sq"]) if t else acomum.codigo_de(nome, None)
        codigos[k] = cod
        info.setdefault(cod, {"t": t, "nome": nome})
    fol["codigo"] = fol.chave.map(codigos)
    sem_tse = sorted({v["nome"] for v in info.values() if v["t"] is None})
    if sem_tse:
        log(f"  {cfg['n']}: sem candidatura no TSE de 2024: {', '.join(sem_tse)}")

    # SAPL: o parlamentar (nome completo ou parlamentar) -> código; dele vêm o nome parlamentar, a foto e o mandato
    sapl_cod, sapl_info = {}, {}
    if len(parl):
        opcoes = [(v["nome"], c) for c, v in info.items()] + [(v["t"]["nome"], c) for c, v in info.items() if v["t"]] + \
                 [(v["t"]["nome_urna"], c) for c, v in info.items() if v["t"]]
        for r in parl.itertuples():
            nome_p = re.sub(r"^(Vereador|Vereadora)\s+", "", r.nome_parlamentar, flags=re.I)
            c = comum.achar_parecido(r.nome_completo, opcoes, 0.88) if r.nome_completo else None
            c = c or comum.achar_parecido(nome_p, opcoes, 0.88)
            if c is not None:
                sapl_cod[str(r.id)] = c
                sapl_info[c] = {"nome": nome_p, "foto": r.fotografia, "id": r.id}
    hoje = comum.hoje_iso()
    com_mandato = {sapl_cod.get(str(int(p))) for p, i, f in zip(mand.get("parlamentar", []), mand.get("inicio", []), mand.get("fim", []))
                   if str(i) <= hoje and (not f or str(f) >= hoje)} - {None} if len(mand) else None

    # no cargo no mês: salário base ou férias (em Porto Velho, jan/2026 veio só com as férias, o mês de descanso de todos)
    base = fol[fol.categoria.isin(["salario", "ferias"])]
    base = base[base.valor >= 0.5]
    ultimo = int((base.ano * 100 + base.mes).max())
    ate = min(comum.ultimo_mes_fechado(), ultimo)
    ver, mandatos, fotos = [], [], []
    for c in sorted(set(fol.codigo)):
        v, sp = info[c], sapl_info.get(c)
        t = v["t"]
        nome = (sp["nome"] if sp and sp["nome"] else None) or (comum.titulo(t["nome_urna"]) if t else comum.titulo(v["nome"]))
        if sp and sp["foto"]:
            fotos.append((c, sp["foto"]))
        ver.append({"codigo": c, "nome": nome, "nome_civil": comum.titulo(t["nome"]) if t else comum.titulo(v["nome"]),
                    "partido": t["partido"] if t else "", "genero": t["genero"] if t else "", "eleito": t["situacao"] if t else "",
                    "pagina": f"{cfg['sapl']}/parlamentar/{sp['id']}" if sp else cfg["pagina"]})
        g = base[base.codigo == c]
        for i, f in comum.periodos_de_meses(g.ano * 100 + g.mes, ultimo):
            if not f and com_mandato is not None and c not in com_mandato:  # está na folha do último mês, mas sem mandato hoje
                a, m = divmod(ultimo, 100)
                f = f"{a}-{m:02d}-{pd.Period(f'{a}-{m:02d}').days_in_month:02d}"
            mandatos.append({"codigo": c, "inicio": i, "fim": f})
    _acertar_datas(mandatos, fol)
    if baixar_fotos:
        faltam = [(c, u) for c, u in fotos if not (comum.FOTOS / f"ver-{cfg['cod']}-{c}.webp").exists()]
        comum.fotos(cfg["cod"], faltam[:FOTOS_POR_VEZ])
        return None
    ganha = fol.groupby(["ano", "mes", "codigo", "categoria"]).valor.sum().reset_index()

    # equipe: o gabinete (o nome na folha) casa com o vereador; só os meses em que ele estava no cargo
    opcoes_g = [(v["nome"], c) for c, v in info.items()] + [(v["t"]["nome_urna"], c) for c, v in info.items() if v["t"]] + \
               [(s["nome"], c) for c, s in sapl_info.items()] + [(l, c) for l, c in zip(fol.lotacao, fol.codigo) if l]
    gab_cod = {g: _achar_gabinete(g, opcoes_g) for g in sorted(set(eq.gabinete) | set(fc.gabinete))}
    sem_g = sorted(g for g, c in gab_cod.items() if c is None)
    if sem_g:
        log(f"  {cfg['n']}: gabinetes sem vereador identificado (não contados): {', '.join(sem_g)}")
    periodos = {}
    for m in mandatos:
        from datetime import date
        periodos.setdefault(m["codigo"], []).append((date.fromisoformat(m["inicio"]), date.fromisoformat(m["fim"]) if m["fim"] else None))
    eq = eq.assign(codigo=eq.gabinete.map(gab_cod))
    eq = eq[eq.codigo.notna()]
    eq = eq[[comum.dias_no_mes(periodos.get(int(c), []), int(a), int(m)) > 0 for a, m, c in zip(eq.ano, eq.mes, eq.codigo)]]
    equipe = eq.groupby(["ano", "mes", "codigo"])[["pessoas", "custo"]].sum().reset_index().astype({"codigo": int})
    cargos = fc.assign(codigo=fc.gabinete.map(gab_cod))
    cargos = cargos[cargos.codigo.notna()].groupby(["codigo", "cargo"]).pessoas.sum().reset_index().astype({"codigo": int})
    equipe_em = f"{int(fc.mes.iloc[0]):02d}/{int(fc.ano.iloc[0])}" if len(fc) else ""

    desp = None
    verba_ate = None
    if len(vb):
        nome_cod = {normalizar_nome(n): c for n, c in zip(fol.nome, fol.codigo)}
        vb = vb.assign(codigo=vb.nome.map(lambda n: nome_cod.get(normalizar_nome(n))))
        vb = vb[vb.codigo.notna()]
        desp = pd.DataFrame({"ano": vb.ano, "mes": vb.mes, "codigo": vb.codigo.astype(int), "tipo": cfg.get("verba_tipo", "Verba indenizatória"),
                             "fornecedor": "", "cnpj_cpf": "", "valor": vb.valor})
        verba_ate = int((vb.ano * 100 + vb.mes).max())
    c = dict(cfg["site"], ultimo_mes=ate, subsidio_folha=True, equipe_em=equipe_em,
             **({"verba_ate": verba_ate} if verba_ate and verba_ate < ate else {}))
    return comum.montar(c, tipos, pd.DataFrame(ver), pd.DataFrame(mandatos), ganha=ganha, despesas=desp, equipe=equipe, cargos=cargos)


def _achar_gabinete(gab, opcoes):
    """"007072-GAB. VEREADOR ZE LOPES", "GAB. DR. BRENO MENDES", "GAB VER. MACÁRIO" -> código do vereador (ou None)."""
    if "PRESIDEN" in normalizar_nome(gab):
        return None
    if any(normalizar_nome(gab) == normalizar_nome(n) for n, _ in opcoes):  # o vereador está lotado nesse mesmo nome
        return next(c for n, c in opcoes if normalizar_nome(gab) == normalizar_nome(n))
    nome = re.sub(r"^\d+-", "", normalizar_nome(gab))
    nome = re.sub(r"^GAB(INETE)?\.?\s*(VEREADORA?|VER)?\s*(\(A\))?\.?\s*-?\s*", "", nome).strip()
    return comum.achar_parecido(nome, [(n, c) for n, c in opcoes if not normalizar_nome(n).startswith("GAB")], 0.86)


def _acertar_datas(mandatos, fol):
    """Começo no meio do mês: a data de admissão da folha; saída no meio do mês: a data de demissão."""
    from calendar import monthrange
    adm = {c: pd.to_datetime(g.admissao, errors="coerce").max() for c, g in fol.groupby("codigo")}
    dem = {c: pd.to_datetime(g.demissao, errors="coerce").max() for c, g in fol.groupby("codigo")}
    for p in mandatos:
        d = adm.get(p["codigo"])
        if d is not None and not pd.isna(d) and d.strftime("%Y-%m") == p["inicio"][:7] and d.day > 1:
            p["inicio"] = d.strftime("%Y-%m-%d")
        s = dem.get(p["codigo"])
        if p["fim"] and s is not None and not pd.isna(s) and s.strftime("%Y-%m") == p["fim"][:7]:
            p["fim"] = s.strftime("%Y-%m-%d")
