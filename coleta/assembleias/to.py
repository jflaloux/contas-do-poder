"""Assembleia Legislativa do Tocantins (Aleto): deputado estadual por deputado estadual.

Fonte: Portal da Transparência da Aleto, "Verba Indenizatória" (CODAP, Cota Despesa de Atividade Parlamentar):
https://www.al.to.leg.br/transparencia/verbaIndenizatoria. A página pesquisa por ano, mês e deputado e devolve o PDF
do mês (com texto), nota por nota: tipo e número do documento, data, emitente, CNPJ/CPF, valor; e o total ressarcido.
O robô faz a mesma pesquisa e lê o PDF. A consulta da folha (outro sistema) tem hCaptcha e não é usada.
- Subsídio: Lei 4.073/2022 (R$ 33.006,39 desde fev/2024 e R$ 34.774,64 desde fev/2025).
- Nome completo, gênero e eleito/suplente: TSE (eleição de 2022); partido: candidatura de 2026 no TSE.
Quem está no cargo hoje: a lista de deputados da página. Desde quando: os meses com prestação da CODAP.
"""
import re
import subprocess
import tempfile
import unicodedata
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from ..config import CACHE, DADOS
from ..prefeituras.comum import feminino, num
from ..util import TempoEsgotado, _sessao, dormir, gravar_csv, log, normalizar_nome, verificar_prazo
from ..vereadores import comum as vc
from . import comum

UF = "TO"
COD = comum.CODIGOS_UF[UF]
INICIO = 202501
SITE = "https://www.al.to.leg.br"
PAGINA = f"{SITE}/transparencia/verbaIndenizatoria"
PASTA = DADOS / "assembleias" / "to"
C = CACHE / "assembleias" / "to"
SIMULTANEOS = 3
CFG = {
    "cod": COD, "n": "Tocantins", "uf": UF, "casa": "Assembleia Legislativa do Tocantins", "vagas": 24, "inicio": INICIO,
    "id_prefixo": "est", "k": "e", "cargo": ("Deputada estadual", "Deputado estadual"),
    "subsidio": [[202402, 33006.39], [202502, 34774.64]],
    "salario_nota": ("Subsídio fixado em lei (Lei 4.073/2022), proporcional aos meses no cargo. A consulta da folha da Aleto tem CAPTCHA, "
                     "por isso o 13º e outros pagamentos não aparecem aqui."),
    "verba_nome": "Cota Despesa de Atividade Parlamentar (CODAP)",
    "verba_regra": "Reembolso de despesas do mandato com nota fiscal, com limite mensal; o saldo não usado passa para o mês seguinte.",
    "verba_notas": ["A Aleto publica um PDF por deputado e mês, nota por nota, sem a categoria de cada despesa: aqui a categoria vem do "
                    "nome do emitente (posto de combustível, hotel, escritório de advocacia...) e o resto fica em \"outras despesas\".",
                    "O total de cada mês é o valor ressarcido do PDF. Notas acima do limite passam para o mês seguinte; a diferença entre a soma "
                    "das notas e o valor ressarcido aparece como \"notas de outros meses e limite mensal\"."],
    "pagina": "https://www.al.to.leg.br/perfil",
    "notas": ["Quem está no cargo hoje: a lista de deputados da página da CODAP. Desde quando: os meses com prestação de contas.",
              "Partido: o da candidatura de 2026 no TSE. Quem não é candidato em 2026 aparece sem partido."],
    "fontes": {"verba": PAGINA, "subsidio": "https://sapl.al.to.leg.br/media/sapl/public/normajuridica/2022/509/lei_4073-2022.pdf"},
}
LINHA = re.compile(r"^\s*\d+\s+(.*?)\s+([\d.]+,\d{2})\s+(\(?-?[\d.]+,\d{2}\)?|-)\s*$")
DATA = [re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})/(\d{4}|\d{3}|\d{2})(?![\d/])"), re.compile(r"(?<![\d/])(\d{2})(\d{2})/(\d{4})(?![\d/])")]
_CATEGORIAS = [(r"POSTO|PETRO|COMBUST|DERIVADOS", "Combustível"), (r"HOTE|POUSADA|PALACE|\bINN\b", "Hospedagem e diárias"),
               (r"RESTAURA|LANCHE|LANCHONETE|CHURRASC|PIZZ|ALIMENT|PANIFICADORA|SUPERMERCADO", "Alimentação"),
               (r"ADVOCACIA|ADVOGAD|CONSULTORIA|ASSESSORIA|CONTAB|PESQUISA", "Consultorias e assessorias"),
               (r"LOCA[CÇ]|LOCADORA|ALUGUEL|\bRENT", "Locação (carros, imóveis ou equipamentos)"),
               (r"GR[AÁ]FIC|PUBLICIDADE|PROPAGANDA|MARKETING|M[IÍ]DIA|COMUNICA[CÇ]|MULTIM[IÍ]DIA|EDITORA|JORNAL|NOT[IÍ]CIA|R[AÁ]DIO|\bTV\b|"
                r"PRODU[CÇ][OÕ]ES|PRODUTORA|V[IÍ]DEO|IMAGEM|FOTOGRAF", "Divulgação do mandato"),
               (r"VIGIL[AÂ]NCIA|SEGURAN[CÇ]A", "Segurança"),
               (r"TELEF|TELECOM|INTERNET|\bCLARO\b|\bVIVO\b|\bTIM\b", "Telefone e internet"),
               (r"A[EÉ]REAS|AZUL|\bGOL\b|LATAM|PASSAGE|TURISMO|VIAGE", "Passagens")]
AJUSTE = "Notas de outros meses e limite mensal"


def _categoria(emitente):
    u = normalizar_nome(emitente)
    for rx, nome in _CATEGORIAS:
        if re.search(rx, u):
            return nome
    return "Outras despesas (sem categoria no PDF)"


def _pedir(metodo, url, **kw):
    verificar_prazo()
    for tentativa in range(3):
        try:
            r = _sessao().request(metodo, url, timeout=120, **kw)
            r.raise_for_status()
            dormir(1)
            return r
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 2:
                raise
            dormir(15)


def _deputados():
    t = _pedir("GET", PAGINA).text
    s = re.search(r'<select[^>]*name="transparencia.parlamentar"[^>]*>(.*?)</select>', t, flags=re.S)
    tipo = re.search(r'name="transparencia.tipoTransparencia.codigo"[^>]*value="([^"]*)"', t)
    nomes = [" ".join(v.split()) for v in re.findall(r'<option[^>]*value="([^"]+)"', s.group(1) if s else "")]
    return nomes, (tipo.group(1) if tipo else "14")


def _nota(l):
    """Uma linha de nota do PDF: "1 NFS-e 77 25/06/2025 Emitente Ltda 13.020.403/0001-44 5.000,00 37.784,34". O formato varia
    de gabinete para gabinete (CNPJ com ou sem pontos, data d/m/aaaa, coluna de tipo vazia), por isso a leitura é por partes."""
    m = LINHA.match(l)
    if not m or "Saldo de notas" in l:
        return None
    resto = m.group(1).split()
    doc = ""
    if resto and len(re.sub(r"[^\d*]", "", resto[-1])) >= 11 and re.fullmatch(r"[\d*./-]+", resto[-1]):
        doc = resto.pop()
        d = re.sub(r"\D", "", doc)
        if len(d) == 15 and d[0] == "0":
            d = d[1:]
        elif len(d) == 13:  # CNPJ sem o zero da frente
            d = "0" + d
        if len(d) == 14:
            doc = f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    texto = " ".join(resto)
    data, antes, depois = "", texto, ""
    for rx in DATA:
        md = rx.search(texto)
        if md:
            dia, mes, ano = md.groups()
            ano = {2: "20" + ano, 3: "2" + ano}.get(len(ano), ano)
            if 1 <= int(dia) <= 31 and 1 <= int(mes) <= 12:
                data = f"{int(dia):02d}/{int(mes):02d}/{ano}"
            antes, depois = texto[:md.start()].split(), texto[md.end():].strip()
            break
    else:
        antes, depois = texto.split()[:2], " ".join(texto.split()[2:])
    if not depois:
        return None
    return {"tipo_doc": antes[0] if len(antes) > 1 else "", "numero": " ".join(antes[1:] if len(antes) > 1 else antes), "data": data,
            "emitente": depois, "cnpj_cpf": vc.mascarar(doc), "valor": num(m.group(2))}


def _ler_pdf(b):
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(b)
        f.flush()
        texto = subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, text=True).stdout
    notas = [x for x in map(_nota, texto.splitlines()) if x]
    ress = re.search(r"Valor ressarcido\s+(-?[\d.]+,\d{2})", texto, flags=re.I)
    dep = re.search(r"DEPUTAD([OA])\s*:\s*(.+?)(?:\s{2,}|$)", texto, flags=re.M)
    return notas, (num(ress.group(1)) if ress else None), ((dep.group(2).strip(), dep.group(1)) if dep else ("", ""))


def _meses():
    h = time.localtime()
    return [a * 100 + m for a in range(INICIO // 100, h.tm_year + 1) for m in range(1, 13) if INICIO <= a * 100 + m < h.tm_year * 100 + h.tm_mon]


def coletar():
    PASTA.mkdir(parents=True, exist_ok=True)
    (C / "pdf").mkdir(parents=True, exist_ok=True)
    nomes, tipo = _deputados()
    if len(nomes) >= 20:
        gravar_csv(pd.DataFrame({"nome": nomes}).assign(visto_em=time.strftime("%Y-%m-%d")), PASTA / "em_exercicio.csv")
    else:
        nomes = list(pd.read_csv(PASTA / "em_exercicio.csv").nome) if (PASTA / "em_exercicio.csv").exists() else nomes
    meses = _meses()
    fila = []
    for am in meses:
        for n in nomes:
            chave = f"{am}_{re.sub(r'[^A-Za-z0-9]+', '_', normalizar_nome(n))}"
            feito = C / "pdf" / f"{chave}.pdf"
            vazio = C / "pdf" / f"{chave}.vazio"
            recente = am >= meses[-2]
            velho = lambda p: time.time() - p.stat().st_mtime > 3 * 86400
            if (feito.exists() and not (recente and velho(feito))) or (vazio.exists() and vazio.read_text() == "2" and not velho(vazio)):
                continue
            fila.append((am, n, feito, vazio))

    def uma(item):
        am, n, feito, vazio = item
        # o nome guardado em cada prestação nem sempre tem acento ("Leo Barbosa" em 2025, "Léo Barbosa" na lista de hoje)
        for nome in dict.fromkeys([n, unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode()]):
            t = _pedir("POST", PAGINA, data={"transparencia.ano": str(am // 100), "transparencia.mes": str(am % 100), "transparencia.parlamentar": nome,
                                             "transparencia.tipoTransparencia.codigo": tipo}).text
            m = re.search(r"(/transparencia/baixar\?arquivo=[^\"']+)", t)
            if m:
                break
        if not m:
            vazio.write_text("2", encoding="utf-8")  # "2": as duas grafias foram tentadas
            return
        feito.write_bytes(_pedir("GET", SITE + m.group(1)).content)

    try:
        with ThreadPoolExecutor(SIMULTANEOS) as ex:
            list(ex.map(uma, fila))
    finally:
        linhas = []
        for am in meses:
            for n in nomes:
                feito = C / "pdf" / f"{am}_{re.sub(r'[^A-Za-z0-9]+', '_', normalizar_nome(n))}.pdf"
                if not feito.exists():
                    continue
                notas, ress, (civil, oa) = _ler_pdf(feito.read_bytes())
                base = {"ano": am // 100, "mes": am % 100, "deputado": n, "nome_pdf": civil, "oa": oa}
                for x in notas:
                    linhas.append({**base, **x, "ajuste": 0})
                soma = sum(x["valor"] for x in notas)
                # O total ressarcido é o que vale: notas de meses anteriores que entram agora, notas acima do limite que passam
                # para o mês seguinte e glosas (limite de combustível) ficam numa linha de ajuste, para a soma bater com o PDF.
                if ress is not None and abs(ress - soma) >= 0.01:
                    linhas.append({**base, "tipo_doc": "", "numero": "", "data": "", "emitente": "", "cnpj_cpf": "",
                                   "valor": round(ress - soma, 2), "ajuste": 1})
        df = pd.DataFrame(linhas)
        if len(df):
            gravar_csv(df.sort_values(["ano", "mes", "deputado", "data"]), PASTA / "codap_notas.csv")
        log(f"  Aleto: {len(nomes)} deputados, {len(df)} linhas da CODAP ({len(fila)} pesquisas na fila desta rodada)")


def montar(tipos):
    arq = PASTA / "codap_notas.csv"
    if not arq.exists():
        return None
    v = pd.read_csv(arq, dtype={"cnpj_cpf": str}).fillna("")
    hoje = set(normalizar_nome(n) for n in pd.read_csv(PASTA / "em_exercicio.csv").nome) if (PASTA / "em_exercicio.csv").exists() else set()
    tse = comum.tse_2022(UF)
    partidos = comum.partido_2026(UF)
    ultimo = vc.ultimo_mes_fechado()
    ultimo_dado = int((v.ano * 100 + v.mes).max())
    ver, mandatos, cods = [], [], {}
    for nome, g in v.groupby("deputado"):
        civis = [c for c in g.nome_pdf.unique() if c]
        t = comum.achar(re.sub(r"^Deputad[oa]\s+", "", nome), tse) or next((x for x in (comum.achar(c, tse) for c in civis) if x), {})
        codigo = comum.codigo_de(nome, t)
        cods[nome] = codigo
        ver.append({"codigo": codigo, "nome": re.sub(r"^Deputad[oa]\s+", "", nome), "nome_civil": vc.titulo(t.get("nome", "")) if t else "",
                    "partido": partidos.get(normalizar_nome(t.get("nome", "")), "") if t else "",
                    "genero": t.get("genero") or ("F" if feminino(nome) else "M"), "eleito": t.get("eleito", ""), "pagina": CFG["pagina"]})
        meses_g = list(g.ano * 100 + g.mes)
        atual = normalizar_nome(nome) in hoje if hoje else None
        if atual:
            meses_g = sorted(set(meses_g) | {ultimo_dado})
        per = comum.periodos(meses_g, ultimo_dado, ultimo)
        if atual is False:
            per = [(i, f or f"{max(meses_g) // 100}-{max(meses_g) % 100:02d}-28") for i, f in per]
        for i, f in per:
            mandatos.append({"codigo": codigo, "inicio": i, "fim": f})
    ajuste = v.get("ajuste", pd.Series([""] * len(v))).astype(str).isin(["1", "1.0"])
    desp = v.assign(codigo=v.deputado.map(cods), fornecedor=v.emitente,
                    tipo=[(AJUSTE if a else _categoria(e)) for a, e in zip(ajuste, v.emitente)])
    cfg = dict(CFG, ultimo_mes=min(ultimo, ultimo_dado))
    return vc.montar(cfg, tipos, pd.DataFrame(ver), pd.DataFrame(mandatos), despesas=desp[["ano", "mes", "codigo", "tipo", "fornecedor", "cnpj_cpf", "valor"]])
