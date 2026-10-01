"""Parte comum dos robôs das Assembleias Legislativas.

- tse_2022(uf): eleitos e suplentes a deputado estadual (ou distrital) em 2022, do arquivo de candidatos do TSE
  (nome de urna, nome civil, partido, gênero, situação), para completar o que a Assembleia não publica.
- achar(nome, tse): o candidato pelo nome parlamentar (igual, ou compatível quando um dos dois vem abreviado).
- escrever(): junta os estados em site/dados/assembleias.json, no mesmo formato de site/dados/camaras.json (com
  "estados" no lugar de "cidades") e busca as fotos com licença livre no Wikimedia Commons, como nas prefeituras.
"""
import csv
import io
import json
import re
import zipfile
from datetime import datetime

from ..config import CACHE, RAIZ
from ..util import TempoEsgotado, baixar, log, normalizar_nome

SAIDA = RAIZ / "site" / "dados" / "assembleias.json"
TSE = "https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/consulta_cand_2022.zip"
TSE_ZIP = CACHE / "assembleias" / "consulta_cand_2022.zip"
CODIGOS_UF = {"RO": 11, "AC": 12, "AM": 13, "RR": 14, "PA": 15, "AP": 16, "TO": 17, "MA": 21, "PI": 22, "CE": 23, "RN": 24, "PB": 25,
              "PE": 26, "AL": 27, "SE": 28, "BA": 29, "MG": 31, "ES": 32, "RJ": 33, "SP": 35, "PR": 41, "SC": 42, "RS": 43, "MS": 50,
              "MT": 51, "GO": 52, "DF": 53}


def tse_2022(uf):
    """{nome de urna normalizado: {...}} dos candidatos a deputado estadual/distrital eleitos ou suplentes em 2022."""
    if not TSE_ZIP.exists():
        TSE_ZIP.parent.mkdir(parents=True, exist_ok=True)
        log("Assembleias: arquivo de candidatos de 2022 do TSE (~4 MB)")
        TSE_ZIP.write_bytes(baixar(TSE, timeout=300).content)
    saida = {}
    with zipfile.ZipFile(TSE_ZIP) as z, z.open(f"consulta_cand_2022_{uf}.csv") as f:
        for l in csv.DictReader(io.TextIOWrapper(f, encoding="latin1"), delimiter=";"):
            if l["CD_CARGO"] not in ("7", "8") or l["NR_TURNO"] != "1":
                continue
            sit = l["DS_SIT_TOT_TURNO"]
            if not (sit.startswith("ELEITO") or sit == "SUPLENTE"):
                continue
            saida[normalizar_nome(l["NM_URNA_CANDIDATO"])] = {
                "sq": l["SQ_CANDIDATO"], "urna": l["NM_URNA_CANDIDATO"].strip(), "nome": l["NM_CANDIDATO"].strip(), "partido": l["SG_PARTIDO"].strip(),
                "genero": "F" if l["DS_GENERO"].upper().startswith("FEM") else "M", "eleito": "eleito" if sit.startswith("ELEITO") else "suplente"}
    return saida


_TITULOS = {"DR", "DRA", "DOUTOR", "DOUTORA", "PROF", "PROFA", "PROFESSOR", "PROFESSORA", "DELEGADO", "DELEGADA", "CAPITAO", "CORONEL",
            "TENENTE", "PASTOR", "PASTORA", "AGENTE", "FEDERAL", "SARGENTO", "SOLDADO", "MAJOR", "CABO", "BISPO", "IRMAO", "IRMA", "DO", "DA",
            "DE", "DOS", "DAS", "E", "CEL", "CAP", "SGT", "TEN", "DEP", "DEPUTADO", "DEPUTADA", "JUNIOR", "FILHO", "NETO"}


def _palavras(nome):
    return [w for w in re.sub(r"[^A-Z ]", " ", normalizar_nome(nome)).split() if w not in _TITULOS and len(w) > 1]


def achar(nome, tse):
    """O candidato pelo nome parlamentar: igual; ou compatível (um dos dois abreviado); ou, por último, o único eleito ou
    suplente cujo nome de urna ou nome civil tem pelo menos duas das palavras do nome parlamentar (sem títulos)."""
    from ..vereadores.comum import compativel
    n = normalizar_nome(nome)
    if n in tse:
        return tse[n]
    achados = list({(v.get("sq") or v.get("mat") or v["nome"]): v for k, v in tse.items() if compativel(n, k) or compativel(n, normalizar_nome(v["nome"]))}.values())
    if len(achados) == 1:
        return achados[0]
    p = set(_palavras(nome))
    if len(p) == 1:  # um nome só ("Hashioka", "Cel. David"): vale se só um eleito tem essa palavra no nome
        unico = list({(v.get("sq") or v.get("mat") or v["nome"]): v for v in tse.values()
                      if v["eleito"] == "eleito" and p & (set(_palavras(v["urna"])) | set(_palavras(v["nome"])))}.values())
        return unico[0] if len(unico) == 1 else None
    if len(p) < 2:
        return None
    melhor = {}
    for v in tse.values():
        comuns = max(len(p & set(_palavras(v["urna"]))), len(p & set(_palavras(v["nome"]))))
        if comuns >= 2:
            melhor.setdefault(comuns, []).append(v)
    if not melhor:
        return None
    topo = list({(v.get("sq") or v.get("mat") or v["nome"]): v for v in melhor[max(melhor)]}.values())  # a mesma pessoa por dois nomes conta uma vez
    eleitos = [v for v in topo if v["eleito"] == "eleito"]
    return topo[0] if len(topo) == 1 else (eleitos[0] if len(eleitos) == 1 else None)


TSE_2026 = CACHE / "assembleias" / "consulta_cand_2026.zip"


def partido_2026(uf):
    """{nome civil normalizado: partido} de quem se candidatou em 2026 no estado (o partido de hoje, depois da janela
    partidária). Só o nome e o partido são lidos do arquivo do TSE."""
    if not TSE_2026.exists():
        TSE_2026.parent.mkdir(parents=True, exist_ok=True)
        TSE_2026.write_bytes(baixar(TSE.replace("2022", "2026"), timeout=300).content)
    saida = {}
    with zipfile.ZipFile(TSE_2026) as z, z.open(f"consulta_cand_2026_{uf}.csv") as f:
        for l in csv.DictReader(io.TextIOWrapper(f, encoding="latin1"), delimiter=";"):
            saida[normalizar_nome(l["NM_CANDIDATO"])] = l["SG_PARTIDO"].strip()
    return saida


def periodos(meses_com_dados, ultimo_dado, ultimo_mes, folga=2):
    """Meses (AAAAMM) em que o deputado aparece nos dados -> períodos no cargo [(inicio, fim)] (texto AAAA-MM-DD).
    Buracos de até `folga` meses entre dois meses com dados contam como meses no cargo (só não houve reembolso), e quem
    aparece num dos `folga` últimos meses com dados continua no cargo (período sem fim)."""
    from ..vereadores.comum import mes_seguinte, periodos_de_meses
    ms = sorted(set(int(x) for x in meses_com_dados))
    cheios = set(ms)
    for a, b in zip(ms, ms[1:]):
        x, passos = mes_seguinte(a), 0
        while x < b and passos < folga:
            x, passos = mes_seguinte(x), passos + 1
        if x == b:
            x = mes_seguinte(a)
            while x < b:
                cheios.add(x)
                x = mes_seguinte(x)
    recente = ms and ms[-1] >= _menos(ultimo_dado, folga - 1)
    if recente:  # no cargo até hoje
        x = ms[-1]
        while x < ultimo_mes:
            x = mes_seguinte(x)
            cheios.add(x)
    return periodos_de_meses(sorted(cheios), ultimo_mes, aberto=bool(recente))


def _menos(am, n):
    from ..vereadores.comum import menos_meses
    return menos_meses(am, n)


def codigo_de(nome, tse_info):
    """Número estável para quem não tem matrícula nos dados abertos: o SQ do candidato no TSE (ou um CRC do nome)."""
    import zlib
    if tse_info and tse_info.get("sq", "").isdigit():
        return int(tse_info["sq"])
    return zlib.crc32(normalizar_nome(nome).encode())


def _fotos_tse(pessoas):
    """Foto da candidatura de 2022 no TSE (coleta/fotos_tse.py) para quem ainda não tem foto: só quando o nome civil do
    deputado é exatamente o de um único candidato a deputado estadual (ou distrital) da UF."""
    from .. import fotos_tse
    por_uf = {}
    for p in pessoas:
        por_uf.setdefault(p["uf"], []).append(p)
    return sum(fotos_tse.por_nome(2022, uf, ps, ("7", "8")) for uf, ps in por_uf.items())


def _fotos(pessoas):
    """Fotos com licença livre no Wikimedia Commons (as mesmas regras do governo federal e das prefeituras)."""
    from .. import fotos as F
    antigo = F.CARGO_OK
    F.CARGO_OK = re.compile(r"deputad|politic|polític|legislat", re.I)
    try:
        return F._governo_commons([{"id": p["id"], "nome": p["n"], "nome_civil": p["nc"], "casa": "executivo"} for p in pessoas if p["x"]], limite=40)
    finally:
        F.CARGO_OK = antigo


def escrever(resultados, tipos, baixar_fotos=True):
    """resultados: [(meta, pessoas), ...] -> site/dados/assembleias.json."""
    todas = [p for _, ps in resultados for p in ps]
    if baixar_fotos and todas:
        try:
            novas = _fotos_tse([p for p in todas if p["x"]])
            if novas:
                log(f"  {novas} fotos novas de deputados estaduais (candidatura de 2022 no TSE)")
            novas = _fotos(todas)
            if novas:
                log(f"  {novas} fotos novas de deputados estaduais (Wikimedia Commons)")
        except TempoEsgotado:
            raise
        except Exception as e:  # noqa: BLE001 — foto é opcional
            log(f"  Fotos das Assembleias: {e}")
    from ..fotos import CREDITOS
    creditos = json.loads(CREDITOS.read_text(encoding="utf-8")).get("fotos", {}) if CREDITOS.exists() else {}
    for p in todas:
        arq = RAIZ / "site" / "fotos" / f"{p['id']}.webp"
        c = creditos.get(p["id"])
        if arq.exists() and c and c.get("arquivo"):
            p["f"] = f"fotos/{p['id']}.webp"
            p["fc"] = {"a": c.get("autor"), "l": c.get("licenca"), "u": c.get("pagina")}
    dados = {"meta": {"gerado_em": datetime.now().isoformat(timespec="seconds"), "tipos": tipos.lista,
                      "categorias": {"verba_gabinete": {"grupo": "custa", "nome": "Verba do gabinete"}},
                      "estados": {meta["uf"]: meta for meta, ps in resultados if ps}},
             "p": todas}
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log(f"Site: {SAIDA.relative_to(RAIZ)} ({SAIDA.stat().st_size / 1e3:.0f} KB, {len(resultados)} estados, {len(todas)} deputados)")
    return dados
