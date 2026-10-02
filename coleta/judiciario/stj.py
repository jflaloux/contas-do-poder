"""STJ: os ministros, mês a mês, pela API da página oficial de transparência (transparencia.web.stj.jus.br).

- GET /consultarmesreferencia/: as folhas publicadas (desde jun/2012), cada uma com um idExtracao;
- POST /consultarpaginado/ com o filtro 0 ("Ministros"): os totais de cada grupo (Anexo VIII da Resolução CNJ
  102/2009), para conferir;
- POST /gerarcsvdetalhado/ com o mesmo filtro: cada rubrica de cada ministro (um pedido por mês). Dela saem o nome de
  cada item (PVTAC, GECJAO, abono de permanência, 1/3 de férias...). Os grupos de desconto (imposto, previdência,
  descontos diversos, retenção pelo teto) não são lidos.
Abre de fora do Brasil (conferido em 01/10/2026). O endereço não tem robots.txt (devolve a própria página).
"""
import csv
import io
import json

from ..util import _sessao, dormir, log, verificar_prazo
from . import comum

ORGAO = "STJ"
PAGINA = "https://transparencia.web.stj.jus.br/"
API = "https://transparencia.web.stj.jus.br/api/transparencia"
PAUSA = 2
DESCONTOS = {"imposto de renda", "previdência pública", "descontos diversos", "retenção por teto constitucional"}


def _post(caminho, corpo, params=None):
    verificar_prazo()
    r = _sessao().post(f"{API}/{caminho}/", data=json.dumps(corpo), params=params, timeout=90,
                       headers={"Content-Type": "application/json"})
    r.raise_for_status()
    dormir(PAUSA)
    return r


def folhas():
    """{AAAAMM: idExtracao}."""
    verificar_prazo()
    r = _sessao().get(f"{API}/consultarmesreferencia/", timeout=60)
    r.raise_for_status()
    return {int(x["anoFolhaPagamento"]) * 100 + int(x["mesFolhaPagamento"]): int(x["idExtracao"]) for x in r.json()}


def _parte(grupo, rubrica):
    g, r = grupo.lower(), rubrica.lower()
    if "abono de perman" in r:
        return "abono_permanencia"
    if "subsídio" in g or "paradigma" in g:
        return "subsidio"
    if g.startswith("vantagens pessoais"):
        return "vantagens_pessoais"
    if g.startswith("indeniza"):
        return "indenizacoes"
    if g.startswith("vantagens eventuais"):
        if "férias" in r or "ferias" in r:
            return "ferias"
        if "natalina" in r or "13" in r:
            return "decimo_terceiro"
        return "vantagens_eventuais"
    if g.startswith("diárias"):
        return "diarias"
    if "origem" in g:
        return None  # pago por outro órgão: fica de fora
    return "outras"  # gratificações e o que mais vier


def mes(am, id_extracao):
    """Os totais de cada grupo vêm de consultarpaginado; o detalhe por rubrica (gerarcsvdetalhado) separa o abono de
    permanência das vantagens pessoais e as férias e o 13º das vantagens eventuais, e dá o nome de cada indenização,
    quando a soma do detalhe bate com os totais (nos meses mais antigos o detalhe vem vazio)."""
    corpo = {"idExtracao": id_extracao, "matricula": None, "nomeServidor": "", "listaCodigoSituacaoFiltro": [0]}
    totais = _post("consultarpaginado", corpo, {"page": 0, "size": 100}).json()["content"]
    texto = _post("gerarcsvdetalhado", corpo).content.decode("utf-8").lstrip("\ufeff")  # vem com o BOM duas vezes
    det = {}
    for r in csv.DictReader(io.StringIO(texto), delimiter=";"):
        if (r.get("Tipo") or "").lower() == "descontos" or (r.get("Grupo") or "").lower() in DESCONTOS or not r.get("Rubrica"):
            continue
        parte = _parte(r["Grupo"], r["Rubrica"])
        if parte is not None:
            det.setdefault(r["Nome"], []).append((r["Grupo"], r["Rubrica"], parte, comum.numero(r["Valor"])))
    linhas = []
    for t in totais:
        nome = t["nomeServidor"]
        v = lambda i: round(float(t[f"valorFinanceiroColuna{i}"] or 0), 2)
        grupos = {"subsidio": round(v(1) + v(3), 2), "vantagens_pessoais": v(2), "indenizacoes": v(4), "vantagens_eventuais": v(5), "outras": v(15)}
        itens_d = det.get(nome, [])
        soma = lambda partes: round(sum(x for _, _, pt, x in itens_d if pt in partes), 2)
        bate = itens_d and all(abs(soma(ps) - grupos[g]) <= 0.05 for g, ps in (
            ("subsidio", ("subsidio",)), ("vantagens_pessoais", ("vantagens_pessoais", "abono_permanencia")), ("indenizacoes", ("indenizacoes",)),
            ("vantagens_eventuais", ("vantagens_eventuais", "ferias", "decimo_terceiro")), ("outras", ("outras",))))
        nota = f"API oficial do STJ (idExtracao {id_extracao}, filtro Ministros)"
        if bate:
            partes = {k: soma((k,)) for k in comum.PARTES}
            itens = [(g, n, x) for g, n, pt, x in itens_d if pt in ("indenizacoes", "vantagens_eventuais", "vantagens_pessoais", "ferias", "outras")]
        else:
            partes, itens = grupos, None
            nota += "; sem o detalhe por rubrica neste mês: o abono de permanência fica nas vantagens pessoais e as férias e o 13º, nas eventuais"
        comum.conferir_total(ORGAO, nome, am, partes, v(11))
        linhas.append(comum.linha(ORGAO, am, nome, t["descCargo"], t["descricaoGrupo"], partes, v(10), itens, PAGINA, nota))
    return linhas


def coletar():
    disp = folhas()
    fazer = comum.a_fazer(ORGAO, disp)
    linhas, lidos = [], []
    try:
        for am in fazer:
            ls = mes(am, disp[am])
            linhas += ls
            lidos.append({"ano_mes": am, "pessoas": len(ls), "url": PAGINA})
    finally:
        n = comum.gravar(ORGAO, linhas, lidos)
        if lidos:
            log(f"  STJ: {len(lidos)} meses lidos ({lidos[0]['ano_mes']} a {lidos[-1]['ano_mes']}), {n} linhas")
    return n
