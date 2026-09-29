"""Funções auxiliares: acesso à internet com cache, números em formato brasileiro, nomes."""
import json
import re
import threading
import time
import unicodedata
from pathlib import Path

import requests

from .config import USER_AGENT


class TempoEsgotado(Exception):
    """A coleta parou porque atingiu o tempo máximo; rode de novo para continuar."""


_prazo = None


def definir_prazo(segundos):
    global _prazo
    _prazo = time.time() + segundos if segundos else None


def verificar_prazo():
    if _prazo and time.time() > _prazo:
        raise TempoEsgotado()


_local = threading.local()


def _sessao():
    if not hasattr(_local, "s"):
        s = requests.Session()
        s.headers["User-Agent"] = USER_AGENT
        _local.s = s
    return _local.s


def baixar(url, params=None, tentativas=4, timeout=90, **kw):
    """GET com novas tentativas em caso de erro temporário."""
    verificar_prazo()
    for i in range(tentativas):
        try:
            r = _sessao().get(url, params=params, timeout=timeout, **kw)
            if r.status_code == 404:
                r.raise_for_status()
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {r.status_code} em {r.url}", response=r)
            r.raise_for_status()
            return r
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                raise
            if i == tentativas - 1:
                raise
        except requests.RequestException:
            if i == tentativas - 1:
                raise
        time.sleep(3 * (i + 1))


def cache_valido(caminho: Path, max_idade_dias=None):
    """Existe no cache e (se max_idade_dias for dado) não está velho demais."""
    if not caminho.exists():
        return False
    if max_idade_dias is None:
        return True
    return (time.time() - caminho.stat().st_mtime) < max_idade_dias * 86400


def salvar_json(caminho: Path, dados):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(caminho.suffix + ".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(caminho)


def ler_json(caminho: Path):
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


def numero_br(texto):
    """'R$ 46.366,19' -> 46366.19 ; '' -> None."""
    if texto is None:
        return None
    t = str(texto).replace("R$", "").replace("\xa0", " ").strip()
    if t in ("", "-", "—"):
        return None
    t = t.replace(".", "").replace(",", ".")
    try:
        return round(float(t), 2)
    except ValueError:
        return None


def normalizar_nome(nome):
    """Maiúsculas, sem acentos e sem espaços duplos — para comparar nomes de fontes diferentes."""
    if not nome:
        return ""
    t = unicodedata.normalize("NFKD", str(nome))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().upper()


def log(*args):
    print(time.strftime("%H:%M:%S"), *args, flush=True)
