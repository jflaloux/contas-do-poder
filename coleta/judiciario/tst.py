"""TST: os ministros, mês a mês, pelo arquivo oficial de remuneração (transparencia-remuneracao.tst.jus.br).

Um CSV por mês (ISO-8859-1, separador ";", valores no formato brasileiro) com todos os magistrados, servidores,
aposentados e pensionistas, no modelo do Anexo VIII da Resolução CNJ 102/2009. Entram as linhas de cargo MINISTRO com
lotação diferente de INATIVO (os aposentados aparecem como INATIVO). O arquivo não separa o abono de permanência
(fica nas vantagens pessoais) nem o 1/3 de férias e o 13º (ficam nas vantagens eventuais), nem dá o nome de cada
indenização. A lista dos arquivos sai em /arquivos (JSON). Abre de fora do Brasil (conferido em 01/10/2026).
"""
import csv
import io
import re

from ..util import _sessao, dormir, log, normalizar_nome, verificar_prazo
from . import comum

ORGAO = "TST"
BASE = "https://transparencia-remuneracao.tst.jus.br"
PAUSA = 2


def arquivos():
    """{AAAAMM: url do CSV}."""
    verificar_prazo()
    r = _sessao().get(f"{BASE}/arquivos", timeout=60)
    r.raise_for_status()
    saida = {}
    for chave in r.json():
        partes = chave.split("-")
        if len(partes) == 3 and partes[2] == "completo":
            saida[int(partes[0]) * 100 + int(partes[1])] = f"{BASE}/arquivo?data-referencia={chave}"
    return saida


def mes(am, url):
    verificar_prazo()
    r = _sessao().get(url, timeout=120)
    r.raise_for_status()
    dormir(PAUSA)
    texto = r.content.decode("latin-1")
    if re.search(r"[\x80-\x9f]", texto):  # jun/2025 veio em MacRoman ("CORRæA" para "CORRÊA")
        texto = r.content.decode("mac_roman")
    linhas_txt = texto.splitlines()
    publicado = next((c for l in linhas_txt[:3] if l.lower().startswith("data de publica") for c in l.split(";")[1:] if c.strip()), "")
    inicio = next(i for i, l in enumerate(linhas_txt) if l.upper().startswith("NOME;CARGO;"))
    tabela = []
    for l in linhas_txt[inicio:]:
        if not l.strip(";").strip():
            break
        tabela.append(l)
    # o leiaute muda de um mês para outro (maiúsculas, "vantagens individuais", coluna de gratificações)
    # alguns arquivos vêm com os acentos perdidos ("Remunerao"): compara só as letras sem acento
    cab = [re.sub(r"[^A-Z]", "", normalizar_nome(c)) for c in next(csv.reader([tabela[0]], delimiter=";"))]
    def idx(padrao, obrigatorio=True):
        for i, c in enumerate(cab):
            if re.search(padrao, c):
                return i
        if obrigatorio:
            raise ValueError(f"TST {am}: coluna {padrao} não encontrada (o leiaute mudou?)")
        return None
    c = {"paradigma": idx("PARADIGMA"), "vp": idx("^VANTAGENS(PESSOAIS|INDIVIDUAIS)"), "sub": idx("^SUBS"),
         "ind": idx("^INDENIZA"), "ev": idx("^VANTAGENSEVENTUAIS"), "grat": idx("^GRATIFICA", obrigatorio=False),
         "total": idx("^TOTAL(DE)?(RENDIMENTOS|DOSCR)"), "diarias": idx("^DI.?RIAS")}
    linhas = []
    for row in csv.reader(tabela[1:], delimiter=";"):
        if len(row) < len(cab) - 1 or row[1].strip().upper() != "MINISTRO" or row[2].strip().upper() in ("INATIVO", "APOSENTADO"):
            continue
        v = lambda k: comum.numero(row[c[k]]) if c[k] is not None else 0.0
        partes = {"subsidio": round(v("paradigma") + v("sub"), 2), "vantagens_pessoais": v("vp"), "indenizacoes": v("ind"),
                  "vantagens_eventuais": v("ev"), "outras": v("grat")}
        nota = f"arquivo oficial do TST (publicado em {publicado})" if publicado else "arquivo oficial do TST"
        if not comum.conferir_total(ORGAO, row[0], am, partes, v("total")):
            nota += (f"; neste mês o próprio arquivo dá R$ {v('total'):.2f} de total de rendimentos, diferente da soma das partes "
                     "(aqui fica a soma das partes, como o arquivo as mostra)")
        linhas.append(comum.linha(ORGAO, am, row[0], "Ministro do Tribunal Superior do Trabalho", row[2], partes, v("diarias"), None, url, nota))
    return linhas


def coletar():
    disp = arquivos()
    fazer = comum.a_fazer(ORGAO, disp)
    linhas, lidos = [], []
    try:
        for am in fazer:
            ls = mes(am, disp[am])
            linhas += ls
            lidos.append({"ano_mes": am, "pessoas": len(ls), "url": disp[am]})
    finally:
        n = comum.gravar(ORGAO, linhas, lidos)
        if lidos:
            log(f"  TST: {len(lidos)} meses lidos ({lidos[0]['ano_mes']} a {lidos[-1]['ano_mes']}), {n} linhas")
    return n
