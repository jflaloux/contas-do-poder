"""Prefeitura de Fortaleza: prefeito, vice e secretários municipais, mês a mês.

Fonte: Portal de Dados Abertos de Fortaleza, "Relação de Servidores da PMF", um CSV por mês (~24 MB, latin1, ";"),
com o nome, o órgão, o cargo e os proventos de cada servidor, sem CPF:
https://dados.fortaleza.ce.gov.br/dataset/servidores

O robô baixa só os meses que ainda não processou (e os 2 últimos de novo) e guarda só as linhas do prefeito, do vice
e dos secretários municipais em dados/municipios/fortaleza/.
"""
import csv
import io
import re
import time

import pandas as pd

from ..config import DADOS
from ..util import TempoEsgotado, _sessao, gravar_csv, log, normalizar_nome, recursos_ckan, verificar_prazo
from . import comum

COD = 2304400
INICIO = 202501
PAGINA = "https://dados.fortaleza.ce.gov.br/dataset/servidores"
PASTA = DADOS / "municipios" / "fortaleza"
LINHAS = PASTA / "prefeitura_remuneracao.csv"
CARGOS = {"PREFEITO": "pr", "VICE PREFEITO": "vp", "VICE-PREFEITO": "vp", "SECRETARIO MUNICIPAL": "se"}
COLUNAS = ["aaaamm", "tp", "nome", "orgao", "vinculo", "cargo", "proventos", "desligamento"]
# órgão (sigla na folha) -> nome; as siglas que não estão aqui aparecem como estão
ORGAOS = {
    "SMS": "Secretaria Municipal da Saúde", "SME": "Secretaria Municipal da Educação", "SEFIN": "Secretaria Municipal das Finanças",
    "SEPOG": "Secretaria Municipal do Planejamento, Orçamento e Gestão", "SEINF": "Secretaria Municipal da Infraestrutura",
    "SEUMA": "Secretaria Municipal do Urbanismo e Meio Ambiente", "SECULTFOR": "Secretaria Municipal da Cultura",
    "SECEL": "Secretaria Municipal do Esporte e Lazer", "SESEC": "Secretaria Municipal da Segurança Cidadã",
    "SETFOR": "Secretaria Municipal do Turismo", "SDE": "Secretaria Municipal do Desenvolvimento Econômico",
    "SDHDS": "Secretaria dos Direitos Humanos e Desenvolvimento Social", "SEJUV": "Secretaria Municipal da Juventude",
    "SEGOV": "Secretaria Municipal de Governo", "SEGER": "Secretaria Municipal da Gestão Regional", "SEMULHER": "Secretaria Municipal das Mulheres",
    "SMPA": "Secretaria Municipal de Proteção Animal", "SERC": "Secretaria Municipal de Relações Comunitárias",
    "SELIFOR": "Secretaria Municipal das Licitações", "CLFOR": "Central de Licitações da Prefeitura de Fortaleza",
    "HABITAFOR": "Secretaria Municipal do Desenvolvimento Habitacional", "CGM": "Controladoria e Ouvidoria Geral do Município",
    "PGM": "Procuradoria-Geral do Município", "SCSP": "Secretaria Municipal da Conservação e Serviços Públicos",
    "GAB PREFEITO": "Gabinete do Prefeito", "GABIVICE": "Gabinete da Vice-prefeita", "AMC": "Autarquia Municipal de Trânsito e Cidadania",
    "AGEFIS": "Agência de Fiscalização de Fortaleza", "URBFOR": "Autarquia de Urbanismo e Paisagismo de Fortaleza",
    "CITINOVA": "Fundação de Ciência, Tecnologia e Inovação de Fortaleza", "IPM": "Instituto de Previdência do Município",
    "PROCON": "Procon Fortaleza",
}
# lotações com vários secretários ao mesmo tempo: os secretários regionais (as 12 Secretarias Regionais respondiam à
# Secretaria da Gestão Regional, extinta em 2025, e agora respondem à Secretaria de Governo) e os secretários do gabinete
LOTACOES = {"SEGOV", "SEGER", "GAB PREFEITO", "GABIVICE"}
CFG = {
    "cod": COD, "n": "Fortaleza", "uf": "CE", "de": "de Fortaleza", "casa": "Prefeitura de Fortaleza", "inicio": INICIO, "fonte": PAGINA, "pagina": PAGINA,
    "salario_nota": ("Proventos brutos da folha da Prefeitura, antes dos descontos. A folha de Fortaleza dá só o total do mês: o que passa "
                     "do valor normal da própria pessoa (13º, férias, atrasados) aparece como \"outros pagamentos\"."),
    "notas": ["Entram todas as pessoas com o cargo de secretário municipal na folha: os titulares das secretarias, os secretários "
              "regionais (Fortaleza tem 12 Secretarias Regionais, as \"prefeiturinhas\" de cada parte da cidade), os secretários lotados "
              "no Gabinete do Prefeito e quem preside órgãos com status de secretaria (como a AMC, a Agefis, a Citinova e o Procon).",
              "A folha diz só o órgão onde cada secretário está lotado, não a pasta que ele comanda. Quando só há um secretário no órgão, "
              "é o titular da pasta. Os secretários regionais aparecem todos lotados na Secretaria de Governo (antes de maio de 2025, na "
              "Secretaria da Gestão Regional, extinta na reforma administrativa), sem dizer qual Regional cada um comanda: por isso "
              "aparecem como \"secretário municipal, lotado na Secretaria Municipal de Governo\".",
              "Quando a Prefeitura paga a um secretário menos de 30% do normal do cargo naquele mês (por exemplo, R$ 2.810 em vez de "
              "R$ 21.551), entendemos que ele recebe de outro órgão (a Câmara, no caso do vereador licenciado, ou o órgão de origem, "
              "no caso do servidor): esses meses ficam fora das comparações. A folha não diz de onde vem o resto.",
              "Vários vereadores eleitos em 2024 se licenciaram da Câmara para serem secretários (em geral, das Regionais). O vereador "
              "licenciado escolhe entre o salário de vereador, pago pela Câmara, e o de secretário, pago pela Prefeitura."],
    "credito_camara": "Câmara Municipal de Fortaleza",
}


def _meses():
    """{AAAAMM: url} dos arquivos do Portal."""
    itens = recursos_ckan(PAGINA)
    saida = {}
    for x in itens:
        m = re.search(r"relacao_(\d{6})\.csv", x.get("url") or "")
        if m and int(m.group(1)) >= INICIO:
            saida[int(m.group(1))] = x["url"]
    return saida


def _ler(am, url):
    verificar_prazo()
    for tentativa in range(3):
        try:
            r = _sessao().get(url, timeout=600)
            r.raise_for_status()
            time.sleep(10)  # Crawl-delay do robots.txt do portal
            break
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 2:
                raise
            time.sleep(20)
    leitor = csv.reader(io.StringIO(r.content.decode("latin1")), delimiter=";")
    cab = [normalizar_nome(c) for c in next(leitor)]
    col = lambda parte: next(i for i, c in enumerate(cab) if parte in c)
    i_org, i_nome, i_vinc, i_cargo, i_prov, i_desl = col("ORGAO"), col("SERVIDOR"), col("VINCULO"), col("CARGO"), col("PROVENTOS"), col("DESLIGAMENTO")
    achados = []
    for l in leitor:
        if len(l) <= i_prov:
            continue
        tp = CARGOS.get(normalizar_nome(l[i_cargo]))
        if tp:
            achados.append({"aaaamm": am, "tp": tp, "nome": l[i_nome].strip(), "orgao": l[i_org].strip(), "vinculo": l[i_vinc].strip(),
                            "cargo": l[i_cargo].strip(), "proventos": comum.num(l[i_prov]), "desligamento": l[i_desl].strip()})
    return achados


def coletar():
    arquivos = _meses()
    linhas = pd.read_csv(LINHAS) if LINHAS.exists() else pd.DataFrame(columns=COLUNAS)
    feitos = set(linhas.aaaamm) if len(linhas) else set()
    ultimos = sorted(arquivos)[-2:]
    PASTA.mkdir(parents=True, exist_ok=True)
    for am, url in sorted(arquivos.items()):
        if am in feitos and am not in ultimos:
            continue
        achados = _ler(am, url)
        linhas = pd.concat([linhas[linhas.aaaamm != am], pd.DataFrame(achados, columns=COLUNAS)], ignore_index=True)
        gravar_csv(linhas.sort_values(["aaaamm", "tp", "nome"]), LINHAS)
        log(f"  Prefeitura de Fortaleza: {am % 100:02d}/{am // 100} ({len(achados)} linhas)")
        time.sleep(2)


def _pasta(tp, orgao):
    if tp in ("pr", "vp"):
        return f"Prefeitura {CFG['de']}"
    o = re.sub(r"\s+", " ", normalizar_nome(orgao)).strip()
    o2 = o.replace(" ", "")
    for sigla, nome in ORGAOS.items():
        if o == sigla or o2 == sigla.replace(" ", ""):
            return nome
    return f"Secretaria ({orgao.strip()})"


def montar():
    if not LINHAS.exists():
        return None
    linhas = pd.read_csv(LINHAS).fillna("")
    saida = []
    for nome, g in linhas.groupby("nome"):
        normal = float(g.proventos.median())
        for (am, tp), gm in g.groupby(["aaaamm", "tp"]):
            prov = float(gm.proventos.sum())
            extra = max(0.0, prov - normal) if prov > normal * 1.1 else 0.0  # 13º, férias, atrasados
            org = re.sub(r"\s+", " ", normalizar_nome(gm.orgao.iloc[0])).strip()
            lot = 1 if tp == "se" and (org in LOTACOES or org.replace(" ", "") in {x.replace(" ", "") for x in LOTACOES}) else 0
            saida.append({"aaaamm": int(am), "tp": tp, "nome": nome, "pasta": _pasta(tp, gm.orgao.iloc[0]), "salario": prov - extra,
                          "decimo": 0.0, "outros": extra, "bruta": prov, "cedido": 0, "lotado": lot})
    df = pd.DataFrame(saida, columns=[*comum.COLUNAS, "lotado"])
    # secretário com um valor muito abaixo do normal do cargo naquele mês (menos de 30% da mediana): a Prefeitura
    # paga só uma parte; o resto, se houver, vem de outro órgão (fica fora das comparações)
    # (somando todos os cargos da pessoa no mês: a vice que também é secretária recebe R$ 0 como secretária e o
    # salário de vice; não conta)
    med = df[df.tp == "se"].groupby("aaaamm").bruta.median()
    total = df.groupby(["nome", "aaaamm"]).bruta.sum()
    chefe = set(zip(df[df.tp.isin(["pr", "vp"])].nome, df[df.tp.isin(["pr", "vp"])].aaaamm))
    df["cedido"] = [1 if tp == "se" and (n, am) not in chefe and total[(n, am)] < 0.3 * med.get(am, 0) else 0
                    for n, am, tp in zip(df.nome, df.aaaamm, df.tp)]
    return comum.montar(CFG, df)
