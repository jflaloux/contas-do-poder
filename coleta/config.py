"""Configurações gerais da coleta."""
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DADOS = RAIZ / "dados"
CACHE = DADOS / "cache"            # arquivos baixados (não vai para o Git)
BRUTOS = DADOS / "brutos"          # dados de cada fonte, já limpos
PROCESSADOS = DADOS / "processados"  # base unificada usada pelo site
REFERENCIA = DADOS / "referencia"  # tabelas fixas (limites da cota etc.)
for _pasta in (CACHE, BRUTOS, PROCESSADOS):
    _pasta.mkdir(parents=True, exist_ok=True)

# Legislatura atual: 01/02/2023 a 31/01/2027
LEGISLATURA = 57
INICIO_LEGISLATURA = (2023, 2)  # (ano, mês)
FIM_LEGISLATURA = (2027, 1)     # último mês desta legislatura
HOJE = date.today()
ULTIMO_MES = min((HOJE.year, HOJE.month), FIM_LEGISLATURA)  # não coleta além do fim da legislatura
ANOS = list(range(INICIO_LEGISLATURA[0], ULTIMO_MES[0] + 1))
LEGISLATURA_ENCERRADA = (HOJE.year, HOJE.month) > FIM_LEGISLATURA

# Quantos pedidos simultâneos fazer aos sites oficiais (seja educado com eles)
PARALELO = 4

USER_AGENT = "Mozilla/5.0 (compatible; ContasDoPoder/0.1; projeto civico de transparencia)"


def meses_da_legislatura():
    """Lista de (ano, mês) do início da legislatura até o mês atual (ou o fim da legislatura)."""
    ano, mes = INICIO_LEGISLATURA
    saida = []
    while (ano, mes) <= ULTIMO_MES:
        saida.append((ano, mes))
        mes += 1
        if mes > 12:
            ano, mes = ano + 1, 1
    return saida
