"""Testes de leitura de formatos de fontes que já mudaram sem aviso (com texto inventado, sem rede).

    python3 -m coleta.testes_fontes
"""
import sys

import pandas as pd

from . import padronizar
from .assembleias import ms

CABECALHO = "Deputado;Ano;Mês;Categoria;CPF/CNPJ;Fornecedor;Documento;Emissão;\"Valor (R$)\";Comprovante"
LINHA = '"DEP. FULANO";2026;Janeiro;"Combustível";16.551.514/0001-75;"Posto";NF 1;02/01/2026;"1.234,50";http://x'


def executar():
    falhas, total = [], 0

    def caso(nome, ok):
        nonlocal total
        total += 1
        if not ok:
            falhas.append(nome)

    antigo = ms._registros(f"{CABECALHO}\n{LINHA}\n")
    caso("Alems: formato antigo (sem cabeçalho de título)", len(antigo) == 1 and antigo[0]["Ano"] == "2026")
    novo = ms._registros('"Portal da Transparência da Assembleia Legislativa de Mato Grosso do Sul"\n"CEAP — Cota do Exercício da Atividade Parlamentar"\n'
                         '"Gerado em 07/10/2026 às 15:56 (horário de Mato Grosso do Sul)"\n"Filtros aplicados: Período: 2026 (todos os meses)"\n\n'
                         f"{CABECALHO}\n{LINHA}\n{LINHA}\n")
    caso("Alems: formato de 07/10/2026 (5 linhas antes das colunas)", len(novo) == 2 and novo[0]["Fornecedor"] == "Posto")
    caso("Alems: arquivo sem a linha de colunas não quebra a leitura", ms._registros("só um aviso\n") == [])
    # cota da Câmara completada pelo total mensal do site (padronizar.completar_cota_com_site)
    compl = "COMPLEMENTAÇÃO DO AUXÍLIO-MORADIA"
    # deputado 1: jan a jul batem com o site (complementação de 1.000 que vira positiva no arquivo tratado); ago com SIGEPA a mais;
    #   set com créditos (site 500 abaixo); deputado 2: o site fica 300 abaixo todo mês (consulta que omite um tipo): não confiável
    linhas = []
    for mes in range(1, 13):
        linhas += [(1, 2025, mes, "COMBUSTÍVEIS", 10000.0), (1, 2025, mes, compl, 1000.0), (2, 2025, mes, "COMBUSTÍVEIS", 20000.0)]
    cota = pd.DataFrame(linhas, columns=["id_deputado", "ano", "mes", "tipo", "valor"])
    # total do site = arquivo com a complementação NEGATIVA (11.000 - 2.000 = 9.000)
    site_linhas = []
    for mes in range(1, 13):
        t1 = 9000.0 + (3000.0 if mes == 8 else 0) - (500.0 if mes == 9 else 0)
        site_linhas += [(1, 2025, mes, t1), (2, 2025, mes, 19700.0 - (500.0 if mes == 9 else 0))]
    site = pd.DataFrame(site_linhas, columns=["id_deputado", "ano", "mes", "total_site"])
    r = padronizar.completar_cota_com_site(cota, site, {1: "a", 2: "b"})
    por = {(i, a, m): v for i, a, m, _, v in r}
    caso("cota: meses em que o site e o arquivo concordam (com a complementação negativa no site) não ganham linha", (1, 2025, 3) not in por)
    caso("cota: mês com passagem a mais no site é completado", por.get((1, 2025, 8)) == 3000.0)
    caso("cota: crédito só no site (depois de ago/2025) desconta quando o deputado é confiável", por.get((1, 2025, 9)) == -500.0)
    caso("cota: deputado com diferença fixa antes da lacuna não é confiável: sem desconto", (2, 2025, 9) not in por and (2, 2025, 10) not in por)
    caso("cota: antes da lacuna, diferença negativa nunca desconta", all(k[2] >= 8 for k, v in por.items() if v < 0))
    # a mesma conta sem a complementação, com o site abaixo antes de ago/2025: nada
    s0 = pd.DataFrame([(3, 2025, 3, 5000.0)], columns=["id_deputado", "ano", "mes", "total_site"])
    c0 = pd.DataFrame([(3, 2025, 3, "COMBUSTÍVEIS", 6000.0)], columns=["id_deputado", "ano", "mes", "tipo", "valor"])
    caso("cota: site abaixo do arquivo antes da lacuna é ignorado", padronizar.completar_cota_com_site(c0, s0, {3: "c"}) == [])
    print(f"{total - len(falhas)}/{total} casos certos" + (f"; falharam: {falhas}" if falhas else ""))
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(executar())
