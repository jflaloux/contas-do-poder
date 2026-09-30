"""Roraima: API do Portal da Transparência, remuneração por nome e mês, com cada lançamento.
https://www.transparencia.rr.gov.br/remuneracoes (API pública usada pelo próprio portal).
A resposta traz o CPF mascarado, que não é guardado."""
import time

from ..util import TempoEsgotado, _sessao, verificar_prazo
from . import comum

UF = "RR"
API = "https://api.transparencia.rr.gov.br/api/v1/portal/transparencia/pesquisar-remuneracoes"
FONTE = "https://www.transparencia.rr.gov.br/remuneracoes"


def _get(params):
    verificar_prazo()
    for tentativa in range(4):
        try:
            r = _sessao().get(API, params=params, timeout=90)
            r.raise_for_status()
            return r.json()
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 3:
                raise
            time.sleep(10 * (tentativa + 1))


def coletar():
    ultimo = comum.ultimo_possivel()
    feitos, linhas = [], []
    for am in comum.a_fazer(UF, ultimo, refazer=3):
        achou = False
        for nome, papel in comum.nomes_folha(UF, am).items():
            d = _get({"nome": nome, "mes": am % 100, "ano": am // 100, "page": 0})
            for x in (d.get("data") or {}).get("content") or []:
                if comum.normalizar_nome(x["nome"]) != comum.normalizar_nome(nome):
                    continue
                cargos = [m.get("cargo") for m in x.get("matriculas") or []]
                tp = next((comum.tp_do_cargo(c) for c in cargos if comum.tp_do_cargo(c)), None) or papel
                rub = [(l.get("descricao") or l.get("evento"), l.get("valor"), l.get("tipoEvento") == "P") for l in x.get("lancamentos") or []]
                partes, redutor, bruto = comum.somar_rubricas(rub)
                if abs(bruto - float(x.get("remuneracaoBruta") or 0)) > 1:  # os lançamentos não fecham: fica o total, sem as partes
                    partes, bruto = None, float(x.get("remuneracaoBruta") or 0)
                linhas.append(comum.linha(am, tp, x["nome"], " / ".join(c for c in cargos if c), bruto, partes, redutor))
                achou = True
            time.sleep(1)
        if achou:
            feitos.append(am)
    comum.gravar(UF, linhas, feitos)
    return len(linhas)
