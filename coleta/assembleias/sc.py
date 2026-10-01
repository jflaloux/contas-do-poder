"""Assembleia Legislativa de Santa Catarina (Alesc): deputado estadual por deputado estadual.

Fontes:
- Gastos dos gabinetes parlamentares (diárias de deputados e funcionários, passagens, telefone, veículos, aluguel do
  escritório, reembolsos), um CSV por ano: https://transparencia.alesc.sc.gov.br/gabinetes-parlamentares/csv/AAAA
  (índice em https://transparencia.alesc.sc.gov.br/gabinetes-parlamentares/dados-abertos). O CSV traz o favorecido,
  mas não o CNPJ. Nas diárias e passagens o favorecido é uma pessoa (o deputado ou um funcionário): não guardamos o
  nome, só a categoria e o valor.
- Subsídio: Lei 18.642/2023 (R$ 33.006,39 desde fev/2024 e R$ 34.774,64 desde fev/2025).
- Nome completo, gênero e eleito/suplente: TSE (eleição de 2022); partido: candidatura de 2026 no TSE.
Quem esteve no cargo em cada mês sai dos meses com gastos do gabinete.
"""
import csv
import io
import time

import pandas as pd

from ..config import CACHE, DADOS
from ..prefeituras.comum import feminino, num
from ..util import TempoEsgotado, _sessao, dormir, log, normalizar_nome, verificar_prazo
from ..vereadores import comum as vc
from . import comum

UF = "SC"
COD = comum.CODIGOS_UF[UF]
INICIO = 202501
CSV = "https://transparencia.alesc.sc.gov.br/gabinetes-parlamentares/csv/{ano}"
PASTA = DADOS / "assembleias" / "sc"
C = CACHE / "assembleias" / "sc"
PESSOA = {"DIARIAS", "PASSAGENS"}  # o favorecido é o deputado ou um funcionário
CFG = {
    "cod": COD, "n": "Santa Catarina", "uf": UF, "casa": "Assembleia Legislativa de Santa Catarina", "vagas": 40, "inicio": INICIO,
    "id_prefixo": "est", "k": "e", "cargo": ("Deputada estadual", "Deputado estadual"),
    "subsidio": [[202402, 33006.39], [202502, 34774.64]],
    "salario_nota": ("Subsídio fixado em lei (Lei 18.642/2023), proporcional aos meses no cargo. A Alesc mostra o contracheque de cada "
                     "deputado só numa janela da página, por isso o 13º e outros pagamentos não aparecem aqui."),
    "verba_nome": "Gastos do gabinete",
    "verba_regra": "Diárias, passagens, telefone, veículos, aluguel do escritório de apoio e reembolsos de despesas do gabinete.",
    "verba_notas": ["Entram as diárias e passagens do deputado e dos funcionários do gabinete.",
                    "A Alesc publica o favorecido, mas não o CNPJ. Nas diárias e passagens o favorecido é uma pessoa e não aparece aqui."],
    "pagina": "https://transparencia.alesc.sc.gov.br/deputados",
    "notas": ["Quem está no cargo hoje: a lista de deputados da Alesc. Desde quando: os meses com gastos do gabinete (um mês sem "
              "gastos entre dois com gastos conta como mês no cargo).", "Partido: o da candidatura de 2026 no TSE. Quem não é candidato em 2026 aparece sem partido."],
    "fontes": {"verba": "https://transparencia.alesc.sc.gov.br/gabinetes-parlamentares/dados-abertos", "subsidio": "https://leis.alesc.sc.gov.br/ato-normativo/21961"},
}


def _baixar(ano, dias):
    arq = C / f"gabinetes_{ano}.csv"
    if arq.exists() and time.time() - arq.stat().st_mtime < dias * 86400:
        return arq.read_bytes()
    verificar_prazo()
    for tentativa in range(3):
        try:
            r = _sessao().get(CSV.format(ano=ano), timeout=300)
            r.raise_for_status()
            break
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 2:
                raise
            dormir(20)
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_bytes(r.content)
    dormir(3)
    return r.content


def _em_exercicio():
    """Nomes da página de deputados da Alesc, com o mês de referência (o mês da folha em que aparecem)."""
    import html as H
    import re
    verificar_prazo()
    t = _sessao().get("https://transparencia.alesc.sc.gov.br/deputados", timeout=120).text
    saida = []
    for linha in re.findall(r"<tr[^>]*>(.*?)</tr>", t, flags=re.S):
        c = [H.unescape(re.sub(r"<[^>]+>", "", x)).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", linha, flags=re.S)]
        if len(c) >= 2 and re.match(r"\d{2}/\d{4}$", c[1]):
            saida.append({"nome": " ".join(c[0].split()), "mes_referencia": c[1]})
    return pd.DataFrame(saida)


def coletar():
    PASTA.mkdir(parents=True, exist_ok=True)
    ex = _em_exercicio()
    if len(ex) >= 30:
        ex.to_csv(PASTA / "em_exercicio.csv", index=False)
    ano_hoje = int(time.strftime("%Y"))
    linhas = []
    for ano in range(INICIO // 100, ano_hoje + 1):
        texto = _baixar(ano, 3 if ano >= ano_hoje - 1 else 3650).decode("utf-8-sig")
        for r in csv.DictReader(io.StringIO(texto), delimiter=";"):
            data = (r.get("Data de Referência") or "").strip()
            if len(data) != 10:
                continue
            d, m, a = data.split("/")
            verba = (r.get("Verba") or "").strip()
            linhas.append({"ano": int(a), "mes": int(m), "deputado": " ".join((r.get("Conta") or "").split()), "verba": verba,
                           "descricao": (r.get("Descrição") or "").strip(),
                           "fornecedor": "" if normalizar_nome(verba) in PESSOA else (r.get("Favorecido") or "").strip(),
                           "valor": num(r.get("Valor"))})
    df = pd.DataFrame(linhas)
    df = df[(df.ano * 100 + df.mes >= INICIO) & (df.deputado != "")]
    df.sort_values(["ano", "mes", "deputado", "verba", "descricao"]).to_csv(PASTA / "gastos_gabinete.csv", index=False)
    log(f"  Alesc: {len(df)} gastos de gabinete de {df.deputado.nunique()} deputados desde {INICIO % 100:02d}/{INICIO // 100}")


def montar(tipos):
    arq = PASTA / "gastos_gabinete.csv"
    if not arq.exists():
        return None
    g = pd.read_csv(arq).fillna("")
    tse = comum.tse_2022(UF)
    partidos = comum.partido_2026(UF)
    ultimo = vc.ultimo_mes_fechado()
    ultimo_dado = int((g.ano * 100 + g.mes).max())
    ex = pd.read_csv(PASTA / "em_exercicio.csv").fillna("") if (PASTA / "em_exercicio.csv").exists() else pd.DataFrame(columns=["nome", "mes_referencia"])
    mes_lista = max((int(m[3:]) * 100 + int(m[:2]) for m in ex.mes_referencia), default=0)
    hoje = [n for n, m in zip(ex.nome, ex.mes_referencia) if int(m[3:]) * 100 + int(m[:2]) == mes_lista]

    def no_cargo(nome, t):
        alvo = {nome, t.get("nome", ""), t.get("urna", "")} - {""}
        return any(comum.achar(h, {normalizar_nome(a): {"nome": a, "urna": a, "eleito": "eleito"}}) for a in alvo for h in hoje)

    ver, mandatos, cods = [], [], {}
    for nome, gg in g.groupby("deputado"):
        t = comum.achar(nome, tse) or {}
        codigo = comum.codigo_de(nome, t)
        cods[nome] = codigo
        ver.append({"codigo": codigo, "nome": nome, "nome_civil": vc.titulo(t.get("nome", "")) if t else "",
                    "partido": partidos.get(normalizar_nome(t.get("nome", "")), "") if t else "",
                    "genero": t.get("genero") or ("F" if feminino(nome) else "M"), "eleito": t.get("eleito", ""), "pagina": CFG["pagina"]})
        meses_g = list(gg.ano * 100 + gg.mes)
        if hoje:  # a lista da Alesc diz quem está no cargo hoje; os meses com gastos dizem desde quando
            atual = no_cargo(nome, t)
            meses_g = sorted(set(meses_g) | ({ultimo_dado} if atual else set()))
            per = comum.periodos(meses_g, ultimo_dado, ultimo)
            if not atual:
                per = [(i, f or f"{max(meses_g) // 100}-{max(meses_g) % 100:02d}-28") for i, f in per]
        else:
            per = comum.periodos(meses_g, ultimo_dado, ultimo)
        for i, f in per:
            mandatos.append({"codigo": codigo, "inicio": i, "fim": f})
    desp = g.assign(codigo=g.deputado.map(cods), tipo=g.descricao.where(g.descricao != "", g.verba.str.capitalize()), cnpj_cpf="")
    cfg = dict(CFG, ultimo_mes=min(ultimo, ultimo_dado))
    return vc.montar(cfg, tipos, pd.DataFrame(ver), pd.DataFrame(mandatos), despesas=desp[["ano", "mes", "codigo", "tipo", "fornecedor", "cnpj_cpf", "valor"]])
