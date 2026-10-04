"""Prefeitura do Rio de Janeiro: prefeito e vice, mês a mês.

Fonte: Prefeitura do Rio, "Consultar Remuneração do Servidor" (Portal da Transparência Rio, Servidor Municipal >
Remuneração): https://transparencia.prefeitura.rio/servidor-municipal/remuneracao/
A página oferece a base consolidada de cada mês em CSV (Salarios_<Mês>_<AA>.csv, em contrachequedoc.rio.gov.br), com
o nome, a unidade, o tipo de folha, a remuneração bruta, o abate-teto e os descontos de cada servidor. O arquivo não
diz o cargo, então só dá para achar o prefeito e o vice, pelo nome (os eleitos em 2024, no TSE). Os secretários
ficam de fora até a Prefeitura publicar o cargo. Não guardamos os descontos nem a matrícula: só as linhas dos dois,
em dados/municipios/rio_de_janeiro/.
"""
import io
import json
import time
from datetime import date

import pandas as pd

from ..config import CACHE, DADOS
from ..util import TempoEsgotado, _sessao, dormir, gravar_csv, log, normalizar_nome, verificar_prazo
from . import comum

COD = 3304557
INICIO = 202501  # mandato 2025–2028
PAGINA = "https://transparencia.prefeitura.rio/servidor-municipal/remuneracao/"
ARQUIVO = "https://contrachequedoc.rio.gov.br/repositorio/ArquivoTC{am}.csv"
PASTA = DADOS / "municipios" / "rio_de_janeiro"
LINHAS = PASTA / "prefeitura_remuneracao.csv"
C = CACHE / "prefeituras" / "rio_de_janeiro"
PAUSA = 10
# eleitos em 2024 (TSE, consulta_cand_2024): Eduardo Paes (prefeito) e Eduardo Cavaliere (vice)
PREFEITO = "EDUARDO DA COSTA PAES"
VICE = "EDUARDO CAVALIERE GONCALVES PINTO"
COLUNAS = ["aaaamm", "nome", "unidade", "folha", "bruta", "abate_teto"]
CFG = {
    "cod": COD, "n": "Rio de Janeiro", "uf": "RJ", "de": "do Rio de Janeiro", "casa": "Prefeitura do Rio de Janeiro", "inicio": INICIO,
    "fonte": PAGINA, "pagina": PAGINA,
    "salario_nota": ("Remuneração bruta da folha da Prefeitura, já descontado o abate-teto, antes do imposto e da previdência. A folha "
                     "normal do mês é o salário; as folhas suplementares e a do 13º aparecem à parte."),
    "notas": ["A Prefeitura do Rio publica a folha de cada mês em CSV, com o nome, a unidade e a remuneração de cada servidor, mas sem o "
              "cargo. Por isso entram só o prefeito e o vice, achados pelo nome (os eleitos em 2024). Os secretários municipais ficam "
              "de fora até a folha trazer o cargo.",
              "Eduardo Paes deixou a Prefeitura em 2026 e o vice, Eduardo Cavaliere, assumiu. A folha normal de Paes vai até "
              "fevereiro de 2026 (o acerto da saída veio em abril). No site, Cavaliere aparece como vice até fevereiro e como "
              "prefeito a partir de março."],
    "credito_camara": "Câmara Municipal do Rio de Janeiro",
}


def _linhas_mes(am):
    """Só as linhas do prefeito e do vice no CSV do mês (~21 MB, lido em streaming). None = mês ainda sem arquivo."""
    verificar_prazo()
    alvo = {PREFEITO, VICE}
    for tentativa in range(3):
        try:
            r = _sessao().get(ARQUIVO.format(am=am), timeout=300, stream=True)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            achadas = []
            for bruta in r.iter_lines():
                l = bruta.decode("latin1")
                if "EDUARDO" not in l:
                    continue
                c = l.split(";")
                if len(c) >= 9 and normalizar_nome(c[0]) in alvo:
                    achadas.append({"aaaamm": am, "nome": normalizar_nome(c[0]), "unidade": c[2].strip(), "folha": c[3].strip(),
                                    "bruta": comum.num(c[4]), "abate_teto": comum.num(c[8])})
            dormir(PAUSA)
            return achadas
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 2:
                raise
            dormir(30 * (tentativa + 1))


def _meses():
    hoje = date.today()
    am, fim = INICIO, hoje.year * 100 + hoje.month
    while am <= fim:
        yield am
        am = am + 1 if am % 100 < 12 else (am // 100 + 1) * 100 + 1


def coletar():
    PASTA.mkdir(parents=True, exist_ok=True)
    C.mkdir(parents=True, exist_ok=True)
    linhas = pd.read_csv(LINHAS) if LINHAS.exists() else pd.DataFrame(columns=COLUNAS)
    feitos = set(linhas.aaaamm.astype(int)) if len(linhas) else set()
    meses = list(_meses())
    recentes = set(sorted(feitos)[-2:]) | {m for m in meses if m > max(feitos, default=0)}
    for am in reversed(meses):  # o arquivo é atualizado nos dias 7, 12 e 20 do mês seguinte
        cache = C / f"{am}.json"
        fresco = cache.exists() and time.time() - cache.stat().st_mtime < 3 * 86400
        if am in feitos and (am not in recentes or fresco):
            continue
        novas = _linhas_mes(am)
        if not novas:
            log(f"  Prefeitura do Rio: {am % 100:02d}/{am // 100} ainda sem arquivo (ou sem o prefeito)")
            continue
        cache.write_text(json.dumps(novas, ensure_ascii=False), encoding="utf-8")
        linhas = pd.concat([linhas[linhas.aaaamm.astype(int) != am], pd.DataFrame(novas, columns=COLUNAS)], ignore_index=True)
        gravar_csv(linhas.sort_values(["aaaamm", "nome", "folha"]), LINHAS)
        log(f"  Prefeitura do Rio: {am % 100:02d}/{am // 100} ({len(novas)} linhas)")


def montar():
    if not LINHAS.exists():
        return None
    linhas = pd.read_csv(LINHAS).fillna("")
    # o vice vira prefeito depois do último mês com a folha normal de Paes (o acerto da saída vem depois, numa folha de rescisão)
    normal_paes = linhas[(linhas.nome == PREFEITO) & (linhas.folha.map(normalizar_nome) == "NORMAL")].aaaamm
    ultimo_paes = int(normal_paes.max()) if len(normal_paes) else 0
    saida = []
    for (am, nome), g in linhas.groupby(["aaaamm", "nome"]):
        tp = "pr" if nome == PREFEITO or am > ultimo_paes else "vp"
        normal = g[g.folha.map(normalizar_nome) == "NORMAL"]
        decimo_g = g[g.folha.map(normalizar_nome).str.contains(r"13|NATAL|DECIMO")]
        salario = float(normal.bruta.sum() - normal.abate_teto.sum())
        decimo = float(decimo_g.bruta.sum() - decimo_g.abate_teto.sum())
        resto = g.drop(normal.index.union(decimo_g.index))
        outros = float(resto.bruta.sum() - resto.abate_teto.sum())
        saida.append({"aaaamm": int(am), "tp": tp, "nome": nome, "pasta": f"Prefeitura {CFG['de']}", "salario": salario, "decimo": decimo,
                      "outros": outros, "bruta": salario + decimo + outros, "cedido": 0})
    return comum.montar(CFG, pd.DataFrame(saida, columns=comum.COLUNAS))
