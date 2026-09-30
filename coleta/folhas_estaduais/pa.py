"""Pará: Portal da Transparência (Servidores Públicos), pela API pública que o próprio portal usa:
busca pelo nome no mês e, para cada vínculo de governador ou vice ("MANDATO ELETIVO"), as rubricas do mês (vantagens e
descontos). A vice Hana Ghassan também é auditora fiscal da Secretaria da Fazenda: esse outro vínculo não entra, só o
de vice. Desde abril de 2026 a folha não traz mais ninguém em mandato eletivo (governadora e vice somem da consulta).
Só abre de dentro do Brasil. https://www.sistemas.pa.gov.br/portaltransparencia/servidores"""
from . import _http, comum

UF = "PA"
FONTE = "https://www.sistemas.pa.gov.br/portaltransparencia/servidores"
API = "https://api-servidores-publicos.sistemas.pa.gov.br/dados-transparencias"
H = {"Origin": "https://www.sistemas.pa.gov.br", "Accept": "application/json"}


def _mes_publicado(am):
    d = _http.get(f"{API}/totais-ano-mes", headers=H, params={"ano": am // 100, "mes": am % 100}) or {}
    d = d.get("data") if isinstance(d, dict) and "data" in d else d
    return bool(d) and any(v not in (None, 0, "0") for v in (d.values() if isinstance(d, dict) else [d]))


def coletar():
    meses = comum.a_fazer(UF, comum.ultimo_possivel(), refazer=2)
    ocup = [o for o in comum.ocupantes(UF) if o.get("folha_nome")]
    linhas, feitos = [], []
    try:
        for am in meses:
            nomes = list(dict.fromkeys(o["folha_nome"] for o in ocup if comum.no_cargo(o, am)))
            if not nomes or not _mes_publicado(am):
                continue
            ano, mes = divmod(am, 100)
            vistos = set()
            for nome in nomes:
                d = _http.get(f"{API}/funcionarios/filtro-por-texto", headers=H, timeout=120,
                              params={"ano": ano, "mes": mes, "texto": nome, "quantidade": 20, "ordem": "nome", "ascDesc": "ASC", "pagina": 1}) or {}
                for x in d.get("data") or []:
                    tp = comum.tp_do_cargo(x.get("cargo"))
                    if not tp or comum.normalizar_nome(x.get("nome")) != comum.normalizar_nome(nome) or x["id_funcionario"] in vistos:
                        continue
                    vistos.add(x["id_funcionario"])
                    det = _http.get(f"{API}/funcionarios/detalhes", headers=H, timeout=120, params={"ano": ano, "mes": mes, "funcionario": x["id_funcionario"]}) or {}
                    itens = det.get("data") if isinstance(det, dict) else det
                    rub = [(i.get("rubrica"), i.get("valor"), str(i.get("sessao")) == "2") for i in itens or [] if str(i.get("sessao")) in ("2", "3")]
                    partes, redutor, bruto = comum.somar_rubricas(rub)
                    if abs(bruto - float(x.get("salario_bruto") or 0)) > 1:
                        partes, bruto = None, float(x.get("salario_bruto") or 0)
                    linhas.append(comum.linha(am, tp, x["nome"], x.get("cargo"), bruto, partes, redutor))
            feitos.append(am)
    finally:  # se o tempo acabar no meio, guarda os meses já feitos
        comum.gravar(UF, linhas, feitos)
    return len(linhas)
