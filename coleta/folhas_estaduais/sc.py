"""Santa Catarina: Portal de Dados Abertos, "Remuneração dos servidores": um CSV por mês (~22 MB), com o nome, o
cargo, o órgão e o valor bruto (o CPF vem mascarado e não é guardado). Só o total do mês, sem as partes.
https://dados.sc.gov.br/dataset/remuneracaoservidores"""
import re

from ..util import recursos_ckan
from . import comum

UF = "SC"
FONTE = "https://dados.sc.gov.br/dataset/remuneracaoservidores"


def _arquivos():
    saida = {}
    for x in recursos_ckan(FONTE):
        m = re.match(r"Servidores-Ativos-(\d{4})-(\d{2})\.csv$", x.get("name") or "", re.I)
        if m:
            saida[int(m.group(1)) * 100 + int(m.group(2))] = x["url"]
    return saida


def coletar():
    arquivos = _arquivos()
    feitos, linhas = [], []
    for am in comum.a_fazer(UF, max(arquivos)):
        if am not in arquivos:
            continue
        cab, achadas = comum.linhas_csv(arquivos[am], ["GOVERNADOR"])
        col = {c.lower(): c for c in cab}
        for x in achadas:
            tp = comum.tp_do_cargo(x.get(col.get("cargo", "Cargo")))
            if tp:
                bruto = comum.num(x.get(col.get("valorbruto", "ValorBruto")))
                linhas.append(comum.linha(am, tp, x[col.get("nome", "Nome")], x[col.get("cargo", "Cargo")], bruto))
        feitos.append(am)
        comum.gravar(UF, linhas, feitos)
    return len(linhas)
