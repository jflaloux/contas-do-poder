"""Câmara Municipal de Aracaju: vereador por vereador.

Fontes (Portal da Câmara, sem cadastro):
- Folha de pagamento, uma planilha por mês ("Relação de funcionários por cargo": matrícula, nome, admissão, cargo,
  lotação, valor bruto): https://www.aracaju.se.leg.br/transparencia/gestao-de-pessoas/Folha%20de%20Pagamento/<ano>.
  Dela saem quem estava no cargo em cada mês (cargo VEREADOR) e o valor bruto do mês.
- VAEP (Verba do Exercício Parlamentar, Lei 4.678/2015): um PDF por mês com uma página por vereador, mas é imagem e mais
  da metade das páginas não tem texto; fica de fora (precisaria de OCR). A leitura das páginas com texto está em _vaep().
- Nome de urna, partido e gênero: TSE (eleição de 2024).
"""
import re
import subprocess
import tempfile
import time

import pandas as pd

from ..config import CACHE, DADOS
from ..util import TempoEsgotado, _sessao, dormir, log, normalizar_nome, verificar_prazo
from . import comum

COD = 2800308
INICIO = 202501
SITE = "https://www.aracaju.se.leg.br/transparencia/"
FOLHA = SITE + "gestao-de-pessoas/Folha%20de%20Pagamento/{ano}"
VAEP = SITE + "fundos-verbas-e-outros/lei-no-4-678-2016-vaep/verba-do-exercicio-parlamentar-vaep-{ano}"
PASTA = DADOS / "municipios" / "aracaju"
C = CACHE / "cmaracaju"
CFG = {
    "cod": COD, "n": "Aracaju", "uf": "SE", "casa": "Câmara Municipal de Aracaju", "vagas": 24, "inicio": INICIO,
    "subsidio": [[202501, 22865.16]],
    "salario_nota": "Valor bruto da folha de pagamento da Câmara (a planilha não separa subsídio, 13º e outros pagamentos).",
    "credito_foto": "Câmara Municipal de Aracaju", "pagina": "https://www.aracaju.se.leg.br/institucional/vereadores",
    "notas": ["Quem estava no cargo em cada mês: os vereadores na folha de pagamento do mês.",
              "A Verba do Exercício Parlamentar (VAEP, até R$ 20.000 por mês, Lei 4.678/2015) sai num PDF de imagem por mês, sem texto "
              "em boa parte das páginas: ainda não entra aqui."],
    "fontes": {"folha": FOLHA.format(ano=2026)},
}


def _get(url, binario=False):
    verificar_prazo()
    for tentativa in range(3):
        try:
            r = _sessao().get(url, timeout=180)
            r.raise_for_status()
            dormir(2)
            return r.content if binario else r.text
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 2:
                raise
            dormir(20)


def _arquivos(pasta, padrao):
    """Pasta do portal (Plone) -> {mês: link do arquivo}."""
    saida = {}
    for link in set(re.findall(r'href="([^"]+)"', _get(pasta))):
        m = re.search(padrao, link)
        if m:
            saida[int(m.group(1))] = re.sub(r"/(view|at_download/file)$", "", link) + "/at_download/file"
    return saida


def _valor(t):
    """Número reconhecido no PDF: "13.583.52" e "13.583,52" valem 13583.52."""
    t = re.sub(r"[^\d.,]", "", t or "")
    m = re.match(r"^(.*?)[.,](\d{2})$", t)
    return float(re.sub(r"\D", "", m.group(1)) + "." + m.group(2)) if m else None


def _vaep(b):
    """PDF da VAEP -> [(vereador, total ressarcido)], só quando o valor em números confere com o "Valor do ressarcimento é de R$"."""
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(b)
        f.flush()
        texto = subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, text=True).stdout
    saida, falhas = [], 0
    for pag in texto.split("\f"):
        nome = re.search(r"VEREADOR[A]?\s+([A-ZÀ-Ú][A-ZÀ-Ú .]+?)\s*$", pag, flags=re.M)
        total = re.search(r"TOTAL\s+DO\s+RESSARCIMENTO\s+([\d.,]+)", pag, flags=re.I)
        extenso = re.search(r"ressarc\w*\s+[eé]\s+de\s+R\$\s*([\d .,]+?)\s*\(", pag, flags=re.I)
        if not nome:
            continue
        a, b_ = _valor(total.group(1)) if total else None, _valor(extenso.group(1).replace(" ", ".")) if extenso else None
        if a is not None and b_ is not None and abs(a - b_) < 0.01:
            saida.append((" ".join(nome.group(1).split()), a))
        else:
            falhas += 1
    return saida, falhas


LINHA_PDF = re.compile(r"^\s*(\d{5,6})\s+(.+?)\s{2,}(\d{2}/\d{2}/\d{4})\s+VEREADORA?\s+.*?([\d.]+,\d{2})\s*$")


def _folha_pdf(b):
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(b)
        f.flush()
        texto = subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, text=True).stdout
    saida = []
    for l in texto.splitlines():
        m = LINHA_PDF.match(l)
        if m:
            saida.append((int(m.group(1)), m.group(2), m.group(3), float(m.group(4).replace(".", "").replace(",", "."))))
    return saida


def coletar():
    PASTA.mkdir(parents=True, exist_ok=True)
    h = time.localtime()
    anos = list(range(INICIO // 100, h.tm_year + 1))
    arq_f, arq_v = PASTA / "folha_vereadores.csv", PASTA / "vaep.csv"
    fol = pd.read_csv(arq_f) if arq_f.exists() else pd.DataFrame(columns=["ano", "mes"])
    vae = pd.read_csv(arq_v) if arq_v.exists() else pd.DataFrame(columns=["ano", "mes"])
    feitos_f, feitos_v = set(zip(fol.ano, fol.mes)), set(zip(vae.ano, vae.mes))
    novos_f, novos_v = [], []
    try:
        for a in anos:
            for m, link in sorted(_arquivos(FOLHA.format(ano=a), rf"folha-de-pagamento-0?(\d{{1,2}})-{a}\.xlsx").items()):
                if (a, m) in feitos_f or a * 100 + m < INICIO:
                    continue
                arq = C / f"folha_{a}{m:02d}.xlsx"
                arq.parent.mkdir(parents=True, exist_ok=True)
                arq.write_bytes(_get(link, binario=True))
                try:
                    d = pd.read_excel(arq, sheet_name=0, header=None, skiprows=6).iloc[:, :9]
                    d.columns = ["mat", "nome", "admissao", "cargo", "lotacao", "nivel", "nivel_reduzido", "horas", "bruto"]
                    v = d[d.cargo.astype(str).str.strip().str.upper().isin(["VEREADOR", "VEREADORA"])]
                    linhas = [(int(r.mat), str(r.nome), str(r.admissao)[:10], float(r.bruto)) for r in v.itertuples()]
                except (ValueError, KeyError, OSError):
                    # a planilha às vezes vem vazia (dez/2025): vale o PDF do mesmo mês
                    linhas = _folha_pdf(_get(link.replace(".xlsx/", ".pdf/"), binario=True))
                    log(f"  Aracaju: a planilha da folha de {m:02d}/{a} não abriu; lido o PDF ({len(linhas)} vereadores)")
                for mat, nome, adm, bruto in linhas:
                    novos_f.append({"ano": a, "mes": m, "matricula": mat, "nome": " ".join(nome.split()), "admissao": adm, "bruto": bruto})
            for m, link in []:  # VAEP: ver o comentário no começo do arquivo
                if (a, m) in feitos_v or a * 100 + m < INICIO:
                    continue
                linhas, falhas = _vaep(_get(link, binario=True))
                if falhas:
                    log(f"  Aracaju, VAEP de {m:02d}/{a}: {falhas} página(s) sem o total legível; ficam de fora")
                novos_v += [{"ano": a, "mes": m, "nome": n, "valor": v} for n, v in linhas] or [{"ano": a, "mes": m, "nome": "", "valor": 0.0}]
    finally:
        if novos_f:
            fol = pd.concat([fol, pd.DataFrame(novos_f)])
            fol.sort_values(["ano", "mes", "nome"]).to_csv(arq_f, index=False)
        if novos_v:
            vae = pd.concat([vae, pd.DataFrame(novos_v)])
            vae.sort_values(["ano", "mes", "nome"]).to_csv(arq_v, index=False)
        log(f"  Aracaju: {len(novos_f)} linhas de folha e {len(novos_v)} da VAEP novas")


def montar(tipos):
    arq_f = PASTA / "folha_vereadores.csv"
    if not arq_f.exists():
        return None
    fol = pd.read_csv(arq_f)
    fol = fol[fol.bruto > 0]  # quem aparece na folha com valor zero não estava no exercício do mandato
    tse = comum.candidatos_tse("SE", "Aracaju")
    civil = {normalizar_nome(n): r for n, r in zip(tse.nome, tse.to_dict("records"))} if len(tse) else {}
    ate = comum.ultimo_mes_fechado()
    ultimo = int((fol.ano * 100 + fol.mes).max())
    ver, mandatos, ganha = [], [], []
    for mat, g in fol.groupby("matricula"):
        nome = g.nome.iloc[-1]
        t = civil.get(normalizar_nome(nome))
        ver.append({"codigo": int(mat), "nome": comum.titulo(t["nome_urna"]) if t else comum.titulo(nome), "nome_civil": comum.titulo(nome),
                    "partido": t["partido"] if t else "", "genero": t["genero"] if t else "", "eleito": t["situacao"] if t else "",
                    "pagina": CFG["pagina"]})
        for i, f in comum.periodos_de_meses(g.ano * 100 + g.mes, ultimo):
            mandatos.append({"codigo": int(mat), "inicio": i, "fim": f})
        for r in g.itertuples():
            ganha.append({"ano": r.ano, "mes": r.mes, "codigo": int(mat), "categoria": "salario", "valor": r.bruto})
    cfg = dict(CFG, ultimo_mes=min(ate, ultimo))
    return comum.montar(cfg, tipos, pd.DataFrame(ver), pd.DataFrame(mandatos), ganha=pd.DataFrame(ganha))
