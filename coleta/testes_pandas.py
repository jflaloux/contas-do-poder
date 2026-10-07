"""Teste de compatibilidade com o pandas 3: procura no código `&`, `|` ou `^` entre uma máscara do pandas e uma lista, tupla
ou compreensão de lista (o pandas 3 recusa com TypeError; em 06/10/2026 isso derrubou o `padronizar` no GitHub). A lista
tem que virar `np.array(..., dtype=bool)` ou `pd.Series(..., index=...)`. Sem rede e sem dados.

    python3 -m coleta.testes_pandas
"""
import ast
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
OPERADORES = (ast.BitAnd, ast.BitOr, ast.BitXor)
LISTAS = (ast.List, ast.ListComp, ast.Tuple, ast.GeneratorExp)


def listas_em_operacao_logica():
    """[(arquivo, linha)] de operações de bits em que um dos lados é lista, tupla ou compreensão."""
    achados = []
    for arq in [*sorted((RAIZ / "coleta").rglob("*.py")), RAIZ / "coletar.py"]:
        if arq.name == Path(__file__).name:
            continue
        for no in ast.walk(ast.parse(arq.read_text(encoding="utf-8"))):
            if isinstance(no, ast.BinOp) and isinstance(no.op, OPERADORES) and (isinstance(no.left, LISTAS) or isinstance(no.right, LISTAS)):
                achados.append((str(arq.relative_to(RAIZ)), no.lineno))
    return achados


def executar():
    falhas, total = [], 0

    def caso(nome, ok):
        nonlocal total
        total += 1
        if not ok:
            falhas.append(nome)

    achados = listas_em_operacao_logica()
    caso(f"nenhuma máscara combinada com lista no código {achados}", not achados)
    # o detector pega o padrão que quebrou
    amostra = ast.parse('rem[(rem.id == 1) & [(a, m) in q for a, m in zip(rem.a, rem.m)]]')
    caso("o detector acha `máscara & [compreensão]`",
         any(isinstance(n, ast.BinOp) and isinstance(n.right, LISTAS) for n in ast.walk(amostra)))
    # a forma correta funciona com o pandas instalado
    df = pd.DataFrame({"id": [1, 1, 2], "a": [2025, 2026, 2025], "m": [1, 2, 3]})
    q = {(2026, 2)}
    certo = df[(df.id == 1) & np.array([(a, m) in q for a, m in zip(df.a, df.m)], dtype=bool)]
    caso("np.array(dtype=bool) combina com a máscara", len(certo) == 1 and int(certo.a.iloc[0]) == 2026)
    vazio = df[(df.id == 1) & np.array([(a, m) in set() for a, m in zip(df.a, df.m)], dtype=bool)]
    caso("lista de falsos não escolhe ninguém", vazio.empty)
    print(f"pandas {pd.__version__}: {total - len(falhas)}/{total} casos certos" + (f"; falharam: {falhas}" if falhas else ""))
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(executar())
