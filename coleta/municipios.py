"""Robô das câmaras municipais (vereadores), passo 1: a Câmara de cada cidade.

Fontes (todas nacionais, para as 5.568 cidades com câmara):
- Tesouro Nacional (Siconfi), lista de municípios com a população estimada pelo IBGE:
  https://apidatalake.tesouro.gov.br/ords/siconfi/tt/entes
- Tesouro Nacional (Siconfi), Declaração de Contas Anuais, Anexo I-E (despesa por função), uma consulta por
  cidade: https://apidatalake.tesouro.gov.br/ords/siconfi/tt/dca?an_exercicio=AAAA&no_anexo=DCA-Anexo%20I-E&id_ente=COD
  Custo da Câmara = função "01 - Legislativa" menos "01.032 - Controle Externo" (tribunal de contas do
  município, que só São Paulo e Rio têm), em despesas liquidadas.
- IBGE, Cadastro Central de Empresas (CEMPRE), salário médio mensal dos trabalhadores formais por cidade (tabela 9509
  do SIDRA): https://apisidra.ibge.gov.br/values/t/9509/n6/all/v/1606,10143/p/last%201
- TSE, candidatos de 2024: https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/consulta_cand_2024.zip
  (vereadores eleitos: "ELEITO POR QP" e "ELEITO POR MÉDIA"; com eleição suplementar, vale a que tem mais eleitos).

O salário de cada vereador não tem fonte nacional (cada câmara publica no seu portal). Por enquanto o site
mostra o teto que a Constituição permite (art. 29, VI), pela população.

Os resultados vão para dados/municipios/ (vai para o Git): assim o robô semanal só consulta o Tesouro para
as cidades que ainda faltam, e não as 5.568 de novo.
"""
import csv
import io
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests

from .config import CACHE, DADOS, HOJE
from .util import TempoEsgotado, _sessao, baixar, cache_valido, gravar_csv, ler_json, log, normalizar_nome, salvar_json, verificar_prazo

SICONFI = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt"
TSE = "https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/consulta_cand_2024.zip"
PASTA = DADOS / "municipios"
C = CACHE / "municipios"
CUSTOS = PASTA / "camaras_custo.csv"
COLUNAS_CUSTO = ["cod_ibge", "ano", "legislativa", "controle_externo", "consultado_em"]


def ano_contas():
    """Último ano cujas contas anuais já deviam ter sido entregues (prazo: 30 de abril do ano seguinte)."""
    return HOJE.year - 1 if HOJE.month >= 6 else HOJE.year - 2


# ---------------------------------------------------------------- municípios
def municipios():
    arq = PASTA / "municipios.csv"
    if cache_valido(arq, 30):
        return pd.read_csv(arq, dtype={"cod_ibge": int})
    log("Municípios: lista do Siconfi")
    itens = baixar(f"{SICONFI}/entes", timeout=120).json()["items"]
    df = pd.DataFrame([{"cod_ibge": int(x["cod_ibge"]), "nome": x["ente"], "uf": x["uf"], "capital": int(str(x["capital"]).strip() or 0),
                        "populacao": x.get("populacao")} for x in itens if x.get("esfera") == "M"])
    df = df.sort_values(["uf", "nome"])
    PASTA.mkdir(parents=True, exist_ok=True)
    if not gravar_csv(df, arq):  # recusado por perda de cobertura (util.gravar_com): fica a lista anterior
        return pd.read_csv(arq, dtype={"cod_ibge": int})
    return df


# ---------------------------------------------------------------- custo das câmaras (Siconfi)
def _dca(cod, ano):
    """(legislativa, controle externo) liquidados no ano, ou None se a cidade não entregou as contas."""
    for tentativa in range(3):
        try:
            r = _sessao().get(f"{SICONFI}/dca", params={"an_exercicio": ano, "no_anexo": "DCA-Anexo I-E", "id_ente": cod}, timeout=60)
            if r.status_code == 429:
                time.sleep(20 * (tentativa + 1))
                continue
            r.raise_for_status()
            itens = [x for x in r.json().get("items", []) if x.get("coluna") == "Despesas Liquidadas"]
            if not itens:
                return None
            valor = lambda prefixo: sum(x["valor"] or 0 for x in itens if (x.get("conta") or "").startswith(prefixo))
            return round(valor("01 - Legislativa"), 2), round(valor("01.032"), 2)
        except requests.RequestException:
            if tentativa == 2:
                raise
            time.sleep(5)
    return None


def custos(muni):
    """Custo anual da Câmara de cada cidade. Só consulta o que falta; quem não entregou é tentado de novo depois de 30 dias."""
    ano = ano_contas()
    feitos = pd.read_csv(CUSTOS) if CUSTOS.exists() else pd.DataFrame(columns=COLUNAS_CUSTO)
    limite = (pd.Timestamp(HOJE) - pd.Timedelta(days=30)).strftime("%Y-%m-%d")
    ok = feitos[feitos.legislativa.notna() | (feitos.consultado_em > limite)]
    ja = set(zip(ok.cod_ibge.astype(int), ok.ano.astype(int)))
    sem_ano = set(feitos[feitos.legislativa.isna() & (feitos.ano == ano)].cod_ibge.astype(int))
    # para cada cidade: o ano mais recente; só se não entregou, o anterior
    tarefas = [(c, ano) for c in muni.cod_ibge if (c, ano) not in ja]
    tarefas += [(c, ano - 1) for c in muni.cod_ibge if c in sem_ano and (c, ano - 1) not in ja]
    if not tarefas:
        return feitos
    log(f"Câmaras: custo anual no Siconfi — {len(tarefas)} consultas a fazer")
    novos = []

    def salvar():
        nonlocal feitos
        if novos:
            chaves = {(n["cod_ibge"], n["ano"]) for n in novos}
            velhos = feitos[[(int(c), int(a)) not in chaves for c, a in zip(feitos.cod_ibge, feitos.ano)]] if len(feitos) else None
            feitos = pd.DataFrame(novos) if velhos is None or velhos.empty else pd.concat([velhos, pd.DataFrame(novos)], ignore_index=True)
            gravar_csv(feitos.sort_values(["cod_ibge", "ano"]), CUSTOS)
            novos.clear()

    ex = ThreadPoolExecutor(6)
    futuros = {ex.submit(_dca, c, a): (c, a) for c, a in tarefas}
    try:
        for i, f in enumerate(as_completed(futuros), 1):
            verificar_prazo()
            c, a = futuros[f]
            try:
                res = f.result()
            except Exception as e:  # noqa: BLE001
                log(f"  {c}/{a}: {e}")
                continue
            novos.append({"cod_ibge": c, "ano": a, "legislativa": res[0] if res else None,
                          "controle_externo": res[1] if res else None, "consultado_em": HOJE.isoformat()})
            if i % 200 == 0:
                salvar()
                log(f"  {i}/{len(tarefas)}")
    except TempoEsgotado:
        ex.shutdown(wait=False, cancel_futures=True)
        salvar()
        raise
    ex.shutdown(wait=True)
    salvar()
    return feitos


# ---------------------------------------------------------------- vereadores eleitos (TSE)
def vereadores(muni):
    arq = PASTA / "vereadores.csv"
    zipado = C / "consulta_cand_2024.zip"
    if cache_valido(arq, 30):
        return pd.read_csv(arq, dtype={"cod_ibge": int})
    if not cache_valido(zipado, 30):
        log("Vereadores: arquivo de candidatos do TSE (~60 MB)")
        C.mkdir(parents=True, exist_ok=True)
        zipado.write_bytes(baixar(TSE, timeout=600).content)
    linhas = []
    with zipfile.ZipFile(zipado) as z, z.open("consulta_cand_2024_BRASIL.csv") as f:
        leitor = csv.reader(io.TextIOWrapper(f, encoding="latin1"), delimiter=";")
        cab = next(leitor)
        i = {c: k for k, c in enumerate(cab)}
        for l in leitor:
            if l[i["CD_CARGO"]] == "13" and l[i["DS_SIT_TOT_TURNO"]] in ("ELEITO POR QP", "ELEITO POR MÉDIA"):
                d, m, a = l[i["DT_ELEICAO"]].split("/")
                linhas.append({"sg_ue": l[i["SG_UE"]], "uf": l[i["SG_UF"]], "municipio": l[i["NM_UE"]],
                               "data_eleicao": f"{a}-{m}-{d}", "nome_urna": l[i["NM_URNA_CANDIDATO"]].strip(),
                               "nome": l[i["NM_CANDIDATO"]].strip(), "partido": l[i["SG_PARTIDO"]], "genero": l[i["DS_GENERO"]][:1]})
    v = pd.DataFrame(linhas)
    # cidade com eleição suplementar: vale a eleição com mais eleitos (uma suplementar pode ser só para uma vaga)
    n = v.groupby(["sg_ue", "data_eleicao"]).size().rename("n").reset_index()
    melhor = n.sort_values(["n", "data_eleicao"]).groupby("sg_ue").tail(1)
    v = v.merge(melhor[["sg_ue", "data_eleicao"]], on=["sg_ue", "data_eleicao"])
    # código do TSE -> código do IBGE, pelo nome da cidade e a UF
    chave = lambda uf, nome: f"{uf}|{normalizar_nome(nome).replace('-', ' ').replace(chr(39), ' ')}".replace("  ", " ")
    ibge = {chave(r.uf, r.nome): r.cod_ibge for r in muni.itertuples()}
    ibge.update(_NOMES_DIFERENTES)
    v["cod_ibge"] = [ibge.get(chave(u, n)) for u, n in zip(v.uf, v.municipio)]
    sem = v[v.cod_ibge.isna()][["uf", "municipio"]].drop_duplicates()
    if len(sem):
        log(f"  {len(sem)} cidades do TSE sem código do IBGE: {', '.join(f'{m}-{u}' for u, m in sem.values[:20])}")
    v = v[v.cod_ibge.notna()].astype({"cod_ibge": int})
    v = v.sort_values(["cod_ibge", "nome_urna"])[["cod_ibge", "nome_urna", "nome", "partido", "genero"]]
    PASTA.mkdir(parents=True, exist_ok=True)
    gravar_csv(v, arq)
    log(f"Vereadores: {len(v)} eleitos em {v.cod_ibge.nunique()} cidades")
    return v


# nomes que o TSE e o IBGE escrevem diferente (preenchido depois de conferir o log)
_NOMES_DIFERENTES = {
    "PA|SANTA ISABEL DO PARA": 1506500, "MG|SAO THOME DAS LETRAS": 3165206, "RO|ESPIGAO DO OESTE": 1100098,
    "RN|AREZ": 2401206, "SP|FLORINEA": 3516101, "BA|SANTA TEREZINHA": 2928505, "SE|GRACCHO CARDOSO": 2802601,
    "RN|ASSU": 2400208, "BA|MUQUEM DO SAO FRANCISCO": 2922250, "BA|CAMACA": 2905602, "RO|ALVORADA DO OESTE": 1100346,
    "PA|ELDORADO DOS CARAJAS": 1502954, "MG|DONA EUSEBIA": 3122900,
}


SIDRA_SALARIO = "https://apisidra.ibge.gov.br/values/t/9509/n6/all/v/1606,10143/p/last%201"
SALARIO_MEDIO = PASTA / "salario_medio.csv"


def salario_medio():
    """Salário médio mensal dos trabalhadores formais de cada cidade (IBGE, Cadastro Central de Empresas, tabela 9509 do
    SIDRA): em reais e em salários mínimos, do ano mais recente. Uma consulta só, para os 5.570 municípios do IBGE (com Brasília e Fernando de Noronha); de novo a cada
    30 dias (o IBGE publica um ano novo por vez)."""
    if SALARIO_MEDIO.exists() and time.time() - SALARIO_MEDIO.stat().st_mtime < 30 * 86400:
        return
    linhas = {}
    for x in _sessao().get(SIDRA_SALARIO, timeout=180).json()[1:]:
        if x.get("V") in (None, "", "-", "...", "X"):
            continue
        r = linhas.setdefault(int(x["D1C"]), {"cod_ibge": int(x["D1C"]), "ano": int(x["D3C"])})
        r["salario_medio_reais" if x["D2C"] == "10143" else "salario_medio_sm"] = float(x["V"])
    if len(linhas) < 5000:
        raise ValueError(f"salário médio do IBGE: só {len(linhas)} cidades")
    gravar_csv(pd.DataFrame(list(linhas.values())).sort_values("cod_ibge"), SALARIO_MEDIO)
    log(f"  Salário médio dos trabalhadores formais (IBGE, CEMPRE): {len(linhas)} cidades")


def coletar():
    muni = municipios()
    vereadores(muni)
    custos(muni)
    salario_medio()
