"""Câmara Municipal de Maceió: vereador por vereador.

Fontes (portal da Câmara, sem cadastro; o site não tem robots.txt):
- Vereadores atuais (nome parlamentar, partido, foto e página): https://www.maceio.al.leg.br/vereadores-atuais.
  Os suplentes que assumiram e já saíram da lista têm página em /vereadores/<nº> (procuramos os números da
  legislatura atual que faltam na lista).
- Folha de pagamento por lotação, mês a mês (número de servidores e valor bruto de cada gabinete), um ano por vez:
  https://www.maceio.al.leg.br/transparencia/portal/relatorios/excel_folha.php?lotacao=&mes=&ano= (tabela HTML).
  O mês "13" é a folha do 13º salário.
- Folha nominal de uma lotação, em PDF: .../transparencia/portal/relatorios/pdf_folha_lot.php?lotacao=&mes=&ano=
  A dos vereadores é a lotação "VEREADOR" (publicada com nomes desde out/2025; antes, só o total da lotação).
  Guardamos só o bruto de cada vereador; dos gabinetes, só a contagem de cargos do último mês.
  Matrícula, descontos, líquido e nomes de assessores não são guardados.
- VIAP (Verba Indenizatória de Atividade Parlamentar), mês a mês por vereador:
  .../transparencia/portal/viap-detalhes&vereador=<nº>&ano= (gasto apresentado, glosas, excesso e valor indenizado).
  Lei 7.137/2022, alterada pela Lei 7.629/2025: até R$ 20.500 por mês. O tipo de despesa só está no requerimento de
  cada mês, em PDF (de 1 a 100 MB, com as notas escaneadas, e cada gabinete monta o seu de um jeito): não é lido.
- Nome completo, partido e gênero: TSE (eleição de 2024).
Para ler os PDFs da folha é preciso o programa pdftotext (pacote poppler-utils); sem ele, essa parte fica como estava.
"""
import hashlib
import html as html_lib
import os
import re
import shutil
import subprocess
import time

import pandas as pd

from ..config import CACHE, DADOS
from ..util import _sessao, cache_valido, log, normalizar_nome, verificar_prazo
from . import comum

COD = 2704302
INICIO = 202501
SITE = "https://www.maceio.al.leg.br"
PORTAL = f"{SITE}/transparencia/portal"
PASTA = DADOS / "municipios" / "maceio"
C = CACHE / "cmmaceio"
REBAIXAR = 3
PRIMEIRO_NUMERO = 114  # o primeiro vereador cadastrado no site para a legislatura 2025–2028 (os reeleitos mantêm o número antigo)
VIAP_MES = 20500.0
MESES_NOME = {normalizar_nome(n): i for i, n in enumerate(["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto",
                                                           "Setembro", "Outubro", "Novembro", "Dezembro"], 1)}
CFG = {
    "cod": COD, "n": "Maceió", "uf": "AL", "casa": "Câmara Municipal de Maceió", "vagas": 27, "inicio": INICIO,
    "verba_nome": "Verba Indenizatória de Atividade Parlamentar (VIAP)", "verba_mes": {"2025": VIAP_MES, "2026": VIAP_MES},
    "verba_regra": "Reembolso de despesas do mandato, até R$ 20.500 por mês (Lei 7.137/2022, alterada pela Lei 7.629/2025). "
                   "O que passa do limite num mês pode ser reembolsado no mês seguinte.",
    "verba_notas": ["A Câmara publica o valor reembolsado em cada mês; o tipo de despesa e as notas só estão no requerimento de cada vereador, em PDF, por isso a verba aparece aqui sem divisão por tipo."],
    "equipe_nota": "Servidores lotados no gabinete, pela folha de pagamento da Câmara (valor bruto, com o 13º).",
    "credito_foto": "Câmara Municipal de Maceió", "pagina": f"{SITE}/vereadores-atuais",
    "fontes": {"vereadores": f"{SITE}/vereadores-atuais", "folha": f"{PORTAL}/folhax", "viap": f"{PORTAL}/viapx"},
}


# ---------------------------------------------------------------- acesso ao site
def _pedir(url, params=None, arquivo=None, dias=None):
    """GET de uma página (texto). De fora do Brasil o servidor às vezes derruba a conexão: tenta de novo."""
    if arquivo is not None and cache_valido(arquivo, dias):
        return arquivo.read_text(encoding="utf-8")
    verificar_prazo()
    for tentativa in range(6):
        try:
            r = _sessao().get(url, params=params, timeout=120)
            r.raise_for_status()
            t = r.content.decode("utf-8-sig", errors="replace")
            break
        except Exception:
            if tentativa == 5:
                raise
            time.sleep(3 + 3 * tentativa)
    time.sleep(1)
    if arquivo is not None:
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_text(t, encoding="utf-8")
    return t


def _texto_pdf(url, params=None):
    """Baixa um PDF para um arquivo temporário, devolve o texto (pdftotext -layout) e apaga o arquivo."""
    verificar_prazo()
    C.mkdir(parents=True, exist_ok=True)
    tmp = C / f"tmp_{os.getpid()}.pdf"
    try:
        for tentativa in range(6):
            try:
                with _sessao().get(url, params=params, timeout=300, stream=True) as r:
                    r.raise_for_status()
                    with open(tmp, "wb") as f:
                        for bloco in r.iter_content(1 << 20):
                            f.write(bloco)
                break
            except Exception:
                if tentativa == 5:
                    raise
                time.sleep(3 + 3 * tentativa)
        return subprocess.run(["pdftotext", "-layout", str(tmp), "-"], capture_output=True, text=True, timeout=300).stdout
    finally:
        tmp.unlink(missing_ok=True)
        time.sleep(1)


def _valor(t):
    t = re.sub(r"[^\d,]", "", str(t or ""))
    return float(t.replace(",", ".")) if t else 0.0


def _juntar(*dfs):
    """pd.concat das tabelas que têm linhas (sem aviso do pandas sobre tabelas vazias)."""
    cheios = [d for d in dfs if len(d)]
    return pd.concat(cheios, ignore_index=True) if cheios else dfs[0].iloc[0:0]


def _limpo(t):
    return re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", t or ""))).strip()


# ---------------------------------------------------------------- coleta
def lista_site():
    """Nome parlamentar, partido, foto e página dos vereadores atuais e dos suplentes que já passaram pela Câmara."""
    t = _pedir(f"{SITE}/vereadores-atuais")
    linhas = []
    for bloco in t.split("<!--Grid column-->"):
        a = re.search(r'href="https?://www\.maceio\.al\.leg\.br/vereadores/(\d+)"', bloco)
        nome = re.search(r'<h6 class="card-title[^"]*">(.*?)</h6>', bloco, re.S)
        if not (a and nome):
            continue
        img = re.search(r'<img\s[^>]*?src="([^"]*/galeria/vereadores/[^"]+)"', bloco, re.S)
        partido = re.search(r'<p class="card-text[^"]*">(.*?)</p>', bloco, re.S)
        n = _limpo(nome.group(1))
        linhas.append({"numero": int(a.group(1)), "nome": re.sub(r"\s*-\s*Licenciad[oa]\s*$", "", n, flags=re.I).strip(),
                       "partido": _limpo(partido.group(1)).strip("() ") if partido else "", "licenciado": int(bool(re.search(r"Licenciad", n, re.I))),
                       "atual": 1, "foto": img.group(1) if img else "", "pagina": f"{SITE}/vereadores/{a.group(1)}"})
    if not linhas:
        raise RuntimeError("a página de vereadores atuais veio sem vereadores")
    # suplentes que saíram da lista: páginas da legislatura atual que não estão nela
    atuais = {l["numero"] for l in linhas}
    for numero in range(PRIMEIRO_NUMERO, max(atuais) + 6):
        if numero in atuais:
            continue
        p = _pedir(f"{SITE}/vereadores/{numero}", arquivo=C / f"vereador_{numero}.html", dias=30)
        nome = re.search(r'<h6 class="card-title[^"]*">(.*?)</h6>', p, re.S)
        if not nome or not _limpo(nome.group(1)):
            continue  # número sem vereador
        img = re.search(r'<meta property="og:image" content="([^"]*/galeria/vereadores/[^"]+)"', p)
        partido = re.search(r'<h6 class="card-title[^"]*">.*?</h6>\s*(?:<!--[^>]*-->\s*)?<p class="card-text[^"]*">(.*?)</p>', p, re.S)
        linhas.append({"numero": numero, "nome": _limpo(nome.group(1)), "partido": _limpo(partido.group(1)).strip("() ") if partido else "",
                       "licenciado": 0, "atual": 0, "foto": img.group(1) if img else "", "pagina": f"{SITE}/vereadores/{numero}"})
    df = pd.DataFrame(linhas)
    PASTA.mkdir(parents=True, exist_ok=True)
    df.to_csv(PASTA / "site_vereadores.csv", index=False)
    log(f"  Maceió: {int(df.atual.sum())} vereadores na página da Câmara ({int(df.licenciado.sum())} licenciados) e {int((df.atual == 0).sum())} suplentes fora dela")
    return df


def _tabela_folha(ano):
    """Planilha (HTML) da folha por lotação de um ano -> linhas (ano, mes, lotacao, pessoas, bruto, abono, eventuais)."""
    t = _pedir(f"{PORTAL}/relatorios/excel_folha.php", params={"lotacao": "", "mes": "", "ano": ano})
    linhas = []
    for tr in re.findall(r"<tr.*?</tr>", t, re.S):
        c = [_limpo(x) for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
        m = re.match(r"(\d{2}) / (\d{4})$", c[1]) if len(c) == 8 else None
        if not m:
            continue
        # descontos e líquido (colunas 6 e 7) não são guardados
        linhas.append({"ano": int(m.group(2)), "mes": int(m.group(1)), "lotacao": c[0], "pessoas": int(_valor(c[2])),
                       "bruto": _valor(c[3]), "abono": _valor(c[4]), "eventuais": _valor(c[5])})
    return linhas


def _linhas_pdf_folha(texto):
    """Texto do PDF da folha de uma lotação -> [(nome, cargo, remuneração, abono, eventuais)] e o total informado.
    Os descontos e o líquido (as duas últimas colunas) são descartados aqui mesmo."""
    saida, total, registros = [], None, None
    cab = None
    for l in texto.split("\n"):
        if "Servidor" in l and "Cargo" in l:
            cab = (l.index("Servidor"), l.index("Cargo"))
            continue
        m = re.match(r"\s*\d{6,}\s+(.*?)\s+(-?[\d.]+,\d\d)\s+(-?[\d.]+,\d\d)\s+(-?[\d.]+,\d\d)\s+(-?[\d.]+,\d\d)\s+(-?[\d.]+,\d\d)\s*$", l)
        if m:
            meio = m.group(1)
            partes = re.split(r"\s{2,}", meio.strip())
            if len(partes) >= 2:
                nome, cargo = partes[0], " ".join(partes[1:])
            elif cab:
                nome, cargo = l[cab[0]:cab[1]].strip(), l[cab[1]:l.index(m.group(2))].strip()
            else:
                nome, cargo = meio.strip(), ""
            saida.append((nome, cargo, _valor(m.group(2)), _valor(m.group(3)), _valor(m.group(4))))
            continue
        t = re.search(r"Registros:\s*(\d+)\s+TOTAIS:\s+([\d.]+,\d\d)", l)
        if t:
            registros, total = int(t.group(1)), _valor(t.group(2))
    return saida, total, registros


def folha():
    """Folha por lotação (todos os meses), bruto de cada vereador (PDF nominal) e cargos dos gabinetes no último mês."""
    ate = comum.ultimo_mes_fechado()
    recentes = comum.menos_meses(ate, REBAIXAR)
    PASTA.mkdir(parents=True, exist_ok=True)
    arq_l, arq_v, arq_n, arq_c = (PASTA / "folha_lotacoes.csv", PASTA / "folha_vereadores.csv", PASTA / "folha_nominal_meses.csv",
                                  PASTA / "cargos_gabinetes.csv")
    lotacoes = []
    for ano in range(INICIO // 100, ate // 100 + 1):
        lotacoes += _tabela_folha(ano)
    fl = pd.DataFrame(lotacoes, columns=["ano", "mes", "lotacao", "pessoas", "bruto", "abono", "eventuais"])
    if not len(fl):
        raise RuntimeError("a folha por lotação veio vazia")
    fl.to_csv(arq_l, index=False)
    log(f"  Maceió: folha por lotação, {len(fl)} linhas ({fl.lotacao.nunique()} lotações)")

    if not shutil.which("pdftotext"):
        log("  Maceió: sem o programa pdftotext; a folha nominal e os cargos ficam como estavam")
        return
    # folha nominal dos vereadores, mês a mês (o mês 13 é o 13º salário)
    fv = pd.read_csv(arq_v) if arq_v.exists() else pd.DataFrame(columns=["ano", "mes", "nome", "cargo", "remuneracao", "abono", "eventuais"])
    fn = pd.read_csv(arq_n) if arq_n.exists() else pd.DataFrame(columns=["ano", "mes", "registros", "total"])
    feitos = {int(a) * 100 + int(m) for a, m, r in zip(fn.ano, fn.mes, fn.registros) if r > 0}
    ver_meses = sorted({(int(a), int(m)) for a, m, l in zip(fl.ano, fl.mes, fl.lotacao) if l == "VEREADOR" and (a * 100 + min(m, 12)) <= ate})
    for a, m in ver_meses:
        am = a * 100 + m
        if am in feitos and a * 100 + min(m, 12) <= recentes:
            continue
        texto = _texto_pdf(f"{PORTAL}/relatorios/pdf_folha_lot.php", params={"lotacao": "VEREADOR", "mes": f"{m:02d}", "ano": a})
        linhas, total, registros = _linhas_pdf_folha(texto)
        soma = round(sum(x[2] for x in linhas), 2)
        if registros is None or len(linhas) != registros or (total is not None and abs(soma - total) > 0.05):
            log(f"  Maceió: folha nominal de {m:02d}/{a} não bateu ({len(linhas)} linhas, {registros} registros, {soma} x {total}); fica de fora")
            continue
        fv = _juntar(fv[(fv.ano * 100 + fv.mes) != am],
                     pd.DataFrame([{"ano": a, "mes": m, "nome": n, "cargo": c, "remuneracao": r, "abono": ab, "eventuais": ev}
                                   for n, c, r, ab, ev in linhas], columns=fv.columns))
        fn = _juntar(fn[(fn.ano * 100 + fn.mes) != am], pd.DataFrame([{"ano": a, "mes": m, "registros": registros, "total": total}]))
        fv.sort_values(["ano", "mes", "nome"]).to_csv(arq_v, index=False)
        fn.sort_values(["ano", "mes"]).to_csv(arq_n, index=False)
        if registros:
            log(f"  Maceió: folha nominal dos vereadores de {m:02d}/{a} ({registros} vereadores)")

    # cargos dos gabinetes no último mês fechado (só a contagem; os nomes não são guardados)
    mensais = fl[(fl.mes <= 12) & ((fl.ano * 100 + fl.mes) <= ate)]
    if not len(mensais):
        return
    am = int((mensais.ano * 100 + mensais.mes).max())
    a, m = divmod(am, 100)
    fc = pd.read_csv(arq_c) if arq_c.exists() else pd.DataFrame(columns=["ano", "mes", "lotacao", "cargo", "pessoas"])
    if len(fc) and int(fc.ano.iloc[0]) * 100 + int(fc.mes.iloc[0]) == am:
        return
    linhas_c = []
    gabinetes = sorted(l for l in set(mensais[(mensais.ano == a) & (mensais.mes == m)].lotacao) if _eh_gabinete(l))
    for lot in gabinetes:
        texto = _texto_pdf(f"{PORTAL}/relatorios/pdf_folha_lot.php", params={"lotacao": lot, "mes": f"{m:02d}", "ano": a})
        linhas, _, registros = _linhas_pdf_folha(texto)
        if registros is None or len(linhas) != registros:
            log(f"  Maceió: cargos de {lot} em {m:02d}/{a} não bateram ({len(linhas)} linhas, {registros} registros)")
            continue
        conta = {}
        for _, cargo, *_ in linhas:
            k = _cargo(cargo)
            conta[k] = conta.get(k, 0) + 1
        linhas_c += [{"ano": a, "mes": m, "lotacao": lot, "cargo": k, "pessoas": n} for k, n in conta.items()]
    if linhas_c:
        pd.DataFrame(linhas_c).to_csv(arq_c, index=False)
        log(f"  Maceió: cargos de {len(gabinetes)} gabinetes em {m:02d}/{a}")


def _eh_gabinete(lot):
    n = normalizar_nome(lot)
    return bool(re.match(r"^VEREADORA? \S", n)) or n.startswith("CEDIDOS - GABINETE")


# Cargos dos gabinetes. Um nome muito comprido às vezes cobre o começo do cargo no PDF ("…SESSORIA PARLAMENTAR"),
# por isso a busca é por um pedaço do nome do cargo.
_CARGOS = [(r"CHEF", "Chefe de gabinete"), (r"SESSOR", "Assessor parlamentar"), (r"T[EÉ]CNICO", "Técnico parlamentar"),
           (r"SSISTENTE", "Assistente parlamentar"), (r"SECRET[AÁ]RI", "Secretário parlamentar")]


def _cargo(c):
    c = re.sub(r"\s+[IVX]+$", "", re.sub(r"\s+", " ", c or "").strip())
    for padrao, nome in _CARGOS:
        if re.search(padrao, c, re.I):
            return nome
    return comum.titulo(c) if c else "Sem cargo informado"


def _mes_ref(ref):
    """"Dezembro / 2025 (3º Quadrimestre)" -> (2025, 12)."""
    m = re.match(r"\s*(\S+)\s*/\s*(\d{4})", ref or "")
    if not m or normalizar_nome(m.group(1)) not in MESES_NOME:
        return None
    return int(m.group(2)), MESES_NOME[normalizar_nome(m.group(1))]


def viap():
    """VIAP mês a mês por vereador: a tabela de cada vereador e ano (valor indenizado e o requerimento em PDF)."""
    ate = comum.ultimo_mes_fechado()
    ano_atual = ate // 100
    PASTA.mkdir(parents=True, exist_ok=True)
    # quem tem VIAP em cada ano: a lista paginada do portal (a mais recente primeiro)
    pares, pagina = set(), 1
    while pagina <= 50:
        t = _pedir(f"{PORTAL}/viap&pagina={pagina}")
        achados = {(int(v), int(a)) for v, a in re.findall(r"viap-detalhes&(?:amp;)?vereador=(\d+)&(?:amp;)?ano=(\d{4})", t)}
        pares |= {p for p in achados if p[1] >= INICIO // 100}
        if not achados or min(a for _, a in achados) < INICIO // 100:
            break
        pagina += 1
    nomes = {}
    t = _pedir(f"{PORTAL}/viapx")
    for v, n in re.findall(r'<option value="(\d+)"[^>]*>\s*(.*?)\s*</option>', t, re.S):
        nomes[int(v)] = _limpo(n)
    linhas = []
    for vid, ano in sorted(pares):
        t = _pedir(f"{PORTAL}/viap-detalhes&vereador={vid}&ano={ano}", arquivo=C / f"viap_{vid}_{ano}.html", dias=5 if ano >= ano_atual - 1 else None)
        for tr in re.findall(r"<tr>(.*?)</tr>", t, re.S):
            c = [_limpo(x) for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
            ref = _mes_ref(c[0]) if c else None
            if not ref or len(c) < 6:
                continue
            pdf = re.search(r"documentos/viap/([\w.-]+\.pdf)", tr)
            linhas.append({"vereador_id": vid, "vereador": nomes.get(vid, ""), "ano": ref[0], "mes": ref[1], "saldo_anterior": _valor(c[1]),
                           "gastos": _valor(c[2]), "glosadas": _valor(c[3]), "excesso": _valor(c[4]), "indenizado": _valor(c[5]),
                           "pdf": pdf.group(1) if pdf else ""})
    vi = pd.DataFrame(linhas, columns=["vereador_id", "vereador", "ano", "mes", "saldo_anterior", "gastos", "glosadas", "excesso", "indenizado", "pdf"])
    vi.sort_values(["vereador_id", "ano", "mes"]).to_csv(PASTA / "viap.csv", index=False)
    log(f"  Maceió: VIAP, {len(vi)} meses de {vi.vereador_id.nunique()} vereadores")


def coletar():
    lista_site()
    folha()
    viap()


# ---------------------------------------------------------------- montagem
def _codigo(nome, t):
    if t is not None:
        return int(t["sq"])
    return int(hashlib.md5(normalizar_nome(nome).encode()).hexdigest()[:10], 16)


_COMUNS = {"FILHO", "FILHA", "NETO", "NETTO", "JUNIOR", "SOBRINHO", "SILVA", "SANTOS", "OLIVEIRA", "COSTA", "SOUZA", "SOUSA", "LIMA",
           "PEREIRA", "FERREIRA", "BARBOSA", "MELO", "VEREADOR", "VEREADORA", "GABINETE", "CEDIDOS", "PASTOR", "DELEGADO", "COLETIVO"}


def _achar(nome, pessoas):
    """Código da pessoa por um nome (parlamentar, de urna ou completo, às vezes cortado): igual, compatível ou bem
    parecido; senão, uma palavra rara que só o nome parlamentar ou de urna de uma pessoa tem ("OLIVIA", "GALBA",
    "EMPREGO" em "EMPREGOS"). pessoas: {código: {"nomes": [...], "apelidos": [...]}}."""
    fora_par = re.sub(r"\(.*?\)", " ", nome or "").strip()
    if fora_par != (nome or "").strip():  # "Francisco Filho (Chico Filho)": o nome de fora; senão, o de dentro dos parênteses
        for parte in [fora_par] + re.findall(r"\((.*?)\)", nome):
            c = _achar(parte, pessoas)
            if c is not None:
                return c
        return None
    opcoes = [(n, cod) for cod, p in pessoas.items() for n in p["nomes"] + p["apelidos"] if n]
    k = comum.chave_nome(nome)
    for teste in (lambda n: comum.chave_nome(n) == k, lambda n: comum.compativel(k, n)):
        achados = {cod for n, cod in opcoes if teste(n)}
        if len(achados) == 1:
            return achados.pop()
        if achados:
            return None  # mais de uma pessoa: melhor não chutar
    c = comum.achar_parecido(nome, opcoes, 0.9)
    if c is not None:
        return c
    for w in (w for w in k.split() if len(w) >= 5 and w not in _COMUNS):
        achados = {cod for cod, p in pessoas.items() for n in p["apelidos"] for x in comum.chave_nome(n).split()
                   if x == w or (len(x) > len(w) and x.startswith(w))}
        if len(achados) == 1:
            return achados.pop()
    return None


def _dono(lot, pessoas):
    """Lotação do gabinete ("VEREADOR ALDO ROBERTO DA ROCHA LOUR", "CEDIDOS - GABINETE CHARLES HEBERT") -> código."""
    return _achar(re.sub(r"^(CEDIDOS - GABINETE|VEREADORA?)\s+", "", normalizar_nome(lot)), pessoas)


def _categorias(r, subsidio):
    """Linha da folha nominal -> [(ano, mês, categoria, valor)]. O mês 13 é o 13º (vai para dezembro); o que passa
    do subsídio no mês (acertos) e o abono vão para "outros pagamentos"."""
    a, m, rem = int(r.ano), int(r.mes), float(r.remuneracao)
    extra = float(r.abono) + float(r.eventuais)
    if m == 13:
        return [(a, 12, "decimo_terceiro", rem + extra)]
    saida = [(a, m, "salario", rem)] if rem <= subsidio * 1.01 else [(a, m, "salario", subsidio), (a, m, "outros_rendimentos", rem - subsidio)]
    return saida + ([(a, m, "outros_rendimentos", extra)] if extra else [])


def montar(tipos):
    if not (PASTA / "folha_lotacoes.csv").exists():
        return None
    ate = comum.ultimo_mes_fechado()
    fl = pd.read_csv(PASTA / "folha_lotacoes.csv")
    fv = pd.read_csv(PASTA / "folha_vereadores.csv") if (PASTA / "folha_vereadores.csv").exists() else pd.DataFrame(columns=["ano", "mes", "nome", "cargo", "remuneracao", "abono", "eventuais"])
    fn = pd.read_csv(PASTA / "folha_nominal_meses.csv") if (PASTA / "folha_nominal_meses.csv").exists() else pd.DataFrame(columns=["ano", "mes", "registros", "total"])
    fc = pd.read_csv(PASTA / "cargos_gabinetes.csv") if (PASTA / "cargos_gabinetes.csv").exists() else pd.DataFrame(columns=["ano", "mes", "lotacao", "cargo", "pessoas"])
    site = pd.read_csv(PASTA / "site_vereadores.csv").fillna("") if (PASTA / "site_vereadores.csv").exists() else pd.DataFrame(columns=["numero", "nome", "partido", "licenciado", "atual", "foto", "pagina"])
    vi = pd.read_csv(PASTA / "viap.csv").fillna({"pdf": "", "vereador": ""}) if (PASTA / "viap.csv").exists() else None
    tse = comum.candidatos_tse("AL", "Maceió")
    tse_civil = {normalizar_nome(n): r for n, r in zip(tse.nome, tse.to_dict("records"))}

    # subsídio: o valor mais comum na folha nominal dos vereadores (é o de todos, inclusive do presidente)
    mensal = fv[fv.mes <= 12]
    subsidio = round(float(mensal.remuneracao.round(2).mode().iloc[0]), 2) if len(mensal) else 18991.68
    ultimo_folha = int((fl[fl.mes <= 12].ano * 100 + fl[fl.mes <= 12].mes).max())
    ultimo = min(ate, ultimo_folha)

    # pessoas: os eleitos de 2024 e quem aparece na folha nominal como vereador (suplentes que assumiram)
    pessoas = {}

    def nova(civil, t):
        cod = _codigo(civil, t)
        if cod not in pessoas:
            pessoas[cod] = {"civil": civil, "tse": t, "nomes": [civil] + ([t["nome"]] if t is not None else []),
                            "apelidos": [t["nome_urna"]] if t is not None else []}
        return cod
    for t in tse[tse.situacao == "eleito"].to_dict("records"):
        nova(t["nome"], t)
    cod_folha = {}
    for nome in sorted(set(fv.nome)):
        t = tse_civil.get(normalizar_nome(nome))
        if t is None:
            achados = [r for r in tse.to_dict("records") if comum.compativel(nome, r["nome"]) or comum.compativel(r["nome"], nome)]
            t = achados[0] if len(achados) == 1 else None
        if t is None:
            i = comum.achar_parecido(nome, [(n, i) for i, n in enumerate(tse.nome)], 0.9)
            t = tse.iloc[i].to_dict() if i is not None else None
        cod_folha[nome] = nova(nome, t)
    sem = [n for n, c in cod_folha.items() if pessoas[c]["tse"] is None]
    if sem:
        log(f"  Maceió: na folha como vereador e sem correspondência no TSE: {', '.join(sem)}")
    # nome parlamentar, partido, foto e página: o site da Câmara
    do_site = {}
    for r in site.to_dict("records"):
        c = _achar(r["nome"], pessoas)
        if c is None:
            log(f"  Maceió: {r['nome']} (site da Câmara) não achado na folha nem no TSE")
            continue
        if c not in do_site or (r["atual"] and not do_site[c]["atual"]):
            do_site[c] = r
    for c, r in do_site.items():
        pessoas[c]["apelidos"].append(r["nome"])

    # no cargo em cada mês: a folha nominal (pago como vereador na folha mensal); nos meses sem nomes (até set/2025),
    # quem tinha gabinete com servidores naquele mês, conferido com o número de vereadores pagos
    gabs = fl[fl.lotacao.map(_eh_gabinete)]
    lot_cod = {l: _dono(l, pessoas) for l in set(gabs.lotacao) | set(fc.lotacao)}
    gab = gabs[gabs.mes <= 12]
    com_nome = {int(a) * 100 + int(m) for a, m, r in zip(fn.ano, fn.mes, fn.registros) if r > 0 and m <= 12}
    gab_mes = {}
    for l, a, m, n in zip(gab.lotacao, gab.ano, gab.mes, gab.pessoas):
        if n > 0 and lot_cod.get(l) is not None:
            gab_mes.setdefault(lot_cod[l], set()).add(int(a) * 100 + int(m))
    # um pagamento pequeno num mês em que o vereador já não tinha gabinete é acerto de quem saiu (férias, dias do
    # mês anterior), não mês no cargo
    no_mes, acertos = {}, []
    for r in mensal.itertuples():
        am, rem, c = int(r.ano) * 100 + int(r.mes), float(r.remuneracao), cod_folha[r.nome]
        if rem >= subsidio / 2 or (rem > 0 and am in gab_mes.get(c, set())):
            no_mes.setdefault(c, set()).add(am)
        elif rem > 0:
            acertos.append(f"{r.nome} {am % 100:02d}/{am // 100}")
    if acertos:
        log(f"  Maceió: pagamentos pequenos fora dos meses com gabinete (contam no salário, não como mês no cargo): {', '.join(acertos)}")
    validos = {c for c, p in pessoas.items() if p["tse"] is not None and p["tse"]["situacao"] == "eleito"} | set(cod_folha.values())
    avisos = []
    for (a, m), g in fl[(fl.lotacao == "VEREADOR") & (fl.mes <= 12)].groupby(["ano", "mes"]):
        am = int(a) * 100 + int(m)
        if am in com_nome or am > ultimo:
            continue
        quem = {lot_cod[l] for l in gab[(gab.ano == a) & (gab.mes == m) & (gab.pessoas > 0)].lotacao if lot_cod.get(l) in validos}
        pagos, bruto = int(g.pessoas.iloc[0]), float(g.bruto.iloc[0])
        if len(quem) != pagos or abs(bruto - pagos * subsidio) > 1:
            avisos.append(f"{int(m):02d}/{int(a)}: {len(quem)} gabinetes e {pagos} vereadores pagos (R$ {bruto:,.2f})")
        for c in quem:
            no_mes.setdefault(c, set()).add(am)
    if avisos:
        log(f"  Maceió: meses sem folha nominal que não batem: {'; '.join(avisos)}")

    # salário: a folha nominal; nos meses sem nomes, o subsídio (a folha da lotação VEREADOR confere: pagos x subsídio)
    ganha_l = []
    for r in fv.itertuples():
        for a, m, cat, v in _categorias(r, subsidio):
            if v:
                ganha_l.append({"ano": a, "mes": m, "codigo": cod_folha[r.nome], "categoria": cat, "valor": round(v, 2)})
    for c, ms in no_mes.items():
        for am in ms:
            if am not in com_nome:
                ganha_l.append({"ano": am // 100, "mes": am % 100, "codigo": c, "categoria": "salario", "valor": subsidio})
    ganha = pd.DataFrame(ganha_l, columns=["ano", "mes", "codigo", "categoria", "valor"])
    linhas_m = []
    for c, ms in no_mes.items():
        for de, fim in comum.periodos_de_meses({am for am in ms if am <= ultimo}, ultimo):
            linhas_m.append({"codigo": c, "inicio": de, "fim": fim})
    mandatos = pd.DataFrame(linhas_m, columns=["codigo", "inicio", "fim"])

    # vereadores
    linhas_v, fotos = [], []
    for c, p in pessoas.items():
        if c not in no_mes:
            continue
        t, s = p["tse"], do_site.get(c)
        nome = s["nome"] if s is not None else comum.titulo(t["nome_urna"] if t is not None else p["civil"])
        linhas_v.append({"codigo": c, "nome": nome, "nome_civil": comum.titulo(t["nome"] if t is not None else p["civil"]),
                         "partido": _partido((s["partido"] if s is not None and s["partido"] else "") or (t["partido"] if t is not None else "")),
                         "genero": t["genero"] if t is not None else "", "eleito": t["situacao"] if t is not None else "",
                         "pagina": s["pagina"] if s is not None else CFG["pagina"]})
        if s is not None and s["foto"] and "/galeria/vereadores/" in s["foto"]:
            fotos.append((c, s["foto"]))
    ver = pd.DataFrame(linhas_v)
    comum.fotos(COD, fotos)

    # equipe: servidores e bruto de cada gabinete por mês (o 13º dos servidores entra em dezembro), só nos meses em
    # que o dono do gabinete estava no cargo (fora deles, são acertos com quem saiu)
    sem_g = sorted(l for l, c in lot_cod.items() if c is None)
    if sem_g:
        log(f"  Maceió: gabinetes sem vereador identificado: {', '.join(sem_g)}")
    eq = gabs.assign(codigo=gabs.lotacao.map(lot_cod))
    eq = eq[eq.codigo.notna()]
    eq = eq.assign(custo=eq.bruto + eq.abono + eq.eventuais, pessoas=eq.pessoas.where(eq.mes <= 12, 0), mes=eq.mes.clip(upper=12))
    fora = eq[[int(a) * 100 + int(m) not in no_mes.get(int(c), set()) for a, m, c in zip(eq.ano, eq.mes, eq.codigo)]]
    if len(fora):
        log(f"  Maceió: {len(fora)} linhas de gabinete fora dos meses no cargo do vereador (R$ {fora.custo.sum():,.2f}), não contadas")
    eq = eq.drop(fora.index)
    equipe = eq.groupby(["ano", "mes", "codigo"])[["pessoas", "custo"]].sum().reset_index().astype({"codigo": int})
    cargos = fc.assign(codigo=fc.lotacao.map(lot_cod), cargo=fc.cargo.map(_cargo))
    cargos = cargos[cargos.codigo.notna()].groupby(["codigo", "cargo"]).pessoas.sum().reset_index().astype({"codigo": int})
    ultimo_eq = f"{int(fc.mes.iloc[0]):02d}/{int(fc.ano.iloc[0])}" if len(fc) else ""

    # VIAP
    despesas, notas, verba_fora = None, [], []
    if vi is not None and len(vi):
        ids = {int(vid): _achar(g.vereador.iloc[0], pessoas) for vid, g in vi.groupby("vereador_id")}
        sem_v = sorted({n for v, n in zip(vi.vereador_id, vi.vereador) if ids.get(int(v)) is None})
        if sem_v:
            log(f"  Maceió: na VIAP e sem vereador identificado: {', '.join(sem_v)}")
        despesas = pd.DataFrame([{"ano": int(r.ano), "mes": int(r.mes), "codigo": ids[int(r.vereador_id)], "tipo": "Verba indenizatória",
                                  "fornecedor": "", "cnpj_cpf": "", "valor": float(r.indenizado)}
                                 for r in vi.itertuples() if ids.get(int(r.vereador_id)) is not None and r.indenizado],
                                columns=["ano", "mes", "codigo", "tipo", "fornecedor", "cnpj_cpf", "valor"])
        # ano em que a Câmara não publicou a VIAP de todos os meses de todos os vereadores: fica de fora para todos,
        # para não comparar quem tem a verba contada com quem não tem
        publicados = {(int(ids[int(v)]), int(a) * 100 + int(m)) for v, a, m in zip(vi.vereador_id, vi.ano, vi.mes) if ids.get(int(v)) is not None}
        nomes_v = dict(zip(ver.codigo, ver.nome))
        for ano in range(INICIO // 100, ultimo // 100 + 1):
            faltam = {}
            for c, ms in no_mes.items():
                for am in ms:
                    if am // 100 == ano and am <= ultimo and (c, am) not in publicados:
                        faltam.setdefault(c, []).append(am)
            if not faltam:
                continue
            verba_fora.append(str(ano))
            despesas = despesas[despesas.ano != ano]
            no_ano = {c for c, ms in no_mes.items() if any(am // 100 == ano and am <= ultimo for am in ms)}
            if not any(a == ano for a in vi.ano):
                notas.append(f"A Câmara ainda não publicou a VIAP de {ano}.")
            else:
                completos = len(no_ano) - len(faltam)
                quem = sorted(nomes_v.get(c, str(c)) for c in faltam)
                notas.append(f"A VIAP de {ano} está publicada completa para {completos} dos {len(no_ano)} vereadores que passaram pela Câmara; "
                             f"para os outros {len(faltam)} ({', '.join(quem)}), faltam meses. Para não comparar vereadores com e sem a verba, "
                             f"a VIAP de {ano} fica de fora para todos até a Câmara completar a publicação.")
        if verba_fora:
            log(f"  Maceió: VIAP fora do site em {', '.join(verba_fora)} (publicação incompleta)")

    ultimo_nominal = max(com_nome) if com_nome else None
    salario_nota = (f"Valores brutos da folha de pagamento da Câmara, com o 13º e o terço de férias. O subsídio é de {_br(subsidio)} por mês, "
                    "igual para todos, inclusive o presidente.")
    if com_nome:
        primeiro = min(com_nome)
        salario_nota += (f" A folha com o nome de cada vereador só é publicada desde {primeiro % 100:02d}/{primeiro // 100}; antes disso, cada vereador "
                         f"aparece com o subsídio, porque a folha da lotação dos vereadores mostra, nesses meses, o subsídio exato para cada um dos pagos.")
    notas = ["Quem estava no cargo em cada mês vem da folha de pagamento da Câmara (os vereadores pagos no mês; antes de a folha trazer "
             "os nomes, os gabinetes com servidores), por isso pode diferir da página de vereadores do site da Câmara."] + notas
    cfg = dict(CFG, ultimo_mes=ultimo, equipe_em=ultimo_eq, subsidio=[[INICIO, subsidio]], salario_nota=salario_nota,
               notas=notas, verba_fora=verba_fora)
    if ultimo_nominal:
        log(f"  Maceió: folha nominal até {ultimo_nominal % 100:02d}/{ultimo_nominal // 100}")
    return comum.montar(cfg, tipos, ver, mandatos, ganha=ganha, despesas=despesas, equipe=equipe, cargos=cargos)


def _partido(p):
    """"PC do B" (TSE) -> "PCdoB", como nas outras cidades."""
    return "PCdoB" if normalizar_nome(p).replace(" ", "") == "PCDOB" else p


def _br(v):
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
