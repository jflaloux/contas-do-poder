"""Robô das câmaras municipais, passo 2: São Paulo (capital), vereador por vereador.

Fontes (Câmara Municipal de São Paulo, dados abertos, sem cadastro):
- Quem ocupou cada um dos 55 gabinetes, com as datas (titulares e suplentes): SPLegis, OcupacaoGabineteJSON
  https://splegisws.saopaulo.sp.leg.br/ws/ws2.asmx/OcupacaoGabineteJSON
- Partido de cada mandato: SPLegis, VereadoresCMSPJSON
- Gastos do gabinete (Auxílio-Encargos Gerais de Gabinete), nota por nota, mês a mês, e o crédito mensal:
  SisGV, ObterDebitoVereadorJSON e ObterCreditoVereadorJSON (SOAP)
  https://sisgvconsulta.saopaulo.sp.leg.br/ws/Servicos.asmx
- Funcionários de cada gabinete (retrato do mês mais recente):
  https://www.saopaulo.sp.leg.br/static/transparencia/funcionarios/CMSP-XML-Funcionarios.xml
- Nome de urna, nome completo, gênero e partido na eleição: TSE (o mesmo arquivo do passo 1, municipios.py)
- Foto e página oficial: https://www.saopaulo.sp.leg.br/vereadores/membros/ (a Câmara diz que o banco de
  imagens dela é livre para uso; o site mostra o crédito)

Salário (subsídio): o mesmo para todos, fixado pela própria Câmara em 2024 para a legislatura 2025–2028:
R$ 24.754,79 em janeiro de 2025 e R$ 26.080,98 desde fevereiro de 2025 (75% do salário do deputado estadual,
o máximo que a Constituição permite). Quem ocupou o gabinete só parte do mês recebe proporcional aos dias.
A Câmara só mostra o contracheque de cada vereador e de cada assessor para quem informa um CPF; por isso não
usamos essa página: o 13º (se houver) fica de fora, e da equipe do gabinete só contamos as pessoas.

Saída (vai para o Git): dados/municipios/sp/*.csv e site/dados/camaras.json.
"""
import csv
import io
import json
import re
import time
import xml.etree.ElementTree as ET
import zipfile
from calendar import monthrange
from collections import Counter
from datetime import date, datetime

import pandas as pd

from .config import CACHE, DADOS, HOJE, RAIZ
from .fotos import _ajustar
from .util import TempoEsgotado, _sessao, baixar, cache_valido, log, normalizar_nome, verificar_prazo

COD_IBGE = 3550308
LEGISLATURA = 19               # 2025–2028
INICIO = (2025, 1)
SUBSIDIO = [((2025, 1), 24754.79), ((2025, 2), 26080.98)]  # (a partir de, valor mensal)
PASTA = DADOS / "municipios" / "sp"
C = CACHE / "cmsp"
FOTOS = RAIZ / "site" / "fotos"
SAIDA = RAIZ / "site" / "dados" / "camaras.json"
TSE_ZIP = CACHE / "municipios" / "consulta_cand_2024.zip"  # baixado pelo passo 1
TSE = "https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/consulta_cand_2024.zip"

SPLEGIS = "https://splegisws.saopaulo.sp.leg.br/ws/ws2.asmx"
SISGV = "https://sisgvconsulta.saopaulo.sp.leg.br/ws/Servicos.asmx"
SISGV_NS = "http://saopaulo.sp.leg.br/sisgv/ws2"
FUNCIONARIOS = "https://www.saopaulo.sp.leg.br/static/transparencia/funcionarios/CMSP-XML-Funcionarios.xml"
SITE_CMSP = "https://www.saopaulo.sp.leg.br"
CONTAS = f"{SITE_CMSP}/transparencia/custos-de-mandato/contas-vereadores/"
REBAIXAR_MESES = 4  # os últimos meses ainda recebem notas: baixa de novo a cada semana


def _meses(ate):
    a, m = INICIO
    while (a, m) <= ate:
        yield a, m
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)


def ultimo_mes():
    """Último mês fechado (o mês corrente ainda está recebendo notas e créditos)."""
    return (HOJE.year - 1, 12) if HOJE.month == 1 else (HOJE.year, HOJE.month - 1)


def _json_do_ws(texto):
    """Os serviços da Câmara devolvem o JSON seguido de um envelope XML: fica só com o JSON."""
    i = texto.find("<?xml")
    return json.loads((texto[:i] if i > 0 else texto).strip() or "[]")


# ---------------------------------------------------------------- SPLegis: gabinetes e partidos
def _splegis(op, dias=7):
    arq = C / f"{op}.json"
    if not cache_valido(arq, dias):
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_text(json.dumps(_json_do_ws(baixar(f"{SPLEGIS}/{op}", timeout=120).text), ensure_ascii=False), encoding="utf-8")
    return json.loads(arq.read_text(encoding="utf-8"))


def gabinetes():
    """Quem ocupou cada gabinete nesta legislatura: [gabinete, codigo, vereador, inicio, fim]."""
    linhas = [{"gabinete": x["gabinete"], "codigo": x["codigo"], "vereador": x["vereador"].strip(),
               "inicio": x["inicio"][:10], "fim": (x.get("fim") or "")[:10]}
              for x in _splegis("OcupacaoGabineteJSON") if x["legislatura"] == LEGISLATURA]
    df = pd.DataFrame(linhas).sort_values(["gabinete", "inicio"])
    PASTA.mkdir(parents=True, exist_ok=True)
    df.to_csv(PASTA / "gabinetes.csv", index=False)
    return df


def _partidos(codigos):
    """Partido do mandato atual (o que começou nesta legislatura); se não houver, a filiação mais recente."""
    saida = {}
    for v in _splegis("VereadoresCMSPJSON"):
        if v["chave"] not in codigos:
            continue
        mand = [m for m in v.get("mandatos") or [] if (m.get("inicio") or "") >= f"{INICIO[0]}-01-01" and m.get("partido")]
        fil = sorted([f for f in v.get("filiacoes") or [] if f.get("partido")], key=lambda f: f.get("inicio") or "")
        if mand:
            saida[v["chave"]] = max(mand, key=lambda m: m["inicio"])["partido"]["sigla"]
        elif fil:
            saida[v["chave"]] = fil[-1]["partido"]["sigla"]
    return saida


# ---------------------------------------------------------------- TSE: nome de urna, nome completo, gênero
def _candidatos():
    """Eleitos e suplentes a vereador em São Paulo (2024). Guarda só o necessário, sem CPF."""
    arq = PASTA / "candidatos_tse.csv"
    if arq.exists():
        return pd.read_csv(arq, dtype=str).fillna("")
    if not cache_valido(TSE_ZIP, 60):
        log("Vereadores SP: arquivo de candidatos do TSE (~60 MB)")
        TSE_ZIP.parent.mkdir(parents=True, exist_ok=True)
        TSE_ZIP.write_bytes(baixar(TSE, timeout=600).content)
    linhas = []
    with zipfile.ZipFile(TSE_ZIP) as z, z.open("consulta_cand_2024_SP.csv") as f:
        for l in csv.DictReader(io.TextIOWrapper(f, encoding="latin1"), delimiter=";"):
            if l["NM_UE"] == "SÃO PAULO" and l["CD_CARGO"] == "13" and l["DS_SIT_TOT_TURNO"] in ("ELEITO POR QP", "ELEITO POR MÉDIA", "SUPLENTE"):
                linhas.append({"nome_urna": l["NM_URNA_CANDIDATO"].strip(), "nome": l["NM_CANDIDATO"].strip(),
                               "partido": l["SG_PARTIDO"], "genero": l["DS_GENERO"][:1], "situacao": l["DS_SIT_TOT_TURNO"]})
    df = pd.DataFrame(linhas).sort_values("nome_urna")
    df.to_csv(arq, index=False)
    return df.fillna("")


# ---------------------------------------------------------------- site da Câmara: nome, foto e página
def _slug(nome):
    return re.sub(r"[^a-z0-9]+", "-", normalizar_nome(nome).lower()).strip("-")


def _cartoes():
    """Cartões da página de vereadores (no cargo e licenciados): nome, página e foto."""
    saida = []
    for filtro in ("", "?filtro=licenciados"):
        t = baixar(f"{SITE_CMSP}/vereadores/membros/{filtro}", timeout=60).text
        for bloco in t.split('<div class="card-vereador">')[1:]:
            nome = re.search(r"<h3[^>]*>(.*?)</h3>", bloco, re.S)
            pagina = re.search(r'href="(https://www\.saopaulo\.sp\.leg\.br/vereador/[^"#]+)"', bloco)
            foto = re.search(r'<img class="thumbnail" src="([^"]+)"', bloco)
            if nome and pagina:
                saida.append({"nome": re.sub(r"\s+", " ", nome.group(1)).strip(), "pagina": pagina.group(1), "foto": foto.group(1) if foto else ""})
    return saida


def _pagina_vereador(nome):
    """Para quem já saiu (não aparece na lista): tenta a página pelo nome."""
    url = f"{SITE_CMSP}/vereador/{_slug(nome)}/"
    try:
        t = baixar(url, timeout=60, tentativas=2).text
    except TempoEsgotado:
        raise
    except Exception:
        return None
    h1 = re.search(r'<h1 class="desktop-headeline-3">\s*([^<]+)', t)
    foto = re.search(r'<img src="([^"]+)" alt="foto do vereador"', t)
    if not h1:
        return None
    return {"nome": h1.group(1).strip(), "pagina": url, "foto": foto.group(1) if foto else ""}


_MINUSCULAS = {"da", "de", "do", "das", "dos", "e"}


def _titulo(nome):
    return " ".join(w.lower() if w.lower() in _MINUSCULAS and i else w.capitalize() for i, w in enumerate(nome.lower().split()))


# nome na Câmara -> nome de urna no TSE, quando nem as palavras do nome batem
_NOMES_TSE = {"SILVINHO LEITE": "SILVINHO"}


def _no_tse(nome_cmsp, por_urna, tse):
    """Acha o candidato no TSE: pelo nome de urna; senão, quem tem todas as palavras do nome (urna + nome civil)."""
    n = normalizar_nome(_NOMES_TSE.get(nome_cmsp, nome_cmsp))
    if n in por_urna or n.replace(".", "") in por_urna:
        return por_urna.get(n) or por_urna.get(n.replace(".", ""))
    palavras = set(n.replace(".", "").split()) - {"DR", "DRA"}
    achados = [r for r in tse.itertuples() if palavras <= set(normalizar_nome(f"{r.nome_urna} {r.nome}").replace(".", "").split())]
    eleitos = [r for r in achados if r.situacao != "SUPLENTE"]
    if len(eleitos) == 1:
        return eleitos[0]
    return achados[0] if len(achados) == 1 else None


def vereadores(gab):
    arq = PASTA / "vereadores.csv"
    antigos = pd.read_csv(arq, dtype={"codigo": int}).fillna("") if arq.exists() else pd.DataFrame()
    ja = {r.codigo: r for r in antigos.itertuples()} if len(antigos) else {}
    codigos = dict(zip(gab.codigo, gab.vereador))
    partidos = _partidos(set(codigos))
    tse = _candidatos()
    por_urna = {normalizar_nome(r.nome_urna): r for r in tse.itertuples()}
    cartoes = {normalizar_nome(c["nome"]).replace(".", ""): c for c in _cartoes()}
    linhas = []
    for cod, nome_cmsp in sorted(codigos.items(), key=lambda x: x[1]):
        chave = normalizar_nome(nome_cmsp).replace(".", "")
        c = cartoes.get(chave)
        if not c and cod in ja and ja[cod].pagina:
            c = {"nome": ja[cod].nome, "pagina": ja[cod].pagina, "foto": ja[cod].foto}
        if not c:
            c = _pagina_vereador(nome_cmsp) or {}
        t = _no_tse(nome_cmsp, por_urna, tse)
        linhas.append({
            "codigo": cod, "nome": c.get("nome") or _titulo(nome_cmsp), "nome_cmsp": nome_cmsp,
            "nome_civil": t.nome if t is not None else "", "genero": t.genero if t is not None else "",
            "eleito": "" if t is None else ("suplente" if t.situacao == "SUPLENTE" else "eleito"),
            "partido": partidos.get(cod) or (t.partido if t is not None else ""),
            "pagina": c.get("pagina", ""), "foto": c.get("foto", ""),
        })
    df = pd.DataFrame(linhas)
    df.to_csv(arq, index=False)
    sem = df[df.genero == ""].nome_cmsp.tolist()
    if sem:
        log(f"  Vereadores SP sem correspondência no TSE: {', '.join(sem)}")
    return df


def fotos(ver):
    """site/fotos/ver-3550308-{codigo}.webp (240×320), só as que faltam."""
    FOTOS.mkdir(parents=True, exist_ok=True)
    novas = 0
    for r in ver.itertuples():
        destino = FOTOS / f"ver-{COD_IBGE}-{r.codigo}.webp"
        if destino.exists() or not r.foto:
            continue
        try:
            destino.write_bytes(_ajustar(baixar(r.foto, timeout=60).content))
            novas += 1
        except TempoEsgotado:
            raise
        except Exception as e:  # sem foto o site mostra as iniciais
            log(f"  Foto de {r.nome}: {e}")
    if novas:
        log(f"  {novas} fotos novas de vereadores de SP")


# ---------------------------------------------------------------- SisGV: gastos e créditos do gabinete
def _sisgv(op, ano, mes):
    arq = C / f"{op}_{ano}{mes:02d}.json"
    recente = (ano, mes) > _menos_meses(ultimo_mes(), REBAIXAR_MESES)
    if arq.exists() and not (recente and not cache_valido(arq, 5)):
        return json.loads(arq.read_text(encoding="utf-8"))
    verificar_prazo()
    corpo = ('<?xml version="1.0" encoding="utf-8"?><soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
             'xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>'
             f'<{op} xmlns="{SISGV_NS}"><ano>{ano}</ano><mes>{mes}</mes></{op}></soap:Body></soap:Envelope>')
    for tentativa in range(4):
        try:
            r = _sessao().post(SISGV, data=corpo.encode("utf-8"), timeout=120,
                               headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": f'"{SISGV_NS}/{op}"'})
            r.raise_for_status()
            dados = _json_do_ws(r.text)
            break
        except Exception:
            if tentativa == 3:
                raise
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    time.sleep(1)  # um pedido por vez, com pausa: o serviço é da Câmara
    return dados


def _menos_meses(am, n):
    a, m = am
    for _ in range(n):
        a, m = (a - 1, 12) if m == 1 else (a, m - 1)
    return a, m


def _mascarar(doc):
    """CPF de pessoa física (aluguel de imóvel) fica mascarado, como no Portal da Transparência."""
    d = re.sub(r"\D", "", doc or "")
    return f"***.{d[3:6]}.{d[6:9]}-**" if len(d) == 11 else (doc or "").strip()


def gastos(ate):
    """Notas do auxílio-encargos (débitos) e créditos mensais de cada vereador, de jan/2025 até o último mês fechado."""
    desp, verba = [], []
    for ano, mes in _meses(ate):
        for x in _sisgv("ObterDebitoVereadorJSON", ano, mes):
            desp.append({"ano": ano, "mes": mes, "vereador": x["VEREADOR"].strip(), "despesa": (x.get("DESPESA") or "").strip(),
                         "cnpj_cpf": _mascarar(x.get("CNPJ")), "fornecedor": re.sub(r"\s+", " ", x.get("FORNECEDOR") or "").strip(),
                         "valor": round(float(x.get("VALOR") or 0), 2)})
        for x in _sisgv("ObterCreditoVereadorJSON", ano, mes):
            verba.append({"ano": ano, "mes": mes, "vereador": x["VEREADOR"].strip(),
                          "movimento": "credito" if x.get("TPMOVIMENTOID") == 1 else "saldo_devolvido" if x.get("TPMOVIMENTOID") == 4 else str(x.get("TPMOVIMENTOID")),
                          "valor": round(float(x.get("VALOR") or 0), 2)})
    d = pd.DataFrame(desp)
    v = pd.DataFrame(verba)
    d.to_csv(PASTA / "despesas.csv", index=False)
    v.to_csv(PASTA / "verba.csv", index=False)
    log(f"Vereadores SP: {len(d)} notas de gastos do gabinete até {ate[1]:02d}/{ate[0]} ({d.valor.sum() / 1e6:.1f} milhões)")
    return d, v


# ---------------------------------------------------------------- funcionários por gabinete
def equipe():
    arq = C / "funcionarios.xml"
    if not cache_valido(arq, 6):
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_bytes(baixar(FUNCIONARIOS, timeout=120).content)
    raiz = ET.fromstring(arq.read_bytes())
    data = raiz.attrib.get("data", "")
    cont = Counter()
    for f in raiz:
        cc = (f.findtext("Centro_de_Custos") or "").strip()
        cargo = (f.findtext("Descricao_Cargo") or "").strip()
        m = re.match(r"(\d+)º GABINETE DE VEREADOR", cc)
        if m and not cargo.startswith("VEREADOR"):
            cont[(int(m.group(1)), cargo)] += 1
    df = pd.DataFrame([{"data": data, "gabinete": g, "cargo": c, "pessoas": n} for (g, c), n in sorted(cont.items())])
    df.to_csv(PASTA / "equipe.csv", index=False)
    return df


# ---------------------------------------------------------------- nomes curtos dos tipos de gasto
_TIPOS = [
    (r"CONTE[UÚ]DO DIGITAL|REDES SOCIAIS", "Conteúdo para internet e redes sociais"),
    (r"GRAFIC|DIAGRAMA", "Material gráfico (arte e impressão)"),
    (r"CONTRATA[CÇ][AÃ]O DE PESSOA JUR", "Serviços contratados de empresas"),
    (r"VE[IÍ]CULO|ONIX", "Aluguel de carros"),
    (r"COMBUST", "Combustível"),
    (r"M[OÓ]VEIS|EQUIPAMENTO", "Aluguel de móveis e equipamentos"),
    (r"SITE|HOSPEDAGEM", "Site (criação e hospedagem)"),
    (r"MATERIA(L|IS) DE ESCRIT|CONSUMO", "Material de escritório"),
    (r"IM[OÓ]VEL", "Escritório (aluguel e contas)"),
    (r"CORREIO", "Correios"),
    (r"REPROGRAFIA|XEROX", "Cópias e encadernação"),
    (r"EVENTO|SEMIN", "Eventos e seminários"),
    (r"TELEFONE|INTERNET", "Telefone e internet"),
    (r"APERFEI", "Cursos"),
    (r"JORNA|REVISTA|LIVRO", "Assinaturas e livros"),
    (r"ESTACIONAMENTO|APLICATIVO|LIMPEZA DE VE|T[AÁ]XI", "Aplicativo, táxi e estacionamento"),
]


def tipo_curto(despesa):
    for padrao, nome in _TIPOS:
        if re.search(padrao, despesa or "", re.I):
            return nome
    return _titulo(re.sub(r"\s*-\s*Inciso.*$", "", despesa or "Outros", flags=re.I)).strip() or "Outros"


_SIGLAS = {"ltda": "Ltda", "me": "ME", "epp": "EPP", "s/a": "S/A", "sa": "S/A", "s.a.": "S.A.", "eireli": "Eireli", "cmsp": "CMSP"}


def _cargo(cargo):
    """'ASSESSOR ESPECIAL DE GABINETE' -> 'Assessor especial de gabinete'."""
    if "CEDIDO" in cargo.upper():
        return "Servidor cedido por outro órgão"
    return cargo.capitalize()


def _empresa(nome):
    nome = re.sub(r"\s+", " ", nome or "").strip(" .-")
    return " ".join(_SIGLAS.get(w.lower(), w.lower() if w.lower() in _MINUSCULAS and i else w.capitalize()) for i, w in enumerate(nome.split())) or "Sem nome"


# ---------------------------------------------------------------- site/dados/camaras.json
def _subsidio(ano, mes):
    valor = 0
    for (a, m), v in SUBSIDIO:
        if (ano, mes) >= (a, m):
            valor = v
    return valor


def _dias(ocup, ano, mes):
    """Dias no cargo naquele mês, somando as ocupações do gabinete (inclusive nas pontas)."""
    ini_mes, fim_mes = date(ano, mes, 1), date(ano, mes, monthrange(ano, mes)[1])
    total = 0
    for ini, fim in ocup:
        a, b = max(ini, ini_mes), min(fim or date(9999, 1, 1), fim_mes)
        if b >= a:
            total += (b - a).days + 1
    return min(total, monthrange(ano, mes)[1])


def _r(v):
    return int(round(v))


def site(gab, ver, desp, verba, eq, ate):
    tipos, idx = [], {}

    def tipo(nome):
        if nome not in idx:
            idx[nome] = len(tipos)
            tipos.append(nome)
        return idx[nome]

    meses = list(_meses(ate))
    anos = sorted({a for a, _ in meses})
    desp = desp[[(a, m) <= ate for a, m in zip(desp.ano, desp.mes)]].copy()
    desp["tipo"] = desp.despesa.map(tipo_curto)
    desp["aaaamm"] = desp.ano * 100 + desp.mes
    verba = verba[[(a, m) <= ate for a, m in zip(verba.ano, verba.mes)]]
    data_eq = eq.data.iloc[0] if len(eq) else ""
    pessoas_gab = eq.groupby("gabinete").pessoas.sum().to_dict() if len(eq) else {}
    cargos_gab = {g: [[_cargo(c), int(n)] for c, n in sorted(zip(gg.cargo, gg.pessoas), key=lambda x: (-x[1], x[0]))] for g, gg in eq.groupby("gabinete")} if len(eq) else {}
    info = {r.codigo: r for r in ver.itertuples()}
    pessoas = []
    for cod, g in gab.groupby("codigo"):
        r = info.get(cod)
        if r is None:
            continue
        ocup = [(date.fromisoformat(i), date.fromisoformat(f) if f else None) for i, f in zip(g.inicio, g.fim.fillna(""))]
        no_cargo = any(f is None or f >= HOJE for _, f in ocup)
        gab_atual = int(g.sort_values("inicio").gabinete.iloc[-1])
        dias_total = sum(_dias(ocup, a, m) for a, m in meses)
        if dias_total < 15 and not no_cargo:
            continue  # assumiu só por poucos dias (para uma votação, por exemplo): fica fora da lista
        d = desp[desp.vereador == r.nome_cmsp]
        vb = verba[verba.vereador == r.nome_cmsp]
        serie = []
        for a, m in meses:
            dias = _dias(ocup, a, m)
            ganha = _subsidio(a, m) * dias / monthrange(a, m)[1]
            custa = d[(d.ano == a) & (d.mes == m)].valor.sum()
            if dias or abs(custa) >= 0.5:
                serie.append((a * 100 + m, ganha, custa, dias))
        if not serie:
            continue

        def bloco(filtro):
            s = [x for x in serie if filtro(x[0])]
            if not s:
                return None
            m = sum(1 for x in s if x[3])
            mc = sum(1 for x in s if x[3] or abs(x[2]) >= 0.5)
            g_, c_ = sum(x[1] for x in s), sum(x[2] for x in s)
            cats = {k: _r(v) for k, v in (("salario", g_), ("verba_gabinete", c_)) if _r(v)}
            return {"m": m, "mg": m, "mc": mc, "me": 0, "g": _r(g_), "c": _r(c_), "e": 0, "pm": 0, "mp": 0, "pu": 0, "ep": 0, "cats": cats}

        def detalhe(filtro):
            dd = d[[filtro(x) for x in d.aaaamm]]
            if not len(dd):
                return None
            por_tipo = dd.groupby("tipo").valor.sum().sort_values(ascending=False)
            forn = dd.assign(chave=[re.sub(r"\D", "", c) or f"?{f}" for c, f in zip(dd.cnpj_cpf.fillna(""), dd.fornecedor)])
            nomes = {}
            for ch, gg in forn.groupby("chave"):
                pf = gg.cnpj_cpf.iloc[0].startswith("***")
                nomes[ch] = "Pessoa física (aluguel de imóvel)" if pf else _empresa(gg.fornecedor.mode().iloc[0])
            por_forn = forn.assign(nome=forn.chave.map(nomes)).groupby("nome").valor.sum().sort_values(ascending=False)
            return {"verba_gabinete": [[tipo(t), _r(v)] for t, v in por_tipo.items() if _r(v) > 0][:8],
                    "fornecedores": [[tipo(t), _r(v)] for t, v in por_forn.items() if _r(v) > 0][:8]}

        filtros = {str(a): (lambda x, a=a: x // 100 == a) for a in anos}
        filtros["leg"] = lambda x: True
        per, dt = {}, {}
        for k, f in filtros.items():
            b = bloco(f)
            if b:
                per[k] = b
                det = detalhe(f)
                if det:
                    dt[k] = det
        credito = {str(a): _r(vb[(vb.ano == a) & (vb.movimento == "credito")].valor.sum()) for a in anos}
        devolvido = {str(a): _r(-vb[(vb.ano == a) & (vb.movimento == "saldo_devolvido")].valor.sum()) for a in anos}
        n_eq = int(pessoas_gab.get(gab_atual, 0)) if no_cargo else 0
        pessoas.append({
            "id": f"ver-{COD_IBGE}-{cod}", "k": "v", "cid": COD_IBGE, "n": r.nome, "nc": r.nome_civil or r.nome_cmsp,
            "g": "Vereadora" if r.genero == "F" else "Vereador", "pt": r.partido, "uf": "SP",
            "f": f"fotos/ver-{COD_IBGE}-{cod}.webp" if (FOTOS / f"ver-{COD_IBGE}-{cod}.webp").exists() else None,
            "fc": {"a": "Câmara Municipal de São Paulo", "u": r.pagina or f"{SITE_CMSP}/vereadores/membros/"} if (FOTOS / f"ver-{COD_IBGE}-{cod}.webp").exists() else None,
            "x": 1 if no_cargo else 0, "o": r.pagina or CONTAS, "gab": gab_atual, "sup": 1 if r.eleito == "suplente" else 0,
            "oc": [[i.strftime("%Y%m%d"), f.strftime("%Y%m%d") if f else None] for i, f in sorted(ocup)],
            "per": per,
            "t": [[am, _r(gg), _r(cc), 0, 0, 0] for am, gg, cc, _ in serie],
            "dt": dt,
            "vb": {a: [credito[a], devolvido[a]] for a in credito if credito[a] or devolvido[a]},
            "eq": {"n": n_eq, "c": cargos_gab.get(gab_atual, [])} if n_eq else None,
        })
    pessoas.sort(key=lambda p: normalizar_nome(p["n"]))
    dados = {
        "meta": {
            "gerado_em": datetime.now().isoformat(timespec="seconds"),
            "tipos": tipos,
            "categorias": {"verba_gabinete": {"grupo": "custa", "nome": "Verba do gabinete (auxílio-encargos)"}},
            "cidades": {str(COD_IBGE): {
                "n": "São Paulo", "uf": "SP", "casa": "Câmara Municipal de São Paulo", "vagas": int(gab.gabinete.nunique()),
                "inicio": INICIO[0] * 100 + INICIO[1], "ultimo_mes": ate[0] * 100 + ate[1], "anos": [str(a) for a in anos],
                "subsidio": [[a * 100 + m, v] for (a, m), v in SUBSIDIO],
                "verba_mes": {str(a): round(float(verba[(verba.ano == a) & (verba.movimento == "credito")].groupby("vereador").valor.sum().max() / sum(1 for x in meses if x[0] == a)), 2) for a in anos},
                "equipe_em": data_eq,
                "fontes": {"gastos": CONTAS, "gabinetes": f"{SPLEGIS}/OcupacaoGabineteJSON", "funcionarios": FUNCIONARIOS,
                           "verba": f"{SITE_CMSP}/transparencia/custos-de-mandato/",
                           "subsidio": "https://www.gazetasp.com.br/politica/vereadores-de-sao-paulo-aprovam-reajuste-salarial-para-mais-de-r-26/1146396"},
            }},
        },
        "p": pessoas,
    }
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log(f"Site: {SAIDA.relative_to(RAIZ)} ({SAIDA.stat().st_size / 1e3:.0f} KB, {len(pessoas)} vereadores de SP, {sum(p['x'] for p in pessoas)} no cargo)")
    return dados


def conferir(dados):
    """Alertas simples: quantos no cargo, e se a verba usada cabe no limite do ano."""
    alertas = []
    ps = dados["p"]
    no_cargo = sum(p["x"] for p in ps)
    if no_cargo != 55:
        alertas.append(f"Vereadores de SP no cargo: {no_cargo} (esperado 55)")
    sem_foto = [p["n"] for p in ps if p["x"] and not p["f"]]
    if sem_foto:
        alertas.append(f"Vereadores de SP sem foto: {', '.join(sem_foto)}")
    for p in ps:
        for ano, (cred, _) in p["vb"].items():
            usado = p["per"].get(ano, {}).get("c", 0)
            if cred and usado > cred * 1.02:
                alertas.append(f"{p['n']}: gastou {usado} em {ano}, acima do crédito de {cred}")
    for a in alertas:
        log("  ALERTA", a)
    return alertas


def coletar():
    ate = ultimo_mes()
    gab = gabinetes()
    ver = vereadores(gab)
    fotos(ver)
    desp, verba = gastos(ate)
    eq = equipe()
    dados = site(gab, ver, desp, verba, eq, ate)
    conferir(dados)


def executar_site():
    """Só remonta site/dados/camaras.json com o que já está em dados/municipios/sp/ (sem baixar nada)."""
    if not (PASTA / "gabinetes.csv").exists():
        return
    ate = ultimo_mes()
    gab = pd.read_csv(PASTA / "gabinetes.csv", dtype={"fim": str}).fillna({"fim": ""})
    ver = pd.read_csv(PASTA / "vereadores.csv").fillna("")
    desp = pd.read_csv(PASTA / "despesas.csv", dtype={"cnpj_cpf": str}).fillna({"cnpj_cpf": "", "fornecedor": "", "despesa": ""})
    verba = pd.read_csv(PASTA / "verba.csv")
    eq = pd.read_csv(PASTA / "equipe.csv", dtype={"data": str}) if (PASTA / "equipe.csv").exists() else pd.DataFrame(columns=["data", "gabinete", "cargo", "pessoas"])
    site(gab, ver, desp, verba, eq, ate)
