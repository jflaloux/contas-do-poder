"""Prefeitura de Curitiba: prefeito, vice e secretários municipais, mês a mês.

Fonte: Portal da Transparência de Curitiba, "Remuneração dos Servidores" (Gestão de Pessoal), com o nome, o cargo,
a lotação e a remuneração bruta de cada servidor ativo:
https://www.transparencia.curitiba.pr.gov.br/meta4/servidores.aspx?quadro=
A página oferece a lista inteira do mês em CSV (o botão "Exportar para CSV"); o robô faz o mesmo que o botão, mês a
mês. A lista dá só o total bruto do mês. Guardamos só o prefeito, o vice e os secretários em dados/municipios/curitiba/
(não guardamos o líquido).
"""
import csv
import io
import re
import time

import pandas as pd
from bs4 import BeautifulSoup

from ..config import CACHE, DADOS
from ..util import TempoEsgotado, _sessao, dormir, log, normalizar_nome, verificar_prazo
from . import comum

COD = 4106902
INICIO = 202501  # mandato 2025–2028
PAGINA = "https://www.transparencia.curitiba.pr.gov.br/meta4/servidores.aspx?quadro="
PASTA = DADOS / "municipios" / "curitiba"
LINHAS = PASTA / "prefeitura_remuneracao.csv"
C = CACHE / "prefeituras" / "curitiba"
PAUSA = 5
CP = "ctl00$cphMasterPrincipal$"
COLUNAS = ["aaaamm", "tp", "nome", "cargo", "lotacao", "bruta"]
CFG = {
    "cod": COD, "n": "Curitiba", "uf": "PR", "de": "de Curitiba", "casa": "Prefeitura de Curitiba", "inicio": INICIO,
    "fonte": PAGINA, "pagina": PAGINA,
    "salario_nota": ("Remuneração bruta da folha da Prefeitura, antes dos descontos. A lista de Curitiba dá só o total do mês: o que passa "
                     "do valor normal da própria pessoa (13º, férias, atrasados) aparece como \"outros pagamentos\"."),
    "notas": ["O Portal da Transparência de Curitiba publica a remuneração bruta de cada servidor ativo, mês a mês, com o nome, o "
              "cargo e a lotação. Entram o prefeito, o vice e quem aparece na lista com o cargo de secretário. Secretário que é "
              "servidor de carreira e recebe pelo cargo de origem aparece na lista com esse cargo, sem dizer que é secretário, e "
              "por isso não entra. Os presidentes de fundações e institutos (como o IPPUC e a FAS) também não entram.",
              "Secretário com remuneração zero na lista é servidor de outro órgão, que paga o salário. Por isso fica fora das "
              "comparações."],
    "credito_camara": "Câmara Municipal de Curitiba",
}


def _tp(cargo):
    c = normalizar_nome(cargo)
    if c in ("PREFEITO", "PREFEITA"):
        return "pr"
    if c in ("VICE-PREFEITO", "VICE PREFEITO", "VICE-PREFEITA", "VICE PREFEITA"):
        return "vp"
    if c in ("SECRETARIO", "SECRETARIA", "SECRETARIO MUNICIPAL", "SECRETARIA MUNICIPAL"):
        return "se"
    return None


def _campos(html):
    b = BeautifulSoup(html, "html.parser")
    d = {i["name"]: i.get("value", "") for i in b.select("input[type=hidden]") if i.get("name")}
    meses = [o.get("value") for o in b.select(f"select[name='{CP}ddlMes'] option")]
    anos = [o.get("value") for o in b.select(f"select[name='{CP}ddlAno'] option")]
    return d, anos, meses


def _post(dados):
    verificar_prazo()
    for tentativa in range(4):
        try:
            r = _sessao().post(PAGINA, data=dados, timeout=180)
            r.raise_for_status()
            dormir(PAUSA)
            return r
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 3:
                raise
            dormir(15 * (tentativa + 1))


def _form(ano):
    """Campos do formulário com o ano escolhido (trocar o ano recarrega a lista de meses)."""
    verificar_prazo()
    r = _sessao().get(PAGINA, timeout=90)
    r.raise_for_status()
    d, anos, meses = _campos(r.text)
    if str(ano) not in anos:
        return None, []
    if not meses or str(ano) != anos[0]:
        d.update({"__EVENTTARGET": f"{CP}ddlAno", "__EVENTARGUMENT": "", f"{CP}ddlAno": str(ano), f"{CP}rblAtivoInativo": "0"})
        d, _, meses = _campos(_post(d).text)
    return d, meses


def _csv_mes(d, am):
    d = dict(d)
    d.update({"__EVENTTARGET": f"{CP}lnbExportar", "__EVENTARGUMENT": "", f"{CP}ddlAno": str(am // 100), f"{CP}ddlMes": str(am % 100),
              f"{CP}rblAtivoInativo": "0", f"{CP}txtNome": "", f"{CP}ddlCargo": "", f"{CP}hdnExportarTipo": "2", "ctl00$txtPesquisaTopo": ""})
    r = _post(d)
    if "csv" not in (r.headers.get("Content-Disposition") or "").lower():
        raise RuntimeError(f"a exportação de {am} não devolveu o CSV")
    return r.content.decode("latin1")


def _linhas(texto, am):
    saida = []
    for row in csv.reader(io.StringIO(texto), delimiter=";"):
        if len(row) < 4:
            continue
        tp = _tp(row[1])
        if tp:
            saida.append({"aaaamm": am, "tp": tp, "nome": row[0].strip(), "cargo": row[1].strip(), "lotacao": row[2].strip(), "bruta": comum.num(row[3])})
    return saida


def coletar():
    PASTA.mkdir(parents=True, exist_ok=True)
    C.mkdir(parents=True, exist_ok=True)
    linhas = pd.read_csv(LINHAS) if LINHAS.exists() else pd.DataFrame(columns=COLUNAS)
    feitos = set(linhas.aaaamm.astype(int)) if len(linhas) else set()
    hoje = time.localtime()
    for ano in range(hoje.tm_year, INICIO // 100 - 1, -1):  # do mais recente para o mais antigo
        d, meses = _form(ano)
        if d is None:
            continue
        disponiveis = sorted((ano * 100 + int(m) for m in meses if m and m.isdigit()), reverse=True)
        recentes = set(sorted(feitos | set(disponiveis))[-2:])
        for am in disponiveis:
            if am < INICIO:
                continue
            cache = C / f"{am}.csv"
            fresco = cache.exists() and time.time() - cache.stat().st_mtime < 3 * 86400
            if am in feitos and (am not in recentes or fresco):
                continue
            texto = _csv_mes(d, am)
            novas = _linhas(texto, am)
            if not any(x["tp"] == "pr" for x in novas):
                log(f"  Prefeitura de Curitiba: {am % 100:02d}/{am // 100} sem o prefeito na lista; fica de fora")
                continue
            cache.write_text("\n".join(f"{x['nome']};{x['cargo']};{x['bruta']}" for x in novas), encoding="utf-8")
            linhas = pd.concat([linhas[linhas.aaaamm.astype(int) != am], pd.DataFrame(novas, columns=COLUNAS)], ignore_index=True)
            linhas.sort_values(["aaaamm", "tp", "nome"]).to_csv(LINHAS, index=False)
            feitos.add(am)
            log(f"  Prefeitura de Curitiba: {am % 100:02d}/{am // 100} ({len(novas)} pessoas)")


_ACENTOS = {"ECONOMICO": "Econômico", "INOVACAO": "Inovação", "GESTAO": "Gestão", "SEGURANCA": "Segurança", "EXTRAORDINARIA": "Extraordinária",
            "REGIAO": "Região", "OBRAS": "Obras", "PUBLICAS": "Públicas", "SAUDE": "Saúde", "COMUNICACAO": "Comunicação"}


def _pasta(tp, lotacao):
    if tp in ("pr", "vp"):
        return f"Prefeitura {CFG['de']}"
    t = comum.bonito(lotacao)
    t = re.sub(r"^Secretaria Municipal Meio Ambiente$", "Secretaria Municipal do Meio Ambiente", t)
    for sem, com in _ACENTOS.items():
        t = re.sub(rf"\b{sem.capitalize()}\b", com, t)
    t = re.sub(r"\b(Para|Ó)\b", lambda m: m.group(1).lower().replace("ó", "o"), t)  # "Para Ó Desenvolvimento" -> "para o desenvolvimento"
    return t or "Secretaria municipal"


def montar():
    if not LINHAS.exists():
        return None
    linhas = pd.read_csv(LINHAS).fillna("")
    saida = []
    for nome, g in linhas.groupby("nome"):
        pagos = g[g.bruta > 0]
        normal = float(pagos.bruta.median()) if len(pagos) else 0.0
        for (am, tp), gm in g.groupby(["aaaamm", "tp"]):
            b = float(gm.bruta.sum())
            extra = max(0.0, b - normal) if normal and b > normal * 1.1 else 0.0
            cedido = 1 if tp == "se" and b == 0 else 0
            saida.append({"aaaamm": int(am), "tp": tp, "nome": nome, "pasta": _pasta(tp, gm.lotacao.iloc[0]), "salario": b - extra,
                          "decimo": 0.0, "outros": extra, "bruta": b, "cedido": cedido})
    r = comum.montar(CFG, pd.DataFrame(saida, columns=comum.COLUNAS))
    for p in (r[1] if r else []):
        if p.get("g", "").startswith("Secretário Municipal Extraordinária"):
            p["g"] = p["g"].replace("Secretário Municipal Extraordinária", "Secretário Municipal Extraordinário", 1)
    return r
