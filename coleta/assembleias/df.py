"""Câmara Legislativa do Distrito Federal (CLDF): deputado distrital por deputado distrital.

Fontes (só abrem de dentro do Brasil, então este robô roda no Mac):
- Folha: o "Quadro demonstrativo de pessoal mensal" dos dados abertos da CLDF (CKAN), um CSV por mês, com tipo, cargo e
  lotação de cada deputado e servidor: https://dados.cl.df.gov.br/dataset/quadro-demonstrativo-de-pessoal-mensal. Dele
  saem os rendimentos de cada deputado (subsídio, 13º, auxílios, acertos; nunca IRRF, seguridade, outros descontos ou
  líquido) e, para cada gabinete ("GABINETE DO DEPUTADO ..."), quantas pessoas recebem e a soma dos rendimentos delas
  (sem nomes). Quem está no cargo: quem está na folha do mês como deputado.
- Verba indenizatória: o "Quadro demonstrativo" consolidado de cada mês (PDF assinado, com o valor de cada deputado por
  categoria), https://www.cl.df.gov.br/web/portal-transparencia/quadro-demonstrativo. As notas fiscais em XLSX dos dados
  abertos (dataset verbas-indenizatorias) cobrem só parte dos gabinetes, trazem o CPF do deputado e não dizem o mês da
  prestação de contas: não são usadas.
- Nome completo, gênero e eleito/suplente: TSE (eleição de 2022); partido: candidatura de 2026 no TSE.
O robots.txt de dados.cl.df.gov.br proíbe só /api/ (os arquivos são achados pela página do conjunto de dados, com os 10 s
de pausa que ele pede); o de www.cl.df.gov.br proíbe só /web/guest/search.
"""
import html as H
import io
import re
import subprocess
import tempfile
import time

import pandas as pd

from ..config import DADOS
from ..prefeituras.comum import feminino
from ..util import TempoEsgotado, _sessao, dormir, log, normalizar_nome, recursos_ckan, verificar_prazo
from ..vereadores import comum as vc
from . import comum

UF = "DF"
COD = comum.CODIGOS_UF[UF]
INICIO = 202501
DADOS_ABERTOS = "https://dados.cl.df.gov.br"
CONJ_FOLHA = f"{DADOS_ABERTOS}/dataset/quadro-demonstrativo-de-pessoal-mensal"
PORTAL = "https://www.cl.df.gov.br/web/portal-transparencia"
PAG_VERBA = f"{PORTAL}/quadro-demonstrativo"
PASTA = DADOS / "assembleias" / "df"
CFG = {
    "cod": COD, "n": "Distrito Federal", "uf": UF, "casa": "Câmara Legislativa do Distrito Federal", "vagas": 24, "inicio": INICIO,
    "id_prefixo": "est", "k": "e", "cargo": ("Deputada distrital", "Deputado distrital"),
    "subsidio": [[202402, 33006.39], [202502, 34774.64]],
    "subsidio_folha": True,
    "salario_nota": ("Valores da folha da CLDF (quadro demonstrativo de pessoal mensal): subsídio, 13º, auxílio-alimentação, auxílio "
                     "pré-escolar e acertos de meses anteriores, sem descontos. O subsídio é de 75% do subsídio do deputado federal "
                     "(Decreto Legislativo 2.383/2022): R$ 34.774,64 desde fev/2025. O arquivo de fev/2026 nos dados abertos é uma cópia "
                     "do de jun/2025; nesse mês vale o subsídio da lei."),
    "verba_nome": "Verba indenizatória",
    "verba_mes": {"2025": 20864.78, "2026": 20864.78},
    "verba_regra": ("Reembolso de despesas do gabinete com nota fiscal, até 60% do subsídio por mês; o saldo não usado passa para o mês "
                    "seguinte dentro do bimestre (Atos da Mesa Diretora 197/2024 e 144/2025)."),
    "verba_notas": ["A CLDF publica um quadro mensal consolidado com o valor de cada deputado por categoria (imóvel, veículo, combustível, "
                    "consultorias, divulgação...), sem fornecedor. O quadro é provisório e pode ser retificado; quem não tem valor no mês "
                    "aparece no quadro com asterisco (\"não foram computados valores\").",
                    "Em alguns meses, a soma das categorias de um deputado no quadro é diferente do total do quadro; aqui vale o total, e a "
                    "diferença aparece como \"Diferença entre o total e as categorias no quadro\"."],
    "equipe_nota": ("Equipe: pessoas lotadas no gabinete do deputado (\"Gabinete do Deputado ...\") com algum rendimento na folha do mês e a "
                    "soma desses rendimentos, antes dos descontos. Não inclui quem trabalha para o deputado lotado em outro setor (Mesa "
                    "Diretora, Presidência, lideranças)."),
    "pagina": "https://www.cl.df.gov.br/deputados",
    "notas": ["Quem está no cargo: quem está na folha do mês como deputado distrital. Desde quando: os meses na folha.",
              "Partido: o da candidatura de 2026 no TSE. Quem não é candidato em 2026 aparece sem partido."],
    "fontes": {"folha": CONJ_FOLHA, "verba": PAG_VERBA},
}

# colunas de rendimentos do CSV da folha (as de desconto e o líquido não são lidas)
RENDIMENTOS = {"Vencimentos, Subsidio ou Provento": "subsidio", "Remuneracao do Cargo em Comissao": "cargo_comissao",
               "Vantagens Periodicas e Eventuais": "vantagens_eventuais", "Vantagens Pessoais": "vantagens_pessoais",
               "Outros Creditos": "outros_creditos", "Redutor Remuneracao": "redutor", "Auxílio Pré-escolar": "aux_preescolar",
               "Auxílio Transporte": "aux_transporte", "Auxílio Alimentação": "aux_alimentacao"}
LIDAS = ["Matrícula", "Nome", "Tipo", "Cargo Efetivo", "Cargo em Comissão/Função", "Lotação", "Tipo Lotação", "Folha", *RENDIMENTOS]
GABINETE = re.compile(r"^GABINETE D[OA] DEPUTAD[OA]\s+")
MESES = {m: i + 1 for i, m in enumerate(["JANEIRO", "FEVEREIRO", "MARCO", "ABRIL", "MAIO", "JUNHO", "JULHO", "AGOSTO", "SETEMBRO",
                                          "OUTUBRO", "NOVEMBRO", "DEZEMBRO"])}


def _get(url, pausa=2, **kw):
    verificar_prazo()
    for tentativa in range(3):
        try:
            r = _sessao().get(url, timeout=180, **kw)
            r.raise_for_status()
            dormir(pausa)
            return r
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 2:
                raise
            dormir(20)


def _meses():
    h = time.localtime()
    return [a * 100 + m for a in range(INICIO // 100, h.tm_year + 1) for m in range(1, 13) if INICIO <= a * 100 + m < h.tm_year * 100 + h.tm_mon]


def _ler_csv(b):
    """CSV da folha -> DataFrame só com as colunas lidas. Alguns meses vêm com a linha do cabeçalho inteira entre aspas."""
    t = b.decode("utf-8-sig", errors="replace")
    cab, _, resto = t.partition("\n")
    if cab.startswith('"') and cab.rstrip().endswith('"') and "Matr" in cab and cab.count('","') == 0:
        cab = cab.strip().strip('"').replace('""', '"')
    d = pd.read_csv(io.StringIO(cab + "\n" + resto), dtype=str, keep_default_na=False)
    d.columns = [c.strip() for c in d.columns]
    faltam = [c for c in LIDAS if c not in d.columns]
    if faltam:
        raise ValueError(f"colunas que faltam no CSV: {faltam}")
    d = d[LIDAS].copy()
    for c in RENDIMENTOS:
        d[c] = pd.to_numeric(d[c].str.replace(",", ".", regex=False), errors="coerce").fillna(0.0)
    d["rendimentos"] = d[list(RENDIMENTOS)].sum(axis=1).round(2)
    return d


def _resumo_folha(d, am):
    """-> (deputados, gabinetes, cargos): só o que o site usa, sem descontos nem nomes de servidores."""
    a, m = divmod(am, 100)
    eh_dep = (d.Tipo.str.upper() == "DEPUTADO") | d["Cargo em Comissão/Função"].str.upper().str.startswith("DEPUTAD")
    dep = d[eh_dep]
    deputados = [{"ano": a, "mes": m, "matricula": r["Matrícula"], "nome": r.Nome.strip(), "lotacao": " ".join(r["Lotação"].split()),
                  "folha": r.Folha.strip(), **{RENDIMENTOS[c]: round(r[c], 2) for c in RENDIMENTOS}} for _, r in dep.iterrows()]
    serv = d[~eh_dep & d["Lotação"].map(lambda x: bool(GABINETE.match(normalizar_nome(x))))]
    por = serv.groupby(["Lotação", "Matrícula"]).agg(rend=("rendimentos", "sum"), cargo=("Cargo em Comissão/Função", "first"),
                                                     efetivo=("Cargo Efetivo", "first")).reset_index()
    por = por[por.rend > 0.005]
    gabinetes = [{"ano": a, "mes": m, "lotacao": " ".join(l.split()), "pessoas": int(len(g)), "rendimentos": round(float(g.rend.sum()), 2)}
                 for l, g in por.groupby("Lotação")]
    por["cargo"] = [c.strip() or e.strip() or "Sem cargo informado" for c, e in zip(por.cargo, por.efetivo)]
    cargos = [{"ano": a, "mes": m, "lotacao": " ".join(l.split()), "cargo": c, "pessoas": int(n)}
              for (l, c), n in por.groupby(["Lotação", "cargo"]).size().items()]
    return deputados, gabinetes, cargos


def _assinatura(deputados):
    """Para achar o mesmo arquivo publicado em dois meses (o de fev/2026 é uma cópia do de jun/2025)."""
    return "|".join(sorted(f"{x['matricula']};{x['folha']};" + ";".join(f"{x[k]:.2f}" for k in RENDIMENTOS.values()) for x in deputados))


def _coletar_folha(meses):
    arq_d, arq_g, arq_c, arq_m = PASTA / "folha_deputados.csv", PASTA / "gabinetes.csv", PASTA / "gabinete_cargos.csv", PASTA / "folha_meses.csv"
    dep = pd.read_csv(arq_d, dtype={"matricula": str}) if arq_d.exists() else pd.DataFrame(columns=["ano", "mes", "matricula"])
    gab = pd.read_csv(arq_g) if arq_g.exists() else pd.DataFrame(columns=["ano", "mes", "lotacao"])
    car = pd.read_csv(arq_c) if arq_c.exists() else pd.DataFrame(columns=["ano", "mes", "lotacao"])
    lid = pd.read_csv(arq_m).fillna("") if arq_m.exists() else pd.DataFrame(columns=["ano", "mes", "url", "situacao", "lido_em"])
    recursos = {}
    for x in recursos_ckan(CONJ_FOLHA):
        m = re.fullmatch(r"\s*(\d{4})-(\d{1,2})\s*", x["name"])
        if m and x["url"].lower().split("?")[0].endswith(".csv"):
            recursos.setdefault(int(m.group(1)) * 100 + int(m.group(2)), x["url"])
    hoje = time.strftime("%Y-%m-%d")
    ja = {int(a) * 100 + int(m_): (u, s, l) for a, m_, u, s, l in zip(lid.ano, lid.mes, lid.url, lid.situacao, lid.lido_em)}
    assinaturas = {}
    novos = 0
    try:
        for am in meses:
            url = recursos.get(am)
            if not url:
                continue
            antes = ja.get(am)
            if antes and antes[0] == url and (am < meses[-2] or antes[2] == hoje):
                continue
            b = _get(url, pausa=0).content
            d, g, c = _resumo_folha(_ler_csv(b), am)
            # o nome do arquivo diz o mês ("qdp-2026-08.csv", "qdp202506-1.csv"): se for de outro mês, é cópia
            nome = url.rsplit("/", 1)[-1]
            mm = re.search(r"(20\d{2})[-_]?(\d{2})(?!\d)", nome)
            outro = mm and int(mm.group(1)) * 100 + int(mm.group(2)) != am
            assin = _assinatura(d)
            if not assinaturas:
                for (a2, m2), g2 in dep.groupby(["ano", "mes"]):
                    assinaturas[_assinatura(g2.to_dict("records"))] = int(a2) * 100 + int(m2)
            repetido = assinaturas.get(assin)
            situacao = "ok"
            if outro or (repetido and repetido != am) or len({x["matricula"] for x in d}) < 20:
                situacao = (f"cópia do arquivo de {mm.group(2)}/{mm.group(1)}" if outro else
                            f"igual ao de {repetido % 100:02d}/{repetido // 100}" if repetido and repetido != am else "sem deputados")
                log(f"  CLDF: folha de {am % 100:02d}/{am // 100} fica de fora ({situacao})")
                d, g, c = [], [], []
            else:
                assinaturas[assin] = am
            fora = lambda df: df[(df.ano.astype(int) * 100 + df.mes.astype(int)) != am] if len(df) else df
            dep = pd.concat([fora(dep), pd.DataFrame(d)]) if d else fora(dep)
            gab = pd.concat([fora(gab), pd.DataFrame(g)]) if g else fora(gab)
            car = pd.concat([fora(car), pd.DataFrame(c)]) if c else fora(car)
            lid = pd.concat([lid[(lid.ano.astype(int) * 100 + lid.mes.astype(int)) != am],
                             pd.DataFrame([{"ano": am // 100, "mes": am % 100, "url": url, "situacao": situacao, "lido_em": hoje}])])
            novos += 1
            dormir(1)
    finally:
        if novos:
            dep.sort_values(["ano", "mes", "nome", "folha"]).to_csv(arq_d, index=False)
            gab.sort_values(["ano", "mes", "lotacao"]).to_csv(arq_g, index=False)
            car.sort_values(["ano", "mes", "lotacao", "cargo"]).to_csv(arq_c, index=False)
            lid.sort_values(["ano", "mes"]).to_csv(arq_m, index=False)
        log(f"  CLDF: folha de {novos} meses lida agora; {len(set(zip(dep.ano, dep.mes)))} meses com deputados")


# ---------------------------------------------------------------- verba (quadro demonstrativo em PDF)
PALAVRA = re.compile(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>')
DINHEIRO = re.compile(r"^-?\d{1,3}(?:\.\d{3})*[,.]\d{2}$")  # "1.225.41" (ponto no lugar da vírgula) aparece no quadro de jan/2025
COLUNAS = {"IMÓVEL": "imovel", "EQUIPAMENTO": "equipamento", "MATERIAIS": "materiais", "VEÍCULO": "veiculo", "LUBRIFICANTE": "combustivel",
           "JURÍDICA": "juridica", "ESPECIALIZADA": "especializada", "PARLAMENTAR": "divulgacao", "OUTROS": "outros", "GLOSA": "glosa",
           "TOTAL": "total"}
TIPOS = {"imovel": "Escritório (aluguel e contas)", "equipamento": "Aluguel de móveis e equipamentos", "materiais": "Material de escritório",
         "veiculo": "Aluguel de carros", "combustivel": "Combustível", "juridica": "Consultoria jurídica",
         "especializada": "Consultorias e assessorias", "divulgacao": "Divulgação do mandato", "outros1": "Outras despesas",
         "outros2": "Outras despesas", "glosa": "Glosa (valor não reembolsado)", "ajuste": "Diferença entre o total e as categorias no quadro"}


def _centavos(t):
    return int(re.sub(r"\D", "", t)) / 100 * (-1 if t.startswith("-") else 1)


def _palavras_pdf(b):
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(b)
        f.flush()
        saida = subprocess.run(["pdftotext", "-bbox", f.name, "-"], capture_output=True, text=True).stdout
    for pag in saida.split("<page ")[1:]:
        yield [(float(a), float(b_), float(c), float(d), H.unescape(t)) for a, b_, c, d, t in PALAVRA.findall(pag)]


def _quadro(b):
    """PDF do quadro demonstrativo -> (aaaamm do título, [(nome no quadro, {coluna: valor})]). O nome do deputado ocupa uma a
    quatro linhas na primeira coluna; a linha de valores fica no meio do bloco do nome. Os blocos são separados pelo espaço
    entre as linhas (o espaço entre dois deputados é maior que o espaço entre duas linhas do mesmo nome)."""
    cols, saida, xnome, titulo = None, [], None, None
    for w in _palavras_pdf(b):
        if titulo is None:
            txt = " ".join(t for *_, t in sorted(w, key=lambda p: (round(p[1]), p[0]))[:60])
            m = re.search(r"(JANEIRO|FEVEREIRO|MARÇO|ABRIL|MAIO|JUNHO|JULHO|AGOSTO|SETEMBRO|OUTUBRO|NOVEMBRO|DEZEMBRO)\s*-\s*(20\d{2})", txt)
            if m:
                titulo = int(m.group(2)) * 100 + MESES[normalizar_nome(m.group(1))]
        cab = [(x0, x1, y0, t) for x0, y0, x1, y1, t in w if (t in COLUNAS or t == "DEPUTADO") and y0 < 250]
        if any(t == "DEPUTADO" for *_, t in cab) and any(t == "GLOSA" for *_, t in cab):
            cols, outros = [], 0
            for x0, x1, y0, t in sorted(cab):
                if t == "DEPUTADO":
                    continue
                k = COLUNAS[t]
                if k == "outros":
                    outros += 1
                    k = f"outros{outros}"
                cols.append(((x0 + x1) / 2, k))
            xnome = min(x for x, _ in cols) - 15
            topo = max(y0 for _, _, y0, _ in cab) + 6
        elif cols is None:
            continue
        else:
            topo = 0
        nota = [y0 for x0, y0, x1, y1, t in w if t in ("(", "( ¹", "(¹") and y0 > topo + 10] + [y0 for x0, y0, x1, y1, t in w if t == "¹" and y0 > topo + 20]
        fim = min(nota + [1e9])
        corpo = [p for p in w if topo < p[1] < fim - 1]
        linhas = []
        for x0, y0, x1, y1, t in sorted(corpo, key=lambda p: (p[1], p[0])):
            if x1 >= xnome + 5 or DINHEIRO.match(t):
                continue
            if linhas and abs(y0 - linhas[-1]["y0"]) < 1.5:
                linhas[-1]["pal"].append(t)
                linhas[-1]["y1"] = max(linhas[-1]["y1"], y1)
            else:
                linhas.append({"y0": y0, "y1": y1, "pal": [t]})
        difs = [b_["y0"] - a["y0"] for a, b_ in zip(linhas, linhas[1:])]
        passo = min(difs) if difs else 0
        blocos = []
        for i, l in enumerate(linhas):
            if blocos and l["y0"] - linhas[i - 1]["y0"] <= passo * 1.04:
                blocos[-1]["pal"] += l["pal"]
                blocos[-1]["y1"] = l["y1"]
            else:
                blocos.append({"y0": l["y0"], "y1": l["y1"], "pal": list(l["pal"]), "v": {}})
        for x0, y0, x1, y1, t in corpo:
            if DINHEIRO.match(t) and x0 > xnome - 30 and blocos:
                b_ = min(blocos, key=lambda b_: abs((b_["y0"] + b_["y1"]) / 2 - (y0 + y1) / 2))
                k = min(cols, key=lambda c: abs(c[0] - (x0 + x1) / 2))[1]
                b_["v"][k] = round(b_["v"].get(k, 0.0) + _centavos(t), 2)
        saida += [(" ".join(b_["pal"]), b_["v"]) for b_ in blocos]
    return titulo, saida


def _pdfs_verba():
    """{aaaamm: (rótulo, url)} de todos os anos desde INICIO; quando o mês tem retificação, vale a última publicada (maior número)."""
    t = _get(PAG_VERBA).text
    pastas = re.findall(r'<option value="(\d+)"[^>]*>\s*(20\d{2})\s*</option>', t)
    classe = re.search(r'data-folder-class-pk="(\d+)"', t)
    saida, escolhido = {}, {}
    for pasta, ano in pastas:
        if int(ano) < INICIO // 100:
            continue
        pag = t if pasta == pastas[0][0] else _get(f"{PAG_VERBA}?classpk={classe.group(1)}&folderId={pasta}").text
        for url, rotulo in re.findall(r'<a href="(https://www\.cl\.df\.gov\.br/documents/[^"]+)"[^>]*>\s*<div[^>]*>\s*<p class="small">([^<]+)</p>', pag):
            m = re.match(r"\s*(\d+)\s*-\s*([A-Za-zçÇãõéêíóú]+)\s+(20\d{2})", H.unescape(rotulo))
            if not m or normalizar_nome(m.group(2)) not in MESES:
                continue
            am = int(m.group(3)) * 100 + MESES[normalizar_nome(m.group(2))]
            if am < INICIO:
                continue
            if am not in escolhido or int(m.group(1)) > escolhido[am]:
                escolhido[am] = int(m.group(1))
                saida[am] = (" ".join(H.unescape(rotulo).split()), H.unescape(url))
    return saida


def _coletar_verba(meses):
    arq_v, arq_p = PASTA / "verba_quadro.csv", PASTA / "verba_pdfs.csv"
    ver = pd.read_csv(arq_v) if arq_v.exists() else pd.DataFrame(columns=["ano", "mes", "deputado", "coluna", "valor"])
    pdfs = pd.read_csv(arq_p).fillna("") if arq_p.exists() else pd.DataFrame(columns=["ano", "mes", "rotulo", "url", "deputados", "sem_valores", "lido_em"])
    hoje = time.strftime("%Y-%m-%d")
    ja = {int(a) * 100 + int(m): (u, l) for a, m, u, l in zip(pdfs.ano, pdfs.mes, pdfs.url, pdfs.lido_em)}
    lidos = 0
    try:
        for am, (rotulo, url) in sorted(_pdfs_verba().items()):
            if am not in meses:
                continue
            antes = ja.get(am)
            if antes and antes[0] == url and (am < meses[-2] or antes[1] == hoje):
                continue
            b = _get(url).content
            if not b.startswith(b"%PDF"):
                raise RuntimeError(f"verba de {am}: o download não é um PDF")
            titulo, linhas = _quadro(b)
            if titulo != am:
                log(f"  CLDF: o quadro da verba \"{rotulo}\" diz {titulo}; fica de fora")
                continue
            if len(linhas) < 20:
                raise RuntimeError(f"verba de {am}: só {len(linhas)} deputados no quadro (o leiaute mudou?)")
            novas = []
            for nome, v in linhas:
                tot = v.get("total", 0.0)
                soma = round(sum(x for k, x in v.items() if k not in ("total", "glosa")) - v.get("glosa", 0.0), 2)
                if v and abs(soma - tot) >= 0.01:
                    log(f"  CLDF, verba de {am % 100:02d}/{am // 100}: {nome}: categorias somam {soma:.2f} e o total é {tot:.2f}")
                    v = dict(v, ajuste=round(tot - soma, 2))
                for k, x in v.items():
                    novas.append({"ano": am // 100, "mes": am % 100, "deputado": nome, "coluna": k, "valor": x})
                if not v:
                    novas.append({"ano": am // 100, "mes": am % 100, "deputado": nome, "coluna": "", "valor": 0.0})
            resto = ver[(ver.ano * 100 + ver.mes) != am]
            ver = pd.concat([resto, pd.DataFrame(novas)]) if len(resto) else pd.DataFrame(novas)
            sem = sum(1 for n, v in linhas if not v)
            linha = pd.DataFrame([{"ano": am // 100, "mes": am % 100, "rotulo": rotulo, "url": url, "deputados": len(linhas), "sem_valores": sem, "lido_em": hoje}])
            resto = pdfs[(pdfs.ano * 100 + pdfs.mes) != am]
            pdfs = pd.concat([resto, linha]) if len(resto) else linha
            lidos += 1
    finally:
        if lidos:
            ver.sort_values(["ano", "mes", "deputado", "coluna"]).to_csv(arq_v, index=False)
            pdfs.sort_values(["ano", "mes"]).to_csv(arq_p, index=False)
        log(f"  CLDF: quadro da verba de {lidos} meses lido agora; {len(pdfs)} meses gravados")


def coletar():
    PASTA.mkdir(parents=True, exist_ok=True)
    try:  # de fora do Brasil os sites da CLDF não respondem: desiste logo (o site usa o que já está gravado)
        _sessao().get(CONJ_FOLHA, timeout=20).raise_for_status()
    except Exception as e:  # noqa: BLE001
        log(f"  CLDF: os dados abertos não abriram ({type(e).__name__}); fica o que já estava gravado (este robô roda no Brasil)")
        return
    meses = _meses()
    _coletar_folha(meses)
    _coletar_verba(meses)


# ---------------------------------------------------------------- montagem
def _parlamentar(lotacao):
    return GABINETE.sub("", normalizar_nome(lotacao)).strip()


def _chave(nome):
    t = re.sub(r"[*.]", " ", normalizar_nome(nome))
    t = re.sub(r"\bDRA\b", "DOUTORA", t)
    return " ".join(t.split())


def montar(tipos):
    arq_d = PASTA / "folha_deputados.csv"
    if not arq_d.exists():
        return None
    fol = pd.read_csv(arq_d, dtype={"matricula": str}).fillna({"lotacao": "", "folha": ""})
    gab = pd.read_csv(PASTA / "gabinetes.csv") if (PASTA / "gabinetes.csv").exists() else pd.DataFrame(columns=["ano", "mes", "lotacao", "pessoas", "rendimentos"])
    car = pd.read_csv(PASTA / "gabinete_cargos.csv") if (PASTA / "gabinete_cargos.csv").exists() else pd.DataFrame(columns=["ano", "mes", "lotacao", "cargo", "pessoas"])
    ver = pd.read_csv(PASTA / "verba_quadro.csv").fillna({"coluna": ""}) if (PASTA / "verba_quadro.csv").exists() else pd.DataFrame(columns=["ano", "mes", "deputado", "coluna", "valor"])
    lidos = pd.read_csv(PASTA / "folha_meses.csv").fillna("") if (PASTA / "folha_meses.csv").exists() else pd.DataFrame(columns=["ano", "mes", "situacao"])
    tse = comum.tse_2022(UF)
    por_civil = {normalizar_nome(v["nome"]): v for v in tse.values()}
    partidos = comum.partido_2026(UF)
    ultimo = vc.ultimo_mes_fechado()
    fol["am"] = fol.ano * 100 + fol.mes
    meses_folha = sorted(set(fol.am))
    ultimo_dado = int(max(meses_folha))
    # meses sem a folha certa (o arquivo de fev/2026 é cópia do de jun/2025): quem estava no cargo antes e depois fica com o subsídio da lei
    sem_folha = {int(a) * 100 + int(m) for a, m, s in zip(lidos.ano, lidos.mes, lidos.situacao) if s != "ok"}
    subsidio = lambda am: [v for d, v in CFG["subsidio"] if d <= am][-1]
    ver_, mandatos, ganha, cod_lot, nomes_verba = [], [], [], {}, []
    for mat, g in fol.groupby("matricula"):
        g = g.sort_values(["am", "folha"])
        nome = g.nome.iloc[-1]
        lot = [x for x in g.lotacao if GABINETE.match(normalizar_nome(x))] or list(g.lotacao)
        parl = _parlamentar(lot[-1])
        t = por_civil.get(normalizar_nome(nome)) or comum.achar(parl, tse) or {}
        codigo = comum.codigo_de(nome, t)
        exib = t.get("urna") if t.get("urna") and normalizar_nome(t["urna"]) == parl else parl
        for l in g.lotacao.unique():
            cod_lot[(normalizar_nome(l))] = codigo
        nomes_verba.append((codigo, parl, nome, t.get("urna", "")))
        ver_.append({"codigo": codigo, "nome": vc.titulo(exib), "nome_civil": vc.titulo(t.get("nome") or nome),
                     "partido": partidos.get(normalizar_nome(t.get("nome") or nome)) or partidos.get(normalizar_nome(nome), ""),
                     "genero": t.get("genero") or ("F" if re.match(r"GABINETE DA DEPUTADA", normalizar_nome(lot[-1])) or feminino(nome) else "M"),
                     "eleito": t.get("eleito", ""), "pagina": CFG["pagina"]})
        # no cargo: os meses com subsídio na folha (a folha de acertos de um mês pode trazer quem já saiu)
        meses_g = sorted(set(g[(g.subsidio > 0.005) | (g.folha == "Folha 001")].am)) or sorted(set(g.am))
        cheios = set(meses_g) | {x for x in sem_folha if any(m < x for m in meses_g) and any(m > x for m in meses_g)}
        per = comum.periodos(sorted(cheios), ultimo_dado, ultimo, folga=1)
        fim = max(cheios)
        if fim < ultimo_dado:
            per = [(i, f or f"{fim // 100}-{fim % 100:02d}-28") for i, f in per]
        for i, f in per:
            mandatos.append({"codigo": codigo, "inicio": i, "fim": f})
        for r in g.itertuples():
            treze = r.folha != "Folha 001"  # vantagens eventuais numa folha à parte = 13º (002 e 003: adiantamento; 016: dezembro)
            for cat, v in (("salario", r.subsidio + r.redutor + r.cargo_comissao), ("decimo_terceiro", r.vantagens_eventuais if treze else 0.0),
                           ("outros_rendimentos", r.vantagens_pessoais + r.outros_creditos + (0.0 if treze else r.vantagens_eventuais)),
                           ("auxilios", r.aux_preescolar + r.aux_transporte + r.aux_alimentacao)):
                if abs(v) >= 0.005:
                    ganha.append({"ano": r.ano, "mes": r.mes, "codigo": codigo, "categoria": cat, "valor": round(v, 2)})
        for am in sorted(cheios - set(g.am)):
            ganha.append({"ano": am // 100, "mes": am % 100, "codigo": codigo, "categoria": "salario", "valor": subsidio(am)})
    # verba: o nome do quadro ("DRA. JANE", "PEDRO PAULO DE OLIVEIRA") é o nome parlamentar da lotação ou o nome civil
    opcoes = [(n, c) for c, parl, civil, urna in nomes_verba for n in (parl, civil, urna) if n]
    quem = {n: vc.achar_parecido(_chave(n), [(_chave(a), c) for a, c in opcoes], minimo=0.8) for n in ver.deputado.unique()}
    sem = sorted(n for n, c in quem.items() if c is None)
    if sem:
        log(f"  CLDF: verba sem deputado na folha: {', '.join(sem)}")
    # o quadro da verba escreve o nome com acento ("JOÃO CARDOSO"); a lotação da folha, sem: vale o do quadro quando é o mesmo nome
    for x in ver_:
        if normalizar_nome(x["nome"]) != x["nome"].upper():
            continue
        for n, c in quem.items():
            if c == x["codigo"] and normalizar_nome(n) == normalizar_nome(x["nome"]):
                x["nome"] = vc.titulo(n)
                break
    v = ver[(ver.coluna != "") & (ver.coluna != "total") & (ver.valor.abs() >= 0.005)]
    v = v.assign(codigo=v.deputado.map(quem)).dropna(subset=["codigo"])
    desp = pd.DataFrame({"ano": v.ano, "mes": v.mes, "codigo": v.codigo.astype(int), "tipo": v.coluna.map(TIPOS).fillna("Outras despesas"),
                         "fornecedor": "", "cnpj_cpf": "", "valor": [-x if c == "glosa" else x for c, x in zip(v.coluna, v.valor)]})
    eq = gab.assign(codigo=gab.lotacao.map(lambda x: cod_lot.get(normalizar_nome(x)))).dropna(subset=["codigo"])
    equipe = pd.DataFrame({"ano": eq.ano, "mes": eq.mes, "codigo": eq.codigo.astype(int), "pessoas": eq.pessoas, "custo": eq.rendimentos})
    cargos, equipe_em = None, ""
    if len(car):
        car["am"] = car.ano * 100 + car.mes
        ult = int(car.am.max())
        c = car[car.am == ult]
        c = c.assign(codigo=c.lotacao.map(lambda x: cod_lot.get(normalizar_nome(x)))).dropna(subset=["codigo"])
        cargos = pd.DataFrame({"codigo": c.codigo.astype(int), "cargo": c.cargo.map(vc.titulo), "pessoas": c.pessoas})
        equipe_em = f"{ult % 100:02d}/{ult // 100}"
    cfg = dict(CFG, ultimo_mes=min(ultimo, ultimo_dado), equipe_em=equipe_em)
    return vc.montar(cfg, tipos, pd.DataFrame(ver_), pd.DataFrame(mandatos), ganha=pd.DataFrame(ganha, columns=["ano", "mes", "codigo", "categoria", "valor"]),
                     despesas=desp, equipe=equipe, cargos=cargos)
