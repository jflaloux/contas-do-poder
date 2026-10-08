"""Assembleia Legislativa do Rio de Janeiro (Alerj): deputado estadual por deputado estadual.

Fontes:
- DOCIGP (Descentralização Orçamentária de Custeio Individualizado para Gabinete Parlamentar), o portal de transparência
  da verba indenizatória: https://docigp.alerj.rj.gov.br/transparencia. O robô lê o que a página usa (/api/v1/...): os
  deputados da legislatura, o orçamento mensal de cada um (valor do mês) e os lançamentos publicados de cada mês (data,
  centro de custo, fornecedor, CNPJ/CPF, documento, valor). O robots.txt do DOCIGP tem "Disallow: /": a leitura é uma das
  exceções do projeto (verba de agente público, que a LAI manda publicar), ver coleta/util.py e o README.
- Subsídio: Lei 11.074/2025 (R$ 34.774,64), pela tabela de remuneração da Alerj.
- Quem está no cargo hoje e o partido de hoje: a página "Quem são" do site da Alerj (www.alerj.rj.gov.br/Deputados/QuemSao,
  sem robots.txt); o partido do DOCIGP está desatualizado (ainda tem DEM, PSL, PHS): para quem saiu, vale o da eleição de 2022.
- Nome completo, gênero e eleito/suplente: TSE (eleição de 2022).
Desde quando: os meses com orçamento no DOCIGP.
"""
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from ..config import DADOS
from ..prefeituras.comum import feminino
from ..util import TempoEsgotado, _sessao, gravar_csv, log, normalizar_nome, verificar_prazo
from ..vereadores import comum as vc
from . import comum

UF = "RJ"
COD = comum.CODIGOS_UF[UF]
INICIO = 202502
API = "https://docigp.alerj.rj.gov.br/api/v1"
PASTA = DADOS / "assembleias" / "rj"
QUEM_SAO = "https://www.alerj.rj.gov.br/Deputados/QuemSao"
CFG = {
    "cod": COD, "n": "Rio de Janeiro", "uf": UF, "casa": "Assembleia Legislativa do Rio de Janeiro", "vagas": 70, "inicio": INICIO,
    "id_prefixo": "est", "k": "e", "cargo": ("Deputada estadual", "Deputado estadual"),
    "subsidio": [[202502, 34774.64]],
    "salario_nota": ("Subsídio fixado em lei (Lei 11.074/2025), proporcional aos meses no cargo. O período começa em fev/2025. "
                     "O 13º e outros pagamentos não aparecem aqui."),
    "verba_nome": "Verba indenizatória (DOCIGP)",
    "verba_regra": "Valor mensal por gabinete para custeio do mandato (Ato N/MD/641/2019), com os lançamentos publicados um a um.",
    "verba_notas": ["Entram os lançamentos de débito publicados no DOCIGP (o saldo que passa de um mês para o outro, os créditos e a devolução do saldo não gasto não).",
                    "O DOCIGP publica o mês de cada gabinete depois da análise da prestação de contas: o site vai até o último mês em que pelo menos 80% dos gabinetes já foram publicados."],
    "pagina": "https://www.alerj.rj.gov.br/Deputados",
    "notas": ["Quem está no cargo hoje: a lista de deputados em exercício do site da Alerj. Desde quando: os meses com orçamento no DOCIGP.",
              "Partido: o do site da Alerj; para quem saiu, o da eleição de 2022 (TSE)."],
    "fontes": {"verba": "https://docigp.alerj.rj.gov.br/transparencia", "subsidio": "https://transparencia.alerj.rj.gov.br/section/report/62"},
}
Q = lambda **kw: {"query": json.dumps({"filter": kw.get("filtro", {"text": None}), "pagination": {"per_page": 100, "current_page": kw.get("pagina", 1)}, "order": {}})}


def _json(caminho, params=None):
    verificar_prazo()
    for tentativa in range(3):
        try:
            r = _sessao().get(f"{API}/{caminho}", params=params, timeout=120,
                              headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"})
            r.raise_for_status()
            return r.json()
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 2:
                raise
            time.sleep(15)


def _todas(caminho, **kw):
    saida, p = [], 1
    while True:
        j = _json(caminho, Q(pagina=p, **kw))
        saida += j.get("rows", [])
        if p >= j["links"]["pagination"]["last_page"]:
            return saida
        p += 1


def _quem_sao():
    """{id do perfil no site da Alerj: {"partido", "nome"}} dos deputados em exercício hoje."""
    import html
    import re
    t = _sessao().get(QUEM_SAO, timeout=60).text
    saida = {}
    for bloco in re.split(r'class="controle_deputado[^"]*"', t)[1:]:
        m = re.search(r"/Deputados/PerfilDeputado/(\d+)", bloco)
        p = re.search(r'class="partido">\s*([^<]*?)\s*<', bloco)
        n = re.search(r'class="nome"><a[^>]*>\s*([^<]*?)\s*<', bloco)
        if m:
            saida[int(m.group(1))] = {"partido": html.unescape(p.group(1)).strip() if p else "", "nome": html.unescape(n.group(1)).strip() if n else ""}
    return saida


def _so_cnpj(doc):
    """Só o CNPJ (empresa) é guardado; o CPF de quem é pessoa física não, nem mascarado (regra do projeto): no lugar dele,
    a marca "PF" (vereadores.comum.mascarar), para o site mostrar "Pessoa física" e não o nome."""
    d = re.sub(r"\D", "", doc or "")
    return d if len(d) == 14 else (vc.PF if len(d) == 11 or "*" in (doc or "") else "")


def coletar():
    PASTA.mkdir(parents=True, exist_ok=True)
    env = _json("environment")
    legs = sorted((env.get("tables") or {}).get("legislatures") or [], key=lambda x: -x["number"])
    leg = legs[0]["id"] if legs else 2
    filtro = {"text": None, "checkboxes": {"withMandate": False, "withoutMandate": False, "withPendency": False, "withoutPendency": False,
                                            "unread": False, "joined": False, "notJoined": False}, "selects": {"legislatureId": "current"}}
    # todos os deputados do DOCIGP (o filtro "na legislatura" deixa de fora quem assumiu há pouco)
    deps = _todas("congressmen", filtro=filtro)
    # quem está no cargo hoje e o partido de hoje: a página "Quem são" do site da Alerj (os 70 em exercício). O id do
    # perfil no site é o remote_id do DOCIGP.
    hoje = _quem_sao()
    # o DOCIGP não tem o id do site para alguns: aí vale o nome (igual, ou todas as palavras do nome do site no nome completo)
    sem_id = {i: h for i, h in hoje.items() if i not in {d.get("remote_id") for d in deps}}
    def _no_site(d):
        if d.get("remote_id") in hoje:
            return d["remote_id"]
        nomes = {normalizar_nome(d.get("nickname") or ""), normalizar_nome(d["name"])}
        for i, h in sem_id.items():
            n = normalizar_nome(h["nome"])
            if n in nomes or set(n.split()) <= set(normalizar_nome(d["name"]).split()):
                return i
        return None
    linhas = []
    for d in deps:
        i = _no_site(d)
        linhas.append({"id": d["id"], "nome": " ".join((d.get("nickname") or d["name"]).split()), "nome_completo": " ".join(d["name"].split()),
                       "partido": (hoje.get(i) or {}).get("partido") or (d.get("party") or {}).get("code", ""),
                       "com_mandato": int(bool(d.get("has_mandate"))), "id_alerj": i or "", "em_exercicio": int(i is not None)})
    gravar_csv(pd.DataFrame(linhas).sort_values("nome"), PASTA / "deputados.csv")
    if sum(x["em_exercicio"] for x in linhas) < 65:
        log(f"Alerj: só {sum(x['em_exercicio'] for x in linhas)} deputados em exercício achados no DOCIGP (o site tem {len(hoje)}); confira")
    # orçamentos (um por deputado e mês) e os lançamentos publicados de cada um
    arq_o, arq_l = PASTA / "orcamentos.csv", PASTA / "lancamentos.csv"
    orc_antigo = pd.read_csv(arq_o) if arq_o.exists() else pd.DataFrame(columns=["orcamento", "lido_em"])
    lan = pd.read_csv(arq_l, dtype={"cnpj_cpf": str}) if arq_l.exists() else pd.DataFrame(columns=["orcamento"])
    lido = {b: str(d) for b, d in zip(orc_antigo.orcamento, orc_antigo.lido_em) if isinstance(d, str) and d}
    semana = time.strftime("%Y-%m-%d", time.localtime(time.time() - 6 * 86400))
    # orçamentos de cada deputado: de novo uma vez por semana (guardados a cada deputado, para a coleta em partes)
    arq_q = PASTA / "orcamentos_lidos.csv"
    lidos_dep = dict(pd.read_csv(arq_q).values) if arq_q.exists() else {}
    orcs = orc_antigo.drop(columns=["lido_em"], errors="ignore").to_dict("records") if len(orc_antigo) else []

    def orcamentos(d):
        saida = []
        for b in _todas(f"congressmen/{d['id']}/legislatures/{leg}/budgets"):
            data = (b.get("budget") or {}).get("date", "")[:7]
            cl = b.get("congressman_legislature") or {}
            saida.append({"orcamento": b["id"], "deputado": d["id"], "mes": data, "valor_mes": float(b.get("value") or 0),
                          "publicado": int(bool(b.get("published_at"))), "inicio": (cl.get("started_at") or "")[:10], "fim": (cl.get("ended_at") or "")[:10]})
        return d["id"], saida
    fila = [d for d in deps if str(lidos_dep.get(d["id"], "")) < semana]
    try:
        with ThreadPoolExecutor(2) as ex:
            for dep, r in ex.map(orcamentos, fila):
                orcs = [o for o in orcs if int(o["deputado"]) != dep] + r
                lidos_dep[dep] = time.strftime("%Y-%m-%d")
    finally:
        if not orcs or gravar_csv(pd.DataFrame(orcs).assign(lido_em=lambda x: x.orcamento.map(lambda b: lido.get(b, ""))).sort_values(["deputado", "mes"]), arq_o):
            gravar_csv(pd.DataFrame(list(lidos_dep.items()), columns=["deputado", "lido_em"]), arq_q)
    orc = pd.DataFrame(orcs)
    orc = orc[orc.mes.str.replace("-", "").astype(int) >= INICIO]
    pedir = [(int(o.deputado), int(o.orcamento)) for o in orc.itertuples()
             if o.publicado and (o.orcamento not in lido or (lido[o.orcamento] < semana and o.mes >= time.strftime("%Y-%m", time.localtime(time.time() - 75 * 86400))))]

    def lancamentos(item):
        dep, b = item
        saida = []
        for e in _todas(f"congressmen/{dep}/legislatures/{leg}/budgets/{b}/entries"):
            v = float(e.get("value") or 0)
            if e.get("is_transport_or_credit") or v >= 0:
                continue  # crédito do mês e saldo que passa: não é gasto
            saida.append({"orcamento": b, "deputado": dep, "data": e.get("date", ""), "centro_custo": e.get("cost_center_name", ""),
                          "codigo_centro": e.get("cost_center_code", ""), "objeto": " ".join((e.get("object") or "").split()),
                          "fornecedor": " ".join((e.get("provider_name") or e.get("to") or "").split()),
                          "cnpj_cpf": _so_cnpj(e.get("provider_cpf_cnpj") or ""), "documento": e.get("document_number", ""), "valor": round(-v, 2)})
        return b, saida
    res = []
    try:
        with ThreadPoolExecutor(2) as ex:
            for r in ex.map(lancamentos, pedir):
                res.append(r)
    finally:
        hoje = time.strftime("%Y-%m-%d")
        if res:
            feitos = {b for b, _ in res}
            if len(lan):
                lan = lan[~lan.orcamento.isin(feitos)]
            novos = pd.DataFrame([x for _, s in res for x in s])
            lan = pd.concat([lan, novos]) if len(novos) else lan
            ordem = [c for c in ("deputado", "orcamento", "data") if c in lan.columns]
            if gravar_csv(lan.sort_values(ordem) if ordem else lan, arq_l):  # o vazio também passa pela comparação
                for b in feitos:  # os orçamentos só contam como lidos se os lançamentos foram gravados
                    lido[b] = hoje
        gravar_csv(orc.assign(lido_em=orc.orcamento.map(lambda b: lido.get(b, ""))).sort_values(["deputado", "mes"]), arq_o)
        log(f"  Alerj: {len(deps)} deputados, {len(orc)} orçamentos mensais; lançamentos de {len(res)} de {len(pedir)} pedidos agora")


_TIPOS = [(r"COMBUST", "Combustível"), (r"VE[IÍ]CULO|FRETAMENTO", "Aluguel de carros"), (r"IMPULSION|M[IÍ]DIA", "Conteúdo para internet e redes sociais"),
          (r"DIVULGA|PUBLICIDADE", "Divulgação do mandato"), (r"CONSULTORIA|ASSESSORIA|PESQUISA|T[EÉ]CNIC", "Consultorias e assessorias"),
          (r"M[OÓ]VEIS|EQUIPAMENTO", "Aluguel de móveis e equipamentos"), (r"IM[OÓ]VE|ESCRIT[OÓ]RIO|CONDOM", "Escritório (aluguel e contas)"),
          (r"TELEF|INTERNET", "Telefone e internet"), (r"MATERIA", "Material de escritório"), (r"HOSPEDA|DI[AÁ]RIA", "Hospedagem e diárias"),
          (r"PASSAGE|A[EÉ]RE", "Passagens"), (r"ALIMENTA|REFEI", "Alimentação"), (r"GR[AÁ]FIC|IMPRESS", "Material gráfico (arte e impressão)")]


def _tipo(t):
    import re
    u = normalizar_nome(t)
    for rx, nome in _TIPOS:
        if re.search(rx, u):
            return nome
    return vc.tipo_curto(t)


def montar(tipos):
    arq_d, arq_o = PASTA / "deputados.csv", PASTA / "orcamentos.csv"
    if not arq_d.exists() or not arq_o.exists():
        return None
    deps = pd.read_csv(arq_d).fillna("")
    orc = pd.read_csv(arq_o).fillna("")
    lan = pd.read_csv(PASTA / "lancamentos.csv", dtype={"cnpj_cpf": str}).fillna({"fornecedor": "", "cnpj_cpf": "", "centro_custo": ""}) \
        if (PASTA / "lancamentos.csv").exists() else pd.DataFrame(columns=["orcamento", "deputado", "data", "centro_custo", "fornecedor", "cnpj_cpf", "valor"])
    orc["am"] = orc.mes.str.replace("-", "").astype(int)
    tse = comum.tse_2022(UF)
    por_civil = {normalizar_nome(x["nome"]): x for x in tse.values()}
    ultimo = vc.ultimo_mes_fechado()
    # O DOCIGP publica o mês de cada gabinete depois da análise da prestação: o último mês do site é o último em que pelo
    # menos 80% das vagas já têm o mês publicado (os seguintes ficam para a próxima coleta).
    pub = orc[orc.publicado == 1] if (orc.publicado == 1).any() else orc
    por_mes = pub.groupby("am").deputado.nunique()
    cheios = [int(m) for m, n in por_mes.items() if n >= 0.8 * CFG["vagas"]]
    ultimo_dado = max(cheios) if cheios else int(por_mes.index.max())
    ver, mandatos = [], []
    for d in deps.itertuples():
        g = orc[orc.deputado == d.id]
        meses_g = sorted(set(g.am[g.am <= ultimo_dado]))
        if not meses_g and not d.em_exercicio:
            continue
        t = por_civil.get(normalizar_nome(d.nome_completo)) or comum.achar(d.nome, tse) or comum.achar(d.nome_completo, por_civil) or {}
        # a Alerj escreve alguns nomes em maiúsculas ("ATILA NUNES"): aí vale o nome de urna do TSE, que tem os acentos
        nome = (vc.titulo(t["urna"]) if t.get("urna") else vc.titulo(d.nome)) if d.nome.isupper() else d.nome
        ver.append({"codigo": int(d.id), "nome": nome, "nome_civil": vc.titulo(t.get("nome") or d.nome_completo),
                    "partido": d.partido if d.em_exercicio else (t.get("partido") or d.partido),
                    "genero": t.get("genero") or ("F" if feminino(d.nome_completo) else "M"), "eleito": t.get("eleito", ""), "pagina": CFG["pagina"]})
        if d.em_exercicio:
            meses_g = sorted(set(meses_g) | {ultimo_dado})
        per = comum.periodos(meses_g, ultimo_dado, ultimo, folga=1)
        if not d.em_exercicio:
            fim = max(meses_g)
            per = [(i, f or f"{fim // 100}-{fim % 100:02d}-28") for i, f in per]
        for i, f in per:
            mandatos.append({"codigo": int(d.id), "inicio": i, "fim": f})
    mes_do = dict(zip(orc.orcamento, orc.am))
    lan = lan[lan.orcamento.map(mes_do).notna()]
    # A devolução de saldo é o dinheiro que não foi gasto voltando para a Alerj: não é despesa do gabinete.
    lan = lan[~lan.centro_custo.map(normalizar_nome).str.startswith("DEVOLUCAO")]
    lan = lan[lan.orcamento.map(mes_do) <= ultimo_dado]
    am = lan.orcamento.map(mes_do).astype(int)
    desp = pd.DataFrame({"ano": am // 100, "mes": am % 100, "codigo": lan.deputado.astype(int), "tipo": lan.centro_custo.map(_tipo),
                         "fornecedor": lan.fornecedor, "cnpj_cpf": lan.cnpj_cpf, "valor": lan.valor})
    cfg = dict(CFG, ultimo_mes=min(ultimo, ultimo_dado))
    return vc.montar(cfg, tipos, pd.DataFrame(ver), pd.DataFrame(mandatos), despesas=desp)
