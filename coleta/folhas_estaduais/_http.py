"""GET/POST com novas tentativas, para os robôs das folhas estaduais (portais lentos ou instáveis)."""
import time

from ..util import TempoEsgotado, _sessao, dormir, restante, verificar_prazo


def pedir(metodo, url, tentativas=4, pausa=0.5, vazio=(404,), json=True, **kw):
    """Faz o pedido; devolve o JSON (ou a resposta, com json=False). Status em `vazio` = None (não achou)."""
    kw.setdefault("timeout", 90)
    for i in range(tentativas):
        verificar_prazo()
        try:
            falta = restante()  # a consulta não passa do prazo
            r = _sessao().request(metodo, url, **{**kw, "timeout": kw["timeout"] if falta is None else max(5, min(kw["timeout"], falta))})
            if r.status_code in vazio:
                return None
            if r.status_code == 429 and i < tentativas - 1:  # pediu para ir mais devagar
                espera = r.headers.get("Retry-After")
                dormir(int(espera) if espera and espera.isdigit() else 30 * (i + 1))
                continue
            r.raise_for_status()
            falta = restante()
            time.sleep(pausa if falta is None else max(0, min(pausa, falta)))  # resposta boa: não se perde por causa do prazo
            return r.json() if json else r
        except TempoEsgotado:
            raise
        except Exception:
            if i == tentativas - 1:
                raise
            dormir(10 * (i + 1))


def get(url, **kw):
    return pedir("GET", url, **kw)


def post(url, **kw):
    return pedir("POST", url, **kw)
