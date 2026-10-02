"""Assembleia Legislativa de Rondônia (ALE-RO): deputado estadual por deputado estadual.

Fonte: Portal da Transparência da ALE-RO, "Verba Indenizatória" (CEAP), por gabinete e mês, nota por nota (prestador,
CNPJ ou CPF mascarado, classe, data, valor), com as verbas gerais e as de saúde, em lotes principal e complementar:
https://transparencia.al.ro.leg.br/Deputados/VerbaIndenizatoria/?categoria=&ano=AAAA&mes=M&gabinete=N
(a página da remuneração pede nome e e-mail de quem consulta: não é usada).
- Subsídio: Lei 5.530/2023 (R$ 33.006,39 desde fev/2024 e R$ 34.774,64 desde fev/2025).
- Nome completo, gênero e eleito/suplente: TSE (eleição de 2022); partido: candidatura de 2026 no TSE.
Quem esteve no cargo em cada mês sai dos meses com prestação de contas (o cabeçalho de cada lote diz o deputado); quem
está no cargo hoje, da lista de deputados do site da ALE-RO (https://www.al.ro.leg.br/deputados/perfil/). A lista de
gabinetes da página da verba guarda o gabinete do suplente depois que o titular volta: serve só para baixar a verba.
"""
import html as H
import re
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from ..config import CACHE, DADOS
from ..prefeituras.comum import feminino, num
from ..util import TempoEsgotado, _sessao, dormir, log, normalizar_nome, verificar_prazo
from ..vereadores import comum as vc
from . import comum

UF = "RO"
COD = comum.CODIGOS_UF[UF]
INICIO = 202501
PAGINA = "https://transparencia.al.ro.leg.br/Deputados/VerbaIndenizatoria/"
PASTA = DADOS / "assembleias" / "ro"
C = CACHE / "assembleias" / "ro"
SIMULTANEOS = 3
CFG = {
    "cod": COD, "n": "Rondônia", "uf": UF, "casa": "Assembleia Legislativa de Rondônia", "vagas": 24, "inicio": INICIO,
    "id_prefixo": "est", "k": "e", "cargo": ("Deputada estadual", "Deputado estadual"),
    "subsidio": [[202402, 33006.39], [202502, 34774.64]],
    "salario_nota": ("Subsídio fixado em lei (Lei 5.530/2023), proporcional aos meses no cargo. A página de remuneração da ALE-RO pede "
                     "nome e e-mail de quem consulta, por isso o 13º e outros pagamentos não aparecem aqui."),
    "verba_nome": "Cota para o Exercício da Atividade Parlamentar (verba indenizatória)",
    "verba_regra": "Reembolso de despesas do mandato com nota fiscal, e um reembolso de despesas de saúde à parte.",
    "verba_notas": ["Cada mês pode ter um lote principal e um complementar; os dois entram no mês.",
                    "Os reembolsos de saúde não têm o prestador publicado: aparecem só com o valor."],
    "pagina": "https://transparencia.al.ro.leg.br/",
    "notas": ["Quem está no cargo hoje: a lista de deputados do site da ALE-RO. Desde quando: os meses com prestação de contas.",
              "Partido: o da candidatura de 2026 no TSE. Quem não é candidato em 2026 aparece sem partido."],
    "fontes": {"verba": PAGINA, "subsidio": "https://sapl.al.ro.leg.br/media/sapl/public/normajuridica/2023/11274/lei_5530.pdf"},
}
DOC = re.compile(r"(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\*{3}\.\d{3}\.\d{3}\*?-\*{2})")


def _get(params):
    verificar_prazo()
    for tentativa in range(3):
        try:
            r = _sessao().get(PAGINA, params=params, timeout=120)
            r.raise_for_status()
            dormir(0.5)
            return r.text
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 2:
                raise
            dormir(15)


def _gabinetes():
    t = _get({})
    s = re.search(r'<select[^>]*name="gabinete"[^>]*>(.*?)</select>', t, flags=re.S)
    return [(v, " ".join(H.unescape(n).split())) for v, n in re.findall(r'<option[^>]*value="(\d+)"[^>]*>([^<]*)', s.group(1) if s else "")]


def _ler(t, am, gab):
    saida, ctx = [], None
    for cel in re.findall(r"<td[^>]*>(.*?)</td>", t, flags=re.S):
        x = " ".join(H.unescape(re.sub(r"<[^>]+>", " ", cel)).split())
        m = re.match(r"(Deputad[oa] .+?) - Mes: (\d+)/(\d{4}) - Lote: (\w+) - (Verbas? [^-]+?) - Total pago", x)
        if m:
            ctx = {"deputado": re.sub(r"^Deputad[oa]\s+", "", m.group(1)).strip(), "lote": m.group(4), "verba": m.group(5).strip()}
            continue
        if not ctx or "Valor:" not in x:
            continue
        valor = num(re.search(r"Valor:\s*R\$\s*([\d.,-]+)", x).group(1)) if re.search(r"Valor:\s*R\$\s*([\d.,-]+)", x) else 0.0
        data = (re.search(r"Data:\s*(\d{2}/\d{2}/\d{4})", x) or [None, ""])[1]
        classe = (re.search(r"Classe:\s*([^|]+)", x) or [None, ""])[1].strip()
        prest = (re.search(r"Prestador:\s*([^|]+)", x) or [None, ""])[1].strip()
        doc = DOC.search(prest)
        nome = prest[:doc.start()].strip() if doc else prest
        saude = "SAUDE" in normalizar_nome(ctx["verba"])
        saida.append({"ano": am // 100, "mes": am % 100, "gabinete": gab, "deputado": ctx["deputado"], "lote": ctx["lote"],
                      "tipo": "Reembolso de despesas de saúde" if saude else (classe.capitalize() or "Outras despesas"),
                      "fornecedor": "" if saude else nome, "cnpj_cpf": doc.group(1) if doc else "", "data": data, "valor": valor})
    return saida


def _meses():
    h = time.localtime()
    return [a * 100 + m for a in range(INICIO // 100, h.tm_year + 1) for m in range(1, 13) if INICIO <= a * 100 + m < h.tm_year * 100 + h.tm_mon]


LISTA = "https://www.al.ro.leg.br/deputados/perfil/"


def _em_exercicio():
    """Nomes da lista de deputados do site da ALE-RO (quem está em exercício hoje)."""
    verificar_prazo()
    t = _sessao().get(LISTA, timeout=120).text
    return [" ".join(H.unescape(re.sub(r"<[^>]+>", "", n)).split())
            for n in re.findall(r'<a href="/deputados/perfil/[^"]+">\s*<div class="font-bold[^"]*">(.*?)</div>', t, flags=re.S)]


def coletar():
    PASTA.mkdir(parents=True, exist_ok=True)
    (C / "paginas").mkdir(parents=True, exist_ok=True)
    try:
        comum.gravar_em_exercicio(PASTA, _em_exercicio(), CFG["vagas"], LISTA)
    except TempoEsgotado:
        raise
    except Exception as e:  # noqa: BLE001 — sem a lista, fica a que já estava gravada
        log(f"  ALE-RO: a lista de deputados não abriu ({type(e).__name__}); fica a já gravada")
    gabs = _gabinetes()
    if len(gabs) >= 20:
        pd.DataFrame(gabs, columns=["gabinete", "nome"]).assign(visto_em=time.strftime("%Y-%m-%d")).to_csv(PASTA / "gabinetes.csv", index=False)
    meses = _meses()
    fila = []
    for am in meses:
        for gab, _ in gabs:
            arq = C / "paginas" / f"{am}_{gab}.html"
            if arq.exists() and (am < meses[-2] or time.time() - arq.stat().st_mtime < 3 * 86400):
                continue
            fila.append((am, gab, arq))

    def uma(item):
        am, gab, arq = item
        arq.write_text(_get({"categoria": "", "ano": am // 100, "mes": am % 100, "gabinete": gab}), encoding="utf-8")

    try:
        with ThreadPoolExecutor(SIMULTANEOS) as ex:
            list(ex.map(uma, fila))
    finally:
        linhas = []
        for am in meses:
            for gab, _ in gabs:
                arq = C / "paginas" / f"{am}_{gab}.html"
                if arq.exists():
                    linhas += _ler(arq.read_text(encoding="utf-8"), am, gab)
        df = pd.DataFrame(linhas)
        if len(df):
            df.sort_values(["ano", "mes", "gabinete", "lote", "data"]).to_csv(PASTA / "verba_notas.csv", index=False)
        faltam = sum(1 for am in meses for gab, _ in gabs if not (C / "paginas" / f"{am}_{gab}.html").exists())
        log(f"  ALE-RO: {len(gabs)} gabinetes, {len(df)} notas, {faltam} páginas (gabinete e mês) ainda por baixar")


def montar(tipos):
    arq = PASTA / "verba_notas.csv"
    if not arq.exists():
        return None
    v = pd.read_csv(arq, dtype={"cnpj_cpf": str}).fillna("")
    tse = comum.tse_2022(UF)
    partidos = comum.partido_2026(UF)
    ultimo = vc.ultimo_mes_fechado()
    ultimo_dado = int((v.ano * 100 + v.mes).max())
    ver, mandatos, cods = [], [], {}
    for nome, g in v.groupby("deputado"):
        t = comum.achar(nome, tse) or {}
        codigo = comum.codigo_de(nome, t)
        cods[nome] = codigo
        ver.append({"codigo": codigo, "nome": nome, "nome_civil": vc.titulo(t.get("nome", "")) if t else "",
                    "partido": partidos.get(normalizar_nome(t.get("nome", "")), "") if t else "",
                    "genero": t.get("genero") or ("F" if re.match(r"^Deputada", nome) or feminino(nome) else "M"), "eleito": t.get("eleito", ""),
                    "pagina": CFG["pagina"]})
        for i, f in comum.periodos(list(g.ano * 100 + g.mes), ultimo_dado, ultimo):
            mandatos.append({"codigo": codigo, "inicio": i, "fim": f})
    lista, atual = comum.ler_em_exercicio(PASTA), None  # quem está no cargo hoje; os meses com prestação dizem desde quando
    if lista:
        atual = comum.casar_em_exercicio(lista, ver, UF)
        mandatos = comum.aplicar_hoje(mandatos, atual, ultimo_dado)
    desp = v.assign(codigo=v.deputado.map(cods))
    cfg = dict(CFG, ultimo_mes=min(ultimo, ultimo_dado), fora_hoje=comum.fora_hoje(atual))
    return vc.montar(cfg, tipos, pd.DataFrame(ver), pd.DataFrame(mandatos), despesas=desp[["ano", "mes", "codigo", "tipo", "fornecedor", "cnpj_cpf", "valor"]])
