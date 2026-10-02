"""Parte comum dos robôs do Judiciário (ver o README, "Judiciário").

Quem entra: os ministros do STF, STJ, TST, STM e TSE, os conselheiros do CNJ e o Procurador-Geral da República. Cada
fonte é um módulo desta pasta com `coletar()`, que grava em dados/judiciario/<orgao>/ (vai para o Git):

- folha.csv: uma linha por pessoa, órgão e mês (COLUNAS), só com as partes brutas do pagamento, como a fonte separa:
  subsídio, vantagens pessoais, abono de permanência, indenizações (com o nome de cada item em `itens`, quando a
  fonte dá), vantagens eventuais, férias, 13º e outras; `total_bruto` é a soma dessas partes (antes do abate-teto);
  as diárias ficam numa coluna à parte, fora do total. Nunca descontos (imposto, previdência, abate-teto, descontos
  pessoais), nunca o líquido, nunca o CPF. A "remuneração do órgão de origem" (o salário pago por outro tribunal a
  quem está no TSE ou no CNJ) fica de fora, para nada ser contado duas vezes.
- fontes.csv: um registro por mês lido (FONTES), com quantas pessoas entraram, o endereço lido e quando.

O robô só lê o que falta, de jan/2025 (INICIO) ao último mês publicado: os meses que ainda não estão em fontes.csv e
os 2 últimos publicados e os que vieram vazios de novo (a folha pode ser corrigida ou publicada depois), esses só
se a última leitura tem mais de 3 dias.
Quem está no cargo vem de dados/judiciario/composicao.json (mantido à mão, conferido com a folha).
"""
import csv
import json
import re
from datetime import datetime, timedelta

from ..config import DADOS
from ..util import log, normalizar_nome

PASTA = DADOS / "judiciario"
COMPOSICAO = PASTA / "composicao.json"
INICIO = 202501
REFAZER = 2
DIAS_RELER = 3

PARTES = ["subsidio", "vantagens_pessoais", "abono_permanencia", "indenizacoes", "vantagens_eventuais", "ferias",
          "decimo_terceiro", "outras"]
COLUNAS = ["orgao", "ano_mes", "nome", "cargo", "lotacao", *PARTES, "total_bruto", "diarias", "itens", "fonte", "nota"]
FONTES = ["orgao", "ano_mes", "pessoas", "url", "lido_em"]
# nomes de colunas que nunca podem ir para os arquivos (conferência no fim de cada gravação)
PROIBIDO = re.compile(r"liquid|líquid|desconto|imposto|previd|cpf|abate|redutor|retenc|retenç", re.I)


# ---------------------------------------------------------------- meses
def mes_mais(aaaamm, n=1):
    a, m = divmod(int(aaaamm), 100)
    t = a * 12 + (m - 1) + n
    return (t // 12) * 100 + t % 12 + 1


def meses(inicio, fim):
    saida, m = [], int(inicio)
    while m <= int(fim):
        saida.append(m)
        m = mes_mais(m)
    return saida


def agora():
    return datetime.now().strftime("%Y-%m-%dT%H:%M")


# ---------------------------------------------------------------- arquivos
def pasta(orgao):
    return PASTA / orgao.lower()


def _ler(caminho):
    if not caminho.exists():
        return []
    with open(caminho, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def ler(orgao):
    return _ler(pasta(orgao) / "folha.csv")


def ler_fontes(orgao):
    return _ler(pasta(orgao) / "fontes.csv")


def _num(v):
    return "" if v is None or v == "" else f"{float(v):.2f}"


def _escrever(caminho, linhas, colunas):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=colunas, extrasaction="ignore")
        w.writeheader()
        w.writerows(linhas)
    tmp.replace(caminho)


def linha(orgao, ano_mes, nome, cargo, lotacao, partes, diarias=None, itens=None, fonte="", nota=""):
    """Uma linha de COLUNAS. partes: {parte: valor ou None (a fonte não separa)}; total_bruto = soma das partes."""
    desconhecidas = set(partes) - set(PARTES)
    if desconhecidas:
        raise ValueError(f"partes desconhecidas: {desconhecidas}")
    total = round(sum(float(v) for v in partes.values() if v not in (None, "")), 2)
    return {"orgao": orgao, "ano_mes": int(ano_mes), "nome": re.sub(r"\s+", " ", str(nome)).strip(), "cargo": cargo or "",
            "lotacao": re.sub(r"\s+", " ", str(lotacao or "")).strip(),
            **{p: _num(partes.get(p)) for p in PARTES}, "total_bruto": _num(total), "diarias": _num(diarias),
            "itens": "; ".join(f"{g}: {n} = {v:.2f}" for g, n, v in (itens or [])), "fonte": fonte, "nota": nota or ""}


def gravar(orgao, linhas, lidos):
    """Troca, no arquivo do órgão, os meses lidos agora pelas linhas novas. lidos: [{ano_mes, pessoas, url}]."""
    if not lidos:
        return 0
    meses_lidos = {int(x["ano_mes"]) for x in lidos}
    velhas = [l for l in ler(orgao) if int(l["ano_mes"]) not in meses_lidos]
    novas = [l for l in linhas if int(l["ano_mes"]) in meses_lidos]
    for l in novas:
        for k, v in l.items():
            if k in ("nome", "lotacao", "itens", "nota") and re.search(r"(?<!\d)\d{11}(?!\d)|\d{3}\.\d{3}\.\d{3}-\d{2}", str(v)):
                raise ValueError(f"{orgao}: um número de 11 dígitos apareceu em {k} ({l['nome']}); nada foi gravado")
    todas = sorted(velhas + novas, key=lambda l: (int(l["ano_mes"]), normalizar_nome(l["nome"])))
    _escrever(pasta(orgao) / "folha.csv", todas, COLUNAS)
    f = [x for x in ler_fontes(orgao) if int(x["ano_mes"]) not in meses_lidos]
    f += [{"orgao": orgao, "ano_mes": int(x["ano_mes"]), "pessoas": x["pessoas"], "url": x["url"], "lido_em": agora()} for x in lidos]
    _escrever(pasta(orgao) / "fontes.csv", sorted(f, key=lambda x: int(x["ano_mes"])), FONTES)
    return len(novas)


def a_fazer(orgao, disponiveis):
    """Meses a ler (AAAAMM), do mais antigo ao mais novo: os disponíveis desde INICIO que ainda não foram lidos e os
    REFAZER últimos disponíveis, se a última leitura deles tem mais de DIAS_RELER dias."""
    disp = sorted(m for m in set(int(x) for x in disponiveis) if m >= INICIO)
    f = ler_fontes(orgao)
    lidos = {int(x["ano_mes"]): x.get("lido_em") or "" for x in f}
    vazios = {int(x["ano_mes"]) for x in f if str(x.get("pessoas")) in ("0", "")}  # a fonte pode publicar depois
    limite = (datetime.now() - timedelta(days=DIAS_RELER)).strftime("%Y-%m-%dT%H:%M")
    ultimos = set(disp[-REFAZER:]) | vazios
    return [m for m in disp if m not in lidos or (m in ultimos and lidos[m] < limite)]


# ---------------------------------------------------------------- números
def numero(texto):
    """'46.366,19', 'R$ 46.366,19', '44,047.88' (a página do CNJ mistura os dois formatos), ',00', '-1.234,5' -> float."""
    if texto is None:
        return 0.0
    if isinstance(texto, (int, float)):
        return round(float(texto), 2)
    t = str(texto).replace("R$", "").replace("\xa0", "").replace(" ", "").strip()
    if t in ("", "-", "—"):
        return 0.0
    neg = t.startswith("-")
    t = t.lstrip("-+")
    if re.fullmatch(r"\d{1,3}(,\d{3})+\.\d{1,2}|\d+\.\d{1,2}", t):  # formato americano: 44,047.88 ou 4294.67
        v = float(t.replace(",", ""))
    else:
        v = float(t.replace(".", "").replace(",", ".") or 0)
    return round(-v if neg else v, 2)


def conferir_total(orgao, nome, am, partes, total_fonte, tolerancia=0.05):
    """Avisa (no log) quando a soma das partes não bate com o total que a própria fonte dá."""
    soma = round(sum(float(v) for v in partes.values() if v not in (None, "")), 2)
    if total_fonte is not None and abs(soma - float(total_fonte)) > tolerancia:
        log(f"  {orgao} {am} {nome}: soma das partes {soma:.2f} ≠ total da fonte {float(total_fonte):.2f}")
        return False
    return True


# ---------------------------------------------------------------- composição
def composicao():
    return json.loads(COMPOSICAO.read_text(encoding="utf-8")) if COMPOSICAO.exists() else {"orgaos": {}, "membros": []}


def chave_nome(nome):
    return re.sub(r"[^A-Z ]", "", normalizar_nome(nome))
