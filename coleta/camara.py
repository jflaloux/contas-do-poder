"""Robô da Câmara dos Deputados.

Fontes:
- API de dados abertos: lista e dados pessoais dos deputados
  https://dadosabertos.camara.leg.br/swagger/api.html
- Arquivos anuais da Cota Parlamentar (CEAP): https://www.camara.leg.br/cotas/Ano-AAAA.csv.zip
- Página principal de cada deputado: verba de gabinete usada em cada mês
  https://www.camara.leg.br/deputados/ID?ano=AAAA
- Auxílio-moradia e imóvel funcional: https://www.camara.leg.br/moradia/detalhamento

O robots.txt da Câmara (desde 18/09/2026) não deixa robôs abrirem /deputados/ID/... (as páginas de salário, de verba
de gabinete e de pessoal de gabinete de cada deputado). Por isso, desde 30/09/2026:
- salário: até set/2026, o que essas páginas mostravam (guardado em dados/camara/remuneracao_paginas.csv); depois, o
  subsídio fixado em lei (Decreto Legislativo 172/2022) nos meses em que o deputado estava em exercício, pelo histórico
  da API de dados abertos;
- equipe do gabinete: até set/2026, contada nas páginas de pessoal (dados/camara/pessoal_paginas.csv); depois, sem dado;
- verba de gabinete: pela página principal do deputado, que o robots.txt permite.
O 13º, as férias e as diárias só aparecem nas páginas proibidas: ficam de fora até a Câmara autorizar.
"""
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests
from bs4 import BeautifulSoup

from .config import ANOS, BRUTOS, CACHE, DADOS, HOJE, INICIO_LEGISLATURA, LEGISLATURA, PARALELO, ULTIMO_MES, meses_da_legislatura
from .util import TempoEsgotado, baixar, cache_valido, ler_json, log, numero_br, salvar_json

API = "https://dadosabertos.camara.leg.br/api/v2"
SITE = "https://www.camara.leg.br"
C = CACHE / "camara"
JSON = {"Accept": "application/json"}


# ---------------------------------------------------------------- deputados
def _lista(params):
    saida, pagina = [], 1
    while True:
        r = baixar(f"{API}/deputados", params={**params, "itens": 100, "pagina": pagina}, headers=JSON)
        dados = r.json()["dados"]
        if not dados:
            return saida
        saida += dados
        pagina += 1


def _detalhe(id_):
    arq = C / "detalhe" / f"{id_}.json"
    if cache_valido(arq, 30):
        return ler_json(arq)
    d = baixar(f"{API}/deputados/{id_}", headers=JSON).json()["dados"]
    salvar_json(arq, d)
    return d


def deputados():
    """Quem exerceu mandato na legislatura atual (inclui suplentes que assumiram)."""
    arq = BRUTOS / "camara_deputados.json"
    if cache_valido(arq, 1):
        return ler_json(arq)
    log("Câmara: lista de deputados")
    da_legislatura = _lista({"idLegislatura": LEGISLATURA, "ordem": "ASC", "ordenarPor": "nome"})
    em_exercicio = {d["id"]: d for d in _lista({"ordem": "ASC", "ordenarPor": "nome"})}
    unicos = {}
    for d in da_legislatura:
        unicos[d["id"]] = d
    unicos.update(em_exercicio)  # partido/UF mais recentes para quem está no cargo
    log(f"Câmara: {len(unicos)} deputados na legislatura, {len(em_exercicio)} em exercício. Buscando detalhes...")

    detalhes = {}
    with ThreadPoolExecutor(PARALELO) as ex:
        futuros = {ex.submit(_detalhe, i): i for i in unicos}
        for f in as_completed(futuros):
            detalhes[futuros[f]] = f.result()

    saida = []
    for id_, d in sorted(unicos.items(), key=lambda x: x[1]["nome"]):
        det = detalhes.get(id_, {})
        status = det.get("ultimoStatus") or {}
        saida.append({
            "id": id_,
            "nome": d["nome"],
            "nome_civil": det.get("nomeCivil"),
            "sexo": det.get("sexo"),
            "partido": d.get("siglaPartido"),
            "uf": d.get("siglaUf"),
            "foto": d.get("urlFoto"),
            "em_exercicio": id_ in em_exercicio,
            "situacao": status.get("situacao"),
            "condicao_eleitoral": status.get("condicaoEleitoral"),
            "data_nascimento": det.get("dataNascimento"),
            "municipio_nascimento": det.get("municipioNascimento"),
            "uf_nascimento": det.get("ufNascimento"),
            "escolaridade": det.get("escolaridade"),
            "pagina_oficial": f"{SITE}/deputados/{id_}",
        })
    salvar_json(arq, saida)
    return saida


# ---------------------------------------------------------------- cota parlamentar
def cota():
    """Soma, por deputado, mês e tipo de despesa, o valor líquido reembolsado pela cota."""
    partes = []
    for ano in ANOS:
        arq = C / "cota" / f"Ano-{ano}.csv.zip"
        idade = 1 if ano == HOJE.year else 30
        if not cache_valido(arq, idade):
            log(f"Câmara: baixando cota parlamentar {ano}")
            r = baixar(f"{SITE}/cotas/Ano-{ano}.csv.zip", timeout=600)
            arq.parent.mkdir(parents=True, exist_ok=True)
            arq.write_bytes(r.content)
        with zipfile.ZipFile(arq) as z:
            df = pd.read_csv(z.open(z.namelist()[0]), sep=";", dtype=str, encoding="utf-8")
        df = df[df["ideCadastro"].notna() & (df["codLegislatura"] == str(LEGISLATURA))].copy()
        df["valor"] = pd.to_numeric(df["vlrLiquido"], errors="coerce").fillna(0.0)
        # Nos arquivos, a complementação do auxílio-moradia vem com sinal negativo, mas é um gasto
        # da cota (o site oficial soma como positivo).
        compl = df["txtDescricao"].str.contains("COMPLEMENTAÇÃO DO AUXÍLIO-MORADIA", na=False)
        df.loc[compl, "valor"] = df.loc[compl, "valor"].abs()
        g = (df.groupby(["ideCadastro", "numAno", "numMes", "txtDescricao"], as_index=False)
               .agg(valor=("valor", "sum"), documentos=("valor", "size")))
        partes.append(g)
    out = pd.concat(partes, ignore_index=True).rename(columns={
        "ideCadastro": "id_deputado", "numAno": "ano", "numMes": "mes", "txtDescricao": "tipo"})
    for c in ("id_deputado", "ano", "mes"):
        out[c] = out[c].astype(float).astype(int)
    out["valor"] = out["valor"].round(2)
    out = out.sort_values(["id_deputado", "ano", "mes", "tipo"])
    out.to_csv(BRUTOS / "camara_cota.csv", index=False)
    log(f"Câmara: cota parlamentar ok ({len(out)} linhas, R$ {out['valor'].sum():,.2f})")


# ---------------------------------------------------------------- cota: total mensal do site oficial
# Desde ago/2025 as passagens compradas pelo sistema da Câmara (SIGEPA) sumiram dos arquivos de
# dados abertos, mas continuam no site. Por isso guardamos também o total mensal que o site mostra.
MESES = {"janeiro": 1, "fevereiro": 2, "março": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7,
         "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}
RX_MES = re.compile(r"(Janeiro|Fevereiro|Março|Abril|Maio|Junho|Julho|Agosto|Setembro|Outubro|Novembro|Dezembro)/(\d{4})\s*R\$\s*(-?[\d\.,]+)")


def _cota_site_ano(tarefa):
    id_, ano = tarefa
    arq = C / "cota_site" / f"{id_}_{ano}.json"
    if cache_valido(arq, 3 if ano == HOJE.year else (30 if ano == HOJE.year - 1 else None)):
        return
    try:
        html = baixar(f"{SITE}/cota-parlamentar/consulta-cota-parlamentar",
                      params={"ideDeputado": id_, "dataInicio": f"01{ano}", "dataFim": f"12{ano}"}).text
    except requests.HTTPError as e:
        # O site responde erro 500 para quem não usou a cota no ano (ex.: licenciado para ser ministro).
        if e.response is not None and e.response.status_code == 500:
            salvar_json(arq, [])
            return
        raise
    texto = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>", "", html, flags=re.S)))
    meses = {}
    for nome_mes, a, valor in RX_MES.findall(texto):
        if int(a) == ano:
            meses[MESES[nome_mes.lower()]] = numero_br(valor)
    salvar_json(arq, [{"mes": m, "total_site": v} for m, v in sorted(meses.items())])


ANO_INICIO_LACUNA = 2025  # a lacuna começa em ago/2025; antes disso os arquivos batem com o site


def cota_site(lista):
    """Só para os anos com lacuna e só para quem recebeu salário naquele ano."""
    rem = pd.read_csv(BRUTOS / "camara_remuneracao.csv")
    ativos = set(map(tuple, rem[rem["valor"] > 0][["id_deputado", "ano"]].drop_duplicates().values.tolist()))
    tarefas = [(d["id"], ano) for d in lista for ano in ANOS
               if ano >= ANO_INICIO_LACUNA and (d["id"], ano) in ativos]
    log(f"Câmara: total mensal da cota no site oficial ({len(tarefas)} consultas, com cache)")
    erros = []
    with ThreadPoolExecutor(PARALELO) as ex:
        futuros = {ex.submit(_cota_site_ano, t): t for t in tarefas}
        try:
            for f in as_completed(futuros):
                try:
                    f.result()
                except TempoEsgotado:
                    raise
                except Exception as e:
                    erros.append((futuros[f], repr(e)))
        except TempoEsgotado:
            ex.shutdown(wait=True, cancel_futures=True)
            raise
    if erros:
        raise RuntimeError(f"{len(erros)} consultas falharam, ex.: {erros[:2]}. Rode de novo.")
    linhas = []
    for id_, ano in tarefas:
        linhas += [{"id_deputado": id_, "ano": ano, **x} for x in ler_json(C / "cota_site" / f"{id_}_{ano}.json")]
    pd.DataFrame(linhas).to_csv(BRUTOS / "camara_cota_site.csv", index=False)
    log(f"Câmara: total mensal do site ok ({len(linhas)} meses)")


# ---------------------------------------------------------------- moradia
def _periodo(ano):
    ini = f"{INICIO_LEGISLATURA[1]:02d}/{ano}" if ano == INICIO_LEGISLATURA[0] else f"01/{ano}"
    fim = f"{ULTIMO_MES[1]:02d}/{ano}" if ano == ULTIMO_MES[0] else f"12/{ano}"
    return ini, fim


def moradia():
    """Por deputado e ano: dias em imóvel funcional, auxílio-moradia recebido e complemento pago com a cota."""
    linhas = []
    for ano in ANOS:
        arq = C / "moradia" / f"{ano}.json"
        if not cache_valido(arq, 3 if ano == HOJE.year else 60):
            ini, fim = _periodo(ano)
            log(f"Câmara: moradia {ano} ({ini} a {fim})")
            dados, pagina, vistos = [], 1, set()
            while True:
                r = baixar(f"{SITE}/moradia/detalhamento", params={
                    "legislatura": LEGISLATURA, "deputado": "Todos", "situacao": "todos",
                    "cargo": "deputado", "ordenacao": "nome",
                    "dataInicial": ini, "dataFinal": fim, "pagina": pagina})
                soup = BeautifulSoup(r.text, "lxml")
                novos = 0
                for tr in soup.select("table tbody tr"):
                    a = tr.find("a", href=True)
                    tds = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
                    m = re.search(r"(\d+)$", a["href"]) if a else None
                    if not m or len(tds) < 4:
                        continue
                    id_ = int(m.group(1))
                    if id_ in vistos:
                        continue
                    vistos.add(id_)
                    novos += 1
                    dias = re.search(r"\d+", tds[1])
                    dados.append({"id_deputado": id_, "ano": ano,
                                  "dias_imovel_funcional": int(dias.group()) if dias else 0,
                                  "auxilio_moradia": numero_br(tds[2]) or 0.0,
                                  "complemento_cota": numero_br(tds[3]) or 0.0})
                if novos == 0:
                    break
                pagina += 1
            salvar_json(arq, dados)
        linhas += ler_json(arq)
    df = pd.DataFrame(linhas)
    df.to_csv(BRUTOS / "camara_moradia.csv", index=False)
    log(f"Câmara: moradia ok ({len(df)} linhas, auxílio total R$ {df['auxilio_moradia'].sum():,.2f})")


# ---------------------------------------------------------------- página principal de cada deputado
CONGELADO = DADOS / "camara"  # vai para o Git: o que as páginas de cada deputado mostravam até set/2026
MESES_ABREV = {m: i + 1 for i, m in enumerate(["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"])}
# Subsídio dos membros do Congresso (Decreto Legislativo 172/2022, art. 1º): (a partir de AAAAMM, valor)
SUBSIDIOS = [(202301, 39293.32), (202304, 41650.92), (202402, 44008.52), (202502, 46366.19)]
DL_SUBSIDIO = "https://www2.camara.leg.br/legin/fed/decleg/2022/decretolegislativo-172-21-dezembro-2022-793529-publicacaooriginal-166604-pl.html"


def subsidio(aaaamm):
    return [v for de, v in SUBSIDIOS if de <= aaaamm][-1]


def _linhas_tabela(html, id_tabela=None):
    soup = BeautifulSoup(html, "lxml")
    tabela = soup.find("table", id=id_tabela) if id_tabela else soup.find("table")
    if not tabela:
        return []
    return [[td.get_text(" ", strip=True) for td in tr.find_all("td")]
            for tr in tabela.select("tbody tr") if tr.find("td")]


def _principal_ano(tarefa):
    """Verba de gabinete usada em cada mês do ano, pela página principal do deputado (/deputados/ID?ano=AAAA)."""
    id_, ano = tarefa
    arq = C / "principal" / f"{id_}_{ano}.json"
    if cache_valido(arq, 3 if ano == HOJE.year else None):
        return
    try:
        html = baixar(f"{SITE}/deputados/{id_}", params={"ano": ano}).text
    except requests.HTTPError as e:
        if e.response is None or e.response.status_code != 404:
            raise
        html = ""
    verba = []
    for l in _linhas_tabela(html, "gastomensalverbagabinete"):
        if len(l) >= 3 and l[0].upper() in MESES_ABREV:
            pct = float(l[2].replace("%", "").replace(",", ".") or 0)
            verba.append({"mes": MESES_ABREV[l[0].upper()], "gasto": numero_br(l[1]), "pct": pct})
    salvar_json(arq, {"verba_gabinete": verba})


def verba_gabinete(lista):
    tarefas = [(d["id"], ano) for d in lista for ano in ANOS]
    pendentes = [t for t in tarefas
                 if not cache_valido(C / "principal" / f"{t[0]}_{t[1]}.json", 3 if t[1] == HOJE.year else None)]
    log(f"Câmara: verba de gabinete (página principal de cada deputado) — {len(tarefas) - len(pendentes)}/{len(tarefas)} já no cache")
    erros = []
    feitos = 0
    with ThreadPoolExecutor(PARALELO) as ex:
        futuros = {ex.submit(_principal_ano, t): t for t in pendentes}
        try:
            for f in as_completed(futuros):
                try:
                    f.result()
                except TempoEsgotado:
                    raise
                except Exception as e:  # registra e segue
                    erros.append((futuros[f], repr(e)))
                feitos += 1
                if feitos % 200 == 0:
                    log(f"  ... {feitos}/{len(pendentes)}")
        except TempoEsgotado:
            ex.shutdown(wait=True, cancel_futures=True)
            raise
    if erros:
        log(f"Câmara: {len(erros)} páginas com erro (serão tentadas de novo na próxima vez): {erros[:3]}")
        raise RuntimeError("Algumas páginas falharam; rode de novo.")
    verba = []
    for id_, ano in tarefas:
        d = ler_json(C / "principal" / f"{id_}_{ano}.json")
        verba += [{"id_deputado": id_, "ano": ano, **x} for x in d["verba_gabinete"]]
    df = pd.DataFrame(verba, columns=["id_deputado", "ano", "mes", "gasto", "pct"])
    # a página dá o gasto e o percentual do disponível (arredondado); o disponível é o mesmo para todos no mês
    est = df[df.pct >= 50].assign(d=lambda x: x.gasto / (x.pct / 100)).groupby(["ano", "mes"]).d.median().round(2)
    df["disponivel"] = [est.get((a, m)) for a, m in zip(df.ano, df.mes)]
    df[["id_deputado", "ano", "mes", "disponivel", "gasto"]].to_csv(BRUTOS / "camara_verba_gabinete.csv", index=False)
    log(f"Câmara: verba de gabinete ok ({len(df)} meses)")


# ---------------------------------------------------------------- salário: páginas (até set/2026) e lei (depois)
def _historico(id_):
    """Situações do deputado (posse, licença, afastamento, reassunção...) pela API de dados abertos."""
    arq = C / "historico" / f"{id_}.json"
    if not cache_valido(arq, 3):
        d = baixar(f"{API}/deputados/{id_}/historico", headers=JSON).json()["dados"]
        salvar_json(arq, [[x["dataHora"][:10], x.get("idLegislatura"), x.get("situacao")] for x in d])
    return ler_json(arq)


def meses_em_exercicio(eventos, legislatura=LEGISLATURA):
    """Meses (AAAAMM) em exercício na legislatura. O mês da posse e o mês da saída contam."""
    evs = sorted((dt, sit) for dt, leg, sit in eventos if leg == legislatura and sit)
    fim = ULTIMO_MES[0] * 100 + ULTIMO_MES[1]
    meses, dentro, desde = set(), False, None
    for dt, sit in evs:
        am = int(dt[:4] + dt[5:7])
        if sit == "Exercício" and not dentro:
            dentro, desde = True, am
        elif sit != "Exercício" and dentro:
            meses.update(x for x in _meses_entre(desde, am))
            dentro = False
    if dentro:
        meses.update(_meses_entre(desde, fim))
    return meses


def _meses_entre(de, ate):
    a, m = divmod(de, 100)
    while a * 100 + m <= ate:
        yield a * 100 + m
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)


def remuneracao(lista):
    """Salário de cada mês. Até set/2026, o que a página de remuneração de cada deputado mostrava (guardado no Git).
    Depois, o subsídio fixado em lei, nos meses em que o deputado estava em exercício pelo histórico da API; quem, no
    último mês guardado, recebia o subsídio cheio sem estar em exercício (licenciado que optou pelo salário de
    deputado, como os ministros) continua recebendo enquanto o histórico não mudar."""
    base = pd.read_csv(CONGELADO / "remuneracao_paginas.csv")
    base["calculado"] = False
    ultimo = int((base.ano * 100 + base.mes).max())
    novos = [a * 100 + m for a, m in meses_da_legislatura() if a * 100 + m > ultimo]
    linhas = []
    if novos:
        pagos = base[base.ano * 100 + base.mes == ultimo].set_index("id_deputado").valor
        ids = [d["id"] for d in lista]
        with ThreadPoolExecutor(PARALELO) as ex:
            hist = dict(zip(ids, ex.map(_historico, ids)))
        fim_ultimo = f"{ultimo // 100}-{ultimo % 100:02d}-31"
        for id_ in ids:
            ev = hist[id_]
            meses = meses_em_exercicio(ev)
            mudou = any(dt > fim_ultimo and leg == LEGISLATURA for dt, leg, _ in ev)
            continua = not mudou and pagos.get(id_, 0) >= 0.9 * subsidio(ultimo)
            for am in novos:
                if am in meses or continua:
                    linhas.append({"id_deputado": id_, "ano": am // 100, "mes": am % 100, "valor": subsidio(am), "calculado": True})
    df = pd.concat([base, pd.DataFrame(linhas, columns=base.columns)], ignore_index=True)
    df.to_csv(BRUTOS / "camara_remuneracao.csv", index=False)
    log(f"Câmara: salários ok ({len(base)} meses das páginas, até {ultimo % 100:02d}/{ultimo // 100}; "
        f"{len(linhas)} meses pelo subsídio da lei)")


# ---------------------------------------------------------------- tamanho da equipe
def pessoal(lista):
    """Quantas pessoas trabalharam no gabinete de cada deputado em cada mês, até set/2026 (contadas nas páginas de
    pessoal de gabinete, que o robots.txt da Câmara não deixa mais robôs abrirem; sem nomes)."""
    df = pd.read_csv(CONGELADO / "pessoal_paginas.csv")
    df.to_csv(BRUTOS / "camara_pessoal.csv", index=False)
    log(f"Câmara: tamanho das equipes ok ({len(df)} meses, até {int((df.ano * 100 + df.mes).max()) % 100:02d}/{int(df.ano.max())})")


def coletar():
    lista = deputados()
    cota()
    moradia()
    remuneracao(lista)
    verba_gabinete(lista)
    pessoal(lista)
    cota_site(lista)
    log("Câmara: coleta completa.")
