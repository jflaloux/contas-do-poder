"""Configurações gerais da coleta."""
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DADOS = RAIZ / "dados"
CACHE = DADOS / "cache"            # arquivos baixados (não vai para o Git)
BRUTOS = DADOS / "brutos"          # dados de cada fonte, já limpos
PROCESSADOS = DADOS / "processados"  # base unificada usada pelo site
REFERENCIA = DADOS / "referencia"  # tabelas fixas (limites da cota etc.)

# Legislatura atual: 01/02/2023 a 31/01/2027
LEGISLATURA = 57
INICIO_LEGISLATURA = (2023, 2)  # (ano, mês)
HOJE = date.today()
ANOS = list(range(2023, HOJE.year + 1))

# Quantos pedidos simultâneos fazer aos sites oficiais (seja educado com eles)
PARALELO = 4

USER_AGENT = "Mozilla/5.0 (compatible; ContasDoPoder/0.1; projeto civico de transparencia)"


def meses_da_legislatura():
    """Lista de (ano, mês) de fev/2023 até o mês atual."""
    ano, mes = INICIO_LEGISLATURA
    saida = []
    while (ano, mes) <= (HOJE.year, HOJE.month):
        saida.append((ano, mes))
        mes += 1
        if mes > 12:
            ano, mes = ano + 1, 1
    return saida
