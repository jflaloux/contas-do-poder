"""Fotos oficiais dos parlamentares, guardadas no próprio site: site/fotos/{id}.webp (240×320).

Por que guardar aqui: a imagem para compartilhar é desenhada no navegador (canvas), e o site da
Câmara não deixa outro endereço usar as fotos dele num canvas (CORS). De quebra, a página carrega
mais rápido e não depende do site oficial para mostrar as fotos.

Só baixa as fotos que ainda não existem. Se uma foto falhar, o site usa o endereço oficial.
"""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

from PIL import Image

from .config import PARALELO, PROCESSADOS, RAIZ
from .util import TempoEsgotado, baixar, ler_json, log

PASTA = RAIZ / "site" / "fotos"
TAMANHO = (240, 320)  # retrato 3:4


def _enderecos(p):
    numero = p["id"].split("-")[1]
    if p["casa"] == "camara":
        # a versão "maior" tem 354×472; a normal, 114×152
        return [f"https://www.camara.leg.br/internet/deputado/bandep/{numero}.jpgmaior.jpg", p.get("foto")]
    return [f"https://legis.senado.leg.br/senadores/fotos-oficiais/{numero}", p.get("foto")]


def _ajustar(conteudo):
    """Corta em 3:4 (tirando dos lados, ou de baixo para não cortar o rosto) e reduz para 240×320."""
    im = Image.open(BytesIO(conteudo)).convert("RGB")
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


def coletar():
    politicos = ler_json(PROCESSADOS / "politicos.json")
    PASTA.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(PARALELO) as ex:
        res = list(ex.map(_uma, politicos))
    log(f"Fotos: {res.count('nova')} novas, {res.count('já tinha')} já existiam, {res.count('falhou')} sem foto")
