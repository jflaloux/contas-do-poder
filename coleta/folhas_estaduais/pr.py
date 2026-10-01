"""Paraná: Portal da Transparência do Estado, "Remuneração": a busca pelo nome e a página de detalhes de cada
servidor, com a remuneração mês a mês (vencimento, gratificações, retroativos, outros, auxílios, férias e 13º, bruto).
O robô faz o mesmo que a página: busca o nome, abre os detalhes e lê a tabela (os 20 meses mais recentes).
https://www.transparencia.pr.gov.br/pte/pessoal/servidores/poderexecutivo/remuneracao
A coluna "Redutor/Devoluções" mistura o abate-teto com devoluções pessoais e não é guardada; o governador e o vice
ganham abaixo do teto. A página de busca usa o CPF como marcador interno; ele não é lido nem guardado."""
import html
import re
import time

from ..util import TempoEsgotado, _sessao, verificar_prazo
from . import comum

UF = "PR"
BASE = "https://www.transparencia.pr.gov.br"
PAGINA = f"{BASE}/pte/pessoal/servidores/poderexecutivo/remuneracao"
FONTE = PAGINA
AJAX = {"Faces-Request": "partial/ajax", "X-Requested-With": "XMLHttpRequest"}
MESES = {"JAN": 1, "FEV": 2, "MAR": 3, "ABR": 4, "MAI": 5, "JUN": 6, "JUL": 7, "AGO": 8, "SET": 9, "OUT": 10, "NOV": 11, "DEZ": 12}


def _viewstate(t):
    m = re.search(r'id="j_id1:javax.faces.ViewState:\d+" value="([^"]+)"', t) or re.search(r"javax.faces.ViewState[^>]*><!\[CDATA\[([^\]]+)", t)
    return m.group(1)


def _tabela(nome):
    """[(AAAAMM, cargo, [valores])] da página de detalhes do servidor (None se o nome não aparece)."""
    verificar_prazo()
    s = _sessao()
    t = s.get(PAGINA, timeout=90).text
    url = BASE + re.search(r'<form id="formRemuneracoes"[^>]*action="([^"]+)"', t).group(1).replace("&amp;", "&")
    base = {"formRemuneracoes": "formRemuneracoes", "formRemuneracoes:filtroNome": nome}
    x = s.post(url, data={**base, "javax.faces.partial.ajax": "true", "javax.faces.source": "formRemuneracoes:buttonPesquisar",
                          "javax.faces.partial.execute": "formRemuneracoes", "javax.faces.partial.render": "formRemuneracoes",
                          "formRemuneracoes:buttonPesquisar": "formRemuneracoes:buttonPesquisar", "javax.faces.ViewState": _viewstate(t)},
               headers=AJAX, timeout=90).text
    botoes = re.findall(r'id="(formRemuneracoes:dataTableServidores:\d+:j_idt\d+:\d+:btn-detalhes-remuneracao)"', x)
    cargos = [html.unescape(c).strip() for c in re.findall(r'</div></td><td class="vertical-top lh-px-17">([^<]+)</td>', x)]
    if not botoes:
        return None
    saida = []
    for botao, cargo in zip(botoes, cargos or [""] * len(botoes)):
        time.sleep(1)
        r = s.post(url, data={**base, "javax.faces.partial.ajax": "true", "javax.faces.source": botao, "javax.faces.partial.execute": "@all",
                              botao: botao, "javax.faces.ViewState": _viewstate(x)}, headers=AJAX, timeout=90)
        destino = re.search(r'<redirect url="([^"]+)"', r.text)
        if not destino:
            continue
        pag = s.get(BASE + destino.group(1).replace("&amp;", "&"), timeout=90).text
        corpo = re.search(r'<tbody id="formExibirRemuneracao:dataTableRhRemuneracao_data"[^>]*>(.*?)</tbody>', pag, re.S)
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", corpo.group(1) if corpo else "", re.S):
            c = [html.unescape(re.sub(r"<[^>]+>", "", td)).strip() for td in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
            m = re.fullmatch(r"([A-Z]{3})/(\d{4})", c[1]) if len(c) >= 9 else None
            if m:
                saida.append((int(m.group(2)) * 100 + MESES[m.group(1)], cargo, [comum.num(v) for v in c[2:9]]))
    return saida


# O robots.txt do Portal da Transparência do Paraná tem "Disallow: /pte" para todos os robôs (menos os buscadores).
# Desde 30/09/2026 o robô não abre mais o portal: o site usa o que já estava gravado (até ago/2026) até o Estado
# autorizar. Para voltar a coletar, troque para False.
BLOQUEADO_ROBOTS = True


def coletar():
    if BLOQUEADO_ROBOTS:
        comum.avisar(UF, "o robots.txt do portal não permite robôs; fica o que já estava gravado")
        return 0
    feitos, linhas = set(), []
    fazer = set(comum.a_fazer(UF, comum.ultimo_possivel()))
    if not fazer:
        return 0
    for nome, papel in comum.nomes_folha(UF).items():
        for tentativa in range(3):
            try:
                tabela = _tabela(nome)
                break
            except TempoEsgotado:
                raise
            except Exception:
                if tentativa == 2:
                    raise
                time.sleep(20)
        for am, cargo, (venc, grat, retro, outros, aux, ferias13, bruto) in tabela or []:
            if am not in fazer or not any(comum.no_cargo(o, am) for o in comum.ocupantes(UF) if o.get("folha_nome") == nome):
                continue
            tp = comum.tp_do_cargo(cargo) or papel
            linhas.append(comum.linha(am, tp, nome, cargo, bruto, {"salario": venc + grat, "decimo": None, "ferias": None, "beneficios": aux,
                                                                 # 13º e férias vêm juntos numa coluna; entram em "outros"
                                                                 "outros": retro + outros + ferias13}))
            feitos.add(am)
    comum.gravar(UF, linhas, sorted(feitos))
    return len(linhas)
