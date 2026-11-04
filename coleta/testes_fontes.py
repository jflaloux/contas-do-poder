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

    # fornecedor pessoa física: o nome nunca vai para o site (08/10/2026: desde 01/10, o CPF tirado deixava o documento
    # vazio, e o site mostrava o nome de quem não tinha CNPJ)
    from .assembleias import ro
    from .vereadores import comum as vc

    def cpf_inventado(base9):
        """Os 11 algarismos de um CPF inventado (os 9 de base e os dois verificadores calculados), sem número no arquivo."""
        d = [int(c) for c in base9]
        for n in (9, 10):
            d.append(sum(d[i] * (n + 1 - i) for i in range(n)) * 10 % 11 % 10)
        return "".join(map(str, d))
    cpf = cpf_inventado("011122233")  # começa com zero: sem ele, fica com 10 algarismos
    caso("mascarar: CPF vira a marca PF", vc.mascarar(f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}") == "PF" and vc.mascarar("***.111.222-**") == "PF")
    caso("mascarar: CNPJ fica e vazio fica vazio", vc.mascarar("12.345.678/0001-90") == "12.345.678/0001-90" and vc.mascarar("") == "")
    # nomes inventados, com as mesmas armadilhas dos nomes reais: sobrenome que é palavra de empresa ("Câmara", "Sá", "Mei")
    pf = [("PF", "XYZ COMERCIAL LTDA"), ("***.111.222*-**", "Fulano"), (cpf, "Fulano"), ("", "Carlos Pereira"),
          ("", "Fulana Câmara da Costa"), ("", "MARIA NOGUEIRA SÁ DE ALMEIDA"), ("", "REGINA MARIA MEI SOUZA"),
          ("", "TAXI - JOSE DA SILVA"), ("", "Fulano de Tal e Beltrana de Tal - SEI 26.0.000012345-6"), (None, "José")]
    caso("pessoa física: sem CNPJ e com nome de pessoa, ou com CPF, não mostra o nome", all(vc.fornecedor_pf(d, n) for d, n in pf))
    empresas = [("12.345.678/0001-90", "Fulano de Tal"), ("1234567800019", "X"), ("", "ABC VEÍCULOS LTDA"), ("", "Energia DistribuiçãoS/A"),
                ("", "Prefeitura Municipal de Exemplo"), ("", "ZOOM COMMUNICATIONS INC"), ("", "Silva & Souza Ltda 10.111.222/0001 50")]
    caso("empresa: com CNPJ, ou sem CNPJ e com nome de empresa, mostra o nome", not any(vc.fornecedor_pf(d, n) for d, n in empresas))
    caso("nome sem o começo de um CPF", vc.sem_cpf_curto(f"Fulana de Tal {cpf[:9]}") == "Fulana de Tal"
         and vc.sem_cpf_curto("XYZ LTDA 1112223000144") == "XYZ LTDA 1112223000144" and vc.empresa(f"Fulano Silva {cpf[1:]}") == "Fulano Silva")
    caso("Alero: nome e documento do prestador", ro._prestador("XYZ LTDA ME 1112223000144 AVENIDA BRASIL 352 - Cacoal - RO")
         == ("XYZ LTDA ME", "1112223000144") and ro._prestador(f"FULANO SILVA {cpf[1:]} AV. BRASIL") == ("FULANO SILVA", "PF")
         and ro._prestador("FULANO ***.111.222*-** RUA X") == ("FULANO", "PF"))
    ver = pd.DataFrame([{"codigo": 1, "nome": "Ver A", "nome_civil": "", "partido": "", "genero": "M", "eleito": "eleito", "pagina": ""}])
    mand = pd.DataFrame([{"codigo": 1, "inicio": "2025-01-01", "fim": ""}])
    desp = pd.DataFrame([(2025, 1, 1, "Aluguel", "Maria da Silva Souza", "", 1000.0), (2025, 1, 1, "Aluguel", "Beltrano Souza", "PF", 900.0),
                         (2025, 1, 1, "Combustível", "Posto Bom Ltda", "", 500.0), (2025, 1, 1, "Assessoria", "Fulano de Tal", "12.345.678/0001-90", 800.0)],
                        columns=["ano", "mes", "codigo", "tipo", "fornecedor", "cnpj_cpf", "valor"])
    tipos = vc.Tipos()
    _, ps = vc.montar({"cod": 1, "n": "Teste", "uf": "XX", "casa": "Câmara", "inicio": 202501, "ultimo_mes": 202501}, tipos, ver, mand, despesas=desp)
    nomes = [tipos.lista[i] for i, _ in ps[0]["dt"]["leg"]["fornecedores"]]
    caso("montar: o site mostra 'Pessoa física' e nunca o nome de quem não tem CNPJ",
         "Pessoa física" in nomes and "Posto Bom Ltda" in nomes and "Fulano de Tal" in nomes
         and not any(n in tipos.lista for n in ("Maria da Silva Souza", "Beltrano Souza")))
    # verba da Câmara do Recife congelada (27/10/2026): a fonte não é pulada (a folha continua) e o robô não chama a verba
    from unittest import mock
    from . import onde, situacao
    from .vereadores import recife
    caso("Recife: congelamento só da verba não pula a fonte", onde.CONGELADAS["vereadores/recife"].get("so_a_verba") and not onde.congelada("vereadores/recife"))
    with mock.patch.object(recife, "mandatos"), mock.patch.object(recife, "folha"), mock.patch.object(recife, "verba") as v:
        recife.coletar()
    caso("Recife: coletar() não chama a verba", not v.called)
    caso("Recife: a verba mostrada vai até o mês congelado (dez/2025)", recife.VERBA_ATE == 202512)
    # conferência: a verba de gabinete da Câmara sai com atraso (03/11/2026: último mês julho, quatro meses de atraso)
    from . import conferir
    def verba(*meses):  # (ano, mês, deputados com verba) -> lançamentos
        return pd.DataFrame([{"id_politico": f"dep-{i}", "ano": a, "mes": m, "categoria": "assessores_gabinete", "valor": 1000.0}
                             for a, m, n in meses for i in range(n)])
    lanc = pd.concat([verba((2026, 6, 500), (2026, 7, 514), (2026, 8, 3)),
                      pd.DataFrame([{"id_politico": "sen-1", "ano": 2026, "mes": 10, "categoria": "assessores_gabinete", "valor": 1.0}]
                                   + [{"id_politico": "dep-1", "ano": 2026, "mes": 10, "categoria": "cota_parlamentar", "valor": 1.0}])])
    caso("Conferência: o último mês da verba é o último com deputados de verdade (não conta mês de poucos casos, senador nem outra categoria)",
         conferir.ultimo_mes_da_verba(lanc, (2026, 11)) == ((2026, 7), 4))
    caso("Conferência: atraso de 6 meses ainda passa, de 7 não",
         conferir.ATRASO_MAXIMO_VERBA - conferir.ultimo_mes_da_verba(lanc, (2027, 1))[1] >= 0
         and conferir.ATRASO_MAXIMO_VERBA - conferir.ultimo_mes_da_verba(lanc, (2027, 2))[1] < 0)
    caso("Conferência: sem nenhuma verba de gabinete, o atraso é enorme (falha)",
         conferir.ultimo_mes_da_verba(lanc[lanc.mes != 7].query("mes != 6"), (2026, 11)) == ((None, None), 99))
    caso("Conferência: mês novo publicado vira o mês conferido", conferir.ultimo_mes_da_verba(
         pd.concat([lanc, verba((2026, 8, 520))]), (2026, 11)) == ((2026, 8), 3))
    # 03/11/2026: portaltp devolveu um objeto com a "mensagem" para o mês que ainda não saiu (Porto Velho, 10/2026) e o robô
    # tentou ler a frase como se fosse registro; o portal de SP devolveu HTTP 503 e o max() da lista vazia derrubou a etapa
    from .folhas_estaduais import sp
    from .vereadores import portaltp
    msg = {"mensagem": "Informamos que, no período consultado, não houve informações disponibilizadas pelo Município."}
    caso("portaltp: mês sem dados (objeto com a mensagem) vale como lista vazia", portaltp._lista(msg, "/api/x", 202610) == [])
    caso("portaltp: lista de registros passa como está", portaltp._lista([{"nome": "A"}], "/api/x", 202601) == [{"nome": "A"}])
    try:
        portaltp._lista({"erro": "outro formato"}, "/api/x", 202610)
        caso("portaltp: objeto de outro formato é erro, não mês vazio", False)
    except RuntimeError:
        caso("portaltp: objeto de outro formato é erro, não mês vazio", True)
    try:
        sp._arquivos("<html><h2>Service Unavailable</h2></html>")
        caso("SP: página sem a lista de arquivos dá erro claro (e não max() de lista vazia)", False)
    except RuntimeError:
        caso("SP: página sem a lista de arquivos dá erro claro (e não max() de lista vazia)", True)
    arq = sp._arquivos('<a href="historico/remuneracao_Setembro_2026.rar"></a><a href="txt/RemuneracaoAtivos.csv"></a>')
    caso("SP: a lista traz a série histórica e o mês atual (o seguinte ao último)", sorted(arq) == [202609, 202610])
    print(f"{total - len(falhas)}/{total} casos certos" + (f"; falharam: {falhas}" if falhas else ""))
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(executar())
