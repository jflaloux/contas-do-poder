"""Minas Gerais: Portal de Dados Abertos, "Remuneração dos servidores ativos": um CSV por mês (~130 MB, latin-1), com o
nome, o cargo em comissão e as partes da remuneração (a coluna de CPF vem vazia e não é lida). O leiaute mudou em
fevereiro de 2026; o robô lê os dois. A Secretaria de Planejamento publica com alguns meses de atraso.
https://dados.mg.gov.br/dataset/remuneracao-servidores-ativos"""
import re

from ..util import recursos_ckan
from . import comum

UF = "MG"
FONTE = "https://dados.mg.gov.br/dataset/remuneracao-servidores-ativos"
# nome no leiaute novo | no antigo
COL = {"cargo": ("cargo_comissao", "desccomi"), "salario": ("remuneracao", "remuner"), "teto": ("abate_teto", "teto"),
       "ferias": ("ferias",), "decimo": ("decimo_terceiro", "decter"),
       "outros": ("judic", "premio", "ferias_premio", "feriasprem", "jetons", "eventual")}
# jetons dos conselhos de empresas do Estado (cada coluna é uma empresa)
ESTATAIS = ("bdmg", "cemig", "codemig", "cohab", "copasa", "emater", "epamig", "funpemg", "gasmig", "mgi", "mgs", "prodemge",
            "prominas", "emip", "codemge", "emc")


def _arquivos():
    saida = {}
    for x in recursos_ckan(FONTE):
        u = x.get("url") or ""
        m = re.search(r"servidores-(\d{4})-(\d{2})\.csv$", u) or re.search(r"servidores_(\d{2})(\d{4})\.csv$", u)
        if m:
            a, mes = (m.group(1), m.group(2)) if len(m.group(1)) == 4 else (m.group(2), m.group(1))
            saida[int(a) * 100 + int(mes)] = u
    return saida


def coletar():
    arquivos = _arquivos()
    feitos, linhas = [], []
    for am in comum.a_fazer(UF, max(arquivos)):
        if am not in arquivos:
            continue
        cab, achadas = comum.linhas_csv(arquivos[am], ["GOVERNADOR"], encoding="latin-1")
        tem = set(cab)
        v = lambda x, nomes: sum(comum.num(x.get(n)) for n in nomes if n in tem)
        for x in achadas:
            cargo = next((x[c] for c in COL["cargo"] if c in tem), "")
            tp = comum.tp_do_cargo(cargo)
            if not tp:
                continue
            partes = {"salario": v(x, COL["salario"]), "decimo": v(x, COL["decimo"]), "ferias": v(x, COL["ferias"]), "beneficios": None,
                      "outros": v(x, COL["outros"]) + v(x, ESTATAIS)}
            redutor = abs(v(x, COL["teto"]))
            linhas.append(comum.linha(am, tp, x["nome"], cargo, sum(p for p in partes.values() if p), partes, redutor))
        feitos.append(am)
        comum.avisar(UF, f"{am % 100:02d}/{am // 100}: {len(achadas)} linhas com GOVERNADOR")
        comum.gravar(UF, linhas, feitos)
    return len(linhas)
