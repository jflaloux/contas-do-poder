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


# Quem está em exercício hoje. A folha e a verba dizem quem recebeu em cada mês, mas não quem está no cargo: o titular
# licenciado (secretário de Estado, licença de saúde) pode continuar na folha, o suplente pode ficar na folha do mês em
# que o titular voltou, e quem não prestou contas nos últimos meses continua no cargo. Onde a Assembleia publica a lista
# de quem está em exercício, ela decide o "no cargo" de hoje (aplicar_hoje); a folha e a verba dizem desde quando.
EM_EXERCICIO = "em_exercicio.csv"


def gravar_em_exercicio(pasta, nomes, vagas, fonte):
    """Grava a lista oficial de quem está em exercício hoje (nomes como a Assembleia escreve). Só grava se a lista parece
    inteira (entre 80% e 120% das vagas): uma página quebrada não tira ninguém do cargo nem põe ninguém."""
    import time
    nomes = sorted({" ".join(str(n).split()) for n in nomes if str(n).strip()})
    if not (0.8 * vagas <= len(nomes) <= 1.2 * vagas):
        log(f"  lista de quem está em exercício com {len(nomes)} nomes para {vagas} vagas: fica a que já estava gravada")
        return
    with open(pasta / EM_EXERCICIO, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["nome", "visto_em", "fonte"])
        for n in nomes:
            w.writerow([n, time.strftime("%Y-%m-%d"), fonte])


def ler_em_exercicio(pasta):
    """[nomes] da lista oficial gravada, ou None (sem lista: o "no cargo" sai só da folha e da verba)."""
    arq = pasta / EM_EXERCICIO
    if not arq.exists():
        return None
    with open(arq, encoding="utf-8") as f:
        return [l["nome"] for l in csv.DictReader(f)] or None


def casar_em_exercicio(nomes, ver, uf, apelidos=None):
    """{codigo: True/False} de cada pessoa de `ver` (dicts com codigo, nome, nome_civil) pela lista oficial `nomes`
    (o nome parlamentar, comparado com o nome, o nome civil e o nome de urna do TSE; `apelidos`: {nome da lista: nome
    civil} para quem mudou de nome parlamentar)."""
    apelidos = {normalizar_nome(k): v for k, v in (apelidos or {}).items()}
    nomes = [re.sub(r"[´'`’]", "", apelidos.get(normalizar_nome(n), n)) for n in nomes]  # "Kaká D´Ávila" = "Kaká dÁvila"
    tse = tse_2022(uf)
    alvos = {}
    for v in ver:
        t = achar(v["nome"], tse) or {}
        for n in {v["nome"], v.get("nome_civil") or "", t.get("urna", ""), t.get("nome", "")} - {""}:
            alvos.setdefault(normalizar_nome(re.sub(r"[´'`’]", "", n)), {"nome": v.get("nome_civil") or v["nome"], "urna": v["nome"], "eleito": "eleito", "mat": v["codigo"]})
    atual, sem = {}, []
    for n in nomes:
        a = achar(n, alvos)
        if a:
            atual[a["mat"]] = True
        else:
            sem.append(n)
    if sem:
        log(f"  {uf}: em exercício pela lista da Assembleia, sem dados nossos: {', '.join(sem)}")
    return {v["codigo"]: atual.get(v["codigo"], False) for v in ver}


def aplicar_hoje(mandatos, atual, ultimo_dado, fins=None, folga=2, pagos=()):
    """Acerta os períodos (lista de dicts codigo/inicio/fim, fim "" = no cargo) pela lista oficial de hoje. Quem está fora
    da lista e em `pagos` (o licenciado que continua recebendo da Casa) fica com o período aberto: quem tira essa pessoa
    do "no cargo" é cfg["fora_hoje"] (fora_hoje(atual)), no vereadores.comum.montar.
    - na lista e sem período aberto: está no cargo, só não aparece nos últimos meses. Se o último período acabou há até
      `folga` meses do último mês com dados, ele fica aberto; se acabou antes, um período novo começa no último mês com
      dados (o tempo no meio, sem dado nenhum, fica de fora, como antes);
    - fora da lista e com período aberto: o período fecha na data que a Assembleia publica (`fins`, {codigo: "AAAA-MM-DD"})
      ou, sem ela, no fim do último mês com dados.
    Sem lista (atual None), nada muda."""
    from calendar import monthrange
    if not atual:
        return mandatos
    fins = fins or {}
    a, m = divmod(int(ultimo_dado), 100)
    fim_dados = f"{a}-{m:02d}-{monthrange(a, m)[1]:02d}"
    limite = _menos(int(ultimo_dado), folga + 1)
    por_cod = {}
    for p in mandatos:
        por_cod.setdefault(p["codigo"], []).append(p)
    for cod, ps in por_cod.items():
        if cod not in atual:
            continue
        ps.sort(key=lambda p: p["inicio"])
        aberto = [p for p in ps if not (isinstance(p["fim"], str) and p["fim"].strip())]
        if (atual[cod] or cod in pagos) and not aberto:  # no cargo, ou licenciado e recebendo: o período continua
            if int(str(ps[-1]["fim"])[:7].replace("-", "")) >= limite:
                ps[-1]["fim"] = ""
            else:
                mandatos.append({**ps[-1], "inicio": f"{a}-{m:02d}-01", "fim": ""})
        elif not atual[cod] and aberto and cod not in pagos:
            for p in aberto:
                fim = fins.get(cod) or fim_dados
                p["fim"] = max(fim, p["inicio"])
    return mandatos


def fora_hoje(atual):
    """Para cfg["fora_hoje"]: os códigos que a lista oficial não mostra em exercício hoje."""
    return {c for c, a in (atual or {}).items() if not a}


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
