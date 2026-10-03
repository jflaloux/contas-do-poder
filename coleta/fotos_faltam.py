"""Fotos para quem ainda não tem no site: Wikidata/Wikimedia Commons (licença livre) e as fotos das candidaturas no TSE.

Quem não tem foto sai dos arquivos do site (o campo "f" vazio ou o arquivo inexistente): governo federal, Judiciário,
governadores e vices, deputados estaduais, vereadores e prefeituras das capitais. Para cada pessoa:

1. Wikidata: a busca pelo nome curto e pelo nome civil; vale o item de um ser humano (P31 Q5) brasileiro (P27 Q155),
   com foto (P18), cujo rótulo ou apelido é exatamente o nome curto ou o civil, e com o cargo ou a profissão do grupo
   (P39 ou P106: ministro, juiz, político, deputado...). Dois itens assim (homônimos): fica sem foto. A licença é
   conferida no próprio Commons (CC BY, CC BY-SA, CC0, domínio público; nunca "ND", porque o corte é obra derivada).
   Foto mais larga que alta: o retrato sai do centro (marcada "cortada" no crédito).
2. TSE (CC BY, coleta/fotos_tse.py): quem foi candidato em 2024 (vereador, prefeito, vice) ou em 2022 (governador a
   deputado), quando o nome civil é exatamente o de um único candidato do lugar.

As fotos vão para site/fotos/<id>.webp (240×320, como as outras) com o crédito em site/fotos/creditos.json. Depois, só
"f" e "fc" mudam nos arquivos do site (preencher()), sem refazer os arquivos inteiros. Quem não tem foto aceitável só é
procurado de novo depois de 30 dias (creditos.json, "procurado_em").

Uso: python3 -m coleta.fotos_faltam [lista|wikidata|tse|preencher] [grupo ...] [--forcar]
"""
import json
import re
import sys
import time

from . import fotos as F
from .config import RAIZ
from .util import TempoEsgotado, log, normalizar_nome

SITE = RAIZ / "site" / "dados"
# o que o cargo (P39) ou a profissão (P106) do item precisa ter, por grupo
PAPEL = {
    "judiciario": re.compile(r"minist|juiz|juíz|judge|jurist|magistr|desembarg|procurador|prosecutor|conselheir|advogad|lawyer|"
                             r"presid|tribunal|court", re.I),
    "executivo": re.compile(r"minist|secret|presid|polític|politic|econom|chefe", re.I),
    "governadores": re.compile(r"governad|vice|polític|politic|deputad|juiz|judge|desembarg|presid", re.I),
    "assembleias": re.compile(r"deputad|polític|politic|vereador|prefeit|secret", re.I),
    "camaras": re.compile(r"vereador|polític|politic|deputad|prefeit|secret", re.I),
    "prefeituras": re.compile(r"prefeit|secret|polític|politic|vereador|deputad|vice", re.I),
}
# as licenças de fotos.py, mais "Attribution" (a predefinição do Commons de uso livre com crédito, que o STF e outros usam)
LICENCA_OK = re.compile(F.LICENCA_OK.pattern + r"|^attribution$", re.I)
# fotos conferidas a olho e recusadas (a do Wikidata não serve): {id: motivo}
RECUSADAS = {
    "jud-tst-jose-roberto-freire-pimenta": "foto de grupo (Ministros TST.jpg): não dá para saber quem é ele",
}
TSE_CARGOS_2024 = ("11", "12", "13")  # prefeito, vice, vereador
TSE_CARGOS_2022 = ("3", "4", "5", "6", "7", "8")  # governador, vice, senador, deputado federal, estadual, distrital
UF_MUNICIPIO = {}  # código IBGE -> (nome, UF), de municipios.json


def _tem(f):
    return bool(f) and (RAIZ / "site" / f).exists()


def lista():
    """{grupo: [{id, n, nc, uf, cid, x}]} de quem não tem foto, nos arquivos do site."""
    sem = {g: [] for g in PAPEL}
    for p in json.loads((SITE / "dados.json").read_text(encoding="utf-8"))["p"]:
        if p["k"] == "e" and not _tem(p.get("f")):
            sem["executivo"].append({"id": p["id"], "n": p["n"], "nc": p.get("nc"), "uf": p.get("uf"), "x": int(p.get("x") or 0)})
    for p in json.loads((SITE / "judiciario.json").read_text(encoding="utf-8"))["p"]:
        if not _tem(p.get("f")) and not (p["org"] == "TSE" and p.get("rel")):  # quem vem do STF/STJ usa a foto da outra página
            sem["judiciario"].append({"id": p["id"], "n": p["n"], "nc": p.get("nc"), "x": int(p.get("x") or 0), "org": p["org"]})
    vistos = set()
    for e in json.loads((SITE / "governadores.json").read_text(encoding="utf-8"))["e"]:
        for o in e["oc"]:
            if o["id"] not in vistos and not _tem(o.get("f")):
                vistos.add(o["id"])
                sem["governadores"].append({"id": o["id"], "n": o["n"], "nc": o.get("nc"), "uf": e["uf"], "x": 0 if o.get("ate") else 1})
    for arq, g in (("assembleias.json", "assembleias"), ("camaras.json", "camaras"), ("prefeituras.json", "prefeituras")):
        for p in json.loads((SITE / arq).read_text(encoding="utf-8"))["p"]:
            if not _tem(p.get("f")):
                sem[g].append({"id": p["id"], "n": p["n"], "nc": p.get("nc"), "uf": p.get("uf"), "cid": p.get("cid"),
                               "x": int(p.get("x") or 0), "g": p.get("g")})
    return sem


# ------------------------------------------------------------------------------------------------- Wikidata/Commons
def _valores(c, prop):
    return [x.get("mainsnak", {}).get("datavalue", {}).get("value") for x in c.get(prop, [])]


def _ids(c, prop):
    return [v.get("id") for v in _valores(c, prop) if isinstance(v, dict) and v.get("id")]


def achar(p, grupo):
    """(QID, arquivo do P18) do único item que bate com a pessoa; None se não houver ou se houver homônimos."""
    nomes = {normalizar_nome(n) for n in (p.get("n"), p.get("nc")) if n}
    candidatos = []
    for busca in dict.fromkeys(n for n in (p.get("nc"), p.get("n")) if n):
        candidatos += [x["id"] for x in F._api(F.WIKIDATA, action="wbsearchentities", search=busca, language="pt", limit=7,
                                                type="item").get("search", [])]
    candidatos = list(dict.fromkeys(candidatos))
    if not candidatos:
        return None
    ents = F._api(F.WIKIDATA, action="wbgetentities", ids="|".join(candidatos[:50]), props="claims|labels|aliases|descriptions",
                  languages="pt|pt-br|en")["entities"]
    civil = set(normalizar_nome(p.get("nc") or "").split())
    bons = []
    for qid in candidatos:
        e = ents.get(qid, {})
        c = e.get("claims", {})
        rotulos = {normalizar_nome(v["value"]) for v in e.get("labels", {}).values()}
        rotulos |= {normalizar_nome(a["value"]) for vs in e.get("aliases", {}).values() for a in vs}
        descricao = " ".join(v["value"] for v in e.get("descriptions", {}).values())
        # o nome: igual ao curto ou ao civil; ou o rótulo é o civil abreviado (todas as palavras, pelo menos 3, estão nele)
        nome_ok = bool(rotulos & nomes) or any(len(r.split()) >= 3 and set(r.split()) <= civil for r in rotulos)
        # brasileiro: P27 Brasil; ou a descrição diz (o P27 às vezes falta ou traz só outra cidadania)
        brasil = "Q155" in _ids(c, "P27") or bool(re.search(r"brazil|brasileir", descricao, re.I)) or \
            (not _ids(c, "P27") and any(len(r.split()) >= 3 and r == normalizar_nome(p.get("nc") or "") for r in rotulos))
        if "Q5" not in _ids(c, "P31") or not brasil or not nome_ok:
            continue
        fotos = [v for v in _valores(c, "P18") if v]
        papeis = F._nomes_cargos((_ids(c, "P39") + _ids(c, "P106"))[:50])
        if any(PAPEL[grupo].search(n) for n in papeis + [descricao]):
            bons.append((qid, fotos[-1] if fotos else None))
    if len(bons) != 1:
        if len(bons) > 1:
            log(f"  {p['n']}: {len(bons)} itens no Wikidata com o mesmo nome e cargo (homônimos): sem foto")
        return None
    return bons[0] if bons[0][1] else None


def baixar_commons(pid, qid, arquivo):
    """Baixa, ajusta e grava a foto e o crédito. Devolve o motivo de não usar, ou None se usou."""
    f = F._commons(arquivo, 330)
    if not f["url"] or not LICENCA_OK.search(f["licenca"] or ""):
        return f"licença {f['licenca'] or 'desconhecida'}"
    larga = f["altura"] < 0.95 * f["largura"]
    if larga:
        if f["largura"] > 2.2 * f["altura"]:
            return "foto panorâmica"
        f = F._commons(arquivo, 900)  # o retrato sai do centro de uma foto mais larga: pega uma versão maior
    time.sleep(1.1)
    import requests
    r = requests.get(f["url"], headers=F._ua, timeout=60)
    if r.status_code == 429:
        raise F.WikimediaLimitou()
    r.raise_for_status()
    (F.PASTA / f"{pid}.webp").write_bytes(F._ajustar(r.content))
    dados = F.ler_json(F.CREDITOS)
    dados["fotos"][pid] = {"wikidata": qid, "arquivo": arquivo, **{k: f[k] for k in ("autor", "licenca", "url_licenca", "pagina")},
                           **({"cortada": True} if larga else {})}
    F.salvar_json(F.CREDITOS, dados)
    return None


def wikidata(grupos=None, limite=None, forcar=False):
    """forcar: procura também quem foi procurado nos últimos 30 dias (as regras de busca mudaram)."""
    sem = lista()
    dados = F.ler_json(F.CREDITOS)
    tentou = dados.setdefault("procurado_em", {})
    antes = time.strftime("%Y-%m-%d", time.localtime(time.time() - 30 * 86400))
    hoje = time.strftime("%Y-%m-%d")
    novas, buscas, motivos = {}, 0, {}
    try:
        for grupo, pessoas in sem.items():
            if grupos and grupo not in grupos:
                continue
            for p in pessoas:
                if (F.PASTA / f"{p['id']}.webp").exists() or p["id"] in RECUSADAS or (not forcar and tentou.get(p["id"], "0000") > antes):
                    continue
                if limite is not None and buscas >= limite:
                    raise StopIteration
                buscas += 1
                t0 = time.time()
                try:
                    achou = achar(p, grupo)
                    motivo = "sem item com foto no Wikidata" if not achou else baixar_commons(p["id"], *achou)
                except (TempoEsgotado, F.WikimediaLimitou):
                    raise
                except Exception as e:  # noqa: BLE001 — foto é opcional
                    motivo = f"erro: {e}"
                dados = F.ler_json(F.CREDITOS)
                dados.setdefault("procurado_em", {})[p["id"]] = hoje
                tentou = dados["procurado_em"]
                F.salvar_json(F.CREDITOS, dados)
                log(f"  {grupo} {p['n']}: {'foto nova' if motivo is None else motivo} ({time.time() - t0:.0f} s)")
                if motivo is None:
                    novas.setdefault(grupo, []).append(p["id"])
                else:
                    motivos[motivo.split(":")[0]] = motivos.get(motivo.split(":")[0], 0) + 1
    except StopIteration:
        pass
    except F.WikimediaLimitou:
        log("  A Wikimedia pediu para ir mais devagar; o resto fica para a próxima vez.")
    log(f"Fotos (Wikidata): {sum(len(v) for v in novas.values())} novas {({k: len(v) for k, v in novas.items()})}; sem foto: {motivos}")
    return novas


# ------------------------------------------------------------------------------------------------------------ TSE
def tse(grupos=None):
    from . import fotos_tse
    mun = json.loads((SITE / "municipios.json").read_text(encoding="utf-8"))["m"]
    nome_mun = {int(m[0]): (m[1], m[2]) for m in mun}
    sem = lista()
    novas = {}

    def rodar(grupo, ano, cargos, por_lugar):
        """por_lugar: {(uf, município ou None): [pessoas]}."""
        for (uf, municipio), pessoas in por_lugar.items():
            faltam = [{"id": p["id"], "nc": p.get("nc"), "n": p.get("n")} for p in pessoas if not (F.PASTA / f"{p['id']}.webp").exists()]
            if not faltam or not uf:
                continue
            try:
                n = fotos_tse.por_nome(ano, uf, faltam, cargos, municipio=municipio)
            except TempoEsgotado:
                raise
            except Exception as e:  # noqa: BLE001
                log(f"  TSE {ano} {uf} {municipio or ''}: {e}")
                n = 0
            if n:
                novas[grupo] = novas.get(grupo, 0) + n

    for grupo in ("camaras", "prefeituras"):
        if grupos and grupo not in grupos:
            continue
        por = {}
        for p in sem[grupo]:
            cid = int(p.get("cid") or 0)
            if cid in nome_mun:
                por.setdefault((nome_mun[cid][1], nome_mun[cid][0]), []).append(p)
        rodar(grupo, 2024, TSE_CARGOS_2024, por)
        rodar(grupo, 2022, TSE_CARGOS_2022, {(uf, None): ps for (uf, _), ps in por.items()})
    for grupo in ("assembleias",):
        if grupos and grupo not in grupos:
            continue
        por = {}
        for p in sem[grupo]:
            por.setdefault((p.get("uf"), None), []).append(p)
        rodar(grupo, 2022, TSE_CARGOS_2022, por)
        rodar(grupo, 2024, TSE_CARGOS_2024, por)
    log(f"Fotos (TSE): {novas}")
    return novas


# ----------------------------------------------------------------------------------------------- arquivos do site
def _fc(credito):
    return {"a": credito.get("autor"), "l": credito.get("licenca"), "u": credito.get("pagina"), **({"r": 1} if credito.get("cortada") else {})}


def preencher():
    """Põe f/fc de quem ganhou foto nos arquivos do site, sem refazer o resto (o judiciario.json é refeito pelo próprio
    montador, que só lê os CSVs e a composição)."""
    creditos = F.ler_json(F.CREDITOS).get("fotos", {})
    mudou = {}

    def acerto(p, pid=None):
        pid = pid or p["id"]
        if _tem(p.get("f")) or not (F.PASTA / f"{pid}.webp").exists() or pid not in creditos:
            return False
        p["f"], p["fc"] = f"fotos/{pid}.webp", _fc(creditos[pid])
        return True

    for arq in ("dados.json", "assembleias.json", "camaras.json", "prefeituras.json"):
        d = json.loads((SITE / arq).read_text(encoding="utf-8"))
        n = sum(acerto(p) for p in d["p"] if arq != "dados.json" or p["k"] == "e")
        if n:
            (SITE / arq).write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            mudou[arq] = n
    g = json.loads((SITE / "governadores.json").read_text(encoding="utf-8"))
    n = 0
    for e in g["e"]:
        for o in [e["gov"], e.get("vice"), *e["oc"]]:
            if o:
                n += acerto(o)
    if n:
        (SITE / "governadores.json").write_text(json.dumps(g, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        mudou["governadores.json"] = n
    from .judiciario import site as jsite
    antes = sum(1 for p in json.loads((SITE / "judiciario.json").read_text(encoding="utf-8"))["p"] if p.get("f"))
    jsite.escrever(baixar_fotos=False)
    depois = sum(1 for p in json.loads((SITE / "judiciario.json").read_text(encoding="utf-8"))["p"] if p.get("f"))
    if depois != antes:
        mudou["judiciario.json"] = depois - antes
    log(f"Fotos nos arquivos do site: {mudou}")
    return mudou


if __name__ == "__main__":
    acao = sys.argv[1] if len(sys.argv) > 1 else "lista"
    grupos = {a for a in sys.argv[2:] if not a.startswith("-")} or None
    if acao == "lista":
        for g, ps in lista().items():
            print(f"{g}: {len(ps)} sem foto ({sum(p['x'] for p in ps)} no cargo)")
    elif acao == "wikidata":
        wikidata(grupos, forcar="--forcar" in sys.argv)
    elif acao == "tse":
        tse(grupos)
    elif acao == "preencher":
        preencher()
