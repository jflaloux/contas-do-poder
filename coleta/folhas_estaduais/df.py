"""Distrito Federal: Portal da Transparência do DF, remuneração por nome e mês (API do próprio portal).
https://www.transparencia.df.gov.br/#/servidores/remuneracao
A API pede um cabeçalho x-client-id com um identificador qualquer, que o site gera a cada visita; mandamos um fixo.
A resposta traz o CPF mascarado, que não é guardado."""
import time

from ..util import TempoEsgotado, _sessao, verificar_prazo
from . import comum

UF = "DF"
API = "https://www.transparencia.df.gov.br/api/remuneracao"
FONTE = "https://www.transparencia.df.gov.br/#/servidores/remuneracao"
CAB = {"x-client-id": "7d1f3c2a-5b6e-4f80-9a1b-2c3d4e5f6a7b"}


def _get(url, params=None):
    verificar_prazo()
    for tentativa in range(3):
        try:
            r = _sessao().get(url, params=params, headers=CAB, timeout=90)
            r.raise_for_status()
            return r.json()
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 2:
                raise
            time.sleep(10)


def coletar():
    ultimo = int(_get(f"{API}/ultimo-exercicio"))
    feitos, linhas = [], []
    for am in comum.a_fazer(UF, ultimo):
        for nome, papel in comum.nomes_folha(UF, am).items():
            d = _get(API, {"anoExercicio": am // 100, "mesReferencia": f"{am % 100:02d}", "nomeServidor": nome, "page": 0})
            for x in d.get("content") or []:
                if comum.normalizar_nome(x["nomeServidor"]) != comum.normalizar_nome(nome):
                    continue
                tp = comum.tp_do_cargo(x.get("funcao")) or comum.tp_do_cargo(x.get("cargo")) or papel
                g = lambda k: float(x.get(k) or 0)
                partes = {"salario": g("valorFuncoes") + g("valorRemuneracaoBasica"), "decimo": None, "ferias": None,
                          "beneficios": g("valorBeneficios"),
                          # verbas eventuais (13º e férias, que o DF não separa), meses anteriores, horas extras, jetons...
                          "outros": g("valorVerbasEventuais") + g("valorReceitasMesesAnteriores") + g("valorHoraExtra") + g("valorComissaoConselheiro")
                          + g("valorLicencaPremio") + g("valorVerbasJudiciais") - g("valorReposicaoPagamentoMaior")}
                # a "reposição de pagamento a maior" de dezembro devolve o adiantamento do 13º pago antes: tiramos do bruto,
                # para o 13º não contar duas vezes
                linhas.append(comum.linha(am, tp, x["nomeServidor"], x.get("funcao"), g("valorBruto") - g("valorReposicaoPagamentoMaior"), partes,
                                          g("valorRedutorTeto")))
            time.sleep(1)
        feitos.append(am)
    comum.gravar(UF, linhas, feitos)
    return len(linhas)
