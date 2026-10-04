"""Prefeitura do Natal: prefeito, vice e secretários municipais, mês a mês.

Fonte: Natal Transparente, "Servidores - Folha de Pagamento", com o nome, o cargo, a lotação e as rubricas de cada
servidor: https://www2.natal.rn.gov.br/transparencia/servidores.php
A página lista os cargos de cada mês (transparenciaapi/folha_pagamentos/getCargos), pesquisa a folha por cargo
(servidores-folha.php) e mostra o contracheque de cada pessoa (transparenciaapi/folha_pagamentos/view/<id>), com as
rubricas (subsídio, 13º, férias, jetons). O robô faz as mesmas consultas, só para os cargos de prefeito, vice e
secretário municipal. Não guardamos o CPF (vem mascarado), os descontos nem a matrícula. Guardamos as linhas em
dados/municipios/natal/.
"""
import html as H
import json
import re
import time
from datetime import date

import pandas as pd

from ..config import CACHE, DADOS
from ..util import TempoEsgotado, _sessao, dormir, gravar_csv, log, normalizar_nome, verificar_prazo
from . import comum

COD = 2408102
INICIO = 202501  # mandato 2025–2028
INST = "9"  # "PREFEITURA MUNICIPAL DO NATAL" na lista de instituições da página
BASE = "https://www2.natal.rn.gov.br"
PAGINA = f"{BASE}/transparencia/servidores.php"
API = f"{BASE}/transparenciaapi/folha_pagamentos"
CABECALHOS = {"Referer": PAGINA, "X-Requested-With": "XMLHttpRequest"}
PASTA = DADOS / "municipios" / "natal"
LINHAS = PASTA / "prefeitura_remuneracao.csv"
C = CACHE / "prefeituras" / "natal"
PAUSA = 0.5
COLUNAS = ["aaaamm", "folha", "tp", "nome", "cargo", "lotacao", "basica", "decimo", "ferias", "jetons", "outros"]
# os cargos de secretário vêm abreviados de vários jeitos ("SEC MUN SAUDE", "SECR MUNICIPAL DE EDUCACAO", "SECRET MUNIC OBRAS PUB INFRA")
SECRETARIO = re.compile(r"^(SEC|SECR|SECRET|SECRETARIO|SECRETARIA)\.?\s*(MUN|MUNIC|MUNICIPAL)\b\.?")
# siglas da lotação -> nome da secretaria (conferido nas páginas de cada secretaria em natal.rn.gov.br, em 01/10/2026)
SECRETARIAS = {
    "SECOM": "Secretaria Municipal de Comunicação Social", "SECULT": "Secretaria Municipal de Cultura e Arte",
    "SEHARPE": "Secretaria Municipal de Habitação, Regularização Fundiária e Projetos Estruturantes",
    "SEINFRA": "Secretaria Municipal de Infraestrutura", "SEMAD": "Secretaria Municipal de Administração",
    "SEMDES": "Secretaria Municipal de Segurança Pública e Defesa Social", "SEMIDH": "Secretaria Municipal de Direitos Humanos e Diversidade",
    "SEMPLA": "Secretaria Municipal de Planejamento", "SEMSUR": "Secretaria Municipal de Serviços Urbanos",
    "SEMTAS": "Secretaria Municipal de Trabalho e Assistência Social", "SEMUL": "Secretaria Municipal de Políticas para as Mulheres",
    "SEMURB": "Secretaria Municipal de Meio Ambiente e Urbanismo",
    "SEPAE": "Secretaria Municipal de Concessões, Parcerias, Empreendedorismo e Inovações", "SETUR": "Secretaria Municipal de Turismo",
    "SME": "Secretaria Municipal de Educação", "SMG": "Secretaria Municipal de Governo", "SMS": "Secretaria Municipal de Saúde",
    "SEL": "Secretaria Municipal de Esporte e Lazer", "SEMUT": "Secretaria Municipal de Finanças", "SEFIN": "Secretaria Municipal de Finanças",
    "SEMOB": "Secretaria Municipal de Mobilidade Urbana", "STTU": "Secretaria Municipal de Mobilidade Urbana",
}
CFG = {
    "cod": COD, "n": "Natal", "uf": "RN", "de": "do Natal", "casa": "Prefeitura do Natal", "inicio": INICIO, "fonte": PAGINA, "pagina": PAGINA,
    "salario_nota": ("Remuneração bruta da folha da Prefeitura: o subsídio (ou vencimento), o 13º, as férias e os jetons, antes do imposto "
                     "e da previdência."),
    "notas": ["O Natal Transparente publica o contracheque de cada servidor, mês a mês, com o nome, o cargo, a lotação e cada rubrica. "
              "Entram o prefeito, a vice e todas as pessoas com o cargo de secretário municipal (os secretários adjuntos e executivos "
              "não entram).",
              "O prefeito, a vice e os secretários recebem, além do subsídio, um \"jeton indenizatório\" todo mês (Lei 7.274/2021, "
              "R$ 15,6 mil para o prefeito e R$ 9,4 mil para os demais em 2026): aparece em \"outros pagamentos\".",
              "Secretário que está na lista do mês sem contracheque (remuneração zero) recebe por outro órgão. Por isso fica fora "
              "das comparações."],
    "credito_camara": "Câmara Municipal do Natal",
}


def _tp(cargo):
    c = normalizar_nome(cargo)
    if c.startswith("PREFEITO MUNICIPAL") or c in ("PREFEITO", "PREFEITA"):
        return "pr"
    if c in ("VICE PREFEITO", "VICE-PREFEITO", "VICE PREFEITA", "VICE-PREFEITA"):
        return "vp"
    if SECRETARIO.match(c) and not re.search(r"\b(ADJ|ADJUNT[OA]?|EXEC|EXECUTIV[OA]|PART|PARTICULAR)\b", c):
        return "se"
    return None


def _pedir(metodo, url, **kw):
    verificar_prazo()
    for tentativa in range(4):
        try:
            r = _sessao().request(metodo, url, timeout=120, **kw)
            r.raise_for_status()
            dormir(PAUSA)
            return r
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 3:
                raise
            dormir(10 * (tentativa + 1))


def _meses_do_ano(ano):
    try:
        return sorted(ano * 100 + int(m) for m in _pedir("GET", f"{API}/getMeses/{ano}/{INST}", headers=CABECALHOS).json())
    except ValueError:
        return []


def _pesquisa(am, cargo):
    d = {"instituicao": INST, "ano": str(am // 100), "mes": str(am % 100), "cargo": cargo, "lotacao": "", "vinculo": "", "matricula": "",
         "demitidos": "false", "nome": "", "pesquisaFolhas": "pesquisaFolhas"}  # "demitidos" true traz todos que já tiveram o cargo
    t = _pedir("POST", f"{BASE}/transparencia/servidores-folha.php", data=d).text
    m = re.search(r"const resposta = (\[.*?\]);\s*\n", t, flags=re.S)
    if not m:
        raise RuntimeError(f"a pesquisa de {cargo} em {am} não trouxe a lista")
    return (json.loads(m.group(1))[0] or {}).get("rows") or []


def _contracheque(id_):
    """Rubricas do contracheque do mês. A página pode trazer mais de uma folha (salário, 13º, férias), cada uma num bloco."""
    t = _pedir("GET", f"{API}/view/{id_}", headers={"Referer": f"{BASE}/transparencia/servidores-folha.php"}).text
    soma = {"basica": 0.0, "decimo": 0.0, "ferias": 0.0, "jetons": 0.0, "outros": 0.0}
    folhas = []
    blocos = re.split(r"<div class=['\"]tipo-folha\s+", t)[1:]  # sem bloco: a pessoa está na lista do mês, mas sem contracheque
    for bloco in blocos:
        tipo = normalizar_nome(re.match(r"([^'\"]*)", bloco).group(1))
        folhas.append(tipo.lower())
        for linha in re.findall(r"<tr[^>]*>(.*?)</tr>", bloco, flags=re.S):
            c = [H.unescape(re.sub(r"<[^>]+>", "", x)).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", linha, flags=re.S)]
            if len(c) < 4 or normalizar_nome(c[-1]) != "PROVENTO":
                continue
            r, v = normalizar_nome(c[0]), comum.num(c[-2])
            if re.search(r"13|DECIMO|NATALIN", tipo) or re.search(r"\b13|NATALIN", r):
                soma["decimo"] += v
            elif "FERIAS" in tipo or "FERIAS" in r:
                soma["ferias"] += v
            elif "JETON" in r:
                soma["jetons"] += v
            elif re.search(r"SUBSIDIO|VENCIMENTO|REPRESENTACAO|CARGO\s*(EM\s*)?COMISSAO|SALARIO", r):
                soma["basica"] += v
            else:
                soma["outros"] += v
    return ",".join(folhas), soma


def _mes(am):
    cargos = _pedir("GET", f"{API}/getCargos/{am // 100}/{am % 100}/{INST}", headers=CABECALHOS).json()
    alvo = sorted(k for k in cargos if _tp(k))
    linhas = []
    for cargo in alvo:
        for x in _pesquisa(am, cargo):
            _, nome, cargo_folha, lotacao = (x.get("cell") or ["", "", "", ""])[:4]
            folha, soma = _contracheque(x["id"])
            linhas.append({"aaaamm": am, "folha": folha, "tp": _tp(cargo_folha or cargo), "nome": nome.strip(), "cargo": (cargo_folha or cargo).strip(),
                           "lotacao": lotacao.strip(), **soma})
    return linhas


def coletar():
    PASTA.mkdir(parents=True, exist_ok=True)
    C.mkdir(parents=True, exist_ok=True)
    linhas = pd.read_csv(LINHAS) if LINHAS.exists() else pd.DataFrame(columns=COLUNAS)
    feitos = set(linhas.aaaamm.astype(int)) if len(linhas) else set()
    meses = [am for ano in range(date.today().year, INICIO // 100 - 1, -1) for am in reversed(_meses_do_ano(ano)) if am >= INICIO]
    recentes = set(meses[:2])
    for am in meses:  # do mais recente para o mais antigo
        cache = C / f"{am}.json"
        fresco = cache.exists() and time.time() - cache.stat().st_mtime < 3 * 86400
        if am in feitos and (am not in recentes or fresco):
            continue
        novas = _mes(am)
        if not any(x["tp"] == "pr" for x in novas):
            log(f"  Prefeitura do Natal: {am % 100:02d}/{am // 100} sem o prefeito na folha; fica de fora")
            continue
        cache.write_text(json.dumps(novas, ensure_ascii=False), encoding="utf-8")
        linhas = pd.concat([linhas[linhas.aaaamm.astype(int) != am], pd.DataFrame(novas, columns=COLUNAS)], ignore_index=True)
        gravar_csv(linhas.sort_values(["aaaamm", "tp", "nome", "folha"]), LINHAS)
        log(f"  Prefeitura do Natal: {am % 100:02d}/{am // 100} ({len(novas)} contracheques)")


def _pasta(tp, lotacao):
    if tp in ("pr", "vp"):
        return f"Prefeitura {CFG['de']}"
    if "IGUALDADE RACIAL" in normalizar_nome(lotacao):
        return "Secretaria Municipal de Igualdade Racial e Direitos Humanos"
    sigla = re.split(r"[\s\-/]+", lotacao.strip().upper())[0] if lotacao else ""
    return SECRETARIAS.get(sigla, "Secretaria municipal")


def montar():
    if not LINHAS.exists():
        return None
    linhas = pd.read_csv(LINHAS).fillna("")
    for c in ("basica", "decimo", "ferias", "jetons", "outros"):
        linhas[c] = pd.to_numeric(linhas[c], errors="coerce").fillna(0)
    saida = []
    for (am, nome, tp), g in linhas.groupby(["aaaamm", "nome", "tp"]):
        salario, decimo = float(g.basica.sum()), float(g.decimo.sum())
        outros = float(g.ferias.sum() + g.jetons.sum() + g.outros.sum())
        saida.append({"aaaamm": int(am), "tp": tp, "nome": nome, "pasta": _pasta(tp, g.lotacao.iloc[0]), "salario": salario, "decimo": decimo,
                      "outros": outros, "bruta": salario + decimo + outros, "cedido": 1 if tp == "se" and salario + decimo + outros == 0 else 0})
    return comum.montar(CFG, pd.DataFrame(saida, columns=comum.COLUNAS))
