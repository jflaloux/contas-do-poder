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
    # 09/11/2026 (balanço): o histórico da Câmara põe "SUPLENCIA" e "Exercício" no mesmo dia (vale a ordem da API) e o
    # suplente convocado às vezes não ganha o evento "Exercício"; ordenar por (data, situação) deixava Marcos Braz sem
    # nenhum mês no cargo
    from datetime import date
    from . import balanco
    ev = [["2023-02-01", 57, None], ["2026-05-28", 57, "SUPLENCIA"], ["2026-05-28", 57, "CONVOCADO"], ["2026-05-28", 57, "Exercício"],
          ["2026-10-10", 57, "SUPLENCIA"]]
    caso("Balanço: SUPLENCIA e Exercício no mesmo dia, na ordem da API", balanco._intervalos_camara(ev, date(2026, 10, 31))
         == [(date(2026, 5, 28), date(2026, 10, 10))])
    ev = [["2024-12-04", 57, "CONVOCADO"], ["2025-11-13", 57, "SUPLENCIA"]]
    caso("Balanço: CONVOCADO sem 'Exercício' depois conta como exercício", balanco.meses_em_exercicio(ev, date(2026, 10, 31))
         == {a * 100 + m for a in (2024, 2025) for m in range(1, 13) if 202412 <= a * 100 + m <= 202511})
    fr = balanco._fracoes([(date(2024, 6, 16), date(2024, 7, 31))], date(2026, 10, 31))
    caso("Balanço: meio mês no cargo conta 0,5", fr == {202406: 0.5, 202407: 1.0})
    vig = [(date(2023, 2, 1), 100.0), (date(2026, 2, 20), 128.0)]
    caso("Balanço: limite da cota no mês da mudança, pelos dias", abs(balanco.limite_do_mes(vig, 202602) - (100 * 19 + 128 * 9) / 28) < 1e-9
         and balanco.limite_do_mes(vig, 202601) == 100.0 and balanco.limite_do_mes(vig, 202603) == 128.0)
    # 03/11/2026: a folha de out/2026 de Salvador saiu com 1 dos 19 secretários (o portal publica aos poucos)
    from .prefeituras import salvador
    ant = pd.DataFrame([{"aaaamm": 202609, "tp": "pr" if i == 0 else "se"} for i in range(19)])
    caso("Salvador: mês com 1 de 19 pessoas é folha incompleta", salvador.incompleto([{"tp": "se"}], ant, 202610))
    caso("Salvador: mês completo passa", not salvador.incompleto([{"tp": "pr"}] + [{"tp": "se"}] * 17, ant, 202610))
    caso("Salvador: primeiro mês guardado não tem com o que comparar", not salvador.incompleto([{"tp": "se"}], ant.iloc[0:0], 202501))
    # 04/11/2026: a Alepi recebe as notas da verba aos poucos; ago/2026 ficou com 2 deputados porque só os 2 últimos meses
    # eram relidos
    from .assembleias import pi
    vb = pd.DataFrame([{"ano": 2026, "mes": m, "parlamentar": f"D{i}"} for m in range(1, 8) for i in range(30)]
                      + [{"ano": 2026, "mes": 8, "parlamentar": f"D{i}"} for i in range(2)]
                      + [{"ano": 2026, "mes": 9, "parlamentar": f"D{i}"} for i in range(20)])
    caso("Alepi: meses com a verba pela metade são relidos", pi.incompletos(vb, [202600 + m for m in range(1, 11)]) == [202608, 202609, 202610])
    # revisão de 10/11/2026: convocação com posse depois (Priscila Costa: convocada 9/7/2026, posse 6/8/2026); limite da
    # cota em fev/2026 (mudou no dia 20) para quem esteve no cargo só parte do mês (Soldado Noelio, 11 a 28/02)
    ev = [["2026-07-09", 57, "CONVOCADO"], ["2026-07-09", 57, "CONVOCADO"], ["2026-08-06", 57, "Exercício"]]
    caso("Balanço: com posse depois da convocação, vale a posse", balanco._intervalos_camara(ev, date(2026, 10, 31))
         == [(date(2026, 8, 6), date(2026, 10, 31))])
    dias = [date(2026, 2, d) for d in range(11, 29)]
    esperado = (100 * 9 + 128 * 9) / 28  # 11 a 19/02 no valor antigo, 20 a 28/02 no novo
    caso("Balanço: limite da cota pelos dias em exercício, com a mudança no meio do mês",
         abs(balanco.limite_dos_dias(vig, dias) - esperado) < 1e-9)
    # terceira revisão (10/11/2026): pesos da equipe, da cota e dos outros gastos do Senado; convocação de um dia
    def lin(pid, am, grupo, cat, v, rat=False):
        return {"id_politico": pid, "ano": am // 100, "mes": am % 100, "grupo": grupo, "categoria": cat, "descricao": "x",
                "valor": v, "fonte": "f", "rateado": rat}
    L = []
    for pid in ("dep-1", "dep-2"):
        L += [lin(pid, 202500 + m, "ganha", "salario", 46366.19) for m in range(1, 6)]
        L += [lin(pid, 202500 + m, "custa", "cota_parlamentar", 40000) for m in range(1, 6)]
        L += [lin(pid, 202500 + m, "equipe", "assessores_gabinete", 130000) for m in range(1, 6)]
    L.append(lin("dep-1", 202506, "equipe", "assessores_gabinete", 130000))  # 1 dia no cargo, o resto de licença
    L.append(lin("dep-2", 202506, "custa", "cota_parlamentar", 3000))  # nota depois da saída, sem licença
    L += [lin("sen-9", 202500 + m, "ganha", "salario", 46366.19) for m in range(1, 4)]
    L += [lin("sen-9", 202500 + m, "custa", "outros_gastos_mandato", 1000, True) for m in range(1, 7)]
    L.append(lin("sen-9", 202502, "equipe", "assessores_gabinete", -500))  # estimativa negativa (0 assessores)
    pol = [{"id": "dep-1", "casa": "camara", "nome": "A", "uf": "SP"}, {"id": "dep-2", "casa": "camara", "nome": "B", "uf": "SP"},
           {"id": "dep-3", "casa": "camara", "nome": "C", "uf": "SP"},
           {"id": "sen-9", "casa": "senado", "nome": "D", "uf": "SP", "exercicios": [{"inicio": "2025-01-01", "fim": "2025-03-31"}]}]
    hist = {"1": [["2025-01-01", 57, "Exercício"], ["2025-06-01", 57, "Licença"]],
            "2": [["2025-01-01", 57, "Exercício"], ["2025-05-31", 57, "SUPLENCIA"]],
            "3": [["2025-03-10", 57, "CONVOCADO"], ["2025-03-10", 57, "SUPLENCIA"]]}
    df = balanco.calcular(pd.DataFrame(L), pol, hist, hoje=date(2025, 6, 30))[0].set_index("id")
    caso("Balanço: verba de gabinete do mês com 1 dia no cargo pesa o gasto ÷ o disponível (não passa de 100%)",
         df.loc["dep-1", "e_n"] > 5.9 and df.loc["dep-1", "e_pct"] <= 100)
    caso("Balanço: nota da cota num mês sem exercício nem licença fica no gasto, sem contar o mês",
         abs(df.loc["dep-2", "c_n"] - 5) < 0.01 and df.loc["dep-2", "c"] == 203000)
    caso("Balanço: outros gastos do Senado (valor anual repartido) contam só os meses no cargo", abs(df.loc["sen-9", "o_n"] - 3) < 0.01)
    caso("Balanço: convocação e suplência no mesmo dia, sem pagamento, não contam como mês no cargo", "dep-3" not in df.index)
    caso("Balanço: equipe estimada negativa do Senado conta zero", df.loc["sen-9", "e"] == 0)
    caso("Balanço: meses sem pagamento e de licença com subsídio em fração, sem passar dos meses no cargo",
         (df.r_sem_pagamento <= df.mc + 1e-9).all() and (df.r_n <= df.mc + df.r_licenca + 1e-6).all())
    from .site import _salario_repetido
    caso("Site: no mês seguinte à saída, sai o salário igual (±R$ 1) ao de um mês que já sai",
         _salario_repetido({202605: 29144.46, 202608: 5000.0}, [29144.46, 29144.0]) == {202605})
    seg = pd.DataFrame([{"aaaamm": 202611, "tp": "se"} for _ in range(10)])
    caso("Salvador: mês menor confirmado pelo mês seguinte é aceito",
         salvador.confirmado([{"tp": "pr"}] + [{"tp": "se"}] * 9, seg, 202610) and not salvador.confirmado([{"tp": "se"}], seg, 202610))
    # gravação por parte (util.gravar_json_por_parte): os dois casos reais, em cópias num diretório temporário
    import json as _json
    import tempfile
    from pathlib import Path
    from . import util
    from .vereadores import comum as vcomum
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        guardados = util._arquivo_eventos, util._eventos
        util._arquivo_eventos, util._eventos = (lambda lugar_: tmp / f"recusas_{lugar_}.json"), None
        try:
            # 03/11/2026: Salvador com a folha pela metade (1 de 19 no cargo) segurava os meses novos do Recife
            arq = tmp / "prefeituras.json"
            def pref(n_sal, x_sal, n_rec, ult_rec):
                return {"meta": {"tipos": [], "cidades": {"2927408": {"n": "Salvador", "ultimo_mes": 202610 if x_sal == 1 else 202609},
                                                          "2611606": {"n": "Recife", "ultimo_mes": ult_rec}}},
                        "p": [{"id": f"pre-2927408-{i}", "cid": "2927408", "x": 1 if i < x_sal else 0} for i in range(n_sal)]
                             + [{"id": f"pre-2611606-{i}", "cid": "2611606", "x": 1} for i in range(n_rec)]}
            arq.write_text(_json.dumps(pref(19, 19, 23, 202606)), encoding="utf-8")
            ok = util.gravar_json_por_parte(arq, pref(19, 1, 26, 202610))
            r = _json.loads(arq.read_text(encoding="utf-8"))
            sal = [x for x in r["p"] if x["cid"] == "2927408"]
            ev = util.ler_recusas()
            caso("Gravação por parte: Salvador pela metade fica com a parte anterior, e o Recife entra",
                 ok and sum(x["x"] for x in sal) == 19 and r["meta"]["cidades"]["2927408"]["ultimo_mes"] == 202609
                 and sum(1 for x in r["p"] if x["cid"] == "2611606") == 26 and r["meta"]["cidades"]["2611606"]["ultimo_mes"] == 202610
                 and ev.get(f"{util._rel(arq)}#cid=2927408", {}).get("estado") == "recusado")
            ok2 = util.gravar_json_por_parte(arq, pref(19, 19, 26, 202610))
            caso("Gravação por parte: a parte que volta ao normal entra e a recusa dela vira aceite",
                 ok2 and util.ler_recusas()[f"{util._rel(arq)}#cid=2927408"]["estado"] == "aceito")
            # 20 a 27/10/2026: a verba do Recife com erro 500 (dt vazio nos 37 vereadores) segurava o camaras.json inteiro
            arq = tmp / "camaras.json"
            def cam(dt_recife, tipos, idx, valor_jp):
                return {"meta": {"tipos": tipos, "cidades": {"2611606": {"n": "Recife"}, "2507507": {"n": "João Pessoa", "v": valor_jp}}},
                        "p": [{"id": f"ver-2611606-{i}", "cid": "2611606", "dt": {"2026": {"verba_gabinete": [[idx, 100]]}} if dt_recife else {}}
                              for i in range(37)]
                             + [{"id": f"ver-2507507-{i}", "cid": "2507507", "dt": {}, "v": valor_jp} for i in range(29)]}
            arq.write_text(_json.dumps(cam(True, ["Aluguel", "Combustível"], 0, 1)), encoding="utf-8")
            ok = util.gravar_json_por_parte(arq, cam(False, ["Combustível", "Telefone"], 0, 2), ajustar=vcomum.remapear_tipos)
            r = _json.loads(arq.read_text(encoding="utf-8"))
            rec = [x for x in r["p"] if x["cid"] == "2611606"]
            i = rec[0]["dt"]["2026"]["verba_gabinete"][0][0] if rec and rec[0]["dt"] else None
            caso("Gravação por parte: o Recife sem a verba fica com a parte anterior (índices dos tipos refeitos), e João Pessoa entra",
                 ok and len(rec) == 37 and i is not None and r["meta"]["tipos"][i] == "Aluguel"
                 and all(x["v"] == 2 for x in r["p"] if x["cid"] == "2507507") and r["meta"]["cidades"]["2507507"]["v"] == 2)
        finally:
            util._arquivo_eventos, util._eventos = guardados
    # viagens dos governadores de BA, ES e RS (10/11/2026): fontes sem o nome (cargo) ou com as datas só no histórico
    from .viagens_governadores import ba as vba
    from .viagens_governadores import es as ves
    from .viagens_governadores import rs as vrs

    def em_ms(dia):
        import datetime
        return int(datetime.datetime.fromisoformat(dia + "T00:00:00+00:00").timestamp() * 1000)
    bil = [[1, "Governador", em_ms("2026-03-05"), em_ms("2026-02-24"), "AÉREO", "POA - CGH", "Porto Alegre", "São Paulo", 1000],
           [2, "Governador", em_ms("2026-03-07"), em_ms("2026-02-24"), "AÉREO", "CGH - BSB", "São Paulo", "Brasília", 500],
           [3, "Governador", em_ms("2026-03-09"), em_ms("2026-02-24"), "AÉREO", "BSB - POA", "Brasília", "Porto Alegre", 700],
           [4, "Governador", em_ms("2026-03-09"), em_ms("2026-03-20"), "AÉREO", "BSB - POA", "Brasília", "Porto Alegre", 90],
           [5, "Governador", em_ms("2026-04-01"), em_ms("2026-03-20"), "SEGURO", "", None, None, 300],
           [6, "Governador", em_ms("2026-04-01"), em_ms("2026-03-20"), "AÉREO", "POA - GRU - JFK", "Porto Alegre", "New York", 20000],
           [7, "Governador", em_ms("2026-04-10"), em_ms("2026-03-20"), "AÉREO", "POA - CGH", "Porto Alegre", "São Paulo", 800],
           [8, "Vice-Governador", em_ms("2026-03-05"), em_ms("2026-03-01"), "AÉREO", "POA - CGH", "Porto Alegre", "São Paulo", 400],
           [9, "Governador", em_ms("2024-12-30"), em_ms("2024-12-01"), "AÉREO", "POA - CGH", "Porto Alegre", "São Paulo", 999]]
    desp = [["Governador", em_ms("2026-03-08"), em_ms("2026-03-08"), "Brasília", "Hospedagem", 200],
            ["Governador", em_ms("2026-09-10"), em_ms("2026-09-10"), "Caxias do Sul", "Hospedagem", 300],
            ["Governador", em_ms("2026-09-11"), em_ms("2026-09-11"), "Portão", "Alimentação", 50],
            ["Governador", em_ms("2026-09-14"), em_ms("2026-09-14"), "Santa Rosa", "Alimentação", 0.0]]
    rsv = {v["inicio"]: v for v in vrs.viagens(bil, desp) if v["cargo"] == "Governador"}
    caso("RS viagens: ida, conexão e volta a Porto Alegre são uma viagem (com a remarcação do mesmo dia)",
         rsv["2026-03-05"]["passagens"] == 2290 and rsv["2026-03-05"]["fim"] == "2026-03-09"
         and rsv["2026-03-05"]["destino"] == "São Paulo; Brasília")
    caso("RS viagens: despesa dentro de uma viagem de avião entra em outros dela", rsv["2026-03-05"]["outros"] == 200)
    caso("RS viagens: seguro-viagem em outros, e bilhete novo saindo de Porto Alegre abre outra viagem",
         rsv["2026-04-01"]["outros"] == 300 and rsv["2026-04-01"]["passagens"] == 20000 and "2026-04-10" in rsv)
    caso("RS viagens: despesas de dias seguidos sem avião são uma viagem por terra; valor zero não conta",
         rsv["2026-09-10"]["outros"] == 350 and rsv["2026-09-10"]["fim"] == "2026-09-11" and "2026-09-14" not in rsv)
    caso("RS viagens: a pessoa sai do cargo e da data (vice à parte), e nada antes de 2025",
         rsv["2026-03-05"]["nome"] == "Eduardo Leite" and any(v["cargo"] == "Vice-Governador" and v["nome"] == "Gabriel Souza"
                                                              for v in vrs.viagens(bil, desp)) and "2024-12-30" not in rsv)
    linhas_ba = [["Vice Governador", "s1", em_ms("2026-01-21"), em_ms("2026-01-25"), "ILHEUS", "BA", "nob1", em_ms("2026-02-27"), 1000.0],
                 ["Vice Governador", "s1", em_ms("2026-01-21"), em_ms("2026-01-25"), "ILHEUS", "BA", "nob2", em_ms("2026-03-10"), 200.0],
                 ["Vice Governador", "s2", em_ms("2924-08-26"), em_ms("2924-08-27"), "SALVADOR", "BA", "nob3", em_ms("2026-03-10"), 50.0],
                 ["Assessor", "s3", em_ms("2026-01-21"), em_ms("2026-01-25"), "ILHEUS", "BA", "nob4", em_ms("2026-02-27"), 70.0]]
    bav = vba.viagens(linhas_ba)
    caso("BA viagens: a diária paga em duas ordens bancárias soma; data errada da fonte (2924) e outro cargo ficam fora",
         len(bav) == 1 and bav[0]["diarias"] == 1200.0 and bav[0]["destino"] == "Ilheus/BA" and bav[0]["nome"] == "Geraldo Júnior")
    caso("ES viagens: período do histórico ('no período de 04.03.2025 a 14.03.2025'), sem a data da cotação nem a do decreto",
         ves.periodo_do_historico("viagem para o Vietnam, no período de 04.03.2025 a 14.03.2025. Decreto de 27.10.2023. Cotação do "
                                  "dólar na data de 13.02.2025, processo 2025-LPGKV", 2025) == ("2025-03-04", "2025-03-14"))
    caso("ES viagens: período do histórico ('nos dias 16 e 17/08/2026'; número de processo não vira data)",
         ves.periodo_do_historico("nos dias 16 e 17/08/2026. Processo nº 2026-SMK72 e 12345678", 2026) == ("2026-08-16", "2026-08-17"))
    caso("ES viagens: período do histórico ('no dia 08/07/2026, com retorno no mesmo dia'; sem período: None)",
         ves.periodo_do_historico("SAINDO DE VITÓRIA, NO DIA 08/07/2026, COM RETORNO NO MESMO DIA", 2026) == ("2026-07-08", "2026-07-08")
         and ves.periodo_do_historico("Reforço de empenho. RD-030/2025/SCM", 2025) is None)
    es_l = [{"Ano": "2025", "Data": "10/02/2025 00:00:00", "ValorPago": "0,0000", "Favorecido": "RICARDO REZENDE FERRACO",
             "HistoricoDocumento": "viagem no período de 04.03.2025 a 14.03.2025", "Documento": "2025NE00001", "DocumentoEmpenho": "2025NE00001",
             "UnidadeGestora": "SECRETARIA DA CASA MILITAR", "CargoFuncaoDiaria": "|SCM/#VICE-GOVERNADOR DO ESTADO#"},
            {"Ano": "2025", "Data": "19/02/2025 00:00:00", "ValorPago": "26.684,9900", "Favorecido": "RICARDO REZENDE FERRACO",
             "HistoricoDocumento": " ", "Documento": "2025OB00002", "DocumentoEmpenho": "2025NE00001",
             "UnidadeGestora": "SECRETARIA DA CASA MILITAR", "CargoFuncaoDiaria": ""},
            {"Ano": "2025", "Data": "01/04/2025 00:00:00", "ValorPago": "0,0000", "Favorecido": "RICARDO REZENDE FERRACO",
             "HistoricoDocumento": "sem pagamento", "Documento": "2025NE00009", "DocumentoEmpenho": "2025NE00009",
             "UnidadeGestora": "SECRETARIA DA CASA MILITAR", "CargoFuncaoDiaria": ""}]
    esv = ves.montar_viagens(es_l)
    caso("ES viagens: um empenho é uma viagem (valor pago das ordens bancárias, datas do histórico); empenho sem pagamento fica fora",
         len(esv) == 1 and esv[0]["diarias"] == 26684.99 and esv[0]["inicio"] == "2025-03-04" and esv[0]["fim"] == "2025-03-14"
         and esv[0]["cargo"] == "VICE-GOVERNADOR DO ESTADO")
    print(f"{total - len(falhas)}/{total} casos certos" + (f"; falharam: {falhas}" if falhas else ""))
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(executar())
