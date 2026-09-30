"""Pernambuco: Portal de Dados Abertos, "Remuneração de servidores": um CSV por mês (~34 MB), com o nome, o cargo, a
função e as partes da remuneração (o CPF vem mascarado e não é guardado).
https://dados.pe.gov.br/dataset/remuneracao-de-servidores
A governadora Raquel Lyra não recebe como governadora: aparece como procuradora do Estado (o cargo de carreira dela),
e é achada pelo nome (folha_nome em dados/governadores/governadores.json)."""
import re

from ..util import _sessao
from . import comum

UF = "PE"
PACOTE = "https://dados.pe.gov.br/api/3/action/package_show?id=remuneracao-de-servidores"
FONTE = "https://dados.pe.gov.br/dataset/remuneracao-de-servidores"


def _arquivos():
    saida = {}
    for x in _sessao().get(PACOTE, timeout=120).json()["result"]["resources"]:
        m = re.search(r"/(\d{4})_(\d{1,2})_remuneracao_ativos\.csv$", x.get("url") or "")
        if m:
            saida[int(m.group(1)) * 100 + int(m.group(2))] = x["url"]
    return saida


def coletar():
    arquivos = _arquivos()
    feitos, linhas = [], []
    for am in comum.a_fazer(UF, max(arquivos)):
        if am not in arquivos:
            continue
        nomes = comum.nomes_folha(UF, am)
        _, achadas = comum.linhas_csv(arquivos[am], ["GOVERNADOR", *nomes])
        por = {}
        for x in achadas:
            nome = (x.get("r_nome") or "").strip()
            tp = comum.tp_do_cargo(x.get("r_funcao")) or comum.tp_do_cargo(x.get("r_cargo")) or nomes.get(comum.normalizar_nome(nome))
            if not tp:
                continue
            cargo = " / ".join(c for c in (x.get("r_cargo", "").strip(), x.get("r_funcao", "").strip()) if c)
            p = por.setdefault((tp, nome), {"cargo": cargo, "salario": 0.0, "decimo": 0.0, "ferias": 0.0, "beneficios": None, "outros": 0.0, "redutor": 0.0})
            g = lambda k: comum.num(x.get(k))
            p["salario"] += g("r_remuneracao")
            p["ferias"] += g("r_ferias")
            p["decimo"] += g("r_natalina")
            # "outras vantagens" e o que o total tem a mais que as partes (há linhas só com o total, sem descrição e
            # sem imposto descontado, como o segundo pagamento que a governadora recebe como procuradora)
            p["outros"] += g("r_outras_vantagens") + max(0.0, g("r_total_vantagens") - g("r_remuneracao") - g("r_ferias") - g("r_natalina")
                                                           - g("r_outras_vantagens"))
            p["bruto"] = p.get("bruto", 0.0) + g("r_total_vantagens")
            p["redutor"] += g("r_desconto_excedente")
        for (tp, nome), p in por.items():
            partes = {k: p[k] for k in comum.PARTES}
            bruto = p["bruto"]
            linhas.append(comum.linha(am, tp, nome, p["cargo"], bruto, partes, p["redutor"]))
        feitos.append(am)
        comum.gravar(UF, linhas, feitos)
    return len(linhas)
