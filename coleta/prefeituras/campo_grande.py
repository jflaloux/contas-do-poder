"""Prefeitura de Campo Grande: prefeita, vice e secretários municipais, mês a mês.

Fonte: Portal da Transparência de Campo Grande, "Consultar Remuneração dos Servidores" (SIG Transparência), com o nome,
a lotação, o cargo e a remuneração bruta de cada servidor: https://sig-transparencia.campogrande.ms.gov.br/servidores/consulta
A página pesquisa por cargo e mês e oferece o resultado em JSON (botão "Download JSON"); o robô faz o mesmo, para os
cargos de prefeito, vice-prefeito e secretário municipal. O CPF vem mascarado e não é guardado; as páginas de detalhe
(que têm o CPF no endereço) não são usadas. Em 01/10/2026 a consulta só tinha meses até dez/2025.
"""
import re
import time

import pandas as pd

from ..config import CACHE, DADOS
from ..util import TempoEsgotado, _sessao, dormir, log, normalizar_nome, verificar_prazo
from . import comum

COD = 5002704
INICIO = 202506  # de jan a mai/2025 a consulta não traz o cargo de ninguém (campo vazio)
PAGINA = "https://sig-transparencia.campogrande.ms.gov.br/servidores/consulta"
PASTA = DADOS / "municipios" / "campo_grande"
LINHAS = PASTA / "prefeitura_remuneracao.csv"
C = CACHE / "prefeituras" / "campo_grande"
COLUNAS = ["aaaamm", "tp", "nome", "cargo", "secretaria", "bruta"]
CAMPOS = ["_token", "page", "download", "situacao", "matricula", "cpf", "nome", "nome_secretaria", "tipo_nome_cargo", "tipo_nome_funcao", "competencia", "ano"]
SECRETARIAS = {
    "SEC ESPECIAL DE PLANEJAMENTO E PARCERIAS ESTRATEG": "Secretaria Especial de Planejamento e Parcerias Estratégicas",
    "SEC MUN D MEIO AMB GEST URB E DESENV ECON TUR SUST": "Secretaria Municipal de Meio Ambiente, Gestão Urbana e Desenvolvimento Econômico, Turístico e Sustentável",
    "SEC MUN DE INFRA-ESTRUTURA E SERVICOS PUBLICOS": "Secretaria Municipal de Infraestrutura e Serviços Públicos",
    "SECRETARIA ESPECIAL DA CASA CIVIL": "Secretaria Especial da Casa Civil",
    "SECRETARIA ESPECIAL DE ARTICULACAO REGIONAL": "Secretaria Especial de Articulação Regional",
    "SECRETARIA ESPECIAL DE LICITACOES E CONTRATOS": "Secretaria Especial de Licitações e Contratos",
    "SECRETARIA MUN DE GOVERNO RELACOES INSTITUCIONAIS": "Secretaria Municipal de Governo e Relações Institucionais",
    "SECRETARIA MUNICIPAL DA FAZENDA": "Secretaria Municipal da Fazenda",
    "SECRETARIA MUNICIPAL DE ADMINISTRACAO E INOVACAO": "Secretaria Municipal de Administração e Inovação",
    "SECRETARIA MUNICIPAL DE EDUCACAO": "Secretaria Municipal de Educação",
    "SECRETARIA MUNICIPAL DE SAUDE": "Secretaria Municipal de Saúde",
    "SEC MUN DE INOVAC, DESENVOLV ECONOM E AGRONEGOCIO": "Secretaria Municipal de Inovação, Desenvolvimento Econômico e Agronegócio",
}
CFG = {
    "cod": COD, "n": "Campo Grande", "uf": "MS", "de": "de Campo Grande", "casa": "Prefeitura de Campo Grande", "inicio": INICIO,
    "fonte": PAGINA, "pagina": PAGINA,
    "salario_nota": ("Remuneração bruta (\"vencimentos brutos\") da folha da Prefeitura, antes dos descontos. A consulta dá só o total "
                     "do mês: o que passa do valor normal da própria pessoa (13º, férias, atrasados) aparece como \"outros pagamentos\"."),
    "notas": ["Entram a prefeita, a vice e todas as pessoas com o cargo de secretário municipal (os secretários adjuntos e executivos "
              "não entram). Secretário que é servidor de carreira e recebe pelo cargo de origem não aparece com o cargo de secretário.",
              "De janeiro a maio de 2025 a consulta da Prefeitura não traz o cargo de ninguém (o campo vem vazio), então não dá para "
              "achar os secretários: os dados começam em junho de 2025."],
    "credito_camara": "Câmara Municipal de Campo Grande",
}


def _tp(cargo):
    c = normalizar_nome(cargo)
    if c.startswith("(C) PREFEITO MUNICIPAL") or c.startswith("(C) PREFEITA MUNICIPAL"):
        return "pr"
    if c.startswith("(C) VICE-PREFEIT") or c.startswith("(C) VICE PREFEIT"):
        return "vp"
    if re.match(r"\(C\) SECRETARI[OA] MUNICIPAL", c):
        return "se"
    return None


def _json(am, cargo):
    verificar_prazo()
    s = _sessao()
    for tentativa in range(3):
        try:
            t = s.get(PAGINA, timeout=90).text
            d = {n: "" for n in CAMPOS}
            d.update({"_token": re.search(r'name="_token"[^>]*value="([^"]+)"', t).group(1), "tipo_nome_cargo": cargo,
                      "competencia": f"{am % 100:02d}", "ano": str(am // 100), "download": "json"})
            dormir(2)
            r = s.post(PAGINA, data=d, timeout=180)
            r.raise_for_status()
            dormir(2)
            return r.json() if "json" in (r.headers.get("Content-Disposition") or "") else []
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 2:
                raise
            dormir(20)


def coletar():
    PASTA.mkdir(parents=True, exist_ok=True)
    linhas = pd.read_csv(LINHAS) if LINHAS.exists() else pd.DataFrame(columns=COLUNAS)
    feitos = set(linhas.aaaamm.astype(int)) if len(linhas) else set()
    h = time.localtime()
    meses = [a * 100 + m for a in range(INICIO // 100, h.tm_year + 1) for m in range(1, 13) if INICIO <= a * 100 + m < h.tm_year * 100 + h.tm_mon]
    ultimo_feito = max(feitos, default=0)
    C.mkdir(parents=True, exist_ok=True)
    for am in meses:  # os que faltam, do mais antigo para o mais recente; o último já feito é baixado de novo
        if am in feitos and am < ultimo_feito:
            continue
        vazio = C / f"vazio_{am}"
        if am > ultimo_feito and vazio.exists() and time.time() - vazio.stat().st_mtime < 3 * 86400:
            continue  # já se viu há pouco que o mês ainda não tem folha
        novas = []
        for cargo in ("PREFEIT", "SECRETARIO MUNICIPAL", "SECRETARIA MUNICIPAL"):
            for x in _json(am, cargo):
                tp = _tp(x.get("tipo_nome_cargo") or "")
                if tp:
                    novas.append({"aaaamm": am, "tp": tp, "nome": (x.get("nomefun") or "").strip(), "cargo": x["tipo_nome_cargo"].strip(),
                                  "secretaria": " ".join((x.get("nome_secretaria") or "").split()), "bruta": comum.num(x.get("vencimentos_bruto"))})
        if not any(n["tp"] == "pr" for n in novas):
            vazio.write_text("", encoding="utf-8")
            continue  # mês ainda sem folha na consulta
        nv = pd.DataFrame(novas, columns=COLUNAS).drop_duplicates()
        linhas = pd.concat([linhas[linhas.aaaamm.astype(int) != am], nv], ignore_index=True)
        linhas.sort_values(["aaaamm", "tp", "nome"]).to_csv(LINHAS, index=False)
        log(f"  Prefeitura de Campo Grande: {am % 100:02d}/{am // 100} ({len(nv)} pessoas)")


def _pasta(tp, secretaria):
    if tp in ("pr", "vp"):
        return f"Prefeitura {CFG['de']}"
    return SECRETARIAS.get(" ".join(secretaria.split()).upper(), comum.bonito(secretaria) or "Secretaria municipal")


def montar():
    if not LINHAS.exists():
        return None
    linhas = pd.read_csv(LINHAS).fillna("")
    saida = []
    for nome, g in linhas.groupby("nome"):
        normal = float(g.bruta.median())
        for (am, tp), gm in g.groupby(["aaaamm", "tp"]):
            b = float(gm.bruta.sum())
            extra = max(0.0, b - normal) if b > normal * 1.1 else 0.0
            saida.append({"aaaamm": int(am), "tp": tp, "nome": nome, "pasta": _pasta(tp, gm.secretaria.iloc[0]), "salario": b - extra,
                          "decimo": 0.0, "outros": extra, "bruta": b, "cedido": 0})
    return comum.montar(CFG, pd.DataFrame(saida, columns=comum.COLUNAS))
