"""Maranhão: Portal da Transparência, "Remuneração" (pessoal): busca pelo nome no mês e, para cada matrícula da pessoa,
o histórico do ano (uma coluna por mês), com cada provento (subsídio, férias, adiantamento do 13º, outros proventos).
O governador e o vice têm uma segunda matrícula, de conselheiro (Casa Civil), com R$ 8.850 por mês: entra em
"outros". Os descontos pessoais não são lidos. Atenção: a busca de nomes do portal (autocompletar) mostra CPFs sem
máscara e não é usada. Só abre de dentro do Brasil. https://www.transparencia.ma.gov.br/app/v2/pessoal/remuneracao"""
import re
from html import unescape

from . import _http, comum

UF = "MA"
FONTE = "https://www.transparencia.ma.gov.br/app/v2/pessoal/remuneracao"
BASE = "https://www.transparencia.ma.gov.br"


def _celulas(tr):
    return [re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", c))).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]


def _matriculas(nome, am):
    """[(cargo, link do histórico)] das matrículas com esse nome exato no mês."""
    busca = comum.normalizar_nome(nome)
    html = _http.get(FONTE, params={"ano": am // 100, "mes": am % 100, "tipo_busca": "nome", "nome": busca}, json=False, pausa=1).text
    saida = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        c, link = _celulas(tr), re.findall(r'href="([^"]*remuneracao/detalhe[^"]*)"', tr)
        if len(c) >= 6 and link and comum.normalizar_nome(c[1]) == busca:
            u = unescape(link[0])
            saida.append((c[4], u if u.startswith("http") else BASE + u))
    return saida


def _historico(link):
    """{mês (1-12): {"partes": {...}, "redutor": x}} pelas linhas de proventos ("P") e do teto."""
    html = _http.get(link, json=False, pausa=1).text
    meses = {}
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        c = _celulas(tr)
        if len(c) >= 14 and c[0] in ("P", "D", "B"):
            marca, nome, vals = c[0], c[1], c[2:14]
        elif len(c) >= 13:
            marca, nome, vals = "", c[0], c[1:13]
        else:
            continue
        provento = marca == "P"
        teto = not provento and comum.eh_redutor(nome)
        if not (provento or teto):
            continue
        for i, v in enumerate(vals, start=1):
            valor = comum.num(v) if v not in ("", "-") else 0.0
            if not valor:
                continue
            m = meses.setdefault(i, {"partes": {k: 0.0 for k in comum.PARTES}, "redutor": 0.0})
            if provento:
                m["partes"][comum.classificar(nome)] += valor
            else:
                m["redutor"] += abs(valor)
    return meses


def coletar():
    meses = comum.a_fazer(UF, comum.ultimo_possivel())
    linhas, feitos = [], set()
    for o in comum.ocupantes(UF):
        nome, meus = o.get("folha_nome"), [am for am in meses if comum.no_cargo(o, am)]
        if not nome or not meus:
            continue
        papel = "vice" if o["cargo"] == "vice" else "gov"
        for ano in sorted({am // 100 for am in meus}):
            do_ano = [am for am in meus if am // 100 == ano]
            total, cargos = {}, []
            for cargo, link in _matriculas(nome, do_ano[-1]) or _matriculas(nome, do_ano[0]):
                cargos.append(cargo)
                for mes, m in _historico(link).items():
                    t = total.setdefault(ano * 100 + mes, {"partes": {k: 0.0 for k in comum.PARTES}, "redutor": 0.0})
                    for k, v in m["partes"].items():
                        t["partes"][k] += v
                    t["redutor"] += m["redutor"]
            for am in do_ano:
                t = total.get(am)
                if t and sum(t["partes"].values()):
                    linhas.append(comum.linha(am, papel, nome, "; ".join(dict.fromkeys(cargos)), sum(t["partes"].values()), t["partes"], t["redutor"]))
                    feitos.add(am)
    comum.gravar(UF, linhas, sorted(feitos))
    return len(linhas)
