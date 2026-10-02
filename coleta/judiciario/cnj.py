"""CNJ: os conselheiros pagos pelo próprio CNJ, mês a mês, pela página oficial da folha (www.cnj.jus.br/remuneracao/).

A página monta a tabela por POST (rem.php, com mês de dois dígitos, ano e tipo 3 = Conselheiro) e traz os valores de
cada pessoa como argumentos de uma função (mostraCaixa). Conselheiros que vêm de um tribunal recebem o salário no órgão
de origem e, no CNJ, só a diferença de subsídio; os de fora (advogados e cidadãos indicados pela Câmara e pelo
Senado) recebem o subsídio no CNJ. O presidente (presidente do STF) e o corregedor nacional (ministro do STJ) são
pagos pelos seus tribunais e não aparecem nesta folha. A "remuneração bruta do órgão de origem" não é guardada.
O robots.txt do CNJ só proíbe /remuneracao/ para o Googlebot. Abre de fora do Brasil (conferido em 01/10/2026).
"""
import html
import re

from ..util import _sessao, dormir, log, verificar_prazo
from . import comum

ORGAO = "CNJ"
PAGINA = "https://www.cnj.jus.br/remuneracao/"
PAUSA = 3
# argumentos de mostraCaixa(), na ordem da página
ARGS = ["nome", "cargo", "RP", "VP", "FC", "AUX", "VE", "Grat", "bruto", "RTC", "ir", "PSS", "DescDiv", "descontos", "liquido",
        "origem", "diaria", "lotacao", "orgorigem", "obrigacao_patronal"]


def _post(arquivo, dados):
    verificar_prazo()
    r = _sessao().post(PAGINA + arquivo, data=dados, timeout=90)
    r.raise_for_status()
    dormir(PAUSA)
    return r.content.decode("utf-8", "replace")


def disponiveis():
    """Meses publicados, de INICIO ao mês atual (a lista de meses de cada ano vem de pegaMes.php)."""
    from ..config import HOJE
    saida = []
    for ano in range(comum.INICIO // 100, HOJE.year + 1):
        for m in re.findall(r'value="(\d\d)"', _post("pegaMes.php", {"anoRef": ano})):
            saida.append(ano * 100 + int(m))
    return saida


def _args(chamada):
    return [html.unescape(a) for a in re.findall(r"'((?:[^'\\]|\\.)*)'", chamada)]


def mes(am):
    texto = _post("rem.php", {"mesRef": f"{am % 100:02d}", "anoRef": am // 100, "nmServ": "", "tpServ": 3})
    linhas = []
    for chamada in re.findall(r"mostraCaixa\(([^)]*)\)", texto):
        a = _args(chamada)
        if len(a) < len(ARGS) or not a[0].strip():
            continue
        d = dict(zip(ARGS, a))
        if "CONSELHEIR" not in d["cargo"].upper():
            continue
        v = lambda k: comum.numero(d[k])
        partes = {"subsidio": round(v("RP") + v("FC"), 2), "vantagens_pessoais": v("VP"), "indenizacoes": v("AUX"),
                  "vantagens_eventuais": v("VE"), "outras": v("Grat")}
        origem = d["orgorigem"].strip()
        nota = "página oficial da folha do CNJ (conselheiros)" + (f"; órgão de origem: {origem} (o que ele paga fica de fora)" if origem else "")
        if re.fullmatch(r",\d+\.\d\d", d["FC"].strip()):
            # a página às vezes perde o primeiro algarismo do subsídio (",10.37" para 710,37): vale o total da própria página
            partes["subsidio"] = round(v("bruto") - sum(x for k, x in partes.items() if k != "subsidio"), 2)
            nota += f"; a página mostra o subsídio como \"{d['FC'].strip()}\": o valor aqui é o total da página menos as outras partes"
        comum.conferir_total(ORGAO, d["nome"], am, partes, v("bruto"))
        linhas.append(comum.linha(ORGAO, am, d["nome"], "Conselheiro do CNJ", d["lotacao"], partes, v("diaria"), None, PAGINA, nota))
    return linhas


def coletar():
    disp = disponiveis()
    fazer = comum.a_fazer(ORGAO, disp)
    linhas, lidos = [], []
    try:
        for am in fazer:
            ls = mes(am)
            linhas += ls
            lidos.append({"ano_mes": am, "pessoas": len(ls), "url": PAGINA})
    finally:
        n = comum.gravar(ORGAO, linhas, lidos)
        if lidos:
            log(f"  CNJ: {len(lidos)} meses lidos ({lidos[0]['ano_mes']} a {lidos[-1]['ano_mes']}), {n} linhas")
    return n
