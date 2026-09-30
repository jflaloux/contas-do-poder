"""Paraíba: API de dados abertos da Codata, remuneração por órgão e mês.
https://dados.pb.gov.br/dataset/remuneracao-servidores
O governador está na Secretaria de Estado do Governo e o vice na Vice-Governadoria; a API só filtra pelo órgão (CNPJ).
A resposta traz o CPF, que não é guardado."""
import time

from ..util import TempoEsgotado, _sessao, verificar_prazo
from . import comum

UF = "PB"
API = "https://api.dadosabertos.codata.pb.gov.br/api/v1/remuneracao/servidor"
FONTE = "https://dados.pb.gov.br/dataset/remuneracao-servidores"
ORGAOS = ["08761124000100", "08761124000363"]  # Secretaria de Estado do Governo; Vice-Governadoria


def _get(params):
    verificar_prazo()
    for tentativa in range(5):
        try:
            r = _sessao().get(API, params=params, timeout=120)
            r.raise_for_status()
            return r.json()
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 4:
                raise
            time.sleep(10 * (tentativa + 1))


def _mes(am):
    linhas = []
    for org in ORGAOS:
        pagina = 1
        while True:
            d = _get({"ano": am // 100, "mes": am % 100, "page": pagina, "per_page": 100, "cnpjOrgao": org})
            for x in d.get("dados") or []:
                tp = comum.tp_do_cargo(x.get("nomeCargo"))
                if tp:
                    fixa, var = float(x.get("vantagemFixa") or 0), float(x.get("vantagemVariavel") or 0)
                    linhas.append(comum.linha(am, tp, x["nomeServidor"], x["nomeCargo"], fixa + var,
                                              {"salario": fixa, "decimo": None, "ferias": None, "beneficios": None, "outros": var},
                                              float(x.get("valorRedutor") or 0)))
            pag = d.get("paginacao") or {}
            if pagina >= int(pag.get("total_paginas") or 1):
                break
            pagina += 1
            time.sleep(0.5)
    return linhas


def coletar():
    feitos, linhas = [], []
    for am in comum.a_fazer(UF, comum.ultimo_possivel()):
        ls = _mes(am)
        if not ls:
            continue  # mês ainda sem dados
        linhas += ls
        feitos.append(am)
    comum.gravar(UF, linhas, feitos)
    return len(linhas)
