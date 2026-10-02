"""Roda o robô de um Tribunal de Contas só, com tempo máximo.

Uso: python3 -m coleta.tce pb [segundos]    (padrão: 150 s)
     python3 -m coleta.tce ce 150
     python3 -m coleta.tce site             (só escreve site/dados/interior/ com o que já está gravado)

Útil onde cada comando tem tempo limitado: o robô grava o que já pegou e, se o tempo acabar, continua de onde parou
na próxima vez (código de saída 3).
"""
import sys

from ..util import TempoEsgotado, definir_prazo
from . import ESTADOS, executar_site

if len(sys.argv) < 2:
    sys.exit(__doc__)
if sys.argv[1].lower() == "site":
    executar_site()
    sys.exit(0)
definir_prazo(int(sys.argv[2]) if len(sys.argv) > 2 else 150)
robo = ESTADOS[sys.argv[1].upper()]
try:
    print(sys.argv[1].upper(), "linhas novas ou refeitas:", robo.coletar())
except TempoEsgotado:
    print(sys.argv[1].upper(), "tempo esgotado: rode de novo para continuar")
    sys.exit(3)
