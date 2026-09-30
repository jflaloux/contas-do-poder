"""Sergipe: Portal da Transparência do Estado, "Folha de Pagamento" (servidores ativos), pela API do próprio portal:
a lista por órgão, mês e cargo, e o contracheque de cada vínculo, com as rubricas. Sem CPF.
https://www.transparencia.se.gov.br/RecursosHumanos/FolhaPagamento
O governador está na Secretaria de Estado da Casa Civil e o vice na Vice-Governadoria."""
import time

from ..util import TempoEsgotado, _sessao, verificar_prazo
from . import comum

UF = "SE"
API = "https://api.transparencia.se.gov.br/api/recursos-humanos/remuneracao-servidores-ativos"
FONTE = "https://www.transparencia.se.gov.br/RecursosHumanos/FolhaPagamento"
ORGAOS = ("SECC", "VG")  # Casa Civil; Vice-Governadoria (os ids vêm da lista de órgãos da API)


def _get(url, params=None):
    verificar_prazo()
    for tentativa in range(4):
        try:
            r = _sessao().get(url, params=params, timeout=90)
            r.raise_for_status()
            time.sleep(0.5)
            return r.json()
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 3:
                raise
            time.sleep(10 * (tentativa + 1))


def coletar():
    ids = {o["sigla"]: o["id"] for o in _get(f"{API}/orgaos")}
    feitos, linhas = [], []
    for am in comum.a_fazer(UF, comum.ultimo_possivel()):
        achou = False
        for sigla in ORGAOS:
            d = _get(API, {"idOrgao": ids[sigla], "ano": am // 100, "mes": am % 100, "cargo": "GOVERNADOR", "page": 1, "limit": 50})
            for x in d.get("data") or []:
                tp = comum.tp_do_cargo(x.get("cargoServidor"))
                if not tp:
                    continue
                cc = _get(f"{API}/contracheque", {"codVinculo": x["codVinculo"], "mes": am % 100, "ano": am // 100})
                rub = [(r["nome"], r["valor"], r.get("tipo") == "R") for r in cc.get("rubricas") or [] if r.get("tipo") in ("R", "D")]
                partes, redutor, bruto = comum.somar_rubricas(rub)
                if abs(bruto - float(x.get("valorBruto") or 0)) > 1:
                    partes, bruto = None, float(x.get("valorBruto") or 0)
                linhas.append(comum.linha(am, tp, x["nomeServidor"], x["cargoServidor"], bruto, partes, redutor))
                achou = True
        if achou:
            feitos.append(am)
    comum.gravar(UF, linhas, feitos)
    return len(linhas)
