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
from collections import Counter

import pandas as pd

from ..config import CACHE, DADOS, HOJE, RAIZ
from ..fotos import _ajustar
from ..util import TempoEsgotado, _sessao, baixar, cache_valido, gravar_csv, log, normalizar_nome, verificar_prazo

COD_IBGE = 3550308
LEGISLATURA = 19               # 2025–2028
INICIO = (2025, 1)
SUBSIDIO = [((2025, 1), 24754.79), ((2025, 2), 26080.98)]  # (a partir de, valor mensal): Resolução nº 10/2024, art. 1º
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
    gravar_csv(df, PASTA / "gabinetes.csv")
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
    gravar_csv(df, arq)
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
    gravar_csv(df, arq)
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
    """Só o CNPJ fica; o CPF de pessoa física (aluguel de imóvel) não é guardado, nem mascarado (ver comum.mascarar)."""
    from .comum import mascarar
    return mascarar(doc)


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
    gravar_csv(d, PASTA / "despesas.csv")
    gravar_csv(v, PASTA / "verba.csv")
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
    gravar_csv(df, PASTA / "equipe.csv")
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


# ---------------------------------------------------------------- tabelas no formato comum
CFG = {
    "cod": COD_IBGE, "n": "São Paulo", "uf": "SP", "casa": "Câmara Municipal de São Paulo", "vagas": 55,
    "inicio": INICIO[0] * 100 + INICIO[1], "subsidio": [[a * 100 + m, v] for (a, m), v in SUBSIDIO],
    "verba_nome": "Auxílio-Encargos Gerais de Gabinete",
    "verba_regra": "O que não é usado num mês fica para os meses seguintes; o que sobra no fim do ano volta para a Câmara.",
    "verba_notas": ["Carros, correios e cópias podem vir de contratos da própria Câmara, descontados da verba do vereador."],
    "salario_nota": "A Câmara só mostra o contracheque de cada um para quem informa um CPF, por isso descontos, 13º e outros pagamentos não aparecem aqui.",
    "equipe_nota": "Cargos de confiança, escolhidos pelo vereador. A Câmara só mostra os salários para quem informa um CPF.",
    "credito_foto": "Câmara Municipal de São Paulo", "pagina": f"{SITE_CMSP}/vereadores/membros/",
    "fontes": {"gastos": CONTAS, "gabinetes": f"{SPLEGIS}/OcupacaoGabineteJSON", "funcionarios": FUNCIONARIOS,
               "verba": f"{SITE_CMSP}/transparencia/custos-de-mandato/",
               "subsidio": "https://saopaulo.sp.leg.br/iah/fulltext/resolucoescmsp/RC1024.pdf"},
}


def vigencias(por_mes):
    """{AAAAMM: valor} -> [[desde AAAAMM, valor]]: os meses seguidos com o mesmo valor juntos; uma mudança de um mês só
    (no último mês, ou entre dois meses com o mesmo valor) é crédito parcial e fica com o valor de antes."""
    meses = sorted(por_mes)
    trechos = []
    for am in meses:
        if trechos and abs(trechos[-1][2] - por_mes[am]) < 0.01:
            trechos[-1][1] = am
        else:
            trechos.append([am, am, por_mes[am]])
    limpos = []
    for i, t in enumerate(trechos):
        um_mes = t[0] == t[1]
        ultimo = i == len(trechos) - 1
        entre_iguais = 0 < i < len(trechos) - 1 and abs(trechos[i - 1][2] - trechos[i + 1][2]) < 0.01
        if limpos and um_mes and (ultimo or entre_iguais):
            continue
        if limpos and abs(limpos[-1][1] - t[2]) < 0.01:
            continue
        limpos.append([t[0], round(t[2], 2)])
    return limpos


def valor_por_ano(vigencia, anos):
    """{ano: o valor em vigor no último mês do ano que está na vigência (ou no começo do ano seguinte)}."""
    saida = {}
    for a in anos:
        em_vigor = [v for desde, v in vigencia if desde <= a * 100 + 12]
        if em_vigor:
            saida[a] = em_vigor[-1]
    return saida


def montar(tipos):
    """Lê o que está em dados/municipios/sp/ e devolve (meta, pessoas) pelo formato comum."""
    from . import comum
    if not (PASTA / "gabinetes.csv").exists():
        return None
    ate = comum.ultimo_mes_fechado()
    gab = pd.read_csv(PASTA / "gabinetes.csv", dtype={"fim": str}).fillna({"fim": ""})
    ver = pd.read_csv(PASTA / "vereadores.csv").fillna("")
    desp = pd.read_csv(PASTA / "despesas.csv", dtype={"cnpj_cpf": str}).fillna({"cnpj_cpf": "", "fornecedor": "", "despesa": ""})
    verba = pd.read_csv(PASTA / "verba.csv")
    eq = pd.read_csv(PASTA / "equipe.csv", dtype={"data": str}) if (PASTA / "equipe.csv").exists() else pd.DataFrame(columns=["data", "gabinete", "cargo", "pessoas"])
    codigo_de = {normalizar_nome(n): int(c) for c, n in zip(gab.codigo, gab.vereador)}
    desp = desp.assign(codigo=desp.vereador.map(lambda n: codigo_de.get(normalizar_nome(n))), tipo=desp.despesa.map(comum.tipo_curto))
    desp = desp[desp.codigo.notna()].astype({"codigo": int})
    verba = verba.assign(codigo=verba.vereador.map(lambda n: codigo_de.get(normalizar_nome(n))))
    verba = verba[verba.codigo.notna()]
    anual = verba.assign(credito=verba.valor.where(verba.movimento == "credito", 0), devolvido=-verba.valor.where(verba.movimento == "saldo_devolvido", 0))
    anual = anual[anual.ano * 100 + anual.mes <= ate].groupby(["ano", "codigo"])[["credito", "devolvido"]].sum().reset_index()
    # equipe: retrato do mês mais recente, pelo número do gabinete -> quem ocupa hoje
    atuais = gab[gab.fim == ""].groupby("gabinete").codigo.last().to_dict()
    cargos = pd.DataFrame([{"codigo": atuais[g], "cargo": _cargo(c), "pessoas": int(n)} for g, c, n in zip(eq.gabinete, eq.cargo, eq.pessoas) if g in atuais])
    cfg = dict(CFG, ultimo_mes=ate, equipe_em=eq.data.iloc[0] if len(eq) else "")
    # o limite da verba por mês, por vigência: o crédito mais comum entre os vereadores em cada mês (não a média do ano,
    # que cai quando o último mês ainda está creditado só em parte, nem o mais comum do ano, que esconde um reajuste no
    # meio do ano). Uma mudança que dura um mês só, no último mês ou entre dois meses iguais, é crédito parcial e não
    # conta. verba_vigencia: [[desde AAAAMM, valor]]; verba_mes: o valor em vigor no último mês de cada ano
    creditos = verba[(verba.movimento == "credito") & (verba.valor > 0) & (verba.ano * 100 + verba.mes <= ate)]
    cfg["verba_vigencia"] = vigencias({int(a) * 100 + int(m): float(g.valor.round(2).mode().max())
                                       for (a, m), g in creditos.groupby(["ano", "mes"])})
    cfg["verba_mes"] = {str(a): v for a, v in valor_por_ano(cfg["verba_vigencia"], sorted({int(a) for a in creditos.ano})).items()}
    ver2 = pd.DataFrame({"codigo": ver.codigo, "nome": ver.nome, "nome_civil": ver.nome_civil.where(ver.nome_civil != "", ver.nome_cmsp),
                         "partido": ver.partido, "genero": ver.genero, "eleito": ver.eleito, "pagina": ver.pagina})
    mand = pd.DataFrame({"codigo": gab.codigo, "inicio": gab.inicio, "fim": gab.fim, "gabinete": gab.gabinete})
    return comum.montar(cfg, tipos, ver2, mand, despesas=desp[["ano", "mes", "codigo", "tipo", "fornecedor", "cnpj_cpf", "valor"]],
                        verba=anual, cargos=cargos if len(cargos) else None)


def coletar():
    ate = ultimo_mes()
    gab = gabinetes()
    ver = vereadores(gab)
    fotos(ver)
    gastos(ate)
    equipe()
