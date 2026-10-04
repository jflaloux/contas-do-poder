"""Prefeitura de Vitória: prefeito, vice e secretários municipais, mês a mês.

Fonte: Portal de Dados Abertos de Vitória, conjunto "Pessoal", uma tabela por mês com o nome, a secretaria, o
quadro (efetivo, comissionado, cedido...), o cargo e a remuneração bruta de cada servidor, pela API do portal:
https://dadosabertos.vitoria.es.gov.br (daRecurso/RecursosConjunto?IdConjunto=2 e daRecurso/TabelaPaginada?Id=)
O CPF vem mascarado e não é guardado. Guardamos só o prefeito, o vice e os secretários em dados/municipios/vitoria/.
"""
import re
import time

import pandas as pd

from ..config import DADOS
from ..util import TempoEsgotado, _sessao, gravar_csv, log, normalizar_nome, verificar_prazo
from . import comum

COD = 3205309
INICIO = 202501
API = "https://dadosabertosapi.vitoria.es.gov.br/daRecurso"
CABECALHOS = {"Tectrilha-Sistema": "transparenciaWeb", "x-api-version": "1"}  # os mesmos que o site do portal manda
PAGINA = "https://dadosabertos.vitoria.es.gov.br/"
PASTA = DADOS / "municipios" / "vitoria"
LINHAS = PASTA / "prefeitura_remuneracao.csv"
MESES = {normalizar_nome(m): i for i, m in enumerate(["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto",
                                                      "Setembro", "Outubro", "Novembro", "Dezembro"], 1)}
COLUNAS = ["aaaamm", "tp", "nome", "cargo", "quadro", "secretaria", "bruta"]
CFG = {
    "cod": COD, "n": "Vitória", "uf": "ES", "de": "de Vitória", "casa": "Prefeitura de Vitória", "inicio": INICIO, "fonte": PAGINA, "pagina": PAGINA,
    "salario_nota": ("Remuneração bruta da folha da Prefeitura, antes dos descontos. A folha de Vitória dá só o total do mês: o que passa "
                     "do valor normal da própria pessoa (13º, férias, atrasados) aparece como \"outros pagamentos\"."),
    "notas": ["Entram o prefeito, a vice e os secretários municipais (e o secretário da Controladoria-Geral). Os subsecretários "
              "e os secretários executivos de conselhos, que também estão na folha, não entram.",
              "Secretário que é servidor de outro órgão (\"cedido por outros órgãos\", na folha) recebe da Prefeitura só uma parte: o "
              "salário vem do órgão de origem. Por isso fica fora das comparações.",
              "Lorenzo Pazolini renunciou à Prefeitura, com efeito em 4 de abril de 2026, para disputar o governo do Estado, e a vice, "
              "Cristhine (Cris) Samorini, assumiu. Pazolini não aparece na folha da Prefeitura de agosto de 2025 a março de 2026: "
              "nesses meses, a folha publicada não traz nenhum pagamento a ele, e a Prefeitura não explica por quê. Por isso, no site, "
              "os meses dele vão só até julho de 2025.",
              "Em abril de 2026, o mês da troca, a folha registra Cris Samorini com o cargo de secretária de Desenvolvimento da Cidade "
              "e Habitação (a pasta que ela comandava como vice). Em maio, já como prefeita, ela recebeu R$ 50.833,16 brutos, "
              "provavelmente com acertos de abril (a folha de Vitória dá só o total do mês)."],
    "credito_camara": "Câmara Municipal de Vitória",
}


def _tp(cargo):
    c = normalizar_nome(cargo)
    if c in ("PREFEITO", "PREFEITA"):
        return "pr"
    if c in ("VICE-PREFEITO", "VICE PREFEITO", "VICE-PREFEITA", "VICE PREFEITA"):
        return "vp"
    if re.match(r"^SECRETARI[OA] (MUNICIPAL|DA CONTROLADORIA|CHEFE|-CHEFE|GERAL)", c):
        return "se"
    return None


def _get(caminho, params):
    verificar_prazo()
    for tentativa in range(4):
        try:
            r = _sessao().get(f"{API}/{caminho}", params=params, headers=CABECALHOS, timeout=300)
            r.raise_for_status()
            return r.json()
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 3:
                raise
            time.sleep(15 * (tentativa + 1))


def coletar():
    recursos = {}
    for x in _get("RecursosConjunto", {"IdConjunto": 2}):
        m = re.search(r"-\s*([A-Za-zçÇ]+)/(\d{4})", x.get("nome") or "")
        if m and MESES.get(normalizar_nome(m.group(1))):
            am = int(m.group(2)) * 100 + MESES[normalizar_nome(m.group(1))]
            if am >= INICIO:
                recursos[am] = x["id"]
    linhas = pd.read_csv(LINHAS) if LINHAS.exists() else pd.DataFrame(columns=COLUNAS)
    feitos = set(linhas.aaaamm) if len(linhas) else set()
    ultimos = sorted(recursos)[-2:]
    PASTA.mkdir(parents=True, exist_ok=True)
    for am, rid in sorted(recursos.items()):
        if am in feitos and am not in ultimos:
            continue
        d = _get("TabelaPaginada", {"Id": rid, "paginaAtual": 1, "tamanhoPagina": 50000})
        achados = []
        for x in d.get("dados") or []:
            tp = _tp(x.get("Cargo"))
            if tp:
                achados.append({"aaaamm": am, "tp": tp, "nome": x["NomeServidor"].strip(), "cargo": x["Cargo"].strip(), "quadro": (x.get("Quadro") or "").strip(),
                                "secretaria": (x.get("Secretaria") or "").strip(), "bruta": comum.num(x.get("RemuneracaoBruta"))})
        linhas = pd.concat([linhas[linhas.aaaamm != am], pd.DataFrame(achados, columns=COLUNAS)], ignore_index=True)
        gravar_csv(linhas.sort_values(["aaaamm", "tp", "nome"]), LINHAS)
        log(f"  Prefeitura de Vitória: {am % 100:02d}/{am // 100} ({len(achados)} linhas)")
        time.sleep(2)


def _pasta(tp, secretaria):
    if tp in ("pr", "vp"):
        return f"Prefeitura {CFG['de']}"
    s = re.sub(r"^[A-Z]+\s*-\s*", "", secretaria.strip())  # "SEMUS-Secretaria de Saúde" -> "Secretaria de Saúde"
    return s or "Secretaria municipal"


def montar():
    if not LINHAS.exists():
        return None
    linhas = pd.read_csv(LINHAS).fillna("")
    saida = []
    # a pasta é a do cargo ("Secretário Municipal de Obras"); a lotação ("SEMOB-Secretaria de Obras") só dá o nome com acentos
    nomes = {normalizar_nome(_pasta("se", x)): _pasta("se", x) for x in linhas.secretaria.unique() if x}

    def pasta(tp, cargo, secretaria):
        if tp == "se" and normalizar_nome(cargo).startswith("SECRETARIO DA CONTROLADORIA"):
            return "Secretaria da Controladoria-Geral do Município"  # o cargo é "Secretário da Controladoria-Geral"
        c = re.sub(r"^SECRETARI[OA] (MUNICIPAL )?(D[AEO]S? )?", "", normalizar_nome(cargo))
        for n, bonito in nomes.items():
            if tp == "se" and re.sub(r"^SECRETARIA (MUNICIPAL )?(D[AEO]S? )?", "", n) == c:
                return bonito
        return _pasta(tp, secretaria)

    for nome, g in linhas.groupby("nome"):
        normal = float(g.bruta.median())
        for (am, tp), gm in g.groupby(["aaaamm", "tp"]):
            b = float(gm.bruta.sum())
            extra = max(0.0, b - normal) if b > normal * 1.1 else 0.0
            cedido = 1 if tp == "se" and gm.quadro.map(normalizar_nome).str.contains("CEDIDO").any() else 0
            saida.append({"aaaamm": int(am), "tp": tp, "nome": nome, "pasta": pasta(tp, gm.cargo.iloc[0], gm.secretaria.iloc[0]), "salario": b - extra,
                          "decimo": 0.0, "outros": extra, "bruta": b, "cedido": cedido})
    return comum.montar(CFG, pd.DataFrame(saida, columns=comum.COLUNAS))
