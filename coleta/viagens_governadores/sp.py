"""São Paulo: gastos individualizados com diárias e passagens aéreas (Portal da Transparência do Estado), pela busca
que a página usa (POST /Diarias/Buscar, por nome do favorecido e ano). Cada registro é um item (passagem de um trecho,
seguro-viagem, diária); os itens da mesma pessoa no mesmo dia são uma viagem.
https://www.transparencia.sp.gov.br/Gastosindividualizadoscomdiariasepassagensaereas/Index"""
from . import comum

UF = "SP"
FONTE = "https://www.transparencia.sp.gov.br/Gastosindividualizadoscomdiariasepassagensaereas/Index"
API = "https://www.transparencia.sp.gov.br/Diarias/Buscar"
NOTA = ("Diárias e passagens aéreas do governador e do vice, item por item, pela consulta de gastos individualizados "
        "do Portal da Transparência de São Paulo; os itens da mesma pessoa no mesmo dia contam como uma viagem, e o "
        "seguro-viagem entra em outros.")


def coletar(nomes):
    """`nomes`: nomes normalizados. A busca é pelas duas primeiras palavras (a fonte às vezes tem espaço duplo no nome)."""
    itens = {}
    anos = sorted({am // 100 for am in comum.meses()})
    for nome in sorted(nomes):
        busca = " ".join(nome.split()[:2])
        for ano in anos:
            dias = 5 if ano == anos[-1] else None
            pagina = 1
            while True:
                d = comum.obter(API, comum.C / "sp" / f"{ano}_{busca.replace(' ', '_')}_{pagina}.json", dias, metodo="POST",
                                json={"favorecido": busca, "anoReferencia": ano, "page": pagina, "pageSize": 50, "totalItens": 0},
                                headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"})
                for x in d.get("items") or []:
                    if comum.normalizar_nome(x.get("favorecido")) not in nomes:
                        continue
                    dia = (x.get("data") or "")[:10]
                    if not dia:
                        continue
                    k = (comum.normalizar_nome(x["favorecido"]), dia)
                    v = itens.setdefault(k, {"id": f"sp-{k[0].replace(' ', '-').lower()}-{dia}", "inicio": dia,
                                             "fim": (x.get("dataFinal") or "")[:10] or dia, "nome": " ".join(x["favorecido"].split()),
                                             "cargo": x.get("cargo"), "destino": [], "diarias": 0.0, "passagens": 0.0, "outros": 0.0,
                                             "fonte": FONTE})
                    destino = " ".join((x.get("destino") or "").split())
                    if "SEGURO" in comum.normalizar_nome(destino):
                        v["outros"] += comum.num(x.get("valorTotal"))
                    else:
                        v["diarias"] += comum.num(x.get("valorDiaria"))
                        v["passagens"] += comum.num(x.get("valorPassagem"))
                        if destino and destino not in v["destino"]:
                            v["destino"].append(destino)
                if not d.get("hasNext"):
                    break
                pagina += 1
    for v in itens.values():
        v["destino"] = "; ".join(v["destino"])
    return comum.gravar(UF, list(itens.values()))
