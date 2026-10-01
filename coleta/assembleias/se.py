"""Assembleia Legislativa de Sergipe (Alese): deputado estadual por deputado estadual.

Fontes (Portal da Transparência da Alese, sem cadastro):
- Folha de pagamento, um PDF por mês ("Detalhamento da folha de pagamento", com texto):
  https://al.se.leg.br/portal-da-transparencia/recursos-humanos/subsidio-e-remuneracoes/. Dele saem os rendimentos de
  cada deputado (subsídio, "outras verbas", 13º, férias, auxílios; sem descontos nem líquido) e, para cada gabinete, quantas
  pessoas estão lotadas e quanto recebem no total (sem guardar nomes). Quem está no cargo: quem está na folha do mês.
- Ressarcimento dos deputados, um PDF por mês de pagamento (por deputado e categoria, sem fornecedor):
  https://al.se.leg.br/portal-da-transparencia/despesas/ressarcimento-dos-deputados/
- Nome completo, gênero e eleito/suplente: TSE (eleição de 2022); partido: candidatura de 2026 no TSE. O nome
  parlamentar vem da lotação do gabinete na folha ("GABINETE DO DEPUTADO PATO MARAVILHA").
"""
import difflib
import html as H
import re
import subprocess
import tempfile
import time

import pandas as pd

from ..config import CACHE, DADOS
from ..prefeituras.comum import feminino, num
from ..util import TempoEsgotado, _sessao, dormir, log, normalizar_nome, verificar_prazo
from ..vereadores import comum as vc
from . import comum, se_folha

UF = "SE"
COD = comum.CODIGOS_UF[UF]
INICIO = 202501
SITE = "https://al.se.leg.br"
PAG_FOLHA = f"{SITE}/portal-da-transparencia/recursos-humanos/subsidio-e-remuneracoes/"
PAG_VERBA = f"{SITE}/portal-da-transparencia/despesas/ressarcimento-dos-deputados/"
PASTA = DADOS / "assembleias" / "se"
C = CACHE / "assembleias" / "se"
MESES = {m: i + 1 for i, m in enumerate(["JANEIRO", "FEVEREIRO", "MARCO", "ABRIL", "MAIO", "JUNHO", "JULHO", "AGOSTO", "SETEMBRO",
                                          "OUTUBRO", "NOVEMBRO", "DEZEMBRO"])}
CFG = {
    "cod": COD, "n": "Sergipe", "uf": UF, "casa": "Assembleia Legislativa de Sergipe", "vagas": 24, "inicio": INICIO,
    "id_prefixo": "est", "k": "e", "cargo": ("Deputada estadual", "Deputado estadual"),
    "subsidio": [[202402, 33006.39], [202502, 34774.64]],
    "subsidio_folha": True,
    "salario_nota": ("Valores da folha de pagamento da Alese (rendimentos, sem descontos). Além do subsídio, a folha paga aos deputados "
                     "\"outras verbas\" (R$ 10.432,39 por mês em 2026, 30% do subsídio) e um auxílio de R$ 1.200; a folha não diz o que são "
                     "as \"outras verbas\"."),
    "verba_nome": "Ressarcimento de despesas do mandato",
    "verba_regra": "Reembolso de despesas do mandato com nota fiscal, por categoria (artigo 4º do ato que regula a verba).",
    "verba_notas": ["A Alese publica o ressarcimento por deputado e categoria, sem fornecedor nem CNPJ. O mês é o da competência das notas "
                    "(o pagamento sai no mês seguinte)."],
    "equipe_nota": ("Equipe: servidores lotados no gabinete do deputado na folha do mês e a soma dos rendimentos deles (antes dos descontos). "
                    "Não inclui quem trabalha para o deputado lotado em outro setor: o Gabinete da Presidência, as lideranças e a Mesa ficam de fora."),
    "pagina": f"{SITE}/deputados/",
    "notas": ["Quem está no cargo hoje: quem está na folha do último mês publicado. Desde quando: os meses na folha.",
              "Partido: o da candidatura de 2026 no TSE. Quem não é candidato em 2026 aparece sem partido."],
    "fontes": {"folha": PAG_FOLHA, "verba": PAG_VERBA},
}


def _get(url, **kw):
    verificar_prazo()
    for tentativa in range(3):
        try:
            r = _sessao().get(url, timeout=300, **kw)
            r.raise_for_status()
            dormir(2)
            return r
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 2:
                raise
            dormir(20)


def _arquivos(pagina):
    """Página da Alese -> {aaaamm: link do PDF}. A página tem um título por ano e uma aba por mês, com o pacote de download."""
    t = _get(pagina).text
    saida, ano, mes = {}, None, None
    for m in re.finditer(r'elementor-tab-mobile-title[^>]*>([^<]+)<|data-downloadurl="([^"]+)"|<h[1-4][^>]*class="elementor-heading-title[^>]*>([^<]+)<', t):
        if m.group(3) and re.fullmatch(r"\s*\d{4}\s*", m.group(3)):
            ano, mes = int(m.group(3)), None
        elif m.group(1):
            mes = MESES.get(normalizar_nome(m.group(1)))
        elif m.group(2) and ano and mes and ano * 100 + mes not in saida:
            url = H.unescape(m.group(2))
            saida[ano * 100 + mes] = re.sub(r"&refresh=[^&]*", "", url)
    return saida


def _pdf(tipo, am, url, recente):
    arq = C / "pdf" / f"{tipo}_{am}.pdf"
    if arq.exists() and not (recente and time.time() - arq.stat().st_mtime > 7 * 86400):
        return arq, False
    b = _get(url).content
    if not b.startswith(b"%PDF"):
        raise RuntimeError(f"{tipo} {am}: o download não é um PDF")
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_bytes(b)
    return arq, True


ITEM = re.compile(r"^\s*(\d+)\s+(.+?)\s+R\$\s*(-?[\d.]+,\d{2})\s*$")


def _ressarcimento(b):
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(b)
        f.flush()
        texto = subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, text=True).stdout
    linhas, dep, comp, soma, problemas = [], None, None, 0.0, []
    for l in texto.splitlines():
        m = re.search(r"Deputad[oa]:\s*(.+?)\s{2,}Compet[eê]ncia:\s*(\d{2})/(\d{4})", l)
        if m:
            dep, comp, soma = " ".join(m.group(1).split()), int(m.group(3)) * 100 + int(m.group(2)), 0.0
            continue
        m = ITEM.match(l)
        if m and dep:
            v = num(m.group(3))
            soma += v
            linhas.append({"deputado": dep, "competencia": comp, "item": int(m.group(1)), "descricao": " ".join(m.group(2).split()), "valor": v})
            continue
        m = re.search(r"Total:\s*R\$\s*(-?[\d.]+,\d{2})", l)
        if m and dep and abs(num(m.group(1)) - soma) >= 0.01:
            problemas.append(f"{dep} {comp}: total {m.group(1)} e itens {soma:.2f}")
    return linhas, problemas


def coletar():
    PASTA.mkdir(parents=True, exist_ok=True)
    hoje = time.localtime()
    limite = hoje.tm_year * 100 + hoje.tm_mon
    folhas = {am: u for am, u in _arquivos(PAG_FOLHA).items() if INICIO <= am < limite}
    verbas = {am: u for am, u in _arquivos(PAG_VERBA).items() if INICIO <= am < limite}
    arq_d, arq_g, arq_v = PASTA / "folha_deputados.csv", PASTA / "gabinetes.csv", PASTA / "ressarcimento.csv"
    dep = pd.read_csv(arq_d) if arq_d.exists() else pd.DataFrame(columns=["ano", "mes"])
    gab = pd.read_csv(arq_g) if arq_g.exists() else pd.DataFrame(columns=["ano", "mes"])
    ver = pd.read_csv(arq_v) if arq_v.exists() else pd.DataFrame(columns=["pagamento"])
    feitos_f = set(dep.ano * 100 + dep.mes) if len(dep) else set()
    feitos_v = set(ver.pagamento) if len(ver) else set()
    try:
        for am, url in sorted(folhas.items()):
            arq, novo = _pdf("folha", am, url, am >= max(folhas) - 1)
            if not novo and am in feitos_f:
                continue
            d, g, n = se_folha.ler(arq.read_bytes())
            if len(d) < 20:
                log(f"  Alese: folha de {am % 100:02d}/{am // 100} com só {len(d)} deputados em {n} registros; fica de fora")
                continue
            dep = pd.concat([dep[(dep.ano * 100 + dep.mes) != am], pd.DataFrame([{"ano": am // 100, "mes": am % 100, **x} for x in d])])
            gab = pd.concat([gab[(gab.ano * 100 + gab.mes) != am],
                             pd.DataFrame([{"ano": am // 100, "mes": am % 100, "lotacao": k, "pessoas": p, "rendimentos": round(v, 2)} for k, (p, v) in g.items()])])
            feitos_f.add(am)
        for am, url in sorted(verbas.items()):
            arq, novo = _pdf("ressarcimento", am, url, am >= max(verbas) - 1)
            if not novo and am in feitos_v:
                continue
            linhas, problemas = _ressarcimento(arq.read_bytes())
            for p in problemas:
                log(f"  Alese, ressarcimento pago em {am % 100:02d}/{am // 100}: {p}")
            ver = pd.concat([ver[ver.pagamento != am], pd.DataFrame([{"pagamento": am, **x} for x in linhas])])
            feitos_v.add(am)
    finally:
        if len(dep):
            dep.sort_values(["ano", "mes", "nome"]).to_csv(arq_d, index=False)
            gab.sort_values(["ano", "mes", "lotacao"]).to_csv(arq_g, index=False)
        if len(ver):
            ver.sort_values(["pagamento", "item"]).to_csv(arq_v, index=False)
        log(f"  Alese: {len(feitos_f)} folhas e {len(feitos_v)} ressarcimentos desde {INICIO % 100:02d}/{INICIO // 100}")


_TIPOS = [(r"COMBUST|LUBRIFIC", "Combustível e manutenção de veículos"), (r"LOCA[CÇ][AÃ]O DE VE[IÍ]C", "Aluguel de carros"),
          (r"CONSULTORIA|ASSESSORIA|PESQUISA", "Consultorias e assessorias"), (r"IM[OÓ]VEL|ESCRIT[OÓ]RIO", "Escritório (aluguel e contas)"),
          (r"DIVULGA|PUBLICIDADE|M[IÍ]DIA|COMUNICA", "Divulgação do mandato"), (r"GR[AÁ]FIC|IMPRESS", "Material gráfico (arte e impressão)"),
          (r"TELEF|INTERNET", "Telefone e internet"), (r"PASSAGE|A[EÉ]RE", "Passagens"), (r"HOSPEDA|HOTEL|DI[AÁ]RIA", "Hospedagem e diárias"),
          (r"ALIMENTA|REFEI", "Alimentação"), (r"MATERIA(L|IS) DE (ESCRIT|CONSUMO|EXPEDIENTE)", "Material de escritório")]


def _tipo(descricao):
    u = re.sub(r"^ART\.?\s*\d+\S*\s+[IVXLC]+\s*-\s*", "", normalizar_nome(descricao))
    for rx, nome in _TIPOS:
        if re.search(rx, u):
            return nome
    return (u[:1] + u[1:].lower()) if u else "Outras despesas"


def _parlamentar(lotacao):
    return re.sub(r"^GABINETE D[OA] DEPUTAD[OA]\s+", "", normalizar_nome(lotacao)).strip()


def montar(tipos):
    arq_d = PASTA / "folha_deputados.csv"
    if not arq_d.exists():
        return None
    dep = pd.read_csv(arq_d).fillna("")
    gab = pd.read_csv(PASTA / "gabinetes.csv").fillna("") if (PASTA / "gabinetes.csv").exists() else pd.DataFrame(columns=["ano", "mes", "lotacao", "pessoas", "rendimentos"])
    ver = pd.read_csv(PASTA / "ressarcimento.csv").fillna("") if (PASTA / "ressarcimento.csv").exists() else pd.DataFrame(columns=["pagamento", "deputado", "competencia", "descricao", "valor"])
    tse = comum.tse_2022(UF)
    por_civil = {normalizar_nome(v["nome"]): v for v in tse.values()}
    partidos = comum.partido_2026(UF)
    ultimo = vc.ultimo_mes_fechado()
    ultimo_dado = int((dep.ano * 100 + dep.mes).max())
    pessoas, cod_nome, cod_gab, parl = [], {}, {}, {}
    ganha, mandatos = [], []
    for nome, g in dep.groupby("nome"):
        g = g.sort_values(["ano", "mes"])
        lot_dep = [x for x in g.lotacao if re.match(r"GABINETE D[OA] DEPUTAD[OA]\b", normalizar_nome(x))] or list(g.lotacao)
        p = _parlamentar(lot_dep[-1])
        t = por_civil.get(normalizar_nome(nome)) or comum.achar(p, tse) or comum.achar(nome, por_civil) or {}
        codigo = comum.codigo_de(nome, t)
        cod_nome[nome] = codigo
        for lot in g.lotacao.unique():
            if re.match(r"GABINETE D[OA] DEPUTAD[OA]\b", normalizar_nome(lot)):  # o Gabinete da Presidência não é o gabinete do deputado
                cod_gab[normalizar_nome(lot)] = codigo
                parl[_parlamentar(lot)] = codigo
        urna = t.get("urna", "")
        bruto = re.sub(r"^GABINETE D[OA] DEPUTAD[OA]\s+", "", " ".join(lot_dep[-1].split()), flags=re.I)
        pessoas.append({"codigo": codigo, "nome": vc.titulo(bruto) or vc.titulo(urna) or vc.titulo(nome),
                        "nome_civil": vc.titulo(t.get("nome") or nome), "partido": partidos.get(normalizar_nome(t.get("nome") or nome), ""),
                        "genero": t.get("genero") or ("F" if "DEPUTADA" in normalizar_nome(g.lotacao.iloc[-1]) or feminino(nome) else "M"),
                        "eleito": t.get("eleito", ""), "pagina": CFG["pagina"]})
        for r in g.itertuples():
            outros = r.c02 + r.c03 + r.c05 + r.c06 + r.c07 + r.c08
            resto = round(r.c10 - (r.c01 + r.c04 + r.c09 + outros), 2)
            for cat, v in (("salario", r.c01), ("decimo_terceiro", r.c04), ("auxilios", r.c09), ("outros_rendimentos", outros + resto)):
                if abs(v) >= 0.005:
                    ganha.append({"ano": r.ano, "mes": r.mes, "codigo": codigo, "categoria": cat, "valor": round(v, 2)})
        meses_g = sorted(set(g.ano * 100 + g.mes))
        per = comum.periodos(meses_g, ultimo_dado, ultimo, folga=1)
        if meses_g[-1] < ultimo_dado:
            per = [(i, f or f"{meses_g[-1] // 100}-{meses_g[-1] % 100:02d}-28") for i, f in per]
        for i, f in per:
            mandatos.append({"codigo": codigo, "inicio": i, "fim": f})
    # verba: o nome do ressarcimento é o nome parlamentar ("Kitty Lima"), o mesmo da lotação do gabinete
    chaves = list(parl)

    def de_quem(n):
        u = normalizar_nome(n)
        if u in parl:
            return parl[u]
        t = comum.achar(n, tse)
        if t and comum.codigo_de("", t) in cod_nome.values():
            return comum.codigo_de("", t)
        perto = difflib.get_close_matches(u, chaves, n=1, cutoff=0.8)
        return parl[perto[0]] if perto else None

    desp = pd.DataFrame(columns=["ano", "mes", "codigo", "tipo", "fornecedor", "cnpj_cpf", "valor"])
    if len(ver):
        quem = {n: de_quem(n) for n in ver.deputado.unique()}
        # o nome do ressarcimento tem maiúsculas e acentos ("Luizão Donatrampi"): é o que aparece no site
        for n, c in quem.items():
            for x in pessoas:
                if x["codigo"] == c:
                    x["nome"] = n
        sem = sorted(n for n, c in quem.items() if c is None and ver[ver.deputado == n].competencia.max() >= INICIO)
        if sem:
            log(f"  Alese: ressarcimento sem deputado na folha: {', '.join(sem)}")
        v = ver.assign(codigo=ver.deputado.map(quem)).dropna(subset=["codigo"])
        desp = pd.DataFrame({"ano": v.competencia // 100, "mes": v.competencia % 100, "codigo": v.codigo.astype(int), "tipo": v.descricao.map(_tipo),
                             "fornecedor": "", "cnpj_cpf": "", "valor": v.valor})
    eq = gab.assign(codigo=gab.lotacao.map(lambda x: cod_gab.get(normalizar_nome(x)))).dropna(subset=["codigo"])
    equipe = pd.DataFrame({"ano": eq.ano, "mes": eq.mes, "codigo": eq.codigo.astype(int), "pessoas": eq.pessoas, "custo": eq.rendimentos})
    cfg = dict(CFG, ultimo_mes=min(ultimo, ultimo_dado))
    return vc.montar(cfg, tipos, pd.DataFrame(pessoas), pd.DataFrame(mandatos), ganha=pd.DataFrame(ganha), despesas=desp, equipe=equipe)
