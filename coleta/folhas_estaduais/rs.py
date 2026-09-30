"""Rio Grande do Sul: Portal da Transparência, painel "Pessoal do Poder Executivo" (Power BI), com a chave anônima que a
própria página entrega a qualquer visitante (ver powerbi.py). Para cada mês, o valor bruto do vínculo e as rubricas
(subsídio, 1/3 de férias, 13º, vale-refeição); descontos pessoais e impostos não são lidos. O painel cobre os últimos
36 meses. Os arquivos mensais de dados abertos (arquivostransparencia.sefaz.rs.gov.br) não são usados: o robots.txt
daquele endereço proíbe acesso automático. https://www.transparencia.rs.gov.br/"""
import re

from ..util import _sessao
from . import comum, powerbi

UF = "RS"
FONTE = "https://www.transparencia.rs.gov.br/"
TOKEN = "https://www.transparencia.rs.gov.br/umbraco/Surface/PowerBI/Report"
PAINEL = {"workspaceId": "48138f86-653d-4a67-98d5-4cf00cdbcf4a", "reportId": "a6f4998b-b544-4b77-8f4d-4e95ec395dc9"}
CLUSTER = "https://wabi-brazil-south-redirect.analysis.windows.net"
CARGOS = ["Governador do Estado", "Vice-governador"]
# rubricas que são descontos (não entram no bruto): impostos, previdência, estorno de adiantamento do 13º, consignados...
DESCONTO = re.compile(r"IMPOSTO|INSS|PREVID|IPE|CONSIG|PENS[AO]|ESTORNO|DESCONTO|CONTRIB|EMPREST|SINDIC|PLANO|SEGURO|ASSOC|FALTA")


def coletar():
    meses = set(comum.a_fazer(UF, comum.ultimo_possivel()))
    if not meses:
        return 0
    r = _sessao().post(TOKEN, data=PAINEL, timeout=60)
    r.raise_for_status()
    d = r.json()
    token, rel = d["Token"], d.get("Id") or PAINEL["reportId"]
    mid = powerbi.modelo(CLUSTER, token, rel)
    filtro = [powerbi.em("d", "Cargo", CARGOS)]
    vinc = powerbi.consultar(CLUSTER, token, mid, [("d", "DimServidor"), ("f", "FatoVinculos")],
                             [("d", "Servidor", None), ("d", "Cargo", None), ("f", "Periodo", None), ("f", "VlrBruto", powerbi.SOMA)], filtro)
    rub = powerbi.consultar(CLUSTER, token, mid, [("d", "DimServidor"), ("f", "FatoVinculos"), ("r", "FatoRubricas")],
                            [("d", "Servidor", None), ("f", "Periodo", None), ("r", "TipoFolhaTratado", None), ("r", "Rubrica_Descr", None), ("r", "Valor", powerbi.SOMA)], filtro)
    partes, redutor = {}, {}
    for nome, am, folha, desc, valor in rub:
        am, valor, d_ = int(am), float(valor or 0), comum.normalizar_nome(desc)
        chave = (nome, am)
        if comum.eh_redutor(desc):
            redutor[chave] = redutor.get(chave, 0.0) + abs(valor)
            continue
        if DESCONTO.search(d_):
            continue
        p = partes.setdefault(chave, {k: 0.0 for k in comum.PARTES})
        tipo = "decimo" if "13" in comum.normalizar_nome(folha) else comum.classificar(desc)
        p[tipo] += valor
    linhas, feitos = [], set()
    for nome, cargo, am, bruto in vinc:
        am, bruto = int(am), float(bruto or 0)
        if am not in meses or not bruto:
            continue
        p = partes.get((nome, am))
        if p is not None and abs(sum(p.values()) - bruto) > 1:  # as rubricas não fecham com o bruto: fica só o total
            p = None
        linhas.append(comum.linha(am, comum.tp_do_cargo(cargo) or ("vice" if "VICE" in comum.normalizar_nome(cargo) else "gov"),
                                  nome, cargo, bruto, p, redutor.get((nome, am), 0.0)))
        feitos.add(am)
    comum.gravar(UF, linhas, sorted(feitos))
    return len(linhas)
