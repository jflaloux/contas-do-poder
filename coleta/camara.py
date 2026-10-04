"""Robô da Câmara dos Deputados.

Fontes:
- API de dados abertos: lista e dados pessoais dos deputados
  https://dadosabertos.camara.leg.br/swagger/api.html
- Arquivos anuais da Cota Parlamentar (CEAP): https://www.camara.leg.br/cotas/Ano-AAAA.csv.zip
- Página principal de cada deputado: verba de gabinete usada em cada mês
  https://www.camara.leg.br/deputados/ID?ano=AAAA
- Páginas de cada deputado: salário mensal, contracheque detalhado de cada mês e pessoal de gabinete
  https://www.camara.leg.br/deputados/ID/remuneracao?ano=AAAA
  https://www.camara.leg.br/deputados/ID/remuneracao-deputado-detalhado?mesAno=MMAAAA
  https://www.camara.leg.br/deputados/ID/pessoal-gabinete?ano=AAAA
- Auxílio-moradia e imóvel funcional: https://www.camara.leg.br/moradia/detalhamento

O robots.txt da Câmara (desde 18/09/2026) não deixa robôs abrirem /deputados/ID/... (as páginas de salário, do
contracheque detalhado e de pessoal de gabinete de cada deputado). Essas páginas são lidas como exceção (regra no
CLAUDE.md, lista em coleta/util.py): é a remuneração de agente público, que a LAI manda publicar e abrir para acesso
automatizado. Devagar (um pedido a cada 0,25 s) e só o que falta: o que já foi lido fica em dados/camara/ (no Git) e não
é baixado de novo, a não ser os meses recentes. Se a Câmara bloquear, o robô usa o que está em dados/camara/ e, para os
meses seguintes, o subsídio fixado em lei (Decreto Legislativo 172/2022) nos meses em exercício.
Do contracheque detalhado guardamos só o que o deputado recebe (subsídio, vantagens, 13º, férias, acertos, abate-teto,
diárias, auxílios, verbas indenizatórias), nunca o imposto de renda, a previdência ou o líquido.
"""
import hashlib
import os
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests
from bs4 import BeautifulSoup

from .config import ANOS, BRUTOS, CACHE, DADOS, HOJE, INICIO_LEGISLATURA, LEGISLATURA, PARALELO, ULTIMO_MES, meses_da_legislatura
from .util import BloqueadoRobots, TempoEsgotado, baixar, cache_valido, gravar_csv, ler_json, log, normalizar_nome, numero_br, salvar_json

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
CONGELADO = DADOS / "camara"  # vai para o Git: salário, contracheque detalhado e equipe de cada deputado
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


# ---------------------------------------------------------------- páginas de cada deputado (exceção ao robots.txt)
def _pagina(id_, tipo, **params):
    try:
        return baixar(f"{SITE}/deputados/{id_}/{tipo}", params=params).text
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            return ""
        raise


def _em_paralelo(func, tarefas, nome, tolerancia=0):
    """Roda func em cada tarefa (PARALELO de cada vez; a sessão espaça os pedidos). Falhas acima da tolerância: erro."""
    erros, feitos = [], 0
    with ThreadPoolExecutor(PARALELO) as ex:
        futuros = {ex.submit(func, t): t for t in tarefas}
        try:
            for f in as_completed(futuros):
                try:
                    f.result()
                except (TempoEsgotado, BloqueadoRobots):
                    raise
                except Exception as e:  # registra e segue
                    erros.append((futuros[f], repr(e)))
                feitos += 1
                if feitos % 500 == 0:
                    log(f"  ... {nome}: {feitos}/{len(tarefas)}")
        except (TempoEsgotado, BloqueadoRobots):
            ex.shutdown(wait=True, cancel_futures=True)
            raise
    if erros:
        log(f"Câmara: {len(erros)} páginas de {nome} com erro (tentadas de novo na próxima vez), ex.: {erros[:2]}")
        if len(erros) > tolerancia:
            raise RuntimeError(f"{len(erros)} páginas de {nome} falharam; rode de novo.")


def _resumo_ano(tarefa):
    """Salário de cada mês do ano (a folha normal), pela página de remuneração do deputado."""
    id_, ano = tarefa
    linhas = _linhas_tabela(_pagina(id_, "remuneracao", ano=ano))
    salvar_json(C / "remuneracao" / f"{id_}_{ano}.json",
                [{"mes": int(l[0]), "valor": numero_br(l[1])} for l in linhas if len(l) >= 2 and l[0].isdigit()])


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
            meses.update(_meses_entre(desde, am))
            dentro = False
    if dentro:
        meses.update(_meses_entre(desde, fim))
    return meses


def _meses_entre(de, ate):
    a, m = divmod(de, 100)
    while a * 100 + m <= ate:
        yield a * 100 + m
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)


def _pela_lei(lista, base):
    """Se as páginas não abrem: depois do último mês guardado, o subsídio da lei nos meses em exercício. Quem, no último
    mês guardado, recebia o subsídio cheio sem estar em exercício (licenciado que optou pelo salário de deputado, como
    os ministros) continua recebendo enquanto o histórico não mudar."""
    ultimo = int((base.ano * 100 + base.mes).max())
    novos = [a * 100 + m for a, m in meses_da_legislatura() if a * 100 + m > ultimo]
    if not novos:
        return []
    pagos = base[base.ano * 100 + base.mes == ultimo].set_index("id_deputado").valor
    ids = [d["id"] for d in lista]
    with ThreadPoolExecutor(PARALELO) as ex:
        hist = dict(zip(ids, ex.map(_historico, ids)))
    fim_ultimo = f"{ultimo // 100}-{ultimo % 100:02d}-31"
    linhas = []
    for id_ in ids:
        ev = hist[id_]
        meses = meses_em_exercicio(ev)
        mudou = any(dt > fim_ultimo and leg == LEGISLATURA for dt, leg, _ in ev)
        continua = not mudou and pagos.get(id_, 0) >= 0.9 * subsidio(ultimo)
        linhas += [{"id_deputado": id_, "ano": am // 100, "mes": am % 100, "valor": subsidio(am), "calculado": True}
                   for am in novos if am in meses or continua]
    return linhas


def remuneracao(lista):
    """Salário de cada mês (a folha normal), pela página de remuneração de cada deputado; guardado em
    dados/camara/remuneracao.csv. Os anos passados que já estão lá não são baixados de novo."""
    arq = CONGELADO / "remuneracao.csv"
    guardado = pd.read_csv(arq) if arq.exists() else pd.DataFrame(columns=["id_deputado", "ano", "mes", "valor"])
    tem = set(zip(guardado.id_deputado, guardado.ano))
    tarefas = [(d["id"], ano) for d in lista for ano in ANOS]
    pendentes = [t for t in tarefas if not cache_valido(C / "remuneracao" / f"{t[0]}_{t[1]}.json", 3)
                 and (t[1] == HOJE.year or t not in tem)]
    log(f"Câmara: salário (página de remuneração de cada deputado) — {len(pendentes)} páginas a ler")
    try:
        _em_paralelo(_resumo_ano, pendentes, "remuneração")
        novas = []
        for id_, ano in tarefas:
            c = C / "remuneracao" / f"{id_}_{ano}.json"
            if c.exists() and (ano == HOJE.year or (id_, ano) not in tem or cache_valido(c, 3)):
                novas += [{"id_deputado": id_, "ano": ano, **x} for x in ler_json(c)]
        refeitos = {(x["id_deputado"], x["ano"]) for x in novas}
        df = pd.concat([guardado[[k not in refeitos for k in zip(guardado.id_deputado, guardado.ano)]],
                        pd.DataFrame(novas, columns=guardado.columns)], ignore_index=True)
        df = df.sort_values(["id_deputado", "ano", "mes"])
        if not gravar_csv(df, arq):  # recusado por perda de cobertura (util.gravar_com): fica o guardado
            df = pd.read_csv(arq)
        df["calculado"] = False
        log(f"Câmara: salários ok ({len(df)} meses)")
    except (BloqueadoRobots, RuntimeError, requests.RequestException) as e:
        log(f"Câmara: as páginas de remuneração não abriram ({e}); fica o que está em dados/camara/ e, depois, o subsídio da lei")
        df = guardado.assign(calculado=False)
        df = pd.concat([df, pd.DataFrame(_pela_lei(lista, df), columns=df.columns)], ignore_index=True)
    df.to_csv(BRUTOS / "camara_remuneracao.csv", index=False)
    return df


# ---------------------------------------------------------------- contracheque detalhado de cada mês
# rubrica da página -> coluna (o resto, como imposto de renda, previdência e líquido, não é guardado)
RUBRICAS = [("REMUNERACAO FIXA", "fixa"), ("VANTAGENS DE NATUREZA PESSOAL", "vantagens_pessoais"),
            ("FUNCAO OU CARGO EM COMISSAO", "funcao"), ("GRATIFICACAO NATALINA", "natalina"), ("FERIAS", "ferias"),
            ("OUTRAS REMUNERACOES EVENTUAIS", "eventuais"), ("ABONO PERMANENCIA", "abono"), ("REDUTOR CONSTITUCIONAL", "redutor"),
            ("DIARIAS", "diarias"), ("AUXILIOS", "auxilios"), ("VANTAGENS INDENIZATORIAS", "indenizatorias")]
NAO_GUARDA = ("CONTRIBUICAO PREVIDENCIARIA", "IMPOSTO DE RENDA", "REMUNERACAO APOS DESCONTOS")
COLUNAS_DETALHE = ["id_deputado", "ano", "mes", "folhas"] + [c for _, c in RUBRICAS]
# contracheques novos por vez (os mais recentes primeiro; ~25 min com a pausa); o resto fica para a próxima semana.
# Para ler tudo de uma vez no Mac: CAMARA_MAX_DETALHE=30000 python3 coletar.py camara (~1h40)
MAX_DETALHE = int(os.environ.get("CAMARA_MAX_DETALHE", 6000))


def _ler_detalhe(html):
    """{coluna: soma de todas as folhas do mês (normal, 13º, complementar...)} e os nomes das folhas."""
    soma, folhas = {c: 0.0 for _, c in RUBRICAS}, []
    for t in BeautifulSoup(html, "lxml").find_all("table"):
        cap = t.find("caption")
        if not cap or "Tipo Folha" not in cap.get_text():
            continue
        folhas.append(re.sub(r"\s+", " ", cap.get_text(" ", strip=True)).split(":", 1)[-1].split("-", 1)[-1].strip())
        for tr in t.select("tbody tr"):
            tds = tr.find_all("td")
            if len(tds) != 2:
                continue
            rotulo = normalizar_nome(tds[0].get_text(" ", strip=True))
            if any(n in rotulo for n in NAO_GUARDA):
                continue
            col = next((c for chave, c in RUBRICAS if chave in rotulo), None)
            if col is None:
                log(f"Câmara: rubrica nova no contracheque, não lida: {rotulo}")
                continue
            soma[col] += numero_br(tds[1].get_text(strip=True)) or 0.0
    return soma, folhas


def _detalhe_mes(tarefa):
    id_, am = tarefa
    html = _pagina(id_, "remuneracao-deputado-detalhado", mesAno=f"{am % 100:02d}{am // 100}")
    soma, folhas = _ler_detalhe(html)
    salvar_json(C / "detalhe" / f"{id_}_{am}.json", {"folhas": folhas, **{k: round(v, 2) for k, v in soma.items()}})


def detalhe(rem):
    """13º, férias, acertos, diárias e verbas indenizatórias (como a ajuda de custo), pelo contracheque detalhado de
    cada mês com salário; guardado em dados/camara/remuneracao_detalhe.csv. Só os meses que faltam e os 2 últimos."""
    arq = CONGELADO / "remuneracao_detalhe.csv"
    guardado = pd.read_csv(arq) if arq.exists() else pd.DataFrame(columns=COLUNAS_DETALHE)
    tem = set(zip(guardado.id_deputado, guardado.ano * 100 + guardado.mes))
    inicio = INICIO_LEGISLATURA[0] * 100 + INICIO_LEGISLATURA[1]
    fim = ULTIMO_MES[0] * 100 + ULTIMO_MES[1]
    recentes = {fim, fim - 1 if fim % 100 > 1 else fim - 89}
    r = rem[~rem.calculado.astype(bool) & (rem.valor.fillna(0) != 0)]
    meses = sorted({(int(i), int(a) * 100 + int(m)) for i, a, m in zip(r.id_deputado, r.ano, r.mes) if inicio <= a * 100 + m <= fim},
                   key=lambda t: (-t[1], t[0]))
    faltam = [t for t in meses if (t not in tem or t[1] in recentes) and not cache_valido(C / "detalhe" / f"{t[0]}_{t[1]}.json", 3)]
    log(f"Câmara: contracheques detalhados — {len(meses) - len(faltam)}/{len(meses)} já lidos; {min(len(faltam), MAX_DETALHE)} agora")
    erro = None
    try:
        _em_paralelo(_detalhe_mes, faltam[:MAX_DETALHE], "contracheque detalhado", tolerancia=20)
    except (BloqueadoRobots, RuntimeError, requests.RequestException) as e:
        erro = e
        log(f"Câmara: os contracheques detalhados não abriram ({e}); fica o que está em dados/camara/")
    finally:  # grava o que já foi lido, mesmo se o tempo acabar
        novas = []
        for id_, am in meses:
            c = C / "detalhe" / f"{id_}_{am}.json"
            if c.exists() and ((id_, am) not in tem or am in recentes):
                novas.append({"id_deputado": id_, "ano": am // 100, "mes": am % 100, **ler_json(c)})
        if novas:
            for x in novas:
                x["folhas"] = "; ".join(x["folhas"]) if isinstance(x["folhas"], list) else x["folhas"]
            refeitos = {(x["id_deputado"], x["ano"] * 100 + x["mes"]) for x in novas}
            guardado = pd.concat([guardado[[k not in refeitos for k in zip(guardado.id_deputado, guardado.ano * 100 + guardado.mes)]],
                                  pd.DataFrame(novas, columns=COLUNAS_DETALHE)], ignore_index=True)
            guardado = guardado.sort_values(["id_deputado", "ano", "mes"])
            CONGELADO.mkdir(parents=True, exist_ok=True)
            if not gravar_csv(guardado, arq):  # recusado por perda de cobertura (util.gravar_com): fica o guardado
                guardado = pd.read_csv(arq)
        guardado.to_csv(BRUTOS / "camara_remuneracao_detalhe.csv", index=False)
    cobertos = set(zip(guardado.id_deputado, guardado.ano * 100 + guardado.mes))
    falta = [am for t in meses for am in [t[1]] if t not in cobertos]
    log(f"Câmara: contracheques detalhados ok ({len(guardado)} meses; faltam {len(falta)}"
        f"{f', o mais recente {max(falta) % 100:02d}/{max(falta) // 100}' if falta else ''})")
    return erro


# ---------------------------------------------------------------- tamanho da equipe
RX_PERIODO = re.compile(r"(?:De|Desde)\s+(\d{2})/(\d{2})/(\d{4})(?:\s+a\s+(\d{2})/(\d{2})/(\d{4}))?")


def _pessoal_ano(tarefa):
    """Lê a página de pessoal de gabinete de um ano e guarda os períodos de exercício de cada pessoa.
    Não guarda nomes: só um código (hash) para contar pessoas diferentes.
    Secretários parlamentares são pagos pela verba de gabinete; cargos de natureza especial (CNE),
    pela própria Câmara, quando o deputado tem cargo de liderança ou na Mesa."""
    id_, ano = tarefa
    linhas = _linhas_tabela(_pagina(id_, "pessoal-gabinete", ano=ano))
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
    salvar_json(C / "pessoal_v2" / f"{id_}_{ano}.json", periodos)


def pessoal(lista, rem):
    """Quantas pessoas trabalharam no gabinete de cada deputado em cada mês, pela página de pessoal de gabinete
    (sem nomes); guardado em dados/camara/pessoal.csv. As páginas são por ano, mas uma pessoa pode aparecer só na
    página do ano em que começou; por isso juntamos as páginas de todos os anos antes de contar."""
    arq = CONGELADO / "pessoal.csv"
    verba = pd.read_csv(BRUTOS / "camara_verba_gabinete.csv")
    ativos = set(map(tuple, pd.concat([rem[rem["valor"] > 0][["id_deputado", "ano"]],
                                       verba[verba["gasto"] > 0][["id_deputado", "ano"]]]).drop_duplicates().values.tolist()))
    tarefas = [(d["id"], ano) for d in lista for ano in ANOS if (d["id"], ano) in ativos]
    pendentes = [t for t in tarefas if not cache_valido(C / "pessoal_v2" / f"{t[0]}_{t[1]}.json", 3 if t[1] == HOJE.year else None)]
    log(f"Câmara: tamanho das equipes — {len(tarefas) - len(pendentes)}/{len(tarefas)} já no cache")
    try:
        # algumas páginas dão erro 500 de vez em quando; toleramos poucas (são tentadas de novo na próxima vez)
        _em_paralelo(_pessoal_ano, pendentes, "pessoal de gabinete", tolerancia=max(20, int(0.05 * len(pendentes))))
    except (BloqueadoRobots, RuntimeError, requests.RequestException) as e:
        log(f"Câmara: as páginas de pessoal não abriram ({e}); fica o que está em dados/camara/pessoal.csv")
        df = pd.read_csv(arq)
        df.to_csv(BRUTOS / "camara_pessoal.csv", index=False)
        return
    por_dep = {}
    for id_, ano in tarefas:
        a = C / "pessoal_v2" / f"{id_}_{ano}.json"
        if a.exists():
            conj = por_dep.setdefault(id_, set())
            for x in ler_json(a):
                conj.add((x["h"], x["t"], tuple(x["i"]), tuple(x["f"]) if x["f"] else None))
    linhas = []
    for id_, periodos in por_dep.items():
        for am in meses_da_legislatura():
            sp = {h for h, t, i, f in periodos if t == "sp" and i <= am and (f is None or am <= f)}
            cne = {h for h, t, i, f in periodos if t == "cne" and i <= am and (f is None or am <= f)}
            if sp or cne:
                linhas.append({"id_deputado": id_, "ano": am[0], "mes": am[1], "secretarios": len(sp), "cne": len(cne)})
    df = pd.DataFrame(linhas, columns=["id_deputado", "ano", "mes", "secretarios", "cne"])
    if len(df) < 0.8 * len(pd.read_csv(arq)) if arq.exists() else False:  # o cache sumiu: não troca o guardado por menos
        log("Câmara: equipes com menos meses que o guardado (cache incompleto?); fica o que está em dados/camara/pessoal.csv")
        df = pd.read_csv(arq)
    elif not gravar_csv(df.sort_values(["id_deputado", "ano", "mes"]), arq):  # util.gravar_com recusou: fica o guardado
        df = pd.read_csv(arq)
    df.to_csv(BRUTOS / "camara_pessoal.csv", index=False)
    log(f"Câmara: tamanho das equipes ok ({len(df)} meses)")


def coletar():
    lista = deputados()
    cota()
    moradia()
    rem = remuneracao(lista)
    detalhe(rem)
    verba_gabinete(lista)
    pessoal(lista, rem)
    cota_site(lista)
    log("Câmara: coleta completa.")
