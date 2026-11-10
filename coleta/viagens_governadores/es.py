"""Espírito Santo: diárias do governador e do vice pelos dados abertos do Estado (conjunto "Portal da Transparência -
Pessoal - Diárias", CKAN: https://dados.es.gov.br/dataset/portal-da-transparencia-pessoal-diarias). Um CSV por ano
(Diarias-AAAA.csv, ~290 MB), achado pela página do conjunto (o robots.txt proíbe /api/ e pede 10 s entre os pedidos).
Cada linha é um documento (empenho, liquidação ou pagamento) de um favorecido; a viagem é o empenho, e o valor é a soma
do valor pago dos seus documentos. As colunas de destino e de período vêm vazias: as datas saem do histórico do
documento (só as datas; o resto do texto livre não é guardado). O CPF mascarado do arquivo não é lido.
Depois de lido, o arquivo do ano dá lugar a um resumo pequeno (só as linhas do governador e do vice) no cache."""
import csv
import json
import re
import time

from ..util import _sessao, normalizar_nome, recursos_ckan, verificar_prazo
from . import comum

UF = "ES"
FONTE = "https://dados.es.gov.br/dataset/portal-da-transparencia-pessoal-diarias"
NOTA = ("Diárias do governador e do vice pelos dados abertos do Espírito Santo, viagem por viagem (um empenho por viagem), "
        "valor pago; o mês é o do início da viagem, tirado do histórico do empenho (sem data no histórico, vale a data do "
        "empenho). As passagens não são publicadas por pessoa e não entram.")
COLUNAS = ["Ano", "Data", "ValorEmpenho", "ValorLiquidado", "ValorPago", "ValorRap", "Favorecido", "HistoricoDocumento",
           "Documento", "DocumentoEmpenho", "UnidadeGestora", "CargoFuncaoDiaria"]  # o CPF (CpfCnpjNis) não é lido
_D = r"(\d{1,2})[./](\d{1,2})[./](\d{4})"
_ATE = r"\s*(?:a|à|até|e|-)\s*"
# na ordem de preferência: "de 04.03.2025 a 14.03.2025"; "de 04 a 14/03/2025", "nos dias 16 e 17/08/2026"; "no dia 08/07/2026"
PERIODO = re.compile(r"(?<!\d)" + _D + _ATE + _D + r"(?!\d)")
DIAS = re.compile(r"(?<![\d./])(\d{1,2})(?:\s*,\s*\d{1,2})*" + _ATE + _D + r"(?!\d)")
DIA = re.compile(r"\b(?:dia|em)\s+" + _D + r"(?!\d)", re.I)


def periodo_do_historico(texto, ano):
    """(início, fim) da viagem (AAAA-MM-DD) pelo histórico, ou None. Só as formas de período ("de X a Y", "dias X e Y",
    "no dia X"), para não tomar por data da viagem a da cotação do dólar ou a do decreto citado no mesmo texto; datas fora
    de ano-1 a ano+1 (o exercício do empenho) não valem."""
    def dia(d, m, a):
        d, m, a = int(d), int(m), int(a)
        return f"{a}-{m:02d}-{d:02d}" if ano - 1 <= a <= ano + 1 and 1 <= m <= 12 and 1 <= d <= 31 else None
    t = texto or ""
    for d1, m1, a1, d2, m2, a2 in PERIODO.findall(t):
        i, f = dia(d1, m1, a1), dia(d2, m2, a2)
        if i and f and i <= f:
            return i, f
    for d1, d2, m, a in DIAS.findall(t):
        i, f = dia(d1, m, a), dia(d2, m, a)
        if i and f and i <= f:
            return i, f
    for d, m, a in DIA.findall(t):
        if dia(d, m, a):
            return dia(d, m, a), dia(d, m, a)
    return None


def _dia(t):
    """"19/02/2025 00:00:00" -> "2025-02-19"."""
    t = (t or "").strip()
    return f"{t[6:10]}-{t[3:5]}-{t[0:2]}" if len(t) >= 10 and t[2] == "/" else ""


def _ano(ano, url, nomes, dias):
    """As linhas do governador e do vice no arquivo do ano. O resumo do cache vale por `dias`; depois, o pedido começa e,
    se o arquivo não mudou (mesmo Last-Modified), para antes do corpo (~290 MB) e o resumo continua valendo."""
    resumo = comum.C / "es" / f"{ano}.json"
    antes = json.loads(resumo.read_text(encoding="utf-8")) if resumo.exists() else None
    if antes is not None and time.time() - resumo.stat().st_mtime < dias * 86400:
        return antes["linhas"]
    verificar_prazo()
    resumo.parent.mkdir(parents=True, exist_ok=True)
    tmp = resumo.with_suffix(".csv.parcial")
    with _sessao().get(url, timeout=900, stream=True) as r:
        r.raise_for_status()
        modificado = r.headers.get("Last-Modified") or ""
        if antes is not None and modificado and modificado == antes.get("modificado"):
            resumo.touch()
            return antes["linhas"]
        with open(tmp, "wb") as f:
            for b in r.iter_content(1 << 20):
                f.write(b)
    linhas = []
    try:
        with open(tmp, encoding="utf-8-sig", errors="replace", newline="") as f:
            leitor = csv.DictReader(f, delimiter=";")
            faltam = [c for c in COLUNAS if c not in (leitor.fieldnames or [])]
            if faltam:
                raise RuntimeError(f"Diarias-{ano}.csv sem as colunas {faltam} (leiaute novo?)")
            n = 0
            for x in leitor:
                n += 1
                if normalizar_nome(x["Favorecido"]) in nomes:
                    linhas.append({c: x[c] for c in COLUNAS})
            if n < 1000:
                raise RuntimeError(f"Diarias-{ano}.csv com só {n} linhas (arquivo incompleto?)")
    finally:
        tmp.unlink(missing_ok=True)
    resumo.write_text(json.dumps({"modificado": modificado, "linhas": linhas}, ensure_ascii=False), encoding="utf-8")
    return linhas


def _sigla(ug):
    """Um pedaço estável do nome da unidade gestora para o id (o número do empenho se repete entre unidades)."""
    return "".join(w[0] for w in normalizar_nome(ug).split() if len(w) > 2)[:12].lower() or "ug"


def montar_viagens(linhas):
    """Linhas do CSV (só do governador e do vice) -> viagens, uma por empenho (valor pago das ordens bancárias)."""
    por = {}
    for x in linhas:
        ne = (x.get("DocumentoEmpenho") or "").strip()
        if not ne:
            continue
        v = por.setdefault((x.get("UnidadeGestora") or "", ne), {"pago": 0.0, "periodo": None, "data_ne": "", "nome": x["Favorecido"],
                                                                 "cargo": ""})
        v["pago"] += comum.num(x.get("ValorPago"))
        v["periodo"] = v["periodo"] or periodo_do_historico(x.get("HistoricoDocumento"), int(ne[:4]) if ne[:4].isdigit() else int(x["Ano"]))
        if (x.get("Documento") or "").strip() == ne and _dia(x.get("Data")):
            v["data_ne"] = min(v["data_ne"] or "9", _dia(x.get("Data")))
        # "|VG/#MANDATO ELETIVO/#VICE-GOVERNADOR DO ESTADO#": o cargo é o último pedaço
        v["cargo"] = v["cargo"] or next((c.strip() for c in reversed(re.split(r"[|#/]", x.get("CargoFuncaoDiaria") or "")) if c.strip()), "")
    saida = []
    for (ug, ne), v in por.items():
        if not v["pago"]:
            continue  # empenho sem pagamento (ainda não pago ou anulado)
        inicio, fim = v["periodo"] or (v["data_ne"], v["data_ne"])
        if not inicio:
            continue
        saida.append({"id": f"es-{_sigla(ug)}-{ne}", "inicio": inicio, "fim": fim, "nome": " ".join(v["nome"].split()), "cargo": v["cargo"],
                      "destino": "", "diarias": v["pago"] if v["pago"] > 0 else 0.0, "devolucoes": -v["pago"] if v["pago"] < 0 else 0.0,
                      "obs": "" if v["periodo"] else "sem o período no histórico: data do empenho", "fonte": FONTE})
    return saida


def coletar(nomes):
    """`nomes`: nomes normalizados como o arquivo escreve (NOMES_FONTE: o do vice vem sem o "DE")."""
    urls = {}
    for r in recursos_ckan(FONTE):
        m = re.search(r"diarias-(\d{4})\.csv$", r["url"], re.I)
        if m:
            urls[int(m.group(1))] = r["url"]
    anos = sorted({am // 100 for am in comum.meses()})
    if anos[-1] not in urls and anos[-1] - 1 in urls and time.localtime().tm_mon <= 2:
        anos = anos[:-1]  # janeiro e fevereiro: o arquivo do ano novo pode ainda não existir
    linhas = []
    for ano in anos:
        if ano not in urls:
            raise RuntimeError(f"o conjunto não tem o arquivo Diarias-{ano}.csv")
        linhas += _ano(ano, urls[ano], nomes, 6)
    if not linhas:
        raise RuntimeError("nenhuma linha do governador ou do vice nos arquivos (nome mudou?)")
    viagens = [v for v in montar_viagens(linhas) if v["inicio"] >= f"{comum.INICIO // 100}-{comum.INICIO % 100:02d}-01"]
    return comum.gravar(UF, viagens)
