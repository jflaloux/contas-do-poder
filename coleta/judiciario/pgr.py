"""Procurador-Geral da República: o pagamento mês a mês, pelas planilhas oficiais do MPF (transparencia.mpf.mp.br).

Duas planilhas ODS por mês, com endereço previsível: a remuneração dos membros ativos (uma linha por membro, no modelo
do CNMP) e as verbas indenizatórias e outras remunerações temporárias (uma linha por item, com o nome). Entra a linha
de lotação PGR com o nome de quem é PGR no mês (dados/judiciario/composicao.json). No arquivo, o "total de
rendimentos brutos" não inclui as outras remunerações temporárias nem as verbas indenizatórias; aqui o total soma
tudo. O endereço com www tem
certificado de outro nome: usamos o sem www. Abre de fora do Brasil (conferido em 01/10/2026). As planilhas são lidas
sem biblioteca extra (o ODS é um zip com um XML).
"""
import io
import re
import zipfile
import xml.etree.ElementTree as ET



from ..config import HOJE
from ..util import _sessao, dormir, log, normalizar_nome, verificar_prazo
from . import comum

ORGAO = "PGR"
BASE = "https://transparencia.mpf.mp.br/conteudo/contracheque"
MESES = ["Janeiro", "Fevereiro", "Marco", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
PAUSA = 2
_T = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
_O = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"


def url_remuneracao(am):
    a, m = divmod(am, 100)
    return f"{BASE}/remuneracao-membros-ativos/{a}/remuneracao-membros-ativos_{a}_{MESES[m - 1]}.ods"


def url_indenizacoes(am):
    a, m = divmod(am, 100)
    return (f"{BASE}/verbas-indenizatorias-e-outras-remuneracoes-temporarias/membros-ativos/{a}/"
            f"verbas-indenizatorias-e-outras-remuneracoes-temporarias_{a}_{MESES[m - 1]}.ods")


def ler_ods(conteudo):
    """Linhas (listas de textos) da primeira tabela de um arquivo ODS."""
    with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
        xml = z.read("content.xml")
    linhas = []
    for _, el in ET.iterparse(io.BytesIO(xml), events=("end",)):
        if el.tag == f"{_T}table-row":
            row = []
            for cel in el:
                if cel.tag not in (f"{_T}table-cell", f"{_T}covered-table-cell"):
                    continue
                n = min(int(cel.get(f"{_T}number-columns-repeated", "1")), 200)
                valor = cel.get(f"{_O}value")
                texto = valor if valor is not None else " ".join("".join(p.itertext()) for p in cel)
                row += [texto.strip()] * n
            while row and not row[-1]:
                row.pop()
            reps = min(int(el.get(f"{_T}number-rows-repeated", "1")), 5)
            linhas += [row] * (reps if row else 1)
            el.clear()
        elif el.tag == f"{_T}table":
            break  # só a primeira tabela
    return linhas


def _baixar(url):
    verificar_prazo()
    r = _sessao().get(url, timeout=120)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    dormir(PAUSA)
    return r.content


def pgr_no_mes(am):
    """Nomes (normalizados) de quem é PGR no mês, pela composição."""
    nomes = set()
    for p in comum.composicao().get("membros", []):
        if p.get("orgao") != ORGAO:
            continue
        de, ate = int(str(p.get("inicio") or "190001").replace("-", "")[:6]), int(str(p.get("fim") or "299912").replace("-", "")[:6])
        if de <= am <= ate:
            nomes |= {normalizar_nome(n) for n in [p["nome_civil"], *p.get("folha", [])]}
    return nomes


def mes(am):
    rem = _baixar(url_remuneracao(am))
    if rem is None:
        return None
    nomes = pgr_no_mes(am)
    linhas_rem = ler_ods(rem)
    cab = next(i for i, r in enumerate(linhas_rem) if r and r[0] == "Lotação")
    # colunas pelo rótulo da linha de títulos (a planilha tem células mescladas)
    rot = [(j, t) for r in linhas_rem[cab:cab + 3] for j, t in enumerate(r) if t]
    col = lambda comeco: next(j for j, t in rot if t.startswith(comeco))
    c = {"cargo_ef": col("Remuneração do Cargo Efetivo"), "outras_v": col("Outras Verbas Remuneratórias"), "funcao": col("Função de Confiança"),
         "natal": col("Gratificação Natalina"), "ferias": col("Férias"), "abono": col("Abono de Permanência"), "temp": col("Outras Remunerações Temporárias"),
         "ind": col("Verbas Indenizatórias"), "bruto": col("Total de Rendimentos Brutos")}
    alvo = [r for r in linhas_rem[cab + 3:] if len(r) > 6 and r[0].strip().upper() == "PGR" and normalizar_nome(r[4]) in nomes]
    if not alvo:
        log(f"  PGR {am}: o PGR do mês não está na planilha (ver dados/judiciario/composicao.json)")
        return []
    r = alvo[0]
    v = lambda k: comum.numero(r[c[k]]) if c[k] < len(r) else 0.0
    itens = []
    ind = _baixar(url_indenizacoes(am))
    if ind:
        for li in ler_ods(ind):
            if len(li) > 16 and normalizar_nome(li[4]) == normalizar_nome(r[4]) and li[0].strip().upper() == "PGR" and li[12]:
                itens.append(("Verbas indenizatórias", re.sub(r"\s+", " ", li[12]).strip(), comum.numero(li[16])))
            if len(li) > 18 and normalizar_nome(li[4]) == normalizar_nome(r[4]) and li[17] and li[17].upper() not in ("N/C", "NC"):
                itens.append(("Outras remunerações temporárias", re.sub(r"\s+", " ", li[17]).strip(), comum.numero(li[18])))
    partes = {"subsidio": v("cargo_ef"), "vantagens_pessoais": v("outras_v"), "outras": v("funcao"), "decimo_terceiro": v("natal"),
              "ferias": v("ferias"), "abono_permanencia": v("abono"), "vantagens_eventuais": v("temp"), "indenizacoes": v("ind")}
    comum.conferir_total(ORGAO, r[4], am, {k: x for k, x in partes.items() if k not in ("indenizacoes", "vantagens_eventuais")}, v("bruto"))
    soma_itens = round(sum(x for g, _, x in itens if g == "Verbas indenizatórias"), 2)
    if itens and abs(soma_itens - partes["indenizacoes"]) > 0.05:
        log(f"  PGR {am}: itens das verbas indenizatórias ({soma_itens:.2f}) ≠ coluna da planilha ({partes['indenizacoes']:.2f})")
    return [comum.linha(ORGAO, am, r[4], "Procurador-Geral da República", r[0], partes, None, itens, url_remuneracao(am),
                        "planilhas oficiais do MPF (remuneração e verbas indenizatórias: " + url_indenizacoes(am) + ")")]


def coletar():
    ultimo = HOJE.year * 100 + HOJE.month
    fazer = comum.a_fazer(ORGAO, comum.meses(comum.INICIO, ultimo))
    linhas, lidos = [], []
    try:
        for am in fazer:
            ls = mes(am)
            if ls is None:  # ainda não publicado
                continue
            linhas += ls
            lidos.append({"ano_mes": am, "pessoas": len(ls), "url": url_remuneracao(am)})
    finally:
        n = comum.gravar(ORGAO, linhas, lidos)
        if lidos:
            log(f"  PGR: {len(lidos)} meses lidos ({lidos[0]['ano_mes']} a {lidos[-1]['ano_mes']}), {n} linhas")
    return n
