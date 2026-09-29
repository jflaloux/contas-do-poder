"""Conferência: compara nossos números com o que os sites oficiais mostram.

Gera dados/processados/conferencia.md. Rode depois de `padronizar`.
"""
import random
import re
from datetime import datetime

import pandas as pd

import json

from .config import BRUTOS, CACHE, PROCESSADOS, RAIZ, ULTIMO_MES
from .util import baixar, ler_json, log, numero_br

SITE = "https://www.camara.leg.br"
AMOSTRA = 20
SUBSIDIOS = {39293.32, 41650.92, 44008.52, 46366.19}


def _cota_oficial_camara(id_, ano):
    """Total gasto e não utilizado da cota, como aparece na página do deputado."""
    html = baixar(f"{SITE}/deputados/{id_}", params={"ano": ano}).text
    m = re.search(r'id="percentualgastocotaparlamentar".*?</table>', html, re.S)
    if not m:
        return None, None
    bloco = m.group(0).replace("<!--", "").replace("-->", "")
    pares = dict((k.strip(), numero_br(v)) for k, v in
                 re.findall(r"<td>\s*([^<]+?)\s*</td>\s*<td>\s*([\d\.,]+)\s*</td>", bloco))
    return pares.get("Gasto"), pares.get("Não utilizado")


def _cidades_com_custo():
    arq = RAIZ / "site" / "dados" / "municipios.json"
    return sum(1 for m in json.load(open(arq, encoding="utf-8"))["m"] if m[6]) if arq.exists() else 0


def _vereadores_no_site():
    arq = RAIZ / "site" / "dados" / "municipios.json"
    return sum(m[5] for m in json.load(open(arq, encoding="utf-8"))["m"]) if arq.exists() else 0


def executar():
    random.seed(42)
    rel = [f"# Conferência dos dados — {datetime.now():%d/%m/%Y %H:%M}", ""]
    problemas = 0
    politicos = ler_json(PROCESSADOS / "politicos.json")
    lanc = pd.read_csv(PROCESSADOS / "lancamentos.csv.gz")
    deps = [p for p in politicos if p["casa"] == "camara"]
    sens = [p for p in politicos if p["casa"] == "senado"]

    # 1. Cobertura
    rel += ["## 1. Cobertura", "",
            f"- Deputados na base: {len(deps)} (em exercício hoje: {sum(p['em_exercicio'] for p in deps)} de 513)",
            f"- Senadores na base: {len(sens)} (em exercício hoje: {sum(p['em_exercicio'] for p in sens)} de 81)",
            f"- Governo federal na base: {sum(p['casa'] == 'executivo' for p in politicos)} (presidente, vice e ministros desde 2023)", ""]
    if sum(p["em_exercicio"] for p in deps) != 513 or sum(p["em_exercicio"] for p in sens) != 81:
        problemas += 1
        rel.append("**ATENÇÃO: número de parlamentares em exercício diferente do esperado.**\n")

    # 2. Cota da Câmara vs página oficial de cada deputado
    log("Conferência: cota da Câmara vs páginas oficiais (amostra)")
    cota = lanc[lanc.categoria == "cota_parlamentar"]
    rel += ["## 2. Cota parlamentar da Câmara: nossa soma × página oficial do deputado", "",
            f"Amostra aleatória de {AMOSTRA} deputados em exercício, anos 2024 e 2025.", "",
            "| Deputado | Ano | Nossa soma | Site oficial | Diferença |", "|---|---|---:|---:|---:|"]
    amostra = random.sample([p for p in deps if p["em_exercicio"]], AMOSTRA)
    difs = 0
    for p in amostra:
        id_ = int(p["id"].split("-")[1])
        for ano in (2024, 2025):
            nossa = cota[(cota.id_politico == p["id"]) & (cota.ano == ano)].valor.sum()
            oficial, _ = _cota_oficial_camara(id_, ano)
            if oficial is None:
                continue
            dif = round(nossa - oficial, 2)
            if abs(dif) >= 1:
                difs += 1
            rel.append(f"| {p['nome']} | {ano} | {nossa:,.2f} | {oficial:,.2f} | {dif:,.2f} |")
    rel += ["", f"**Resultado: {difs} diferença(s) de R$ 1 ou mais.** "
            "(Em 2024 são esperadas pequenas diferenças: ver pendências nos metadados.)", ""]
    problemas += difs

    # 3. Cota do Senado vs total da API "recursos utilizados"
    log("Conferência: cota do Senado vs API de recursos utilizados")
    rel += ["## 3. Cota parlamentar do Senado: nossa soma × total oficial por ano", ""]
    ceaps_bruto = pd.read_csv(BRUTOS / "senado_ceaps.csv")
    total, difs_s, exemplos = 0, 0, []
    for p in sens:
        cod = p["id"].split("-")[1]
        for arq in (CACHE / "senado" / "recursos").glob(f"{cod}_*.json"):
            ano = int(arq.stem.split("_")[1])
            for d in ler_json(arq):
                oficial = (d.get("cotas") or {}).get("totalValor")
                if oficial is None:
                    continue
                # ano completo (inclui janeiro/2023, que é da legislatura anterior)
                nossa = ceaps_bruto[(ceaps_bruto.id_senador == int(cod)) & (ceaps_bruto.ano == ano)].valor.sum()
                total += 1
                if abs(nossa - oficial) >= 1:
                    difs_s += 1
                    exemplos.append(f"{p['nome']} {ano}: nossa {nossa:,.2f} × oficial {oficial:,.2f}")
    rel += [f"- Comparações senador × ano: {total}", f"- **Diferenças de R$ 1 ou mais: {difs_s}**"]
    rel += [f"  - {e}" for e in exemplos[:15]] + [""]
    problemas += difs_s

    # 4. Auxílio-moradia da Câmara: total do ano vs resumo da página oficial
    log("Conferência: auxílio-moradia da Câmara")
    html = baixar(f"{SITE}/transparencia/gastos-parlamentares/").text
    texto = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    m = re.search(r"auxílio-moradia:\s*R\$\s*([\d\.,]+)", texto)
    oficial = numero_br(m.group(1)) if m else None
    mor = pd.read_csv(BRUTOS / "camara_moradia.csv")
    nossa = round(mor[mor.ano == ULTIMO_MES[0]].auxilio_moradia.sum(), 2)
    ok = oficial is not None and abs(nossa - oficial) < 1
    rel += ["## 4. Auxílio-moradia da Câmara no ano (todos os deputados)", "",
            f"- Nossa soma {ULTIMO_MES[0]}: R$ {nossa:,.2f}", f"- Página oficial: R$ {oficial:,.2f}" if oficial else "- Página oficial: não encontrado",
            f"- **{'OK' if ok else 'DIFERENTE'}**", ""]
    problemas += 0 if ok else 1

    # 5. Salários fora do padrão (para revisar à mão)
    sal = lanc[lanc.categoria == "salario"]
    fora = sal[(sal.valor.round(2) > max(SUBSIDIOS) + 0.01)]
    rel += ["## 5. Salários mensais acima do subsídio (revisar à mão)", "",
            f"Casos: {len(fora)}. Podem ser acertos de meses anteriores; confira na página oficial.", ""]
    nomes = {p["id"]: p["nome"] for p in politicos}
    for r in fora.sort_values("valor", ascending=False).head(15).itertuples():
        rel.append(f"- {nomes[r.id_politico]} — {r.mes:02.0f}/{r.ano}: R$ {r.valor:,.2f}")
    rel.append("")

    # 6. Assessores do Senado: pessoas na nossa conta × API
    pessoal = pd.read_csv(BRUTOS / "senado_pessoal.csv")
    gab = pd.read_csv(BRUTOS / "senado_assessores_gabinete.csv")
    ultimo = gab[(gab.ano * 100 + gab.mes) == (gab.ano * 100 + gab.mes).max()]
    api = pessoal[pessoal.ano == ULTIMO_MES[0]].groupby("id_senador").quantidade.sum()
    cmp = ultimo.set_index("id_senador").join(api.rename("api")).dropna()
    cmp["dif"] = cmp.pessoas - cmp.api
    rel += ["## 6. Senado: assessores encontrados na folha × quantidade informada pela API", "",
            f"- Senadores comparados: {len(cmp)}",
            f"- Diferença mediana: {cmp.dif.median():.0f} pessoa(s); casos com diferença > 5: {(cmp.dif.abs() > 5).sum()}",
            "- Lembrete: o custo dos assessores do Senado é uma ESTIMATIVA (ver metadados).", ""]

    # 7. Sanidade: se algo grande quebrou (uma fonte fora do ar, um site que mudou de layout),
    #    estes números despencam. Cada falha soma 10 alertas e trava a publicação automática.
    # Usa o mês retrasado: no começo do mês, a folha do mês anterior pode ainda não ter saído.
    k = ULTIMO_MES[0] * 12 + (ULTIMO_MES[1] - 1) - 2
    ano_f, mes_f = k // 12, k % 12 + 1
    lanc["casa"] = lanc.id_politico.str[:3]
    def quantos(casa, cat):
        f = lanc[(lanc.casa == casa) & (lanc.categoria == cat) & (lanc.ano == ano_f) & (lanc.mes == mes_f) & (lanc.valor > 0)]
        return f.id_politico.nunique()
    chave = lanc.ano * 12 + lanc.mes.fillna(0)
    janela = (chave > ano_f * 12 + mes_f - 12) & (chave <= ano_f * 12 + mes_f)
    def cota_12m(casa):
        return lanc[janela & (lanc.casa == casa) & (lanc.categoria == "cota_parlamentar")].valor.sum()
    eq = pd.read_csv(PROCESSADOS / "equipe.csv")
    n_equipe_dep = eq[(eq.id_politico.str.startswith("dep")) & (eq.ano == ano_f) & (eq.mes == mes_f) & (eq.pessoas > 0)].id_politico.nunique()
    with open(RAIZ / "site" / "dados" / "dados.json", encoding="utf-8") as f:
        n_site = len(json.load(f)["p"])
    # governo federal: último mês publicado pelo Portal da Transparência
    exe = [p for p in politicos if p["casa"] == "executivo"]
    ult_e = max((p.get("ultimo_mes_publicado") or 0) for p in exe) if exe else 0
    no_cargo_e = [p["id"] for p in exe if ult_e in p.get("meses_no_cargo", [])]
    com_salario_e = lanc[(lanc.casa == "exe") & (lanc.grupo == "ganha") & (lanc.ano * 100 + lanc.mes == ult_e)].id_politico.nunique()
    checagens = [
        (f"Governo federal: no cargo em {ult_e % 100:02d}/{ult_e // 100}", len(no_cargo_e), 30),
        ("Câmaras municipais com custo no arquivo do site", _cidades_com_custo(), 5000),
        ("Vereadores eleitos no arquivo do site", _vereadores_no_site(), 55000),
        (f"Governo federal: com salário em {ult_e % 100:02d}/{ult_e // 100}", com_salario_e, 25),
        (f"Deputados com salário em {mes_f:02d}/{ano_f}", quantos("dep", "salario"), 480),
        (f"Deputados com verba de gabinete em {mes_f:02d}/{ano_f}", quantos("dep", "assessores_gabinete"), 450),
        (f"Senadores com salário em {mes_f:02d}/{ano_f}", quantos("sen", "salario"), 75),
        (f"Senadores com assessores em {mes_f:02d}/{ano_f}", quantos("sen", "assessores_gabinete"), 60),
        ("Cota da Câmara nos últimos 12 meses (R$ milhões)", round(cota_12m("dep") / 1e6), 150),
        ("Cota do Senado nos últimos 12 meses (R$ milhões)", round(cota_12m("sen") / 1e6), 15),
        ("Parlamentares no arquivo do site", n_site, 700),
        (f"Deputados com a equipe contada em {mes_f:02d}/{ano_f}", n_equipe_dep, 450),
    ]
    rel += ["## 7. Sanidade (trava a publicação automática)", "", "| Checagem | Valor | Mínimo | |", "|---|---:|---:|---|"]
    for nome, valor, minimo in checagens:
        ok = valor >= minimo
        problemas += 0 if ok else 10
        rel.append(f"| {nome} | {valor} | {minimo} | {'OK' if ok else 'FALHOU'} |")
    rel.append("")

    rel += ["---", f"**Total de alertas: {problemas}**"]
    (PROCESSADOS / "conferencia.md").write_text("\n".join(rel), encoding="utf-8")
    log(f"Conferência pronta: dados/processados/conferencia.md — {problemas} alerta(s)")
    return problemas
