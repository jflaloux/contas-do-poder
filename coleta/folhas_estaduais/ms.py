"""Mato Grosso do Sul: Portal da Transparência, "Folha de Pagamento", pela API que o próprio portal usa.

O portal entrega a qualquer visitante uma chave anônima de acesso (GET /Auth/Token, sem login nem senha) e consulta a
API de folha (gw.sgi.ms.gov.br) com ela. Só essa chave anônima é usada.
A busca é por cargo ("GOVERNADOR", "VICE-GOVERNADOR") e mês; a resposta traz a remuneração fixa e a eventual (sem as
rubricas). O CPF da resposta não é guardado. Só abre de dentro do Brasil.
https://www.transparencia.ms.gov.br/"""
import time

from ..util import TempoEsgotado, _sessao, verificar_prazo
from . import comum

UF = "MS"
FONTE = "https://www.transparencia.ms.gov.br/"
API = "https://gw.sgi.ms.gov.br/d0125/transpfolhadepagamento/v1/servidores"
CARGOS = ("GOVERNADOR", "VICE-GOVERNADOR")


def _token():
    s = _sessao()
    s.get(FONTE, timeout=60)
    r = s.get(f"{FONTE}Auth/Token", timeout=60)
    r.raise_for_status()
    return r.text.strip().strip('"')


def _consulta(token, am, cargo):
    params = {"anoexercicio": am // 100, "mescompetencia": am % 100, "orgao": "", "vinculo": "", "nome": "", "situacao": "",
              "cargo": cargo, "tipoFolha": "0", "pageno": 1, "pagesize": 50, "exportarcsv": "false"}
    for tentativa in range(4):
        verificar_prazo()
        try:
            r = _sessao().get(API, params=params, headers={"Authorization": f"Bearer {token}"}, timeout=90)
            if r.status_code == 404:  # a API responde 404 quando não acha ninguém
                return []
            r.raise_for_status()
            time.sleep(0.7)
            return r.json().get("data") or []
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 3:
                raise
            time.sleep(10 * (tentativa + 1))


def coletar():
    token = _token()
    feitos, linhas = [], []
    for am in comum.a_fazer(UF, comum.ultimo_possivel()):
        achou = False
        for cargo in CARGOS:
            for x in _consulta(token, am, cargo):
                tp = comum.tp_do_cargo(x.get("cargo"))
                if not tp or x.get("orgao") != "GOVERNADORIA":
                    continue
                fixa, eventual = float(x.get("remuneracaoFixa") or 0), float(x.get("remuneracoesEventuais") or 0)
                linhas.append(comum.linha(am, tp, x["nome"], x["cargo"], fixa + eventual, {"salario": fixa, "outros": eventual}))
                achou = True
        if achou:
            feitos.append(am)
    comum.gravar(UF, linhas, feitos)
    return len(linhas)
