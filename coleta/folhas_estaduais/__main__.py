"""Roda o robô da folha de um estado só, com tempo máximo.

Uso: python3 -m coleta.folhas_estaduais rn [segundos]   (padrão: 150 s)

Útil onde cada comando tem tempo limitado: o robô grava os meses que já pegou e, se o tempo acabar, continua de onde
parou na próxima vez. Depois, "python3 coletar.py governadores" junta tudo em site/dados/governadores.json.
"""
import importlib
import sys

from ..util import TempoEsgotado, definir_prazo

if len(sys.argv) < 2:
    sys.exit(__doc__)
definir_prazo(int(sys.argv[2]) if len(sys.argv) > 2 else 150)
robo = importlib.import_module(f"{__package__}.{sys.argv[1].lower()}")
try:
    print(sys.argv[1].upper(), "linhas novas:", robo.coletar())
except TempoEsgotado:
    print(sys.argv[1].upper(), "tempo esgotado: rode de novo para continuar")
    sys.exit(3)
