"""Bahia: diárias do governador e do vice no "Painel de Diárias" do Portal da Transparência (Power BI lido com a chave
anônima que a própria página entrega a qualquer visitante, como a folha da BA; ver folhas_estaduais/powerbi.py).
https://www.transparencia.ba.gov.br/ServidorPessoal/PainelDiarias
A pessoa é achada pelo cargo ("Governador", "Vice Governador"), como na folha; as colunas de nome e de CPF do modelo não
são pedidas, e a pessoa é a que ocupava o cargo no dia (comum.nome_no_cargo). Uma linha por diária (destino, datas) e o
valor da ordem bancária que a pagou. O motivo (texto livre) não é lido. Não há passagens no painel."""
import base64
import datetime
import json
import re

from ..folhas_estaduais import powerbi
from ..util import _sessao
from . import comum

UF = "BA"
FONTE = "https://www.transparencia.ba.gov.br/ServidorPessoal/PainelDiarias"
CARGO = {"Governador": "gov", "Vice Governador": "vice"}
NOTA = ("Diárias do governador e do vice, viagem por viagem, pelo Painel de Diárias do Portal da Transparência da Bahia "
        "(valor pago); a fonte identifica a pessoa pelo cargo. O mês é o do início da viagem. O painel não publica "
        "passagens.")


def _dia(ms):
    return datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc).strftime("%Y-%m-%d") if ms else ""


def _painel():
    html = _sessao().get(FONTE, timeout=60).text
    token = re.search(r'const accessToken = "([^"]+)"', html).group(1)
    rel = re.search(r'const embedReportId = "([^"]+)"', html).group(1)
    cluster = json.loads(base64.b64decode(token.split(".")[1] + "==")).get("clusterUrl", "").lower()
    return cluster, token, powerbi.modelo(cluster, token, rel)


def viagens(linhas, inicio="2025-01-01", ate=None):
    """Linhas [cargo, código da diária, ms início, ms fim, município, UF, nº da ordem bancária, ms do pagamento, valor] ->
    viagens (uma por diária; a mesma diária paga em mais de uma ordem bancária soma)."""
    ate = ate or (datetime.date.today() + datetime.timedelta(days=60)).isoformat()  # a fonte tem datas como 2924
    por = {}
    for cargo, cod, ini, fim, mun, uf, nob, pago_em, valor in linhas:
        ini, fim = _dia(ini), _dia(fim)
        if cargo not in CARGO or not cod or not ini or not inicio <= ini <= ate:
            continue
        v = por.setdefault(cod, {"id": f"ba-{cod}", "inicio": ini, "fim": fim or ini, "cargo": cargo,
                                 "destino": f"{mun.title()}/{uf}" if mun and uf else (mun or "").title(),
                                 "diarias": 0.0, "_nobs": set(), "fonte": FONTE})
        if (nob, pago_em) not in v["_nobs"]:
            v["_nobs"].add((nob, pago_em))
            v["diarias"] += comum.num(valor)
    saida = []
    for v in por.values():
        v.pop("_nobs")
        v["nome"] = comum.nome_no_cargo(UF, CARGO[v["cargo"]], v["inicio"])
        saida.append(v)
    return saida


def coletar(nomes):  # noqa: ARG001 — a fonte é lida pelo cargo; a pessoa sai do cargo e da data
    cluster, token, mid = _painel()
    linhas = powerbi.consultar(cluster, token, mid, [("d", "vw_pagamento_diaria"), ("p", "pag_not_ord_banc")],
                               [("d", "nom_cargo_servidor", None), ("d", "cod_diaria_recebedor", None),
                                ("d", "Data de Início da Diária", None), ("d", "Data de Término da Diária", None),
                                ("d", "nom_municipio_destino", None), ("d", "sig_unidade_federacao_destino", None),
                                ("p", "num_pagto_nob", None), ("p", "Data do Pagamento", None), ("p", "val_pagto_nob", powerbi.SOMA)],
                               [powerbi.em("d", "nom_cargo_servidor", list(CARGO))], limite=30000)
    if not linhas:
        raise RuntimeError("o painel não trouxe diárias do governador nem do vice (cargo ou colunas mudaram?)")
    _conferir_ordens(cluster, token, mid, {l[6] for l in linhas if l[6]})
    inicio = f"{comum.INICIO // 100}-{comum.INICIO % 100:02d}-01"
    return comum.gravar(UF, viagens(linhas, inicio))


def _conferir_ordens(cluster, token, mid, ordens):
    """O valor vem da ordem bancária: se uma delas pagou também diárias de outra pessoa, o valor não seria só do governador
    ou do vice. Nesse caso a coleta falha (fica o que estava), em vez de publicar um valor errado."""
    if not ordens:
        return
    outras = powerbi.consultar(cluster, token, mid, [("d", "vw_pagamento_diaria")],
                               [("d", "num_pagto_nob", None), ("d", "nom_cargo_servidor", None), ("d", "cod_diaria_recebedor", None)],
                               [powerbi.em("d", "num_pagto_nob", sorted(ordens))], limite=30000)
    mistas = sorted({nob for nob, cargo, _ in outras if cargo not in CARGO})
    if mistas:
        raise RuntimeError(f"ordens bancárias que pagaram diárias de outras pessoas junto: {mistas[:5]}")
