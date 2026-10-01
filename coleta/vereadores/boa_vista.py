"""Câmara Municipal de Boa Vista: vereador por vereador.

Fontes (Portal da Câmara, sem cadastro):
- Verba indenizatória (Resolução 182/2013 e alterações): um PDF por vereador e mês, com o quadro de valores (despesa,
  limite, gasto, ressarcimento e total pago): https://www.boavista.rr.leg.br/transparencia/parlamentares-e-gabinetes/<ano>/<mês>.
  Quem estava no cargo em cada mês: os vereadores com o quadro do mês (23 por mês).
- Subsídio: Resolução 253/2023, R$ 20.864,78 (60% do subsídio de deputado estadual) desde 1º de fevereiro de 2025:
  https://sapl.boavista.rr.leg.br/media/sapl/public/normajuridica/2023/4107/res-253-2023.pdf
- Nome de urna, partido e gênero: TSE (eleição de 2024), pelo nome completo do quadro.
"""
import re
import subprocess
import tempfile
import time
import zlib
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from ..config import CACHE, DADOS
from ..util import TempoEsgotado, _sessao, dormir, log, normalizar_nome, verificar_prazo
from . import comum

COD = 1400100
INICIO = 202502
SITE = "https://www.boavista.rr.leg.br/transparencia/parlamentares-e-gabinetes"
PASTA = DADOS / "municipios" / "boa_vista"
C = CACHE / "cmboavista"
MESES = ["JANEIRO", "FEVEREIRO", "MARCO", "ABRIL", "MAIO", "JUNHO", "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"]
CFG = {
    "cod": COD, "n": "Boa Vista", "uf": "RR", "casa": "Câmara Municipal de Boa Vista", "vagas": 23, "inicio": INICIO,
    "subsidio": [[202502, 20864.78]],
    "salario_nota": ("Subsídio fixado pela Resolução 253/2023 (60% do subsídio de deputado estadual), desde fev/2025, proporcional aos "
                     "meses no cargo. A Câmara não publica a folha dos vereadores, por isso o 13º e outros pagamentos não aparecem aqui."),
    "verba_nome": "Verba indenizatória", "verba_mes": {"2025": 40000.0, "2026": 40000.0},
    "verba_regra": "Ressarcimento de despesas do mandato, com limite por tipo de despesa e de R$ 40.000 por mês (Resolução 182/2013 e alterações).",
    "verba_notas": ["A Câmara publica um quadro por vereador e mês, por tipo de despesa, sem fornecedor nem CNPJ."],
    "credito_foto": "Câmara Municipal de Boa Vista", "pagina": "https://www.boavista.rr.leg.br/processo-legislativo/vereadores",
    "notas": ["Quem estava no cargo em cada mês: os vereadores com o quadro da verba indenizatória do mês."],
    "fontes": {"verba": SITE, "subsidio": "https://sapl.boavista.rr.leg.br/media/sapl/public/normajuridica/2023/4107/res-253-2023.pdf"},
}


def _get(url, binario=False):
    verificar_prazo()
    for tentativa in range(3):
        try:
            r = _sessao().get(url, timeout=120)
            r.raise_for_status()
            dormir(1)
            return r.content if binario else r.text
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 2:
                raise
            dormir(15)


def _meses_do_ano(ano):
    """Pasta do ano -> {mês: endereço da pasta do mês} (as pastas têm nomes como "janeiro-1" e "marco-1")."""
    saida = {}
    for link in set(re.findall(rf'href="({re.escape(SITE)}/{ano}/([a-z]+)(?:-\d+)?)"', _get(f"{SITE}/{ano}"))):
        nome = normalizar_nome(link[1])
        if nome in MESES:
            saida.setdefault(MESES.index(nome) + 1, link[0])
    return saida


ITEM = re.compile(r"^\s*(\d+)\s+(.+?)\s+([\d.]+,\d{2})\s+([\d.]+,\d{2})\s+([\d.]+,\d{2})\s*$")


def _quadro(b):
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(b)
        f.flush()
        texto = subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, text=True).stdout
    nome = re.search(r"VEREADOR[A]?\s*:\s*(.+)", texto)
    num = lambda t: float(t.replace(".", "").replace(",", "."))
    itens = [(m.group(2).strip(), num(m.group(5))) for m in map(ITEM.match, texto.splitlines()) if m]
    pago = re.search(r"TOTAL\s+PAGO\s+([\d.]+,\d{2})", texto)
    return (" ".join(nome.group(1).split()) if nome else ""), itens, (num(pago.group(1)) if pago else None)


def coletar():
    PASTA.mkdir(parents=True, exist_ok=True)
    try:  # se o portal não responder, desiste logo: o site usa o que já está gravado
        _sessao().get(SITE, timeout=20).raise_for_status()
    except Exception as e:  # noqa: BLE001
        log(f"  Boa Vista: o portal da Câmara não abriu ({type(e).__name__}); fica o que já estava gravado")
        return
    h = time.localtime()
    arq = PASTA / "verba_quadros.csv"
    feito = pd.read_csv(arq) if arq.exists() else pd.DataFrame(columns=["ano", "mes", "arquivo"])
    vistos = set(zip(feito.ano, feito.mes, feito.arquivo))
    pedir = []
    for a in range(INICIO // 100, h.tm_year + 1):
        for m, pasta in sorted(_meses_do_ano(a).items()):
            if not INICIO <= a * 100 + m < h.tm_year * 100 + h.tm_mon:
                continue
            # os arquivos às vezes vêm sem ".pdf" no endereço (fev/2025)
            links = set(re.findall(rf'href="({re.escape(pasta)}/[^"/#?]+)"', _get(pasta)))
            for pdf in sorted(l for l in links if l.rsplit("/", 1)[1] not in ("RSS", "rss.xml", "atom.xml", "view")
                              and normalizar_nome(re.sub(r"-\d+$", "", l.rsplit("/", 1)[1])) not in MESES):
                if (a, m, pdf.rsplit("/", 1)[1]) not in vistos:
                    pedir.append((a, m, pdf))

    def um(item):
        a, m, pdf = item
        try:
            b = _get(pdf, binario=True)
            if not b.startswith(b"%PDF"):
                b = _get(pdf + "/at_download/file", binario=True)
        except TempoEsgotado:
            raise
        except Exception:  # noqa: BLE001 — link quebrado na pasta do mês (404): guarda vazio para não pedir de novo
            b = b""
        if not b.startswith(b"%PDF"):
            return [{"ano": a, "mes": m, "arquivo": pdf.rsplit("/", 1)[1], "vereador": "", "total_pago": None, "despesa": "", "valor": 0.0}]
        nome, itens, pago = _quadro(b)
        soma = round(sum(v for _, v in itens), 2)
        if pago is not None and abs(soma - pago) >= 0.01:
            log(f"  Boa Vista: {nome} {m:02d}/{a}: itens somam {soma:.2f} e o total pago é {pago:.2f}")
        base = {"ano": a, "mes": m, "arquivo": pdf.rsplit("/", 1)[1], "vereador": nome, "total_pago": pago}
        return [{**base, "despesa": d, "valor": v} for d, v in itens] or [{**base, "despesa": "", "valor": 0.0}]
    res = []
    try:
        with ThreadPoolExecutor(3) as ex:
            for r in ex.map(um, pedir):
                res.append(r)
    finally:
        if res:
            feito = pd.concat([feito, pd.DataFrame([x for r in res for x in r])])
            feito.sort_values(["ano", "mes", "vereador", "despesa"]).to_csv(arq, index=False)
        log(f"  Boa Vista: {len(res)} de {len(pedir)} quadros da verba baixados agora")


_TIPOS = [(r"CONTAB", "Consultorias e assessorias"), (r"IMPRENSA|DIVULGA", "Divulgação do mandato"), (r"JUR[IÍ]DIC", "Consultorias e assessorias"),
          (r"GR[AÁ]FIC", "Material gráfico (arte e impressão)"), (r"COMBUST", "Combustível"), (r"VE[IÍ]CULO", "Aluguel de carros"),
          (r"IM[OÓ]VEL|ESCRIT", "Escritório (aluguel e contas)"), (r"TELEF|INTERNET", "Telefone e internet")]


def _tipo(d):
    u = normalizar_nome(d)
    for rx, nome in _TIPOS:
        if re.search(rx, u):
            return nome
    return comum.tipo_curto(d)


def montar(tipos):
    arq = PASTA / "verba_quadros.csv"
    if not arq.exists():
        return None
    v = pd.read_csv(arq).fillna({"despesa": "", "vereador": ""})
    v = v[v.vereador != ""]
    tse = comum.candidatos_tse("RR", "Boa Vista")
    civil = {normalizar_nome(n): r for n, r in zip(tse.nome, tse.to_dict("records"))} if len(tse) else {}
    opcoes = [(n, i) for i, n in enumerate(tse.nome)] if len(tse) else []
    ate = comum.ultimo_mes_fechado()
    ultimo = int((v.ano * 100 + v.mes).max())
    ver, mandatos, cods, info = [], [], {}, {}
    for nome in v.vereador.map(normalizar_nome).unique():  # o mesmo vereador às vezes vem com grafias diferentes
        t = civil.get(nome)
        if t is None and opcoes:  # "BABARA RIBEIRO FALCÃO" no quadro x "BARBARA RIBEIRO FALCAO" no TSE
            i = comum.achar_parecido(nome, opcoes, 0.9)
            t = tse.iloc[i].to_dict() if i is not None else None
        cods[nome] = int(t["sq"]) if t else zlib.crc32(nome.encode())
        info[cods[nome]] = t
    v["codigo"] = v.vereador.map(normalizar_nome).map(cods)
    for codigo, g in v.groupby("codigo"):
        t = info[codigo]
        ver.append({"codigo": codigo, "nome": comum.titulo(t["nome_urna"]) if t else comum.titulo(g.vereador.iloc[-1]),
                    "nome_civil": comum.titulo(t["nome"]) if t else comum.titulo(g.vereador.iloc[-1]), "partido": t["partido"] if t else "",
                    "genero": t["genero"] if t else "", "eleito": t["situacao"] if t else "", "pagina": CFG["pagina"]})
        for i, f in comum.periodos_de_meses(g.ano * 100 + g.mes, ultimo):
            mandatos.append({"codigo": codigo, "inicio": i, "fim": f})
    d = v[(v.despesa != "") & (v.valor.abs() >= 0.005)]
    desp = pd.DataFrame({"ano": d.ano, "mes": d.mes, "codigo": d.codigo, "tipo": d.despesa.map(_tipo),
                         "fornecedor": "", "cnpj_cpf": "", "valor": d.valor})
    # o total do mês é o "total pago" do quadro: a diferença (linha que a leitura não pegou, ou o que passou do limite) vira uma linha
    ajustes = []
    for (a, m, c), g in v.groupby(["ano", "mes", "codigo"]):
        pago = g.drop_duplicates("arquivo").total_pago.dropna()
        dif = round(float(pago.sum()) - float(g.valor.sum()), 2) if len(pago) else 0.0
        if abs(dif) >= 0.01:
            ajustes.append({"ano": a, "mes": m, "codigo": c, "tipo": "Outros itens do quadro" if dif > 0 else "Acima do limite mensal",
                            "fornecedor": "", "cnpj_cpf": "", "valor": dif})
    if ajustes:
        desp = pd.concat([desp, pd.DataFrame(ajustes)])
    cfg = dict(CFG, ultimo_mes=min(ate, ultimo))
    return comum.montar(cfg, tipos, pd.DataFrame(ver), pd.DataFrame(mandatos), despesas=desp)
