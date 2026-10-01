"""Folhas de pagamento dos estados: o que o governador e o vice receberam em cada mês, desde janeiro de 2025.

Cada módulo cuida de um estado cuja folha, com o nome de cada servidor, abre para o robô (a maioria pelos dados
abertos do Estado): `coletar()` grava dados/governadores/folha/<uf>.csv (vai para o Git) só com os meses que faltam
(e os 2 últimos de novo, porque a folha pode ser corrigida). Um estado fora do ar não para os outros: o site usa o
que já estava gravado. O resto (o salário fixado em lei, quem ocupa o cargo) está em dados/governadores/governadores.json.
"""
from ..util import TempoEsgotado, log
from . import ac, al, am, ba, ce, df, es, go, ma, mg, ms, pa, pb, pe, pi, pr, rj, rn, ro, rr, rs, sc, se, sp

ESTADOS = {m.UF: m for m in (ac, al, am, ba, ce, df, es, go, ma, mg, ms, pa, pb, pe, pi, pr, rj, rn, ro, rr, rs, sc, se, sp)}
# o que a folha de cada estado mostra (vai para a página do estado)
NOTAS = {
    "AC": "A folha do Acre separa cada rubrica (subsídio, auxílio-alimentação, 13º, férias) e cada tipo de folha (normal, adiantamento do 13º, rescisão).",
    "AL": "A folha de Alagoas separa a remuneração base, a comissão (é por ela que o governador recebe), os benefícios, as verbas eventuais e o abate-teto; a folha do 13º entra em dezembro.",
    "AM": "A folha do Amazonas dá o total bruto e o desconto do teto, sem separar salário, 13º e férias. O vice Tadeu de Souza é procurador do Estado e recebia como vice pelo cargo de origem.",
    "BA": "O painel da Bahia mostra o nome mascarado (\"JERONIMO R*** S***\"); achamos o governador e o vice pelo cargo. Separa o valor bruto, o 13º, as férias e o estorno do teto.",
    "CE": "O arquivo do Ceará dá o salário bruto e o abatimento do teto, sem separar 13º e férias. Até março de 2026, a vice Jade Romero recebeu como secretária da Proteção Social e como conselheira do Detran, e não como vice: entram todos os pagamentos com o nome dela.",
    "DF": "A folha do Distrito Federal separa o subsídio, os benefícios (auxílios) e as verbas eventuais (13º e férias, que ela não separa entre si). Em dezembro, tiramos a devolução do adiantamento do 13º, para ele não contar duas vezes.",
    "ES": "A folha do Espírito Santo traz cada rubrica (subsídio, 13º, férias, auxílios), uma linha por rubrica.",
    "GO": "O arquivo de Goiás separa o provento do mês, o 13º, as férias e o corte do teto. O mês de junho de 2026 não foi publicado.",
    "MA": "O portal do Maranhão separa subsídio, férias e adiantamento do 13º. O governador e o vice (este, em 2025) também recebem R$ 8.850 por mês como conselheiros, que entram em \"outros\".",
    "MG": "A folha de Minas Gerais separa a remuneração, o 13º, as férias, os jetons de conselhos de empresas do Estado e o abate-teto. A Secretaria de Planejamento publica com alguns meses de atraso.",
    "MS": "A folha de Mato Grosso do Sul dá a remuneração fixa e a eventual, sem separar 13º e férias.",
    "PA": "A folha do Pará dá o total de cada mês. Desde abril de 2026 ninguém em mandato eletivo aparece mais na consulta pública: nem a governadora Hana Ghassan, nem o vice.",
    "PB": "A folha da Paraíba dá só a parte fixa (o subsídio) e a parte variável de cada mês, sem dizer o que é a variável; o 13º não aparece.",
    "PE": "A folha de Pernambuco separa a remuneração, as férias, o 13º, outras vantagens e o desconto do teto. Algumas linhas trazem só o total, sem descrição: entram em \"outros\".",
    "PI": "A folha do Piauí separa a remuneração básica, a variável (o subsídio) e a eventual (1/3 de férias, adiantamento do 13º); a folha do 13º entra em dezembro.",
    "PR": "A folha do Paraná separa o vencimento, as gratificações, os retroativos, os auxílios e, numa coluna só, as férias e o 13º (que entram em \"outros\").",
    "RJ": "A folha do Rio separa a folha mensal, o adiantamento do 13º (junho) e o 13º (dezembro). O governador em exercício desde março de 2026, presidente do Tribunal de Justiça, é pago pelo Tribunal e não aparece nesta folha.",
    "RN": "A folha do Rio Grande do Norte dá a remuneração do mês, outras remunerações e o redutor do teto; o 13º e as férias não aparecem.",
    "RO": "A folha de Rondônia traz cada rubrica, e o 13º vem numa folha à parte.",
    "RR": "A folha de Roraima traz cada lançamento (subsídio, parcelas do 13º, férias).",
    "RS": "O painel do Rio Grande do Sul traz cada rubrica: subsídio, 1/3 de férias, adiantamento do 13º (novembro) e 13º (dezembro).",
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
