"""GET/POST com novas tentativas, para os robôs das folhas estaduais (portais lentos ou instáveis)."""
import time

from ..util import TempoEsgotado, _sessao, verificar_prazo


def pedir(metodo, url, tentativas=4, pausa=0.5, vazio=(404,), json=True, **kw):
    """Faz o pedido; devolve o JSON (ou a resposta, com json=False). Status em `vazio` = None (não achou)."""
    kw.setdefault("timeout", 90)
    for i in range(tentativas):
        verificar_prazo()
        try:
            r = _sessao().request(metodo, url, **kw)
            if r.status_code in vazio:
                return None
            if r.status_code == 429 and i < tentativas - 1:  # pediu para ir mais devagar
                espera = r.headers.get("Retry-After")
                time.sleep(int(espera) if espera and espera.isdigit() else 30 * (i + 1))
                continue
            r.raise_for_status()
            time.sleep(pausa)
            return r.json() if json else r
        except TempoEsgotado:
            raise
        except Exception:
            if i == tentativas - 1:
                raise
            time.sleep(10 * (i + 1))


def get(url, **kw):
    return pedir("GET", url, **kw)


def post(url, **kw):
    return pedir("POST", url, **kw)
