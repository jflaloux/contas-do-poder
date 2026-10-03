"""Amazonas: diárias e passagens do governador e do vice, viagem por viagem (solicitação do SCDP), pelo serviço que a
página "Diárias e Passagens" do Portal da Transparência usa (por órgão, ano e mês da solicitação). Só abre do Brasil.
https://www.transparencia.am.gov.br/diarias-e-passagens/
Órgãos: 75 Casa Civil, 77 Gabinete do Vice-Governador (SGVG), 154 Casa Militar, 170 SEGOV. Os trechos em voo da Casa
Militar vêm com valor 0 (o custo do avião oficial não é publicado)."""
from . import comum

UF = "AM"
FONTE = "https://www.transparencia.am.gov.br/diarias-e-passagens/"
API = "https://www.transparencia.am.gov.br/servicos/scdp/{tipo}/{orgao}/{ano}/{mes}"
ORGAOS = (75, 77, 154, 170)
NOTA = ("Diárias e passagens do governador e do vice, viagem por viagem (solicitação no sistema de diárias e passagens), "
        "pelo Portal da Transparência do Amazonas; o mês é o do início da viagem. Trechos em voo da Casa Militar aparecem "
        "com valor zero: o custo do avião oficial não é publicado.")


def _dia(t):
    """"20/03/2025" -> "2025-03-20"."""
    t = (t or "").strip()
    return f"{t[6:10]}-{t[3:5]}-{t[0:2]}" if len(t) >= 10 and t[2] == "/" else ""


def coletar(nomes):
    viagens = {}
    for am in comum.meses():
        a, m = divmod(am, 100)
        dias = 5 if comum.recente(am) else None
        for orgao in ORGAOS:
            for tipo in ("diarias", "passagens"):
                d = comum.obter(API.format(tipo=tipo, orgao=orgao, ano=a, mes=m), comum.C / "am" / f"{am}_{orgao}_{tipo}.json", dias,
                                headers={"Accept": "application/json"})
                for x in d if isinstance(d, list) else []:
                    if comum.normalizar_nome(x.get("interessado")) not in nomes:
                        continue
                    sol = str(x["solicitacao"])
                    v = viagens.setdefault(sol, {"id": f"am-{sol}", "inicio": "", "fim": "", "nome": x["interessado"], "cargo": x.get("cargo"),
                                                 "destino": "", "diarias": 0.0, "passagens": 0.0, "obs": "", "fonte": FONTE, "_trechos": set()})
                    if tipo == "diarias":
                        v["inicio"], v["fim"] = _dia(x.get("data_ida")) or v["inicio"], _dia(x.get("data_volta")) or v["fim"]
                        v["destino"] = x.get("cidade_destino") or v["destino"]
                        v["diarias"] = comum.num(x.get("valor_total_diaria"))  # a mesma solicitação pode vir em dois meses
                    else:
                        trecho = (x.get("cidade_origem"), x.get("cidade_destino"), x.get("data_partida"))
                        if trecho in v["_trechos"]:
                            continue
                        v["_trechos"].add(trecho)
                        v["passagens"] += comum.num(x.get("valor_total_passagem"))
                        partida = _dia(x.get("data_partida"))
                        if partida and (not v["inicio"] or partida < v["inicio"]):
                            v["inicio"] = partida
                        if "CASA MILITAR" in comum.normalizar_nome(x.get("pago_terceiros")):
                            v["obs"] = "voo da Casa Militar (sem custo publicado)"
                        if not v["destino"]:
                            v["destino"] = x.get("cidade_destino") or ""
    for v in viagens.values():
        v.pop("_trechos", None)
    return comum.gravar(UF, [v for v in viagens.values() if v["inicio"]])
