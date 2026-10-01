"""Prefeitura de Salvador: prefeito, vice e secretários municipais, mês a mês.

Fonte: Portal da Transparência de Salvador, "Remunerações" (Pessoal), com o nome, o órgão, o cargo e o vínculo de cada
servidor: https://transparencia.salvador.ba.gov.br/#/RemuneracaoDadosFuncionais
A página consulta uma API pública, sem login: a lista do mês filtrada pelo cargo (api/remuneracao/gridDetalhada) e,
para cada pessoa, o detalhe do mês (api/remuneracao/detalhamento), com a remuneração básica, o 13º, as férias, as
verbas indenizatórias e o abate-teto. O robô faz as mesmas consultas. Não guardamos o imposto, a previdência nem o
líquido (são descontos pessoais), nem a matrícula. Guardamos só o prefeito, o vice e os secretários municipais em
dados/municipios/salvador/.
"""
import json
import time
from datetime import date

import pandas as pd

from ..config import CACHE, DADOS
from ..util import TempoEsgotado, _sessao, dormir, log, normalizar_nome, verificar_prazo
from . import comum

COD = 2927408
INICIO = 202501  # mandato 2025–2028
API = "https://apitmptransparencia.salvador.ba.gov.br/api/remuneracao"
PAGINA = "https://transparencia.salvador.ba.gov.br/#/RemuneracaoDadosFuncionais"
CABECALHOS = {"Origin": "https://transparencia.salvador.ba.gov.br", "Referer": "https://transparencia.salvador.ba.gov.br/"}
PASTA = DADOS / "municipios" / "salvador"
LINHAS = PASTA / "prefeitura_remuneracao.csv"
C = CACHE / "prefeituras" / "salvador"
PAUSA = 1.5
COLUNAS = ["aaaamm", "tp", "nome", "cargo", "orgao", "vinculo", "basica", "decimo", "ferias", "indenizatorias", "abate_teto"]
# siglas da folha -> nome das secretarias (conferido nos sites de cada secretaria, em salvador.ba.gov.br, em 01/10/2026)
SECRETARIAS = {
    "SACPB": "Secretaria Comunitária e Prefeituras-Bairro",
    "SECIS": "Secretaria Municipal de Sustentabilidade, Inovação e Resiliência",
    "SECOM": "Secretaria Municipal de Comunicação",
    "SECULT": "Secretaria Municipal de Cultura e Turismo",
    "SEDUR": "Secretaria Municipal de Desenvolvimento Urbano",
    "SEFAZ": "Secretaria Municipal da Fazenda",
    "SEGOV": "Secretaria Municipal de Governo",
    "SEINFRA": "Secretaria Municipal de Infraestrutura e Obras Públicas",
    "SEMAN": "Secretaria Municipal de Manutenção da Cidade",
    "SEMDEC": "Secretaria Municipal de Desenvolvimento Econômico, Emprego e Renda",
    "SEMGE": "Secretaria Municipal de Gestão",
    "SEMIT": "Secretaria Municipal de Inovação e Tecnologia",
    "SEMOB": "Secretaria Municipal de Mobilidade",
    "SEMOP": "Secretaria Municipal de Ordem Pública",
    "SEMPRE": "Secretaria Municipal de Promoção Social, Combate à Pobreza, Esportes e Lazer",
    "SEMUR": "Secretaria Municipal da Reparação",
    "SMED": "Secretaria Municipal de Educação",
    "SMS": "Secretaria Municipal da Saúde",
    "SPMJ": "Secretaria Municipal de Políticas para Mulheres, Infância e Juventude",
}
CFG = {
    "cod": COD, "n": "Salvador", "uf": "BA", "de": "de Salvador", "casa": "Prefeitura de Salvador", "inicio": INICIO,
    "fonte": PAGINA, "pagina": PAGINA,
    "salario_nota": ("Remuneração bruta da folha da Prefeitura: a remuneração básica, o 13º e as férias, já descontado o abate-teto, "
                     "antes do imposto e da previdência. Verbas indenizatórias não entram."),
    "notas": ["O Portal da Transparência de Salvador publica a remuneração de cada servidor, mês a mês, com o nome, o órgão, o "
              "cargo e o vínculo. Entram o prefeito, a vice e todas as pessoas com o cargo de secretário municipal. O chefe da "
              "Casa Civil, a controladora-geral e o procurador-geral, que também estão na folha, não entram.",
              "Secretário com o vínculo \"regime especial outra esfera\" é servidor de outro órgão: a Prefeitura paga só uma parte, "
              "e o salário vem do órgão de origem. Por isso fica fora das comparações."],
    "credito_camara": "Câmara Municipal de Salvador",
}


def _tp(cargo):
    c = normalizar_nome(cargo)
    if c == "PREFEITO" or c == "PREFEITA":
        return "pr"
    if c in ("VICE PREFEITO", "VICE-PREFEITO", "VICE PREFEITA", "VICE-PREFEITA"):
        return "vp"
    if c.endswith("SECRETARIO MUNICIPAL") or c.endswith("SECRETARIA MUNICIPAL"):
        return "se"
    return None


def _periodo(am):
    """A página manda o mês como o intervalo do primeiro ao último dia, à meia-noite de Salvador (03:00 UTC)."""
    a, m = divmod(am, 100)
    fim = (date(a + (m == 12), m % 12 + 1, 1) - date.resolution)
    return f"{a}-{m:02d}-01T03:00:00.000Z", f"{fim.isoformat()}T03:00:00.000Z"


def _post(caminho, corpo, params=None):
    verificar_prazo()
    for tentativa in range(4):
        try:
            r = _sessao().post(f"{API}/{caminho}", params=params, json=corpo, headers=CABECALHOS, timeout=90)
            r.raise_for_status()
            dormir(PAUSA)
            return r.json()
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 3:
                raise
            dormir(10 * (tentativa + 1))


def _lista(am, cargo):
    ini, fim = _periodo(am)
    saida, pagina = [], 1
    while True:
        d = _post("gridDetalhada", {"filtros": [{"atributo": "CARGO", "valor": cargo, "label": cargo}], "dataInicio": ini, "dataFim": fim},
                  params={"pagina": pagina, "tamanho": 100})
        saida += d.get("dados") or []
        if pagina >= int((d.get("paginacao") or {}).get("paginas") or 1):
            return saida
        pagina += 1


def _mes(am):
    """Linhas do mês (prefeito, vice e secretários), com o detalhe de cada um. None = mês ainda sem folha."""
    pessoas = {}
    for cargo in ("PREFEITO", "SECRETARIO MUNICIPAL"):
        for x in _lista(am, cargo):
            tp = _tp(x.get("cargo"))
            if tp:
                pessoas[x["matricula"]] = (tp, x)
    if not pessoas:
        return None
    ini, _ = _periodo(am)
    linhas = []
    for matricula, (tp, x) in sorted(pessoas.items(), key=lambda i: (i[1][0], i[1][1]["nome"])):
        r = (_post("detalhamento", {"dataInicio": ini, "filtros": [{"atributo": "MATRICULA", "valor": matricula}]}) or {}).get("infoRemuneracao") or {}
        linhas.append({"aaaamm": am, "tp": tp, "nome": x["nome"].strip(), "cargo": x["cargo"].strip(), "orgao": (x.get("orgao") or "").strip(),
                       "vinculo": (x.get("vinculo") or "").strip(), "basica": comum.num(r.get("rendaBrutaBasica")),
                       "decimo": comum.num(r.get("decTercSalario")), "ferias": comum.num(r.get("ferias")),
                       "indenizatorias": comum.num(r.get("verbasIndeniz")), "abate_teto": comum.num(r.get("excedenteTeto"))})
    return linhas


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
    for am in reversed(meses):  # do mais recente para o mais antigo
        cache = C / f"{am}.json"
        fresco = cache.exists() and time.time() - cache.stat().st_mtime < 3 * 86400
        if am in feitos and (am not in recentes or fresco):
            continue
        novas = _mes(am)
        if novas is None:
            log(f"  Prefeitura de Salvador: {am % 100:02d}/{am // 100} ainda sem folha")
            continue
        (C / f"{am}.json").write_text(json.dumps(novas, ensure_ascii=False), encoding="utf-8")
        linhas = pd.concat([linhas[linhas.aaaamm.astype(int) != am], pd.DataFrame(novas, columns=COLUNAS)], ignore_index=True)
        linhas.sort_values(["aaaamm", "tp", "nome"]).to_csv(LINHAS, index=False)
        log(f"  Prefeitura de Salvador: {am % 100:02d}/{am // 100} ({len(novas)} pessoas)")


def _pasta(tp, orgao):
    if tp in ("pr", "vp"):
        return f"Prefeitura {CFG['de']}"
    return SECRETARIAS.get(orgao.strip().upper(), "Secretaria municipal")


def montar():
    if not LINHAS.exists():
        return None
    linhas = pd.read_csv(LINHAS).fillna("")
    saida = []
    for (am, nome, tp), g in linhas.groupby(["aaaamm", "nome", "tp"]):
        salario = max(0.0, float(g.basica.sum()) - float(g.abate_teto.sum()))
        decimo = float(g.decimo.sum())
        outros = float(g.ferias.sum())
        cedido = 1 if tp == "se" and g.vinculo.map(normalizar_nome).str.contains("OUTRA ESFERA").any() else 0
        saida.append({"aaaamm": int(am), "tp": tp, "nome": nome, "pasta": _pasta(tp, g.orgao.iloc[0]), "salario": salario, "decimo": decimo,
                      "outros": outros, "bruta": salario + decimo + outros, "cedido": cedido})
    r = comum.montar(CFG, pd.DataFrame(saida, columns=comum.COLUNAS))
    for p in (r[1] if r else []):  # "Secretário Comunitária e Prefeituras-Bairro" não soa bem: o nome da pasta vai entre parênteses
        if " Comunitária e Prefeituras-Bairro" in p.get("g", ""):
            p["g"] = f"{p['g'].split(' ')[0]} municipal (Comunitária e Prefeituras-Bairro)"
    return r
