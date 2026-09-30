"""Goiás: dados abertos do Estado, "Folha de Pagamento" (Secretaria da Administração), um CSV por mês (e, para os anos
fechados, um ZIP com os 12 meses). O governador aparece como "Governador - DSE-1" (Secretaria-Geral de Governo) e o vice
como "Vice-Governador - DSE-2" (Vice-Governadoria). O arquivo traz o provento total (com 13º e férias), o provento do
mês, o 13º, as férias e o corte do teto; os descontos pessoais não são lidos.
O robots.txt do portal pede 10 segundos entre os acessos e proíbe /api/: usamos só a página do conjunto de dados e os
arquivos. https://dadosabertos.go.gov.br/dataset/folha-de-pagamento"""
import io
import re
import tempfile
import time
import zipfile

from ..util import _sessao, verificar_prazo
from . import _http, comum

UF = "GO"
FONTE = "https://dadosabertos.go.gov.br/dataset/folha-de-pagamento"
CHAVE = "GOVERNADOR - DSE"  # "Governador - DSE-1" e "Vice-Governador - DSE-2"
PAUSA = 10  # Crawl-delay do robots.txt


def _arquivos():
    """{aaaamm: url do CSV} e {ano: url do ZIP do ano}, pela página do conjunto de dados."""
    html = _http.get(FONTE, json=False, pausa=PAUSA).text
    urls = {u if u.startswith("http") else f"https://dadosabertos.go.gov.br{u}"
            for u in re.findall(r'href="([^"]+/download/folhapagamento_[^"]+\.(?:csv|zip))"', html, re.I)}
    mensais, anuais = {}, {}
    for u in urls:
        m = re.search(r"folhapagamento_(\d{6})\.csv$", u, re.I)
        a = re.search(r"folhapagamento_ano_(\d{4})\.zip$", u, re.I)
        if m:
            mensais[int(m.group(1))] = u
        elif a:
            anuais[int(a.group(1))] = u
    return mensais, anuais


def _linha(x):
    n = lambda k: comum.num(x.get(k))
    cargo = x.get("NOMECARGO") or ""
    tp = "vice" if "VICE" in comum.normalizar_nome(cargo) else "gov"
    mes, dec, fer, total = n("VALORPROVENTOMES"), n("VALORDECIMOTERCEIRO"), n("VALORFERIAS"), n("VALORPROVENTO")
    outros = round(total - mes - dec - fer, 2)
    partes = {"salario": mes, "decimo": dec, "ferias": fer, "outros": outros if outros > 0.5 else 0.0}
    if outros < -0.5:  # as partes passam do total: fica só o total
        partes = None
    return comum.linha(int(x["ANOMES"]), tp, x["NOMESERVIDOR"], cargo, total, partes, abs(n("VALORCORTETETO")))


def _do_zip(url, meses):
    """Linhas dos meses pedidos, de dentro do ZIP do ano (um CSV por mês)."""
    import csv
    linhas = []
    with tempfile.TemporaryFile() as tmp:
        with _sessao().get(url, stream=True, timeout=900) as r:
            r.raise_for_status()
            for bloco in r.iter_content(1 << 22):
                tmp.write(bloco)
        verificar_prazo()
        tmp.seek(0)
        with zipfile.ZipFile(tmp) as z:
            for nome in z.namelist():
                m = re.search(r"(\d{6})\.csv$", nome, re.I)
                if not m or int(m.group(1)) not in meses:
                    continue
                with z.open(nome) as f:
                    cab = None
                    for bruta in f:
                        if cab is None:
                            cab = next(csv.reader([bruta.decode("utf-8-sig", "replace")], delimiter=";"))
                            continue
                        if CHAVE.encode() in bruta.upper():
                            linhas.append(_linha(dict(zip(cab, next(csv.reader([bruta.decode("utf-8", "replace")], delimiter=";"))))))
    return linhas


def coletar():
    meses = comum.a_fazer(UF, comum.ultimo_possivel())
    if not meses:
        return 0
    mensais, anuais = _arquivos()
    linhas, feitos = [], set()
    for am in meses:
        if am in mensais:
            time.sleep(PAUSA)
            _, achadas = comum.linhas_csv(mensais[am], [CHAVE])
            linhas += [_linha(x) for x in achadas]
            feitos.add(am)
    for ano in sorted({am // 100 for am in meses if am not in mensais}):
        if ano in anuais:
            time.sleep(PAUSA)
            pedidos = {am for am in meses if am // 100 == ano and am not in mensais}
            novas = _do_zip(anuais[ano], pedidos)
            linhas += novas
            feitos |= {l["aaaamm"] for l in novas}
    comum.gravar(UF, linhas, sorted(feitos))
    return len(linhas)
