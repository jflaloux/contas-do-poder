"""Prefeitura do Recife: prefeito, vice e secretários municipais, mês a mês.

Fonte: Portal de Dados Abertos do Recife, "Relação dos Servidores e salários da Prefeitura do Recife", um arquivo
por ano (CSV de ~85 MB), com o nome de cada servidor: https://dados.recife.pe.gov.br/dataset/servidores
O robô acha os arquivos pela página do conjunto de dados e lê cada um aos poucos, ficando só com o prefeito, o vice e
os secretários. A API do portal (/api/) não é usada: o robots.txt não deixa robôs usarem, e pede 10 s entre pedidos.

Colunas usadas: mês, nome, função (PREFEITO DA CAPITAL, VICE-PREFEITO, SECRETARIO MUNICIPAL), unidade (a secretaria),
proventos (o bruto), férias e 13º ("natalina"). O CPF vem mascarado e não é guardado.
"""
import json
import re
import pandas as pd

from ..config import CACHE, DADOS
from ..util import cache_valido, gravar_csv, log, normalizar_nome, recursos_ckan
from . import comum

COD = 2611606
INICIO = 202501
PAGINA = "https://dados.recife.pe.gov.br/dataset/servidores"
PASTA = DADOS / "municipios" / "recife"
LINHAS = PASTA / "prefeitura_remuneracao.csv"
C = CACHE / "pcr"
FUNCOES = {"PREFEITO DA CAPITAL": "pr", "PREFEITO": "pr", "VICE-PREFEITO": "vp", "VICE PREFEITO": "vp", "SECRETARIO MUNICIPAL": "se"}
COLUNAS = ["aaaamm", "tp", "nome", "funcao", "unidade", "vinculo", "proventos", "ferias", "natal", "genero"]
# unidades que vêm só com a sigla ("GABINETE DA SEFIN"); as que não estão aqui ficam com a sigla
SIGLAS = {"SEFIN": "Secretaria de Finanças", "SMAS": "Secretaria de Meio Ambiente e Sustentabilidade", "SESAU": "Secretaria de Saúde",
          "SEHAB": "Secretaria de Habitação", "SEINFRA": "Secretaria de Infraestrutura", "SETUREL": "Secretaria de Turismo e Lazer",
          "STQP": "Secretaria de Trabalho e Qualificação Profissional", "SESAN": "Secretaria de Saneamento",
          "SEOPS": "Secretaria de Ordem Pública e Segurança", "SEDUL": "Secretaria de Desenvolvimento Urbano e Licenciamento"}
# nomes cortados na folha
NOMES = {"SEC ASSISTENCIA SOCIAL E COMBATE A FOME": "Secretaria de Assistência Social e Combate à Fome",
         "SEC TRANSF DIGITAL CIENCIA E TECNOLOGIA": "Secretaria de Transformação Digital, Ciência e Tecnologia",
         "SEC TRABALHO QUALIFICACAO PROFISSIONAL": "Secretaria de Trabalho e Qualificação Profissional",
         "SEC DESENVOLVIMENTO ECONOMICO": "Secretaria de Desenvolvimento Econômico"}
CFG = {
    "cod": COD, "n": "Recife", "uf": "PE", "de": "do Recife", "casa": "Prefeitura do Recife", "inicio": INICIO, "fonte": PAGINA, "pagina": PAGINA,
    "salario_nota": ("Proventos brutos da folha da Prefeitura, antes dos descontos: o subsídio (ou, para servidor de outro órgão, o que a "
                     "Prefeitura paga), mais 13º e férias quando pagos no mês."),
    "notas": ["A Prefeitura publica a folha de cada ano numa tabela nos dados abertos, com o nome de cada servidor, atualizada de tempos "
              "em tempos (por isso os últimos meses podem demorar a aparecer).",
              "Em abril de 2026, o prefeito João Campos deixou o cargo para disputar a eleição, e o vice, Victor Marques, assumiu a Prefeitura."],
    "credito_camara": "Câmara Municipal do Recife",
}


def _ano(ano, url, arquivo, dias):
    """As linhas do prefeito, do vice e dos secretários no arquivo do ano (guardadas no cache)."""
    if cache_valido(arquivo, dias):
        return json.loads(arquivo.read_text(encoding="utf-8"))
    from ..folhas_estaduais.comum import linhas_csv
    _, achadas = linhas_csv(url, list(FUNCOES), encoding="utf-8-sig", sep=";")
    regs = [x for x in achadas if (x.get("nsalsefunc") or "").strip() in FUNCOES]
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(json.dumps(regs, ensure_ascii=False), encoding="utf-8")
    return regs


def coletar():
    from ..vereadores.comum import ultimo_mes_fechado
    ano_atual = ultimo_mes_fechado() // 100
    recursos = {}
    for r in recursos_ckan(PAGINA):
        m = re.match(r"\s*(\d{4})\s*-", r.get("name") or "")
        if m and int(m.group(1)) >= INICIO // 100 and (r.get("url") or "").lower().endswith(".csv"):
            recursos[int(m.group(1))] = r["url"]
    velhas = pd.read_csv(LINHAS) if LINHAS.exists() else pd.DataFrame(columns=COLUNAS)
    linhas = []
    for ano, url in sorted(recursos.items()):
        regs = _ano(ano, url, C / f"folha_{ano}.json", 5 if ano >= ano_atual else None)
        for x in regs:
            linhas.append({"aaaamm": ano * 100 + int(x["asalsemess"]), "tp": FUNCOES[x["nsalsefunc"].strip()], "nome": x["nsalsenome"].strip(),
                           "funcao": x["nsalsefunc"].strip(), "unidade": (x.get("esalseunidade") or "").strip(), "vinculo": (x.get("nsalsecarg") or "").strip(),
                           "proventos": comum.num(x.get("vsalseprov")), "ferias": comum.num(x.get("vsalseferi")), "natal": comum.num(x.get("vsalsenatl")),
                           "genero": x.get("esalsegenero") or ""})
        log(f"  Prefeitura do Recife: {ano}, {len(regs)} linhas")
    novas = pd.DataFrame(linhas, columns=COLUNAS)
    if len(velhas):  # um ano que sumiu do portal continua com o que já estava gravado
        novas = pd.concat([velhas[~(velhas.aaaamm // 100).isin(set(novas.aaaamm // 100))], novas], ignore_index=True)
    PASTA.mkdir(parents=True, exist_ok=True)
    gravar_csv(novas.sort_values(["aaaamm", "tp", "nome"]), LINHAS)


def _pasta(unidade):
    u = normalizar_nome(unidade)
    if u.startswith("GABINETE DA "):
        sigla = u.replace("GABINETE DA ", "").strip()
        return SIGLAS.get(sigla, f"Secretaria ({sigla})")
    if u in NOMES:
        return NOMES[u]
    if u.startswith("SEC "):
        resto = re.sub(r"^SEC\s+", "", u)
        if not re.match(r"(DE|DA|DO|DAS|DOS)\s", resto):
            resto = "DE " + resto
        return comum.bonito("SECRETARIA " + resto)
    if u.startswith("CONTROLADORIA"):
        return "Controladoria-Geral do Município"
    return comum.bonito(unidade) if unidade else "Secretaria municipal"


def montar():
    if not LINHAS.exists():
        return None
    linhas = pd.read_csv(LINHAS).fillna("")
    saida = []
    # R$ 0 na folha no mês (somando todos os cargos da pessoa): quem paga é outro órgão (por exemplo, o vereador
    # licenciado que continua recebendo da Câmara). O vice que também é secretário recebe R$ 0 como vice e o salário
    # de secretário: não conta.
    total = linhas.groupby(["nome", "aaaamm"]).proventos.sum()
    for nome, g in linhas.groupby("nome"):
        # a secretaria de cada mês; "Gabinete da Sigla" sem nome conhecido: a secretaria da própria pessoa em outro mês
        certas = [_pasta(u) for u in g.unidade if normalizar_nome(u).startswith("SEC ")]
        for r in g.itertuples():
            pasta = f"Prefeitura {CFG['de']}" if r.tp in ("pr", "vp") else _pasta(r.unidade)
            if r.tp == "se" and "(" in pasta and certas:
                pasta = max(set(certas), key=certas.count)
            natal, ferias = float(r.natal or 0), float(r.ferias or 0)
            saida.append({"aaaamm": int(r.aaaamm), "tp": r.tp, "nome": nome, "pasta": pasta, "salario": float(r.proventos) - natal - ferias,
                          "decimo": natal, "outros": ferias, "bruta": float(r.proventos),
                          "cedido": 1 if float(total[(nome, r.aaaamm)]) <= 0 else 0, "genero": r.genero})
    return comum.montar(CFG, pd.DataFrame(saida, columns=[*comum.COLUNAS, "genero"]))
