"""Robô do Senado Federal.

Fontes:
- Dados abertos legislativos (lista e dados dos senadores): https://legis.senado.leg.br/dadosabertos/docs/
- Dados abertos administrativos: https://adm.senado.gov.br/adm-dadosabertos/swagger-ui/index.html
  * folha de pagamento mensal (inclui os senadores)
  * cota parlamentar (CEAPS)
  * recursos utilizados (outros gastos, auxílio-moradia/imóvel funcional, pessoal) — só senadores em exercício
"""
import csv
import io
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests

from .config import ANOS, BRUTOS, CACHE, HOJE, INICIO_LEGISLATURA, LEGISLATURA, PARALELO, meses_da_legislatura
from .util import (TempoEsgotado, baixar, cache_valido, ler_json, log, normalizar_nome,
                   numero_br, salvar_json)

LEGIS = "https://legis.senado.leg.br/dadosabertos"
ADM = "https://adm.senado.gov.br/adm-dadosabertos/api/v1"
C = CACHE / "senado"
JSON = {"Accept": "application/json"}


def _como_lista(x):
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


# ---------------------------------------------------------------- senadores
def _detalhe(cod):
    arq = C / "detalhe" / f"{cod}.json"
    if cache_valido(arq, 30):
        return ler_json(arq)
    d = baixar(f"{LEGIS}/senador/{cod}", headers=JSON).json()["DetalheParlamentar"]["Parlamentar"]
    salvar_json(arq, d)
    return d


def _exercicios(cod):
    """Períodos em que a pessoa de fato exerceu o mandato de senador, recortados para a legislatura."""
    arq = C / "mandatos" / f"{cod}.json"
    if cache_valido(arq, 7):
        d = ler_json(arq)
    else:
        d = baixar(f"{LEGIS}/senador/{cod}/mandatos", headers=JSON).json()
        salvar_json(arq, d)
    inicio_leg = f"{INICIO_LEGISLATURA[0]}-{INICIO_LEGISLATURA[1]:02d}-01"
    hoje = HOJE.isoformat()
    periodos = []
    mandatos = _como_lista(d.get("MandatoParlamentar", {}).get("Parlamentar", {}).get("Mandatos", {}).get("Mandato"))
    for m in mandatos:
        for e in _como_lista((m.get("Exercicios") or {}).get("Exercicio")):
            ini, fim = e.get("DataInicio"), e.get("DataFim") or hoje
            if not ini or fim < inicio_leg or ini > hoje:
                continue
            periodos.append({"inicio": max(ini, inicio_leg), "fim": min(fim, hoje),
                             "motivo_saida": e.get("DescricaoCausaAfastamento")})
    return sorted(periodos, key=lambda x: x["inicio"])


def senadores():
    """Todos com mandato na legislatura (titulares e suplentes), com os períodos em que de fato exerceram."""
    arq = C / "senadores_v2.json"
    if cache_valido(arq, 1):
        return ler_json(arq)
    log("Senado: lista de senadores")
    leg = baixar(f"{LEGIS}/senador/lista/legislatura/{LEGISLATURA}", headers=JSON).json()
    leg = _como_lista(leg["ListaParlamentarLegislatura"]["Parlamentares"]["Parlamentar"])
    atual = baixar(f"{LEGIS}/senador/lista/atual", headers=JSON).json()
    atual = {p["IdentificacaoParlamentar"]["CodigoParlamentar"]: p["IdentificacaoParlamentar"]
             for p in _como_lista(atual["ListaParlamentarEmExercicio"]["Parlamentares"]["Parlamentar"])}

    base = {}
    for p in leg:
        ident = p["IdentificacaoParlamentar"]
        mandatos = _como_lista(p.get("Mandatos", {}).get("Mandato"))
        uf = mandatos[0].get("UfParlamentar") if mandatos else None
        participacao = mandatos[0].get("DescricaoParticipacao") if mandatos else None
        base[ident["CodigoParlamentar"]] = {"ident": ident, "uf": uf, "participacao": participacao}

    detalhes, exercicios = {}, {}
    with ThreadPoolExecutor(PARALELO) as ex:
        futuros = {ex.submit(_detalhe, cod): cod for cod in base}
        for f in as_completed(futuros):
            try:
                detalhes[futuros[f]] = f.result()
            except requests.HTTPError:
                detalhes[futuros[f]] = {}
        futuros = {ex.submit(_exercicios, cod): cod for cod in base}
        for f in as_completed(futuros):
            exercicios[futuros[f]] = f.result()

    saida = []
    for cod, b in base.items():
        det = detalhes.get(cod, {})
        ident = {**b["ident"], **(det.get("IdentificacaoParlamentar") or {}), **(atual.get(cod) or {})}
        basicos = det.get("DadosBasicosParlamentar") or {}
        saida.append({
            "id": int(cod),
            "nome": ident.get("NomeParlamentar"),
            "nome_civil": ident.get("NomeCompletoParlamentar"),
            "sexo": {"Masculino": "M", "Feminino": "F"}.get(ident.get("SexoParlamentar")),
            "partido": ident.get("SiglaPartidoParlamentar"),
            "uf": ident.get("UfParlamentar") or b["uf"],
            "foto": (ident.get("UrlFotoParlamentar") or "").replace("http://", "https://") or None,
            "em_exercicio": cod in atual,
            "participacao": b["participacao"],
            "exercicios": exercicios.get(cod, []),
            "exerceu_na_legislatura": bool(exercicios.get(cod)),
            "data_nascimento": basicos.get("DataNascimento"),
            "municipio_nascimento": basicos.get("Naturalidade"),
            "uf_nascimento": basicos.get("UfNaturalidade"),
            "pagina_oficial": f"https://www25.senado.leg.br/web/senadores/senador/-/perfil/{cod}",
        })
    saida.sort(key=lambda s: s["nome"] or "")
    salvar_json(arq, saida)
    log(f"Senado: {len(saida)} com mandato na legislatura, "
        f"{sum(x['exerceu_na_legislatura'] for x in saida)} exerceram, {len(atual)} em exercício hoje")
    return saida


# ---------------------------------------------------------------- assessores dos gabinetes
RX_GABINETE = re.compile(r"^(?:Gabinete|Escrit[oó]rio de Apoio(?: \d+)?)\s+d[oa]\s+Senador[a]?\s+(.+)$", re.I)


def assessores(lista):
    """Mapa: nome do servidor comissionado -> código do senador em cujo gabinete/escritório ele está lotado.
    ATENÇÃO: a API só informa a lotação atual (ou a última, para quem saiu). É uma aproximação."""
    arq = C / "comissionados.json"
    if not cache_valido(arq, 7):
        log("Senado: lista de servidores comissionados")
        salvar_json(arq, baixar(f"{ADM}/servidores/servidores/comissionados", timeout=300).json())
    servidores = ler_json(arq)

    exato, parcial = {}, []
    for sen in lista:
        if not sen["exercicios"]:
            continue
        for n in (sen.get("nome"), sen.get("nome_civil")):
            if n:
                exato.setdefault(normalizar_nome(n), sen["id"])
        parcial.append((chave_nome(sen.get("nome_civil") or sen["nome"]).split(), sen["id"]))

    def senador_da_lotacao(nome_lotacao):
        m = RX_GABINETE.match((nome_lotacao or "").strip())
        if not m:
            return None
        alvo = normalizar_nome(m.group(1))
        if alvo in exato:
            return exato[alvo]
        tokens = chave_nome(m.group(1)).split()
        candidatos = [cod for civil, cod in parcial
                      if tokens and all(t in civil for t in tokens) and civil[0] == tokens[0]]
        return candidatos[0] if len(candidatos) == 1 else None

    # O "sequencial" desta lista NÃO é o mesmo da folha de pagamento; por isso ligamos pelo nome.
    # Nomes repetidos (homônimos) com lotações diferentes são descartados.
    mapa, conflito = {}, set()
    for x in servidores:
        cod = senador_da_lotacao((x.get("lotacao") or {}).get("nome"))
        chave = normalizar_nome(x.get("nome"))
        if not chave:
            continue
        if chave in mapa and mapa[chave] != cod:
            conflito.add(chave)
        mapa.setdefault(chave, cod)
    mapa = {k: v for k, v in mapa.items() if v and k not in conflito}
    log(f"Senado: {len(mapa)} assessores comissionados ligados a {len(set(mapa.values()))} senadores")
    return mapa


# ---------------------------------------------------------------- folha de pagamento
COLUNAS_FOLHA = {
    "REMUNERAÇÃO BÁSICA": "remuneracao_basica",
    "VANTAGENS PESSOAIS": "vantagens_pessoais",
    "FUNÇÃO COMISSIONADA": "funcao_comissionada",
    "GRATIFICAÇÃO NATALINA": "gratificacao_natalina",
    "HORAS EXTRAS": "horas_extras",
    "OUTRAS EVENTUAIS": "outras_eventuais",
    "ABONO PERMANÊNCIA": "abono_permanencia",
    "REVERSÃO TETO CONSTITUCIONAL": "reversao_teto",
    "IMPOSTO DE RENDA": "imposto_renda",
    "PREVIDÊNCIA": "previdencia",
    "FALTAS": "faltas",
    "REMUNERAÇÃO LÍQUIDA": "remuneracao_liquida",
    "DIÁRIAS": "diarias",
    "AUXÍLIOS": "auxilios",
    "VANTAGENS INDENIZATÓRIAS": "vantagens_indenizatorias",
}


PARTICULAS = {"DE", "DA", "DO", "DAS", "DOS", "E"}


def chave_nome(nome):
    return " ".join(t for t in normalizar_nome(nome).split() if t not in PARTICULAS)


def _janela(periodos):
    """(ano, mês) do primeiro mês de exercício até 3 meses depois do último."""
    ini = periodos[0]["inicio"]
    fim = max(p["fim"] for p in periodos)
    a, m = int(fim[:4]), int(fim[5:7]) + 3
    while m > 12:
        a, m = a + 1, m - 12
    return (int(ini[:4]), int(ini[5:7])), (a, m)


REMUNERATIVAS = ["remuneracao_basica", "vantagens_pessoais", "funcao_comissionada", "gratificacao_natalina",
                 "horas_extras", "outras_eventuais", "abono_permanencia", "reversao_teto"]


def _folha_mes(tarefa, nomes, mapa_assessores, janelas):
    ano, mes = tarefa
    arq = C / "folha_v4" / f"{ano}-{mes:02d}.json"
    recente = (ano, mes) >= ((HOJE.year, HOJE.month - 1) if HOJE.month > 1 else (HOJE.year - 1, 12))
    if cache_valido(arq, 3 if recente else None):
        return
    try:
        texto = baixar(f"{ADM}/servidores/remuneracoes/{ano}/{mes}/csv", timeout=180).content.decode("utf-8-sig")
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            salvar_json(arq, {"senadores": [], "gabinetes": []})
            return
        raise
    linhas = []
    gabinetes = {}
    for row in csv.DictReader(io.StringIO(texto), delimiter=";"):
        cod_gab = mapa_assessores.get(normalizar_nome(row.get("NOME")))
        if cod_gab is not None:
            ini, fim = janelas[cod_gab]
            if ini <= (ano, mes) <= fim:
                bruto = sum(numero_br(row.get(orig)) or 0.0 for orig, novo in COLUNAS_FOLHA.items() if novo in REMUNERATIVAS)
                g = gabinetes.setdefault(cod_gab, {"id_senador": cod_gab, "ano": ano, "mes": mes, "valor": 0.0, "pessoas": set()})
                g["valor"] += bruto
                if bruto > 0:
                    g["pessoas"].add(row.get("SEQUENCIAL"))
        alvo = nomes.get(chave_nome(row.get("NOME")))
        if alvo is None:
            continue
        cod, (ini, fim) = alvo
        if not (ini <= (ano, mes) <= fim):
            continue
        item = {"id_senador": cod, "ano": ano, "mes": mes, "tipo_folha": row.get("TIPO FOLHA"),
                "nome_folha": row.get("NOME")}
        for original, novo in COLUNAS_FOLHA.items():
            item[novo] = numero_br(row.get(original)) or 0.0
        linhas.append(item)
    for g in gabinetes.values():
        g["valor"] = round(g["valor"], 2)
        g["pessoas"] = len(g["pessoas"])
    salvar_json(arq, {"senadores": linhas, "gabinetes": list(gabinetes.values())})


def folha(lista):
    nomes = {}
    for s in lista:
        if not s["exercicios"]:
            continue  # suplente que nunca assumiu: não é senador na folha
        for n in (s.get("nome_civil"), s.get("nome")):
            if n:
                nomes.setdefault(chave_nome(n), (s["id"], _janela(s["exercicios"])))
    janelas = {s["id"]: _janela(s["exercicios"]) for s in lista if s["exercicios"]}
    mapa = assessores(lista)
    tarefas = meses_da_legislatura()
    log(f"Senado: folha de pagamento ({len(tarefas)} meses)")
    with ThreadPoolExecutor(2) as ex:  # arquivos grandes: 2 de cada vez
        futuros = [ex.submit(_folha_mes, t, nomes, mapa, janelas) for t in tarefas]
        try:
            for f in as_completed(futuros):
                f.result()
        except TempoEsgotado:
            ex.shutdown(wait=True, cancel_futures=True)
            raise
    linhas, gabs = [], []
    for ano, mes in tarefas:
        d = ler_json(C / "folha_v4" / f"{ano}-{mes:02d}.json")
        linhas += d["senadores"]
        gabs += d["gabinetes"]
    df = pd.DataFrame(linhas)
    df.to_csv(BRUTOS / "senado_folha.csv", index=False)
    pd.DataFrame(gabs).to_csv(BRUTOS / "senado_assessores_gabinete.csv", index=False)
    log(f"Senado: folha ok ({len(df)} linhas, {df['id_senador'].nunique()} senadores encontrados)")
    return df


# ---------------------------------------------------------------- cota (CEAPS)
def ceaps():
    partes = []
    for ano in ANOS:
        arq = C / "ceaps" / f"{ano}.json"
        if not cache_valido(arq, 1 if ano == HOJE.year else 30):
            log(f"Senado: baixando cota parlamentar (CEAPS) {ano}")
            salvar_json(arq, baixar(f"{ADM}/senadores/despesas_ceaps/{ano}", timeout=300).json())
        df = pd.DataFrame(ler_json(arq))
        if df.empty:
            continue
        df["valorReembolsado"] = pd.to_numeric(df["valorReembolsado"], errors="coerce").fillna(0.0)
        partes.append(df.groupby(["codSenador", "ano", "mes", "tipoDespesa"], as_index=False)
                        .agg(valor=("valorReembolsado", "sum"), documentos=("id", "size")))
    out = pd.concat(partes, ignore_index=True).rename(columns={"codSenador": "id_senador", "tipoDespesa": "tipo"})
    out["valor"] = out["valor"].round(2)
    out = out.sort_values(["id_senador", "ano", "mes", "tipo"])
    out.to_csv(BRUTOS / "senado_ceaps.csv", index=False)
    log(f"Senado: CEAPS ok ({len(out)} linhas, R$ {out['valor'].sum():,.2f})")


# ---------------------------------------------------------------- recursos utilizados
def _recursos(tarefa):
    cod, ano = tarefa
    arq = C / "recursos" / f"{cod}_{ano}.json"
    if cache_valido(arq, 3 if ano == HOJE.year else None):
        return
    try:
        d = baixar(f"{ADM}/senadores/{cod}/recursos-utilizados", params={"ano": ano}).json()
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            d = {"data": []}
        else:
            raise
    salvar_json(arq, d.get("data") or [])


def recursos(lista):
    """Outros gastos do mandato, benefícios e pessoal. A API só responde para quem está em exercício."""
    atuais = [s["id"] for s in lista if s["em_exercicio"]]
    tarefas = [(cod, ano) for cod in atuais for ano in ANOS]
    log(f"Senado: recursos utilizados ({len(tarefas)} consultas)")
    with ThreadPoolExecutor(PARALELO) as ex:
        futuros = [ex.submit(_recursos, t) for t in tarefas]
        try:
            for f in as_completed(futuros):
                f.result()
        except TempoEsgotado:
            ex.shutdown(wait=True, cancel_futures=True)
            raise
    outros, beneficios, pessoal = [], [], []
    for cod, ano in tarefas:
        for d in ler_json(C / "recursos" / f"{cod}_{ano}.json"):
            for x in (d.get("gastosNaoInclusos") or {}).get("despesas", []):
                outros.append({"id_senador": cod, "ano": ano, "tipo": x["recurso"], "valor": x["valor"] or 0.0})
            for x in d.get("beneficios") or []:
                beneficios.append({"id_senador": cod, "ano": ano, "beneficio": x["beneficio"], "utilizacao": x["utilizacao"]})
            for x in d.get("pessoal") or []:
                pessoal.append({"id_senador": cod, "ano": ano, "local": x["local"], "quantidade": x["quantidade"]})
    pd.DataFrame(outros).to_csv(BRUTOS / "senado_outros_gastos.csv", index=False)
    pd.DataFrame(beneficios).to_csv(BRUTOS / "senado_beneficios.csv", index=False)
    pd.DataFrame(pessoal).to_csv(BRUTOS / "senado_pessoal.csv", index=False)
    log(f"Senado: recursos ok ({len(outros)} linhas de outros gastos)")


def coletar():
    lista = senadores()
    ceaps()
    folha(lista)
    recursos(lista)
    log("Senado: coleta completa.")
