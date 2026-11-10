"""Rio Grande do Sul: "Viagens do Governador" no Portal da Transparência (painel Power BI lido com a chave anônima que a
própria página entrega a qualquer visitante, como a folha do RS; ver folhas_estaduais/powerbi.py).
https://www.transparencia.rs.gov.br/viagens/viagens-do-governador/dados/
- passagens (tabela ViagensGovernador2, desde 2023): bilhete por bilhete (data da viagem, rota, valor), com a autoridade
  ("Governador" ou "Vice-Governador"), sem o nome: a pessoa é a que ocupava o cargo no dia (comum.nome_no_cargo);
- despesas de viagem do governador (ViagensGovernador, desde set/2026): alimentação e hospedagem por município e data.
As diárias dos servidores (CSV anual no CKAN) não têm o governador nem o vice. A coluna de informações complementares
(texto livre) não é lida.
Os bilhetes viram viagens: a viagem começa num bilhete e termina no que chega a Porto Alegre (ou depois de 20 dias sem
bilhete, ou num novo bilhete que sai de Porto Alegre); o seguro-viagem e as despesas com datas dentro da viagem entram nela; despesas fora de qualquer viagem de avião
formam viagens por terra (dias seguidos)."""
import datetime

from ..folhas_estaduais import powerbi
from ..util import _sessao
from . import comum

UF = "RS"
FONTE = "https://www.transparencia.rs.gov.br/viagens/viagens-do-governador/dados/"
TOKEN = "https://www.transparencia.rs.gov.br/umbraco/Surface/PowerBI/Report"
PAINEL = {"workspaceId": "48138f86-653d-4a67-98d5-4cf00cdbcf4a", "reportId": "256079ca-fe2b-4681-a5e3-b0e692e56f72"}
CLUSTER = "https://wabi-brazil-south-redirect.analysis.windows.net"
CARGO = {"Governador": "gov", "Vice-Governador": "vice"}
CASA = "Porto Alegre"
NOTA = ("Passagens aéreas e seguro-viagem do governador e do vice, bilhete por bilhete, e despesas de viagem do governador "
        "(alimentação e hospedagem, publicadas desde set/2026, em outros), pela seção Viagens do Governador do Portal da "
        "Transparência do Rio Grande do Sul. A fonte identifica a pessoa pelo cargo. Os bilhetes são juntados em viagens "
        "(da saída até a volta a Porto Alegre); o mês é o do início da viagem. Viagens no avião do Estado não têm custo "
        "publicado.")


def _dia(ms):
    return datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc).strftime("%Y-%m-%d") if ms else ""


def _mais(dia, n):
    return (datetime.date.fromisoformat(dia) + datetime.timedelta(days=n)).isoformat()


def _ler():
    r = _sessao().post(TOKEN, data=PAINEL, timeout=60)
    r.raise_for_status()
    d = r.json()
    token, rel = d["Token"], d.get("Id") or PAINEL["reportId"]
    mid = powerbi.modelo(CLUSTER, token, rel)
    bilhetes = powerbi.consultar(CLUSTER, token, mid, [("p", "ViagensGovernador2")],
                                 [("p", "Id", None), ("p", "Autoridade", None), ("p", "Data da viagem", None),
                                  ("p", "Data da compra da passagem", None), ("p", "Serviço", None), ("p", "Rota", None),
                                  ("p", "MunicipioOrigem", None), ("p", "MunicipioDestino", None), ("p", "Valor", powerbi.SOMA)], limite=30000)
    despesas = powerbi.consultar(CLUSTER, token, mid, [("v", "ViagensGovernador")],
                                 [("v", "Autoridade", None), ("v", "Data Início", None), ("v", "Data Fim", None), ("v", "Municipio", None),
                                  ("v", "Rubrica", None), ("v", "Valor", powerbi.SOMA)], limite=30000)
    return bilhetes, despesas


def viagens(bilhetes, despesas, inicio="2025-01-01"):
    """Bilhetes [id, autoridade, ms da viagem, ms da compra, serviço, rota, município de origem, de destino, valor] e despesas
    [autoridade, ms início, ms fim, município, rubrica, valor] -> viagens (dicts de comum.COLUNAS, sem o nome)."""
    saida = []
    por_aut = {}
    for b in bilhetes:
        if b[1] not in CARGO:
            continue
        dia = _dia(b[2]) or _dia(b[3])  # seguro sem data da viagem: a data da compra
        if dia:
            por_aut.setdefault(b[1], []).append((dia, str(b[0]), b))
    for aut, lista in por_aut.items():
        atual = None
        for dia, _, b in sorted(lista):
            seguro = "SEGURO" in comum.normalizar_nome(b[4])
            sai_de_casa = (b[6] or "").strip() == CASA or (b[5] or "").replace(" ", "").startswith("POA-")
            continua = atual and (dia <= atual["fim"] or (not atual["fechada"] and dia <= _mais(atual["fim"], 20) and not sai_de_casa))
            if not continua:
                atual = {"autoridade": aut, "inicio": dia, "fim": dia, "destino": [], "passagens": 0.0, "outros": 0.0, "fechada": False}
                saida.append(atual)
            atual["fim"] = max(atual["fim"], dia)
            if seguro:
                atual["outros"] += comum.num(b[8])
                continue
            atual["passagens"] += comum.num(b[8])
            destino = (b[7] or "").strip()
            if destino == CASA or (b[5] or "").replace(" ", "").endswith("-POA"):
                atual["fechada"] = True
            elif destino and destino not in atual["destino"]:
                atual["destino"].append(destino)
    # despesas (alimentação, hospedagem): na viagem de avião que cobre a data; senão, viagens por terra de dias seguidos
    soltas = []
    for aut, ini, fim, mun, rub, valor in despesas:
        v = comum.num(valor)
        ini, fim = _dia(ini), _dia(fim) or _dia(ini)
        if aut not in CARGO or not ini or not v:
            continue
        dentro = next((x for x in saida if x["autoridade"] == aut and x["inicio"] <= ini <= x["fim"]), None)
        if dentro:
            dentro["outros"] += v
            if mun and mun not in dentro["destino"]:
                dentro["destino"].append(mun)
        else:
            soltas.append((aut, ini, fim, mun or "", v))
    terra = None
    for aut, ini, fim, mun, v in sorted(soltas):
        if not (terra and terra["autoridade"] == aut and ini <= _mais(terra["fim"], 1)):
            terra = {"autoridade": aut, "inicio": ini, "fim": fim, "destino": [], "passagens": 0.0, "outros": 0.0, "fechada": True}
            saida.append(terra)
        terra["fim"] = max(terra["fim"], fim)
        terra["outros"] += v
        if mun and mun not in terra["destino"]:
            terra["destino"].append(mun)
    linhas = []
    for x in saida:
        if x["inicio"] < inicio:
            continue
        cargo = CARGO[x["autoridade"]]
        linhas.append({"id": f"rs-{cargo}-{x['inicio']}", "inicio": x["inicio"], "fim": x["fim"],
                       "nome": comum.nome_no_cargo(UF, cargo, x["inicio"]), "cargo": x["autoridade"],
                       "destino": "; ".join(x["destino"]), "passagens": x["passagens"], "outros": x["outros"],
                       "obs": "" if x["passagens"] or not x["outros"] else "despesas de viagem, sem passagem aérea", "fonte": FONTE})
    return linhas


def coletar(nomes):  # noqa: ARG001 — a fonte não traz o nome; a pessoa sai do cargo e da data
    bilhetes, despesas = _ler()
    if not any(b[1] in CARGO for b in bilhetes):
        raise RuntimeError("o painel não trouxe bilhetes do governador nem do vice (tabela ou colunas mudaram?)")
    inicio = f"{comum.INICIO // 100}-{comum.INICIO % 100:02d}-01"
    return comum.gravar(UF, viagens(bilhetes, despesas, inicio))
