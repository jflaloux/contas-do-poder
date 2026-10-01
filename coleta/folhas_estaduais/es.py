"""Espírito Santo: Portal de Dados Abertos, "Portal da Transparência - Pessoal": um CSV por mês (85-195 MB), uma linha
por rubrica de cada servidor (sem CPF). O robô lê o arquivo aos poucos e fica só com o governador e o vice.
https://dados.es.gov.br/dataset/portal-da-transparencia-pessoal"""
import re

from ..util import recursos_ckan
from . import comum

UF = "ES"
FONTE = "https://dados.es.gov.br/dataset/portal-da-transparencia-pessoal"


def _arquivos():
    """{AAAAMM: url} dos CSVs mensais."""
    saida = {}
    for x in recursos_ckan(FONTE):
        m = re.match(r"Remuneracoes-(\d{2})_(\d{4})\.csv", x.get("name") or "")
        if m:
            saida[int(m.group(2)) * 100 + int(m.group(1))] = x["url"]
    return saida


def _mes(am, url):
    _, achadas = comum.linhas_csv(url, ["GOVERNADOR DO ESTADO"])
    por = {}
    for x in achadas:
        cargo = x.get("Funcao") or x.get("Cargo")
        tp = comum.tp_do_cargo(x.get("Funcao")) or comum.tp_do_cargo(x.get("Cargo"))
        if not tp or (x.get("NomePensionista") or "").strip():
            continue
        credito = (x.get("VantagemDesconto") or "").strip().upper() == "V"
        por.setdefault((tp, x["Nome"].strip(), cargo.strip()), []).append((x.get("Rubrica"), comum.num(x.get("Valor")), credito))
    linhas = []
    for (tp, nome, cargo), rub in por.items():
        partes, redutor, bruto = comum.somar_rubricas(rub)
        linhas.append(comum.linha(am, tp, nome, cargo, bruto, partes, redutor))
    return linhas


def coletar():
    arquivos = _arquivos()
    feitos, linhas = [], []
    for am in comum.a_fazer(UF, max(arquivos), refazer=1):  # arquivos de até 200 MB: refaz só o último mês
        if am not in arquivos:
            continue
        linhas += _mes(am, arquivos[am])
        feitos.append(am)
        comum.avisar(UF, f"{am % 100:02d}/{am // 100}")
        comum.gravar(UF, linhas, feitos)  # grava a cada mês: o arquivo é grande e demorado
    return len(linhas)
