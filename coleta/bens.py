"""Bens declarados à Justiça Eleitoral na candidatura, por quem está no cargo: Portal de Dados Abertos do TSE, licença
Creative Commons Atribuição (como as fotos das candidaturas).

Fontes: as declarações de bens das candidaturas (https://dadosabertos.tse.jus.br/dataset/candidatos-<ano>, arquivo
bem_candidato_<ano>.zip) cruzadas com o arquivo de candidatos do mesmo ano (consulta_cand_<ano>.zip) pelo SQ do
candidato. Eleições: 2022 (deputados federais e estaduais, senadores eleitos em 2022, governadores e vices), 2018
(senadores eleitos em 2018) e 2024 (prefeitos, vices e vereadores das capitais e das cidades do interior que o site
mostra pessoa por pessoa ou por cargo com os nomes). Só as eleições ordinárias: nada de eleição suplementar nem de 2026.

Ligação com as pessoas do site: o mesmo critério das fotos do TSE (coleta/fotos_tse.py): o nome civil exatamente igual
ao de um único candidato do mesmo cargo e lugar (UF; na eleição municipal, também a cidade) ou, sem ele, o nome de urna
exatamente igual ao de um único candidato. Homônimo ou dúvida fica sem.

O que se guarda, por pessoa: o ano da declaração, o total, o número de itens e o total por tipo de bem (imóveis,
veículos, aplicações e depósitos, participações em empresas, outros), e o link da página do candidato no
DivulgaCandContas. Nunca a descrição de cada bem (endereços, contas, nomes de terceiros) nem o CPF: a coluna de CPF do
arquivo de candidatos não é lida. Saída: dados/bens/declaracoes.csv e dados/bens/resumo.json.

O site só mostra a partir de 26/10/2026 (regra eleitoral): exportar_site(), chamado pela etapa `site`, só grava
site/dados/bens.json e site/dados/bens-interior/<uf>.json a partir dessa data.
"""
import csv
import io
import json
import zipfile
from collections import Counter, defaultdict
from datetime import date

from .config import CACHE, DADOS, RAIZ
from .util import baixar, cache_valido, log, normalizar_nome, salvar_json

TSE = "https://cdn.tse.jus.br/estatistica/sead/odsele"
C = CACHE / "bens"
SAIDA = DADOS / "bens"
SITE = RAIZ / "site" / "dados"
DESDE = date(2026, 10, 26)  # o site só mostra os bens declarados a partir desta data
PAGINA = "https://dadosabertos.tse.jus.br/dataset/candidatos-{ano}"
LICENCA = "CC BY (Creative Commons Atribuição)"
CREDITO = "Tribunal Superior Eleitoral, Portal de Dados Abertos (declarações de bens das candidaturas), licença CC BY"
# eleições ordinárias de cada ano (CD_ELEICAO nos arquivos do TSE) e o código da mesma eleição no DivulgaCandContas
ELEICOES = {2018: {"297", "298"}, 2022: {"546", "547"}, 2024: {"619", "620"}}
DIVULGA = {2018: "2022802018", 2022: "2040602022", 2024: "2045202024"}
# a página do candidato: região (maiúsculas, sem acento), UF, código da eleição, SQ, ano e UE (a UF nas eleições gerais,
# o código TSE do município em 2024), formato conferido num navegador em 03/10/2026
LINK = "https://divulgacandcontas.tse.jus.br/divulga/#/candidato/{regiao}/{uf}/{eleicao}/{sq}/{ano}/{ue}"
REGIOES = {**{u: "NORTE" for u in ("AC", "AM", "AP", "PA", "RO", "RR", "TO")},
           **{u: "NORDESTE" for u in ("AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE")},
           **{u: "CENTROOESTE" for u in ("DF", "GO", "MS", "MT")},
           **{u: "SUDESTE" for u in ("ES", "MG", "RJ", "SP")},
           **{u: "SUL" for u in ("PR", "RS", "SC")}}
# tipo de bem (código da Receita Federal usado pelo TSE) -> grupo; o resto é "outros"
GRUPOS = ["imoveis", "veiculos", "aplicacoes", "participacoes", "outros"]
NOMES_GRUPOS = {"imoveis": "Imóveis", "veiculos": "Veículos", "aplicacoes": "Aplicações e depósitos",
                "participacoes": "Participações em empresas", "outros": "Outros bens e direitos"}
TIPO = {**{c: "imoveis" for c in (1, 2, 3, 11, 12, 13, 14, 15, 16, 17, 18, 19)},
        **{c: "veiculos" for c in (21, 22, 23)},
        **{c: "aplicacoes" for c in (41, 45, 46, 47, 49, 53, 54, 59, 61, 62, 63, 64, 69, 71, 72, 73, 74, 79, 97)},
        **{c: "participacoes" for c in (31, 32, 39)}}
# cargos do TSE: 3 governador, 4 vice, 5 senador, 6 dep. federal, 7 estadual, 8 distrital, 9 e 10 suplentes de senador,
# 11 prefeito, 12 vice-prefeito, 13 vereador
CARGOS = {"dep": {"6"}, "sen": {"5", "9", "10"}, "gov": {"3", "4"}, "est": {"7", "8"}, "pre": {"11", "12"}, "ver": {"13"}}


def _arquivo(tipo, ano):
    """O zip do TSE (consulta_cand ou bem_candidato), guardado no cache por 30 dias."""
    arq = C / f"{tipo}_{ano}.zip"
    if not cache_valido(arq, 30):
        r = baixar(f"{TSE}/{tipo}/{tipo}_{ano}.zip", timeout=900)
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_bytes(r.content)
    return arq


def _linhas(arq, prefixo, uf):
    with zipfile.ZipFile(arq) as z:
        nome = f"{prefixo}_{uf}.csv"
        if nome not in z.namelist():
            return
        with z.open(nome) as f:
            yield from csv.DictReader(io.TextIOWrapper(f, encoding="latin1"), delimiter=";")


_cand = {}


def _candidatos(ano, uf):
    """{(ue normalizada, cargo): {"civil": {nome: [SQ]}, "urna": {nome: [SQ]}}} e {SQ: (SG_UE, NM_UE, CD_CARGO)}, das
    eleições ordinárias. A coluna de CPF não é lida."""
    if (ano, uf) in _cand:
        return _cand[(ano, uf)]
    idx, info = defaultdict(lambda: {"civil": defaultdict(list), "urna": defaultdict(list)}), {}
    for l in _linhas(_arquivo("consulta_cand", ano), f"consulta_cand_{ano}", uf):
        if l["CD_ELEICAO"] not in ELEICOES[ano]:
            continue
        sq = l["SQ_CANDIDATO"]
        ue = normalizar_nome(l["NM_UE"]) if ano == 2024 else uf
        grupo = idx[(ue, l["CD_CARGO"])]
        for chave, campo in (("civil", "NM_CANDIDATO"), ("urna", "NM_URNA_CANDIDATO")):
            lista = grupo[chave][normalizar_nome(l[campo])]
            if sq not in lista:
                lista.append(sq)
        info[sq] = (l["SG_UE"], l["NM_UE"], l["CD_CARGO"])
    _cand[(ano, uf)] = (idx, info)
    return idx, info


def _casar(ano, uf, cargos, pessoa, cidade=None):
    """(SQ, motivo): o SQ do único candidato com o nome civil (ou, sem ele, o nome de urna) da pessoa, ou (None, por
    que não)."""
    idx, _ = _candidatos(ano, uf)
    ue = normalizar_nome(cidade) if cidade else uf
    grupos = [idx[(ue, c)] for c in cargos if (ue, c) in idx]
    if not grupos:
        return None, "cidade não achada no arquivo do TSE" if cidade else "cargo sem candidatos no arquivo"
    for chave, nome in (("civil", pessoa.get("nc")), ("urna", pessoa.get("n"))):
        if not nome:
            continue
        sqs = sorted({sq for g in grupos for sq in g[chave].get(normalizar_nome(nome), [])})
        if len(sqs) == 1:
            return sqs[0], None
        if len(sqs) > 1:
            return None, "homônimo (mais de um candidato com o mesmo nome)"
    return None, "nenhum candidato com o mesmo nome"


_bens = {}


def _declaracoes(ano, uf, sqs):
    """{SQ: {"itens", "total", grupos...}} dos SQs pedidos, das eleições ordinárias. A descrição de cada bem não é lida."""
    chave = (ano, uf)
    if chave not in _bens:
        por = {}
        for l in _linhas(_arquivo("bem_candidato", ano), f"bem_candidato_{ano}", uf):
            if l["CD_ELEICAO"] not in ELEICOES[ano]:
                continue
            d = por.setdefault(l["SQ_CANDIDATO"], {"itens": 0, "total": 0.0, **{g: 0.0 for g in GRUPOS}})
            v = float((l["VR_BEM_CANDIDATO"] or "0").replace(".", "").replace(",", ".")) if "," in (l["VR_BEM_CANDIDATO"] or "") \
                else float(l["VR_BEM_CANDIDATO"] or 0)
            g = TIPO.get(int(l["CD_TIPO_BEM_CANDIDATO"] or 0), "outros")
            d["itens"] += 1
            d["total"] += v
            d[g] += v
        _bens[chave] = por
    return {sq: _bens[chave].get(sq) for sq in sqs}


def _slug(nome):
    from .governadores import _slug as slug
    return slug(nome)


def _mandato_senador(cod):
    """(ano da eleição, cargos no TSE) do mandato atual do senador, pelos mandatos do Senado (dados/cache/senado):
    eleito em 2018 se a 2ª legislatura do mandato é a 57ª, em 2022 se é a 1ª; titular = cargo 5, 1º suplente = 9,
    2º suplente = 10. Sem o mandato, (None, ...): fica sem."""
    from .config import LEGISLATURA
    from .senado import C as CS, _como_lista
    arq = CS / "mandatos" / f"{cod}.json"
    if not arq.exists():
        from .senado import _exercicios
        _exercicios(cod)
    try:
        d = json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, set()
    for m in _como_lista(d.get("MandatoParlamentar", {}).get("Parlamentar", {}).get("Mandatos", {}).get("Mandato")):
        leg1 = str((m.get("PrimeiraLegislaturaDoMandato") or {}).get("NumeroLegislatura"))
        leg2 = str((m.get("SegundaLegislaturaDoMandato") or {}).get("NumeroLegislatura"))
        if str(LEGISLATURA) not in (leg1, leg2):
            continue
        part = (m.get("DescricaoParticipacao") or "").lower()
        cargos = {"9"} if part.startswith("1") else {"10"} if part.startswith("2") else {"5"}
        return (2022 if leg1 == str(LEGISLATURA) else 2018), cargos
    return None, set()


def _pessoas():
    """[(grupo, chave, uf, cidade ou None, ano(s), cargos, {n, nc})] de quem está no cargo, pelos arquivos do site."""
    ler = lambda n: json.loads((SITE / n).read_text(encoding="utf-8")) if (SITE / n).exists() else {}
    cidades = {str(m[0]): m[1] for m in ler("municipios.json").get("m", [])}
    saida = []
    for p in ler("dados.json").get("p", []):
        if p.get("x") not in (1, "1"):
            continue
        if p["k"] == "d":
            saida.append(("deputados federais", p["id"], p["uf"], None, (2022,), CARGOS["dep"], p))
        elif p["k"] == "s":
            ano, cargos = _mandato_senador(p["id"].split("-", 1)[1])
            saida.append(("senadores", p["id"], p["uf"], None, (ano,) if ano else (), cargos, p))
    # governadores: o nome civil vem do arquivo curado ("civil" ou o nome na folha do Estado, "folha_nome")
    curado = json.loads((DADOS / "governadores" / "governadores.json").read_text(encoding="utf-8"))
    civis = {}
    for e in curado:
        for o in e["ocupantes"]:
            civis.setdefault(f"gov-{e['uf'].lower()}-{_slug(o['nome'])}", o.get("civil") or o.get("folha_nome"))
    for e in ler("governadores.json").get("e", []):
        for o in (e.get("gov"), e.get("vice")):
            if o:
                saida.append(("governadores e vices", o["id"], e["uf"], None, (2022,), CARGOS["gov"],
                              {**o, "nc": o.get("nc") or civis.get(o["id"])}))
    for p in ler("assembleias.json").get("p", []):
        if p.get("x") in (1, "1"):
            saida.append(("deputados estaduais", p["id"], p["uf"], None, (2022,), CARGOS["est"], p))
    for p in ler("camaras.json").get("p", []):
        if p.get("x") in (1, "1"):
            saida.append(("vereadores das capitais", p["id"], p["uf"], cidades.get(str(p["cid"])), (2024,), CARGOS["ver"], p))
    for p in ler("prefeituras.json").get("p", []):
        if p.get("tp") in ("pr", "vp") and p.get("x") in (1, "1"):
            saida.append(("prefeitos e vices das capitais", p["id"], p["uf"], cidades.get(str(p["cid"])), (2024,), CARGOS["pre"], p))
    # interior: a chave é "<código IBGE>|<nome como no arquivo do site>"
    for pasta, blocos in (("interior", {"v": "ver", "pf": "pre", "vp": "pre"}), ("interior-cargo", {"c": "ver", "pf": "pre", "vp": "pre"})):
        for arq in sorted((SITE / pasta).glob("*.json")) if (SITE / pasta).exists() else []:
            d = ler(f"{pasta}/{arq.name}")
            uf = d.get("meta", {}).get("uf") or arq.stem.upper()
            for cid, m in d.get("m", {}).items():
                for bloco, cargo in blocos.items():
                    lista = m.get(bloco)
                    if isinstance(lista, dict):  # valor por cargo: os nomes do último mês em "ps"
                        lista = [{**x, "x": 1} for x in lista.get("ps") or []]
                    for p in lista or []:
                        if p.get("x") in (1, "1") and (p.get("nc") or p.get("n")):
                            grupo = "vereadores do interior" if cargo == "ver" else "prefeitos e vices do interior"
                            saida.append((grupo, f"{cid}|{p.get('nc') or p.get('n')}", uf, m.get("n") or cidades.get(cid), (2024,),
                                          CARGOS[cargo], p))
    return saida


def coletar():
    """Liga cada pessoa no cargo a uma candidatura e grava dados/bens/declaracoes.csv e resumo.json. Falha aqui não
    para a rodada (o dado é opcional)."""
    try:
        return _coletar()
    except Exception as e:  # noqa: BLE001
        log(f"Bens declarados: a coleta falhou ({type(e).__name__}: {e}); fica o que já estava gravado")
        return 0


def _coletar():
    pessoas = _pessoas()
    contagem = defaultdict(Counter)
    linhas, casados = [], []
    vistos = Counter(chave for _, chave, *_ in pessoas)
    for grupo, chave, uf, cidade, anos, cargos, p in pessoas:
        contagem[grupo]["no cargo"] += 1
        if vistos[chave] > 1:  # duas pessoas com o mesmo nome na mesma cidade (interior): fica sem
            contagem[grupo]["sem: duas pessoas com o mesmo nome no site"] += 1
            continue
        sq, motivo, ano = None, "sem o mandato no Senado para saber o ano da eleição", None
        for ano in anos:
            sq, motivo = _casar(ano, uf, cargos, p, cidade)
            if sq:
                break
        if not sq:
            contagem[grupo][f"sem: {motivo}"] += 1
            continue
        casados.append((grupo, chave, uf, ano, sq))
    por_ano_uf = defaultdict(set)
    for _, _, uf, ano, sq in casados:
        por_ano_uf[(ano, uf)].add(sq)
    decl = {}
    for (ano, uf), sqs in por_ano_uf.items():
        for sq, d in _declaracoes(ano, uf, sqs).items():
            decl[(ano, sq)] = d
    for grupo, chave, uf, ano, sq in casados:
        _, info = _candidatos(ano, uf)
        ue, nm_ue, cargo = info[sq]
        d = decl.get((ano, sq)) or {"itens": 0, "total": 0.0, **{g: 0.0 for g in GRUPOS}}
        contagem[grupo]["com declaração" if d["itens"] else "candidatura sem bens no arquivo do TSE"] += 1
        linhas.append({"chave": chave, "grupo": grupo, "uf": uf, "ano": ano, "sq": sq, "cargo_tse": cargo, "ue": ue,
                       "municipio": nm_ue if ano == 2024 else "", "itens": d["itens"], "total": round(d["total"], 2),
                       **{g: round(d[g], 2) for g in GRUPOS},
                       "link": LINK.format(regiao=REGIOES[uf], uf=uf, eleicao=DIVULGA[ano], sq=sq, ano=ano, ue=ue)})
    SAIDA.mkdir(parents=True, exist_ok=True)
    campos = ["chave", "grupo", "uf", "ano", "sq", "cargo_tse", "ue", "municipio", "itens", "total", *GRUPOS, "link"]
    with open(SAIDA / "declaracoes.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, campos)
        w.writeheader()
        w.writerows(sorted(linhas, key=lambda l: (l["grupo"], l["chave"])))
    resumo = {"gerado_em": date.today().isoformat(), "fonte": [PAGINA.format(ano=a) for a in sorted(ELEICOES)],
              "grupos": {g: dict(c) for g, c in sorted(contagem.items())}}
    salvar_json(SAIDA / "resumo.json", resumo)
    for g, c in sorted(contagem.items()):
        log(f"Bens declarados, {g}: {c['no cargo']} no cargo, {c['com declaração']} com declaração")
    return len(linhas)


def exportar_site(hoje=None):
    """site/dados/bens.json (quem tem página no site) e site/dados/bens-interior/<uf>.json (interior, pela cidade e pelo
    nome), só a partir de DESDE (26/10/2026). Antes disso, não grava nada."""
    hoje = hoje or date.today()
    if hoje < DESDE:
        log(f"Bens declarados: o site só mostra a partir de {DESDE:%d/%m/%Y}; arquivo do site não gerado")
        return False
    arq = SAIDA / "declaracoes.csv"
    if not arq.exists():
        return False
    with open(arq, encoding="utf-8", newline="") as f:
        linhas = list(csv.DictReader(f))
    num = lambda v: int(float(v)) if float(v) == int(float(v)) else round(float(v), 2)
    reg = lambda l: [int(l["ano"]), num(l["total"]), int(l["itens"]), *[num(l[g]) for g in GRUPOS], l["ue"], l["sq"]]
    meta = {"gerado_em": date.today().isoformat(), "credito": CREDITO, "licenca": LICENCA,
            "fontes": {str(a): PAGINA.format(ano=a) for a in sorted(ELEICOES)},
            "campos": ["ano da eleição", "total declarado (R$)", "número de itens", *[NOMES_GRUPOS[g] for g in GRUPOS],
                       "ue (o lugar da candidatura no TSE)", "sq (o número da candidatura no TSE)"],
            "grupos": NOMES_GRUPOS,
            # a página do candidato no DivulgaCandContas: LINK com a região da UF (regiao), a UF, o código da eleição
            # (eleicao[ano]), o SQ, o ano e a UE
            "link": LINK, "eleicao": {str(a): c for a, c in DIVULGA.items()}, "regiao": REGIOES}
    pessoas = {l["chave"]: reg(l) for l in linhas if "|" not in l["chave"]}
    (SITE / "bens.json").write_text(json.dumps({"meta": meta, "p": pessoas}, ensure_ascii=False, separators=(",", ":")) + "\n",
                                    encoding="utf-8")
    interior = defaultdict(lambda: defaultdict(dict))
    for l in linhas:
        if "|" in l["chave"]:
            cid, nome = l["chave"].split("|", 1)
            interior[l["uf"].lower()][cid][nome] = reg(l)
    pasta = SITE / "bens-interior"
    pasta.mkdir(exist_ok=True)
    for uf, m in interior.items():
        (pasta / f"{uf}.json").write_text(json.dumps({"meta": meta, "m": m}, ensure_ascii=False, separators=(",", ":")) + "\n",
                                          encoding="utf-8")
    log(f"Bens declarados: {len(pessoas)} pessoas em site/dados/bens.json e o interior de {', '.join(sorted(interior)).upper()}")
    return True
