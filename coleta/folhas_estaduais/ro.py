"""Rondônia: API do Portal da Transparência, remuneração por cargo e mês, com cada rubrica.
https://transparencia.api.ro.gov.br/swagger/index.html (documentada em dados.ro.gov.br, conjunto "servidores").
O 13º vem numa folha à parte ("rotina" Decimo). Sem CPF na resposta."""
import time

from ..util import TempoEsgotado, _sessao, verificar_prazo
from . import comum

UF = "RO"
API = "https://transparencia.api.ro.gov.br/api/v1/remuneracao-servidor"
FONTE = "https://transparencia.api.ro.gov.br/swagger/index.html"


def _get(params):
    verificar_prazo()
    for tentativa in range(3):
        try:
            r = _sessao().get(API, params=params, timeout=90)
            if r.status_code == 404:
                return {}  # o mês ainda não foi publicado (a API responde 404, e não uma lista vazia)
            r.raise_for_status()
            return r.json()
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 2:
                raise
            time.sleep(10)


def _mes(am):
    """Linhas do governador e do vice no mês (None se o mês ainda não foi publicado)."""
    d = _get({"Ano": am // 100, "Mes": am % 100, "Cargo": "GOVERNADOR", "Page": 1, "PageSize": 100})
    res = [x for x in d.get("resultados") or [] if comum.tp_do_cargo(x.get("cargo"))]
    if not res:
        return None
    por = {}
    for x in res:
        chave = (comum.tp_do_cargo(x["cargo"]), x["nome"].strip(), x["cargo"].strip())
        rub = por.setdefault(chave, [])
        decimo = "DECIMO" in comum.normalizar_nome(x.get("rotina") or "")
        rub += [("13º SALARIO" if decimo else p["descricao"], p["valor"], True) for p in x.get("proventos") or []]
        rub += [(dsc["descricao"], dsc["valor"], False) for dsc in x.get("descontos") or []]
    linhas = []
    for (tp, nome, cargo), rub in por.items():
        partes, redutor, bruto = comum.somar_rubricas(rub)
        linhas.append(comum.linha(am, tp, nome, cargo, bruto, partes, redutor))
    return linhas


def coletar():
    feitos, linhas = [], []
    for am in comum.a_fazer(UF, comum.ultimo_possivel() + 1 if comum.ultimo_possivel() % 100 < 12 else comum.ultimo_possivel() + 89):
        ls = _mes(am)
        time.sleep(1)
        if ls is None:
            continue  # ainda não publicado
        linhas += ls
        feitos.append(am)
    comum.gravar(UF, linhas, feitos)
    return len(linhas)
