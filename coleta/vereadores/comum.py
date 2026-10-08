"""Parte comum dos robôs de vereador por vereador (uma cidade por arquivo nesta pasta).

Cada cidade entrega as mesmas tabelas (pandas) para `montar()`, que devolve os registros do site no mesmo
formato dos deputados: contracheque, mês a mês, detalhe da verba, equipe. `escrever()` junta todas as cidades
em site/dados/camaras.json.

Tabelas de entrada (só `ver` e `mandatos` são obrigatórias):
- ver:       codigo, nome, nome_civil, partido, genero (M/F), eleito ("eleito"/"suplente"/""), pagina
- mandatos:  codigo, inicio (AAAA-MM-DD), fim (AAAA-MM-DD ou vazio) e, se houver, gabinete — períodos no cargo
- ganha:     ano, mes, codigo, categoria (salario, decimo_terceiro, auxilios, outros_rendimentos...), valor
             — quando a Câmara publica a folha dos vereadores. Sem ela, usa o subsídio de cfg["subsidio"]
             proporcional aos dias no cargo.
- despesas:  ano, mes, codigo, tipo (nome curto), fornecedor, cnpj_cpf, valor — a verba do gabinete, nota a nota
             (ou por categoria, com fornecedor vazio)
- verba:     ano, codigo, credito, devolvido — o limite (crédito) do ano e o que sobrou e voltou para a Câmara
- equipe:    ano, mes, codigo, pessoas, custo (vazio se não publicado) — equipe do gabinete mês a mês
- cargos:    codigo, cargo, pessoas — retrato mais recente dos cargos de cada gabinete
"""
import json
import re
from calendar import monthrange
from datetime import date, datetime

import pandas as pd

from ..config import HOJE, RAIZ
from ..util import TempoEsgotado, baixar, gravar_json, gravar_linhas, log, normalizar_nome

FOTOS = RAIZ / "site" / "fotos"
SAIDA = RAIZ / "site" / "dados" / "camaras.json"
CATEGORIA_VERBA = {"verba_gabinete": {"grupo": "custa", "nome": "Verba do gabinete"}}


# ---------------------------------------------------------------- datas
def hoje_iso():
    return HOJE.isoformat()


def ultimo_mes_fechado():
    return HOJE.year * 100 + HOJE.month - 1 if HOJE.month > 1 else (HOJE.year - 1) * 100 + 12


def meses(inicio, ate):
    """[(ano, mes), ...] de inicio (AAAAMM) até ate (AAAAMM)."""
    a, m = divmod(inicio, 100)
    saida = []
    while a * 100 + m <= ate:
        saida.append((a, m))
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    return saida


def mes_seguinte(aaaamm):
    a, m = divmod(aaaamm, 100)
    return (a + 1) * 100 + 1 if m == 12 else aaaamm + 1


def periodos_de_meses(meses_ativos, ultimo, aberto=True):
    """Meses (AAAAMM) em que a pessoa estava no cargo -> períodos [(inicio, fim)] em texto AAAA-MM-DD.
    Se o último período chega ao `ultimo` mês com dados e `aberto`, fica sem fim (ainda no cargo)."""
    ms = sorted(set(int(x) for x in meses_ativos))
    corridas = []
    for am in ms:
        if corridas and mes_seguinte(corridas[-1][1]) == am:
            corridas[-1][1] = am
        else:
            corridas.append([am, am])
    saida = []
    for de, ate in corridas:
        a1, m1 = divmod(de, 100)
        a2, m2 = divmod(ate, 100)
        fim = "" if (aberto and ate == ultimo) else f"{a2}-{m2:02d}-{monthrange(a2, m2)[1]:02d}"
        saida.append((f"{a1}-{m1:02d}-01", fim))
    return saida


def menos_meses(aaaamm, n):
    a, m = divmod(aaaamm, 100)
    for _ in range(n):
        a, m = (a - 1, 12) if m == 1 else (a, m - 1)
    return a * 100 + m


def dias_no_mes(periodos, ano, mes):
    """Dias no cargo naquele mês, somando os períodos [(inicio, fim ou None), ...] (inclusive nas pontas)."""
    ini_mes, fim_mes = date(ano, mes, 1), date(ano, mes, monthrange(ano, mes)[1])
    total = 0
    for ini, fim in periodos:
        a, b = max(ini, ini_mes), min(fim or date(9999, 1, 1), fim_mes)
        if b >= a:
            total += (b - a).days + 1
    return min(total, monthrange(ano, mes)[1])


# ---------------------------------------------------------------- textos
_MINUSCULAS = {"da", "de", "do", "das", "dos", "e"}
_SIGLAS = {"ltda": "Ltda", "me": "ME", "epp": "EPP", "s/a": "S/A", "sa": "S/A", "s.a.": "S.A.", "eireli": "Eireli", "mei": "MEI"}


def titulo(nome):
    return " ".join(w.lower() if w.lower() in _MINUSCULAS and i else w.capitalize() for i, w in enumerate((nome or "").lower().split()))


# CPF solto num texto: o MEI tem como razão social "NOME 12345678901" (ou "NOME -12345678901", "NOME/123.456.789-01",
# "2/12345678901", "123456789/01"), e algumas fontes põem o CPF no nome do fornecedor, no histórico do pagamento ou no
# número do documento. O número sai (regra do projeto: CPF de pessoa física, nunca). Antes e depois do número pode haver
# hífen, barra (também depois: "123.456.789-01/2026"), ponto, parêntese ou letra; só não pode haver outro algarismo
# colado (nem ponto ou hífen seguido de algarismo), para não pegar um pedaço de CNPJ. Separado por espaços ou
# tabulações, um ou mais ("123 456 789 01", "123  456  789  01"), só com os dígitos verificadores certos (três ou quatro
# números soltos num texto podem ser outra coisa).
_CPF_NO_TEXTO = re.compile(r"(?<!\d)(?<!\d[.-])(?:\d{3}\.?\d{3}\.?\d{3}[-/]?\d{2}"
                           r"|(?<!\d[ \t])\d{3}[ \t]+\d{3}[ \t]+\d{3}(?:[ \t]*-[ \t]*|[ \t]+)?\d{2}(?![ \t]+\d))(?!\d)(?![.-]\d)")
_COLUNAS_TEXTO = re.compile(r"fornec|benefic|nome|emitente|credor|favorec|objeto|descri|histor|interessad|detalh", re.I)
_COLUNAS_NOME = re.compile(r"fornec|benefic|emitente|credor|favorec|prestador", re.I)
# número do documento (nota, recibo, boleto): aqui sai só o número que é um CPF válido (os dígitos verificadores batem),
# para não apagar números de nota comuns; com o rótulo ("CPF:") junto
_COLUNAS_DOC = re.compile(r"document|^numero$|^num_|^nota$|^nf$|recibo|fatura", re.I)
_ROTULO_CPF = re.compile(r"\bC\.?P\.?F\.?\s*(n[ºo°.]*)?\s*[:.-]?\s*$", re.I)


def cpf_valido(numero):
    d = re.sub(r"\D", "", numero or "")
    if len(d) != 11 or len(set(d)) == 1:
        return False
    for n in (9, 10):
        if (sum(int(d[i]) * (n + 1 - i) for i in range(n)) * 10) % 11 % 10 != int(d[n]):
            return False
    return True


def sem_cpf(texto, so_validos=False):
    """O texto sem nenhum número com cara de CPF (com ou sem pontos). so_validos: só os que têm os dígitos
    verificadores de um CPF (para números de documento, que podem ter 11 algarismos sem ser CPF)."""
    if not isinstance(texto, str) or not _CPF_NO_TEXTO.search(texto):
        return texto

    def trocar(m):
        if (so_validos or re.search(r"[ \t]", m.group(0))) and not cpf_valido(m.group(0)):
            return m.group(0)
        return " "
    partes, fim, tirou = [], 0, False
    for m in _CPF_NO_TEXTO.finditer(texto):
        novo = trocar(m)
        antes = texto[fim:m.start()]
        if novo == " ":
            antes = _ROTULO_CPF.sub("", antes)
            tirou = True
        partes += [antes, novo]
        fim = m.end()
    if not tirou:
        return texto  # nada saiu: o texto fica como veio
    partes.append(texto[fim:])
    return re.sub(r"\s+", " ", "".join(partes)).replace("( )", "").replace("()", "").strip(" -–:/")


def limpar_cpfs(pasta):
    """Tira o CPF dos textos livres (fornecedor, nome, histórico...) e, quando os dígitos verificadores batem, do número
    do documento, em todos os CSVs de uma pasta de dados. Roda depois de cada coleta (coleta/vereadores/__init__.py e
    coleta/assembleias/__init__.py). Devolve quantas células mudaram."""
    import csv
    from pathlib import Path
    csv.field_size_limit(10**9)
    total = 0
    for arq in sorted(Path(pasta).glob("*.csv")):
        with open(arq, encoding="utf-8", newline="") as f:
            linhas = list(csv.reader(f))
        if not linhas:
            continue
        cols = [j for j, h in enumerate(linhas[0]) if _COLUNAS_TEXTO.search(h)]
        nomes = [j for j, h in enumerate(linhas[0]) if _COLUNAS_NOME.search(h)]
        docs = [j for j, h in enumerate(linhas[0]) if _COLUNAS_DOC.search(h) and j not in cols]
        cnpj = next((j for j, h in enumerate(linhas[0]) if re.search(r"cnpj", h, re.I)), None)
        mudou = 0
        for linha in linhas[1:]:
            # no número do documento, sai todo número de 11 algarismos com os dígitos verificadores de um CPF, mesmo na
            # nota de uma empresa (privacidade primeiro: o número de uma nota pode bater por acaso e sair junto; decisão
            # do Jean-François, 04/10/2026, README "CPF")
            empresa_na_linha = cnpj is not None and cnpj < len(linha) and len(re.sub(r"\D", "", linha[cnpj])) == 14
            for j in cols + docs:
                if j >= len(linha) or not _CPF_NO_TEXTO.search(linha[j]):
                    continue
                novo = sem_cpf(linha[j], so_validos=j in docs)
                if novo != linha[j]:
                    linha[j] = novo
                    mudou += 1
            # no nome do fornecedor, também o começo de um CPF (9 algarismos) ou o CPF sem o zero da frente (sem_cpf_curto)
            for j in nomes:
                if j < len(linha):
                    novo = sem_cpf_curto(linha[j])
                    if novo != linha[j]:
                        linha[j] = novo
                        mudou += 1
            # documento de pessoa física com um algarismo a mais (o CPF digitado com erro): 12 algarismos em que os 11
            # primeiros ou os 11 últimos formam um CPF válido
            if not empresa_na_linha:
                for j in docs:
                    if j < len(linha):
                        d = re.sub(r"\D", "", linha[j])
                        if len(d) == 12 and re.fullmatch(r"[\d.\-/ ]+", linha[j]) and (cpf_valido(d[:11]) or cpf_valido(d[1:])):
                            linha[j] = ""
                            mudou += 1
        if mudou and gravar_linhas(arq, None, linhas, dicionarios=False, lineterminator="\n"):
            total += mudou
    return total


# Número de 9 ou 10 algarismos solto num nome: o começo de um CPF (os 9 primeiros algarismos já dão os 2 últimos) ou o
# CPF sem o zero da frente (10 algarismos). Sai do nome (sem algarismo nem separador de número colado).
_CPF_CURTO = re.compile(r"(?<![\d.\-/])(\d{9,10})(?![\d])(?![.\-/]\d)")


def sem_cpf_curto(texto):
    """O nome sem um número que seja o começo de um CPF (9 algarismos) ou um CPF sem o zero da frente (10 algarismos com
    os dígitos verificadores certos)."""
    if not isinstance(texto, str) or not _CPF_CURTO.search(texto):
        return texto

    def trocar(m):
        n = m.group(1)
        return " " if len(n) == 9 or cpf_valido(n.zfill(11)) else n
    novo = _CPF_CURTO.sub(trocar, texto)
    return re.sub(r"\s+", " ", novo).strip(" -–:/") if novo != texto else texto


# Fornecedor sem CNPJ: só aparece pelo nome no site se o nome é de empresa (LTDA, S/A, posto, hotel, prefeitura...) ou
# traz um CNPJ; senão, "Pessoa física" (regra do projeto: o nome de fornecedor pessoa física não aparece no site).
_EMPRESA = re.compile(
    r"\b(LTDA|LTD|ME|EPP|EIRELI|EIRELE|EIRELLI|S\s?/\s?A|S\.\s?A\.?|S/S|INC|LLC|CORP|CORPORATION|LIMITED|GMBH|PLC|CIA|COMPANHIA|"
    r"COMERCIO|COMERCIAL|COM|SERVICOS?|SERV|POSTOS?|AUTO|AUTOPECAS|HOTEL|HOTEIS|HOTELARIA|HOTELEIROS?|POUSADA|RESTAURANTE|"
    r"CHURRASCARIA|PIZZARIA|LANCHONETE|LANCHES|PADARIA|PANIFICADORA|FARMACIA|DROGARIA|SUPERMERCADOS?|MERCADO|MERCADINHO|"
    r"ATACADO|ATACADAO|DISTRIBUIDORA|DISTRIBUICAO|INDUSTRIA|IND|EMPREENDIMENTOS?|PARTICIPACOES|CONSULTORIA|ASSESSORIA|"
    r"CONTABILIDADE|CONTABIL|ADVOGADOS|ADVOCACIA|SOCIEDADE|ASSOCIACAO|INSTITUTO|FUNDACAO|COOPERATIVA|EDITORA|GRAFICA|"
    r"GRAFICOS|IMPRESSORA|JORNAL|JORNALISTICA|RADIO|RADIODIFUSAO|TV|TELEVISAO|COMUNICACAO|COMUNICACOES|PUBLICIDADE|"
    r"PUBLICIDADES|PROPAGANDA|MARKETING|AGENCIA|TURISMO|VIAGENS|LOCADORA|LOCACOES|LOCACAO|TRANSPORTES?|COMBUSTIVEIS?|"
    r"DERIVADOS|PETROLEO|TELECOM|TELECOMUNICACOES|TELEFONICA|BANCO|CORREIOS|EMPRESA|EMPRESARIAL|GRUPO|CLINICA|LABORATORIO|"
    r"IMOBILIARIA|IMOBILIARIOS|IMOVEIS|CONDOMINIO|EDIFICIO|SHOPPING|PREFEITURA|SECRETARIA|ASSEMBLEIA|GOVERNO|MUNICIPIO|"
    r"UNIVERSIDADE|FACULDADE|ESCOLA|COLEGIO|IGREJA|SINDICATO|FEDERACAO|CONFEDERACAO|CONSELHO|ENERGIA|ENERGISA|SANEAMENTO|"
    r"SAAE|ESGOTO|SOFTWARE|SYSTEMS|TECNOLOGIA|TECHNOLOGY|TECHNOLOGIES|INFORMATICA|SOLUCOES|PRODUCOES|PRODUTORA|EVENTOS|"
    r"FILMES|DIGITAL|MIDIA|MIDIAS|INTERNET|PROVEDOR|LOJAS?|MAGAZINE|CALCADOS|CONFECCOES|MOVEIS|MATERIAIS|CONSTRUCOES|"
    r"CONSTRUTORA|ENGENHARIA|GESTAO|NEGOCIOS|IMPORTADORA|ALIMENTOS|BEBIDAS|PAPELARIA|LIVRARIA|OTICA|ESTACIONAMENTOS?|"
    r"OFICINA|MECANICA|PNEUS|VEICULOS|AUTOMOVEIS|REPRESENTACOES|MAQUINAS|EQUIPAMENTOS|MONITORAMENTO|NOTICIAS|"
    r"CAMARA MUNICIPAL|ADOBE|GOOGLE|FACEBOOK|MICROSOFT|AMAZON|APPLE|ZOOM|STREAMYARD|TRELLO|FLICKR|HOSTINGER|STARLINK|UBER|"
    r"IFOOD|LATAM|GOL|AZUL|CLARO|VIVO|TIM|[A-Z]+NET|LIMITADA|CASAN|CELESC|SAMAE|SEMASA|COND|EDIF|CENTER|BUSINESS|COMPUTADORES|"
    r"CARTUCHOS|IMPRESSORAS|COPIA|FUNDACION|PROGRAM|ADMINISTRADORA|INVESTIMENTOS?|CANVA|CAPCUT|DROPBOX|SLACK|PEDAGIO|REVISTA|"
    r"TABELIAO|CARTORIO|RECICLADOS)\b|&|\.COM\b|LTDA\b|S\s?/\s?A\b|EIRELI|CONSULTORIA|COMUNICACAO|TECNOLOGIA")


# um CNPJ no meio do nome: escrito com pontos e barra ("10.528.028/0001 50") ou 12 a 15 algarismos seguidos (Alero)
_CNPJ_NO_NOME = re.compile(r"(?<!\d)(\d{2}\.\d{3}\.\d{3}\s?/\s?\d{4}|\d{12,15})(?!\d)")


def parece_empresa(nome):
    """O nome é de empresa (ou de órgão público), pelas palavras ou por um CNPJ no meio?"""
    n = normalizar_nome(nome or "")
    # "SA" no fim, sem "de" antes ("Habiteto SA", e não "Maria de Sá"), é sociedade anônima
    return bool(_EMPRESA.search(n) or _CNPJ_NO_NOME.search(n) or re.search(r"(?<!\bDE)(?<!\bDA)(?<!\bDO)\s+SA\.?$", n))


def fornecedor_pf(doc, nome):
    """True se o fornecedor é pessoa física (o site mostra "Pessoa física", não o nome):
    - o documento é um CPF: a marca "PF" de mascarar, o CPF mascarado de antes ("***...") ou 11 algarismos;
    - com CNPJ (12 a 15 algarismos: há fonte que perde o zero da frente ou junta um algarismo), não;
    - sem documento: pessoa física, a não ser que o nome seja de empresa (parece_empresa)."""
    c = str(doc or "").strip()
    d = re.sub(r"\D", "", c)
    if c.upper() == "PF" or c.startswith("***") or len(d) == 11 or ("*" in c and len(d) < 12):
        return True
    if len(d) >= 12 or "/" in c:
        return False
    return not parece_empresa(nome)


def empresa(nome):
    nome = re.sub(r"\s+", " ", sem_cpf_curto(sem_cpf(nome or ""))).strip(" .-")
    return " ".join(_SIGLAS.get(w.lower(), w.lower() if w.lower() in _MINUSCULAS and i else w.capitalize())
                    for i, w in enumerate(nome.split())) or "Sem nome"


PF = "PF"  # marca de fornecedor pessoa física no lugar do documento (sem nenhum algarismo do CPF)


def mascarar(doc):
    """Só o CNPJ (empresa) é guardado, como está; o CPF de quem é pessoa física não é guardado, nem mascarado (regra do
    projeto): no lugar dele fica a marca "PF" (para o site mostrar "Pessoa física" e não o nome). Um CPF que já chega
    mascarado da fonte também vira "PF", e num campo composto ("CPF: ... NF 1") só fica o CNPJ, se houver. Sem documento: ""."""
    t = (doc or "").strip()
    d = re.sub(r"\D", "", t)
    if len(d) == 11 or ("*" in t and len(d) != 14) or len(d) in (6, 7, 8, 9):
        return PF
    if _CPF_NO_TEXTO.search(t) or (re.search(r"\bC\.?P\.?F\b", t, re.I) and "CNPJ" not in t.upper()):
        resto = sem_cpf(t)
        return resto if len(re.sub(r"\D", "", resto)) == 14 else PF
    return t


# Nomes curtos dos tipos de gasto, iguais em todas as cidades (a ordem importa: o primeiro que bater vale)
_TIPOS = [
    (r"CONTE[UÚ]DO DIGITAL|REDES SOCIAIS|M[IÍ]DIAS? SOCIA|IMPULSION", "Conteúdo para internet e redes sociais"),
    (r"GR[AÁ]FIC|DIAGRAMA|IMPRESS", "Material gráfico (arte e impressão)"),
    (r"DIVULG|PUBLICIDADE|PROPAGANDA|MARKETING", "Divulgação do mandato"),
    (r"CONTRATA[CÇ][AÃ]O DE PESSOA JUR|SERVI[CÇ]OS? DE TERCEIROS|PRESTA[CÇ][AÃ]O DE SERVI", "Serviços contratados de empresas"),
    (r"CONSULT|ASSESS|PESQUISA|ADVOCACIA|ADVOGAD|SERVI[CÇ]OS? JUR[IÍ]DIC|CONT[AÁ]B", "Consultorias e assessorias"),
    (r"VE[IÍ]CULO|ONIX|LOCA[CÇ][AÃ]O DE (AUTO|CARRO)", "Aluguel de carros"),
    (r"COMBUST|GASOLINA|[OÓ]LEO DIESEL|ABASTEC", "Combustível"),
    (r"M[OÓ]VEIS|EQUIPAMENTO|INFORM[AÁ]TICA|COMPUTADOR", "Aluguel de móveis e equipamentos"),
    (r"\bSITE\b|HOSPEDAGEM DE SITE|SOFTWARE|SISTEMA", "Site e sistemas"),
    (r"MATERIA(L|IS) DE ESCRIT|MATERIAL DE CONSUMO|EXPEDIENTE|CONSUMO", "Material de escritório"),
    (r"IM[OÓ]VEL|ALUGUEL|ESCRIT[OÓ]RIO|CONDOM[IÍ]NIO|[AÁ]GUA|ENERGIA", "Escritório (aluguel e contas)"),
    (r"CORREIO|POSTA", "Correios"),
    (r"REPROGRAFIA|XEROX|C[OÓ]PIA", "Cópias e encadernação"),
    (r"EVENTO|SEMIN|CONGRESS|CURSO|APERFEI|CAPACITA", "Eventos, cursos e seminários"),
    (r"TELEFON|INTERNET|CELULAR|COMUNICA", "Telefone e internet"),
    (r"JORNA|REVISTA|LIVRO|ASSINATURA|PUBLICA[CÇ][OÕ]ES", "Assinaturas e livros"),
    (r"PASSAGE|A[EÉ]RE", "Passagens"),
    (r"HOSPEDAGEM|HOTEL|DI[AÁ]RIA", "Hospedagem e diárias"),
    (r"ALIMENTA|REFEI|LANCHE", "Alimentação"),
    (r"SEGURAN", "Segurança"),
    (r"ESTACIONAMENTO|APLICATIVO|LIMPEZA DE VE|T[AÁ]XI|PED[AÁ]GIO|LOCOMO", "Aplicativo, táxi e estacionamento"),
]


def tipo_curto(despesa):
    for padrao, nome in _TIPOS:
        if re.search(padrao, despesa or "", re.I):
            return nome
    t = re.sub(r"\s*-\s*Inciso.*$", "", despesa or "", flags=re.I).strip()
    return (t[:1].upper() + t[1:].lower()) if t else "Outros"


# ---------------------------------------------------------------- TSE (nome de urna, nome completo, partido e gênero)
TSE = "https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/consulta_cand_2024.zip"


def candidatos_tse(uf, municipio):
    """Eleitos e suplentes a vereador em 2024 numa cidade: sq (número do candidato no TSE), nome_urna, nome, partido,
    genero (M/F), situacao."""
    import csv
    import io
    import zipfile
    from ..config import CACHE
    from ..util import cache_valido
    zipado = CACHE / "municipios" / "consulta_cand_2024.zip"  # o mesmo arquivo do robô das câmaras (municipios.py)
    if not cache_valido(zipado, 60):
        log("Vereadores: arquivo de candidatos do TSE (~60 MB)")
        zipado.parent.mkdir(parents=True, exist_ok=True)
        zipado.write_bytes(baixar(TSE, timeout=600).content)
    alvo = normalizar_nome(municipio)
    linhas = []
    with zipfile.ZipFile(zipado) as z, z.open(f"consulta_cand_2024_{uf}.csv") as f:
        for l in csv.DictReader(io.TextIOWrapper(f, encoding="latin1"), delimiter=";"):
            if l["CD_CARGO"] == "13" and normalizar_nome(l["NM_UE"]) == alvo and l["DS_SIT_TOT_TURNO"] in ("ELEITO POR QP", "ELEITO POR MÉDIA", "SUPLENTE"):
                linhas.append({"sq": int(l["SQ_CANDIDATO"]), "nome_urna": l["NM_URNA_CANDIDATO"].strip(), "nome": l["NM_CANDIDATO"].strip(), "partido": l["SG_PARTIDO"],
                               "genero": l["DS_GENERO"][:1], "situacao": "suplente" if l["DS_SIT_TOT_TURNO"] == "SUPLENTE" else "eleito"})
    return pd.DataFrame(linhas)


def chave_nome(nome):
    """Para comparar nomes de fontes diferentes: sem acento, sem pontos e sem títulos (Dr., Prof....)."""
    t = normalizar_nome(nome).replace(".", " ").replace("-", " ")
    return " ".join(w for w in t.split() if w not in {"DR", "DRA", "PROF", "PROFA", "PROFESSOR", "PROFESSORA", "VER"})


_PARTICULAS = {"DE", "DA", "DO", "DAS", "DOS", "E"}


def compativel(curto, completo):
    """"FRANCISCO F DA SILVA FILHO" cabe em "FRANCISCO FERREIRA DA SILVA FILHO"? (iniciais, partículas e fim cortado)."""
    a = [w for w in normalizar_nome(curto).replace(".", " ").split() if w not in _PARTICULAS]
    b = [w for w in normalizar_nome(completo).replace(".", " ").split() if w not in _PARTICULAS]
    if not a or not b or a[0] != b[0]:
        return False
    j = 0
    for i, w in enumerate(a):
        ultimo = i == len(a) - 1
        while j < len(b) and not (b[j] == w or (len(w) == 1 and b[j][0] == w) or (ultimo and len(w) >= 3 and b[j].startswith(w))):
            j += 1
        if j == len(b):
            return False
        j += 1
    return True


def _limpo(nome):
    t = chave_nome(re.sub(r"\(\s*SUPLENTE\s*\)", " ", str(nome or ""), flags=re.I))
    return " ".join({"JR": "JUNIOR"}.get(w, w) for w in t.split())


def semelhanca(a, b):
    """0 a 1: o mesmo nome escrito de outro jeito ("GERMANO HEMANN" x "Germano He-Man", "PP Cell" x "PPCELL",
    "Ronaldo Martins" x "RONALDO MACHADO MARTINS", "ADRIANA PEDROSA ( SUPLENTE )" x "Adriana Pedrosa")."""
    import difflib
    ka, kb = _limpo(a), _limpo(b)
    if not ka or not kb:
        return 0.0
    if ka == kb:
        return 1.0
    if ka.replace(" ", "") == kb.replace(" ", ""):
        return 0.99
    ta, tb = set(ka.split()), set(kb.split())
    if ta <= tb or tb <= ta:
        return 0.95
    if compativel(ka, kb) or compativel(kb, ka):
        return 0.93
    return difflib.SequenceMatcher(None, ka, kb).ratio()


def achar_parecido(nome, opcoes, minimo=0.86):
    """opcoes: [(nome, código)]. O código do nome mais parecido, se for bem parecido e sem empate com outro código."""
    notas = {}
    for n, cod in opcoes:
        if n:
            notas[cod] = max(notas.get(cod, 0.0), semelhanca(nome, n))
    if not notas:
        return None
    ordem = sorted(notas.items(), key=lambda x: -x[1])
    if ordem[0][1] < minimo or (len(ordem) > 1 and ordem[1][1] >= ordem[0][1] - 0.02):
        return None
    return ordem[0][0]


def achar_no_tse(nome, tse):
    """Linha do TSE para um nome parlamentar (pelo nome de urna; senão, pelas palavras do nome)."""
    if tse is None or not len(tse):
        return None
    k = chave_nome(nome)
    exato = tse[tse.nome_urna.map(chave_nome) == k]
    if len(exato):
        return exato.sort_values("situacao").iloc[0]
    palavras = set(k.split())
    achados = tse[[palavras <= set(chave_nome(f"{u} {n}").split()) for u, n in zip(tse.nome_urna, tse.nome)]]
    eleitos = achados[achados.situacao == "eleito"]
    if len(eleitos) == 1:
        return eleitos.iloc[0]
    return achados.iloc[0] if len(achados) == 1 else None


# ---------------------------------------------------------------- fotos
def fotos(cod, lista, credito_pagina=None):
    """lista: [(codigo, url da foto)]. Salva site/fotos/ver-{cod}-{codigo}.webp (240×320), só as que faltam."""
    from ..fotos import _ajustar
    FOTOS.mkdir(parents=True, exist_ok=True)
    novas = 0
    for codigo, url in lista:
        destino = FOTOS / f"ver-{cod}-{codigo}.webp"
        if destino.exists() or not url:
            continue
        try:
            destino.write_bytes(_ajustar(baixar(url, timeout=60).content))
            novas += 1
        except TempoEsgotado:
            raise
        except Exception as e:  # noqa: BLE001 — sem foto, o site mostra as iniciais
            log(f"  foto do vereador {codigo}: {e}")
    return novas


# ---------------------------------------------------------------- montagem
class Tipos:
    """Lista única de nomes (tipos de gasto e fornecedores) para todas as cidades; o site guarda só o índice."""
    def __init__(self):
        self.lista, self.idx = [], {}

    def __call__(self, nome):
        if nome not in self.idx:
            self.idx[nome] = len(self.lista)
            self.lista.append(nome)
        return self.idx[nome]


# (nome próprio: o _SIGLAS lá de cima é das empresas, e um nome igual aqui o sobrescrevia)
_PARTIDOS = {"PC DO B": "PCdoB", "PCDOB": "PCdoB", "UNIAO BRASIL": "UNIÃO", "UNIAO": "UNIÃO", "PODEMOS": "PODE", "REP": "REPUBLICANOS", "PROGRESSISTAS": "PP",
           "PARTIDO DOS TRABALHADORES": "PT", "PARTIDO LIBERAL": "PL", "MOVIMENTO DEMOCRATICO BRASILEIRO": "MDB",
           "PARTIDO SOCIALISTA BRASILEIRO": "PSB", "PARTIDO SOCIAL DEMOCRATICO": "PSD", "PARTIDO VERDE": "PV",
           "REDE SUSTENTABILIDADE": "REDE", "PARTIDO NOVO": "NOVO", "PCDOB": "PCdoB", "PARTIDO COMUNISTA DO BRASIL": "PCdoB",
           "UB": "UNIÃO", "SD": "SOLIDARIEDADE", "SDD": "SOLIDARIEDADE"}


def sigla(partido):
    """Partido como sigla em maiúsculas, igual para todas as cidades ("União Brasil" e "UNIÃO" -> "UNIÃO")."""
    t = re.sub(r"\s+", " ", str(partido or "")).strip()
    if not t or t.lower() in ("nan", "none"):
        return None
    return _PARTIDOS.get(normalizar_nome(t), t.upper())


def _r(v):
    return int(round(float(v)))


def _vazio(colunas):
    return pd.DataFrame(columns=colunas)


def montar(cfg, tipos, ver, mandatos, ganha=None, despesas=None, verba=None, equipe=None, cargos=None):
    """Devolve (meta da cidade, lista de pessoas)."""
    cod = cfg["cod"]
    ate = cfg["ultimo_mes"]
    lista_meses = meses(cfg["inicio"], ate)
    anos = sorted({a for a, _ in lista_meses})
    ganha = ganha if ganha is not None else _vazio(["ano", "mes", "codigo", "categoria", "valor"])
    despesas = despesas if despesas is not None else _vazio(["ano", "mes", "codigo", "tipo", "fornecedor", "cnpj_cpf", "valor"])
    verba = verba if verba is not None else _vazio(["ano", "codigo", "credito", "devolvido"])
    equipe = equipe if equipe is not None else _vazio(["ano", "mes", "codigo", "pessoas", "custo"])
    cargos = cargos if cargos is not None else _vazio(["codigo", "cargo", "pessoas"])
    for df in (ganha, despesas, equipe):
        if len(df):
            df["aaaamm"] = df.ano.astype(int) * 100 + df.mes.astype(int)
        else:
            df["aaaamm"] = pd.Series(dtype=int)
    despesas = despesas[despesas.aaaamm <= ate]
    ganha = ganha[ganha.aaaamm <= ate]
    equipe = equipe[equipe.aaaamm <= ate]
    subsidio = cfg.get("subsidio") or []
    verba_ate = cfg.get("verba_ate") or 999999
    # meses em que a Câmara não publicou a verba (nem no arquivo do mês nem na folha): não contam na média da verba, e o
    # site diz "não publicada" em vez de R$ 0 (Cuiabá: fev e abr/2026)
    verba_sem = {int(x) for x in (cfg.get("verba_sem") or [])}

    def valor_subsidio(am):
        v = 0
        for de, valor in subsidio:
            if am >= de:
                v = valor
        return v

    info = {int(r.codigo): r for r in ver.itertuples()}
    por_cod = {k: g for k, g in despesas.groupby("codigo")} if len(despesas) else {}
    ganha_cod = {k: g for k, g in ganha.groupby("codigo")} if len(ganha) else {}
    equipe_cod = {k: g for k, g in equipe.groupby("codigo")} if len(equipe) else {}
    verba_cod = {k: g for k, g in verba.groupby("codigo")} if len(verba) else {}
    cargos_cod = {k: [[c, int(n)] for c, n in sorted(zip(g.cargo, g.pessoas), key=lambda x: (-x[1], x[0]))]
                  for k, g in cargos.groupby("codigo")} if len(cargos) else {}
    pessoas = []
    for codigo, g in mandatos.groupby("codigo"):
        codigo = int(codigo)
        r = info.get(codigo)
        if r is None:
            continue
        periodos = sorted((date.fromisoformat(str(i)[:10]), date.fromisoformat(str(f)[:10]) if isinstance(f, str) and f.strip() else None)
                          for i, f in zip(g.inicio, g.fim.fillna("") if "fim" in g else [""] * len(g)))
        # fora_hoje: quem a lista oficial da Casa não mostra em exercício hoje, mas continua recebendo (o titular
        # licenciado): o período segue aberto (o dinheiro continua) e a pessoa não conta como no cargo
        no_cargo = any(f is None or f >= HOJE for _, f in periodos) and codigo not in cfg.get("fora_hoje", ())
        dias_total = sum(dias_no_mes(periodos, a, m) for a, m in lista_meses)
        if dias_total < cfg.get("min_dias", 15) and not no_cargo:
            continue  # ficou só uns dias (para uma votação, por exemplo): fica fora da lista
        d = por_cod.get(codigo, _vazio(["aaaamm", "tipo", "fornecedor", "cnpj_cpf", "valor"]))
        gp = ganha_cod.get(codigo)
        eq = equipe_cod.get(codigo)
        serie, cats_mes = [], {}
        for a, m in lista_meses:
            am = a * 100 + m
            dias = dias_no_mes(periodos, a, m)
            if gp is not None:
                gm = gp[gp.aaaamm == am]
                ganha_m = float(gm.valor.sum())
                for c, v in gm.groupby("categoria").valor.sum().items():
                    cats_mes.setdefault(am, {})[c] = float(v)
            else:
                ganha_m = valor_subsidio(am) * dias / monthrange(a, m)[1]
                if ganha_m:
                    cats_mes.setdefault(am, {})["salario"] = ganha_m
            custa_m = float(d[d.aaaamm == am].valor.sum()) if len(d) else 0.0
            e_m, pes_m = 0.0, 0
            if eq is not None:
                em = eq[eq.aaaamm == am]
                e_m = float(pd.to_numeric(em.custo, errors="coerce").fillna(0).sum())
                pes_m = int(pd.to_numeric(em.pessoas, errors="coerce").fillna(0).sum())
            if dias or abs(ganha_m) >= 0.5 or abs(custa_m) >= 0.5 or e_m >= 0.5:
                serie.append((am, ganha_m, custa_m, e_m, pes_m, dias))
        if not serie:
            continue

        def bloco(filtro):
            s = [x for x in serie if filtro(x[0])]
            if not s:
                return None
            m = sum(1 for x in s if x[5] or abs(x[1]) >= 0.5)
            mg = sum(1 for x in s if abs(x[1]) >= 0.5)
            # verba_ate: último mês com a verba publicada (a verba sai depois da folha); os meses seguintes não contam
            mc = sum(1 for x in s if (x[5] or abs(x[2]) >= 0.5) and x[0] <= verba_ate and x[0] not in verba_sem)
            com_eq = [x for x in s if x[3] >= 0.5]
            com_pes = [x for x in s if x[4] > 0]
            cats = {}
            for x in s:
                for c, v in cats_mes.get(x[0], {}).items():
                    cats[c] = cats.get(c, 0.0) + v
            cats["verba_gabinete"] = sum(x[2] for x in s)
            cats["assessores_gabinete"] = sum(x[3] for x in s)
            return {"m": m, "mg": mg, "mc": mc, "me": len(com_eq), "g": _r(sum(x[1] for x in s)), "c": _r(sum(x[2] for x in s)),
                    "e": _r(sum(x[3] for x in s)), "pm": sum(x[4] for x in com_eq if x[4]), "mp": sum(1 for x in com_eq if x[4]),
                    "pu": com_pes[-1][4] if com_pes else 0, "ep": _r(sum(x[3] for x in com_eq if x[4])),
                    "cats": {k: _r(v) for k, v in cats.items() if abs(_r(v)) >= 1}}

        def detalhe(filtro):
            dd = d[[filtro(x) for x in d.aaaamm]] if len(d) else d
            if not len(dd):
                return None
            ordem = lambda serie: sorted(serie.items(), key=lambda x: (-round(float(x[1]), 2), str(x[0])))  # empate: pelo nome (igual em qualquer computador)
            # só os 8 maiores entram na lista de nomes do arquivo (antes entravam todos, e o arquivo levava nomes que o
            # site não mostra)
            saida = {"verba_gabinete": [[tipos(t), v] for t, v in [(t, _r(v)) for t, v in ordem(dd.groupby("tipo").valor.sum()) if _r(v) > 0][:8]]}
            com_forn = dd[dd.fornecedor.fillna("").astype(str).str.strip() != ""]
            if len(com_forn):
                chave = [re.sub(r"\D", "", str(c)) or f"?{normalizar_nome(f)}" for c, f in zip(com_forn.cnpj_cpf.fillna(""), com_forn.fornecedor)]
                forn = com_forn.assign(chave=chave)
                nomes = {}
                for ch, gg in forn.groupby("chave"):
                    pf = any(fornecedor_pf(c, f) for c, f in zip(gg.cnpj_cpf.fillna(""), gg.fornecedor))
                    nomes[ch] = "Pessoa física" if pf else empresa(gg.fornecedor.mode().iloc[0])
                por_forn = forn.assign(nome=forn.chave.map(nomes)).groupby("nome").valor.sum()
                saida["fornecedores"] = [[tipos(t), v] for t, v in [(t, _r(v)) for t, v in ordem(por_forn) if _r(v) > 0][:8]]
            return saida

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
        vb = {}
        vg = verba_cod.get(codigo)
        if vg is not None:
            for a, gg in vg.groupby("ano"):
                cred, dev = _r(gg.credito.fillna(0).sum()), _r(gg.devolvido.fillna(0).sum())
                if cred or dev:
                    vb[str(int(a))] = [cred, dev]
        prefixo = cfg.get("id_prefixo", "ver")  # as assembleias usam o mesmo formato, com outro prefixo e outro cargo
        foto = FOTOS / f"{prefixo}-{cod}-{codigo}.webp"
        n_cargos = cargos_cod.get(codigo, [])
        n_eq = sum(n for _, n in n_cargos)
        gab = g.gabinete.dropna().iloc[-1] if "gabinete" in g and g.gabinete.notna().any() else None
        pessoas.append({
            "id": f"{prefixo}-{cod}-{codigo}", "k": cfg.get("k", "v"), "cid": cod, "n": r.nome, "nc": (r.nome_civil or r.nome),
            "g": cfg.get("cargo", ("Vereadora", "Vereador"))[0 if r.genero == "F" else 1], "pt": sigla(r.partido), "uf": cfg["uf"],
            "f": f"fotos/{prefixo}-{cod}-{codigo}.webp" if foto.exists() else None,
            "fc": {"a": cfg.get("credito_foto") or cfg["casa"], "u": r.pagina or cfg.get("pagina")} if foto.exists() else None,
            "x": 1 if no_cargo else 0, "o": r.pagina or cfg.get("pagina"),
            **({"gab": int(gab)} if gab is not None and str(gab).isdigit() else {}),
            "sup": 1 if r.eleito == "suplente" else 0,
            "oc": [[i.strftime("%Y%m%d"), f.strftime("%Y%m%d") if f else None] for i, f in periodos],
            "per": per,
            "t": [[am, _r(gg_), _r(cc), _r(ee), pp, 0] for am, gg_, cc, ee, pp, _ in serie],
            "dt": dt,
            "vb": vb,
            "eq": {"n": n_eq, "c": n_cargos} if n_eq and no_cargo else None,
        })
    pessoas.sort(key=lambda p: normalizar_nome(p["n"]))
    meta = {
        "n": cfg["n"], "uf": cfg["uf"], "casa": cfg["casa"], "vagas": cfg.get("vagas") or sum(p["x"] for p in pessoas),
        "inicio": cfg["inicio"], "ultimo_mes": ate, "anos": [str(a) for a in anos],
        "subsidio": subsidio, "subsidio_folha": cfg.get("subsidio_folha", bool(len(ganha))), "salario_nota": cfg.get("salario_nota"),
        "verba_nome": cfg.get("verba_nome"), "verba_mes": cfg.get("verba_mes") or {},
        **({"verba_vigencia": cfg["verba_vigencia"]} if len(cfg.get("verba_vigencia") or []) > 1 else {}), "verba_regra": cfg.get("verba_regra"),
        "verba_notas": cfg.get("verba_notas") or [], "verba_por_nota": bool(len(despesas)) and bool(despesas.fornecedor.fillna("").astype(str).str.strip().ne("").any()),
        "equipe_em": cfg.get("equipe_em") or "", "equipe_custo": bool(len(equipe)) and bool(pd.to_numeric(equipe.custo, errors="coerce").fillna(0).gt(0).any()),
        "equipe_nota": cfg.get("equipe_nota"), "equipe_aviso": cfg.get("equipe_aviso"), "conferir_gastos": cfg.get("conferir_gastos", True), "notas": cfg.get("notas") or [], "fontes": cfg.get("fontes") or {},
        "verba_fora": cfg.get("verba_fora") or [],  # anos em que a verba ficou de fora (fonte com erro)
        # último mês com a verba publicada, quando a verba sai depois da folha (só nas cidades em que isso acontece)
        **({"verba_ate": int(cfg["verba_ate"])} if cfg.get("verba_ate") and int(cfg["verba_ate"]) < ate else {}),
        # meses sem a verba publicada no meio da série (fora deles, a verba é a publicada)
        **({"verba_sem": sorted(m for m in verba_sem if int(cfg["inicio"]) <= m <= min(ate, verba_ate))} if verba_sem else {}),
        # Câmara que não tem verba de gabinete nem cota (Vitória): o texto da Câmara, para o site não dizer "sem dados abertos"
        **({"sem_verba": cfg["sem_verba"]} if cfg.get("sem_verba") else {}),
    }
    return meta, pessoas


def _fotos_tse(resultados, baixar=True):
    """Quem está no cargo e não tem foto da Câmara: a foto da candidatura de 2024 no TSE (coleta/fotos_tse.py), quando o
    nome civil (ou, sem ele, o nome de urna) é exatamente o de um único candidato a vereador da cidade."""
    from .. import fotos_tse
    from ..fotos import CREDITOS
    novas = 0
    for meta, ps in resultados:
        faltam = [p for p in ps if p["x"] and not p["f"]]
        if faltam and baixar:
            try:
                novas += fotos_tse.por_nome(2024, meta["uf"], faltam, ("13",), municipio=meta["n"])
            except TempoEsgotado:
                raise
            except Exception as e:  # noqa: BLE001 — foto é opcional
                log(f"  fotos do TSE ({meta['n']}): {e}")
    creditos = json.loads(CREDITOS.read_text(encoding="utf-8")).get("fotos", {}) if CREDITOS.exists() else {}
    for _, ps in resultados:
        for p in ps:
            c = creditos.get(p["id"])
            if c and c.get("arquivo") and (FOTOS / f"{p['id']}.webp").exists():
                p["f"] = f"fotos/{p['id']}.webp"
                p["fc"] = {"a": c.get("autor"), "l": c.get("licenca"), "u": c.get("pagina")}
    if novas:
        log(f"  {novas} fotos novas de vereadores (candidatura de 2024 no TSE)")


def escrever(resultados, tipos, baixar_fotos=True):
    """resultados: [(meta, pessoas), ...] -> site/dados/camaras.json."""
    _fotos_tse(resultados, baixar_fotos)
    todas = [p for _, ps in resultados for p in ps]
    dados = {
        "meta": {
            "gerado_em": datetime.now().isoformat(timespec="seconds"),
            "tipos": tipos.lista,
            "categorias": {"verba_gabinete": {"grupo": "custa", "nome": "Verba do gabinete"}},
            "cidades": {str(m_cod): meta for m_cod, meta in ((ps[0]["cid"] if ps else None, meta) for meta, ps in resultados) if m_cod},
        },
        "p": todas,
    }
    if gravar_json(SAIDA, dados):  # cidade que sumiu ou perdeu muita gente: fica o arquivo anterior (util.gravar_com)
        log(f"Site: {SAIDA.relative_to(RAIZ)} ({SAIDA.stat().st_size / 1e3:.0f} KB, {len(resultados)} cidades, {len(todas)} vereadores)")
    return dados
