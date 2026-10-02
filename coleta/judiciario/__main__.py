"""Roda uma fonte do Judiciário só, com tempo máximo.

Uso: python3 -m coleta.judiciario stj [segundos]   (padrão: 150 s; fontes: stj, tst, cnj, pgr, stf, stm, tse)
     python3 -m coleta.judiciario site [sem-fotos]  (só escreve site/dados/judiciario.json com o que já está gravado)

Útil onde cada comando tem tempo limitado: o robô grava o que já pegou e, se o tempo acabar, continua de onde parou
na próxima vez (código de saída 3).
"""
import sys

from ..util import TempoEsgotado, definir_prazo
from . import POR_NOME, executar_site

if len(sys.argv) < 2:
    sys.exit(__doc__)
if sys.argv[1].lower() == "site":
    if len(sys.argv) > 2 and sys.argv[2].isdigit():
        definir_prazo(int(sys.argv[2]))
    try:
        executar_site(baixar_fotos="sem-fotos" not in sys.argv)
    except TempoEsgotado:
        print("tempo esgotado: rode de novo para continuar")
        sys.exit(3)
    sys.exit(0)
definir_prazo(int(sys.argv[2]) if len(sys.argv) > 2 else 150)
fonte = POR_NOME[sys.argv[1].lower()]
try:
    print(sys.argv[1].upper(), "linhas novas ou refeitas:", fonte.coletar())
except TempoEsgotado:
    print(sys.argv[1].upper(), "tempo esgotado: rode de novo para continuar")
    sys.exit(3)
