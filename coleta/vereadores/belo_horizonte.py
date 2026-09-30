"""Câmara Municipal de Belo Horizonte: vereador por vereador.

Fontes (portal da Câmara, sem cadastro; o robots.txt pede 10 s entre pedidos, e aqui é um pedido por vez com essa pausa):
- Vereadores no cargo hoje, com partido, página e foto: https://www.cmbh.mg.gov.br/vereadores
- Quem estava no cargo em cada mês (titulares e suplentes que assumiram), dia de reunião a dia de reunião:
  POST https://www.cmbh.mg.gov.br/transparencia/vereadores/presenca-mensal-consolidada (ano=AAAA&mes=MM). Os meses sem
  reunião de Plenário (janeiro) não têm lista.
- Custeio Parlamentar (a verba do gabinete desde ago/2017: escritório, informática, gráfica, divulgação, carimbos,
  copa, correios e telefone), por vereador e por mês, com o tipo de cada despesa e o link da nota fiscal (sem o nome
  do fornecedor): https://www.cmbh.mg.gov.br/transparencia/vereadores/custeio-parlamentar
  (POST .../sites/all/modules/execucao_orcamentaria_custeio/pesquisar.php e detalhar.php, data=MM/AAAA)
- Subsídio e auxílio-alimentação: https://www.cmbh.mg.gov.br/transparencia/pessoal/estrutura-remuneratoria/vereadores
  (subsídio de R$ 18.402,02 pela Lei 11.016/2016; auxílio-alimentação de R$ 2.374,00 por mês pela Lei 11.849/2025,
  promulgada em 29/04/2025 e paga desde maio de 2025). A consulta nominal da folha pede CAPTCHA: não é usada.
- Nome completo, partido na eleição e gênero: TSE (eleição de 2024).
A equipe dos gabinetes não entra: o que cada assessor recebe só aparece na consulta com CAPTCHA.
"""
import hashlib
import html as html_lib
import re
import time
from calendar import monthrange
from datetime import date, timedelta

import pandas as pd

from ..config import CACHE, DADOS
from ..util import TempoEsgotado, _sessao, cache_valido, log, normalizar_nome, verificar_prazo
from . import comum

COD = 3106200
INICIO = 202501
SITE = "https://www.cmbh.mg.gov.br"
PRESENCA = f"{SITE}/transparencia/vereadores/presenca-mensal-consolidada"
CUSTEIO = f"{SITE}/sites/all/modules/execucao_orcamentaria_custeio"
PASTA = DADOS / "municipios" / "belo_horizonte"
C = CACHE / "cmbh"
REBAIXAR = 3
PAUSA = 10  # Crawl-delay do robots.txt da Câmara
SUBSIDIO = 18402.02
AUXILIO = 2374.00
AUXILIO_DESDE = 202505  # Lei 11.849, de 28/04/2025 (promulgada em 29/04): pago a partir de 1º de maio de 2025
MESES_NOME = {normalizar_nome(n): i for i, n in enumerate(["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto",
                                                           "Setembro", "Outubro", "Novembro", "Dezembro"], 1)}
CFG = {
    "cod": COD, "n": "Belo Horizonte", "uf": "MG", "casa": "Câmara Municipal de Belo Horizonte", "vagas": 41, "inicio": INICIO,
    "subsidio": [[202501, SUBSIDIO]],
    "verba_nome": "Custeio Parlamentar",
    "verba_regra": "A Câmara paga as despesas do gabinete com escritório, informática, serviços gráficos, divulgação do mandato, carimbos, material de copa, correios e telefone.",
    "verba_notas": ["A Câmara publica o custeio por vereador e por mês, com o tipo de cada despesa e a nota fiscal, mas sem o nome do fornecedor.",
                    "O portal da Câmara não publica um limite mensal do custeio por vereador."],
    "salario_nota": ("Subsídio de R$ 18.402,02 por mês (Lei 11.016/2016), contado pelos dias no cargo, mais o auxílio-alimentação "
                     "de R$ 2.374,00 por mês desde maio de 2025 (Lei 11.849/2025, pago em cartão-alimentação). A consulta nominal da "
                     "folha pede CAPTCHA, por isso ficam de fora o 13º (pago em dezembro, na proporção da presença nas reuniões do "
                     "Plenário), o 1/3 de férias de janeiro, o pagamento do início da legislatura e o auxílio-alimentação por dia "
                     "de trabalho que valia até abril de 2025."),
    "conferir_gastos": False,  # o custeio é miúdo e muitos gabinetes passam meses sem usar
    "equipe_nota": "A Câmara não publica, sem CAPTCHA, quanto recebe cada assessor de gabinete: a equipe não entra.",
    "credito_foto": "Câmara Municipal de Belo Horizonte", "pagina": f"{SITE}/vereadores",
    "notas": ["Quem estava no cargo em cada mês vem da presença mensal nas reuniões do Plenário, que lista os 41 vereadores em "
              "exercício (titulares e suplentes que assumiram). Em janeiro não há reunião nem lista: vale quem estava no cargo em "
              "dezembro ou, quando um suplente assumiu em janeiro, o suplente (se já tem custeio no mês), desde o dia 1º."],
    "fontes": {"vereadores": f"{SITE}/vereadores", "presenca": PRESENCA, "custeio": f"{SITE}/transparencia/vereadores/custeio-parlamentar",
               "subsidio": f"{SITE}/transparencia/pessoal/estrutura-remuneratoria/vereadores"},
}

# Códigos da presença mensal (legenda da página da Câmara). Fora do cargo naquele dia de reunião: o titular licenciado
# ou que saiu (o dia aparece com o código do suplente que o substitui, "SPL ..."), quem renunciou, teve o mandato cassado,
# não tomou posse, assumiu depois, está de licença sem remuneração ou foi só convocado para uma reunião (V.ADHOC).
FORA = re.compile(r"^(SPL\b.*|REN|MC|NTP|AMDF|SR|V\.?\s*ADHOC)$", re.I)

_ultimo_pedido = [0.0]


# ---------------------------------------------------------------- coleta
def _pedir(metodo, url, arquivo=None, dias=None, **kw):
    """Um pedido por vez, com 10 s entre um e outro (Crawl-delay do robots.txt da Câmara)."""
    if arquivo is not None and cache_valido(arquivo, dias):
        return arquivo.read_text(encoding="utf-8")
    for tentativa in range(3):
        verificar_prazo()
        espera = PAUSA - (time.monotonic() - _ultimo_pedido[0])
        if espera > 0:
            time.sleep(espera)
        try:
            r = _sessao().request(metodo, url, timeout=90, **kw)
            _ultimo_pedido[0] = time.monotonic()
            r.raise_for_status()
            texto = r.content.decode("utf-8", errors="replace")
            break
        except TempoEsgotado:
            raise
        except Exception:
            _ultimo_pedido[0] = time.monotonic()
            if tentativa == 2:
                raise
            time.sleep(PAUSA * (tentativa + 1))
    if arquivo is not None:
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_text(texto, encoding="utf-8")
    return texto


def _texto(t):
    return re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", t or ""))).strip()


def _valor(t):
    t = re.sub(r"[^\d,]", "", t or "")
    return float(t.replace(",", ".")) if t else 0.0


def lista_site():
    """Os 41 vereadores no cargo hoje: nome parlamentar, página, foto e partido, pela página da Câmara."""
    t = _pedir("GET", f"{SITE}/vereadores")
    linhas = []
    for bloco in re.split(r'<div class="vereador">', t)[1:]:
        a = re.search(r'href="(/vereadores/[^"]+)"', bloco)
        img = re.search(r'<img[^>]+src="([^"]+)"', bloco)
        partido = re.search(r'field-sigla">\s*<div class="field-content">(.*?)</div>', bloco, re.S)
        nome = re.search(r'views-field-title">\s*<span class="field-content"><a [^>]*>(.*?)</a>', bloco, re.S)
        if not (a and nome):
            continue
        linhas.append({"pagina": SITE + a.group(1), "foto": img.group(1) if img else "", "nome": _texto(nome.group(1)),
                       "partido": _texto(partido.group(1)) if partido else ""})
    df = pd.DataFrame(linhas, columns=["pagina", "foto", "nome", "partido"]).drop_duplicates("pagina")
    if len(df) < 30:
        raise RuntimeError(f"a página de vereadores trouxe só {len(df)} nomes")
    PASTA.mkdir(parents=True, exist_ok=True)
    df.to_csv(PASTA / "site_vereadores.csv", index=False)
    log(f"  Belo Horizonte: {len(df)} vereadores na página da Câmara")
    return df


def _ler_presenca(t, a, m):
    """HTML da presença mensal -> [{nome, dias, codigos}] (dias de reunião e o código de cada um, separados por "|")."""
    titulo = re.search(r"Presença Mensal Consolidada[^<]*-\s*([^<]+?)\s+de\s+(\d{4})\s*</h2>", t)
    if not titulo or MESES_NOME.get(normalizar_nome(titulo.group(1))) != m or int(titulo.group(2)) != a:
        return None  # mês sem reunião (a página responde "... fpAAAAMM.xls is not readable") ou outra página
    linhas = []
    for nome, tabela in re.findall(r"<h3>(.*?)</h3>\s*<div class=\"table-responsive\">\s*<table[^>]*>(.*?)</table>", t, re.S):
        dias = [_texto(x) for x in re.findall(r"<th[^>]*>(.*?)</th>", tabela, re.S)]
        cods = [_texto(x) for x in re.findall(r"<td[^>]*>(.*?)</td>", tabela, re.S)]
        linhas.append({"ano": a, "mes": m, "nome": _texto(nome), "dias": "|".join(dias), "codigos": "|".join(cods)})
    return linhas


def presenca():
    """Presença mensal no Plenário: quem estava no cargo em cada mês. Os meses antigos já gravados não são baixados de novo."""
    ate = comum.ultimo_mes_fechado()
    recentes = comum.menos_meses(ate, REBAIXAR)
    arq, arq_m = PASTA / "presenca.csv", PASTA / "presenca_meses.csv"
    velha = pd.read_csv(arq, dtype=str).fillna("") if arq.exists() else pd.DataFrame(columns=["ano", "mes", "nome", "dias", "codigos"])
    velha_m = pd.read_csv(arq_m) if arq_m.exists() else pd.DataFrame(columns=["ano", "mes", "publicado"])
    feitos = {int(a) * 100 + int(m): int(p) for a, m, p in zip(velha_m.ano, velha_m.mes, velha_m.publicado)}
    linhas, meses_l = [], []
    for a, m in comum.meses(INICIO, ate):
        am = a * 100 + m
        if am in feitos and am <= recentes:
            linhas += velha[(velha.ano.astype(int) * 100 + velha.mes.astype(int)) == am].to_dict("records")
            meses_l.append({"ano": a, "mes": m, "publicado": feitos[am]})
            continue
        t = _pedir("POST", PRESENCA, C / f"presenca_{am}.html", None if am <= recentes else 5, data={"ano": a, "mes": f"{m:02d}"})
        lido = _ler_presenca(t, a, m)
        if lido is None and "not readable" not in t:
            raise RuntimeError(f"presença de {m:02d}/{a}: resposta inesperada da Câmara")
        linhas += lido or []
        meses_l.append({"ano": a, "mes": m, "publicado": 1 if lido else 0})
    PASTA.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(linhas, columns=["ano", "mes", "nome", "dias", "codigos"]).to_csv(arq, index=False)
    pd.DataFrame(meses_l, columns=["ano", "mes", "publicado"]).to_csv(arq_m, index=False)
    log(f"  Belo Horizonte: presença de {sum(x['publicado'] for x in meses_l)} meses ({len(linhas)} linhas vereador × mês)")


def _ler_totais(t):
    return [{"nome": _texto(n), "id_custeio": c, "total": _valor(v)} for n, c, v in
            re.findall(r"<td[^>]*>([^<]*)</td>\s*<td[^>]*>\s*<a[^>]*data-codvereador=\"([^\"]+)\"[^>]*>.*?</a>\s*</td>\s*<td[^>]*>([^<]*)</td>", t, re.S)]


def _ler_itens(t):
    """Detalhe do custeio de um vereador num mês -> [(despesa, valor, id da nota)]; e o total que a página mostra."""
    itens, total = [], None
    for linha in re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S):
        cel = re.findall(r"<td[^>]*>(.*?)</td>", linha, re.S)
        if len(cel) < 3:
            continue
        if _texto(cel[0]).lower() == "total":
            total = _valor(_texto(cel[2]))
            continue
        nota = re.search(r"downloadNotaFiscal\?id=(\d+)", cel[3] if len(cel) > 3 else "")
        itens.append((_texto(cel[1]), _valor(_texto(cel[2])), nota.group(1) if nota and nota.group(1) != "0" else ""))
    return itens, total


def custeio():
    """Custeio Parlamentar mês a mês: o total de cada vereador e as despesas por tipo. Nos meses recentes, o detalhe de um
    vereador só é pedido de novo se o total mudou (cada pedido leva 10 s)."""
    ate = comum.ultimo_mes_fechado()
    recentes = comum.menos_meses(ate, REBAIXAR)
    arq_t, arq_i = PASTA / "custeio_totais.csv", PASTA / "custeio_itens.csv"
    col_t, col_i = ["ano", "mes", "id_custeio", "nome", "total"], ["ano", "mes", "id_custeio", "nome", "despesa", "valor", "nota"]
    vt = pd.read_csv(arq_t, dtype={"id_custeio": str}) if arq_t.exists() else pd.DataFrame(columns=col_t)
    vi = pd.read_csv(arq_i, dtype={"id_custeio": str, "nota": str}).fillna({"nota": ""}) if arq_i.exists() else pd.DataFrame(columns=col_i)
    meses_ok = set(pd.read_csv(PASTA / "custeio_meses.csv").aaaamm) if (PASTA / "custeio_meses.csv").exists() else set()
    for a, m in comum.meses(INICIO, ate):
        am = a * 100 + m
        if am in meses_ok and am <= recentes:
            continue
        corpo = {"paginaRequerida": 1, "codVereador": "", "mobile": 0, "data": f"{m:02d}/{a}"}
        t = _pedir("POST", f"{CUSTEIO}/pesquisar.php", C / f"custeio_{am}.html", None if am <= recentes else 1, data=corpo)
        totais = _ler_totais(t)
        if not totais and "Resultados da pesquisa" not in t and "resultado" not in t.lower():
            raise RuntimeError(f"custeio de {m:02d}/{a}: resposta inesperada da Câmara")
        antes_t = vt[(vt.ano.astype(int) * 100 + vt.mes.astype(int)) == am] if len(vt) else vt
        antes_i = vi[(vi.ano.astype(int) * 100 + vi.mes.astype(int)) == am] if len(vi) else vi
        novas_t, novas_i = [], []
        for x in totais:
            velho = antes_t[antes_t.id_custeio == x["id_custeio"]]
            velhos_i = antes_i[antes_i.id_custeio == x["id_custeio"]]
            if len(velho) and abs(float(velho.total.iloc[0]) - x["total"]) < 0.005 and len(velhos_i) and abs(velhos_i.valor.sum() - x["total"]) < 0.01:
                novas_i += velhos_i.to_dict("records")
            else:
                d = _pedir("POST", f"{CUSTEIO}/detalhar.php", C / f"custeio_{am}_{x['id_custeio']}_{round(x['total'] * 100)}.html", None,
                           data=dict(corpo, codVereador=x["id_custeio"]))
                itens, total = _ler_itens(d)
                soma = round(sum(v for _, v, _ in itens), 2)
                if abs(soma - x["total"]) >= 0.01 or (total is not None and abs(total - x["total"]) >= 0.01):
                    log(f"  Belo Horizonte: custeio de {x['nome']} em {m:02d}/{a}: total {x['total']:.2f}, detalhe soma {soma:.2f}")
                novas_i += [{"ano": a, "mes": m, "id_custeio": x["id_custeio"], "nome": x["nome"], "despesa": desp, "valor": v, "nota": nota}
                            for desp, v, nota in itens]
            novas_t.append({"ano": a, "mes": m, **x})
        vt = pd.concat([vt[(vt.ano.astype(int) * 100 + vt.mes.astype(int)) != am] if len(vt) else vt, pd.DataFrame(novas_t, columns=col_t)], ignore_index=True)
        vi = pd.concat([vi[(vi.ano.astype(int) * 100 + vi.mes.astype(int)) != am] if len(vi) else vi, pd.DataFrame(novas_i, columns=col_i)], ignore_index=True)
        meses_ok.add(am)
        PASTA.mkdir(parents=True, exist_ok=True)  # grava mês a mês: se o tempo acabar, a próxima rodada continua daqui
        vt.sort_values(["ano", "mes", "nome"]).to_csv(arq_t, index=False)
        vi.sort_values(["ano", "mes", "nome", "despesa"], kind="stable").to_csv(arq_i, index=False)
        pd.DataFrame({"aaaamm": sorted(meses_ok)}).to_csv(PASTA / "custeio_meses.csv", index=False)
        soma = f"{sum(x['total'] for x in totais):_.2f}".replace(".", ",").replace("_", ".")
        log(f"  Belo Horizonte: custeio de {m:02d}/{a}: {len(totais)} vereadores, R$ {soma}")


def fotos():
    """Fotos da página da Câmara, uma por vez e com a pausa do robots.txt (só as que faltam)."""
    site = pd.read_csv(PASTA / "site_vereadores.csv").fillna("") if (PASTA / "site_vereadores.csv").exists() else None
    if site is None:
        return
    tse = comum.candidatos_tse("MG", "Belo Horizonte")
    for s in site.itertuples():
        codigo = _codigo(s.nome, comum.achar_no_tse(s.nome, tse))
        if not s.foto or (comum.FOTOS / f"ver-{COD}-{codigo}.webp").exists():
            continue
        verificar_prazo()
        espera = PAUSA - (time.monotonic() - _ultimo_pedido[0])
        if espera > 0:
            time.sleep(espera)
        comum.fotos(COD, [(codigo, s.foto)])
        _ultimo_pedido[0] = time.monotonic()


def coletar():
    lista_site()
    presenca()
    custeio()
    fotos()


# ---------------------------------------------------------------- montagem
def _codigo(nome, tse_linha):
    """Código do vereador: o número do candidato no TSE (o mesmo em todas as fontes); sem ele, um número tirado do nome."""
    if tse_linha is not None:
        return int(tse_linha["sq"])
    return int(hashlib.md5(comum.chave_nome(nome).encode()).hexdigest()[:10], 16)


def _intervalos_do_mes(a, m, dias, codigos):
    """Dias de reunião do mês e o código de cada um -> [(inicio, fim)] no cargo naquele mês. Um trecho que começa na
    primeira reunião do mês vale desde o dia 1; um que termina na última vale até o fim do mês. Entre um e outro, a troca
    vale no dia da reunião em que ela aparece (o titular sai na véspera, o suplente entra no dia)."""
    por_dia = {}
    for d, c in zip(dias, codigos):
        if str(d).strip().isdigit():
            por_dia[int(d)] = por_dia.get(int(d), False) or not FORA.match(c.strip())
    ordem = sorted(por_dia)
    fim_mes = monthrange(a, m)[1]
    saida, i = [], 0
    while i < len(ordem):
        if not por_dia[ordem[i]]:
            i += 1
            continue
        j = i
        while j + 1 < len(ordem) and por_dia[ordem[j + 1]]:
            j += 1
        ini = 1 if i == 0 else ordem[i]
        fim = fim_mes if j == len(ordem) - 1 else ordem[j + 1] - 1
        saida.append((date(a, m, ini), date(a, m, fim)))
        i = j + 1
    return saida


def _juntar(intervalos):
    saida = []
    for i, f in sorted(intervalos):
        if saida and i <= saida[-1][1] + timedelta(days=1):
            saida[-1] = (saida[-1][0], max(saida[-1][1], f))
        else:
            saida.append((i, f))
    return saida


def montar(tipos):
    if not (PASTA / "presenca.csv").exists():
        return None
    ate = comum.ultimo_mes_fechado()
    pres = pd.read_csv(PASTA / "presenca.csv", dtype=str).fillna("")
    pres_m = pd.read_csv(PASTA / "presenca_meses.csv")
    site = pd.read_csv(PASTA / "site_vereadores.csv").fillna("") if (PASTA / "site_vereadores.csv").exists() else pd.DataFrame(columns=["pagina", "foto", "nome", "partido"])
    itens = pd.read_csv(PASTA / "custeio_itens.csv", dtype={"id_custeio": str, "nota": str}).fillna({"nota": "", "despesa": ""}) if (PASTA / "custeio_itens.csv").exists() else None
    totais = pd.read_csv(PASTA / "custeio_totais.csv", dtype={"id_custeio": str}) if (PASTA / "custeio_totais.csv").exists() else None
    tse = comum.candidatos_tse("MG", "Belo Horizonte")

    # quem é quem: o número do candidato no TSE liga os nomes da presença, do custeio e da página da Câmara
    nomes = {}  # código -> nome mais recente na presença (vale como nome parlamentar de quem não está mais na página)

    ja = {}

    def codigo_de(nome):
        if nome not in ja:
            ja[nome] = _codigo(nome, comum.achar_no_tse(nome, tse))
        return ja[nome]
    site = site.assign(codigo=site.nome.map(codigo_de))
    pres = pres.assign(nome=pres.nome.str.strip(), aaaamm=pres.ano.astype(int) * 100 + pres.mes.astype(int))
    pres = pres.assign(codigo=pres.nome.map(codigo_de))
    for n, c in zip(pres.sort_values("aaaamm").nome, pres.sort_values("aaaamm").codigo):
        nomes[c] = n

    # no cargo, mês a mês, pela presença
    publicados = sorted(int(a) * 100 + int(m) for a, m, p in zip(pres_m.ano, pres_m.mes, pres_m.publicado) if int(p))
    publicados = [am for am in publicados if am <= ate]
    if not publicados:
        return None
    ultimo_pub = publicados[-1]
    interv = {}  # código -> [(inicio, fim)]
    for r in pres[pres.aaaamm.isin(publicados)].itertuples():
        a, m = divmod(int(r.aaaamm), 100)
        interv.setdefault(r.codigo, []).extend(_intervalos_do_mes(a, m, r.dias.split("|"), r.codigos.split("|")))

    def no_cargo_em(dia):
        return {c for c, iv in interv.items() if any(i <= dia <= f for i, f in iv)}
    # meses sem lista (janeiro, sem reunião; e os meses depois da última lista): vale quem estava no cargo no fim do mês
    # anterior com lista. Se uma cadeira trocou de dono entre essa lista e a seguinte, o suplente que já tem custeio no
    # mês sem lista conta desde o começo dele (ex.: Rubão, que assumiu em 06/01/2026 no lugar de Lucas Ganem). No começo
    # da legislatura (jan/2025), vale quem estava no cargo no começo de fevereiro.
    gastou = set()
    if totais is not None and len(totais):
        gastou = {(codigo_de(n), int(a) * 100 + int(m)) for n, a, m, v in zip(totais.nome, totais.ano, totais.mes, totais.total) if float(v) > 0}
    for a, m in comum.meses(INICIO, ate):
        am = a * 100 + m
        if am in publicados:
            continue
        antes = [x for x in publicados if x < am]
        depois = [x for x in publicados if x > am]
        if antes:
            pa, pm = divmod(antes[-1], 100)
            quem = no_cargo_em(date(pa, pm, monthrange(pa, pm)[1]))
            if depois:
                seguinte = no_cargo_em(date(depois[0] // 100, depois[0] % 100, 1))
                saem = sorted(quem - seguinte, key=lambda c: ((c, am) in gastou, c))
                entram = sorted(c for c in seguinte - quem if (c, am) in gastou)[:len(saem)]
                quem = (quem - set(saem[:len(entram)])) | set(entram)
        else:
            quem = no_cargo_em(date(depois[0] // 100, depois[0] % 100, 1)) if depois else set()
        for c in quem:
            interv[c].append((date(a, m, 1), date(a, m, monthrange(a, m)[1])))
    fim_ate = date(ate // 100, ate % 100, monthrange(ate // 100, ate % 100)[1])
    no_site = set(site.codigo)
    linhas_m = []
    for c, iv in interv.items():
        for i, f in _juntar(iv):
            aberto = f >= fim_ate and c in no_site
            linhas_m.append({"codigo": int(c), "inicio": i.isoformat(), "fim": "" if aberto else f.isoformat()})
    mandatos_df = pd.DataFrame(linhas_m, columns=["codigo", "inicio", "fim"])
    fora_da_lista = sorted(set(site.nome[~site.codigo.isin(interv)]))
    if fora_da_lista:
        log(f"  Belo Horizonte: na página da Câmara e não na presença: {', '.join(fora_da_lista)}")

    # cadastro
    info_site = {r.codigo: r for r in site.itertuples()}
    linhas_v = []
    for c in interv:
        s = info_site.get(c)
        nome = s.nome if s is not None else nomes.get(c, "")
        t = comum.achar_no_tse(nome, tse)
        linhas_v.append({"codigo": int(c), "nome": nome.strip(), "nome_civil": comum.titulo(t["nome"]) if t is not None else "",
                         "partido": (s.partido if s is not None and s.partido else "") or (t["partido"] if t is not None else ""),
                         "genero": t["genero"] if t is not None else "", "eleito": t["situacao"] if t is not None else "",
                         "pagina": s.pagina if s is not None else ""})
    ver = pd.DataFrame(linhas_v)
    sem_tse = sorted(ver.nome[ver.nome_civil == ""])
    if sem_tse:
        log(f"  Belo Horizonte: sem nome no TSE: {', '.join(sem_tse)}")

    # contracheque sem a folha: subsídio e auxílio-alimentação pelos dias no cargo
    periodos = {c: _juntar(iv) for c, iv in interv.items()}
    ganha_l = []
    for c, per in periodos.items():
        for a, m in comum.meses(INICIO, ate):
            dias = comum.dias_no_mes(per, a, m)
            if not dias:
                continue
            frac = dias / monthrange(a, m)[1]
            ganha_l.append({"ano": a, "mes": m, "codigo": int(c), "categoria": "salario", "valor": round(SUBSIDIO * frac, 2)})
            if a * 100 + m >= AUXILIO_DESDE:
                ganha_l.append({"ano": a, "mes": m, "codigo": int(c), "categoria": "auxilios", "valor": round(AUXILIO * frac, 2)})
    ganha = pd.DataFrame(ganha_l, columns=["ano", "mes", "codigo", "categoria", "valor"])

    # custeio: despesas por tipo, sem fornecedor
    despesas = None
    if itens is not None and len(itens):
        cod_custeio = {i: codigo_de(n) for i, n in zip(itens.id_custeio, itens.nome)}
        if totais is not None:
            cod_custeio.update({i: codigo_de(n) for i, n in zip(totais.id_custeio, totais.nome) if i not in cod_custeio})
        d = itens.assign(codigo=itens.id_custeio.map(cod_custeio), tipo=itens.despesa.map(_tipo), fornecedor="", cnpj_cpf="")
        if totais is not None and len(totais):
            # o total de cada vereador no mês é o da lista; se o detalhe não fechar com ele, a diferença entra sem tipo
            soma = d.groupby(["ano", "mes", "id_custeio"]).valor.sum()
            difs = []
            for r in totais.itertuples():
                x = round(float(r.total) - float(soma.get((r.ano, r.mes, r.id_custeio), 0.0)), 2)
                if abs(x) >= 0.01:
                    difs.append({"ano": r.ano, "mes": r.mes, "id_custeio": r.id_custeio, "nome": r.nome, "codigo": cod_custeio.get(r.id_custeio),
                                 "tipo": "Outros (sem detalhe)", "fornecedor": "", "cnpj_cpf": "", "valor": x})
            if difs:
                log(f"  Belo Horizonte: custeio com detalhe incompleto em {len(difs)} vereador × mês")
                d = pd.concat([d, pd.DataFrame(difs)], ignore_index=True)
        sem = sorted(set(d.nome[~d.codigo.isin(interv)]))
        if sem:
            log(f"  Belo Horizonte: no custeio e não na presença: {', '.join(sem)}")
        despesas = d[d.codigo.isin(interv)].astype({"codigo": int})[["ano", "mes", "codigo", "tipo", "fornecedor", "cnpj_cpf", "valor"]]

    notas = list(CFG["notas"])
    # quem some da lista por um mês inteiro, sem suplente no lugar (licença curta): fica fora do cargo naquele mês
    lista_de = {am: set(g.codigo) for am, g in pres[pres.aaaamm.isin(publicados)].groupby("aaaamm")}
    sumidos = [(am, c) for k, am in enumerate(publicados[1:-1], 1) for c in (lista_de[publicados[k - 1]] & lista_de[publicados[k + 1]]) - lista_de[am]
               if len(no_cargo_em(date(am // 100, am % 100, monthrange(am // 100, am % 100)[1]))) < CFG["vagas"]]
    if sumidos:
        nome_de = dict(zip(ver.codigo, ver.nome))
        quem = "; ".join(f"{nome_de.get(int(c), c)} em {am % 100:02d}/{am // 100}" for am, c in sumidos)
        notas.append(f"Quem passa um mês inteiro fora (licença) não aparece na lista daquele mês e fica fora do cargo aqui; "
                     f"nenhum suplente assumiu no lugar de: {quem}.")
    if ultimo_pub < ate:
        notas.append(f"A presença de {ate % 100:02d}/{ate // 100} ainda não foi publicada: vale quem estava no cargo em {ultimo_pub % 100:02d}/{ultimo_pub // 100}.")
    cfg = dict(CFG, ultimo_mes=ate, notas=notas)
    meta, pessoas = comum.montar(cfg, tipos, ver, mandatos_df, ganha=ganha, despesas=despesas)
    meta["subsidio_folha"] = False  # o contracheque aqui é o valor fixo da lei pelos dias no cargo, não a folha da Câmara
    return meta, pessoas


# Tipos de despesa do Custeio Parlamentar -> nomes curtos (os da Câmara são poucos e fixos)
_TIPOS_BH = [(r"INFORMATICA|TONER|CARTUCHO", "Material de informática"), (r"COPA|COZINHA", "Material de copa"),
             (r"CARIMBO", "Carimbos"), (r"POSTA|CORREIO", "Correios"), (r"TELEFON|CELULAR", "Telefone e internet")]


def _tipo(desc):
    d = normalizar_nome(desc)
    for padrao, nome in _TIPOS_BH:
        if re.search(padrao, d):
            return nome
    return comum.tipo_curto(desc)
