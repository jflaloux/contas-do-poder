"""Folhas de pagamento dos estados: o que o governador e o vice receberam em cada mês, desde janeiro de 2025.

Cada módulo cuida de um estado cuja folha, com o nome de cada servidor, abre para o robô (a maioria pelos dados
abertos do Estado): `coletar()` grava dados/governadores/folha/<uf>.csv (vai para o Git) só com os meses que faltam
(e os 2 últimos de novo, porque a folha pode ser corrigida). Um estado fora do ar não para os outros: o site usa o
que já estava gravado. O resto (o salário fixado em lei, quem ocupa o cargo) está em dados/governadores/governadores.json.
"""
from ..util import TempoEsgotado, log
from . import ac, df, es, mg, pb, pe, pr, ro, rr, sc, se, sp

ESTADOS = {m.UF: m for m in (ac, df, es, mg, pb, pe, pr, ro, rr, sc, se, sp)}
# o que a folha de cada estado mostra (vai para a página do estado)
NOTAS = {
    "AC": "A folha do Acre separa cada rubrica (subsídio, auxílio-alimentação, 13º, férias) e cada tipo de folha (normal, adiantamento do 13º, rescisão).",
    "DF": "A folha do Distrito Federal separa o subsídio, os benefícios (auxílios) e as verbas eventuais (13º e férias, que ela não separa entre si). Em dezembro, tiramos a devolução do adiantamento do 13º, para ele não contar duas vezes.",
    "ES": "A folha do Espírito Santo traz cada rubrica (subsídio, 13º, férias, auxílios), uma linha por rubrica.",
    "MG": "A folha de Minas Gerais separa a remuneração, o 13º, as férias, os jetons de conselhos de empresas do Estado e o abate-teto. A Secretaria de Planejamento publica com alguns meses de atraso.",
    "PB": "A folha da Paraíba dá só a parte fixa (o subsídio) e a parte variável de cada mês, sem dizer o que é a variável; o 13º não aparece.",
    "PE": "A folha de Pernambuco separa a remuneração, as férias, o 13º, outras vantagens e o desconto do teto. Algumas linhas trazem só o total, sem descrição: entram em \"outros\".",
    "PR": "A folha do Paraná separa o vencimento, as gratificações, os retroativos, os auxílios e, numa coluna só, as férias e o 13º (que entram em \"outros\").",
    "RO": "A folha de Rondônia traz cada rubrica, e o 13º vem numa folha à parte.",
    "RR": "A folha de Roraima traz cada lançamento (subsídio, parcelas do 13º, férias).",
    "SC": "A folha de Santa Catarina dá só o valor bruto do mês, sem as partes. O Estado só mantém publicados os meses mais recentes: a série começa em julho de 2026.",
    "SE": "A consulta de Sergipe mostra o contracheque de cada mês, com o subsídio; o 13º e as férias não aparecem nela.",
    "SP": "A folha de São Paulo separa a remuneração do mês e, numa coluna só, as férias e o 13º (que entram em \"outros\"). O Estado publica a série histórica com alguns meses de atraso.",
}


def coletar():
    for uf, m in ESTADOS.items():
        try:
            n = m.coletar()
            log(f"  Folha {uf}: {n} linhas novas ou refeitas")
        except TempoEsgotado:
            raise
        except Exception as e:  # noqa: BLE001 — um estado fora do ar não para os outros
            log(f"  Folha {uf}: a coleta falhou ({e}); o site usa o que já estava gravado")
