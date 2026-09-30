"""Prefeitura de Porto Alegre: prefeito, vice e secretários municipais, mês a mês.

Fonte: Portal Transparência da Prefeitura (Procempa), "Remuneração dos servidores", com o nome de cada servidor:
https://portaltransparenciapmpa.procempa.com.br/portalpmpa/fpRemuneracaoPesquisa.do
O portal faz uma pesquisa (por mês e tipo de folha) e depois oferece a planilha da pesquisa em CSV, com o órgão de
exercício, o cargo e as rubricas (básica, 13º, férias, eventuais, abate-teto, jetons...). O robô faz o mesmo que o
botão "CSV" da página. Sem CPF. Guardamos só o prefeito, o vice e os secretários em dados/municipios/porto_alegre/.
"""
import io
import re
import time

import pandas as pd

from ..config import DADOS
from ..util import TempoEsgotado, _sessao, log, normalizar_nome, verificar_prazo
from . import comum

COD = 4314902
INICIO = 202501
BASE = "https://portaltransparenciapmpa.procempa.com.br/portalpmpa"
PAGINA = f"{BASE}/fpRemuneracaoPesquisa.do?viaMenu=true"
PASTA = DADOS / "municipios" / "porto_alegre"
LINHAS = PASTA / "prefeitura_remuneracao.csv"
COLUNAS = ["aaaamm", "folha", "tp", "nome", "orgao", "cargo", "basica", "natalina", "ferias", "eventuais", "abate_teto", "jetons"]
CFG = {
    "cod": COD, "n": "Porto Alegre", "uf": "RS", "de": "de Porto Alegre", "casa": "Prefeitura de Porto Alegre", "inicio": INICIO,
    "fonte": PAGINA, "pagina": PAGINA,
    "salario_nota": ("Remuneração bruta da folha da Prefeitura: a remuneração básica, mais 13º, férias, pagamentos eventuais e jetons, "
                     "já descontado o abate-teto, antes do imposto e da previdência. Diárias e verbas indenizatórias não entram."),
    "notas": ["O Portal Transparência da Prefeitura publica a folha de cada mês com o nome, o órgão de exercício e as rubricas de "
              "cada servidor. Entram o prefeito, a vice e todas as pessoas com o cargo de secretário municipal.",
              "Dois secretários aparecem na folha com o cargo de \"Secretário Municipal Extraordinário de Governo e Assuntos Relevantes\", "
              "lotados no Gabinete do Prefeito, sem dizer qual assunto cada um cuida: aparecem como \"secretário municipal, lotado no "
              "Gabinete do Prefeito\".",
              "O 13º é pago numa folha à parte em dezembro (a \"natalina\"), que o robô também baixa. Alguns secretários (como o de "
              "Educação) recebem cerca de R$ 14,7 mil, e não os R$ 21 mil dos demais: a folha não diz por quê (pode ser servidor que "
              "optou por outra remuneração)."],
    "credito_camara": "Câmara Municipal de Porto Alegre",
}


def _tp(cargo):
    c = normalizar_nome(cargo)
    if c == "PREFEITO":
        return "pr"
    if c in ("VICE-PREFEITO", "VICE PREFEITO"):
        return "vp"
    if c.startswith("SECRETARIO MUNICIPAL"):
        return "se"
    return None


def _folha(s, am, tipo):
    """CSV da folha inteira do mês (a pesquisa sem filtros), como o botão da página."""
    verificar_prazo()
    comp = f"01/{am % 100:02d}/{am // 100}"
    d = {"perform": "search", "actionForward": "success", "strutsFormName": "fpRemuneracaoPesquisaForm", "validate": "true", "pesquisar": "true",
         "defaultSearch.pageSize": "0", "empresaSelecionada": "0", "secretariaSelecionada": "", "tipoFolhaSelecionada": tipo,
         "competenciaSelecionadaAsString": comp, "criterioNomeServidor": ""}
    for tentativa in range(3):
        try:
            r = s.post(f"{BASE}/fpRemuneracaoPesquisa.do", data=d, timeout=180)
            r.raise_for_status()
            m = re.search(r"invokePrint\('fpRemuneracaoRelatorio\.do', 'CSV', '([^']*)'\)", r.text)
            if not m:
                return None  # mês ou tipo de folha que não existe
            time.sleep(2)
            r = s.get(f"{BASE}/fpRemuneracaoRelatorio.do?{m.group(1)}acao=CSV", timeout=300)
            r.raise_for_status()
            break
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 2:
                raise
            time.sleep(20)
    t = r.content.decode("latin1")
    i = t.find('"Compet')
    if i < 0:
        return None
    df = pd.read_csv(io.StringIO(t[i:]), sep=";", dtype=str).fillna("")
    df.columns = [normalizar_nome(c) for c in df.columns]
    return df


def coletar():
    from ..vereadores.comum import meses, menos_meses, ultimo_mes_fechado
    ate = ultimo_mes_fechado()
    recentes = menos_meses(ate, 2)
    linhas = pd.read_csv(LINHAS) if LINHAS.exists() else pd.DataFrame(columns=COLUNAS)
    feitos = set(zip(linhas.aaaamm, linhas.folha)) if len(linhas) else set()
    s = _sessao()
    s.get(PAGINA, timeout=60)  # abre a sessão, como o navegador
    PASTA.mkdir(parents=True, exist_ok=True)
    for a, m in meses(INICIO, ate):
        am = a * 100 + m
        # folha mensal todo mês; a do 13º (natalina) em novembro e dezembro
        for tipo in ["MENSAL"] + (["NATALINA"] if m in (11, 12) else []):
            if (am, tipo) in feitos and am <= recentes:
                continue
            df = _folha(s, am, tipo)
            time.sleep(2)
            if df is None or not len(df):
                continue
            achados = []
            for r in df.itertuples(index=False):
                r = dict(zip(df.columns, r))
                tp = _tp(r.get("CARGO"))
                if tp:
                    achados.append({"aaaamm": am, "folha": tipo, "tp": tp, "nome": r["NOME"].strip(), "orgao": r.get("ORGAO DE EXERCICIO", "").strip(),
                                    "cargo": r["CARGO"].strip(), "basica": comum.num(r.get("REMUNERACAO BASICA BRUTA")),
                                    "natalina": comum.num(r.get("GRATIFICACAO NATALINA")), "ferias": comum.num(r.get("FERIAS")),
                                    "eventuais": comum.num(r.get("OUTRAS REMUNERACOES EVENTUAIS")), "abate_teto": comum.num(r.get("ABATE TETO")),
                                    "jetons": comum.num(r.get("JETONS"))})
            linhas = pd.concat([linhas[~((linhas.aaaamm == am) & (linhas.folha == tipo))], pd.DataFrame(achados, columns=COLUNAS)], ignore_index=True)
            linhas.sort_values(["aaaamm", "folha", "tp", "nome"]).to_csv(LINHAS, index=False)
            log(f"  Prefeitura de Porto Alegre: {m:02d}/{a} {tipo.lower()} ({len(achados)} linhas)")


def _pasta(tp, orgao):
    if tp in ("pr", "vp"):
        return f"Prefeitura {CFG['de']}"
    o = re.sub(r"^Secretaria Mun\b\.?", "Secretaria Municipal", orgao.strip())
    o = re.sub(r"^Secretaria Municipal (?!de |da |do |das |dos |Geral )", "Secretaria Municipal de ", o)  # nomes cortados na folha
    for curto, longo in (("Desenv", "Desenvolvimento"), ("Urban", "Urbanismo"), ("Sustentab", "Sustentabilidade"), ("Govern", "Governança"),
                         ("Planejam", "Planejamento"), ("Estrat", "Estratégicos")):
        o = re.sub(rf"\b{curto}\b", longo, o)
    return o or "Secretaria municipal"


def montar():
    if not LINHAS.exists():
        return None
    linhas = pd.read_csv(LINHAS).fillna("")
    saida = []
    for (am, nome, tp), g in linhas.groupby(["aaaamm", "nome", "tp"]):
        m, n = g[g.folha != "NATALINA"], g[g.folha == "NATALINA"]
        # na folha "natalina" (a do 13º, em dezembro), o 13º vem na coluna da remuneração básica
        salario = float(m.basica.sum()) - float(m.abate_teto.sum())
        decimo = float(m.natalina.sum()) + float(n.basica.sum() + n.natalina.sum() - n.abate_teto.sum())
        outros = float(g.ferias.sum() + g.eventuais.sum() + g.jetons.sum())
        saida.append({"aaaamm": int(am), "tp": tp, "nome": nome, "pasta": _pasta(tp, g.orgao.iloc[0]), "salario": salario, "decimo": decimo,
                      "outros": outros, "bruta": salario + decimo + outros, "cedido": 0})
    return comum.montar(CFG, pd.DataFrame(saida, columns=comum.COLUNAS))
