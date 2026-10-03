"""Sergipe: diárias de viagem do governador e do vice, viagem por viagem, pela API do Portal da Transparência
(relatório de diárias por órgão e mês; Casa Civil e Gabinete do Vice-Governador). Só abre de dentro do Brasil.
https://www.transparencia.se.gov.br/Diarias/Relacao
As passagens não são publicadas por pessoa (só o total do mês por órgão e fornecedor): ficam de fora."""
from . import comum

UF = "SE"
FONTE = "https://www.transparencia.se.gov.br/Diarias/Relacao"
API = "https://api.transparencia.se.gov.br/api/relatorios/diaria"
ORGAOS = {"131011": "Casa Civil", "121011": "Gabinete do Vice-Governador"}
NOTA = ("Diárias de viagem do governador e do vice, viagem por viagem, pelo relatório de diárias do Portal da "
        "Transparência de Sergipe (Casa Civil e Gabinete do Vice-Governador): valor pago atualizado. As passagens não são "
        "publicadas por pessoa (só o total do mês por órgão e fornecedor) e não entram.")


def coletar(nomes):
    """`nomes`: os nomes (normalizados) do governador e do vice como a folha escreve."""
    linhas = []
    for am in comum.meses():
        a, m = divmod(am, 100)
        dias = 5 if comum.recente(am) else None
        for org in ORGAOS:
            pagina = 1
            while True:
                d = comum.obter(f"{API}?page={pagina}&limit=300&ano={a}&mes={m}&orgao={org}",
                                comum.C / "se" / f"{am}_{org}_{pagina}.json", dias)
                for x in d.get("data") or []:
                    if comum.normalizar_nome(x.get("Credor")) not in nomes:
                        continue
                    status = (x.get("Status") or "").strip()
                    linhas.append({"id": f"se-{x['id']}", "inicio": (x.get("Data saída") or "")[:10], "fim": (x.get("Data retorno") or "")[:10],
                                   "nome": x["Credor"], "cargo": x.get("Cargo"), "destino": x.get("Destino município"),
                                   "diarias": comum.num(x.get("Valor pago atualizado")),
                                   "obs": "" if status.lower() == "paga" else status, "fonte": FONTE})
                if pagina >= int(d.get("totalPages") or 1):
                    break
                pagina += 1
    return comum.gravar(UF, [l for l in linhas if l["inicio"]])
