"""Assembleia Legislativa de Roraima (ALE-RR): deputado estadual por deputado estadual.

Fontes (Portal da Transparência da ALE-RR, https://transparencia.al.rr.leg.br/; abre também de fora do Brasil, mas é lento):
- Verba indenizatória ("Ressarcimento de despesas parlamentar", Resolução 036/2021): um arquivo por deputado e mês (ODT,
  e o mesmo em PDF) com a cota mensal, o valor de cada item de despesa, a soma, o que passou da cota e a despesa
  indenizada no mês. Sem fornecedor nem CNPJ.
  https://transparencia.al.rr.leg.br/execucao-orcamentaria-e-financeira/verbas-indenizatorias-a-partir-de-set25/
  A lista de arquivos sai do que a página usa (admin-ajax.php, action=wpdf_load_folder_data, com o código que a página
  entrega a quem a abre). A página dos meses até ago/2025 não responde (erro 504 depois de 90 s): esses meses ficam de fora.
- Folha: "Remuneração dos Servidores" (Gestão de Pessoal), um arquivo por mês até set/2025 (ODT até ago/2025, na página
  .../gestao-de-pessoal-ate-ago-25/, e PDF em set/2025): o total de proventos de cada deputado. Descontos e líquido não
  são guardados. Depois de set/2025 a remuneração não foi publicada: vale o subsídio da lei.
- Equipe: a planilha mensal de servidores ("Relatório de servidores" até ago/2025, "Consulta servidores" depois), com o
  setor de cada servidor ("GAB DEP ..."); só o número de pessoas por gabinete e mês e os cargos são guardados, sem nomes.
- Subsídio: Lei 1.789/2023 (R$ 33.006,39 desde fev/2024 e R$ 34.774,64 desde fev/2025).
- Nome completo, gênero e eleito/suplente: TSE (eleição de 2022); partido: candidatura de 2026 no TSE.
Quem está no cargo: os deputados na folha do mês (até set/2025) e com o arquivo da verba no mês (desde set/2025).
"""
import html as H
import io
import re
import shutil
import subprocess
import tempfile
import time
import unicodedata
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from ..config import CACHE, DADOS
from ..prefeituras.comum import feminino
from ..util import TempoEsgotado, _sessao, dormir, gravar_csv, log, normalizar_nome, verificar_prazo
from ..vereadores import comum as vc
from . import comum

UF = "RR"
COD = comum.CODIGOS_UF[UF]
SITE = "https://transparencia.al.rr.leg.br"
EXEC = f"{SITE}/execucao-orcamentaria-e-financeira"
PAG_VERBA = f"{EXEC}/verbas-indenizatorias-a-partir-de-set25/"
PAG_VERBA_ANTIGA = f"{EXEC}/verbas-indenizatorias-de-gabinete-ate-ago25/"
PAG_PESSOAL = f"{EXEC}/gestao-de-pessoal-a-partir-de-set25/"
PAG_PESSOAL_ANTIGA = f"{EXEC}/gestao-de-pessoal-ate-ago-25/"
PASTA = DADOS / "assembleias" / "rr"
C = CACHE / "assembleias" / "rr"
INICIO = 202501
MESES = {m: i for i, m in enumerate(["JANEIRO", "FEVEREIRO", "MARCO", "ABRIL", "MAIO", "JUNHO", "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO",
                                      "NOVEMBRO", "DEZEMBRO"], 1)}
CFG = {
    "cod": COD, "n": "Roraima", "uf": UF, "casa": "Assembleia Legislativa de Roraima", "vagas": 24, "inicio": INICIO,
    "id_prefixo": "est", "k": "e", "cargo": ("Deputada estadual", "Deputado estadual"),
    "subsidio": [[202402, 33006.39], [202502, 34774.64]],
    "subsidio_folha": True,
    "salario_nota": ("De jan/2025 a set/2025, o total de proventos de cada deputado na folha mensal da ALE-RR (a folha publicada não separa "
                     "o subsídio dos outros proventos) e, na folha de 13º de jun/2025, o adiantamento do 13º; sem descontos. Desde out/2025 a ALE-RR não publica a remuneração: vale o "
                     "subsídio da lei (Lei 1.789/2023)."),
    "verba_nome": "Ressarcimento de despesas parlamentar (verba indenizatória)",
    "verba_regra": "Cota mensal de R$ 50.000 para despesas do mandato, reembolsadas com comprovante (Resolução 036/2021).",
    "verba_notas": ["A ALE-RR publica a verba por deputado, mês e item de despesa, sem fornecedor nem CNPJ.",
                    "O que passou da cota do mês e não foi ressarcido entra como valor negativo, para o total ser a despesa indenizada no mês.",
                    "A página com os meses até ago/2025 não respondeu (erro 504): a verba começa em set/2025."],
    "equipe_nota": ("Equipe: servidores do setor do gabinete do deputado (\"GAB DEP ...\") na planilha mensal de servidores da ALE-RR, sem "
                    "o custo. Entram todos os lotados no setor: comissionados (a maioria, \"Auxiliar de Gabinete\"), servidores cedidos "
                    "por outros órgãos e os do gabinete regional. Quem trabalha para o deputado em outro setor (Mesa, lideranças) "
                    "fica de fora."),
    "pagina": "https://al.rr.leg.br/deputados-estaduais-2023/",
    "notas": ["Quem está no cargo: os deputados na folha do mês (até set/2025) e com o arquivo da verba indenizatória no mês (desde set/2025).",
              "Partido: o da candidatura de 2026 no TSE. Quem não é candidato em 2026 aparece sem partido."],
    "fontes": {"verba": PAG_VERBA, "folha": PAG_PESSOAL_ANTIGA, "equipe": PAG_PESSOAL,
               "subsidio": "https://atos.tjrr.jus.br/atos/detalhar/2865"},
}


def _get(url, timeout=150):
    verificar_prazo()
    for tentativa in range(3):
        try:
            r = _sessao().get(url, timeout=timeout)
            r.raise_for_status()
            dormir(1)
            return r
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 2:
                raise
            dormir(20)


# ---------------------------------------------------------------- listas de arquivos
def _arquivos_wpdf(pagina):
    """Lista de arquivos das páginas novas (pastas por ano e mês): [(pasta, nome do arquivo, link)]."""
    t = _get(pagina).text
    nonce = re.search(r'"wpdf_nonce":"([^"]+)"', t)
    ajax = re.search(r'"wpdf_ajax_url":"([^"]+)"', t)
    sid = re.search(r'class="df_container[^"]*"[^>]*data-sid="([^"]+)"', t) or re.search(r'data-sid="([^"]+)"', t)
    if not (nonce and ajax and sid):
        raise RuntimeError("a página não trouxe a lista de arquivos")
    ajax = ajax.group(1).replace("\\/", "/")
    pastas = re.findall(r'<li data-type="folder" data-name="([^"]+)" data-path="([^"]*)"', t)
    if not pastas:  # às vezes a página vem sem as pastas de cima (desde 02/10/2026 na da verba); as de cada ano continuam abrindo
        pastas = [(f"Ano {a}", f"Ano {a}/") for a in range(INICIO // 100, int(time.strftime("%Y")) + 1)]
    saida, vistas = [], set()
    while pastas:
        nome, caminho = pastas.pop(0)
        if caminho in vistas:
            continue
        vistas.add(caminho)
        verificar_prazo()
        r = _sessao().post(ajax, data={"action": "wpdf_load_folder_data", "folder_name": H.unescape(nome), "folder_path": H.unescape(caminho),
                                       "sid": sid.group(1), "wpdf_nonce": nonce.group(1)}, timeout=150)
        r.raise_for_status()
        dormir(1)
        inner = r.json().get("inner_content") or ""
        pastas += re.findall(r'<li data-type="folder" data-name="([^"]+)" data-path="([^"]*)"', inner)
        for arq, link in re.findall(r'<li class="file_record" data-name="([^"]+)".*?href="([^"]+)"', inner, flags=re.S):
            saida.append((H.unescape(caminho), H.unescape(arq), H.unescape(link)))
    return saida


def _arquivos_wpdm(pagina):
    """Lista das páginas antigas (um pacote por arquivo): [(título, link)]."""
    t = _get(pagina, timeout=170).text
    return [(" ".join(H.unescape(n).split()), H.unescape(d)) for n, d in
            re.findall(r"<h3 class=\"package-title\"><a href='[^']+'>([^<]+)</a></h3>.*?data-downloadurl=\"([^\"]+)\"", t, flags=re.S)]


def _mes(texto):
    """"Ano 2026/07 - Julho de 2026/", "Ano 2026/08-Agosto/", "Remuneração dos Servidores – Janeiro/2025" -> AAAAMM."""
    m = re.search(r"(\d{1,2})\s*-\s*[A-Za-zçÇ]+\s+de\s+(\d{4})", texto)
    if m:
        return int(m.group(2)) * 100 + int(m.group(1))
    a = re.findall(r"(20\d\d)", texto)
    u = normalizar_nome(texto)
    for nome, i in MESES.items():
        if re.search(rf"\b{nome}\b", u) and a:
            return int(a[-1]) * 100 + i
    return None


def _id(link):
    """Número do arquivo no link: o wpdf_id muda a cada vez que a página é aberta, mas termina sempre no mesmo número
    ("...-598755"); nos pacotes antigos, o wpdmdl."""
    m = re.search(r"wpdf_id=[\w-]*?-(\d+)(?:&|$)", link) or re.search(r"wpdmdl=(\d+)", link)
    return m.group(1) if m else re.sub(r"[^A-Za-z0-9]+", "_", link)[-80:]


def _baixar(link, nome):
    arq = C / "arquivos" / _id(link)
    if not arq.exists():
        tmp = arq.with_suffix(".parcial")
        tmp.write_bytes(_get(link, timeout=60).content)
        tmp.rename(arq)
    return arq.read_bytes()


# ---------------------------------------------------------------- leitura dos arquivos
def _num(t):
    t = (t or "").replace("R$", "").replace(" ", "").strip()
    if not re.search(r"\d", t):
        return None
    neg = t.startswith("-") or (t.startswith("(") and t.endswith(")"))
    t = t.strip("-()").replace(".", "").replace(",", ".")
    try:
        return -float(t) if neg else float(t)
    except ValueError:
        return None


def _txt(x):
    return " ".join(H.unescape(re.sub(r"<[^>]+>", " ", x or "")).split())


def _linhas_od(conteudo, limite_rep=60):
    """Linhas (listas de células com texto) das tabelas de um ODT ou ODS."""
    x = zipfile.ZipFile(io.BytesIO(conteudo)).read("content.xml").decode("utf-8")
    saida = []
    for row in re.findall(r"<table:table-row\b[^>]*>(.*?)</table:table-row>", x, flags=re.S):
        cel = []
        for attrs, corpo in re.findall(r"<table:(?:covered-)?table-cell\b([^>]*?)(?:/>|>(.*?)</table:(?:covered-)?table-cell>)", row, flags=re.S):
            rep = re.search(r'table:number-columns-repeated="(\d+)"', attrs)
            texto = _txt(corpo)
            cel += [texto] * (min(int(rep.group(1)), limite_rep) if rep else 1)
        saida.append(cel)
    return saida


def _pdf_texto(conteudo):
    if not shutil.which("pdftotext"):
        return None
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(conteudo)
        f.flush()
        return subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, text=True, timeout=600).stdout


_ROTULOS = (("cota", "COTA MENSAL"), ("saldo_anterior", "SALDO DO MES ANTERIOR"), ("soma_parcial", "SOMA PARCIAL"),
            ("acima_limite", "ACIMA DO LIMITE"), ("nao_ressarcido", "VALOR NAO RESSARCIDO"), ("indenizado", "DESPESA INDENIZADA"),
            ("saldo_mes", "SALDO DO MES:"))


def _sem_acento(t):
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().upper()


def _quadro(linhas):
    """Quadro da verba (linhas de células) -> {parlamentar, mes, ano, cota, ..., itens: [(item, grupo, descrição, valor)]}."""
    saida, grupo = {"itens": []}, ""
    for cel in linhas:
        cel = [c for c in cel if c]
        if not cel:
            continue
        j = " ".join(cel)
        m = re.search(r"RESSARCIMENTO DE DESPESAS PARLAMENTAR\s*-\s*(\d{4})", j)
        if m:
            saida["ano"] = int(m.group(1))
            continue
        m = re.match(r"Parlamentar:\s*(.*?)\s+M[êe]s:\s*(\S+)", j)
        if not m:  # alguns arquivos trazem só o nome do mês, sem o rótulo "Mês:"
            m = re.match(r"Parlamentar:\s*(.*?)\s+(\S+)$", j)
            m = m if m and _sem_acento(m.group(2)) in MESES else None
        if m:
            saida["parlamentar"], saida["mes"] = " ".join(m.group(1).split()), _sem_acento(m.group(2))
            continue
        if re.fullmatch(r"\d", cel[0]) and len(cel) >= 2:
            grupo = cel[1]
            continue
        if re.fullmatch(r"\d+\.\d+", cel[0]) and len(cel) >= 2:
            v = _num(cel[-1]) if len(cel) >= 3 else None
            saida["itens"].append((cel[0], grupo, cel[1], v or 0.0))
            continue
        rot = _sem_acento(cel[0])
        for chave, padrao in _ROTULOS:
            if rot.startswith(padrao):
                saida[chave] = _num(cel[-1]) if len(cel) >= 2 else None
    return saida


def _quadro_pdf(conteudo):
    texto = _pdf_texto(conteudo)
    if texto is None:
        return None
    linhas = []
    for l in texto.splitlines():
        l = l.strip()
        if not l:
            continue
        m = re.match(r"^(\d+(?:\.\d+)?)\s+(.*?)(?:\s{2,}(-?[\d.]+,\d{2}))?$", l)
        if m:
            linhas.append([m.group(1), m.group(2).strip()] + ([m.group(3)] if m.group(3) else []))
            continue
        m = re.match(r"^(.*?:?)\s{2,}(?:R\$\s*)?(-?[\d.]+,\d{2})$", l)
        linhas.append([m.group(1).strip(), m.group(2)] if m else [" ".join(l.split())])
    return _quadro(linhas)


def _ler_quadro(conteudo, ext):
    try:
        return _quadro(_linhas_od(conteudo)) if ext == "odt" else _quadro_pdf(conteudo)
    except (zipfile.BadZipFile, KeyError, UnicodeDecodeError):
        return None


def _folha(conteudo):
    """Remuneração dos servidores (ODT ou PDF) -> [(matrícula, nome, total de proventos)] dos deputados."""
    if conteudo[:2] == b"PK":
        linhas = [" | ".join(c for c in l if c) for l in _linhas_od(conteudo)]
    else:
        linhas = [" | ".join(re.split(r"\s{2,}", l.strip())) for l in (_pdf_texto(conteudo) or "").splitlines() if l.strip()]
    saida, atual = [], None
    for l in linhas:
        m = re.match(r"^(\d+)\s+([A-ZÀ-Ú][A-ZÀ-Ú' .-]+?)\s*\|\s*([^|]+)", l)
        if m:
            atual = (m.group(1), " ".join(m.group(2).split()), normalizar_nome(m.group(3)))
            continue
        p = re.search(r"9000\s*-\s*Total de Proventos\s*\|?\s*(-?[\d.]+,\d{2})", l)
        if p and atual and atual[2].startswith("DEPUTAD"):
            saida.append((atual[0], atual[1], _num(p.group(1))))
            atual = None
    return saida


def _setores(conteudo):
    """Planilha de servidores (XLSX ou ODS) -> DataFrame com as colunas setor e cargo."""
    if conteudo[:4] not in (b"PK\x03\x04", b"\xd0\xcf\x11\xe0"):
        return None  # não é planilha (o mesmo relatório também sai em PDF)
    if conteudo[:2] == b"PK" and b"opendocument" in conteudo[:200]:
        linhas = _linhas_od(conteudo, limite_rep=1)
        cab = next((i for i, l in enumerate(linhas) if any(re.search(r"\bSETOR\b", normalizar_nome(c)) or normalizar_nome(c) == "CCUSTO"
                                                           for c in l)), None)
        if cab is None:
            return None
        n = len(linhas[cab])
        df = pd.DataFrame([(l + [""] * n)[:n] for l in linhas[cab + 1:]], columns=linhas[cab])
    else:
        df = pd.read_excel(io.BytesIO(conteudo), dtype=str)
    df = df.fillna("")
    col = {normalizar_nome(c): c for c in df.columns}
    sc = col.get("SETOR") or next((c for n, c in col.items() if re.search(r"\bSETOR\b", n)), None)  # "LOTAÇÃO - SETOR"
    cc = col.get("CCUSTO")  # em jun/2025 o gabinete está só no centro de custo
    if cc and df[cc].map(lambda s: _gab(s) is not None).any():
        setor = df[cc]
    elif sc is not None:
        setor = df[sc]
    else:
        return None
    return pd.DataFrame({"setor": setor.map(lambda s: " ".join(str(s).split())), "cargo": df[col["CARGO"]] if "CARGO" in col else ""})


def _gab(setor):
    """"EST 080 - GAB DEP RENATO SILVA", "GAB. DEP. ANGELA PORTELLA" -> "RENATO SILVA" (ou None se não é gabinete de deputado)."""
    u = " ".join(normalizar_nome(setor).replace(".", " ").split())
    m = re.search(r"\bGAB\s+DEP\s+(.+)$", u)
    return m.group(1).strip() if m else None


# ---------------------------------------------------------------- coleta
def coletar():
    PASTA.mkdir(parents=True, exist_ok=True)
    (C / "arquivos").mkdir(parents=True, exist_ok=True)
    for parte in (_coletar_verba, _coletar_pessoal_antigo, _coletar_pessoal):
        try:
            parte()
        except TempoEsgotado:
            raise
        except Exception as e:  # noqa: BLE001 — uma página fora do ar não para as outras
            log(f"  ALE-RR: {parte.__name__} falhou ({type(e).__name__}: {e}); fica o que já estava gravado")


def _gravar(df, arq, chave, ordem):
    df = df.drop_duplicates(chave, keep="last")
    gravar_csv(df.sort_values(ordem), arq)
    return df


def _ler_folha():
    arq = PASTA / "folha_deputados.csv"
    fol = pd.read_csv(arq, dtype={"matricula": str}) if arq.exists() else \
        pd.DataFrame(columns=["ano", "mes", "matricula", "nome", "proventos", "folha", "arquivo"])
    fol["folha"] = fol.folha.fillna("normal").astype(str) if "folha" in fol else "normal"
    return fol


def _tipo_folha(titulo):
    """"Remuneração dos Servidores – Junho 2025 - 13º" -> "13"; "... Suplementar II ..." -> "suplementar ii"; senão "normal"."""
    u = normalizar_nome(titulo)
    if re.search(r"\b13(O|\b)|DECIMO TERCEIRO", u):
        return "13"
    m = re.search(r"SUPLEMENTAR(\s+[IVX\d]+\b)?", u)
    return ("suplementar" + (m.group(1) or "").lower()) if m else "normal"


def _ler_equipe():
    arq = PASTA / "equipe.csv"
    return pd.read_csv(arq) if arq.exists() else pd.DataFrame(columns=["ano", "mes", "gabinete", "pessoas", "arquivo"])


def _prebaixar(faltam, folga=30):
    """Baixa os arquivos que faltam, 3 por vez, até `folga` segundos antes do prazo (o resto fica para a próxima rodada)."""
    import time as _t
    from ..util import restante

    def um(link, nome):
        try:
            _baixar(link, nome)
        except Exception as e:  # noqa: BLE001 — um arquivo que não veio é pedido de novo na próxima rodada
            log(f"  ALE-RR: {nome} não veio ({type(e).__name__})")
    with ThreadPoolExecutor(3) as ex:
        futs = []
        for x in faltam:
            r = restante()
            if r is not None and r < folga:
                break
            futs.append(ex.submit(um, *x))
            while sum(not f.done() for f in futs) >= 3:
                _t.sleep(0.2)


def _coletar_verba():
    arq_m, arq_i = PASTA / "verba_meses.csv", PASTA / "verba_itens.csv"
    meses = pd.read_csv(arq_m) if arq_m.exists() else pd.DataFrame(columns=["ano", "mes", "deputado", "arquivo"])
    itens = pd.read_csv(arq_i) if arq_i.exists() else pd.DataFrame(columns=["ano", "mes", "deputado", "item", "arquivo"])
    feitos = {_id(x) for x in meses.arquivo}
    por_chave, reserva = {}, {}  # um arquivo por deputado e mês: o ODT; o PDF quando não há ODT ou o ODT não abre
    for caminho, nome, link in _arquivos_wpdf(PAG_VERBA):
        ext = nome.rsplit(".", 1)[-1].lower()
        if ext in ("odt", "pdf"):
            chave = (caminho, normalizar_nome(nome.rsplit(".", 1)[0]))
            if ext == "odt" or chave not in por_chave:
                if chave in por_chave:
                    reserva[chave] = por_chave[chave]
                por_chave[chave] = (caminho, nome, link, ext)
            else:
                reserva[chave] = (caminho, nome, link, ext)
    # baixa antes (3 por vez; cada arquivo fica no cache assim que chega)
    faltam = [(link, nome) for caminho, nome, link, ext in por_chave.values()
              if _id(link) not in feitos and (_mes(caminho) or 0) >= INICIO]
    _prebaixar(faltam)
    novos_m, novos_i = [], []
    estado = {"meses": meses, "itens": itens, "gravados": 0}

    def gravar():  # grava a cada 10 arquivos (e no fim), para a próxima rodada continuar de onde parou
        if len(novos_m) == estado["gravados"]:
            return
        m_ = pd.concat([estado["meses"], pd.DataFrame(novos_m[estado["gravados"]:])], ignore_index=True)
        i_ = pd.concat([estado["itens"], pd.DataFrame(novos_i)], ignore_index=True) if novos_i else estado["itens"]
        novos_i.clear()
        # se a ALE-RR trocou o arquivo de um deputado e mês, vale o último lido
        m_ = _gravar(m_, arq_m, ["ano", "mes", "deputado"], ["ano", "mes", "deputado"])
        i_ = i_[i_.arquivo.map(_id).isin({_id(x) for x in m_.arquivo})]
        gravar_csv(i_.sort_values(["ano", "mes", "deputado", "item"]), arq_i)
        estado.update(meses=m_, itens=i_, gravados=len(novos_m))
    try:
        for chave, (caminho, nome, link, ext) in por_chave.items():
            if len(novos_m) - estado["gravados"] >= 10:
                gravar()
            am = _mes(caminho)
            if am is None or am < INICIO or _id(link) in feitos or not (C / "arquivos" / _id(link)).exists():
                continue  # o que não chegou a ser baixado fica para a próxima rodada
            q = _ler_quadro(_baixar(link, nome), ext)
            if (not q or not q.get("parlamentar")) and chave in reserva:
                caminho, nome, link, ext = reserva[chave]
                q = _ler_quadro(_baixar(link, nome), ext)
            if not q or not q.get("parlamentar"):
                log(f"  ALE-RR: não deu para ler {nome}")
                continue
            if q.get("mes") in MESES and q.get("ano") and q["ano"] * 100 + MESES[q["mes"]] != am:
                log(f"  ALE-RR: {nome} está na pasta {caminho} mas diz {q['mes']}/{q['ano']}; vale o que o arquivo diz")
                am = q["ano"] * 100 + MESES[q["mes"]]
            soma = round(sum(v for *_, v in q["itens"]), 2)
            if q.get("soma_parcial") is not None and abs(soma - q["soma_parcial"]) >= 0.01:
                log(f"  ALE-RR: {nome}: os itens somam {soma} e a soma parcial diz {q['soma_parcial']}")
            novos_m.append({"ano": am // 100, "mes": am % 100, "deputado": q["parlamentar"], "cota": q.get("cota"),
                            "soma_parcial": q.get("soma_parcial"), "acima_limite": q.get("acima_limite"), "nao_ressarcido": q.get("nao_ressarcido"),
                            "indenizado": q.get("indenizado"), "soma_itens": soma, "arquivo": link, "nome_arquivo": nome})
            for item, grupo, desc, v in q["itens"]:
                if abs(v) >= 0.005:
                    novos_i.append({"ano": am // 100, "mes": am % 100, "deputado": q["parlamentar"], "item": item, "grupo": grupo,
                                    "descricao": desc, "valor": v, "arquivo": link})
    finally:
        gravar()
        log(f"  ALE-RR: verba, {len(novos_m)} arquivos novos ({len(por_chave)} deputados e meses na página)")


def _coletar_pessoal_antigo():
    """Página de Gestão de Pessoal até ago/2025: a remuneração (folha) e o relatório de servidores (setor) de cada mês."""
    arq_f, arq_e = PASTA / "folha_deputados.csv", PASTA / "equipe.csv"
    fol, eq = _ler_folha(), _ler_equipe()
    meses_f, meses_e = set(zip(fol.ano, fol.mes)), set(zip(eq.ano, eq.mes))
    lidas = set(zip(fol.ano, fol.mes, fol.folha))
    if all((a, m) in meses_f and (a, m) in meses_e for a, m in vc.meses(INICIO, 202508)):
        return  # a página antiga não muda mais
    for titulo, link in _arquivos_wpdm(PAG_PESSOAL_ANTIGA):
        am = _mes(titulo)
        if am is None or not INICIO <= am <= 202508:
            continue
        u = normalizar_nome(titulo)
        a, m = am // 100, am % 100
        tf = _tipo_folha(titulo)
        if u.startswith("REMUNERACAO DOS SERVIDORES") and (a, m, tf) not in lidas:
            conteudo = _baixar(link, titulo)
            linhas = _folha(conteudo)
            if linhas or conteudo[:2] == b"PK":  # a folha suplementar pode não ter deputados: o mesmo arquivo em PDF não é lido
                lidas.add((a, m, tf))
            if linhas:
                fol = _gravar(pd.concat([fol, pd.DataFrame([{"ano": a, "mes": m, "matricula": x, "nome": n, "proventos": v, "folha": tf, "arquivo": link}
                                                            for x, n, v in linhas])], ignore_index=True), arq_f,
                              ["ano", "mes", "matricula", "folha"], ["ano", "mes", "nome", "folha"])
                meses_f.add((a, m))
                log(f"  ALE-RR: folha de {m:02d}/{a} ({tf}): {len(linhas)} deputados")
        elif u.startswith("RELATORIO DE SERVIDORES") and (a, m) not in meses_e:
            df = _setores(_baixar(link, titulo))
            if df is None:
                continue
            g = df.assign(gab=df.setor.map(_gab)).dropna(subset=["gab"])
            novos = [{"ano": a, "mes": m, "gabinete": k, "pessoas": int(n), "arquivo": link} for k, n in g.groupby("gab").size().items()]
            if novos:
                eq = _gravar(pd.concat([eq, pd.DataFrame(novos)], ignore_index=True), arq_e, ["ano", "mes", "gabinete"], ["ano", "mes", "gabinete"])
                meses_e.add((a, m))


def _coletar_pessoal():
    """Página de Gestão de Pessoal desde set/2025: a planilha de servidores de cada mês e a remuneração de set/2025."""
    arq_f, arq_e = PASTA / "folha_deputados.csv", PASTA / "equipe.csv"
    fol, eq = _ler_folha(), _ler_equipe()
    feitos = {_id(x) for x in list(eq.arquivo) + list(fol.arquivo)}
    ultimo = None
    lista = sorted(_arquivos_wpdf(PAG_PESSOAL), key=lambda x: _mes(x[0]) or 0)
    # só a planilha do mês mais recente é lida de novo (para os cargos); as outras, uma vez
    mes_max = max([_mes(c) or 0 for c, n, _ in lista if normalizar_nome(n).startswith("CONSULTA")] or [0])
    for caminho, nome, link in lista:
        am = _mes(caminho)
        if am is None or am < INICIO:
            continue
        a, m = am // 100, am % 100
        u = normalizar_nome(nome)
        if u.startswith("REMUNERACAO") and _id(link) not in feitos:
            linhas = _folha(_baixar(link, nome))
            if linhas:
                fol = _gravar(pd.concat([fol, pd.DataFrame([{"ano": a, "mes": m, "matricula": x, "nome": n, "proventos": v, "folha": _tipo_folha(nome),
                                                             "arquivo": link} for x, n, v in linhas])], ignore_index=True), arq_f,
                              ["ano", "mes", "matricula", "folha"], ["ano", "mes", "nome", "folha"])
                log(f"  ALE-RR: folha de {m:02d}/{a}: {len(linhas)} deputados")
        elif u.startswith("CONSULTA") and "SERVIDOR" in u:
            ultimo_mes = am >= mes_max
            if _id(link) in feitos and not ultimo_mes:
                continue
            df = _setores(_baixar(link, nome))
            if df is None:
                log(f"  ALE-RR: {nome} ({am}) sem a coluna Setor")
                continue
            g = df.assign(gab=df.setor.map(_gab)).dropna(subset=["gab"])
            if _id(link) not in feitos:
                novos = [{"ano": a, "mes": m, "gabinete": k, "pessoas": int(n), "arquivo": link} for k, n in g.groupby("gab").size().items()]
                if novos:
                    eq = _gravar(pd.concat([eq, pd.DataFrame(novos)], ignore_index=True), arq_e, ["ano", "mes", "gabinete"], ["ano", "mes", "gabinete"])
            if ultimo_mes:
                ultimo = (am, g)
    if ultimo is not None:
        am, g = ultimo
        cargo = g.cargo.map(lambda x: re.sub(r"^[A-Z]{1,5}-?[IVXL\d]+\s+", "", " ".join(str(x).split())).strip() or "Sem cargo informado")
        gravar_csv(g.assign(c=cargo).groupby(["gab", "c"]).size().reset_index().set_axis(["gabinete", "cargo", "pessoas"], axis=1)
                   .assign(ano=am // 100, mes=am % 100), PASTA / "equipe_cargos.csv")
    log(f"  ALE-RR: equipe e folha da página nova lidas (último mês da planilha de servidores: {ultimo[0] if ultimo else '-'})")


# ---------------------------------------------------------------- montagem
def _tipo(grupo, desc):
    d = grupo if re.match(r"(?i)geral\b", desc.strip()) else desc
    u = normalizar_nome(d)
    for rx, nome in ((r"GRAFIC", "Material gráfico (arte e impressão)"), (r"SOFTWARE|INTERNET|INFORMATICA", "Site e sistemas"),
                     (r"CONSUMO|EXPEDIENTE", "Material de escritório"), (r"EQUIPAMENTO", "Aluguel de móveis e equipamentos"),
                     (r"ALUGUEL|CONDOMINIO|IPTU|AGUA|ENERGIA|MANUTENCAO", "Escritório (aluguel e contas)"),
                     (r"TELEFONE", "Telefone e internet"), (r"CORRESPOND|SEDEX", "Correios"),
                     (r"IMPRENSA", "Assessoria de imprensa"), (r"CONTABIL", "Contabilidade"), (r"JURIDIC", "Assessoria jurídica"),
                     (r"CONSULTORIA", "Consultorias e assessorias"), (r"REVISTA|INFORMATIVO", "Assinaturas e livros"),
                     (r"DIVULGA", "Divulgação do mandato"), (r"SEGURAN", "Segurança"), (r"PESQUISA", "Pesquisas"),
                     (r"CURSO|PALESTRA|SEMINAR|CONGRESS", "Eventos, cursos e seminários")):
        if re.search(rx, u):
            return nome
    return vc.tipo_curto(d)


_ABREV = {"SD": "SOLDADO", "CEL": "CORONEL", "JR": "JUNIOR", "DR": "DOUTOR", "DRA": "DOUTORA", "PROF": "PROFESSOR", "PROFA": "PROFESSORA"}


def _dono_por_nome(ver, tse):
    """Nome do gabinete ("SD SAMPAIO", "DR METON") -> código do deputado: o nome de urna igual; senão o único deputado da lista
    com mais palavras em comum (fora títulos) no nome de urna ou no nome civil."""
    urna = {normalizar_nome(v["nome"]): v["codigo"] for v in ver}
    pal = {v["codigo"]: set(comum._palavras(v["nome"])) | set(comum._palavras(v["nome_civil"])) for v in ver}

    def dono(gab):
        x = " ".join(_ABREV.get(w, w) for w in normalizar_nome(gab).split())
        if x in urna:
            return urna[x]
        p = set(comum._palavras(x))
        if not p:
            return None
        pontos = {c: len(p & ps) for c, ps in pal.items()}
        melhor = max(pontos.values(), default=0)
        quem = [c for c, n in pontos.items() if n == melhor]
        return quem[0] if melhor >= 1 and len(quem) == 1 else None
    return dono


def _partido(civil, partidos):
    """Partido da candidatura de 2026 pelo nome civil; se o nome mudou (sobrenome a mais ou a menos), o único compatível."""
    if civil in partidos:
        return partidos[civil]
    achados = {p for n, p in partidos.items() if vc.compativel(n, civil) or vc.compativel(civil, n)}
    return achados.pop() if len(achados) == 1 else ""


def montar(tipos):
    arq_m, arq_f = PASTA / "verba_meses.csv", PASTA / "folha_deputados.csv"
    if not arq_m.exists() and not arq_f.exists():
        return None
    meses = pd.read_csv(arq_m) if arq_m.exists() else pd.DataFrame(columns=["ano", "mes", "deputado", "indenizado", "soma_parcial", "soma_itens"])
    itens = pd.read_csv(PASTA / "verba_itens.csv").fillna("") if (PASTA / "verba_itens.csv").exists() else \
        pd.DataFrame(columns=["ano", "mes", "deputado", "grupo", "descricao", "valor"])
    fol = _ler_folha()
    tse = comum.tse_2022(UF)
    por_civil = {normalizar_nome(x["nome"]): x for x in tse.values()}
    partidos = comum.partido_2026(UF)
    ultimo = vc.ultimo_mes_fechado()
    meses["am"] = meses.ano.astype(int) * 100 + meses.mes.astype(int)
    fol["am"] = fol.ano.astype(int) * 100 + fol.mes.astype(int)
    ultimo_dado = int(max(list(meses.am) + list(fol.am)))
    ult_folha = int(fol.am.max()) if len(fol) else 0
    # cada pessoa pelo nome civil (o da folha e o do quadro da verba são o nome completo)
    presenca = {}
    for n, am in list(zip(meses.deputado.map(normalizar_nome), meses.am)) + list(zip(fol.nome.map(normalizar_nome), fol.am)):
        presenca.setdefault(n, set()).add(int(am))
    ver, mandatos, cods, meses_cod = [], [], {}, {}
    for nome, ms in presenca.items():
        t = por_civil.get(nome) or comum.achar(nome, tse) or {}
        codigo = comum.codigo_de(nome, t)
        cods[nome] = codigo
        if codigo not in meses_cod:  # o mesmo deputado com duas grafias ("AURELINA MEDEIROS" e "AURELINA DE MEDEIROS") entra uma vez
            ver.append({"codigo": codigo, "nome": vc.titulo(t.get("urna") or nome), "nome_civil": vc.titulo(t.get("nome") or nome),
                        "partido": _partido(normalizar_nome(t.get("nome") or nome), partidos) or _partido(nome, partidos),
                        "genero": t.get("genero") or ("F" if feminino(nome) else "M"), "eleito": t.get("eleito", ""), "pagina": CFG["pagina"]})
        meses_cod.setdefault(codigo, set()).update(ms)
    for codigo, ms in meses_cod.items():
        for i, f in comum.periodos(sorted(ms), ultimo_dado, ultimo, folga=1):
            mandatos.append({"codigo": codigo, "inicio": i, "fim": f})
    mand = pd.DataFrame(mandatos, columns=["codigo", "inicio", "fim"])
    # salário: total de proventos da folha (até set/2025); depois, o subsídio da lei nos meses no cargo
    ganha = [{"ano": int(r.ano), "mes": int(r.mes), "codigo": cods[normalizar_nome(r.nome)],
              "categoria": "decimo_terceiro" if r.folha == "13" else "salario", "valor": float(r.proventos)} for r in fol.itertuples()]
    sub = lambda am: [v for d, v in CFG["subsidio"] if d <= am][-1]
    for codigo in set(cods.values()):
        for p in mand[mand.codigo == codigo].itertuples():
            ini = int(p.inicio[:4]) * 100 + int(p.inicio[5:7])
            fim = int(p.fim[:4]) * 100 + int(p.fim[5:7]) if isinstance(p.fim, str) and p.fim else ultimo
            for a, m in vc.meses(max(ini, INICIO, vc.mes_seguinte(ult_folha)), min(fim, ultimo)):
                ganha.append({"ano": a, "mes": m, "codigo": codigo, "categoria": "salario", "valor": sub(a * 100 + m)})
    # verba: os itens do quadro e, quando a despesa indenizada é menor que a soma, a diferença (negativa)
    desp = [{"ano": r.ano, "mes": r.mes, "codigo": cods[normalizar_nome(r.deputado)], "tipo": _tipo(r.grupo, r.descricao), "fornecedor": "",
             "cnpj_cpf": "", "valor": float(r.valor)} for r in itens.itertuples()]
    for r in meses.itertuples():
        total = r.indenizado if pd.notna(r.indenizado) else (r.soma_parcial if pd.notna(r.soma_parcial) else r.soma_itens)
        dif = round(float(total) - float(r.soma_itens), 2)
        if abs(dif) >= 0.01:
            desp.append({"ano": r.ano, "mes": r.mes, "codigo": cods[normalizar_nome(r.deputado)], "tipo": "Acima da cota (não ressarcido)",
                         "fornecedor": "", "cnpj_cpf": "", "valor": dif})
    # equipe: o setor "GAB DEP ANGELA PORTELLA" é do deputado com esse nome de urna (ou do único eleito com essas palavras no nome)
    dono = _dono_por_nome(ver, tse)
    equipe = cargos = None
    if (PASTA / "equipe.csv").exists():
        eq = pd.read_csv(PASTA / "equipe.csv")
        eq["codigo"] = eq.gabinete.map(dono)
        sem = sorted(set(eq[eq.codigo.isna()].gabinete))
        if sem:
            log(f"  ALE-RR: gabinetes sem deputado: {sem}")
        eq = eq.dropna(subset=["codigo"])
        equipe = pd.DataFrame({"ano": eq.ano, "mes": eq.mes, "codigo": eq.codigo.astype(int), "pessoas": eq.pessoas, "custo": ""})
    equipe_em = ""
    if (PASTA / "equipe_cargos.csv").exists():
        cg = pd.read_csv(PASTA / "equipe_cargos.csv")
        if len(cg):  # os cargos são os da planilha de servidores do mês mais recente
            am = int((cg.ano * 100 + cg.mes).max())
            equipe_em = f"{am % 100:02d}/{am // 100}"
        cg["codigo"] = cg.gabinete.map(dono)
        cg = cg.dropna(subset=["codigo"])
        cargos = cg.assign(codigo=cg.codigo.astype(int)).groupby(["codigo", "cargo"]).pessoas.sum().reset_index()
    cfg = dict(CFG, ultimo_mes=min(ultimo, ultimo_dado), equipe_em=equipe_em)
    return vc.montar(cfg, tipos, pd.DataFrame(ver), mand, ganha=pd.DataFrame(ganha, columns=["ano", "mes", "codigo", "categoria", "valor"]),
                     despesas=pd.DataFrame(desp, columns=["ano", "mes", "codigo", "tipo", "fornecedor", "cnpj_cpf", "valor"]), equipe=equipe, cargos=cargos)
