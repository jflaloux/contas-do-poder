"""Robô da Câmara dos Deputados.

Fontes:
- API de dados abertos: lista e dados pessoais dos deputados
  https://dadosabertos.camara.leg.br/swagger/api.html
- Arquivos anuais da Cota Parlamentar (CEAP): https://www.camara.leg.br/cotas/Ano-AAAA.csv.zip
- Páginas de cada deputado: salário mensal e verba de gabinete
  https://www.camara.leg.br/deputados/ID/remuneracao?ano=AAAA
  https://www.camara.leg.br/deputados/ID/verba-gabinete?ano=AAAA
- Auxílio-moradia e imóvel funcional: https://www.camara.leg.br/moradia/detalhamento
"""
import hashlib
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests
from bs4 import BeautifulSoup

from .config import ANOS, BRUTOS, CACHE, HOJE, INICIO_LEGISLATURA, LEGISLATURA, PARALELO, ULTIMO_MES
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


# ---------------------------------------------------------------- páginas de cada deputado
def _linhas_tabela(html):
    soup = BeautifulSoup(html, "lxml")
    tabela = soup.find("table")
    if not tabela:
        return []
    return [[td.get_text(" ", strip=True) for td in tr.find_all("td")]
            for tr in tabela.select("tbody tr") if tr.find("td")]


def _pagina(id_, ano, tipo):
    try:
        return baixar(f"{SITE}/deputados/{id_}/{tipo}", params={"ano": ano}).text
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            return ""
        raise


def _perfil_ano(tarefa):
    id_, ano = tarefa
    arq = C / "perfil" / f"{id_}_{ano}.json"
    if cache_valido(arq, 3 if ano == HOJE.year else None):
        return
    rem = _linhas_tabela(_pagina(id_, ano, "remuneracao"))
    verba = _linhas_tabela(_pagina(id_, ano, "verba-gabinete"))
    salvar_json(arq, {
        "remuneracao": [{"mes": int(l[0]), "valor": numero_br(l[1])} for l in rem if len(l) >= 2 and l[0].isdigit()],
        "verba_gabinete": [{"mes": int(l[0]), "disponivel": numero_br(l[1]), "gasto": numero_br(l[2])}
                           for l in verba if len(l) >= 3 and l[0].isdigit()],
    })


def perfis(lista):
    tarefas = [(d["id"], ano) for d in lista for ano in ANOS]
    pendentes = [t for t in tarefas
                 if not cache_valido(C / "perfil" / f"{t[0]}_{t[1]}.json", 3 if t[1] == HOJE.year else None)]
    log(f"Câmara: páginas de salário e verba de gabinete — {len(tarefas) - len(pendentes)}/{len(tarefas)} já no cache")
    erros = []
    feitos = 0
    with ThreadPoolExecutor(PARALELO) as ex:
        futuros = {ex.submit(_perfil_ano, t): t for t in pendentes}
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

    rem, verba = [], []
    for id_, ano in tarefas:
        d = ler_json(C / "perfil" / f"{id_}_{ano}.json")
        rem += [{"id_deputado": id_, "ano": ano, **x} for x in d["remuneracao"]]
        verba += [{"id_deputado": id_, "ano": ano, **x} for x in d["verba_gabinete"]]
    pd.DataFrame(rem).to_csv(BRUTOS / "camara_remuneracao.csv", index=False)
    pd.DataFrame(verba).to_csv(BRUTOS / "camara_verba_gabinete.csv", index=False)
    log(f"Câmara: salários ({len(rem)} meses) e verba de gabinete ({len(verba)} meses) ok")


# ---------------------------------------------------------------- tamanho da equipe
RX_PERIODO = re.compile(r"(?:De|Desde)\s+(\d{2})/(\d{2})/(\d{4})(?:\s+a\s+(\d{2})/(\d{2})/(\d{4}))?")


def _pessoal_ano(tarefa):
    """Lê a página de pessoal de gabinete de um ano e guarda os períodos de exercício de cada pessoa.
    Não guarda nomes: só um código (hash) para contar pessoas diferentes.
    Secretários parlamentares são pagos pela verba de gabinete; cargos de natureza especial (CNE),
    pela própria Câmara, quando o deputado tem cargo de liderança ou na Mesa."""
    id_, ano = tarefa
    arq = C / "pessoal_v2" / f"{id_}_{ano}.json"
    if cache_valido(arq, 3 if ano == HOJE.year else None):
        return
    linhas = _linhas_tabela(_pagina(id_, ano, "pessoal-gabinete"))
    periodos = []
    for l in linhas:
        if len(l) < 4:
            continue
        m = RX_PERIODO.search(l[3])
        if not m:
            continue
        d1, m1, a1, d2, m2, a2 = m.groups()
        periodos.append({
            "h": hashlib.sha1(l[0].strip().upper().encode("utf-8")).hexdigest()[:12],
            "t": "sp" if "SECRET" in l[1].upper() else "cne",
            "i": [int(a1), int(m1)],
            "f": [int(a2), int(m2)] if a2 else None,
        })
    salvar_json(arq, periodos)


def pessoal(lista):
    """Quantas pessoas trabalharam no gabinete de cada deputado em cada mês.
    As páginas são por ano, mas uma pessoa pode aparecer só na página do ano em que começou;
    por isso juntamos as páginas de todos os anos antes de contar."""
    rem = pd.read_csv(BRUTOS / "camara_remuneracao.csv")
    verba = pd.read_csv(BRUTOS / "camara_verba_gabinete.csv")
    ativos = set(map(tuple, pd.concat([rem[rem["valor"] > 0][["id_deputado", "ano"]],
                                       verba[verba["gasto"] > 0][["id_deputado", "ano"]]]).drop_duplicates().values.tolist()))
    tarefas = [(d["id"], ano) for d in lista for ano in ANOS if (d["id"], ano) in ativos]
    pendentes = [t for t in tarefas if not cache_valido(C / "pessoal_v2" / f"{t[0]}_{t[1]}.json", 3 if t[1] == HOJE.year else None)]
    log(f"Câmara: tamanho das equipes — {len(tarefas) - len(pendentes)}/{len(tarefas)} já no cache")
    erros = []
    with ThreadPoolExecutor(PARALELO) as ex:
        futuros = {ex.submit(_pessoal_ano, t): t for t in pendentes}
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
    # Algumas páginas dão erro 500 de vez em quando; toleramos poucas (são tentadas de novo na próxima vez).
    if erros:
        log(f"Câmara: {len(erros)} páginas de pessoal com erro, ex.: {erros[:2]}")
        if len(erros) > max(20, 0.05 * len(pendentes)):
            raise RuntimeError(f"{len(erros)} páginas de pessoal falharam. Rode de novo.")
    por_dep = {}
    for id_, ano in tarefas:
        arq = C / "pessoal_v2" / f"{id_}_{ano}.json"
        if arq.exists():
            conj = por_dep.setdefault(id_, set())
            for x in ler_json(arq):
                conj.add((x["h"], x["t"], tuple(x["i"]), tuple(x["f"]) if x["f"] else None))
    meses = []
    ano, mes = INICIO_LEGISLATURA
    while (ano, mes) <= ULTIMO_MES:
        meses.append((ano, mes))
        mes += 1
        if mes > 12:
            ano, mes = ano + 1, 1
    linhas = []
    for id_, periodos in por_dep.items():
        for am in meses:
            sp = {h for h, t, i, f in periodos if t == "sp" and i <= am and (f is None or am <= f)}
            cne = {h for h, t, i, f in periodos if t == "cne" and i <= am and (f is None or am <= f)}
            if sp or cne:
                linhas.append({"id_deputado": id_, "ano": am[0], "mes": am[1], "secretarios": len(sp), "cne": len(cne)})
    pd.DataFrame(linhas).to_csv(BRUTOS / "camara_pessoal.csv", index=False)
    log(f"Câmara: tamanho das equipes ok ({len(linhas)} meses)")


def coletar():
    lista = deputados()
    cota()
    moradia()
    perfis(lista)
    pessoal(lista)
    cota_site(lista)
    log("Câmara: coleta completa.")
