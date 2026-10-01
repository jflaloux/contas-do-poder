"""Leitura do PDF mensal "Detalhamento da folha de pagamento" da Alese (Sergipe), pelas posições das palavras.

O PDF tem uma linha de valores por servidor (colunas 01 a 14) e, acima dela, matrícula, nome, admissão, cargo e lotação
(que às vezes ocupam duas ou três linhas). Daqui sai só o que o site usa: os rendimentos dos deputados (colunas 01 a 10,
sem descontos nem líquido) e, para cada gabinete, quantas pessoas e o total de rendimentos (sem nomes).
"""
import html
import re
import subprocess
import tempfile

from ..util import normalizar_nome

DINHEIRO = re.compile(r"^-?\d{1,3}(?:\.\d{3})*,\d{2}$")
DATA = re.compile(r"^\d{2}/\d{2}/\d{4}$")
PALAVRA = re.compile(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>')
COLUNAS = [f"{i:02d}" for i in range(1, 15)]


def _num(t):
    return float(t.replace(".", "").replace(",", "."))


def _paginas(b):
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(b)
        f.flush()
        saida = subprocess.run(["pdftotext", "-bbox", f.name, "-"], capture_output=True, text=True).stdout
    for pag in saida.split("<page ")[1:]:
        yield [(float(a), float(b_), float(c), float(d), html.unescape(t)) for a, b_, c, d, t in PALAVRA.findall(pag)]


def ler(b):
    """-> (deputados, gabinetes, registros). deputados: [{nome, cargo, lotacao, c01..c10}]; gabinetes: {lotação: [pessoas, rendimentos]}."""
    deputados, gabinetes, registros = [], {}, 0
    for w in _paginas(b):
        rot = {t: (x0 + x1) / 2 for x0, y0, x1, y1, t in w if t in COLUNAS and y0 < 200}
        cab = {t: x0 for x0, y0, x1, y1, t in w if t in ("Mat.", "Nome", "Admissão", "Lotação") and y0 < 200}
        cargo_x = [x0 for x0, y0, x1, y1, t in w if t == "Cargo" and y0 < 200 and x0 < cab.get("Lotação", 0)]
        if len(rot) < 10 or len(cab) < 4 or not cargo_x:
            continue
        topo = max(y0 for x0, y0, x1, y1, t in w if t in COLUNAS and y0 < 200)
        x_valores = rot["01"] - 20
        nums = sorted((y0, x0, x1, t) for x0, y0, x1, y1, t in w if y0 > topo + 3 and DINHEIRO.match(t) and x0 >= x_valores)
        linhas = []
        for y0, x0, x1, t in nums:
            if linhas and abs(linhas[-1][0] - y0) < 2.5:
                linhas[-1][1].append((x0, x1, t))
            else:
                linhas.append([y0, [(x0, x1, t)]])
        linhas = [(y, vals) for y, vals in linhas if len(vals) >= 8]
        # a linha de valores fica no meio do registro: o registro vai do meio do caminho até a linha de cima ao meio do caminho até a de baixo
        for i, (y, vals) in enumerate(linhas):
            de = (linhas[i - 1][0] + y) / 2 if i else topo + 3
            ate = (y + linhas[i + 1][0]) / 2 if i + 1 < len(linhas) else 1e9
            banda = [(x0, y0, t) for x0, y0, x1, y1, t in w if de < y0 <= ate and x0 < x_valores]
            texto = lambda a, b_: " ".join(t for x0, y0, t in sorted(banda, key=lambda p: (round(p[1]), p[0])) if a - 2 <= x0 < b_ - 2 and not DATA.match(t))
            nome = texto(cab["Nome"], cab["Admissão"])
            cargo = texto(cargo_x[0], cab["Lotação"])
            lotacao = texto(cab["Lotação"], x_valores)
            col = {}
            for x0, x1, t in vals:
                c = min(rot, key=lambda k: abs(rot[k] - (x0 + x1) / 2))
                col[c] = col.get(c, 0.0) + _num(t)
            registros += 1
            cn = normalizar_nome(cargo)
            if re.match(r"DEPUTAD[OA]\b", cn):
                deputados.append({"nome": nome, "cargo": cargo, "lotacao": lotacao, **{f"c{k}": round(col.get(k, 0.0), 2) for k in COLUNAS[:10]}})
            elif normalizar_nome(lotacao).startswith("GABINETE D"):
                g = gabinetes.setdefault(normalizar_nome(lotacao), [0, 0.0])
                g[0] += 1
                g[1] += col.get("10", 0.0)
    return deputados, gabinetes, registros
