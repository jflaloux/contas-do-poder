"""Assembleia Legislativa do Maranhão (Alema): deputado estadual por deputado estadual.

Fontes (Portal da Transparência da Alema, https://sistemas.al.ma.leg.br/transparencia/; só abre de dentro do Brasil, então
este robô roda no Mac):
- CEAP (Cota para o Exercício da Atividade Parlamentar): a "Consulta Verbas Indenizatórias" (lista-parlamentar.html), um
  formulário JSF por competência (mês) que lista os parlamentares com prestação de contas no mês. O link de cada nome leva à
  página do deputado no mês (lista-sintetico.html?competencia=AAAA-MM-01&parlamentar=N): o total de cada inciso da CEAP (sem
  fornecedor), o valor ressarcido "respeitando os limites regulamentares" e o total gasto. O número N de cada nome é guardado
  (parlamentares.csv), e só um nome novo pede o clique. Quando a tabela tem mais linhas do que a página mostra, o robô usa o
  CSV que o botão "CSV" da página entrega.
- Subsídio: Lei 11.876/2023 (R$ 33.006,39 desde fev/2024; R$ 34.774,64 desde fev/2025). A Alema não publica a folha dos
  deputados (a consulta de remuneração dos servidores não traz os deputados).
- Nome completo, gênero e eleito/suplente: TSE (eleição de 2022); partido: candidatura de 2026 no TSE.
Quem está no cargo: os meses em que o deputado aparece na consulta da CEAP.
O robots.txt de sistemas.al.ma.leg.br responde 403. Para a sessão do projeto (util._robots_de), um erro 4xx no robots.txt
quer dizer que não há robots.txt (RFC 9309, 2.3.1.3) e nada fica proibido; o robô pede uma página por vez em cada linha, com
pausa entre os pedidos.
"""
import base64
import csv
import html as H
import io
import re
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from ..config import DADOS
from ..prefeituras.comum import feminino, num
from ..util import TempoEsgotado, _sessao, dormir, gravar_csv, log, normalizar_nome, verificar_prazo
from ..vereadores import comum as vc
from . import comum

UF = "MA"
COD = comum.CODIGOS_UF[UF]
INICIO = 202501
SITE = "https://sistemas.al.ma.leg.br"
LISTA = f"{SITE}/transparencia/lista-parlamentar.html"
DETALHE = f"{SITE}/transparencia/lista-sintetico.html"
PASTA = DADOS / "assembleias" / "ma"
SIMULTANEOS = 3
AJAX = {"Faces-Request": "partial/ajax", "X-Requested-With": "XMLHttpRequest"}
CFG = {
    "cod": COD, "n": "Maranhão", "uf": UF, "casa": "Assembleia Legislativa do Maranhão", "vagas": 42, "inicio": INICIO,
    "id_prefixo": "est", "k": "e", "cargo": ("Deputada estadual", "Deputado estadual"),
    "subsidio": [[202402, 33006.39], [202502, 34774.64]],
    "salario_nota": ("Subsídio fixado em lei (Lei 11.876/2023), proporcional aos meses no cargo: R$ 34.774,64 desde fev/2025. A "
                     "Alema não publica a folha dos deputados, por isso o 13º (a lei prevê em dezembro um valor igual ao subsídio) e "
                     "outros pagamentos não aparecem aqui."),
    "verba_nome": "Cota para o Exercício da Atividade Parlamentar (CEAP)",
    "verba_mes": {"2025": 47942.35, "2026": 47942.35},
    "verba_regra": ("Ressarcimento de despesas do mandato, até R$ 47.942,35 por mês (R$ 41.779,83 do Decreto Legislativo 472/2016, "
                    "reajustados em 14,75% pelo Decreto Legislativo 661/2023), com limites por tipo de despesa (combustível, até 30% da "
                    "cota)."),
    "verba_notas": ["A Alema publica a CEAP por deputado, mês e inciso (combustível, consultorias, divulgação, locomoção...), sem "
                    "fornecedor nem CNPJ, com o total gasto e o valor ressarcido.",
                    "Quando o total gasto passa dos limites da CEAP, aqui vale o valor ressarcido, e a diferença aparece como "
                    "\"Acima dos limites da CEAP (não ressarcido)\".",
                    "A prestação de contas chega depois do mês: o site vai até o último mês em que pelo menos 80% dos deputados já "
                    "aparecem na consulta, e os meses mais recentes ainda podem crescer."],
    "pagina": "https://www.al.ma.leg.br/sitealema/deputados/",
    "notas": ["Quem está no cargo: os meses em que o deputado aparece na consulta da CEAP da Alema (até dois meses seguidos sem "
              "prestação de contas contam como meses no cargo).",
              "Partido: o da candidatura de 2026 no TSE. Quem não é candidato em 2026 aparece sem partido."],
    "fontes": {"verba": LISTA, "subsidio": "https://arquivos.al.ma.leg.br:8443/ged/legislacao/LEI_11876",
               "verba_regra": f"{SITE}/transparencia/pagina.html?p=legislacao-sobre-a-cota-para-o-exercicio-da-atividade-parlamentar-ceap"},
}


def _pedir(metodo, url, ajax=False, **kw):
    verificar_prazo()
    for tentativa in range(3):
        try:
            r = _sessao().request(metodo, url, timeout=90, headers=AJAX if ajax else None, **kw)
            r.raise_for_status()
            dormir(1)
            return r.text
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 2:
                raise
            dormir(15)


def _meses():
    h = time.localtime()
    return [a * 100 + m for a in range(INICIO // 100, h.tm_year + 1) for m in range(1, 13) if INICIO <= a * 100 + m < h.tm_year * 100 + h.tm_mon]


def _texto(t):
    return " ".join(H.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style).*?</\1>", " ", t, flags=re.S))).split())


def _form(t, campo):
    """O formulário JSF que tem `campo` -> (endereço, {campos escondidos}, html do formulário)."""
    for m in re.finditer(r'<form id="[^"]+".*?</form>', t, flags=re.S):
        if campo in m.group(0):
            f = m.group(0)
            dados = {n: H.unescape(v) for n, v in re.findall(r'<input type="hidden"[^>]*name="([^"]+)"[^>]*value="([^"]*)"', f)}
            return SITE + H.unescape(re.search(r'action="([^"]+)"', f).group(1)), dados, f
    raise RuntimeError(f"Alema: formulário com {campo} não encontrado (o leiaute mudou?)")


def _view_state(t, dados):
    """A resposta AJAX pode trazer um ViewState novo."""
    m = re.search(r'ViewState:\d+"><!\[CDATA\[([^\]]+)\]\]>', t)
    if m:
        dados["javax.faces.ViewState"] = m.group(1)


LINK = re.compile(r'<a id="(tabela:(\d+):j_idt\d+)"[^>]*>([^<]*)</a>')


def _lista(am, ids):
    """Consulta da competência -> [(nome, número do parlamentar)]. `ids` ({nome: número}) evita clicar em quem já é conhecido;
    os números novos entram nele."""
    url, dados, f = _form(_pedir("GET", LISTA), "in_competencia_input")
    botao = re.search(r'<button id="([^"]+)"[^>]*type="submit"', f).group(1)
    comp = f"{am % 100:02d}/{am // 100}"
    t = _pedir("POST", url, data={**dados, "in_competencia_input": comp, botao: ""})
    if "Nenhum resultado encontrado" in t:
        return []
    m = re.search(r'widget_tabela",\{id:"tabela",paginator:\{[^}]*rowCount:(\d+)', t)
    total = int(m.group(1)) if m else len(LINK.findall(t))
    url, dados, _ = _form(t, "in_competencia_input")
    dados["in_competencia_input"] = comp
    linhas, saida, primeiro = LINK.findall(t), [], 0
    while True:
        for fonte, _, nome in linhas:
            nome = " ".join(H.unescape(nome).split())
            if nome not in ids:
                r = _pedir("POST", url, ajax=True, data={**dados, "javax.faces.partial.ajax": "true", "javax.faces.source": fonte,
                                                         "javax.faces.partial.execute": fonte, fonte: fonte})
                n = re.search(r"parlamentar=(\d+)", r)
                if not n:
                    raise RuntimeError(f"Alema: o link de {nome} ({comp}) não levou à página do deputado")
                ids[nome] = int(n.group(1))
            saida.append((nome, ids[nome]))
        primeiro += len(linhas) or 10
        if primeiro >= total or not linhas:
            break
        r = _pedir("POST", url, ajax=True, data={**dados, "javax.faces.partial.ajax": "true", "javax.faces.source": "tabela",
                                                 "javax.faces.partial.execute": "tabela", "javax.faces.partial.render": "tabela", "tabela": "tabela",
                                                 "tabela_pagination": "true", "tabela_first": str(primeiro), "tabela_rows": "10",
                                                 "tabela_skipChildren": "true", "tabela_encodeFeature": "true"})
        _view_state(r, dados)
        linhas = LINK.findall(r)
    if len(saida) != total:
        raise RuntimeError(f"Alema: a consulta de {comp} diz {total} parlamentares e a lista trouxe {len(saida)}")
    return saida


def _linhas_tabela(t):
    corpo = re.search(r'_data" class="ui-datatable-data[^"]*">(.*?)</tbody>', t, flags=re.S)
    saida = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", corpo.group(1) if corpo else "", flags=re.S):
        cel = [_texto(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S)]
        if len(cel) >= 3 and re.search(r"\d,\d{2}", cel[2]):
            saida.append((cel[0], cel[1], num(cel[2])))
    return saida


def _csv_detalhe(t):
    """As linhas pelo CSV que o botão "CSV" da página entrega (quando a tabela tem mais linhas do que a página mostra)."""
    url, dados, f = _form(t, "Gerar PDF")
    botao = re.search(r'<button id="([^"]+)"[^>]*>\s*<span[^>]*>CSV</span>', f).group(1)
    r = _pedir("POST", url, ajax=True, data={**dados, "javax.faces.partial.ajax": "true", "javax.faces.source": botao,
                                             "javax.faces.partial.execute": "@all", botao: botao})
    m = re.search(r"base64,([A-Za-z0-9+/=]+)", r)
    if not m:
        raise RuntimeError("Alema: o CSV da CEAP não veio")
    texto = base64.b64decode(m.group(1)).decode("utf-8-sig", errors="replace")
    return [(l[0].strip(), l[1].strip(), num(l[2])) for l in list(csv.reader(io.StringIO(texto)))[1:] if len(l) >= 3 and l[0].strip()]


def _detalhe(am, n):
    """Página do deputado no mês -> (nome, [(inciso, descrição, valor)], ressarcido, total gasto)."""
    t = _pedir("GET", DETALHE, params={"competencia": f"{am // 100}-{am % 100:02d}-01", "parlamentar": str(n)})
    nome = re.search(r"CEAP - (.*?)\s*</h2>", t, flags=re.S)
    linhas = _linhas_tabela(t)
    qtd = re.search(r'widget_[^"]*tbl",\{id:"[^"]*tbl",paginator:\{[^}]*rowCount:(\d+)', t)
    if qtd and int(qtd.group(1)) > len(linhas):
        linhas = _csv_detalhe(t)
        if len(linhas) != int(qtd.group(1)):
            raise RuntimeError(f"Alema: CEAP de {n} em {am}: {qtd.group(1)} linhas na página e {len(linhas)} no CSV")
    x = _texto(t)
    res = re.search(r"limites regulamentares é\s*(R\$\s*-?[\d.]+,\d{2})?", x)
    gasto = re.search(r"Total gasto no mês:\s*(R\$\s*-?[\d.]+,\d{2})?", x)
    return (" ".join(H.unescape(nome.group(1)).split()) if nome else "", linhas,
            num(res.group(1)) if res and res.group(1) else None, num(gasto.group(1)) if gasto and gasto.group(1) else None)


def coletar():
    PASTA.mkdir(parents=True, exist_ok=True)
    try:  # de fora do Brasil o portal não responde: desiste logo (o site usa o que já está gravado)
        _sessao().get(LISTA, timeout=20).raise_for_status()
    except Exception as e:  # noqa: BLE001
        log(f"  Alema: o portal não abriu ({type(e).__name__}); fica o que já estava gravado (este robô roda no Brasil)")
        return
    meses = _meses()
    hoje = time.strftime("%Y-%m-%d")
    arq_p, arq_c, arq_l = PASTA / "parlamentares.csv", PASTA / "competencias.csv", PASTA / "lista.csv"
    arq_m, arq_i = PASTA / "ceap_meses.csv", PASTA / "ceap_incisos.csv"
    par = pd.read_csv(arq_p).fillna("") if arq_p.exists() else pd.DataFrame(columns=["id", "nome", "visto_em"])
    comp = pd.read_csv(arq_c).fillna("") if arq_c.exists() else pd.DataFrame(columns=["ano", "mes", "parlamentares", "lido_em"])
    lis = pd.read_csv(arq_l).fillna("") if arq_l.exists() else pd.DataFrame(columns=["ano", "mes", "id", "nome"])
    cme = pd.read_csv(arq_m).fillna("") if arq_m.exists() else pd.DataFrame(columns=["ano", "mes", "id", "nome", "ressarcido", "total_gasto", "lido_em"])
    cin = pd.read_csv(arq_i).fillna("") if arq_i.exists() else pd.DataFrame(columns=["ano", "mes", "id", "inciso", "descricao", "valor"])
    ids = {str(n): int(i) for i, n in zip(par.id, par.nome)}
    lidos = {int(a) * 100 + int(m): str(l) for a, m, l in zip(comp.ano, comp.mes, comp.lido_em)}
    recentes = set(meses[-4:])

    def velho(am, lido):
        if am in recentes:
            return lido < hoje
        return pd.Timestamp(lido) < pd.Timestamp(hoje) - pd.Timedelta(days=30) if lido else True
    # 1. quem prestou contas em cada mês (os 4 últimos meses de novo uma vez por dia; os outros, uma vez por mês)
    feitos = 0
    try:
        for am in sorted(meses, reverse=True):
            if am in lidos and not velho(am, lidos[am]):
                continue
            antes = len(ids)
            nomes = _lista(am, ids)
            a, m = divmod(am, 100)
            lis = pd.concat([lis[(lis.ano.astype(int) * 100 + lis.mes.astype(int)) != am] if len(lis) else lis,
                             pd.DataFrame([{"ano": a, "mes": m, "id": i, "nome": n} for n, i in nomes], columns=["ano", "mes", "id", "nome"])])
            comp = pd.concat([comp[(comp.ano.astype(int) * 100 + comp.mes.astype(int)) != am] if len(comp) else comp,
                              pd.DataFrame([{"ano": a, "mes": m, "parlamentares": len(nomes), "lido_em": hoje}])])
            lidos[am] = hoje
            feitos += 1
            if len(ids) > antes:
                par = pd.DataFrame([{"id": i, "nome": n, "visto_em": hoje} for n, i in ids.items()])
                gravar_csv(par.sort_values(["id", "nome"]), arq_p)
            if gravar_csv(lis.sort_values(["ano", "mes", "nome"]), arq_l):  # a competência só conta como lida se a lista foi gravada
                gravar_csv(comp.sort_values(["ano", "mes"]), arq_c)
    finally:
        log(f"  Alema: consulta de {feitos} competências feita agora; {len(ids)} parlamentares conhecidos")
    # 2. a página de cada deputado no mês: quem ainda não foi lido, e os 4 últimos meses de novo uma vez por dia
    ja = {(int(a) * 100 + int(m), int(i)): str(l) for a, m, i, l in zip(cme.ano, cme.mes, cme.id, cme.lido_em)}
    pedir = sorted({(int(a) * 100 + int(m), int(i)) for a, m, i in zip(lis.ano, lis.mes, lis.id)
                    if (int(a) * 100 + int(m), int(i)) not in ja or (int(a) * 100 + int(m) in recentes and ja[(int(a) * 100 + int(m), int(i))] < hoje)},
                   reverse=True)

    def um(item):
        am, n = item
        return am, n, _detalhe(am, n)
    res = []

    def gravar():
        nonlocal cme, cin
        if not res:
            return
        chave = {(am, n) for am, n, _ in res}
        novos_m = pd.DataFrame([{"ano": am // 100, "mes": am % 100, "id": n, "nome": d[0], "ressarcido": d[2], "total_gasto": d[3], "lido_em": hoje}
                                for am, n, d in res])
        novos_i = pd.DataFrame([{"ano": am // 100, "mes": am % 100, "id": n, "inciso": c, "descricao": ds, "valor": v}
                                for am, n, d in res for c, ds, v in d[1]], columns=["ano", "mes", "id", "inciso", "descricao", "valor"])
        fora = lambda df: df[[(int(a) * 100 + int(m), int(i)) not in chave for a, m, i in zip(df.ano, df.mes, df.id)]] if len(df) else df
        cme = pd.concat([fora(cme), novos_m])
        cin = pd.concat([fora(cin), novos_i]) if len(novos_i) else fora(cin)
        if gravar_csv(cme.sort_values(["ano", "mes", "id"]), arq_m):
            gravar_csv(cin.sort_values(["ano", "mes", "id", "inciso"]), arq_i)
    try:
        with ThreadPoolExecutor(SIMULTANEOS) as ex:
            for k in range(0, len(pedir), SIMULTANEOS * 10):  # em lotes, gravando depois de cada lote
                verificar_prazo()
                res.extend(ex.map(um, pedir[k:k + SIMULTANEOS * 10]))
                gravar()
                res.clear()
    finally:
        gravar()
        log(f"  Alema: {len(pedir)} páginas de deputado e mês a ler; {len(cme)} gravadas")


def _partido(nome, partidos):
    """Partido da candidatura de 2026 (comum.partido_2026) pelo nome civil: igual; igual sem os espaços ("D ANGELO" e
    "DANGELO"); ou o único candidato de 2026 com o mesmo primeiro nome e todas as palavras (pelo menos três) dentro do nome
    de 2022 (quem tirou um sobrenome: "JANAINA LIMA ARAUJO" e "JANAINA LIMA ARAUJO RAMOS")."""
    n = normalizar_nome(nome)
    if not n:
        return ""
    if n in partidos:
        return partidos[n]
    juntos = [v for k, v in partidos.items() if k.replace(" ", "") == n.replace(" ", "")]
    if len(juntos) == 1:
        return juntos[0]
    w = n.split()
    dentro = [v for k, v in partidos.items() if len(k.split()) >= 3 and k.split()[0] == w[0] and set(k.split()) <= set(w)]
    return dentro[0] if len(dentro) == 1 else ""


INCISOS = {"I": "Passagens", "II": "Telefone e internet", "III": "Correios", "IV": "Escritório (aluguel e contas)",
           "V": "Assinaturas e livros", "VI": "Alimentação", "VII": "Hospedagem", "VIII": "Outras despesas com locomoção",
           "IX": "Combustível", "X": "Segurança", "XI": "Consultorias e assessorias", "XII": "Divulgação do mandato",
           "XIII": "Material de escritório", "XIV": "Reprografia, fotografia e filmagem", "XV": "Site e sistemas",
           "XVI": "Manutenção de veículos", "XVII": "Diárias de servidores do gabinete"}
ACIMA = "Acima dos limites da CEAP (não ressarcido)"


def montar(tipos):
    arq_l, arq_m = PASTA / "lista.csv", PASTA / "ceap_meses.csv"
    if not arq_l.exists() or not arq_m.exists():
        return None
    lis = pd.read_csv(arq_l)
    cme = pd.read_csv(arq_m)
    cin = pd.read_csv(PASTA / "ceap_incisos.csv").fillna({"inciso": "", "descricao": ""}) if (PASTA / "ceap_incisos.csv").exists() \
        else pd.DataFrame(columns=["ano", "mes", "id", "inciso", "descricao", "valor"])
    lis["am"] = lis.ano * 100 + lis.mes
    if not len(lis):
        return None
    # a prestação de contas chega depois do mês: o último mês do site é o último em que pelo menos 80% das vagas já aparecem
    por_mes = lis.groupby("am").id.nunique()
    cheios = [int(m) for m, n in por_mes.items() if n >= 0.8 * CFG["vagas"]]
    ultimo_dado = max(cheios) if cheios else int(por_mes.index.max())
    lis = lis[lis.am <= ultimo_dado]
    tse = comum.tse_2022(UF)
    partidos = comum.partido_2026(UF)
    ultimo = vc.ultimo_mes_fechado()
    ver, mandatos, cods = [], [], {}
    for i, g in lis.groupby("id"):
        nome = g.sort_values("am").nome.iloc[-1]
        t = comum.achar(nome, tse) or comum.achar(re.sub(r"\b(DR|DRA)ª?\.?\s+", " ", normalizar_nome(nome)), tse) or {}
        codigo = comum.codigo_de(nome, t)
        cods[int(i)] = codigo
        nc = t.get("nome") or nome
        # o nome de urna quando a Alema usa o nome civil ("Ariston Ribeiro de Sousa") ou só o começo dele ("Janaína")
        urna, n_ = normalizar_nome(t.get("urna") or ""), normalizar_nome(nome)
        exib = vc.titulo(t["urna"]) if urna and (n_ == normalizar_nome(t.get("nome")) or (len(urna) > len(n_) and urna.startswith(n_))) else nome
        ver.append({"codigo": codigo, "nome": exib, "nome_civil": vc.titulo(nc), "partido": _partido(nc, partidos),
                    "genero": t.get("genero") or ("F" if feminino(nome) else "M"), "eleito": t.get("eleito", ""), "pagina": CFG["pagina"]})
        meses_g = sorted(set(g.am))
        for a, f in comum.periodos(meses_g, ultimo_dado, ultimo, folga=2):
            mandatos.append({"codigo": codigo, "inicio": a, "fim": f})
    cin["am"] = cin.ano * 100 + cin.mes
    cme["am"] = cme.ano * 100 + cme.mes
    na_lista = set(zip(lis.am, lis.id))
    d = cin[pd.Series([(a, i) in na_lista for a, i in zip(cin.am, cin.id)], index=cin.index, dtype=bool) & (cin.valor.abs() >= 0.005)]
    desp = pd.DataFrame({"ano": d.ano, "mes": d.mes, "codigo": d.id.map(cods), "tipo": [INCISOS.get(c.strip().upper()) or vc.tipo_curto(ds) for c, ds in zip(d.inciso, d.descricao)],
                         "fornecedor": "", "cnpj_cpf": "", "valor": d.valor})
    # o que passou dos limites (total gasto maior que o ressarcido) sai do mês, como linha própria
    soma = d.groupby(["am", "id"]).valor.sum()
    acima = []
    for r in cme[[(a, i) in na_lista for a, i in zip(cme.am, cme.id)]].itertuples():
        res = pd.to_numeric(r.ressarcido, errors="coerce")
        if pd.isna(res):
            continue
        x = round(float(res) - float(soma.get((r.am, r.id), 0.0)), 2)
        if abs(x) >= 0.01:
            acima.append({"ano": r.ano, "mes": r.mes, "codigo": cods[int(r.id)], "tipo": ACIMA if x < 0 else "Diferença entre o ressarcido e os incisos",
                          "fornecedor": "", "cnpj_cpf": "", "valor": x})
    if acima:
        desp = pd.concat([desp, pd.DataFrame(acima)])
    cfg = dict(CFG, ultimo_mes=min(ultimo, ultimo_dado))
    return vc.montar(cfg, tipos, pd.DataFrame(ver), pd.DataFrame(mandatos), despesas=desp)
