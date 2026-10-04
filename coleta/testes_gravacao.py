"""Testes da gravação segura (util.gravar_csv, gravar_json, gravar_linhas e o registro da falha em onde.registrar), com
casos inventados numa pasta temporária. Não abre a internet nem mexe nos arquivos de dados.

    python3 -m coleta.testes_gravacao
"""
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd

from . import onde, util


def _folha(meses, pessoas):
    """Uma folha inventada: cada mês com as pessoas dadas (lista de nomes ou número de pessoas)."""
    linhas = []
    for am in meses:
        nomes = pessoas if isinstance(pessoas, list) else [f"PESSOA {i}" for i in range(pessoas)]
        linhas += [{"ano": am // 100, "mes": am % 100, "nome": n, "valor": 1000.0} for n in nomes]
    return pd.DataFrame(linhas)


def executar():
    falhas, total = [], 0

    def caso(nome, obtido, esperado):
        nonlocal total
        total += 1
        ok = obtido == esperado
        print(f"{'ok ' if ok else 'ERRO'} {nome}: {obtido}" + ("" if ok else f" (esperado {esperado})"))
        if not ok:
            falhas.append(nome)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        arquivo_eventos, eventos = util._arquivo_eventos, util._eventos
        arquivo_coletas, lugar = onde._arquivo, onde.LUGAR
        util._arquivo_eventos = lambda lugar_: tmp / f"recusas_{lugar_}.json"
        onde._arquivo = lambda lugar_: tmp / f"coletas_{lugar_}.json"
        util._eventos = None
        try:
            arq = tmp / "folha.csv"
            meses = [202601, 202602, 202603]
            caso("arquivo anterior inexistente: grava", util.gravar_csv(_folha(meses, 30), arq), True)
            caso("mês novo: grava", util.gravar_csv(_folha(meses + [202604], 30), arq), True)
            caso("perda pequena normal (30 para 29 pessoas num mês): grava",
                 util.gravar_csv(pd.concat([_folha(meses, 30), _folha([202604], 29)]), arq), True)
            caso("vazio: recusa", util.gravar_csv(pd.DataFrame(columns=["ano", "mes", "nome", "valor"]), arq), False)
            caso("o arquivo anterior fica depois da recusa", len(pd.read_csv(arq)), 119)
            caso("perda parcial grande (um mês de 30 para 10 pessoas): recusa",
                 util.gravar_csv(pd.concat([_folha(meses, 30), _folha([202604], 10)]), arq), False)
            caso("um mês inteiro some: recusa", util.gravar_csv(_folha([202601, 202602, 202604], 30), arq), False)
            caso("redução com motivo: grava", util.gravar_csv(_folha(meses, 30), arq, motivo="teste: o mês 04 era cópia do 03"),
                 True)
            caso("perda de 2 pessoas num mês de 5 (abaixo do mínimo de 3): grava",
                 util.gravar_csv(_folha([202601], 5), tmp / "pequena.csv") and
                 util.gravar_csv(_folha([202601], 3), tmp / "pequena.csv"), True)
            r = tmp / "retrato.csv"
            util.gravar_csv(_folha([202608], 40), r)
            caso("retrato do último mês (08 vira 09, mesmas pessoas): grava", util.gravar_csv(_folha([202609], 40), r), True)
            caso("retrato com metade das pessoas: recusa", util.gravar_csv(_folha([202610], 20), r), False)
            sem_mes = tmp / "cadastro.csv"
            util.gravar_csv(pd.DataFrame({"id": range(50), "nome": [f"N{i}" for i in range(50)]}), sem_mes)
            caso("cadastro sem mês perdendo 30 de 50: recusa",
                 util.gravar_csv(pd.DataFrame({"id": range(20), "nome": [f"N{i}" for i in range(20)]}), sem_mes), False)
            pv = tmp / "presenca.csv"
            util.gravar_linhas(pv, ["data", "id_deputado"], [{"data": f"2026-0{m}-1{d}", "id_deputado": i}
                                                            for m in (3, 4) for d in range(3) for i in range(100)],
                               delimiter=";")
            caso("CSV com ; e mês pela data, um mês some: recusa",
                 util.gravar_linhas(pv, ["data", "id_deputado"], [{"data": f"2026-03-1{d}", "id_deputado": i}
                                                                  for d in range(3) for i in range(100)], delimiter=";"),
                 False)
            js = tmp / "camaras.json"
            p = [{"id": f"v{c}{i}", "cid": c, "n": "X"} for c in (1, 2) for i in range(40)]
            util.gravar_json(js, {"meta": {"cidades": {}}, "p": p})
            caso("JSON do site: uma cidade some: recusa", util.gravar_json(js, {"meta": {}, "p": [x for x in p if x["cid"] == 1]}),
                 False)
            caso("JSON do site: uma cidade com 1 pessoa a menos: grava", util.gravar_json(js, {"meta": {}, "p": p[:-1]}), True)
            caso("JSON: o novo não se lê: recusa", util.gravar_texto(js, "{quebrado", tipo="json"), False)
            caso("JSON: arquivo anterior intacto", len(json.loads(js.read_text())["p"]), 79)
            caso("nenhum arquivo temporário sobrou", sorted(x.name for x in tmp.glob(".novo.*")), [])
            ev = util.ler_recusas()
            caso("a recusa fica registrada para a situação", ev.get(util._rel(js), {}).get("estado"), "recusado")
            util.gravar_json(js, {"meta": {}, "p": p})
            caso("depois de gravar certo, o arquivo deixa de estar recusado", util.ler_recusas()[util._rel(js)]["estado"],
                 "aceito")
            # a fonte em coleta é marcada como falhando, sem erro, e o arquivo anterior fica
            onde.LUGAR = "brasil"
            f = tmp / "verba.csv"
            util.gravar_csv(_folha(meses, 30), f)
            with onde.registrar("vereadores", "teste"):
                util.gravar_csv(_folha(meses, 30).iloc[:0], f)
            item = onde.ler("brasil")["vereadores/teste"]
            caso("onde.registrar: falha anotada", (item.get("falhas"), item.get("ultimo_erro", "")[:31]),
                 (1, "Recusado por perda de cobertura"))
            with onde.registrar("vereadores", "teste"):
                util.gravar_csv(_folha(meses, 30), f)
            caso("onde.registrar: gravação certa zera as falhas", onde.ler("brasil")["vereadores/teste"].get("falhas"), 0)
            _viagens(tmp, caso)
            _tce_pe(tmp, caso)
            _tce_es(tmp, caso)
        finally:
            util._arquivo_eventos, util._eventos = arquivo_eventos, eventos
            onde._arquivo, onde.LUGAR = arquivo_coletas, lugar
            util._eventos = None
    print(f"{total - len(falhas)} de {total} casos certos")
    return 1 if falhas else 0


def _viagens(tmp, caso):
    """Viagens dos governadores: o estado com 1 viagem gravada não aceita 0, e o mês lido não avança."""
    from .viagens_governadores import comum as vg
    pasta, lidos = vg.PASTA, vg.LIDOS
    vg.PASTA, vg.LIDOS = tmp / "viagens", tmp / "viagens" / "lidos.json"
    try:
        v = {"id": "1", "inicio": "2026-03-02", "fim": "2026-03-04", "nome": "FULANO", "cargo": "Governador",
             "destino": "Brasília", "diarias": 100.0, "passagens": 0.0, "outros": 0.0, "devolucoes": 0.0, "obs": "",
             "fonte": "x"}
        vg.gravar("SP", [v])
        vg.LIDOS.write_text(json.dumps({"SP": 202601}))
        try:
            vg.gravar("SP", [])
            recusou = False
        except vg.MenosQueOGravado:
            recusou = True
        caso("viagens: 1 viagem gravada e a fonte traz 0: recusa", recusou, True)
        caso("viagens: a viagem continua gravada", len(vg.ler("SP")), 1)
        caso("viagens: o mês lido não avança", json.loads(vg.LIDOS.read_text())["SP"], 202601)
    finally:
        vg.PASTA, vg.LIDOS = pasta, lidos


def _tce_pe(tmp, caso):
    """TCE-PE: duas listas de nomes vazias (sem erro da página) não trocam a quantidade nem apagam os nomes gravados."""
    from .tce import comum as tc, pe
    nomes_ok = {"h1": [(f"VEREADOR {i}", "VEREADOR") for i in range(8)], "h2": [("VEREADOR 0", "PRESIDENTE DA CAMARA")]}
    leitura = {"nomes": nomes_ok}
    salvos = {k: getattr(pe, k) for k in ("unidades", "tabela", "nomes", "disponiveis")}
    pasta, blocos = tc.PASTA, tc.blocos_a_fazer
    tc.PASTA = tmp / "tce"
    pe.unidades = lambda: [(2600054, "Abreu e Lima", "camara", 1, 1)]
    pe.disponiveis = lambda: [202608]
    tc.blocos_a_fazer = lambda *a, **k: [(2600054, "camara", 202608)]
    pe.tabela = lambda cm, idu, am: (40, [("VEREADOR", 9, 90000.0, "h1"), ("PRESIDENTE DA CAMARA", 1, 15000.0, "h2")])
    pe.nomes = lambda href: leitura["nomes"][href]
    try:
        pe.coletar()
        q1 = pe.cargo.ler("PE").quantidade.tolist()
        n1 = len(pe.cargo.ler_nomes("PE"))
        leitura["nomes"] = {"h1": [], "h2": []}
        pe.coletar()
        caso("TCE-PE: listas de nomes vazias: a quantidade fica", (q1, pe.cargo.ler("PE").quantidade.tolist()), (q1, q1))
        caso("TCE-PE: listas de nomes vazias: os nomes gravados ficam", (n1, len(pe.cargo.ler_nomes("PE"))), (9, 9))
        leitura["nomes"] = {"h1": nomes_ok["h1"][:3], "h2": nomes_ok["h2"]}
        pe.coletar()
        caso("TCE-PE: lista com 3 nomes para 9 no cargo (incompleta): os nomes gravados ficam",
             len(pe.cargo.ler_nomes("PE")), 9)
    finally:
        for k, f in salvos.items():
            setattr(pe, k, f)
        tc.PASTA, tc.blocos_a_fazer = pasta, blocos


def _tce_es(tmp, caso):
    """TCE-ES: o arquivo de vínculo que vem só com o cabeçalho (ou sem um mês) não troca o extrato anterior."""
    from .tce import es
    arq = tmp / "vinculo-2026-1.eletivos.csv"
    linhas = [{"esfera": f"Cidade {c}", "ug": f"Câmara {c}", "ano_mes": m, "cargo": "VEREADOR", "nome": f"N{c}-{i}"}
              for m in (202601, 202602, 202603) for c in range(10) for i in range(9)]
    es.trocar_extratos("vinculo-2026-1", [(pd.DataFrame(linhas), arq)])
    antes = arq.read_text()
    for nome, df in (("só o cabeçalho", pd.DataFrame(columns=["esfera", "ug", "ano_mes", "cargo", "nome"])),
                     ("sem um mês", pd.DataFrame([l for l in linhas if l["ano_mes"] != 202603])),
                     ("sem 3 das 10 cidades num mês", pd.DataFrame([l for l in linhas if not (l["ano_mes"] == 202602 and
                                                                                          l["esfera"] in ("Cidade 1", "Cidade 2", "Cidade 3"))]))):
        try:
            es.trocar_extratos("vinculo-2026-1", [(df, arq)])
            recusou = False
        except RuntimeError:
            recusou = True
        caso(f"TCE-ES: vínculo {nome}: recusa e o extrato anterior fica", (recusou, arq.read_text() == antes), (True, True))


if __name__ == "__main__":
    sys.exit(executar())
