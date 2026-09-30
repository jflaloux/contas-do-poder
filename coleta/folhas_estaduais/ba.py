"""Bahia: Portal da Transparência, painel "Dados dos Servidores" (Power BI), com a chave anônima que a própria página
entrega a qualquer visitante (ver powerbi.py). O painel mostra o nome mascarado ("JERONIMO R*** S***"); a coluna com o
nome completo existe no modelo, mas o portal não a mostra, e não a pedimos. Governador e vice são achados pelo cargo em
comissão ("Governador", "Vice Governador"). Para cada mês: valor bruto, 13º, férias, outras verbas temporárias e o
estorno do teto; descontos não são lidos. https://www.transparencia.ba.gov.br/ServidorPessoal/PainelDadosServidores"""
import base64
import json
import re

from ..util import _sessao
from . import comum, powerbi

UF = "BA"
FONTE = "https://www.transparencia.ba.gov.br/ServidorPessoal/PainelDadosServidores?Aba=Remuneracao"
CARGOS = ["Governador", "Vice Governador"]
PARTE = {"Valor Bruto": "salario", "13º Salário": "decimo", "Férias": "ferias", "Outras": "outros"}


def coletar():
    meses = set(comum.a_fazer(UF, comum.ultimo_possivel()))
    if not meses:
        return 0
    html = _sessao().get(FONTE, timeout=60).text
    token = re.search(r'const accessToken = "([^"]+)"', html).group(1)
    rel = re.search(r'const embedReportId = "([^"]+)"', html).group(1)
    cluster = json.loads(base64.b64decode(token.split(".")[1] + "==")).get("clusterUrl", "").lower()
    mid = powerbi.modelo(cluster, token, rel)
    dados = powerbi.consultar(cluster, token, mid, [("r", "Remuneracao"), ("v", "Remuneracao_Valores")],
                              [("r", "ano_referencia", None), ("r", "mes_referencia", None), ("r", "nom_servidor_mascarado", None),
                               ("r", "nom_cargo_em_comissao", None), ("v", "Grupo", None), ("v", "Subgrupo", None), ("v", "Valor", powerbi.SOMA)],
                              [powerbi.em("r", "nom_cargo_em_comissao", CARGOS)])
    por = {}
    for ano, mes, nome, cargo, grupo, sub, valor in dados:
        am = int(ano) * 100 + int(mes)
        if am not in meses or grupo in ("Descontos Legais", "Demais Descontos", "Valor Líquido", "Remuneração Líquida"):
            continue
        t = por.setdefault((am, nome, cargo), {"partes": {k: 0.0 for k in comum.PARTES}, "redutor": 0.0})
        if sub == "Estorno Teto":
            t["redutor"] += abs(float(valor or 0))
        elif grupo == "Valores Indenizatórios":
            t["partes"]["beneficios"] += float(valor or 0)
        else:
            t["partes"][PARTE.get(sub, "outros")] += float(valor or 0)
    linhas = [comum.linha(am, "vice" if cargo.startswith("Vice") else "gov", nome, cargo, sum(t["partes"].values()), t["partes"], t["redutor"])
              for (am, nome, cargo), t in sorted(por.items())]
    comum.gravar(UF, linhas, sorted({l["aaaamm"] for l in linhas}))
    return len(linhas)
