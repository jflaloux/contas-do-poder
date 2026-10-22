"""Testes da base unificada quando uma parte falha (coleta/padronizar.py): a parte que não pode ser montada (arquivo bruto
que falta, ou qualquer erro) fica como estava na base anterior, e a rodada segue. Em 20/10/2026 a Câmara parou de responder,
camara_cota_site.csv não foi gravado, o padronizar caiu e nada foi salvo.

Roda numa pasta temporária, com um pedaço da base que está no Git (dados/processados/), sem nenhum arquivo bruto (como no
começo da rodada do GitHub). Não abre a internet nem mexe nos arquivos de dados.

    python3 -m coleta.testes_padronizar
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

import pandas as pd

from . import padronizar, util
from .config import PROCESSADOS


def _pedaco(origem, destino, n_dep=15, n_sen=8):
    """Copia um pedaço da base (alguns deputados e senadores e todo o governo federal) para a pasta de teste."""
    destino.mkdir(parents=True)
    pol = json.loads((origem / "politicos.json").read_text(encoding="utf-8"))
    deps = [p for p in pol if p["casa"] == "camara"][:n_dep]
    sens = [p for p in pol if p["casa"] == "senado"][:n_sen]
    pol = deps + sens + [p for p in pol if p["casa"] == "executivo"]
    ids = {p["id"] for p in pol}
    (destino / "politicos.json").write_text(json.dumps(pol, ensure_ascii=False), encoding="utf-8")
    lanc = pd.read_csv(origem / "lancamentos.csv.gz")
    lanc[lanc.id_politico.isin(ids)].to_csv(destino / "lancamentos.csv.gz", index=False)
    eq = pd.read_csv(origem / "equipe.csv")
    eq[eq.id_politico.isin(ids)].to_csv(destino / "equipe.csv", index=False)
    shutil.copy(origem / "metadados.json", destino / "metadados.json")
    return pol


def _soma(pasta, prefixo):
    lanc = pd.read_csv(pasta / "lancamentos.csv.gz")
    return round(float(lanc[lanc.id_politico.str.startswith(prefixo)].valor.sum()), 2)


def _dia(iso):
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}"


def _situacao(proc, tmp):
    """{fonte: linha} da situação das fontes, lendo os metadados da pasta de teste e gravando só nela."""
    from . import situacao
    nomes = ("PROCESSADOS", "SAIDA_MD", "SAIDA_JSON", "SAIDA_SITE", "SAIDA_RODADA")
    salvos = {k: getattr(situacao, k) for k in nomes}
    situacao.PROCESSADOS, situacao.SAIDA_MD, situacao.SAIDA_JSON = proc, tmp / "situacao.md", tmp / "situacao.json"
    situacao.SAIDA_SITE, situacao.SAIDA_RODADA = tmp / "situacao-site.json", tmp / "rodada-resumo.json"
    try:
        situacao.executar()
        return {l["fonte"]: l for l in json.loads((tmp / "situacao.json").read_text(encoding="utf-8"))["fontes"]}
    finally:
        for k, v in salvos.items():
            setattr(situacao, k, v)


def executar():
    falhas, total = [], 0

    def caso(nome, obtido, esperado):
        nonlocal total
        total += 1
        ok = obtido == esperado
        print(f"{'ok ' if ok else 'ERRO'} {nome}: {obtido}" + ("" if ok else f" (esperado {esperado})"))
        if not ok:
            falhas.append(nome)

    salvos = {k: getattr(padronizar, k) for k in ("BRUTOS", "PROCESSADOS", "CACHE", "_camara", "_senado")}
    eventos = util._arquivo_eventos, util._eventos
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        proc, brutos = tmp / "dados" / "processados", tmp / "dados" / "brutos"
        brutos.mkdir(parents=True)
        pol = _pedaco(PROCESSADOS, proc)
        meta0 = json.loads((proc / "metadados.json").read_text(encoding="utf-8"))
        antes = {c: _soma(proc, p) for c, p in padronizar.PARTES.items()}
        por_casa = lambda lista: {c: sum(p["casa"] == c for p in lista) for c in padronizar.PARTES}
        padronizar.BRUTOS, padronizar.PROCESSADOS, padronizar.CACHE = brutos, proc, tmp / "dados" / "cache"
        util._arquivo_eventos = lambda lugar: tmp / f"recusas_{lugar}.json"
        util._eventos = None
        try:
            # 1) nenhum arquivo bruto (a coleta das três partes falhou): não cai, e a base fica igual à anterior
            try:
                padronizar.executar()
                caiu = None
            except Exception as e:  # noqa: BLE001
                caiu = repr(e)
            caso("sem nenhum arquivo bruto, o padronizar não cai", caiu, None)
            meta = json.loads((proc / "metadados.json").read_text(encoding="utf-8"))
            caso("as três partes vêm da base anterior", sorted(meta.get("base_anterior", {})), ["camara", "executivo", "senado"])
            caso("o motivo diz o arquivo que falta", "camara_cota_site.csv" in meta["base_anterior"]["camara"]["motivo"], True)
            caso("a data dos dados é a da base anterior", meta["base_anterior"]["camara"]["dados_de"], meta0["gerado_em"])
            caso("mesmas pessoas em cada parte",
                 por_casa(json.loads((proc / "politicos.json").read_text(encoding="utf-8"))), por_casa(pol))
            caso("mesmos valores em cada parte", {c: _soma(proc, p) for c, p in padronizar.PARTES.items()}, antes)
            caso("a pendência dos contracheques da Câmara não muda",
                 [p for p in meta["pendencias"] if "contracheque" in p], [p for p in meta0["pendencias"] if "contracheque" in p])

            # 2) de novo, ainda sem os brutos: a data dos dados continua a da última base montada de verdade
            padronizar.executar()
            meta2 = json.loads((proc / "metadados.json").read_text(encoding="utf-8"))
            caso("duas rodadas seguidas com a base anterior: a data não avança", meta2["base_anterior"]["camara"]["dados_de"],
                 meta0["gerado_em"])

            # 3) a Câmara montada de novo (com um valor a mais) e o resto da base anterior; um erro qualquer (não só arquivo
            # que falta) no Senado também não derruba a base
            def camara_nova():
                p, L, eq = padronizar._base_anterior("camara")
                L[0] = dict(L[0], valor=L[0]["valor"] + 1000)
                eq.assign(id_deputado=eq.id_politico.str[4:].astype(int)).rename(columns={"pessoas": "secretarios"})[
                    ["id_deputado", "ano", "mes", "secretarios", "cne"]].to_csv(brutos / "camara_pessoal.csv", index=False)
                return p, L

            def senado_quebrado():
                raise ValueError("coluna nova no arquivo do Senado")

            padronizar._camara, padronizar._senado = camara_nova, senado_quebrado
            padronizar.executar()
            meta3 = json.loads((proc / "metadados.json").read_text(encoding="utf-8"))
            caso("Câmara nova, Senado e governo da base anterior", sorted(meta3["base_anterior"]), ["executivo", "senado"])
            caso("o erro do Senado vira o motivo", meta3["base_anterior"]["senado"]["motivo"], "ValueError: coluna nova no arquivo do Senado")
            caso("a Câmara entra com o valor novo", round(_soma(proc, "dep-") - antes["camara"], 2), 1000.0)
            caso("o Senado e o governo continuam iguais", (_soma(proc, "sen-"), _soma(proc, "exe-")), (antes["senado"], antes["executivo"]))
            eq = pd.read_csv(proc / "equipe.csv")
            caso("a equipe tem as duas casas", sorted(eq.id_politico.str[:4].unique()), ["dep-", "sen-"])

            # 4) a situação das fontes marca a parte que ficou com a base anterior (com a data dos dados)
            linhas = _situacao(proc, tmp)
            caso("situação: o Senado da base anterior fica 'falhando'", linhas["federal/senado"]["situacao"], "falhando")
            caso("situação: o erro diz a data dos dados", "dados de " + _dia(meta0["gerado_em"]) in (linhas["federal/senado"]["erro"] or ""), True)
            caso("situação: a Câmara (montada de novo) não leva o aviso", "base desta rodada" in (linhas["federal/camara"]["erro"] or ""), False)
        finally:
            for k, v in salvos.items():
                setattr(padronizar, k, v)
            util._arquivo_eventos, util._eventos = eventos
            util._eventos = None
    print(f"{total - len(falhas)} de {total} casos certos")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(executar())
