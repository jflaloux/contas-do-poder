"""São Paulo: Portal da Transparência do Estado, "Remuneração": o arquivo do mês atual (CSV, ~64 MB) e a série
histórica (um .rar por mês), com o nome, o cargo, o órgão e as partes da remuneração (sem CPF).
https://www.transparencia.sp.gov.br/PortalTransparencia-Report/Remuneracao.aspx
O arquivo "atual" não diz o mês: é o mês seguinte ao último da série histórica. Os .rar são lidos com a biblioteca
libarchive (pacote libarchive-c); sem ela, o robô fica só com o arquivo do mês atual."""
import re
import time

from ..util import TempoEsgotado, _sessao, verificar_prazo
from . import comum

UF = "SP"
BASE = "https://www.transparencia.sp.gov.br/PortalTransparencia-Report"
PAGINA = f"{BASE}/Remuneracao.aspx"
FONTE = PAGINA
MESES = {"JANEIRO": 1, "FEVEREIRO": 2, "MARCO": 3, "ABRIL": 4, "MAIO": 5, "JUNHO": 6, "JULHO": 7, "AGOSTO": 8, "SETEMBRO": 9,
         "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12}


def _arquivos():
    """{AAAAMM: url}: a série histórica e o mês atual."""
    t = _sessao().get(PAGINA, timeout=120).text
    saida = {}
    for mes, ano in re.findall(r"historico/remuneracao_([A-Za-z]+)_(\d{4})\.rar", t):
        if comum.normalizar_nome(mes) in MESES:
            saida[int(ano) * 100 + MESES[comum.normalizar_nome(mes)]] = f"{BASE}/historico/remuneracao_{mes}_{ano}.rar"
    if saida and "txt/RemuneracaoAtivos.csv" in t:
        a, m = divmod(max(saida), 100)
        saida[a * 100 + m + 1 if m < 12 else (a + 1) * 100 + 1] = f"{BASE}/txt/RemuneracaoAtivos.csv"
    return saida


def _linhas_rar(url):
    try:
        import libarchive  # noqa: PLC0415 — opcional (precisa da biblioteca libarchive do sistema)
    except Exception as e:  # noqa: BLE001
        raise ImportError(e) from e
    verificar_prazo()
    for tentativa in range(3):
        try:
            conteudo = _sessao().get(url, timeout=600).content
            break
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 2:
                raise
            time.sleep(30)
    achadas, cab, resto = [], None, b""
    with libarchive.memory_reader(conteudo) as arq:
        for entrada in arq:
            for bloco in entrada.get_blocks():
                resto += bloco
                *linhas, resto = resto.split(b"\n")
                for l in linhas:
                    if cab is None:
                        cab = [c.strip() for c in l.decode("latin-1").split(";")]
                    elif b"GOVERNADOR" in l.upper():
                        achadas.append(dict(zip(cab, l.decode("latin-1").rstrip("\r").split(";"))))
            break  # um arquivo só dentro do .rar
    return cab, achadas


def _mes(am, url):
    cab, achadas = _linhas_rar(url) if url.endswith(".rar") else comum.linhas_csv(url, ["GOVERNADOR"], encoding="latin-1")
    col = {comum.normalizar_nome(c): c for c in cab}
    v = lambda x, nome: comum.num(x.get(col.get(nome, nome)))
    linhas = []
    for x in achadas:
        tp = comum.tp_do_cargo(x.get(col.get("CARGO", "CARGO")))
        if not tp:
            continue
        partes = {"salario": v(x, "REMUNERACAO DO MES"), "decimo": None, "ferias": None, "beneficios": None,
                  # 13º e férias vêm juntos numa coluna; entram em "outros", com os eventuais e as indenizações
                  "outros": v(x, "FERIAS E 13O SALARIO") + v(x, "PAGAMENTOS EVENTUAIS")
                  + v(x, "LICENCA PREMIO INDENIZADA") + v(x, "ABONO PERMANENCIA & OUTRAS INDENIZACOES")}
        redutor = abs(v(x, "REDUTOR SALARIAL"))
        linhas.append(comum.linha(am, tp, x[col["NOME"]], x[col["CARGO"]], sum(p for p in partes.values() if p), partes, redutor))
    return linhas


def coletar():
    arquivos = _arquivos()
    feitos, linhas = [], []
    for am in comum.a_fazer(UF, max(arquivos)):
        if am not in arquivos:
            continue
        try:
            ls = _mes(am, arquivos[am])
        except ImportError:
            comum.avisar(UF, "sem a biblioteca libarchive, a série histórica (.rar) fica para depois")
            continue
        linhas += ls
        feitos.append(am)
        comum.gravar(UF, linhas, feitos)
    return len(linhas)
