"""Distrito Federal: diárias do governador e da vice pela API do Portal da Transparência do DF (a mesma da folha do DF;
pede o cabeçalho x-client-id, que o site gera a cada visita: mandamos o fixo de folhas_estaduais/df.py).
https://www.transparencia.df.gov.br/#/despesas/diarias-passagens-locomocao
- /api/despesa/nota-empenho?anoNotaEmpenho=AAAA&nomeCredor=<nome>: os empenhos do ano em nome da pessoa (a busca é por
  parte do nome; o nome inteiro é conferido aqui); ficam os de diárias (elemento "DIÁRIAS - CIVIL");
- /api/despesa/descricao: a descrição do empenho, com destino e período da viagem ("com destino à cidade de São
  Paulo/SP, no período de 06/08/2025 a 10/08/2025"); só o destino e as datas são lidos, o resto do texto (motivo,
  matrícula) não é guardado;
- /api/despesa/nota-empenho/ordem-bancaria: as ordens bancárias do empenho; o valor é a soma do que foi pago.
Uma viagem por empenho. As respostas trazem o CPF (codigoCredor) e o CPF mascarado: nenhum dos dois é lido.
O painel "Detalhamento de Diárias" (Power BI publicado na web, com link no portal) responde 403 a robôs; não é usado.
As passagens são empenhadas à agência de viagens, sem o nome do passageiro: ficam de fora."""
import re
import unicodedata
from urllib.parse import urlencode

from ..folhas_estaduais.df import CAB
from ..util import normalizar_nome
from . import comum
from .es import _ATE, _D, DIAS, PERIODO

PERIODO, DIAS = re.compile(PERIODO.pattern, re.I), re.compile(DIAS.pattern, re.I)  # a descrição vem em maiúsculas

UF = "DF"
FONTE = "https://www.transparencia.df.gov.br/#/despesas/diarias-passagens-locomocao"
API = "https://www.transparencia.df.gov.br/api/despesa"
NOTA = ("Diárias do governador e da vice, viagem por viagem (um empenho por viagem), pelo Portal da Transparência do "
        "Distrito Federal: valor pago; o destino e as datas saem da descrição do empenho (sem data na descrição, vale a do "
        "empenho). As passagens são empenhadas a agências de viagem, sem o nome do passageiro, e não entram.")
MESES = {"JANEIRO": 1, "FEVEREIRO": 2, "MARCO": 3, "ABRIL": 4, "MAIO": 5, "JUNHO": 6, "JULHO": 7, "AGOSTO": 8,
         "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12}
_MES = "(" + "|".join(MESES) + ")"
DIA = re.compile(r"\bDIAS?\s+" + _D + r"(?!\d)")  # "no dia 31/07/2026" (não "publicado em", que é a data do DODF)
# "com destino à cidade de São Paulo/SP", "viagem à cidade de São Paulo/SP", "viagem a São Paulo (SP)"
_LUGAR = r"([A-Z][A-Z' ]*?[A-Z])\s*(?:/\s*|\(\s*)([A-Z]{2})\b\)?"
DESTINO = re.compile(r"\b(?:DESTINO|VIAGEM|DESLOCAMENTO)\s+(?:A|AO|AS|PARA)\s+(?:(?:A\s+)?CIDADE\s+D[EOA]S?\s+|MUNICIPIO\s+D[EOA]\s+)?"
                     + _LUGAR)
MAIS = re.compile(r"\s*(?:,|E)\s+(?:(?:A\s+)?CIDADE\s+D[EOA]S?\s+)?" + _LUGAR)


def _texto(t):
    """Maiúsculas, sem acentos e com as datas por extenso no formato dd/mm/aaaa ("18 de agosto de 2026" -> 18/08/2026;
    "30 de julho a 2 de agosto de 2026" -> 30/07/2026 a 2/08/2026)."""
    t = normalizar_nome(t)
    t = re.sub(r"\b(\d{1,2})(?:º|O)?\s+DE\s+" + _MES + r"\s+DE\s+(\d{4})\b", lambda m: f"{m[1]}/{MESES[m[2]]:02d}/{m[3]}", t)
    # dia e mês sem o ano, seguidos de outra data com o ano: o ano é o da segunda
    return re.sub(r"\b(\d{1,2})(?:º|O)?\s+DE\s+" + _MES + r"(" + _ATE + r"\d{1,2}/\d{2}/(\d{4}))",
                  lambda m: f"{m[1]}/{MESES[m[2]]:02d}/{m[4]}{m[3]}", t, flags=re.I)


def periodo(descricao, ano):
    """(início, fim) da viagem (AAAA-MM-DD) pela descrição do empenho, ou None. Só as formas de período ("de X a Y",
    "nos dias X e Y", "no dia X"), para não tomar por data da viagem a da publicação no DODF; datas fora de ano-1 a ano+1
    (o exercício do empenho) não valem."""
    def dia(d, m, a):
        d, m, a = int(d), int(m), int(a)
        return f"{a}-{m:02d}-{d:02d}" if ano - 1 <= a <= ano + 1 and 1 <= m <= 12 and 1 <= d <= 31 else None
    t = _texto(descricao)
    for d1, m1, a1, d2, m2, a2 in PERIODO.findall(t):
        i, f = dia(d1, m1, a1), dia(d2, m2, a2)
        if i and f and i <= f:
            return i, f
    for d1, d2, m, a in DIAS.findall(t):
        i, f = dia(d1, m, a), dia(d2, m, a)
        if i and f and i <= f:
            return i, f
    for d, m, a in DIA.findall(t):
        if dia(d, m, a):
            return dia(d, m, a), dia(d, m, a)
    return None


def _cidade(nome):
    return " ".join(w.lower() if w in ("DE", "DO", "DA", "DOS", "DAS", "E") else "-".join(p.capitalize() for p in w.split("-")) for w in nome.split())


def _sem_acento(t):
    """Maiúsculas sem acento, com o mesmo comprimento do texto (para recortar o nome com acento do texto original)."""
    def base(c):
        b = "".join(x for x in unicodedata.normalize("NFKD", c) if not unicodedata.combining(x))
        return b if len(b) == 1 else c
    return "".join(base(c) for c in t)


def destino(descricao):
    """"São Paulo/SP" (ou "Belo Horizonte/MG; Salvador/BA") pela descrição; "" se não achar (cidade sem UF, exterior)."""
    original = re.sub(r"\s+", " ", (descricao or "").upper())
    t = _sem_acento(original)
    m = DESTINO.search(t)
    if not m:
        return ""
    lugares, pos = [f"{_cidade(original[m.start(1):m.end(1)])}/{m[2]}"], m.end()
    while (n := MAIS.match(t, pos)):
        lugares.append(f"{_cidade(original[n.start(1):n.end(1)])}/{n[2]}")
        pos = n.end()
    return "; ".join(lugares)


def montar_viagens(empenhos):
    """Empenhos [{"ne": linha da lista de empenhos, "descricao": [itens], "obs": [ordens bancárias]}] -> viagens."""
    saida = []
    for e in empenhos:
        ne, desc = e["ne"], " ".join(i.get("descricao") or "" for i in e["descricao"])
        pago = round(sum(comum.num(o.get("valorFinal")) for o in e["obs"]), 2)
        if not pago:
            continue  # empenho sem pagamento (ainda não pago ou anulado)
        if pago > comum.num(ne.get("valorNeFinal")) + 0.01:
            # a ordem bancária pagou mais do que o empenho: pagaria também outro empenho (de outra pessoa?); a coleta
            # falha (fica o que estava) em vez de publicar um valor que pode não ser só do governador ou da vice
            raise RuntimeError(f"{ne['numeroNotaEmpenho']}: pago R$ {pago} maior que o empenho (R$ {ne.get('valorNeFinal')})")
        data_ne = (ne.get("dataEmissao") or "")[:10]
        if "/" in data_ne:
            data_ne = f"{data_ne[6:10]}-{data_ne[3:5]}-{data_ne[0:2]}"
        p = periodo(desc, int(ne["anoNotaEmpenho"]))
        inicio, fim = p or (data_ne, data_ne)
        if not inicio:
            continue
        saida.append({"id": f"df-{ne['codigoUnidadeGestora']}-{ne['numeroNotaEmpenho']}", "inicio": inicio, "fim": fim,
                      "nome": " ".join(ne["nomeCredor"].split()), "cargo": "", "destino": destino(desc), "diarias": pago,
                      "obs": f"empenho {ne['numeroNotaEmpenho']}, {_cidade(ne.get('nomeUnidadeGestora') or '')}"
                             + ("" if p else "; sem o período na descrição: data do empenho"),
                      "fonte": FONTE})
    return saida


def _chave(ne):
    return {"numeroNotaEmpenho": ne["numeroNotaEmpenho"], "codigoUnidadeGestora": ne["codigoUnidadeGestora"],
            "anoNotaEmpenho": ne["anoNotaEmpenho"], "codigoGestao": ne["codigoGestao"]}


def coletar(nomes):
    """`nomes`: os nomes normalizados (folha_nome e civil do arquivo curado)."""
    anos = sorted({am // 100 for am in comum.meses()} | {comum.INICIO // 100 - 1})  # empenho de dez/2024 para jan/2025
    atual = anos[-1]
    empenhos = []
    for ano in anos:
        dias = 3 if ano >= atual - 1 else 30
        for nome in sorted(nomes):
            for pagina in range(20):  # limite fixo; cada pessoa tem poucos empenhos por ano
                q = {"anoNotaEmpenho": ano, "nomeCredor": nome, "page": pagina, "size": 50}
                d = comum.obter(f"{API}/nota-empenho?{urlencode(q)}",
                                comum.C / "df" / f"ne_{ano}_{nome.replace(' ', '_')}_{pagina}.json", dias, headers=CAB)
                for ne in d.get("content") or []:
                    if normalizar_nome(ne.get("nomeCredor")) in nomes and "DIARIA" in normalizar_nome(ne.get("nomeElementoDespesa")):
                        empenhos.append({k: ne.get(k) for k in ("numeroNotaEmpenho", "codigoUnidadeGestora", "anoNotaEmpenho",
                                                                "codigoGestao", "nomeCredor", "nomeUnidadeGestora",
                                                                "dataEmissao", "valorNeFinal")})
                if d.get("last", True) or not d.get("content"):
                    break
    vistos, lidos = set(), []
    for ne in empenhos:
        k = tuple(_chave(ne).values())
        if k in vistos:
            continue
        vistos.add(k)
        arq = f"{ne['anoNotaEmpenho']}_{ne['codigoUnidadeGestora']}_{ne['numeroNotaEmpenho']}"
        recente = ne["anoNotaEmpenho"] >= atual - 1
        desc = comum.obter(f"{API}/descricao?{urlencode(_chave(ne))}", comum.C / "df" / f"desc_{arq}.json", 30, headers=CAB)
        obs = comum.obter(f"{API}/nota-empenho/ordem-bancaria?{urlencode(_chave(ne))}", comum.C / "df" / f"ob_{arq}.json",
                          3 if recente else 30, headers=CAB)
        lidos.append({"ne": ne, "descricao": desc or [], "obs": obs or []})
    inicio = f"{comum.INICIO // 100}-{comum.INICIO % 100:02d}-01"
    return comum.gravar(UF, [v for v in montar_viagens(lidos) if v["inicio"] >= inicio])
