"""Câmara Municipal de Porto Alegre: vereador por vereador.

Fontes (dados abertos da Câmara, sem cadastro; os portais da Câmara só respondem a endereços do Brasil):
- Vereadores de hoje (nome parlamentar, nome completo, titular ou suplente, em exercício ou não, partido):
  https://portal-api.camarapoa.rs.gov.br/v1/vereadores.json (a resposta traz também o CPF: é descartado na leitura,
  nunca é gravado).
- Foto e página de cada um: https://www.camarapoa.rs.gov.br/vereadores (em exercício e "Atualmente em licença").
- Quota Básica Mensal (QBM), a verba dos gabinetes, lançamento por lançamento (crédito do mês, transferências de saldo
  entre titular e suplente e cada despesa, com a categoria; sem fornecedor):
  https://portal-api.camarapoa.rs.gov.br/v1/lancamentos/setores.json?tipos[]=GAB&tipos[]=PEN&mes=MM/AAAA (os gabinetes
  que tiveram lançamentos no mês) e .../v1/lancamentos.json?mes=MM/AAAA&setor_id=&agregadores=true (os lançamentos).
  É a mesma fonte da página https://transparencia.camarapoa.rs.gov.br/vereadores/qbm. Regras: Resolução 1.576/2001 e
  alterações, https://legislacao.camarapoa.rs.gov.br/normas-qbm-quota-mensal-basica-parlamentar-na-camara/
- Quem esteve no cargo em cada mês: os gabinetes com crédito da QBM no mês. Quando um suplente assume por mais tempo,
  ele ganha um gabinete próprio na QBM e o saldo do titular passa para ele ("TRANSFERENCIA DE SALDO ..."); a data da
  transferência (ou a data escrita nela) marca o dia da troca. Algumas datas vêm do documento oficial "Informações sobre a
  Legislatura" (Seção de Registros e Anais), https://www.camarapoa.rs.gov.br/legislatura
- Subsídio: Lei 13.575/2023, R$ 23.428,64 por mês para o presidente e os demais vereadores de 2025 a 2028, mais um
  subsídio de 13º em dezembro: https://www.camarapoa.rs.gov.br/draco/processos/138806/Lei_13575.pdf
- Nome de urna, nome completo, partido e gênero: TSE (eleição de 2024). O código de cada vereador aqui é o número do
  candidato no TSE (SQ_CANDIDATO), que não muda quando a pessoa sai da lista da Câmara.
A folha de pagamento e a lista de servidores (transparencia.camarapoa.rs.gov.br/remuneracoes e /pessoas) não são lidas:
o robots.txt do portal pede que robôs não entrem nessas páginas.
"""
import html as html_lib
import json
import re
import time
from datetime import date, timedelta

import pandas as pd

from ..config import CACHE, DADOS
from ..util import _sessao, cache_valido, gravar_csv, gravar_varios, log, normalizar_nome, verificar_prazo
from . import comum

COD = 4314902
INICIO = 202501
API = "https://portal-api.camarapoa.rs.gov.br/v1"
SITE = "https://www.camarapoa.rs.gov.br"
PASTA = DADOS / "municipios" / "porto_alegre"  # a pasta também tem os arquivos da Prefeitura (prefeitura_*.csv)
C = CACHE / "cmpa"
ARQ_VER = PASTA / "camara_vereadores.csv"
ARQ_GAB = PASTA / "camara_qbm_gabinetes.csv"
ARQ_LANC = PASTA / "camara_qbm_lancamentos.csv"
ARQ_TOT = PASTA / "camara_qbm_totais.csv"
REBAIXAR = 3   # meses mais recentes que ainda podem mudar
PAUSA = 0.8    # segundos entre pedidos
SUBSIDIO = 23428.64
QBM_PAGINA = "https://transparencia.camarapoa.rs.gov.br/vereadores/qbm"
COLUNAS_LANC = ["ano", "mes", "setor_id", "id", "data", "valor", "cat", "cat_nome", "raiz", "raiz_nome", "descricao"]
CFG = {
    "cod": COD, "n": "Porto Alegre", "uf": "RS", "casa": "Câmara Municipal de Porto Alegre", "vagas": 35, "inicio": INICIO,
    "subsidio": [[202501, SUBSIDIO]],
    "verba_nome": "Quota Básica Mensal (QBM) do gabinete",
    "verba_regra": ("Paga material de escritório, cópias, telefone, correios, viagens do vereador e a indenização pelo uso do "
                    "carro próprio (por quilômetro). O que não é usado num mês pode ser usado nos meses seguintes do mesmo "
                    "quadrimestre (e até um quarto passa para o quadrimestre seguinte); o que sobra no fim do ano fica com a Câmara."),
    "verba_notas": ["A Câmara publica cada lançamento da QBM com a categoria da despesa, sem o nome dos fornecedores.",
                    "Quando um suplente assume por mais tempo, o saldo do mês passa do gabinete do titular para o do suplente: "
                    "aqui cada um fica com o que gastou."],
    "salario_nota": ("Subsídio fixado pela Lei 13.575/2023 para 2025 a 2028, igual para o presidente da Câmara e os demais "
                     "vereadores. A lei também prevê o 13º (um subsídio a mais em dezembro), que não entra aqui, e permite "
                     "correção anual por Resolução de Mesa: não achamos nenhuma correção publicada até agora."),
    "equipe_aviso": "A Câmara publica a equipe de cada gabinete, mas pede que robôs não a leiam.",
    "credito_foto": "Câmara Municipal de Porto Alegre", "pagina": f"{SITE}/vereadores",
    "notas": ["Quem estava no cargo em cada mês vem da QBM: todo mês cada gabinete em exercício recebe o crédito da quota. "
              "Suplentes que assumiram só por alguns dias, sem gabinete próprio na QBM, não aparecem, e esses dias contam "
              "para o titular.",
              "A Câmara publica a folha de pagamento e a lista de servidores de cada gabinete no Portal da Transparência, "
              "mas pede (no robots.txt do portal) que robôs não leiam essas páginas. Por isso a equipe dos gabinetes não "
              "aparece aqui."],
    "fontes": {"vereadores": f"{SITE}/vereadores", "qbm": QBM_PAGINA, "legislatura": f"{SITE}/legislatura",
               "subsidio": f"{SITE}/draco/processos/138806/Lei_13575.pdf",
               "qbm_normas": "https://legislacao.camarapoa.rs.gov.br/normas-qbm-quota-mensal-basica-parlamentar-na-camara/"},
}


def _get(caminho, arquivo=None, dias=None, params=None, texto=False):
    """GET em portal-api (ou numa URL completa), com cache em arquivo. Nunca mostra o conteúdo da resposta no log."""
    if arquivo is not None and cache_valido(arquivo, dias):
        t = arquivo.read_text(encoding="utf-8")
        return t if texto else json.loads(t)
    verificar_prazo()
    url = caminho if caminho.startswith("http") else f"{API}/{caminho}"
    for tentativa in range(4):
        try:
            r = _sessao().get(url, params=params, timeout=90)
            r.raise_for_status()
            t = r.text
            dados = t if texto else r.json()
            break
        except Exception:
            if tentativa == 3:
                raise
            time.sleep(5 * (tentativa + 1))
    time.sleep(PAUSA)
    if arquivo is not None:
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_text(t, encoding="utf-8")
    return dados


def _num(v):
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------- coleta
def _lista_site():
    """Página "Vereadores" do site da Câmara: nome, partido, página, foto, se está em licença e quem substitui."""
    t = _get(f"{SITE}/vereadores", texto=True)
    linhas = []
    for secao in ("titulares", "suplentes"):  # "suplentes" é a lista "Atualmente em licença"
        m = re.search(rf'<ul[^>]*id="{secao}"[^>]*>(.*?)</ul>', t, re.S)
        for li in re.findall(r'<li class="column vereador">(.*?)</li>', m.group(1) if m else "", re.S):
            href = re.search(r'href="([^"]+)"', li)
            foto = re.search(r'<img[^>]*src="([^"]+)"', li)
            nome = re.search(r"<h2>(.*?)</h2>", li, re.S)
            subst = re.search(r"Substituindo\s+([^<]+)<", li)
            nome_txt = html_lib.unescape(re.sub(r"\s+", " ", nome.group(1))).strip() if nome else ""
            partido = re.search(r"\(([^()]*)\)\s*$", nome_txt)
            foto_url = html_lib.unescape(foto.group(1)) if foto else ""
            if foto_url.startswith("/"):
                foto_url = SITE + foto_url
            linhas.append({"nome_site": re.sub(r"\s*\([^()]*\)\s*$", "", nome_txt).strip(), "partido_site": partido.group(1).strip() if partido else "",
                           "pagina": SITE + href.group(1) if href and href.group(1).startswith("/") else (href.group(1) if href else ""),
                           "foto": "" if "avatar" in foto_url else foto_url, "licenciado": secao == "suplentes",
                           "substituindo": html_lib.unescape(subst.group(1)).strip() if subst else ""})
    return pd.DataFrame(linhas, columns=["nome_site", "partido_site", "pagina", "foto", "licenciado", "substituindo"])


def vereadores():
    """Lista de hoje (API do portal + site). Quem sai da lista continua gravado (atual = False), com a foto e a página."""
    lista = _get("vereadores.json")  # sem cache em arquivo: a resposta traz o CPF
    linhas = []
    for v in lista:
        v.pop("cpf", None)  # descartado aqui mesmo, antes de qualquer outra coisa
        linhas.append({"id": int(v["id"]), "nome_parlamentar": re.sub(r"\s+", " ", v.get("nome_parlamentar") or "").strip(),
                       "nome_completo": re.sub(r"\s+", " ", v.get("nome_completo") or "").strip(), "tipo": v.get("tipo") or "",
                       "em_exercicio": (v.get("vereanca") or "") == "sim", "partido": ((v.get("partido") or {}).get("sigla") or "").strip()})
    del lista
    api = pd.DataFrame(linhas)
    site = _lista_site()
    opcoes = [(n, i) for i, n in enumerate(site.nome_site)]
    extra = {c: [] for c in ["pagina", "foto", "licenciado", "substituindo"]}
    for n in api.nome_parlamentar:
        i = comum.achar_parecido(n, opcoes, 0.9) if opcoes else None
        for c in extra:
            extra[c].append(site.iloc[i][c] if i is not None else ("" if c != "licenciado" else False))
    api = api.assign(**extra, atual=True)
    sem = sorted(set(site.nome_site) - {site.nome_site.iloc[i] for i in (comum.achar_parecido(n, opcoes, 0.9) for n in api.nome_parlamentar) if i is not None})
    if sem:
        log(f"  Porto Alegre: no site e não na API: {', '.join(sem)}")
    if ARQ_VER.exists():
        velho = pd.read_csv(ARQ_VER).fillna("")
        velho = velho[~velho.id.isin(api.id)].assign(atual=False, em_exercicio=False, licenciado=False, substituindo="")
        api = pd.concat([api, velho[api.columns]], ignore_index=True)
    PASTA.mkdir(parents=True, exist_ok=True)
    gravar_csv(api.sort_values("id"), ARQ_VER)
    log(f"  Porto Alegre: {int(api.atual.sum())} vereadores na lista de hoje ({len(api)} gravados)")
    return api


def qbm():
    """Lançamentos da QBM, gabinete por gabinete, mês a mês. Os meses antigos já gravados não são baixados de novo."""
    ate = comum.ultimo_mes_fechado()
    recentes = comum.menos_meses(ate, REBAIXAR)
    gab = pd.read_csv(ARQ_GAB) if ARQ_GAB.exists() else pd.DataFrame(columns=["ano", "mes", "setor_id", "gabinete", "tipo"])
    lanc = pd.read_csv(ARQ_LANC, dtype={"cat": str, "raiz": str}).fillna({"descricao": ""}) if ARQ_LANC.exists() else pd.DataFrame(columns=COLUNAS_LANC)
    tot = pd.read_csv(ARQ_TOT) if ARQ_TOT.exists() else pd.DataFrame(columns=["ano", "mes", "setor_id", "creditos", "gastos", "economia"])
    feitos = set(gab.ano * 100 + gab.mes) if len(gab) else set()
    for a, m in comum.meses(INICIO, ate):
        am = a * 100 + m
        if am in feitos and am <= recentes:
            continue
        dias = 5 if am > recentes else None
        mes = f"{m:02d}/{a}"
        setores = _get("lancamentos/setores.json", C / f"setores_{am}.json", dias,
                       params={"tipos[]": ["GAB", "PEN"], "mes": mes, "invisivel": "true"}).get("setores") or []
        if not setores:
            continue  # mês ainda não publicado
        g_l, l_l, t_l = [], [], []
        for s in setores:
            d = _get("lancamentos.json", C / f"lancamentos_{am}_{s['id']}.json", dias, params={"mes": mes, "setor_id": s["id"], "agregadores": "true"})
            g_l.append({"ano": a, "mes": m, "setor_id": int(s["id"]), "gabinete": re.sub(r"\s+", " ", s["nome"]).strip(), "tipo": s.get("tipo") or ""})
            t_l.append({"ano": a, "mes": m, "setor_id": int(s["id"]), "creditos": _num(d.get("creditos")), "gastos": _num(d.get("gastos")), "economia": _num(d.get("economia"))})
            for x in d.get("lancamentos") or []:
                cat, raiz = x.get("categoria") or {}, x.get("categoria_raiz") or {}
                # a descrição fica só nos créditos fora do comum e nas transferências de saldo (dizem quem substituiu quem
                # e quando) e nos lançamentos sem categoria (estornos e "material adicional")
                texto = re.sub(r"\s+", " ", x.get("descricao") or "").strip()
                guardar = (str(raiz.get("codigo")) == "1" and not normalizar_nome(texto).startswith("CREDITO DE QBM DE R$")) or not raiz.get("codigo")
                l_l.append({"ano": a, "mes": m, "setor_id": int(s["id"]), "id": x.get("id"), "data": (x.get("created_at") or "")[:10], "valor": _num(x.get("valor")),
                            "cat": str(cat.get("codigo") or ""), "cat_nome": (cat.get("nome") or "").strip(), "raiz": str(raiz.get("codigo") or ""),
                            "raiz_nome": (raiz.get("nome") or "").strip(),
                            "descricao": texto if guardar else ""})
        def trocar(df, novas):  # as linhas do mês saem e entram as novas
            velhas = df[(df.ano * 100 + df.mes) != am] if len(df) else df
            return pd.concat([velhas, novas], ignore_index=True) if len(velhas) else novas
        gab = trocar(gab, pd.DataFrame(g_l))
        lanc = trocar(lanc, pd.DataFrame(l_l, columns=COLUNAS_LANC))
        tot = trocar(tot, pd.DataFrame(t_l))
        PASTA.mkdir(parents=True, exist_ok=True)
        ordem = ["ano", "mes", "setor_id"]
        # os lançamentos, os totais e os gabinetes do mês (o controle: os meses em camara_qbm_gabinetes.csv não são
        # baixados de novo), juntos e o controle por último: recusados, nenhum muda e o mês é lido de novo
        if not gravar_varios([(lanc.sort_values(ordem + ["data", "id"]), ARQ_LANC), (tot.sort_values(ordem), ARQ_TOT),
                              (gab.sort_values(ordem), ARQ_GAB)]):
            break
        log(f"  Porto Alegre: QBM de {mes} ({len(setores)} gabinetes, {len(l_l)} lançamentos)")


def fotos():
    """Fotos da página da Câmara (a versão grande; se não houver, a pequena). Só aqui na coleta: o site da Câmara não
    responde fora do Brasil, e montar() só usa as fotos que já estão em site/fotos/."""
    ver, _ = _tabela_vereadores()
    if ver is None:
        return
    com_foto = ver[ver.foto.fillna("") != ""]
    comum.fotos(COD, [(int(c), f.replace("/thumb/", "/original/")) for c, f in zip(com_foto.codigo, com_foto.foto)])
    comum.fotos(COD, [(int(c), f) for c, f in zip(com_foto.codigo, com_foto.foto)])  # só as que faltaram


def coletar():
    vereadores()
    qbm()
    fotos()


# ---------------------------------------------------------------- montagem
# Datas de posse, licença e perda de mandato do documento "Informações da XIX Legislatura" (Seção de Registros e Anais,
# https://www.camarapoa.rs.gov.br/legislatura, versão de 11/08/2026), para as trocas em que a transferência de saldo da
# QBM não traz a data (ou foi lançada dias depois). Só corrigem o dia dentro do mês em que a QBM já mostra a troca.
DATAS_OFICIAIS = {
    "Alexandre Bobadra": {"fim": ["2025-12-15"]},     # suplência cessou às 14h de 15/12/2025
    "Gilvani O Gringo": {"fim": ["2025-12-29"]},      # perda do mandato (Resolução 2.972/2025); Professor Tovi assumiu em 30/12/2025
    "Luky Vieira": {"inicio": ["2026-01-05"], "fim": ["2026-03-05"]},  # no lugar do Professor Tovi, secretário municipal
    "Professor Tovi": {"inicio": ["2026-03-06"]},     # voltou da Secretaria de Esportes (posse em 05/01/2026, licenciado no mesmo dia)
    "Professor Vitorino": {"inicio": ["2026-01-30"]}, # voltou da Secretaria de Serviços Urbanos
    "Rafael Fleck": {"fim": ["2026-01-29"]},          # licenciado a partir de 30/01/2026 (Secretaria de Serviços Urbanos)
}
# Categoria da QBM (subcategoria primeiro) -> nome curto do tipo de gasto (os mesmos nomes das outras cidades)
_TIPOS_QBM = {"11.1": "Passagens", "11.2": "Hospedagem e diárias", "12": "Carro próprio (indenização por km)",
              "2": "Cópias e encadernação", "3": "Telefone e internet", "8": "Telefone e internet",
              "5": "Material de escritório", "6": "Correios"}
_PREFIXO = re.compile(r"^\s*Gab\.?\s*Ver\s*(\(a\))?\.?\s*", re.I)


def _nome_gabinete(nome):
    """"Gab. Ver(a). Aldacir Oliboni" -> "Aldacir Oliboni"."""
    return re.sub(r"\s+", " ", _PREFIXO.sub("", str(nome or ""))).strip()


def _tipo(cat, raiz, raiz_nome, descricao):
    for chave in (cat, raiz):
        if chave in _TIPOS_QBM:
            return _TIPOS_QBM[chave]
    if normalizar_nome(descricao).startswith("MATERIAL"):  # "Material adicional - Outros - Confecção de carimbos", sem categoria
        return "Material de escritório"
    t = comum.tipo_curto(descricao or raiz_nome)
    return t if len(t) <= 40 else "Outros"


def _tabela_vereadores():
    """Uma linha por pessoa que teve gabinete na QBM (código = número do candidato no TSE) e {setor_id: código}."""
    if not ARQ_GAB.exists():
        return None, {}
    gab = pd.read_csv(ARQ_GAB)
    api = pd.read_csv(ARQ_VER).fillna("") if ARQ_VER.exists() else pd.DataFrame(
        columns=["id", "nome_parlamentar", "nome_completo", "tipo", "em_exercicio", "partido", "pagina", "foto", "licenciado", "substituindo", "atual"])
    tse = comum.candidatos_tse("RS", "Porto Alegre")
    api_op = [(n, int(i)) for i, n in zip(api.id, api.nome_parlamentar)]
    pessoas, setor_cod, sem = {}, {}, []
    for sid, g in gab.sort_values(["ano", "mes"]).groupby("setor_id"):
        nome_gab = _nome_gabinete(g.gabinete.iloc[-1])  # "Conselheiro Marcelo Bernardi", "Giovani e Coletivo"...
        aid = comum.achar_parecido(nome_gab, api_op, 0.9) if api_op else None
        a = api[api.id == aid].iloc[0] if aid is not None else None
        nome = a.nome_parlamentar if a is not None else nome_gab
        t = comum.achar_no_tse(nome, tse)
        if t is None:
            t = comum.achar_no_tse(nome_gab, tse)
        if t is None and a is None:
            sem.append(nome_gab)
            continue
        codigo = int(t["sq"]) if t is not None else int(aid)
        setor_cod[int(sid)] = codigo
        if codigo in pessoas:
            continue
        civil = comum.titulo(t["nome"]) if t is not None else ""
        if not civil and a is not None:
            civil = a.nome_completo if a.nome_completo != a.nome_completo.upper() else comum.titulo(a.nome_completo)
        eleito = ({"titular": "eleito", "suplente": "suplente"}.get(a.tipo, "") if a is not None else "") or (t["situacao"] if t is not None else "")
        pessoas[codigo] = {"codigo": codigo, "nome": nome, "nome_civil": civil,
                           "partido": (a.partido if a is not None else "") or (t["partido"] if t is not None else ""),
                           "genero": t["genero"] if t is not None else "", "eleito": eleito,
                           "pagina": (a.pagina if a is not None else "") or CFG["pagina"], "foto": a.foto if a is not None else ""}
    if sem:
        log(f"  Porto Alegre: gabinetes da QBM sem vereador identificado: {', '.join(sem)}")
    return pd.DataFrame(list(pessoas.values())), setor_cod


def _lancamentos(setor_cod):
    """Lançamentos da QBM com o código do vereador e o que cada um é: crédito (crédito do mês, crédito de acúmulo,
    transferência de saldo entre titular e suplente) ou despesa (com o tipo)."""
    lanc = pd.read_csv(ARQ_LANC, dtype={"cat": str, "raiz": str}).fillna({"cat": "", "raiz": "", "cat_nome": "", "raiz_nome": "", "descricao": ""})
    lanc["am"] = lanc.ano * 100 + lanc.mes
    lanc["codigo"] = lanc.setor_id.map(setor_cod)
    desc = lanc.descricao.map(normalizar_nome)
    lanc["transferencia"] = (lanc.raiz == "1") & desc.str.contains("TRANSFER")
    # na categoria "1.3 Transferência de Saldo" há também inscrições em eventos pagas pela quota: são despesa
    lanc["credito"] = (lanc.raiz == "1") & (lanc.cat.isin(["1.1", "1.2"]) | lanc.transferencia)
    # estorno sem categoria: fica com a categoria do lançamento que ele desfaz (mesmo gabinete, mês e valor)
    for i in lanc[(lanc.raiz == "") & (lanc.valor > 0)].index:
        par = lanc[(lanc.setor_id == lanc.at[i, "setor_id"]) & (lanc.am == lanc.at[i, "am"]) & (lanc.valor.round(2) == -round(lanc.at[i, "valor"], 2)) & (lanc.raiz != "")]
        if len(par):
            for c in ("cat", "cat_nome", "raiz", "raiz_nome"):
                lanc.at[i, c] = par.iloc[0][c]
    lanc["tipo"] = [_tipo(c, r, rn, d) for c, r, rn, d in zip(lanc.cat, lanc.raiz, lanc.raiz_nome, lanc.descricao)]
    return lanc


def _data_troca(lanc, codigo, am, entrada):
    """Dia da troca de titular e suplente num mês, pela transferência de saldo que o vereador recebeu (entrada) ou deu:
    a data escrita na transferência ("... EXISTENTE EM 26/05/2025"), senão a data do lançamento."""
    t = lanc[lanc.transferencia & (lanc.codigo == codigo) & (lanc.am == am) & ((lanc.valor > 0) if entrada else (lanc.valor < 0))]
    if not len(t):
        return None
    x = t.iloc[0]
    par = lanc[lanc.transferencia & (lanc.am == am) & (lanc.codigo != codigo) & (lanc.valor.round(2) == -round(x.valor, 2))]
    textos = [x.descricao] + list(par.descricao)
    for texto in textos:
        m = re.search(r"(\d{2})/(\d{2})/(\d{4})", texto)
        if m and int(m.group(3)) * 100 + int(m.group(2)) == am:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return min(date.fromisoformat(d) for d in [x.data] + list(par.data))


def _periodos(lanc, ultimo, ver):
    """Períodos no cargo de cada vereador: os meses com crédito da QBM no gabinete (um mês sem nenhum lançamento, entre
    dois meses com crédito e sem transferência de saldo, conta como no cargo), com o dia exato das trocas."""
    credito = lanc[lanc.credito & lanc.codigo.notna()].groupby(["codigo", "am"]).valor.sum()
    transf = lanc[lanc.transferencia & lanc.codigo.notna()]
    nomes = dict(zip(ver.codigo, ver.nome))
    oficiais = {comum.chave_nome(n): d for n, d in DATAS_OFICIAIS.items()}
    linhas = []
    for codigo in sorted({int(c) for c, _ in credito.index}):
        ms = sorted(am for (c, am), v in credito.items() if int(c) == codigo and v > 0.5)
        if not ms:
            continue
        com_transf = set(transf[transf.codigo == codigo].am)
        cheios = set(ms)
        for de, ate in zip(ms, ms[1:]):
            buraco = comum.meses(comum.mes_seguinte(de), comum.menos_meses(ate, 1)) if ate != comum.mes_seguinte(de) else []
            if buraco and not any(de <= am <= ate for am in com_transf):
                cheios |= {a * 100 + m for a, m in buraco}
        ofi = oficiais.get(comum.chave_nome(nomes.get(codigo, "")), {})
        for ini, fim in comum.periodos_de_meses(cheios, ultimo):
            am_ini, am_fim = int(ini[:4]) * 100 + int(ini[5:7]), (int(fim[:4]) * 100 + int(fim[5:7])) if fim else None
            d = _data_troca(lanc, codigo, am_ini, entrada=True) if am_ini > INICIO else None
            if d:
                ini = d.isoformat()
            if fim:
                d = _data_troca(lanc, codigo, am_fim, entrada=False)
                if d:
                    fim = (d - timedelta(days=1)).isoformat()
            ini = next((x for x in ofi.get("inicio", []) if x[:7] == ini[:7]), ini)
            fim = next((x for x in ofi.get("fim", []) if fim and x[:7] == fim[:7]), fim)
            linhas.append({"codigo": codigo, "inicio": ini, "fim": fim})
    return pd.DataFrame(linhas, columns=["codigo", "inicio", "fim"])


def montar(tipos):
    if not (ARQ_GAB.exists() and ARQ_LANC.exists()):
        return None
    ate = comum.ultimo_mes_fechado()
    ver, setor_cod = _tabela_vereadores()
    lanc = _lancamentos(setor_cod)
    ultimo = min(ate, int(lanc.am.max()))
    lanc = lanc[lanc.am <= ultimo]
    mandatos_df = _periodos(lanc, ultimo, ver)
    # verba: cada despesa (valor positivo; estornos entram negativos), por tipo, sem fornecedor
    desp = lanc[~lanc.credito & lanc.codigo.notna()]
    despesas = pd.DataFrame({"ano": desp.ano, "mes": desp.mes, "codigo": desp.codigo.astype(int), "tipo": desp.tipo,
                             "fornecedor": "", "cnpj_cpf": "", "valor": -desp.valor})
    # limite do ano: os créditos do gabinete (já com as transferências de saldo); o que não foi usado num ano fechado
    # não passa para o ano seguinte
    cred = lanc[lanc.credito & lanc.codigo.notna()].groupby(["ano", "codigo"]).valor.sum().rename("credito")
    gasto = despesas.groupby(["ano", "codigo"]).valor.sum().rename("gasto")
    verba = pd.concat([cred, gasto], axis=1).fillna(0).reset_index()
    ano_fechado = verba.ano.astype(int) * 100 + 12 <= ultimo
    verba["devolvido"] = (verba.credito - verba.gasto).clip(lower=0).where(ano_fechado, 0).round(2)
    verba = verba[["ano", "codigo", "credito", "devolvido"]].astype({"codigo": int})
    mensal = lanc[lanc.cat == "1.1"].groupby("ano").valor.agg(lambda v: v.round(2).mode().iloc[0])
    cfg = dict(CFG, ultimo_mes=ultimo, verba_mes={str(int(a)): float(v) for a, v in mensal.items()})
    return comum.montar(cfg, tipos, ver[["codigo", "nome", "nome_civil", "partido", "genero", "eleito", "pagina"]], mandatos_df,
                        despesas=despesas, verba=verba)
