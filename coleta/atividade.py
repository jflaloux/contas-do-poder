"""Presença e projetos dos deputados federais e dos senadores na legislatura atual (desde 01/02/2023), só pelos dados
abertos oficiais da Câmara e do Senado. Tudo abre de fora do Brasil (roda no GitHub). Sem nota, sem ranking: os números
de cada pessoa, com a fonte.

Câmara dos Deputados
- Presença no Plenário: o serviço de dados abertos "ListarPresencasDia" (www.camara.leg.br/SitCamaraWS, Sessões e
  Reuniões), um pedido por dia com sessão deliberativa. Para cada deputado em exercício naquele dia, a frequência do
  dia ("Presença", "Ausência justificada", com o motivo, ou "Ausência"), a mesma contagem por dia que a Câmara usa. Os
  dias com sessão deliberativa saem do arquivo anual de eventos dos dados abertos (tipo "Sessão Deliberativa", no
  Plenário da Câmara). O serviço identifica o deputado pela carteira parlamentar e pelo nome ("Nome-PARTIDO/UF"): o id
  dos dados abertos sai do nome e da UF (lista de deputados da legislatura) e, para quem está no cargo hoje, também da
  matrícula do serviço "ObterDeputados".
- Projetos: os arquivos anuais de proposições, de autores e de temas dos dados abertos
  (dadosabertos.camara.leg.br/arquivos/proposicoes, proposicoesAutores e proposicoesTemas).

Senado Federal
- Presença: os dados abertos do Senado não trazem a presença por sessão; trazem, em cada votação nominal do Plenário,
  a situação de cada senador em exercício (votou, presente sem registrar voto, presidindo, licença, missão, atividade
  parlamentar, não compareceu...): /dadosabertos/votacao. Por isso, no Senado, a conta é por votação nominal.
- Projetos: /dadosabertos/processo?codigoParlamentarAutor=<código> (os processos de que o senador é autor), com a
  autoria em ordem; o assunto "Honorífico" (data comemorativa, homenagem cívica) do próprio Senado.

Projetos que contam: os que podem virar norma e foram apresentados desde 01/02/2023 (PL, PLP, PEC, PDL e projeto de
resolução: PRC na Câmara, PRS no Senado). Requerimentos, indicações, emendas e pareceres ficam de fora. Cada projeto é
"homenagem ou data" ou "os demais" pela regra da ementa (EMENTA_HOMENAGEM, explicada no README); "virou norma" é a
situação "Transformado em Norma Jurídica" da própria Casa (lei, lei complementar, emenda constitucional, decreto
legislativo ou resolução). Primeiro autor e coautores contam à parte.

Saída: dados/atividade/ (os números de cada pessoa, em CSV) e site/dados/atividade.json.
"""
import csv
import difflib
import io
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

import requests

from .config import CACHE, DADOS, HOJE, INICIO_LEGISLATURA, RAIZ
from .util import baixar, cache_valido, dormir, gravar_json, gravar_linhas, ler_json, log, salvar_json

INICIO = date(INICIO_LEGISLATURA[0], INICIO_LEGISLATURA[1], 1)
C = CACHE / "atividade"
SAIDA = DADOS / "atividade"
SITE = RAIZ / "site" / "dados" / "atividade.json"
ARQUIVOS_CAMARA = "https://dadosabertos.camara.leg.br/arquivos"
WS_CAMARA = "https://www.camara.leg.br/SitCamaraWS"
API_CAMARA = "https://dadosabertos.camara.leg.br/api/v2"
SENADO = "https://legis.senado.leg.br/dadosabertos"
JSON = {"Accept": "application/json"}
PAUSA_WS = 0.5  # segundos entre os pedidos ao serviço de presença da Câmara
_FALHAS = []  # pedidos que falharam nesta rodada: os números saem com o que já estava gravado, e a etapa termina com erro
REVER_DIAS = 45  # a justificativa de uma ausência pode entrar depois: os últimos 45 dias são lidos de novo a cada semana


def _anos():
    return list(range(INICIO.year, HOJE.year + 1))


def _sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto or "") if unicodedata.category(c) != "Mn").lower()


# ---------------------------------------------------------------- Câmara: arquivos anuais
def _arquivo_camara(conjunto, ano):
    """CSV anual dos dados abertos da Câmara (refeito por ela todo dia); guardado no cache por 6 dias."""
    arq = C / "camara" / f"{conjunto}-{ano}.csv"
    if not cache_valido(arq, 6):
        r = baixar(f"{ARQUIVOS_CAMARA}/{conjunto}/csv/{conjunto}-{ano}.csv", timeout=600)
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_bytes(r.content)
    return arq


def _ler_csv(arq):
    with open(arq, encoding="utf-8-sig", newline="") as f:
        yield from csv.DictReader(f, delimiter=";")


# ---------------------------------------------------------------- Câmara: presença
def dias_de_sessao():
    """Dias com sessão deliberativa (ou preparatória) no Plenário da Câmara, desde o início da legislatura até ontem."""
    dias = set()
    for ano in _anos():
        for e in _ler_csv(_arquivo_camara("eventos", ano)):
            tipo = e["descricaoTipo"]  # a sessão preparatória (posse e eleição da Mesa, em 1º de fevereiro) também conta na Câmara
            if ((tipo == "Sessão Deliberativa" or tipo.startswith("Sessão Preparatória"))
                    and e["localCamara.nome"] == "Plenário da Câmara dos Deputados" and e["situacao"].startswith("Encerrada")):
                d = date.fromisoformat(e["dataHoraInicio"][:10])
                if INICIO <= d < HOJE:
                    dias.add(d)
    return sorted(dias)


def _presenca_dia(dia):
    """A frequência de cada deputado em exercício num dia (XML do serviço ListarPresencasDia), guardada no cache."""
    arq = C / "camara" / "presenca" / f"{dia.isoformat()}.xml"
    recente = (HOJE - dia).days <= REVER_DIAS
    if not arq.exists() or (recente and not cache_valido(arq, 6)):
        dormir(PAUSA_WS)
        r = baixar(f"{WS_CAMARA}/sessoesreunioes.asmx/ListarPresencasDia",
                   params={"data": dia.strftime("%d/%m/%Y"), "numMatriculaParlamentar": "", "siglaPartido": "", "siglaUF": ""})
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_bytes(r.content)
    x = ET.fromstring(arq.read_bytes())
    saida = []
    for p in x.findall(".//parlamentar"):
        nome = (p.findtext("nomeParlamentar") or "").strip()
        saida.append({"carteira": (p.findtext("carteiraParlamentar") or "").strip(),
                      "nome": nome.rsplit("-", 1)[0].strip() if "-" in nome else nome,
                      "uf": (p.findtext("siglaUF") or "").strip(),
                      "frequencia": (p.findtext("descricaoFrequenciaDia") or "").strip(),
                      "justificativa": (p.findtext("justificativa") or "").strip()})
    return int(x.findtext("qtdeSessoesDia") or 0), saida


def _carteiras(vistos):
    """{carteira: id do deputado nos dados abertos}. `vistos`: {carteira: (nome, UF)} dos dias lidos agora. Quem está
    no cargo hoje: pela matrícula do serviço ObterDeputados (é o número da carteira). Quem saiu: pelo nome e pela UF na
    lista de deputados da legislatura. O que já foi ligado fica em dados/atividade/camara-carteiras.csv (a carteira não
    muda de dono na legislatura)."""
    arq = SAIDA / "camara-carteiras.csv"
    guardado = {l["carteira"]: l for l in _ler_csv(arq)} if arq.exists() else {}
    faltam = [c for c in vistos if c not in guardado]
    if faltam:
        x = ET.fromstring(baixar(f"{WS_CAMARA}/Deputados.asmx/ObterDeputados").content)
        por_matricula = {(d.findtext("matricula") or "").strip(): (d.findtext("ideCadastro") or "").strip() for d in x.findall("deputado")}
        from .camara import deputados
        deps = deputados()
        por_nome = defaultdict(list)
        for d in deps:
            por_nome[(_nome_chave(d["nome"]), d["uf"])].append(str(d["id"]))
        for c in faltam:
            nome, uf = vistos[c]
            id_ = por_matricula.get(c)
            via = "matrícula"
            if not id_:
                achados = por_nome.get((_nome_chave(nome), uf), [])
                id_, via = (achados[0], "nome e UF") if len(achados) == 1 else (_parecido(nome, uf, deps), "nome parecido e UF")
            if id_:
                guardado[c] = {"carteira": c, "id_deputado": id_, "nome": nome, "uf": uf, "ligado_por": via}
            else:
                log(f"Atividade: carteira {c} ({nome}, {uf}) sem deputado correspondente; fica de fora")
        SAIDA.mkdir(parents=True, exist_ok=True)
        gravar_linhas(arq, ["carteira", "id_deputado", "nome", "uf", "ligado_por"],
                      sorted(guardado.values(), key=lambda l: int(l["carteira"])), delimiter=";")
    return {c: l["id_deputado"] for c, l in guardado.items()}


def _nome_chave(nome):
    n = re.sub(r"[^a-z ]", " ", _sem_acento(nome))
    return " ".join(t for t in n.split() if t not in ("dr", "dra", "pr", "jr", "junior", "filho", "neto", "pai"))


def _parecido(nome, uf, deps):
    """O único deputado da mesma UF com o nome que contém o outro (ou com as mesmas palavras, fora uma): "Tenente
    Coronel Zucco" e "Zucco", "Duarte" e "Duarte Jr.". Sem um só candidato, nenhum."""
    a = set(_nome_chave(nome).split())
    candidatos = []
    for d in deps:
        if d["uf"] != uf:
            continue
        b = set(_nome_chave(d["nome"]).split())
        if a and b and (a <= b or b <= a or len(a ^ b) <= 1
                        or difflib.SequenceMatcher(None, " ".join(sorted(a)), " ".join(sorted(b))).ratio() >= 0.9):
            candidatos.append(str(d["id"]))
    return candidatos[0] if len(candidatos) == 1 else None


FREQ = {"Presença": "P", "Ausência justificada": "J", "Ausência": "A"}


def camara_presenca():
    """Por deputado: dias com sessão deliberativa em que estava em exercício, presenças, ausências justificadas (com o
    motivo) e ausências, no total e por ano. Cada dia lido fica em dados/atividade/camara-presenca-AAAA.csv: na
    rodada seguinte, só os dias novos e os dos últimos 45 dias (a justificativa pode entrar depois) são pedidos de novo."""
    dias = dias_de_sessao()
    guardados = defaultdict(list)
    for arq in sorted(SAIDA.glob("camara-presenca-*.csv")):
        for l in _ler_csv(arq):
            guardados[l["data"]].append(l)
    lidos, vistos = {}, {}
    for dia in dias:
        if guardados.get(dia.isoformat()) and (HOJE - dia).days > REVER_DIAS:
            continue
        try:
            q, lista = _presenca_dia(dia)
        except (requests.RequestException, ET.ParseError) as e:  # fica o que já estava gravado; a etapa termina com erro
            _FALHAS.append(f"presença da Câmara em {dia:%d/%m/%Y}: {e}")
            continue
        if not q or not lista:
            log(f"Atividade: {dia:%d/%m/%Y} sem sessão no serviço de presença da Câmara; fica de fora")
            continue
        linhas = []
        for p in lista:
            f = FREQ.get(re.sub(r"\s*\(~\)$", "", p["frequencia"]))  # "Presença (~)" também aparece no serviço: é presença
            if f is None:
                log(f"Atividade: frequência desconhecida em {dia:%d/%m/%Y}: {p['frequencia']!r}")
                continue
            vistos.setdefault(p["carteira"], (p["nome"], p["uf"]))
            linhas.append({"data": dia.isoformat(), "carteira": p["carteira"], "frequencia": f,
                           "justificativa": p["justificativa"] if f == "J" else ""})
        lidos[dia.isoformat()] = linhas
    carteiras = _carteiras(vistos)
    por_ano = defaultdict(list)
    for dia in dias:
        d = dia.isoformat()
        for l in lidos.get(d) or guardados.get(d) or []:
            por_ano[dia.year].append({**l, "id_deputado": carteiras.get(l["carteira"], "")})
    SAIDA.mkdir(parents=True, exist_ok=True)
    total = defaultdict(lambda: defaultdict(lambda: [0, 0, 0, 0]))
    motivos = defaultdict(Counter)
    for ano, linhas in por_ano.items():
        gravar_linhas(SAIDA / f"camara-presenca-{ano}.csv", ["data", "carteira", "id_deputado", "frequencia", "justificativa"],
                      sorted(linhas, key=lambda l: (l["data"], int(l["carteira"]))), delimiter=";")
        for l in linhas:
            if not l["id_deputado"]:
                continue
            t = total[l["id_deputado"]][str(ano)]
            t[0] += 1
            t["PJA".index(l["frequencia"]) + 1] += 1
            if l["frequencia"] == "J":
                motivos[l["id_deputado"]][l["justificativa"] or "sem motivo informado"] += 1
    ultimo = max((date.fromisoformat(l["data"]) for ls in por_ano.values() for l in ls), default=None)
    log(f"Atividade: presença na Câmara em {sum(len({l['data'] for l in ls}) for ls in por_ano.values())} dias com sessão "
        f"deliberativa (pedidos agora: {len(lidos)}), {len(total)} deputados")
    return total, motivos, ultimo


# ---------------------------------------------------------------- projetos (regra das homenagens)
TIPOS = {"PL": "Projeto de lei", "PLP": "Projeto de lei complementar", "PEC": "Proposta de emenda à Constituição",
         "PDL": "Projeto de decreto legislativo", "PR": "Projeto de resolução"}
TIPO_CASA = {"PRC": "PR", "PRS": "PR"}  # projeto de resolução: PRC na Câmara, PRS no Senado
_Q = r"[\"“”'‘’«]?"
_MESES = "janeiro|fevereiro|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro"
_CORES = "amarelo|azul|branco|cinza|dourado|laranja|lilas|marrom|preto|rosa|roxo|verde|vermelho|bordo|prata|violeta|turquesa|celeste|coral|ouro"
_ATO = r"(^|\bpara |\ba fim de )"  # o ato principal: no começo da ementa ou depois de "para" ("Altera a Lei ... para instituir")
_CRIA = r"(institui|instituir|instituida|instituido|cria|criar|criada|criado|estabelece|estabelecer|declara|declarar|fixa|fixar|oficializa|oficializar)"
_LUGAR = r"(rodovia|trecho|ponte|viaduto|aeroporto|terminal|porto|eclusa|barragem|acude|hospital|campus|escola|agencia|estacao|contorno|anel|novo|nova)"
# Homenagem ou data: a ementa (sem acentos, em minúsculas) bate com uma destas expressões. A primeira que bate dá o
# motivo. Testada contra o tema "Homenagens e Datas Comemorativas" que a Câmara dá a cada proposição (2023 a 2026): ver
# o README.
EMENTA_HOMENAGEM = [
    ("nome de bem público", rf"^(denomina|nomeia|da (o )?nome|da a denominacao|confere (a )?denominacao|atribui (o )?nome|atribui a denominacao)\b|^(altera|dispoe sobre) a denominacao d[aeo]s? {_LUGAR}"),
    ("nome de bem público", r"^altera a lei .{0,120}para (estender|ampliar|alterar) a (homenagem|denominacao)"),
    ("Livro dos Heróis", r"livro dos herois|^inscreve (o|os) nomes?\b"),
    ("data comemorativa", _ATO + _CRIA + rf"\b.{{0,25}}{_Q}\b(dia|semana|mes|quinzena|ano|decada) (nacional|internacional|mundial|d[aeo]s?)\b"),
    ("data comemorativa", _ATO + _CRIA + rf"\b.{{0,80}}\bcomo (o |a )?{_Q}(dia|semana|mes|data)\b"),
    ("data comemorativa", _ATO + _CRIA + rf"\b.{{0,40}}\b({_MESES}) ({_CORES})\b"),
    ("data comemorativa", r"^dispoe sobre a (instituicao|criacao) d[oa] (dia|semana|mes|ano)\b|\b(entre as|nas|como) datas? comemorativas?\b|\befemerides\b"),
    ("data comemorativa", r"^declara feriado|\binstitui (o )?feriado|\bferiado nacional"),
    ("data comemorativa", r"\b(inclu\w*|inscrev\w*|inser\w*)\b.{0,200}\bcalendario (oficial|turistico|de eventos|cultural|nacional de (eventos|datas|campanhas))"),
    ("título honorífico", r"\b(confere|concede|atribui|outorga)\b.{0,80}\btitulo\b(?! de (dominio|propriedade|credito|eleitor))"),
    ("título honorífico", r"\bcapital nacional d[aeo]s?\b|^(institui|declara|reconhece|eleva)\b.{0,80}\bsimbolo nacional\b|^(declara|confere|concede|institui|proclama|reconhece)\b.{0,100}\bpatron[oa]s?\b"),
    ("título honorífico", rf"^(declara|reconhec\w*|institui e reconhece|confere|concede)\b.{{0,140}}\bcomo (o |a )?{_Q}(maior|capital|cidade|municipio|estado|berco|terra|polo|referencia|estancia|santuario|monumento)"),
    ("homenagem, prêmio ou medalha", r"^(homenageia|presta homenagem|concede homenagem)|\b(reconhece|declara)\b.{0,20}\bde utilidade publica (a|o)\b"),
    ("homenagem, prêmio ou medalha", rf"^(institui|cria) (o |a )?{_Q}(premio|diploma)\b|^(institui|cria|dispoe sobre a criacao|fica criad\w*)\b.{{0,80}}\b(medalha|comenda|condecoracao|honraria|ordem do merito)\b"),
    ("homenagem, prêmio ou medalha", r"\bhomenage(m|ar|ia)\b"),
    ("patrimônio ou manifestação cultural", r"^(inclui e )?(declara|reconhec\w*|eleva|inscreve|confere|concede|dispoe sobre o reconhecimento)\b.{0,160}\b(patrimonio (cultural|historico|imaterial|nacional|artistico)|manifestac\w+ (da )?cultura|manifestac\w+ cultural|heroi|heroina|bem de natureza imaterial|interesse cultural|monumento nacional)"),
]
# fora da regra, mesmo batendo numa expressão: vacinas no calendário, desapropriação por utilidade pública, proibição de homenagens
EMENTA_NAO = r"\bvacina|\bdesapropria|\bveda\w*\b.{0,80}\bhomenage"
_RX = [(m, re.compile(p)) for m, p in EMENTA_HOMENAGEM]
_RX_NAO = re.compile(EMENTA_NAO)


def homenagem(ementa):
    """O motivo ("data comemorativa", "nome de bem público"...) se a ementa é de homenagem ou data; senão None."""
    e = " ".join(_sem_acento(ementa).split()).lstrip("\"“”'‘’« ")
    if _RX_NAO.search(e):
        return None
    return next((m for m, rx in _RX if rx.search(e)), None)


def _novo_contador():
    return defaultdict(lambda: [0, 0, 0, 0, 0])  # tipo: [1º autor, dos quais homenagem, viraram norma, das quais homenagem, coautor]


def camara_projetos():
    """Por deputado e tipo: projetos apresentados desde 01/02/2023 como primeiro autor (e quantos são homenagem ou
    data), quantos viraram norma e como coautor; e a lista dos que viraram norma."""
    props = {}
    for ano in _anos():
        for p in _ler_csv(_arquivo_camara("proposicoes", ano)):
            tipo = TIPO_CASA.get(p["siglaTipo"], p["siglaTipo"])
            if tipo not in TIPOS or (p["dataApresentacao"] or "")[:10] < INICIO.isoformat():
                continue
            props[p["id"]] = {"tipo": tipo, "ident": f"{p['siglaTipo']} {p['numero']}/{p['ano']}", "ementa": p["ementa"],
                              "hom": homenagem(p["ementa"]), "norma": p["ultimoStatus_descricaoSituacao"] == "Transformado em Norma Jurídica",
                              "data_norma": (p["ultimoStatus_dataHora"] or "")[:10]}
    conta = defaultdict(_novo_contador)
    normas = defaultdict(list)
    for ano in _anos():
        for a in _ler_csv(_arquivo_camara("proposicoesAutores", ano)):
            p = props.get(a["idProposicao"])
            if not p or a["codTipoAutor"] != "10000" or not a["idDeputadoAutor"] or a["proponente"] != "1":
                continue
            c = conta[a["idDeputadoAutor"]][p["tipo"]]
            if a["ordemAssinatura"] == "1":
                c[0] += 1
                c[1] += bool(p["hom"])
                if p["norma"]:
                    c[2] += 1
                    c[3] += bool(p["hom"])
                    normas[a["idDeputadoAutor"]].append([p["ident"], a["idProposicao"], 1 if p["hom"] else 0, p["data_norma"]])
            else:
                c[4] += 1
    log(f"Atividade: {len(props)} projetos na Câmara desde {INICIO:%d/%m/%Y}, {sum(1 for p in props.values() if p['hom'])} de "
        f"homenagem ou data; {len(conta)} deputados autores")
    return conta, normas, props


# ---------------------------------------------------------------- Senado
def _senado(caminho, params=None, dias_cache=6, nome=None):
    arq = C / "senado" / (nome or (caminho.strip("/").replace("/", "_") + ".json"))
    if not cache_valido(arq, dias_cache):
        salvar_json(arq, baixar(f"{SENADO}{caminho}", params=params, headers=JSON, timeout=300).json())
    return ler_json(arq)


PRESENTE_SENADO = {"Sim", "Não", "Abstenção", "Votou", "Presidente (art. 51 RISF)", "P-NRV", "P-OD", "PR", "PS", "VO", "VS",
                   "OB", "SF", "PSF"}
NAO_COMPARECEU_SENADO = {"NCom"}
OUTRO_SENADO = {"NA", "NR", "NH", "SI"}  # "dispositivo não citado", "não registrou voto", "não houve votação", "votação simbólica"


def senado_presenca():
    """Por senador: votações nominais do Plenário em que estava em exercício (o Senado lista em cada uma os 81 em
    exercício), e em quantas estava presente (votou, presente sem registrar voto, presidindo), ausente com motivo
    registrado (licença, missão, atividade parlamentar...), não compareceu ou em outra situação; no total e por ano.
    Guarda cada voto (só a situação, sem o sentido do voto) em dados/atividade/senado-votacoes-AAAA.csv."""
    tipos = _senado("/plenario/lista/tiposComparecimento", dias_cache=30)
    descr = {t["Sigla"]: t["Descricao"] for t in tipos["ListaTiposComparecimento"]["TiposComparecimento"]["TipoComparecimento"]}
    total = defaultdict(lambda: defaultdict(lambda: [0, 0, 0, 0, 0]))
    motivos = defaultdict(Counter)
    ultima, n = None, 0
    for ano in _anos():
        ini = max(INICIO, date(ano, 1, 1))
        fim = min(date(ano, 12, 31), HOJE - timedelta(days=1))
        votacoes = _senado("/votacao", {"dataInicio": ini.isoformat(), "dataFim": fim.isoformat()},
                           dias_cache=6 if ano == HOJE.year else 30, nome=f"votacao-{ano}.json")
        linhas = []
        for v in sorted(votacoes, key=lambda v: (v["dataSessao"], v.get("sequencialVotacao") or 0, v.get("codigoSessaoVotacao") or 0)):
            if v.get("casaSessao") != "SF":
                continue
            n += 1
            ultima = max(ultima or v["dataSessao"], v["dataSessao"])
            for x in v.get("votos") or []:
                cod, sig = str(x["codigoParlamentar"]), x.get("siglaVotoParlamentar") or ""
                if sig in PRESENTE_SENADO:
                    i = 1
                elif sig in NAO_COMPARECEU_SENADO:
                    i = 3
                elif sig in OUTRO_SENADO or sig not in descr:
                    i = 4
                    if sig not in descr and sig not in OUTRO_SENADO:
                        log(f"Atividade: situação desconhecida numa votação do Senado: {sig!r}")
                else:
                    i = 2
                    motivos[cod][descr[sig]] += 1
                t = total[cod][str(ano)]
                t[0] += 1
                t[i] += 1
                linhas.append({"data": v["dataSessao"], "votacao": v["codigoSessaoVotacao"], "materia": v.get("identificacao") or "",
                               "codigo_senador": cod, "situacao": "votou" if sig in ("Sim", "Não", "Abstenção", "Votou") else sig})
        if linhas:
            SAIDA.mkdir(parents=True, exist_ok=True)
            gravar_linhas(SAIDA / f"senado-votacoes-{ano}.csv", ["data", "votacao", "materia", "codigo_senador", "situacao"],
                          linhas, delimiter=";")
    log(f"Atividade: {n} votações nominais no Plenário do Senado desde {INICIO:%d/%m/%Y}, {len(total)} senadores")
    return total, motivos, ultima


def _sem_titulo(trecho):
    t = re.sub(r"\(.*?\)", "", trecho)
    return _nome_chave(re.sub(r"^\s*senador[a]?\s+", "", t.strip(), flags=re.I))


def senado_projetos(senadores):
    """Por senador e tipo, como camara_projetos, pelos processos de que ele é autor (/processo)."""
    conta = defaultdict(_novo_contador)
    normas = defaultdict(list)
    props = {}
    for s in senadores:
        cod = str(s["id"])
        lista = _senado("/processo", {"codigoParlamentarAutor": cod}, nome=f"processos-{cod}.json")
        nome = _nome_chave(s["nome"])
        # o projeto do Senado emendado pela Câmara volta como outro processo ("PL 1770/2024 (Emenda-CD)", "(Substitutivo-CD)"),
        # e é esse que vira norma: a norma conta para o projeto original
        norma_pela_volta = set()
        for p in lista:
            m = re.match(r"^(\S+ \d+/\d{4}) \((Substitutivo|Emenda)-CD\)", p.get("identificacao") or "")
            if m and (p.get("situacaoAtual") or "").upper().startswith("TRANSFORMADA EM NORMA JURÍDICA"):
                norma_pela_volta.add(m.group(1))
        for p in lista:
            sigla = (p.get("identificacao") or "").split(" ")[0]
            tipo = TIPO_CASA.get(sigla, sigla)
            if tipo not in TIPOS or (p.get("dataApresentacao") or "") < INICIO.isoformat():
                continue
            # só o que nasceu no Senado: fora o que veio da Câmara ("Revisora", como o projeto que o senador apresentou
            # quando era deputado) e as voltas da Câmara e partes de PEC, que têm parênteses na identificação
            if p.get("objetivo") not in (None, "Iniciadora") or "(" in p["identificacao"]:
                continue
            autores = [_sem_titulo(a) for a in (p.get("autoria") or "").split(",")]
            if autores and autores[0] == nome:
                primeiro = True
            elif nome in autores[1:]:
                primeiro = False
            else:  # o nome na autoria é outro (nome civil, apelido): a ordem dos autores no detalhe do processo
                det = _senado(f"/processo/{p['id']}", dias_cache=30, nome=f"processo-{p['id']}.json")
                ordem = {str(a.get("codigoParlamentar")): a.get("ordem") for a in det.get("autoriaIniciativa") or det.get("autoria") or []}
                primeiro = ordem.get(cod) == 1
            hom = homenagem(p.get("ementa"))
            norma = ((p.get("situacaoAtual") or "").upper().startswith("TRANSFORMADA EM NORMA JURÍDICA")
                     or p["identificacao"] in norma_pela_volta)
            props[p["id"]] = {"tipo": tipo, "ident": p["identificacao"], "hom": hom, "norma": norma}
            c = conta[cod][tipo]
            if primeiro:
                c[0] += 1
                c[1] += bool(hom)
                if norma:
                    c[2] += 1
                    c[3] += bool(hom)
                    normas[cod].append([p["identificacao"], str(p.get("codigoMateria") or p["id"]), 1 if hom else 0,
                                        (p.get("dataSituacaoAtual") or "")[:10]])
            else:
                c[4] += 1
    log(f"Atividade: {len(props)} projetos de senadores no Senado desde {INICIO:%d/%m/%Y}, "
        f"{sum(1 for p in props.values() if p['hom'])} de homenagem ou data")
    return conta, normas, props


# ---------------------------------------------------------------- montagem
def _gravar_csv(nome, campos, linhas):
    SAIDA.mkdir(parents=True, exist_ok=True)
    gravar_linhas(SAIDA / nome, campos, linhas, delimiter=";", dicionarios=False)


def coletar():
    _FALHAS.clear()
    from .camara import deputados
    from .senado import senadores
    deps = deputados()
    sens = [s for s in senadores() if s.get("exerceu_na_legislatura")]
    pres_c, mot_c, ate_c = camara_presenca()
    proj_c, norm_c, _ = camara_projetos()
    pres_s, mot_s, ate_s = senado_presenca()
    proj_s, norm_s, _ = senado_projetos(sens)

    pessoas = {}
    linhas_proj = []
    for casa, ids, pres, mot, proj, norm in (("dep", [str(d["id"]) for d in deps], pres_c, mot_c, proj_c, norm_c),
                                             ("sen", [str(s["id"]) for s in sens], pres_s, mot_s, proj_s, norm_s)):
        for i in ids:
            reg = {}
            anos = pres.get(i)
            if anos:
                n = 4 if casa == "dep" else 5
                reg["pa"] = {a: v[:n] for a, v in sorted(anos.items())}
                reg["pr"] = [sum(v[k] for v in anos.values()) for k in range(n)]
                if mot.get(i):
                    reg["pm"] = dict(mot[i].most_common())
            if proj.get(i):
                reg["pj"] = {t: v for t, v in proj[i].items()}
                for t, v in sorted(proj[i].items()):
                    linhas_proj.append([f"{casa}-{i}", t, *v])
            if norm.get(i):
                reg["nj"] = sorted(norm[i], key=lambda x: x[3])
            if reg:
                pessoas[f"{casa}-{i}"] = reg
    _gravar_csv("projetos-por-pessoa.csv", ["id", "tipo", "primeiro_autor", "primeiro_autor_homenagem", "virou_norma",
                                            "virou_norma_homenagem", "coautor"], sorted(linhas_proj))
    _gravar_csv("presenca-por-pessoa.csv", ["id", "ano", "total", "presente", "ausencia_com_motivo", "ausencia", "outra"],
                sorted([k, a, *(v + [0])[:5]] for k, r in pessoas.items() for a, v in (r.get("pa") or {}).items()))
    meta = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "desde": INICIO.isoformat(),
        "camara_presenca_ate": ate_c.isoformat() if ate_c else None,
        "senado_votacoes_ate": ate_s,
        "tipos": TIPOS,
        "campos": {
            "pr": "Câmara: [dias com sessão deliberativa em exercício, presença, ausência justificada, ausência]; Senado: "
                  "[votações nominais em exercício, presente, ausente com motivo registrado, não compareceu, outra situação]",
            "pa": "o mesmo, por ano",
            "pm": "motivos das ausências justificadas (Câmara) ou com motivo registrado (Senado), com o número de dias ou votações",
            "pj": "por tipo: [apresentados como primeiro autor, dos quais homenagem ou data, viraram norma, dos quais homenagem "
                  "ou data, como coautor]",
            "nj": "os que viraram norma (primeiro autor): [identificação, código na Casa, 1 se homenagem ou data, data da situação]",
        },
        "fontes": {
            "camara_presenca": f"{WS_CAMARA}/sessoesreunioes.asmx/ListarPresencasDia",
            "camara_dias": f"{ARQUIVOS_CAMARA}/eventos/csv/eventos-AAAA.csv",
            "camara_projetos": f"{ARQUIVOS_CAMARA}/proposicoes/csv/proposicoes-AAAA.csv",
            "camara_autores": f"{ARQUIVOS_CAMARA}/proposicoesAutores/csv/proposicoesAutores-AAAA.csv",
            "camara_proposicao": "https://www.camara.leg.br/propostas-legislativas/{codigo}",
            "senado_votacoes": f"{SENADO}/votacao",
            "senado_projetos": f"{SENADO}/processo?codigoParlamentarAutor={{codigo}}",
            "senado_materia": "https://www25.senado.leg.br/web/atividade/materias/-/materia/{codigo}",
        },
        "regra_homenagem": "Homenagem ou data: projeto cuja ementa dá nome a bem público, institui data comemorativa (dia, "
                           "semana, mês, campanha de mês com cor, feriado, inclusão em calendário oficial ou turístico), "
                           "inscreve nome no Livro dos Heróis e Heroínas da Pátria, confere título honorífico (capital "
                           "nacional, patrono, símbolo), institui prêmio, medalha ou diploma, reconhece utilidade pública "
                           "ou declara patrimônio ou manifestação cultural. Os demais projetos ficam em \"os demais\".",
    }
    gravar_json(SITE, {"meta": meta, "p": pessoas}, final="\n")
    log(f"Atividade: {sum(1 for k in pessoas if k.startswith('dep-'))} deputados e {sum(1 for k in pessoas if k.startswith('sen-'))} "
        f"senadores em {SITE.relative_to(RAIZ)}")
    if _FALHAS:
        raise RuntimeError(f"{len(_FALHAS)} pedidos falharam (o site ficou com o que já estava gravado): {_FALHAS[0]}")
