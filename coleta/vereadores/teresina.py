"""Câmara Municipal de Teresina: vereador por vereador.

Fontes (sem cadastro; abrem de fora do Brasil, conferido em 08/10/2026; www.teresina.pi.leg.br tem robots.txt sem
proibição e o portal da transparência não tem robots.txt):
- Quem está em exercício hoje, nome parlamentar, nome completo, partido e foto: https://www.teresina.pi.leg.br/vereadores
  (a página separa os "Vereadores Licenciados") e a página de cada vereador.
- Despesas com Atividade Parlamentar (a cota): https://transparencia.teresina.pi.leg.br/project6-war/ext/consultarDespesaAtividade.jsf
  (PrimeFaces): cada pagamento a cada vereador (empenho, liquidação, data, valor) e, no "Detalhar", o mês das despesas
  ("ressarcimento de despesas realizadas no mês de agosto/2026") e as notas (fornecedor, CNPJ, inciso do art. 6º da
  Resolução Normativa 62/2013 e valor). Quem estava no cargo em cada mês: quem recebeu a cota daquele mês.
- Subsídio: R$ 24.754,79 por mês desde jan/2025, o valor que a folha da Câmara mostra para todos os vereadores
  (consulta "Remuneração", vínculo Parlamentar, conferida em 08/10/2026 em jan, fev e dez/2025 e jan, mai e ago/2026).
  A folha publicada não traz o nome de cada um: o salário aqui é o subsídio pelos dias no cargo, e a folha não é lida
  pelo robô.
- Nome civil, nome de urna, partido (quando a página da Câmara não tem) e gênero: TSE (eleição de 2024).

Plano de queda (portal frágil, só um caminho; escrito em 08/10/2026, também em dados/referencia/plano-de-queda.json):
- O subsídio não depende do robô. Se a consulta da cota mudar ou sair do ar, o robô mantém o que já gravou (gravação
  segura) e o site fica até o último mês lido; sem o detalhe de um pagamento, entra o valor pago, sem as notas.
- Lista de vereadores fora do ar: fica a última gravada (em_exercicio.csv e site_vereadores.csv).
- Não há reserva no Tribunal de Contas (o TCE-PI não tem a folha das câmaras em dados abertos que o projeto lê).
- Conserto só se couber em cerca de 1 hora; passou disso, a fonte vai para onde.CONGELADAS.
"""
import html as html_lib
import re

import pandas as pd

from ..config import CACHE, DADOS
from ..util import TempoEsgotado, _sessao, cache_valido, dormir, gravar_csv, log, normalizar_nome, verificar_prazo
from ..assembleias import comum as acomum
from . import comum

COD = 2211001
INICIO = 202501
SITE = "https://www.teresina.pi.leg.br"
LISTA = f"{SITE}/vereadores"
TRANSP = "https://transparencia.teresina.pi.leg.br"
COTA = f"{TRANSP}/project6-war/ext/consultarDespesaAtividade.jsf"
DETALHE = f"{TRANSP}/project6-war/ext/detalharDespesa.jsf"
FOLHA = f"{TRANSP}/project6-war/ext/consultarServidores.jsf"
PASTA = DADOS / "municipios" / "teresina"
C = CACHE / "cmteresina"
VAGAS = 29
SUBSIDIO = 24754.79
PENDENTE_MESES = 4  # pagamento sem notas no detalhe: pergunta de novo enquanto for recente (a Câmara lança as notas depois)
MESES = {m: i + 1 for i, m in enumerate(["janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro",
                                         "outubro", "novembro", "dezembro"])}
CFG = {
    "cod": COD, "n": "Teresina", "uf": "PI", "casa": "Câmara Municipal de Teresina", "vagas": VAGAS, "inicio": INICIO,
    "subsidio": [[INICIO, SUBSIDIO]],
    "salario_nota": ("Subsídio de R$ 24.754,79 por mês, o valor que a folha da Câmara mostra para os vereadores desde jan/2025, "
                     "proporcional aos meses no cargo. A folha publicada não traz o nome de cada vereador, por isso o 13º e outros "
                     "pagamentos não aparecem aqui."),
    "verba_nome": "Despesas com Atividade Parlamentar", "verba_mes": {},
    "verba_regra": ("Ressarcimento das despesas do mês, no valor recomendado pelo parecer da Controladoria da Câmara "
                    "(Lei 4.086/2011 e Resolução Normativa 62/2013)."),
    "verba_notas": ["Cada pagamento entra no mês das despesas que ele ressarce (o detalhe do pagamento diz o mês).",
                    "O tipo de cada nota é o inciso do art. 6º da Resolução Normativa 62/2013, como a Câmara publica.",
                    "Quando as notas de um mês passam do valor pago, cada nota é reduzida na mesma proporção, para a soma dar o que a Câmara pagou."],
    "credito_foto": "Câmara Municipal de Teresina", "pagina": LISTA,
    "notas": ["Quem estava no cargo em cada mês: quem recebeu a cota daquele mês (um mês sem a cota entre dois com ela, num mês em que menos vereadores que cadeiras receberam, conta como no cargo). Quem está em exercício hoje: a lista de vereadores da Câmara (os licenciados ficam à parte)."],
    "fontes": {"cota": COTA, "lista": LISTA, "subsidio": FOLHA},
}
H = {"Faces-Request": "partial/ajax", "X-Requested-With": "XMLHttpRequest"}


def _txt(c):
    return re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", c or ""))).strip()


def _valor(t):
    t = str(t or "").strip()
    if re.fullmatch(r"-?\d+(\.\d+)?", t):  # "25000.00" (campo do detalhe)
        return float(t)
    t = re.sub(r"[^\d,-]", "", t)
    return float(t.replace(",", ".")) if t else 0.0


def _pedir(metodo, url, sessao=None, arquivo=None, dias=None, **kw):
    if arquivo is not None and cache_valido(arquivo, dias):
        return arquivo.read_text(encoding="utf-8")
    verificar_prazo()
    s = sessao or _sessao()
    for tentativa in range(3):
        try:
            r = s.request(metodo, url, timeout=120, **kw)
            r.raise_for_status()
            texto = r.text
            break
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 2:
                raise
            dormir(10 + 10 * tentativa)
    dormir(1)
    if arquivo is not None:
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_text(texto, encoding="utf-8")
    return texto


# ---------------------------------------------------------------- lista de vereadores
def lista():
    """Quem está em exercício e quem está licenciado (página da Câmara), com o nome completo, o partido e a foto da
    página de cada um."""
    t = _pedir("GET", LISTA)
    corte = t.find("Vereadores Licenciados")
    cards = []
    for m in re.finditer(r'<a href="(https://www\.teresina\.pi\.leg\.br/vereadores/([a-z0-9-]+))" class="links-portal">(.*?)</a>', t, re.S):
        texto = _txt(re.search(r'<div class="text-center">(.*?)</div>', m.group(3), re.S).group(1)) if '<div class="text-center">' in m.group(3) else ""
        nome, _, partido = texto.rpartition(" - ")
        cards.append({"slug": m.group(2), "pagina": m.group(1), "nome": nome.strip() or texto, "partido": partido.strip(),
                      "licenciado": int(corte > 0 and m.start() > corte)})
    df = pd.DataFrame(cards).drop_duplicates("slug") if cards else pd.DataFrame()
    em = df[df.licenciado == 0] if len(df) else df
    if not 0.8 * VAGAS <= len(em) <= 1.2 * VAGAS:  # página quebrada: não tira ninguém do cargo nem põe ninguém
        log(f"  Teresina: a lista de vereadores veio com {len(em)} em exercício para {VAGAS} vagas; fica a que estava gravada")
        return
    completos, fotos, mandatos = [], [], []
    for r in df.itertuples():
        p = _pedir("GET", r.pagina, arquivo=C / f"vereador_{r.slug}.html", dias=6)
        nc = re.search(r"Nome Completo:\s*<strong>(.*?)</strong>", p, re.S)
        pt = re.search(r"Partido:\s*<strong>(.*?)</strong>", p, re.S)
        ft = re.search(r'<img src="([^"]+/storage/[^"]+)" class="img-fluid"', p)
        md = re.findall(r"Legislatura N\S*\s*20\s*-\s*(Titular|Suplente)", _txt(p))
        completos.append(_txt(nc.group(1)) if nc else "")
        sigla = _txt(pt.group(1)).rpartition(" - ")[2] if pt else ""
        fotos.append(ft.group(1) if ft else "")
        mandatos.append(md[0] if md else "")
        if sigla and not r.partido:
            df.loc[r.Index, "partido"] = sigla
    df = df.assign(nome_completo=completos, foto=fotos, mandato=mandatos)
    PASTA.mkdir(parents=True, exist_ok=True)
    gravar_csv(df[["slug", "nome", "nome_completo", "partido", "licenciado", "mandato", "foto", "pagina"]], PASTA / "site_vereadores.csv")
    acomum.gravar_em_exercicio(PASTA, list(em.nome), VAGAS, LISTA)
    log(f"  Teresina: {len(em)} vereadores em exercício e {len(df) - len(em)} licenciados na página da Câmara")


# ---------------------------------------------------------------- cota (Despesas com Atividade Parlamentar)
class _Consulta:
    """A consulta da cota de um ano (PrimeFaces): a lista de pagamentos e o detalhe de cada um, na mesma sessão."""

    def __init__(self, ano):
        self.s = _sessao()
        t = _pedir("GET", COTA, self.s)
        opcoes = dict((_txt(lab), val) for val, lab in re.findall(r'<option value="(\d+)"[^>]*>([^<]*)</option>', t[t.find('name="exercicio_input"'):]))
        if str(ano) not in opcoes:
            raise LookupError(f"exercício {ano} não está na consulta")
        self.url = TRANSP + html_lib.unescape(re.search(r'<form id="formConsulta"[^>]*action="([^"]+)"', t).group(1))
        vs = re.search(r'name="javax.faces.ViewState"[^>]*value="([^"]+)"', t).group(1)
        self.base = {"formConsulta": "formConsulta", "nome": "", "exercicio_focus": "", "exercicio_input": opcoes[str(ano)], "javax.faces.ViewState": vs}
        self.ano = ano

    def _ajax(self, fonte, extra):
        return _pedir("POST", self.url, self.s, data=dict(self.base, **{"javax.faces.partial.ajax": "true", "javax.faces.source": fonte}, **extra), headers=H)

    def pagamentos(self):
        busca = self._ajax("btConsultar", {"javax.faces.partial.execute": "formConsulta", "javax.faces.partial.render": "formConsulta", "btConsultar": "btConsultar"})
        t = self._ajax("dataTable", {"javax.faces.partial.execute": "dataTable", "javax.faces.partial.render": "dataTable", "dataTable": "dataTable",
                                     "dataTable_pagination": "true", "dataTable_first": "0", "dataTable_rows": "2000",
                                     "dataTable_skipChildren": "true", "dataTable_encodeFeature": "true"})
        saida = []
        for linha in re.findall(r"<tr data-ri[^>]*>(.*?)</tr>", t, re.S):
            cel = [_txt(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", linha, re.S)]
            botao = re.search(r'id="(dataTable:\d+:j_idt\d+)"', linha)
            if len(cel) < 7 or not botao:
                continue
            saida.append({"exercicio": self.ano, "empenho": cel[2], "liquidacao": cel[3], "data_pagamento": cel[4], "nome": cel[1],
                          "valor": _valor(cel[5]), "_botao": botao.group(1)})
        total = re.search(r"rowCount:(\d+)", busca)
        if total and int(total.group(1)) != len(saida):
            raise ValueError(f"a lista de {self.ano} tem {total.group(1)} pagamentos e vieram {len(saida)}")
        return saida

    def detalhe(self, botao):
        """(mês das despesas AAAAMM ou None, valor, [notas]) de um pagamento."""
        self._ajax(botao, {"javax.faces.partial.execute": "formConsulta", "javax.faces.partial.render": "formConsulta", botao: botao})
        t = _pedir("GET", DETALHE, self.s)
        ref = None
        m = re.search(r"NO M[ÊE]S DE\s+([A-Za-zçÇ]+)\s*/\s*(\d{4})", _txt(t), re.I)
        if m and normalizar_nome(m.group(1)).lower() in MESES:
            ref = int(m.group(2)) * 100 + MESES[normalizar_nome(m.group(1)).lower()]
        valor = re.search(r'id="input8_input"[^>]*value="([^"]*)"', t)
        notas = self._notas(t)
        tabela = re.search(r'PrimeFaces\.cw\("DataTable","[^"]*tabelaD",\{id:"([^"]+)",paginator:\{[^}]*rows:(\d+),rowCount:(\d+)', t)
        if tabela and int(tabela.group(3)) > len(notas):  # mais notas que cabem numa página: pede todas de uma vez
            tid, form = tabela.group(1), re.search(r'<form id="([^"]+)"[^>]*>(?:(?!</form>).)*?' + re.escape(tabela.group(1)), t, re.S)
            vs = re.search(r'name="javax.faces.ViewState"[^>]*value="([^"]+)"', t).group(1)
            dados = {form.group(1) if form else "formCadastro": form.group(1) if form else "formCadastro", "javax.faces.ViewState": vs,
                     "javax.faces.partial.ajax": "true", "javax.faces.source": tid, "javax.faces.partial.execute": tid, "javax.faces.partial.render": tid,
                     tid: tid, f"{tid}_pagination": "true", f"{tid}_first": "0", f"{tid}_rows": "500", f"{tid}_skipChildren": "true", f"{tid}_encodeFeature": "true"}
            notas = self._notas(_pedir("POST", DETALHE, self.s, data=dados, headers=H))
            if len(notas) != int(tabela.group(3)):
                raise ValueError(f"o detalhe tem {tabela.group(3)} notas e vieram {len(notas)}")
        return ref, (_valor(valor.group(1)) if valor else None), notas

    @staticmethod
    def _notas(t):
        i = t.find("tabelaD")
        corpo = t[i:] if i >= 0 else ""
        corpo = corpo[:corpo.find("ANEXOS")] if "ANEXOS" in corpo else corpo
        saida = []
        for linha in re.findall(r"<tr data-ri[^>]*>(.*?)</tr>", corpo, re.S):
            cel = [_txt(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", linha, re.S)]
            if len(cel) >= 6:
                # pf: o documento é um CPF (pessoa física). O CPF não é guardado, nem mascarado (comum.mascarar), e o site
                # mostra "Pessoa física" no lugar do nome
                doc = re.sub(r"\D", "", cel[2])
                pf = int(len(doc) == 11 or ("*" in cel[2] and len(doc) != 14))
                saida.append({"fornecedor": cel[1], "cnpj_cpf": comum.mascarar(cel[2]), "pf": pf, "tipo": cel[3], "observacao": cel[4], "valor": _valor(cel[5])})
        return saida


def cota():
    """Pagamentos da cota desde 2025 e o detalhe de cada um (só os que faltam, e de novo os recentes sem notas)."""
    arq_p, arq_n = PASTA / "cota_pagamentos.csv", PASTA / "cota_notas.csv"
    velhos = pd.read_csv(arq_p, dtype=str).fillna("") if arq_p.exists() else pd.DataFrame(columns=["exercicio", "empenho", "liquidacao"])
    notas_v = pd.read_csv(arq_n, dtype=str).fillna("") if arq_n.exists() else pd.DataFrame(columns=["exercicio", "empenho", "liquidacao"])
    chave = lambda d: (str(d["exercicio"]), str(d["empenho"]), str(d["liquidacao"]))
    feitos = {chave(r): r for r in velhos.to_dict("records")}
    notas_por = {}
    for r in notas_v.to_dict("records"):
        notas_por.setdefault(chave(r), []).append(r)
    hoje = comum.ultimo_mes_fechado()
    limite = comum.menos_meses(hoje, PENDENTE_MESES)
    pags, novos, falhas = [], 0, 0
    try:
        for ano in range(INICIO // 100, hoje // 100 + 2):
            try:
                q = _Consulta(ano)
            except LookupError:
                continue
            for p in q.pagamentos():
                k = chave(p)
                v = feitos.get(k)
                # sem notas no detalhe e pago há pouco: pergunta de novo (a Câmara lança as notas depois)
                pago = re.match(r"\d{2}/(\d{2})/(\d{4})", p["data_pagamento"])
                recente = bool(pago) and int(pago.group(2)) * 100 + int(pago.group(1)) >= limite
                if v is not None and not (str(v.get("notas", "")) in ("", "0") and recente):
                    pags.append({**v, "nome": p["nome"], "valor": p["valor"], "data_pagamento": p["data_pagamento"]})
                    continue
                try:
                    ref, valor, ns = q.detalhe(p["_botao"])
                except TempoEsgotado:
                    raise
                except Exception as e:  # noqa: BLE001 — um detalhe que não abriu fica para a próxima vez
                    falhas += 1
                    log(f"  Teresina: o detalhe de {p['nome']} ({p['empenho']}) não abriu ({e})")
                    if falhas >= 5:
                        raise
                    if v is not None:
                        pags.append(v)
                    continue
                if valor is not None and abs(valor - p["valor"]) >= 0.01:  # o detalhe não é o desta linha: para tudo
                    raise ValueError(f"o detalhe de {p['nome']} ({p['empenho']}) mostra {valor} e a lista {p['valor']}")
                pags.append({k2: v2 for k2, v2 in p.items() if not k2.startswith("_")} | {"ref": ref or "", "notas": len(ns)})
                notas_por[k] = [{"exercicio": k[0], "empenho": k[1], "liquidacao": k[2], **n} for n in ns]
                novos += 1
    finally:
        # o que já veio fica gravado, mesmo se o tempo acabar no meio (na próxima vez continua de onde parou)
        vistos = {chave(p) for p in pags}
        pags += [v for k, v in feitos.items() if k not in vistos]
        if pags:
            dfp = pd.DataFrame(pags, columns=["exercicio", "empenho", "liquidacao", "data_pagamento", "nome", "valor", "ref", "notas"])
            # os já gravados vêm como texto e os novos como número: tudo no mesmo tipo, para a ordem ser sempre a mesma
            dfp = dfp.assign(exercicio=dfp.exercicio.astype(str), valor=pd.to_numeric(dfp.valor),
                             ref=pd.to_numeric(dfp.ref, errors="coerce").astype("Int64"), notas=pd.to_numeric(dfp.notas).astype(int))
            dfn = pd.DataFrame([n for k in sorted(notas_por) if k in {chave(p) for p in pags} for n in notas_por[k]],
                               columns=["exercicio", "empenho", "liquidacao", "fornecedor", "cnpj_cpf", "pf", "tipo", "observacao", "valor"])
            PASTA.mkdir(parents=True, exist_ok=True)
            if gravar_csv(dfn, arq_n):
                gravar_csv(dfp.sort_values(["exercicio", "ref", "nome", "empenho"], kind="stable"), arq_p)
        log(f"  Teresina: cota com {len(pags)} pagamentos ({novos} detalhados agora)")


def coletar():
    try:  # se o portal não responder, desiste logo: o site usa o que já está gravado
        _sessao().get(SITE, timeout=30).raise_for_status()
    except Exception as e:  # noqa: BLE001
        log(f"  Teresina: o site da Câmara não abriu ({type(e).__name__}); fica o que já estava gravado")
        raise
    lista()
    cota()


# ---------------------------------------------------------------- montagem
def _tipo(t):
    m = re.search(r"Inciso\s+([IVXL]+)", t or "", re.I)
    return f"Inciso {m.group(1).upper()} do art. 6º (Resolução 62/2013)" if m else (comum.tipo_curto(t) if t else "Não informado")


def _ref_pela_data(data):
    """Mês das despesas quando o detalhe não diz (um pagamento de jul/2025 traz no detalhe o texto de outro contrato): a
    cota de um mês é paga no começo do mês seguinte (a de dezembro, no fim de dezembro). Pago até o dia 14: o mês
    anterior; depois: o próprio mês."""
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", str(data or ""))
    if not m:
        return 0
    d, mes, ano = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return ano * 100 + mes if d >= 15 else comum.menos_meses(ano * 100 + mes, 1)


def montar(tipos):
    arq = PASTA / "cota_pagamentos.csv"
    if not arq.exists():
        return None
    pag = pd.read_csv(arq, dtype={"empenho": str, "liquidacao": str}).fillna({"ref": 0, "data_pagamento": ""})
    pag["ref"] = [int(float(r)) if float(r) > 0 else _ref_pela_data(d) for r, d in zip(pag.ref, pag.data_pagamento)]
    pag = pag[pag.ref >= INICIO]
    if not len(pag):
        return None
    notas = pd.read_csv(PASTA / "cota_notas.csv", dtype=str).fillna("") if (PASTA / "cota_notas.csv").exists() else pd.DataFrame(columns=["exercicio", "empenho", "liquidacao", "fornecedor", "cnpj_cpf", "tipo", "valor"])
    site = pd.read_csv(PASTA / "site_vereadores.csv").fillna("") if (PASTA / "site_vereadores.csv").exists() else pd.DataFrame(columns=["slug", "nome", "nome_completo", "partido", "licenciado", "mandato", "foto", "pagina"])
    tse = comum.candidatos_tse("PI", "Teresina")
    por_civil = [(n, i) for i, n in enumerate(tse.nome)] if len(tse) else []

    # quem é quem: o nome da cota é o nome civil (às vezes abreviado: "FERNANDO EDUARDO S DE L SANTOS"); o código é o SQ da
    # candidatura no TSE (como em Boa Vista e João Pessoa)
    site_completos = [(r.nome_completo, i) for i, r in enumerate(site.itertuples()) if r.nome_completo]
    codigos, info, fora = {}, {}, []
    for nome in sorted(set(pag.nome)):
        i = comum.achar_parecido(nome, por_civil, 0.9) if por_civil else None
        t = tse.iloc[i].to_dict() if i is not None else None
        if t is None and not (site_completos and comum.achar_parecido(nome, site_completos, 0.9) is not None):
            # a consulta traz também pagamentos que não são a cota de um vereador desta legislatura (INSS, empresas, a
            # própria Câmara, restos a pagar de ex-vereador): quem não foi candidato a vereador em 2024 nem está na página
            # da Câmara fica de fora
            fora.append(nome)
            continue
        cod = int(t["sq"]) if t is not None else acomum.codigo_de(nome, None)
        codigos[nome] = cod
        info.setdefault(cod, {"t": t, "nome": nome})
    if fora:
        log(f"  Teresina: pagamentos que não são de vereador, fora: {', '.join(fora)}")
    pag = pag[pag.nome.isin(codigos)].copy()
    pag["codigo"] = pag.nome.map(codigos)
    sem_tse = sorted({v["nome"] for v in info.values() if v["t"] is None})
    if sem_tse:
        log(f"  Teresina: sem candidatura no TSE de 2024: {', '.join(sem_tse)}")
    # a página da Câmara: pelo nome completo (que casa com o da cota) ou pelo nome parlamentar (com o nome de urna)
    opcoes = [(v["nome"], c) for c, v in info.items()] + [(v["t"]["nome"], c) for c, v in info.items() if v["t"] is not None]
    urnas = [(v["t"]["nome_urna"], c) for c, v in info.items() if v["t"] is not None]
    site_cod = {}
    for r in site.itertuples():
        c = (comum.achar_parecido(r.nome_completo, opcoes, 0.9) if r.nome_completo else None) or comum.achar_parecido(r.nome, urnas, 0.9)
        if c is None:
            log(f"  Teresina: na página da Câmara e sem cota: {r.nome}")
            continue
        site_cod[c] = r
    # último mês: o último em que quase todos já receberam (a cota de um mês sai aos poucos no começo do mês seguinte)
    por_mes = pag.groupby("ref").codigo.nunique()
    completos = [m for m, n in por_mes.items() if n >= 0.8 * VAGAS]
    ultimo = int(max(completos)) if completos else int(por_mes.index.max())
    ate = comum.ultimo_mes_fechado()
    nomes_lista = acomum.ler_em_exercicio(PASTA)
    atual = {c: bool(c in site_cod and not int(site_cod[c].licenciado)) for c in info} if nomes_lista else None

    ver, mandatos, fotos = [], [], []
    for c in sorted(info):
        v, s, t = info[c], site_cod.get(c), info[c]["t"]
        if s is not None and s.foto:
            fotos.append((c, s.foto))
        ver.append({"codigo": c, "nome": s.nome if s is not None else (comum.titulo(t["nome_urna"]) if t else comum.titulo(v["nome"])),
                    "nome_civil": comum.titulo(s.nome_completo) if s is not None and s.nome_completo else (comum.titulo(t["nome"]) if t else comum.titulo(v["nome"])),
                    "partido": (s.partido if s is not None and s.partido else "") or (t["partido"] if t else ""),
                    "genero": t["genero"] if t else "",
                    "eleito": ("suplente" if s is not None and s.mandato == "Suplente" else "eleito" if s is not None and s.mandato == "Titular" else (t["situacao"] if t else "")),
                    "pagina": s.pagina if s is not None else LISTA})
        meses = set(pag[(pag.codigo == c) & (pag.ref <= ultimo)].ref)
        # um mês sem a cota entre dois meses com ela, num mês em que menos vereadores que cadeiras receberam: estava no
        # cargo (a cota daquele mês não saiu para ele)
        for am in list(meses):
            meio, depois = comum.mes_seguinte(am), comum.mes_seguinte(comum.mes_seguinte(am))
            if meio not in meses and depois in meses and por_mes.get(meio, 0) < VAGAS:
                meses.add(meio)
        for i, f in comum.periodos_de_meses(meses, ultimo):
            mandatos.append({"codigo": c, "inicio": i, "fim": f})
        if atual is not None and meses:
            aberto = any(not m["fim"] for m in mandatos if m["codigo"] == c)
            if atual[c] and not aberto:  # em exercício hoje, sem a cota dos últimos meses (voltou de licença, ou a cota ainda não saiu)
                seg = comum.mes_seguinte(ultimo)
                mandatos.append({"codigo": c, "inicio": f"{seg // 100}-{seg % 100:02d}-01", "fim": ""})
            elif not atual[c] and aberto:  # licenciado hoje: o período fecha no fim do último mês com cota
                for m in mandatos:
                    if m["codigo"] == c and not m["fim"]:
                        a, mm = divmod(ultimo, 100)
                        m["fim"] = f"{a}-{mm:02d}-{pd.Period(f'{a}-{mm:02d}').days_in_month:02d}"
    comum.fotos(COD, fotos)

    # verba: no mês das despesas, as notas de todos os pagamentos daquele mês (um mês pode vir em dois pagamentos, com as
    # notas num só). Notas que passam do valor pago (o limite): cada nota é reduzida na mesma proporção, para a soma dar o
    # que a Câmara pagou; pago a mais que as notas, ou sem notas publicadas: a diferença numa linha "Sem detalhe publicado".
    # Fornecedor pessoa física: "Pessoa física" no site (o nome fica só nos dados da Câmara)
    notas = notas.assign(valor=pd.to_numeric(notas.valor, errors="coerce").fillna(0.0), pf=pd.to_numeric(notas.get("pf", 0), errors="coerce").fillna(0))
    chave_pag = {(str(r.exercicio), str(r.empenho), str(r.liquidacao)): (r.codigo, int(r.ref)) for r in pag.itertuples()}
    notas["dono"] = [chave_pag.get((str(e), str(m), str(l))) for e, m, l in zip(notas.exercicio, notas.empenho, notas.liquidacao)]
    notas = notas[notas.dono.notna()]
    notas_por = {k: g for k, g in notas.groupby("dono")} if len(notas) else {}
    linhas = []
    for (cod, ref), g in pag[pag.ref <= ultimo].groupby(["codigo", "ref"]):
        a, m = divmod(int(ref), 100)
        pago = round(float(g.valor.sum()), 2)
        ns = notas_por.get((cod, int(ref)))
        soma = round(float(ns.valor.sum()), 2) if ns is not None else 0.0
        fator = pago / soma if soma > pago and soma else 1.0
        for n in (ns.itertuples() if ns is not None else []):
            pf = bool(int(n.pf))
            linhas.append({"ano": a, "mes": m, "codigo": cod, "tipo": _tipo(n.tipo), "fornecedor": n.fornecedor,
                           "cnpj_cpf": "***" if pf else n.cnpj_cpf, "valor": round(float(n.valor) * fator, 2)})
        if pago - soma >= 0.01:
            linhas.append({"ano": a, "mes": m, "codigo": cod, "tipo": "Sem detalhe publicado", "fornecedor": "", "cnpj_cpf": "", "valor": round(pago - soma, 2)})
    desp = pd.DataFrame(linhas, columns=["ano", "mes", "codigo", "tipo", "fornecedor", "cnpj_cpf", "valor"])
    cfg = dict(CFG, ultimo_mes=min(ate, ultimo))
    return comum.montar(cfg, tipos, pd.DataFrame(ver), pd.DataFrame(mandatos), despesas=desp)
