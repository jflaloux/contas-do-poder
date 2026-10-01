"""Fotos oficiais dos parlamentares, guardadas no próprio site: site/fotos/{id}.webp (240×320).

Por que guardar aqui: a imagem para compartilhar é desenhada no navegador (canvas), e o site da
Câmara não deixa outro endereço usar as fotos dele num canvas (CORS). De quebra, a página carrega
mais rápido e não depende do site oficial para mostrar as fotos.

Só baixa as fotos que ainda não existem. Se uma foto falhar, o site usa o endereço oficial.

Governo federal: ministro que é deputado ou senador usa a foto oficial do Congresso. Os outros não têm
foto em dados abertos; buscamos no Wikidata/Wikimedia Commons, só com licença livre (CC BY, CC BY-SA,
CC0 ou domínio público) e com o crédito do autor guardado em site/fotos/creditos.json (o site mostra).
Para não pegar a foto errada: a pessoa no Wikidata precisa ser brasileira e ter ocupado um cargo de
ministro, presidente ou vice; e a foto precisa ser um retrato (mais alta que larga).
Quem o Wikidata não resolve pode ter a foto escolhida à mão em dados/referencia/fotos_governo.json (arquivo do
Commons e, se preciso, o corte), com as mesmas regras de licença.
"""
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

from PIL import Image

from .config import PARALELO, PROCESSADOS, RAIZ
from .util import TempoEsgotado, baixar, ler_json, log, salvar_json

PASTA = RAIZ / "site" / "fotos"
CREDITOS = PASTA / "creditos.json"
WIKIDATA = "https://www.wikidata.org/w/api.php"
COMMONS = "https://commons.wikimedia.org/w/api.php"
CARGO_OK = re.compile(r"minist|presid|advogad|attorney general|chefe", re.I)
LICENCA_OK = re.compile(r"^(cc[ -]by(?![ -]*nd)|cc0|public domain|dom[ií]nio p[uú]blico|pd)", re.I)  # sem "ND": o corte é uma obra derivada
ESCOLHIDAS = RAIZ / "dados" / "referencia" / "fotos_governo.json"  # fotos escolhidas à mão, quando o Wikidata não ajuda
TAMANHO = (240, 320)  # retrato 3:4


def _enderecos(p):
    numero = p["id"].split("-")[1]
    if p["casa"] == "camara":
        # a versão "maior" tem 354×472; a normal, 114×152
        return [f"https://www.camara.leg.br/internet/deputado/bandep/{numero}.jpgmaior.jpg", p.get("foto")]
    return [f"https://legis.senado.leg.br/senadores/fotos-oficiais/{numero}", p.get("foto")]


def _ajustar(conteudo, corte=None):
    """Corta em 3:4 (tirando dos lados, ou de baixo para não cortar o rosto) e reduz para 240×320.
    corte: [esquerda, topo, direita, base] em frações, para tirar o retrato de uma foto maior (fotos escolhidas à mão)."""
    im = Image.open(BytesIO(conteudo)).convert("RGB")
    if corte:
        w, h = im.size
        im = im.crop((round(corte[0] * w), round(corte[1] * h), round(corte[2] * w), round(corte[3] * h)))
    w, h = im.size
    if w * 4 > h * 3:
        nw = round(h * 3 / 4)
        x = (w - nw) // 2
        im = im.crop((x, 0, x + nw, h))
    else:
        im = im.crop((0, 0, w, round(w * 4 / 3)))
    im = im.resize(TAMANHO, Image.LANCZOS)
    saida = BytesIO()
    im.save(saida, "WEBP", quality=80, method=6)
    return saida.getvalue()


def _uma(p):
    destino = PASTA / f"{p['id']}.webp"
    if destino.exists():
        return "já tinha"
    if p["casa"] == "executivo":
        # ministro que é deputado ou senador: usa a foto oficial do Congresso
        origem = PASTA / f"{p['relacionado']}.webp" if p.get("relacionado") else None
        if origem and origem.exists():
            destino.write_bytes(origem.read_bytes())
            return "nova"
        return "sem foto"  # tenta o Wikimedia Commons depois (_governo_commons)
    for url in _enderecos(p):
        if not url:
            continue
        try:
            r = baixar(url, tentativas=2, timeout=30)
            if not r.headers.get("content-type", "").startswith("image/"):
                continue
            tmp = destino.with_suffix(".tmp")
            tmp.write_bytes(_ajustar(r.content))
            tmp.replace(destino)
            return "nova"
        except TempoEsgotado:
            raise
        except Exception:  # noqa: BLE001 — foto é opcional; tenta o próximo endereço
            continue
    return "falhou"


_ua = {"User-Agent": "ContasDoPoder/0.1 (https://contasdopoder.com; projeto civico de transparencia)"}
_rotulos = {}


class WikimediaLimitou(Exception):
    """A Wikimedia pediu para ir mais devagar (HTTP 429)."""


def _api(url, **params):
    """Consulta à Wikimedia, no máximo ~1 por segundo; 429 = espera o que ela pedir e tenta de novo uma vez."""
    import requests
    for tentativa in range(2):
        time.sleep(1.1)
        r = requests.get(url, params={**params, "format": "json"}, headers=_ua, timeout=60)
        if r.status_code == 429:
            if tentativa:
                raise WikimediaLimitou()
            time.sleep(min(120, int(r.headers.get("Retry-After", "30") or 30)))
            continue
        r.raise_for_status()
        return r.json()


def _nomes_cargos(ids):
    faltam = [i for i in ids if i not in _rotulos]
    for k in range(0, len(faltam), 50):
        ents = _api(WIKIDATA, action="wbgetentities", ids="|".join(faltam[k:k + 50]), props="labels", languages="pt|en")["entities"]
        for qid, e in ents.items():
            _rotulos[qid] = [l["value"] for l in e.get("labels", {}).values()]
    return [n for i in ids for n in _rotulos.get(i, [])]


def _wikidata(p):
    """(QID, arquivo da foto) de quem ocupou cargo de ministro/presidente/vice, ou None."""
    for nome in dict.fromkeys(n for n in (p.get("nome_civil"), p["nome"]) if n):
        ids = [x["id"] for x in _api(WIKIDATA, action="wbsearchentities", search=nome, language="pt", limit=5, type="item").get("search", [])]
        if not ids:
            continue
        ents = _api(WIKIDATA, action="wbgetentities", ids="|".join(ids), props="claims")["entities"]
        valor = lambda c: c.get("mainsnak", {}).get("datavalue", {}).get("value")
        for qid in ids:
            c = ents.get(qid, {}).get("claims", {})
            humano = any((valor(v) or {}).get("id") == "Q5" for v in c.get("P31", []))
            brasil = any((valor(v) or {}).get("id") == "Q155" for v in c.get("P27", []))
            fotos = [valor(v) for v in c.get("P18", []) if valor(v)]
            cargos = [(valor(v) or {}).get("id") for v in c.get("P39", []) if valor(v)]
            if humano and brasil and fotos and cargos and any(CARGO_OK.search(n) for n in _nomes_cargos(cargos[:50])):
                return qid, fotos[-1]  # a mais recente costuma ser a última
    return None


def _commons(arquivo, largura=330):
    paginas = _api(COMMONS, action="query", titles=f"File:{arquivo}", prop="imageinfo",
                   iiprop="url|size|extmetadata", iiurlwidth=largura)["query"]["pages"]  # 330 px: um dos tamanhos padrão da Wikimedia
    info = next(iter(paginas.values())).get("imageinfo", [{}])[0]
    meta = info.get("extmetadata", {})
    texto = lambda k: re.sub(r"<[^>]+>", "", meta.get(k, {}).get("value", "")).strip()
    return {"url": info.get("thumburl") or info.get("url"), "largura": info.get("width", 0), "altura": info.get("height", 0),
            "autor": re.sub(r"\s+", " ", texto("Artist"))[:80], "licenca": texto("LicenseShortName"),
            "url_licenca": texto("LicenseUrl"), "pagina": info.get("descriptionurl")}


def _governo_commons(politicos, limite=None):
    """Fotos do Wikimedia Commons para quem é do governo e ainda não tem foto.
    Quem não tem foto aceitável só é procurado de novo depois de 30 dias. limite: no máximo tantas buscas por vez
    (cada busca leva uns 15 s, por causa do ritmo que a Wikimedia pede; o resto fica para a próxima semana)."""
    dados = ler_json(CREDITOS) if CREDITOS.exists() else {}
    creditos, tentou = dados.setdefault("fotos", {}), dados.setdefault("procurado_em", {})
    escolhidas = ler_json(ESCOLHIDAS).get("fotos", {}) if ESCOLHIDAS.exists() else {}
    hoje = time.strftime("%Y-%m-%d")
    novas = buscas = 0
    try:
        for p in politicos:
            destino = PASTA / f"{p['id']}.webp"
            if p["casa"] != "executivo" or destino.exists():
                continue
            escolhida = escolhidas.get(p["id"])
            if not escolhida and tentou.get(p["id"], "0000") > time.strftime("%Y-%m-%d", time.localtime(time.time() - 30 * 86400)):
                continue
            if limite is not None and buscas >= limite:
                break
            buscas += 1
            tentou[p["id"]] = hoje
            try:
                achou = (None, escolhida["arquivo"]) if escolhida else _wikidata(p)
                if not achou:
                    continue
                qid, arquivo = achou
                corte = (escolhida or {}).get("corte")
                f = _commons(arquivo, 1280 if corte else 330)  # com corte, uma imagem maior (o retrato sai de um pedaço dela)
                if not f["url"] or not LICENCA_OK.search(f["licenca"] or ""):
                    if escolhida:
                        log(f"  foto escolhida de {p['nome']}: sem licença livre no Commons ({f['licenca']}); não usada")
                    continue
                if not escolhida and f["altura"] < 0.95 * f["largura"]:
                    continue  # não é um retrato
                time.sleep(1.1)
                import requests
                r = requests.get(f["url"], headers=_ua, timeout=60)
                if r.status_code == 429:  # a Wikimedia pediu para ir mais devagar: tenta de novo na próxima vez
                    raise WikimediaLimitou()
                r.raise_for_status()
                destino.write_bytes(_ajustar(r.content, corte))
                creditos[p["id"]] = {"wikidata": qid, "arquivo": arquivo, **{k: f[k] for k in ("autor", "licenca", "url_licenca", "pagina")}}
                if corte:
                    creditos[p["id"]]["cortada"] = True
                novas += 1
            except (TempoEsgotado, WikimediaLimitou):
                del tentou[p["id"]]
                raise
            except Exception as e:  # noqa: BLE001 — foto é opcional
                log(f"  foto de {p['nome']}: {e}")
            finally:
                salvar_json(CREDITOS, dados)
    except WikimediaLimitou:
        log("  A Wikimedia pediu para ir mais devagar; o resto das fotos fica para a próxima vez.")
    salvar_json(CREDITOS, dados)
    return novas


def coletar():
    politicos = ler_json(PROCESSADOS / "politicos.json")
    PASTA.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(PARALELO) as ex:
        res = list(ex.map(_uma, politicos))
    if res.count("sem foto"):
        log(f"Fotos: Wikimedia Commons para o governo federal: {_governo_commons(politicos)} novas")
        res = ["sem foto" if r == "sem foto" and not (PASTA / f"{p['id']}.webp").exists() else ("nova" if r == "sem foto" else r)
               for p, r in zip(politicos, res)]
    log(f"Fotos: {res.count('nova')} novas, {res.count('já tinha')} já existiam, {res.count('falhou')} falharam, "
        f"{res.count('sem foto')} do governo sem foto oficial disponível")
