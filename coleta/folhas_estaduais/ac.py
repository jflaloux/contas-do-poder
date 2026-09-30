"""Acre: Portal de Transparência do Estado, "Servidores": a busca por nome e mês e o detalhamento de cada folha
(normal, adiantamento do 13º, rescisão), com as rubricas. O robô faz o mesmo que a página: abre a página (que dá o
token de segurança do formulário) e faz as mesmas consultas. Sem CPF na resposta.
https://transparencia.ac.gov.br/servidores"""
import re
import time

from ..util import TempoEsgotado, _sessao, verificar_prazo
from . import comum

UF = "AC"
BASE = "https://transparencia.ac.gov.br/servidores"
FONTE = BASE


class _Portal:
    def __init__(self):
        self.s = _sessao()
        t = self.s.get(BASE, timeout=90).text
        self.cab = {"X-CSRF-TOKEN": re.search(r'name="csrf-token" content="([^"]+)"', t).group(1),
                    "X-Requested-With": "XMLHttpRequest", "Referer": BASE}

    def post(self, caminho, dados):
        verificar_prazo()
        for tentativa in range(4):
            try:
                r = self.s.post(f"{BASE}/{caminho}", data=dados, headers=self.cab, timeout=90)
                r.raise_for_status()
                time.sleep(1)
                return r.json()
            except TempoEsgotado:
                raise
            except Exception:
                if tentativa == 3:
                    raise
                time.sleep(10 * (tentativa + 1))


def _filtros(am, busca):
    return {"ano": str(am // 100), "mes": f"{am % 100:02d}", "busca": busca, "orgao": "0", "filtro": "orgao", "situacao": "0",
            "tipo_contrato": "0", "admissao": "", "exoneracao": ""}


def coletar():
    p = _Portal()
    feitos, linhas = [], []
    for am in comum.a_fazer(UF, comum.ultimo_possivel()):
        achou = False
        for nome, papel in comum.nomes_folha(UF, am).items():
            lista = p.post("listar", {"draw": "1", "columns[0][data]": "", "order[0][column]": "0", "order[0][dir]": "asc", "start": "0",
                                      "length": "50", "search[value]": "", **_filtros(am, nome)})
            for x in lista.get("data") or []:
                if not comum.normalizar_nome(x["nome"]).startswith(comum.normalizar_nome(nome)):
                    continue
                tp = comum.tp_do_cargo(x.get("cargo_comissao")) or papel
                folhas = p.post("detalhamento", {"id": x["matricula"], "orgao_detalhamento": x["orgao"], "cargo_comissao": x["cargo_comissao"],
                                                 "cargo_efetivo": x.get("cargo_efetivo") or "", "contrato": x["contrato"], **_filtros(am, nome)})
                rub = [(v["descricao"], v["valor"], v["tipo"] == "C") for f in folhas for v in f.get("verbas_formatada") or []]
                partes, redutor, bruto = comum.somar_rubricas(rub)
                if abs(bruto - float(x.get("valor_bruto") or 0)) > 1:
                    partes, bruto = None, float(x.get("valor_bruto") or 0)
                linhas.append(comum.linha(am, tp, x["nome"], x["cargo_comissao"], bruto, partes, redutor))
                achou = True
        if achou:
            feitos.append(am)
    comum.gravar(UF, linhas, feitos)
    return len(linhas)
