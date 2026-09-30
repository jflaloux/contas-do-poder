"""Consulta a painéis do Power BI publicados pelos portais de transparência (Bahia e Rio Grande do Sul).

A página do portal entrega a qualquer visitante uma chave de acesso anônima ao painel ("embed token"); com ela, o painel
pede os dados ao serviço do Power BI (explore/querydata), e é o mesmo pedido que fazemos aqui, só com as colunas e o
filtro de que precisamos (governador e vice). Nada de login, senha ou CAPTCHA. As colunas com CPF ou nome completo que
o próprio painel esconde nunca são pedidas.
A resposta vem num formato compacto (DSR): valores repetidos da linha anterior (bitmask "R"), vazios ("Ø") e
dicionários de valores ("ValueDicts"); `linhas()` desfaz isso."""
import json
import uuid

from ..util import _sessao, verificar_prazo

SOMA = 0  # função de agregação do Power BI


def _coluna(fonte, prop):
    return {"Column": {"Expression": {"SourceRef": {"Source": fonte}}, "Property": prop}}


def em(fonte, prop, valores):
    """Filtro "coluna está na lista"."""
    return {"Condition": {"In": {"Expressions": [_coluna(fonte, prop)], "Values": [[{"Literal": {"Value": f"'{v}'"}}] for v in valores]}}}


def modelo(cluster, token, relatorio):
    r = _sessao().get(f"{cluster}/explore/reports/{relatorio}/modelsAndExploration?preferReadOnlySession=true",
                      headers={"Authorization": f"EmbedToken {token}"}, timeout=90)
    r.raise_for_status()
    return r.json()["models"][0]["id"]


def consultar(cluster, token, modelo_id, tabelas, colunas, filtros=(), limite=5000):
    """tabelas: [(apelido, tabela)]; colunas: [(apelido, coluna, agregação ou None)] -> lista de linhas (listas)."""
    verificar_prazo()
    sel = []
    for fonte, prop, agg in colunas:
        c = _coluna(fonte, prop)
        if agg is not None:
            c = {"Aggregation": {"Expression": c, "Function": agg}}
        c["Name"] = f"{fonte}.{prop}"
        sel.append(c)
    q = {"Version": 2, "From": [{"Name": n, "Entity": e, "Type": 0} for n, e in tabelas], "Select": sel}
    if filtros:
        q["Where"] = list(filtros)
    corpo = {"version": "1.0.0", "queries": [{"Query": {"Commands": [{"SemanticQueryDataShapeCommand": {"Query": q, "Binding": {
        "Primary": {"Groupings": [{"Projections": list(range(len(sel)))}]},
        "DataReduction": {"DataVolume": 3, "Primary": {"Window": {"Count": limite}}}, "Version": 1}}}]}, "QueryId": ""}],
        "cancelQueries": [], "modelId": modelo_id}
    h = {"Authorization": f"EmbedToken {token}", "Content-Type": "application/json;charset=UTF-8", "Origin": "https://app.powerbi.com",
         "Referer": "https://app.powerbi.com/", "ActivityId": str(uuid.uuid4()), "RequestId": str(uuid.uuid4())}
    r = _sessao().post(f"{cluster}/explore/querydata?synchronous=true", headers=h, json=corpo, timeout=120)
    r.raise_for_status()
    return linhas(json.loads(r.content.decode("utf-8-sig")), len(sel))


def linhas(resposta, n):
    ds = resposta["results"][0]["result"]["data"]["dsr"]["DS"][0]
    dicionarios = ds.get("ValueDicts", {})
    ph = ds["PH"][0]
    chave = next(k for k in ph if k.startswith("DM"))
    saida, anterior, esquema = [], [None] * n, None
    for row in ph[chave]:
        if "S" in row:
            esquema = row["S"]
        vals = iter(row["C"]) if "C" in row else iter([])
        repete, vazio = row.get("R", 0), row.get("Ø", 0)
        linha = []
        for i in range(n):
            if repete >> i & 1:
                linha.append(anterior[i])
            elif vazio >> i & 1:
                linha.append(None)
            else:
                v = next(vals, None)
                dn = esquema[i].get("DN") if esquema and i < len(esquema) else None
                if dn and isinstance(v, int):
                    v = dicionarios[dn][v]
                linha.append(v)
        anterior = linha
        saida.append(linha)
    return saida
