"""Câmara Municipal de Cuiabá: vereador por vereador.

Fontes (sem cadastro; abrem de fora do Brasil, conferido em 08/10/2026; o robots.txt do portal da transparência
(gp.srv.br) tem "Disallow: /", que é uma convenção e não lei: lemos com pausa, ver README, "Robôs e robots.txt"):
- Folha mensal, nome por nome: o Portal da Transparência da Câmara, "Folha de pagamento"
  (https://www.gp.srv.br/transparencia_cuiabacm/servlet/folha_pagamento_v2?1). A lista das competências sai dessa página;
  a folha de cada mês, do relatório em PDF que o botão "Visualizar em PDF" abre (arrelacao_folhapag, com o cargo
  VEREADOR): nome (cortado em 38 letras), cargo, a descrição da folha (mensal, 13º, gratificação, rescisão, a linha
  informativa da verba indenizatória...) e o total de proventos. Os descontos e o líquido não são guardados.
- Verba indenizatória: até jan/2026, as linhas informativas da própria folha ("FOLHA INFORMATIVA ESOCIAL (VI + SUP.)");
  a partir de 2026, os arquivos mensais da página "Verba indenizatória - regulamentação e valores"
  (https://www.gp.srv.br/transparencia_cuiabacm/servlet/informativo?verba_regulamentacao,1), um PDF por mês com o nome
  parlamentar e o valor. Em 08/10/2026 faltavam fev e abr/2026, e o arquivo de "09/2026" era o mesmo de 08/2026 (o texto
  diz "mês 08/2026"): vale o mês escrito no arquivo.
- Regra da verba: Lei 6.910/2023 (com a redação da Lei 6.919/2023): 75% da remuneração mensal, pago a cada vereador em
  efetivo exercício, com prestação de contas por relatório de atividades.
- Quem está no cargo em cada mês: quem tem na folha do mês a linha mensal (ou de suplente) ou a verba indenizatória; a
  linha "SUBSIDIO VEREADORES AFASTADOS" é de quem está afastado (continua recebendo, mas não conta como no cargo).
- Nome parlamentar, partido e foto: a lista de vereadores do sistema legislativo da Câmara,
  https://legislativo.camaracuiaba.mt.gov.br/api/Vereador/?v=2&qtd=100 (página
  https://legislativo.camaracuiaba.mt.gov.br/parlamentares.aspx). Ela marca 28 "ativos" para 27 cadeiras: não é usada
  para dizer quem está em exercício.
- Subsídio: R$ 24.754,79 em jan/2025 e R$ 26.080,98 depois (75% do subsídio de deputado estadual; o valor das linhas de
  suplente e de afastado na folha).
- Nome civil, nome de urna, partido (quando a lista da Câmara não tem) e gênero: TSE (eleição de 2024).

Plano de queda (fonte que só tem um caminho; escrito em 08/10/2026, também em dados/referencia/plano-de-queda.json):
- Folha (relatório em PDF) fora do ar ou com outro formato: o robô mantém o que já gravou (gravação segura) e o site fica
  até o último mês lido; sem reserva no Tribunal de Contas (o TCE-MT não tem robô aqui).
- Arquivos da verba fora do ar: a verba fica até o último mês lido (verba_ate) e os meses sem arquivo, "não publicados".
- Conserto só se couber em cerca de 1 hora; passou disso, a fonte vai para onde.CONGELADAS.
"""
import re
import subprocess
import tempfile
from urllib.parse import quote

import pandas as pd

from ..config import CACHE, DADOS
from ..util import TempoEsgotado, _sessao, cache_valido, dormir, gravar_csv, log, normalizar_nome, verificar_prazo
from ..assembleias import comum as acomum
from . import comum

COD = 5103403
INICIO = 202501
GP = "https://www.gp.srv.br/transparencia_cuiabacm/servlet"
FOLHA_PAGINA = f"{GP}/folha_pagamento_v2?1"
RELATORIO = f"{GP}/arrelacao_folhapag?"
VERBA_PAGINA = f"{GP}/informativo?verba_regulamentacao,1"
ARQUIVO = f"{GP}/apdownload_manutencao?"
LEI_VERBA = ("https://legislativo.camaracuiaba.mt.gov.br/Arquivo/Documents/legislacao/html/L69102023.html"
             "?identificador=310032003800360038003A004C00")
SPL = "https://legislativo.camaracuiaba.mt.gov.br"
LISTA_API = f"{SPL}/api/Vereador/?v=2&qtd=100"
LISTA = f"{SPL}/parlamentares.aspx"
PASTA = DADOS / "municipios" / "cuiaba"
C = CACHE / "cmcuiaba"
REBAIXAR = 3  # os últimos meses da folha são baixados de novo (a Câmara ainda pode acertar)
VAGAS = 27
SUBSIDIO = [[202501, 24754.79], [202502, 26080.98]]
CFG = {
    "cod": COD, "n": "Cuiabá", "uf": "MT", "casa": "Câmara Municipal de Cuiabá", "vagas": VAGAS, "inicio": INICIO,
    "subsidio": SUBSIDIO,
    "salario_nota": ("Valor do mês na folha da Câmara. Até o subsídio (R$ 26.080,98 desde fev/2025; R$ 24.754,79 em jan/2025) é "
                     "salário; o que a folha paga além dele aparece em outros pagamentos: a folha mensal da maioria dos "
                     "vereadores é de R$ 38.339,04 e, em alguns meses, separa uma gratificação de R$ 9.128,34 (descrita como "
                     "gratificação de vereador ou de desempenho em comissões); também as rescisões e as diferenças. O 13º vem à "
                     "parte."),
    "verba_nome": "Verba indenizatória", "verba_mes": {},
    "verba_regra": ("Valor fixo por mês, pago a cada vereador em exercício: 75% da remuneração mensal (Lei 6.910/2023, com a "
                    "redação da Lei 6.919/2023), para ressarcir despesas da atividade parlamentar. A prestação de contas é por "
                    "relatório de atividades."),
    "verba_notas": ["A Câmara publica um valor por vereador e mês (até jan/2026 na própria folha, como linha informativa; "
                    "depois, num arquivo por mês), sem as notas: por isso não há tipo de gasto nem fornecedor aqui."],
    "equipe_nota": None,
    "credito_foto": "Câmara Municipal de Cuiabá", "pagina": LISTA,
    "notas": ["Quem estava no cargo em cada mês: quem aparece na folha da Câmara no mês com a folha mensal ou com a verba "
              "indenizatória. Quem a folha marca como afastado continua recebendo o subsídio, mas não conta como no cargo.",
              "A Câmara não publica a equipe de cada gabinete."],
    "fontes": {"folha": FOLHA_PAGINA, "verba": VERBA_PAGINA, "verba_lei": LEI_VERBA, "lista": LISTA},
}
COLUNAS_FOLHA = ["ano", "mes", "nome", "descricao", "proventos"]
COLUNAS_VERBA = ["ano", "mes", "nome", "valor", "fonte"]
_LINHA = re.compile(r"^\s*(?P<nome>\S.*?)\s+VEREADOR\s+(?P<desc>.*?)\s*(?P<prov>-?[\d.]+,\d{2})\s+(?P<desc2>-?[\d.]+,\d{2})"
                    r"\s+(?P<liq>-?[\d.]+,\d{2})\s*$")


def _valor(t):
    t = str(t or "").replace(".", "").replace(",", ".")
    try:
        return round(float(t), 2)
    except ValueError:
        return 0.0


def _baixar(url, arquivo=None, dias=None):
    """Conteúdo (bytes) da resposta, com novas tentativas; guarda no cache (arquivo) e usa o cache se ainda vale."""
    if arquivo is not None and cache_valido(arquivo, dias):
        return arquivo.read_bytes()
    verificar_prazo()
    for tentativa in range(3):
        try:
            r = _sessao().get(url, timeout=120)
            r.raise_for_status()
            conteudo = r.content
            break
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 2:
                raise
            dormir(10 + 10 * tentativa)
    if arquivo is not None:
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_bytes(conteudo)
    return conteudo


def _texto_pdf(conteudo):
    """Texto do PDF (pdftotext -layout, do pacote poppler)."""
    if not conteudo.startswith(b"%PDF"):
        raise RuntimeError("a resposta não é um PDF")
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(conteudo)
        f.flush()
        return subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, text=True, check=True).stdout


# ---------------------------------------------------------------- coleta
def competencias():
    """{AAAAMM: código da competência} da página da folha (o select de competências)."""
    t = _baixar(FOLHA_PAGINA, C / "folha_pagina.html", 1).decode("utf-8", "replace")
    i = t.find('id="vCOMPETENCIA_ID"')
    saida = {}
    for cid, m, a in re.findall(r'<option[^>]*value="(\d+)"[^>]*>\s*(\d{2})/(\d{4})', t[i:i + 30000] if i >= 0 else ""):
        saida.setdefault(int(a) * 100 + int(m), cid)
    if not saida:
        raise RuntimeError("a página da folha não trouxe a lista de competências")
    return saida


def _folha_mes(am, cid, dias):
    """Linhas dos vereadores no relatório da folha de um mês (vazio se o mês ainda não tem folha)."""
    params = [cid, "", "VEREADOR", "", "", "", "0", "1", "Não"]
    texto = _texto_pdf(_baixar(RELATORIO + ",".join(quote(p) for p in params), C / f"folha_{am}.pdf", dias))
    saida = []
    for linha in texto.splitlines():
        m = _LINHA.match(linha)
        if not m:
            continue
        saida.append({"ano": am // 100, "mes": am % 100, "nome": " ".join(m.group("nome").split()),
                      "descricao": " ".join(m.group("desc").split()), "proventos": _valor(m.group("prov"))})
    return saida


def folha():
    """Folha dos vereadores, mês a mês. Os meses que já estão em dados/municipios/cuiaba/ não são baixados de novo (só os
    REBAIXAR últimos)."""
    ate = comum.ultimo_mes_fechado()
    recentes = comum.menos_meses(ate, REBAIXAR)
    comp = competencias()
    arq = PASTA / "folha.csv"
    velha = pd.read_csv(arq) if arq.exists() else pd.DataFrame(columns=COLUNAS_FOLHA)
    feitos = set(velha.ano * 100 + velha.mes) if len(velha) else set()
    linhas = []
    for a, m in comum.meses(INICIO, ate):
        am = a * 100 + m
        if am in feitos and am <= recentes:
            linhas += velha[(velha.ano * 100 + velha.mes) == am].to_dict("records")
            continue
        novas = _folha_mes(am, comp[am], 5 if am > recentes else None) if am in comp else []
        if not novas and am in feitos:  # o mês sumiu da consulta: fica o que estava gravado
            linhas += velha[(velha.ano * 100 + velha.mes) == am].to_dict("records")
            continue
        linhas += novas
    df = pd.DataFrame(linhas, columns=COLUNAS_FOLHA)
    PASTA.mkdir(parents=True, exist_ok=True)
    gravar_csv(df.sort_values(["ano", "mes", "nome", "descricao"], kind="stable"), arq)
    ult = int((df.ano * 100 + df.mes).max()) if len(df) else None
    log(f"  Cuiabá: folha com {len(df)} linhas de vereadores, até {ult}")


def verba():
    """Os arquivos mensais da verba indenizatória (2026). Cada arquivo diz o mês ("Valores pagos no mês 08/2026"); um
    arquivo repetido (o de "09/2026" era o de 08/2026) vale para o mês escrito nele."""
    t = _baixar(VERBA_PAGINA, C / "verba_pagina.html", 1).decode("utf-8", "replace")
    ids = []
    for i in re.findall(r"apdownload_manutencao\?(\d+),41", t):
        if i not in ids:
            ids.append(i)
    linhas, meses_lidos = [], set()
    for i in ids:
        url = f"{ARQUIVO}{i},41"
        try:
            texto = _texto_pdf(_baixar(url, C / f"verba_{i}.pdf", 30))
        except TempoEsgotado:
            raise
        except Exception as e:  # noqa: BLE001 — um arquivo com problema não derruba os outros
            log(f"  Cuiabá: arquivo da verba {i} não lido ({e})")
            continue
        mes = re.search(r"pagos no m[eê]s\s+(\d{2})/(\d{4})", texto)
        if not mes:  # a lei, ou a lista sem mês
            continue
        am = int(mes.group(2)) * 100 + int(mes.group(1))
        if am in meses_lidos or am < INICIO:
            continue
        meses_lidos.add(am)
        for l in texto.splitlines():
            m = re.match(r"^\s*(\S.*?)\s+R\$\s*([\d.]+,\d{2})\s*$", l)
            if m:
                nome = re.sub(r"\s*[–-]\s*Presidente.*$", "", m.group(1)).strip()
                nome = re.sub(r"\s*\([^)]*\)\s*$", "", nome).strip()
                linhas.append({"ano": am // 100, "mes": am % 100, "nome": nome, "valor": _valor(m.group(2)), "fonte": url})
    df = pd.DataFrame(linhas, columns=COLUNAS_VERBA)
    if not len(df):
        log("  Cuiabá: nenhum arquivo de verba lido; fica o que estava gravado")
        return
    PASTA.mkdir(parents=True, exist_ok=True)
    gravar_csv(df.sort_values(["ano", "mes", "nome"], kind="stable"), PASTA / "verba.csv")
    log(f"  Cuiabá: verba de {len(meses_lidos)} meses em arquivo ({', '.join(f'{m % 100:02d}/{m // 100}' for m in sorted(meses_lidos))})")


def lista():
    """Nome parlamentar, nome civil (quando a Câmara põe), partido e foto (a lista do sistema legislativo da Câmara)."""
    import json
    d = json.loads(_baixar(LISTA_API).decode("utf-8"))
    linhas = []
    for x in d.get("dados") or []:
        limpo = lambda s: " ".join(re.sub(r"\(\s*C[âa]mara Digital\s*\)", "", str(s or ""), flags=re.I).split()).strip(" .")
        linhas.append({"id": x.get("ID"), "nome": limpo(x.get("nome_parlamentar")), "nome_civil": limpo(x.get("nome")),
                       "partido": x.get("partido_sigla") or "", "situacao": x.get("situacao") or "", "foto": x.get("foto") or "",
                       "pagina": f"{SPL}/spl/parlamentar.aspx?id={x.get('ID')}" if x.get("ID") else ""})
    df = pd.DataFrame(linhas, columns=["id", "nome", "nome_civil", "partido", "situacao", "foto", "pagina"])
    if not 0.8 * VAGAS <= len(df) <= 2 * VAGAS:
        log(f"  Cuiabá: a lista de vereadores veio com {len(df)} nomes; fica a que estava gravada")
        return
    PASTA.mkdir(parents=True, exist_ok=True)
    gravar_csv(df, PASTA / "site_vereadores.csv")
    log(f"  Cuiabá: {len(df)} vereadores na lista da Câmara")


def coletar():
    lista()
    folha()
    verba()


# ---------------------------------------------------------------- montagem
def _reais(v):
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _subsidio(am):
    v = 0.0
    for de, valor in SUBSIDIO:
        if am >= de:
            v = valor
    return v


def _tipo(descricao):
    """O que é cada linha da folha: verba (a linha informativa da verba indenizatória), decimo_terceiro, auxilios,
    outros_rendimentos (gratificação, diferenças, rescisão) ou base (folha mensal, subsídio de afastado, complementar)."""
    d = normalizar_nome(descricao)
    if "INFORMATIVA" in d or "INDENIZ" in d:
        return "verba"
    if "13" in d:
        return "decimo_terceiro"
    if "AUXILIO" in d:
        return "auxilios"
    if "RESCIS" in d or "GRATIFIC" in d or "DIFEREN" in d:
        return "outros_rendimentos"
    return "base"


def montar(tipos):
    arq = PASTA / "folha.csv"
    if not arq.exists():
        return None
    fol = pd.read_csv(arq).fillna({"descricao": ""})
    if not len(fol):
        return None
    vb = pd.read_csv(PASTA / "verba.csv") if (PASTA / "verba.csv").exists() else pd.DataFrame(columns=COLUNAS_VERBA)
    site = (pd.read_csv(PASTA / "site_vereadores.csv").fillna("") if (PASTA / "site_vereadores.csv").exists()
            else pd.DataFrame(columns=["id", "nome", "nome_civil", "partido", "situacao", "foto", "pagina"]))
    tse = comum.candidatos_tse("MT", "Cuiabá")
    por_civil = [(n, i) for i, n in enumerate(tse.nome)] if len(tse) else []
    por_urna = [(n, i) for i, n in enumerate(tse.nome_urna)] if len(tse) else []

    # quem é quem: o nome civil da folha (cortado em 38 letras) casa com o TSE; o código é o SQ da candidatura
    codigos, info = {}, {}
    for nome in sorted(set(fol.nome)):
        i = comum.achar_parecido(nome, por_civil, 0.9) if por_civil else None
        t = tse.iloc[i].to_dict() if i is not None else None
        cod = int(t["sq"]) if t else acomum.codigo_de(nome, None)
        codigos[normalizar_nome(nome)] = cod
        info.setdefault(cod, {"t": t, "nome": nome})
    fol["codigo"] = fol.nome.map(lambda n: codigos[normalizar_nome(n)])
    sem_tse = sorted({v["nome"] for v in info.values() if v["t"] is None})
    if sem_tse:
        log(f"  Cuiabá: sem candidatura no TSE de 2024: {', '.join(sem_tse)}")

    # nome parlamentar (arquivos da verba e lista da Câmara) -> código: pelo nome de urna do TSE, e depois pelo nome civil
    # ("Tenente-Coronel Dias" no arquivo da verba é "T. CORONEL DIAS" no TSE)
    def por_parlamentar(nome, civil=""):
        nome = re.sub(r"(?i)\bTenente[- ]Coronel\b", "T. Coronel", nome)
        i = comum.achar_parecido(nome, por_urna, 0.88) if por_urna else None
        if i is not None and int(tse.iloc[i]["sq"]) in info:
            return int(tse.iloc[i]["sq"])
        opcoes = [(v["nome"], c) for c, v in info.items()] + [(v["t"]["nome_urna"], c) for c, v in info.items() if v["t"]]
        return comum.achar_parecido(civil, opcoes, 0.88) if civil else comum.achar_parecido(nome, opcoes, 0.88)
    vb_cod = {n: por_parlamentar(n) for n in sorted(set(vb.nome))}
    faltam = [n for n, c in vb_cod.items() if c is None]
    if faltam:
        log(f"  Cuiabá: na verba e não na folha: {', '.join(faltam)}")
    vb = vb.assign(codigo=vb.nome.map(vb_cod)).dropna(subset=["codigo"])
    # nome parlamentar do arquivo da verba mais recente, para quem não está na lista da Câmara (suplente que assumiu)
    nome_vb = {int(c): g.sort_values(["ano", "mes"]).nome.iloc[-1] for c, g in vb.groupby("codigo")}
    site_cod = {}
    for r in site.itertuples():
        c = por_parlamentar(r.nome, r.nome_civil if r.nome_civil and r.nome_civil != r.nome else "")
        if c is not None:
            site_cod.setdefault(c, r)

    fol["tipo"] = fol.descricao.map(_tipo)
    fol["am"] = fol.ano * 100 + fol.mes
    # o último mês: o último com a folha mensal de quase todos (a folha do mês corrente pode vir vazia)
    base_por_mes = fol[fol.tipo == "base"].groupby("am").codigo.nunique()
    ultimo = int(base_por_mes[base_por_mes >= 0.8 * VAGAS].index.max())
    ate = min(comum.ultimo_mes_fechado(), ultimo)

    # no cargo no mês: folha mensal (não de afastado) ou verba indenizatória (paga só a quem está em exercício)
    ativo = fol[((fol.tipo == "base") & ~fol.descricao.str.upper().str.contains("AFASTAD")) | (fol.tipo == "verba")]
    meses_no_cargo = {c: set(g.am) for c, g in ativo.groupby("codigo")}
    for c, g in vb.groupby("codigo"):
        meses_no_cargo.setdefault(int(c), set()).update(g.ano * 100 + g.mes)

    ver, mandatos, fotos = [], [], []
    for c in sorted(set(fol.codigo)):
        v, s = info[c], site_cod.get(c)
        t = v["t"]
        nome = (s.nome if s is not None and s.nome else nome_vb.get(c)
                or (comum.titulo(t["nome_urna"]) if t else comum.titulo(v["nome"])))
        if s is not None and s.foto:
            fotos.append((c, s.foto))
        ver.append({"codigo": c, "nome": nome, "nome_civil": comum.titulo(t["nome"]) if t else comum.titulo(v["nome"]),
                    "partido": (t["partido"] if t else "") or (s.partido if s is not None else ""),
                    "genero": t["genero"] if t else "", "eleito": t["situacao"] if t else "",
                    "pagina": (s.pagina if s is not None and s.pagina else "") or LISTA})
        for i, f in comum.periodos_de_meses([m for m in meses_no_cargo.get(c, set()) if m <= ultimo], ultimo):
            mandatos.append({"codigo": c, "inicio": i, "fim": f})
    comum.fotos(COD, fotos)

    # dinheiro: por pessoa e mês, a parte "base" vai até o subsídio como salário, e o resto vai para outros pagamentos
    linhas = []
    pag = fol[fol.tipo != "verba"]
    for (c, am), g in pag.groupby(["codigo", "am"]):
        a, m = divmod(int(am), 100)
        base = float(g[g.tipo == "base"].proventos.sum())
        sub = _subsidio(am)
        if base:
            sal = min(base, sub) if base > 0 else base
            linhas.append((a, m, c, "salario", round(sal, 2)))
            if base - sal >= 0.005:
                linhas.append((a, m, c, "outros_rendimentos", round(base - sal, 2)))
        for cat, gg in g[g.tipo != "base"].groupby("tipo"):
            linhas.append((a, m, c, cat, round(float(gg.proventos.sum()), 2)))
    ganha = pd.DataFrame(linhas, columns=["ano", "mes", "codigo", "categoria", "valor"])

    # verba: a linha informativa da folha (até jan/2026) e os arquivos mensais (2026); o mesmo mês nas duas, vale o arquivo
    vf = fol[fol.tipo == "verba"][["ano", "mes", "codigo", "proventos"]].rename(columns={"proventos": "valor"})
    va = vb[["ano", "mes", "codigo", "valor"]].astype({"codigo": int})
    meses_arquivo = set(va.ano * 100 + va.mes)
    vf = vf[~(vf.ano * 100 + vf.mes).isin(meses_arquivo)]
    vt = pd.concat([vf, va], ignore_index=True)
    desp = pd.DataFrame({"ano": vt.ano, "mes": vt.mes, "codigo": vt.codigo, "tipo": "Verba indenizatória (valor fixo)",
                         "fornecedor": "", "cnpj_cpf": "", "valor": vt.valor})
    com_verba = set(vt.ano * 100 + vt.mes)
    ultimo_vb = max(com_verba) if com_verba else None
    verba_sem = sorted(am for a, m in comum.meses(INICIO, min(ate, ultimo_vb or ate)) if (am := a * 100 + m) not in com_verba)
    notas = list(CFG["notas"])
    # mês em que a folha mensal de vários vereadores vem bem acima do valor de sempre (jan/2026): a nota diz o que a folha
    # mostra, sem explicar o que ela não explica
    mensal = fol[fol.descricao.str.upper() == "MENSAL"]
    comum_mes = mensal.proventos.round(2).mode()
    if len(comum_mes):
        normal = float(comum_mes.iloc[0])
        for am, g in mensal[mensal.proventos > normal * 1.3].groupby("am"):
            if len(g) >= 5:
                v = float(g.proventos.round(2).mode().iloc[0])
                n_v = int((g.proventos.round(2) == round(v, 2)).sum())
                notas.append(f"Em {am % 100:02d}/{am // 100}, a folha mensal de {len(g)} vereadores vem acima dos {_reais(normal)} "
                             f"dos outros meses ({n_v} com {_reais(v)}); a folha publicada não separa as parcelas. A diferença "
                             f"aparece em outros pagamentos.")
    if verba_sem:
        ms = [f"{x % 100:02d}/{x // 100}" for x in verba_sem]
        notas.append("A Câmara não publicou a verba indenizatória de " + (", ".join(ms[:-1]) + " e " + ms[-1] if len(ms) > 1 else ms[0])
                     + ": esses meses ficam sem verba.")
    if ultimo_vb and ultimo_vb < ate:
        notas.append(f"A verba indenizatória está publicada até {ultimo_vb % 100:02d}/{ultimo_vb // 100}; os meses seguintes ainda não têm verba.")
    cfg = dict(CFG, ultimo_mes=ate, subsidio_folha=True, verba_ate=ultimo_vb, verba_sem=verba_sem, notas=notas)
    return comum.montar(cfg, tipos, pd.DataFrame(ver), pd.DataFrame(mandatos), ganha=ganha, despesas=desp)
