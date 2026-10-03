"""TCE-PE: o total pago aos vereadores, ao prefeito e ao vice de cada município de Pernambuco (184 municípios), mês a
mês, e os nomes de quem estava em cada cargo no último mês.

Fonte: Tome Conta, o portal do Tribunal de Contas de Pernambuco com os dados que cada município manda ao Tribunal pelo
sistema Sagres (https://tomeconta.tce.pe.gov.br/dados/, "Servidores"). Para cada unidade (Câmara ou Prefeitura) e mês,
a página mostra cada cargo com a quantidade de pessoas e o total das vantagens (o bruto, antes dos descontos); o
número da quantidade leva a uma página com os nomes de quem estava no cargo (matrícula, nome, CPF mascarado, ingresso
e afastamento), sem o valor de cada um. O robô lê a tabela por cargo (o mesmo pedido que a página faz,
PessoalFolhaPagamento!paginaVisualizarAjax, com todos os cargos numa página só) e, no último mês de cada cidade, a lista
de nomes dos cargos de vereador, prefeito e vice (e também nos meses em que o papel tem mais de um cargo, para contar
as pessoas uma vez só: o presidente da Câmara costuma aparecer como VEREADOR e de novo como PRESIDENTE). O CPF
mascarado não é guardado.

- A lista das câmaras e prefeituras e os códigos delas vêm da API de Dados Abertos do TCE-PE
  (https://sistemas.tce.pe.gov.br/DadosAbertos/, UnidadesJurisdicionadas), sem login nem chave.
- O robots.txt do Tome Conta não proíbe nada; mesmo assim, um pedido por vez, com pausa (PAUSA), e no máximo
  MAX_PEDIDOS por rodada (a primeira leitura, desde jan/2025, se divide em algumas rodadas).
- O servidor do Tome Conta não manda o certificado intermediário (cadeia incompleta): util.ca_com_intermediario
  completa a cadeia com o intermediário que o próprio certificado indica, conferido com as raízes do certifi. A
  verificação nunca é desligada.
- Vereadores: na Câmara, o cargo de vereador ou de presidente da Câmara (comum.eh_vereador). Prefeito e vice: na
  Prefeitura, o cargo de prefeito ou de vice (cargo.papel_prefeitura); com uma pessoa só no cargo, o total é o valor
  dela.
- O total não separa 13º nem férias: um mês com valor maior (dezembro) pode ter 13º.
"""
import re
import time

from bs4 import BeautifulSoup

from ..config import HOJE
from ..util import (SessaoEducada, TempoEsgotado, USER_AGENT, ca_com_intermediario, dormir, log, numero_br,
                    verificar_prazo)
from . import cargo, comum

UF = "PE"
TOME = "https://tomeconta.tce.pe.gov.br/dados/"
TOME_HOST = "tomeconta.tce.pe.gov.br"
API_UJ = "https://sistemas.tce.pe.gov.br/DadosAbertos/UnidadesJurisdicionadas!json"
CACHE = comum.CACHE_TCE / "pe"
MESES = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"]
NATUREZA = {"Câmara Municipal": "camara", "Prefeitura Municipal": "prefeitura"}
# nomes que o TCE-PE escreve diferente do IBGE (chave do nome no TCE -> nome no IBGE)
NOMES_DIFERENTES = {"BELEM DE SAO FRANCISCO": "Belém do São Francisco", "SAO CAETANO": "São Caitano"}
PAUSA = 0.5          # segundos entre os pedidos ao Tome Conta (um por vez)
MAX_PEDIDOS = 2000   # pedidos por rodada (a semana normal: os 2 últimos meses e os que vieram vazios, ~1.000)
FALHAS_MAX = 5       # blocos seguidos com erro: para (o tribunal pode estar bloqueando) e a fonte fica como falhando
_CPF = re.compile(r"\*{3}\.?\d{3}\.?\d{3}-?\*{2}|\d{3}\.?\d{3}\.?\d{3}-?\d{2}")
_s = None


def _sessao():
    global _s
    if _s is None:
        _s = SessaoEducada()  # lê o robots.txt e respeita o Crawl-delay
        _s.headers["User-Agent"] = USER_AGENT
        _s.verify = ca_com_intermediario(TOME_HOST, "tcepe")
    return _s


def _pedir(url, params=None):
    verificar_prazo()
    for tentativa in range(3):
        try:
            r = _sessao().get(url, params=params, timeout=120)
            if r.status_code in (429, 500, 502, 503, 504):
                raise RuntimeError(f"HTTP {r.status_code}")
            r.raise_for_status()
            dormir(PAUSA)
            r.encoding = "latin1" if "tomeconta" in url else r.encoding
            return r
        except TempoEsgotado:
            raise
        except Exception:  # noqa: BLE001
            if tentativa == 2:
                raise
            dormir(5 * (tentativa + 1))


def unidades():
    """[(cod_ibge, nome da cidade, orgao, id da unidade no TCE-PE, código do município no TCE-PE ("P001"))] das câmaras
    e prefeituras ativas (a lista fica no cache por 30 dias)."""
    import json
    arq = CACHE / "unidades.json"
    if arq.exists() and time.time() - arq.stat().st_mtime < 30 * 86400:
        d = json.loads(arq.read_text(encoding="utf-8"))
    else:
        d = _pedir(API_UJ).json()["resposta"]["conteudo"]
        CACHE.mkdir(parents=True, exist_ok=True)
        arq.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    cid = comum.municipios(UF)
    cid.update({k: cid[comum.chave_cidade(v)] for k, v in NOMES_DIFERENTES.items()})
    saida, sem = [], set()
    for x in d:
        orgao = NATUREZA.get(x.get("NATUREZA"))
        if not orgao or x.get("SITUACAO") != "Ativa" or x.get("UNIDADEFEDERATIVA") != "PE":
            continue
        c = cid.get(comum.chave_cidade(x["MUNICIPIO"]))
        if c is None:
            sem.add(x["MUNICIPIO"])
            continue
        saida.append((c[0], c[1], orgao, str(x["ID_UNIDADE_GESTORA"]), x["CODIGOMUNICIPIO"]))
    if sem:
        log(f"  TCE-PE: {len(sem)} municípios sem código do IBGE: {', '.join(sorted(sem))}")
    return saida


def link(cod_mun):
    return f"{TOME}PessoalFolhaPagamento!principal?municipio.codigo={cod_mun}"


def tabela(cod_mun, id_ug, am):
    """(pessoas na folha do mês, [(cargo, quantidade, total, endereço da lista de nomes)]) de uma unidade num mês."""
    p = {"municipio.codigo": cod_mun, "unidadeJuris.codigoMunUG": cod_mun, "municipioAlterado": id_ug,
         "exercicioAlterado": str(am // 100), "mesAlterado": MESES[am % 100 - 1], "modalidades": "FOLHA DE PAGAMENTO",
         "cargoOuTipoVinculo": "true", "tipoVinculoCSS": "C", "page": "1", "perPage": "5000"}
    r = _pedir(TOME + "PessoalFolhaPagamento!paginaVisualizarAjax", p)
    total = re.search(r"idTotalPessoas'\)\.innerHTML = '[^'(]*\((\d+)\)'", r.text)
    sopa = BeautifulSoup(r.text, "lxml")
    linhas = sopa.select("table.tabDados tr")
    if not linhas or not linhas[0].get_text(" ", strip=True).startswith("Cargo"):
        raise RuntimeError(f"TCE-PE: a tabela por cargo não veio ({cod_mun}, unidade {id_ug}, {am}): o leiaute mudou?")
    saida = []
    for tr in linhas[1:]:
        tds = tr.select("td")
        if len(tds) < 3:
            continue
        a = tds[1].select_one("a")
        q = int(re.sub(r"\D", "", tds[1].get_text()) or 0)
        saida.append((cargo.limpar_cargo(tds[0].get_text(" ", strip=True)), q, numero_br(tds[2].get_text(strip=True)),
                      a["href"] if a and a.get("href") else None))
    return (int(total.group(1)) if total else len(saida)), saida


def nomes(href):
    """[(nome, cargo)] da lista de quem estava no cargo (a página de detalhes do Tome Conta), sem o CPF mascarado."""
    # com a data de atualização da unidade preenchida (como vem em algumas cidades), a página volta vazia
    href = re.sub(r"(unidadeJuris\.dataUltimaAtualizacao=)[^&]*", r"\1", href)
    url = "https://" + TOME_HOST + href + ("&" if "?" in href else "?") + "perPage=500"
    r = _pedir(url)
    sopa = BeautifulSoup(r.text, "lxml")
    saida = []
    for tr in sopa.select("table tr")[1:]:
        tds = [td.get_text(" ", strip=True) for td in tr.select("td")]
        if len(tds) < 3:
            continue
        nome = re.sub(r"\s+", " ", _CPF.sub("", tds[1])).strip().upper()
        cargo_ = re.sub(r"\s+(Eletivo|Efetivo.*|Cargo Comissionado|Contrata.*)$", "", tds[2]).strip()
        if nome and not re.search(r"\d", nome):
            saida.append((nome, cargo.limpar_cargo(cargo_)))
    return saida


def disponiveis():
    """Os meses desde jan/2025 até o mês passado (o mês que o município ainda não mandou vem vazio e é lido de novo)."""
    ate = comum.mes_mais(HOJE.year * 100 + HOJE.month, -1)
    return comum.meses(comum.INICIO, ate)


def coletar():
    ujs = unidades()
    por = {(c, o): (nome, idu, cm) for c, nome, o, idu, cm in ujs}
    fazer = comum.blocos_a_fazer(UF, sorted({c for c, *_ in ujs}), ["camara", "prefeitura"], disponiveis())
    fazer = sorted((k for k in fazer if (k[0], k[1]) in por), key=lambda k: (-k[2], k[0], k[1]))
    if not fazer:
        log("  TCE-PE: nada a ler")
        return 0
    log(f"  TCE-PE: {len(fazer)} blocos (cidade, órgão e mês) a ler; no máximo {MAX_PEDIDOS} pedidos nesta rodada")
    gravados = cargo.ler_nomes(UF)
    ult_nomes = {}
    if len(gravados):
        for (c, o), g in gravados.groupby(["cod_ibge", "orgao"]):
            ult_nomes[(int(c), o)] = int(g.ano_mes.max())
    linhas, blocos, ls_nomes, bl_nomes = [], [], [], []
    total, pedidos, seguidos, feitos = 0, 0, 0, 0

    def salvar():
        nonlocal total
        if blocos:
            n, _ = cargo.gravar(UF, linhas, blocos, ls_nomes, [(b[0], b[1], b[2]) for b in bl_nomes])
            total = n
        for lista in (linhas, blocos, ls_nomes, bl_nomes):
            lista.clear()

    try:
        for c, o, am in fazer:
            if pedidos >= MAX_PEDIDOS:
                log(f"  TCE-PE: {MAX_PEDIDOS} pedidos nesta rodada; faltam {len(fazer) - feitos} blocos para a próxima")
                break
            nome_cid, idu, cm = por[(c, o)]
            try:
                n_pessoas, cargos = tabela(cm, idu, am)
                pedidos += 1
            except TempoEsgotado:
                raise
            except Exception as e:  # noqa: BLE001
                pedidos += 1
                seguidos += 1
                log(f"  TCE-PE {nome_cid} ({o}, {am}): {e}")
                if seguidos >= FALHAS_MAX:
                    raise RuntimeError(f"TCE-PE: {seguidos} blocos seguidos com erro; o último: {e}")
                continue
            seguidos = 0
            por_papel = {}
            for cg, q, v, href in cargos:
                papel = cargo.papel_camara(cg) if o == "camara" else cargo.papel_prefeitura(cg)
                if papel:
                    por_papel.setdefault(papel, []).append((cg, q, v, href))
            # os nomes: no mês mais recente com o cargo em cada cidade e órgão (uma vez: a releitura semanal do mesmo
            # mês não pede os nomes de novo) e, nos outros meses, quando o papel tem mais de um cargo (o presidente da
            # Câmara costuma aparecer como VEREADOR e de novo como PRESIDENTE: a quantidade do papel é a de nomes
            # diferentes, e não a soma dos cargos)
            ultimo = bool(por_papel) and am > ult_nomes.get((c, o), 0)
            lidos = False
            for papel, lista in por_papel.items():
                pessoas = None
                if ultimo or len(lista) > 1:
                    ns, falhou = [], False
                    for cg, q, v, href in lista:
                        if href:
                            pedidos += 1
                            try:
                                ns += [(n, cgn or cg) for n, cgn in nomes(href)]
                            except TempoEsgotado:
                                raise
                            except Exception as e:  # noqa: BLE001 — sem a lista, fica a quantidade da tabela
                                log(f"  TCE-PE {nome_cid} ({o}, {am}): a lista de nomes de {cg} não veio ({e})")
                                falhou = True
                    if falhou:  # os nomes gravados antes (se houver) ficam; volta a tentar na próxima rodada
                        ultimo = False
                    else:
                        ls_nomes.extend({"cod_ibge": c, "orgao": o, "ano_mes": am, "papel": papel, "nome": n,
                                         "cargo": cg} for n, cg in dict.fromkeys(ns))
                        lidos = True
                        pessoas = len({n for n, _ in ns}) or None
                linhas.append({"cod_ibge": c, "municipio": nome_cid, "orgao": o, "ano_mes": am, "papel": papel,
                               "cargo": " / ".join(dict.fromkeys(cg for cg, *_ in lista)),
                               "quantidade": pessoas or sum(q for _, q, _, _ in lista),
                               "valor_total": round(sum(v or 0 for _, _, v, _ in lista), 2), "indenizatorio": None,
                               "decimo": None, "ferias": None, "unidade": None})
            if lidos:
                bl_nomes.append((c, o, am))
            if ultimo:
                ult_nomes[(c, o)] = am
            blocos.append({"cod_ibge": c, "orgao": o, "ano_mes": am, "linhas_fonte": n_pessoas,
                           "pessoas": sum(l["quantidade"] for l in linhas[-len(por_papel):]) if por_papel else 0,
                           "url": link(cm), "lido_em": comum.agora()})
            feitos += 1
            if feitos % 40 == 0:
                salvar()
                log(f"  TCE-PE: {feitos}/{len(fazer)} blocos, {pedidos} pedidos")
    finally:
        salvar()
    return total


CFG = {
    "tribunal": "TCE-PE",
    "fonte": "Tribunal de Contas do Estado de Pernambuco (TCE-PE), Tome Conta: a folha que cada município manda ao "
             "Tribunal (sistema Sagres), com a quantidade de pessoas e o total das vantagens de cada cargo, por mês",
    "url": TOME + "PessoalFolhaPagamento!principal",
    "nota": "O Tribunal de Contas de Pernambuco publica, para cada Câmara e Prefeitura e cada mês, o total pago a cada "
            "cargo (a soma de todas as pessoas, antes dos descontos) e quem estava no cargo. Não publica o valor de cada "
            "vereador: o valor por pessoa é uma média (o total do cargo dividido pela quantidade de pessoas), e não o "
            "salário de um vereador. Para prefeito e vice, com uma pessoa só no cargo, o total é o valor dela.",
    "notas": ["O total não separa salário, 13º e férias: um mês com valor maior (dezembro, por exemplo) pode ter 13º ou "
              "férias.",
              "A quantidade é a de pessoas naquele cargo na folha do mês; pode ser diferente do número de cadeiras "
              "(suplente que assumiu, quem saiu no meio do mês).",
              "Cada município manda a sua folha ao Tribunal todo mês; o mês que ainda não foi mandado aparece sem valor.",
              "Os nomes são os do último mês de cada cidade. Partido: o da eleição de 2024 (TSE), quando o nome da folha "
              "é o de um único candidato da cidade."],
    "orgaos": ("camara", "prefeitura"),
    "link": None,
}
_links = {}


def _link_cidade(cod):
    if not _links:
        try:
            _links.update({c: link(cm) for c, _, o, _, cm in unidades() if o == "prefeitura"})
        except Exception:  # noqa: BLE001 — sem a lista, a cidade fica com o link geral
            pass
    return _links.get(cod)


CFG["link"] = _link_cidade


def montar():
    return cargo.montar_site(UF, CFG)


checar = cargo.checar
