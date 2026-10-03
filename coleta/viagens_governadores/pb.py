"""Paraíba: diárias de viagem do governador e do vice, viagem por viagem (um empenho por viagem), pela API de dados
abertos do Estado (/api/v1/remuneracao/diarias, por ano, mês e nome do credor). https://api.dados.pb.gov.br/swagger/
A resposta traz o CPF mascarado do credor: não é lido. As passagens são empenhadas a agências, sem o nome do
passageiro: ficam de fora."""
from urllib.parse import quote

from . import comum

UF = "PB"
FONTE = "https://api.dados.pb.gov.br/swagger/"
API = "https://api.dados.pb.gov.br/api/v1/remuneracao/diarias"
NOTA = ("Diárias de viagem do governador e do vice, viagem por viagem, pela API de dados abertos da Paraíba: valor pago "
        "(o empenho ainda não pago entra quando for pago). As passagens são empenhadas a agências de viagem, sem o nome "
        "do passageiro, e não entram.")


def coletar(nomes):
    linhas = []
    for am in comum.meses():
        a, m = divmod(am, 100)
        dias = 5 if comum.recente(am) else None
        for nome in sorted(nomes):
            busca = " ".join(nome.split()[:2])  # a busca é por parte do nome; o nome inteiro é conferido abaixo
            pagina = 1
            while True:
                d = comum.obter(f"{API}?ano={a}&mes={m}&nomeCredor={quote(busca)}&per_page=100&page={pagina}",
                                comum.C / "pb" / f"{am}_{busca.replace(' ', '_')}_{pagina}.json", dias)
                for x in d.get("dados") or []:
                    if comum.normalizar_nome(x.get("nomeCredor")) not in nomes:
                        continue
                    linhas.append({"id": f"pb-{x.get('anoExercicio')}-{x.get('codigoOrgao')}-{x.get('numeroEmpenho')}",
                                   "inicio": (x.get("dataSaida") or "")[:10], "fim": (x.get("dataChegada") or "")[:10],
                                   "nome": x["nomeCredor"], "cargo": x.get("nomeOrgao"), "destino": x.get("destinoViagem"),
                                   "diarias": comum.num(x.get("valorPago")),
                                   "obs": "empenhado, ainda não pago" if not comum.num(x.get("valorPago")) else "", "fonte": FONTE})
                if pagina >= int((d.get("paginacao") or {}).get("pages") or 1):
                    break
                pagina += 1
    return comum.gravar(UF, [l for l in linhas if l["inicio"]])
