"""Parte comum dos Tribunais de Contas que publicam o valor por cargo, e não o de cada pessoa (Espírito Santo, Pernambuco
e Rio de Janeiro; ver o README, "Tribunais de Contas").

Nesses estados, o tribunal publica, para cada câmara ou prefeitura e cada mês, o total pago a um cargo (ou a uma
situação funcional) e quantas pessoas estavam nele: "VEREADOR, 13 pessoas, R$ 264.775,16". Dá para saber quanto a
Câmara pagou ao cargo de vereador e a média por pessoa, mas não quanto cada vereador recebeu: o presidente da Câmara,
quem entrou ou saiu no meio do mês e quem recebeu 13º ou férias naquele mês ficam somados aos outros. Quando o cargo tem
uma pessoa só (o prefeito, o vice), o total é o valor dela.

Arquivos de cada estado, em dados/municipios_tce/<uf>/ (vão para o Git):
- cargos.csv (COLUNAS): uma linha por cidade, órgão (camara ou prefeitura), mês, papel (vereador, prefeito ou vice) e
  cargo como a fonte escreve, com a quantidade de pessoas e o total bruto (antes dos descontos); onde a fonte separa,
  as partes indenizatória, 13º e férias dentro do total;
- nomes.csv (NOMES): quem estava no cargo naquele mês, só o nome e o cargo, onde a fonte dá os nomes (ES: todos os
  meses; PE: o último mês lido de cada cidade; RJ: nenhum). Nunca o CPF, nem mascarado;
- fontes.csv (o mesmo de comum.FONTES): cada cidade, órgão e mês já lido, com quantas linhas a folha tinha na fonte
  (0 = o município ainda não tinha mandado).

`montar_site(uf, cfg)` escreve site/dados/interior-cargo/<uf>.json, numa pasta à parte da dos estados com o valor de
cada pessoa (site/dados/interior/), porque o formato é outro (CAMPOS).
"""
import json
import re

import pandas as pd

from ..config import DADOS, RAIZ
from ..util import log, normalizar_nome
from . import comum

SITE = RAIZ / "site" / "dados" / "interior-cargo"
COLUNAS = ["cod_ibge", "municipio", "orgao", "ano_mes", "papel", "cargo", "quantidade", "valor_total", "indenizatorio",
           "decimo", "ferias", "unidade"]
VALORES = ["valor_total", "indenizatorio", "decimo", "ferias"]
NOMES = ["cod_ibge", "orgao", "ano_mes", "papel", "nome", "cargo"]
ORDEM = ["cod_ibge", "orgao", "ano_mes", "papel", "cargo"]
MESES_TIPICO = 12  # o valor típico por pessoa: a mediana dos meses com valor entre os últimos 12 do período
MIN_MESES = 3      # ... com pelo menos 3 meses que entram na conta (ver _bloco)


# ---------------------------------------------------------------- arquivos
def _ler(caminho, colunas):
    if not caminho.exists():
        return pd.DataFrame(columns=colunas)
    df = pd.read_csv(caminho, dtype={"cargo": str, "unidade": str, "municipio": str, "nome": str, "orgao": str,
                                     "papel": str})
    return df if len(df) else pd.DataFrame(columns=colunas)


def ler(uf):
    return _ler(comum.pasta(uf) / "cargos.csv", COLUNAS)


def ler_nomes(uf):
    return _ler(comum.pasta(uf) / "nomes.csv", NOMES)


def _trocar(velho, novo, chaves, colunas):
    """Tira de `velho` os blocos (cod_ibge, orgao, ano_mes) de `chaves` e junta `novo`."""
    tem = lambda df: [(int(c), o, int(m)) in chaves for c, o, m in zip(df.cod_ibge, df.orgao, df.ano_mes)]
    if len(velho):
        velho = velho[[not t for t in tem(velho)]]
    novo = pd.DataFrame(novo, columns=colunas)
    partes = [x for x in (velho, novo) if len(x)]
    if not partes:
        return pd.DataFrame(columns=colunas)
    return pd.concat(partes, ignore_index=True).astype({"cod_ibge": int, "ano_mes": int})


def gravar(uf, linhas, blocos, nomes=None, blocos_nomes=None, manter_data=False):
    """Troca, nos arquivos do estado, os blocos lidos agora (cidade, órgão, mês) pelas linhas novas. linhas: [dict com
    COLUNAS]; blocos: [dict com comum.FONTES]; nomes: [dict com NOMES], só nos blocos de `blocos_nomes` (o padrão: os
    mesmos de `blocos`; num bloco lido sem os nomes, os nomes gravados antes ficam). Um bloco lido vazio não apaga o que
    já estava gravado de outro mês. `manter_data`: o bloco lido de novo sem mudança fica com a data da leitura anterior
    (ES e RJ, que leem todos os meses toda vez; no PE, não, porque a data decide o que ler de novo). Devolve (linhas
    gravadas, blocos gravados)."""
    if not blocos:
        return 0, 0
    novos = pd.DataFrame(blocos, columns=comum.FONTES).drop_duplicates(comum.CHAVE, keep="last")
    chaves = set(zip(novos.cod_ibge.astype(int), novos.orgao, novos.ano_mes.astype(int)))
    df = _trocar(ler(uf), [l for l in linhas if (int(l["cod_ibge"]), l["orgao"], int(l["ano_mes"])) in chaves],
                 chaves, COLUNAS)
    if len(df):
        df = df.astype({c: float for c in VALORES + ["quantidade"]})
    comum._escrever(df, comum.pasta(uf) / "cargos.csv", COLUNAS, ORDEM)
    if nomes is not None:
        ch_n = chaves if blocos_nomes is None else {(int(c), o, int(m)) for c, o, m in blocos_nomes}
        dn = _trocar(ler_nomes(uf), [n for n in nomes if (int(n["cod_ibge"]), n["orgao"], int(n["ano_mes"])) in ch_n],
                     ch_n, NOMES)
        comum._escrever(dn.drop_duplicates(), comum.pasta(uf) / "nomes.csv", NOMES,
                        ["cod_ibge", "orgao", "ano_mes", "papel", "nome"])
    fontes = comum.ler_fontes(uf)
    if len(fontes) and manter_data:
        # bloco lido de novo sem mudança (mesmas linhas na fonte, mesmas pessoas, mesmo endereço): fica a data da
        # leitura anterior, para o arquivo não mudar inteiro a cada rodada (ES e RJ leem todos os meses toda vez)
        antes = {(int(c), o, int(m)): (n, p, u, q) for c, o, m, n, p, u, q in
                 zip(fontes.cod_ibge, fontes.orgao, fontes.ano_mes, fontes.linhas_fonte, fontes.pessoas, fontes.url,
                     fontes.lido_em)}
        quando = []
        for c, o, m, n, p, u, q in zip(novos.cod_ibge, novos.orgao, novos.ano_mes, novos.linhas_fonte, novos.pessoas,
                                       novos.url, novos.lido_em):
            a = antes.get((int(c), o, int(m)))
            igual = a and int(a[0] or 0) == int(n or 0) and int(a[1] or 0) == int(p or 0) and a[2] == u
            quando.append(a[3] if igual else q)
        novos = novos.assign(lido_em=quando)
    if len(fontes):
        tem = [(int(c), o, int(m)) in chaves for c, o, m in zip(fontes.cod_ibge, fontes.orgao, fontes.ano_mes)]
        fontes = fontes[[not t for t in tem]]
    fontes = pd.concat([x for x in (fontes, novos) if len(x)], ignore_index=True)
    comum._escrever(fontes.astype({"cod_ibge": int, "ano_mes": int}), comum.pasta(uf) / "fontes.csv", comum.FONTES,
                    comum.CHAVE)
    return int(len(df)), len(novos)


# ---------------------------------------------------------------- cargos
_PRESIDENTE = re.compile(r"PRESIDENTE(A|OA)?((DA|DE)?CAMARA(MUNICIPAL)?)?")
_PREFEITO = re.compile(r"(VICE)?PREF(EI|E|I)T(O|A|OA|OS)(MUNICIPAL|MUNCIPAL|MUNICIAL|CONSTITUCIONAL|ELETIVO|ELEITO)?"
                       r"(EMEXERCICIO|INTERINO|INTERINA)?")


def _letras(cargo):
    """O cargo só com as letras, sem os códigos que alguns municípios põem junto ao nome (PE): "PREFEITO EX1",
    "PREFEITO - P0216", "PREFEITO (102C)", "001PREFEITO 0010165", "VICE-PREFEITO EMP 01", "CV VEREADOR", "CARGO
    VEREADOR", "1C VEREADOR" -> "PREFEITO", "VICEPREFEITO", "VEREADOR". Devolve as formas a testar: essa e, quando o
    cargo começa com uma letra solta grudada ("PPREFEITO", "AVICE-PREFEITO", "FVEREADOR"), também sem ela."""
    t = normalizar_nome(cargo)
    t = re.sub(r"\([^)]*\)", " ", t)
    t = re.sub(r"\b\d+(?=[A-Z])", "", t)      # 001PREFEITO -> PREFEITO
    t = re.sub(r"\b\w*\d\w*\b", " ", t)       # tokens com algarismo: EX1, P0216, 0063
    t = re.sub(r"^\s*(CARGO|CV)\s+", "", t)
    t = re.sub(r"\s+EMP\s*$", "", t)
    letras = re.sub(r"[^A-Z]", "", t)
    formas = [letras]
    if re.match(r"^[A-Z](PREFE|VICEPREFE|VERE)", letras):
        formas.append(letras[1:])
    return formas


def papel_camara(cargo):
    """"vereador" quando o cargo é o de vereador ou o de presidente da Câmara ("PRESIDENTE", "PRESIDENTE(A) DA CÂMARA";
    ver comum.eh_vereador), também com os códigos que alguns municípios põem junto (_letras); senão None."""
    if comum.eh_vereador(cargo, eletivo=True):
        return "vereador"
    for f in _letras(cargo):
        if comum._VEREADOR.match(f) or _PRESIDENTE.fullmatch(f) or comum._PRESIDENTE_CAMARA.fullmatch(f):
            return "vereador"
    return None


def papel_prefeitura(cargo):
    """"prefeito" ou "vice" (comum.papel_prefeitura e também "PREFEITO MUNICIPAL EM EXERCÍCIO", "Prefeito Muncipal",
    "VICE PREFETO" e os cargos com código junto: _letras); senão None. Não pega quem trabalha para o prefeito
    ("ASSESSOR ESPECIAL DO PREFEITO") nem o subprefeito."""
    p = comum.papel_prefeitura(cargo)
    if p:
        return p
    for f in _letras(cargo):
        m = _PREFEITO.fullmatch(f)
        if m:
            return "vice" if m.group(1) else "prefeito"
    return None


def limpar_cargo(cargo):
    """Como a fonte escreve, sem o código interno do município, sem espaços repetidos nem quebras de linha."""
    return re.sub(r"^\s*\d+\s*-\s*", "", re.sub(r"\s+", " ", str(cargo or ""))).strip()


def cadeiras():
    """{cod_ibge: número de vereadores eleitos em 2024} (TSE, dados/municipios/vereadores.csv)."""
    ver = pd.read_csv(DADOS / "municipios" / "vereadores.csv")
    return ver.groupby("cod_ibge").size().to_dict()


# ---------------------------------------------------------------- site
_r = comum._r


def _por_mes(g, meses_, coluna):
    idx = {m: i for i, m in enumerate(meses_)}
    s = [None] * len(meses_)
    for m, v in g.groupby("ano_mes")[coluna].sum(min_count=1).items():
        if int(m) in idx and pd.notna(v):
            s[idx[int(m)]] = v
    return s


def _pessoas(lista, papel, candidatos):
    """Os nomes do último mês, com o nome de urna e o partido de 2024 quando o nome casa sem dúvida com um único
    candidato da cidade (comum.casar_tse)."""
    saida = []
    exatos = {n: comum.casar_tse(n, papel, candidatos) for n, _ in lista}
    usados = {c["sq"] for c in exatos.values() if c}
    for nome, cargo in lista:
        c = exatos.get(nome) or comum.casar_tse(nome, papel, candidatos, forte=True, excluir=usados)
        if c and not exatos.get(nome):
            usados.add(c["sq"])
        if c:
            e = {"n": comum.titulo(c["urna"]), "nc": comum.titulo(nome), "pt": c["partido"]}
            if c.get("genero") in ("M", "F"):
                e["gn"] = c["genero"]
            if e["nc"] == e["n"]:
                del e["nc"]
        else:
            e = {"n": comum.titulo(nome)}
        e["g"] = cargo
        if papel == "vereador" and comum.eh_presidente(cargo):
            e["pr"] = 1
        saida.append(e)
    return sorted(saida, key=lambda e: normalizar_nome(e["n"]))


def _mediana(valores):
    v = sorted(valores)
    k = len(v) // 2
    return v[k] if len(v) % 2 else (v[k - 1] + v[k]) / 2


def _bloco(g, gn, meses_, papel, candidatos, esperado, separa_13):
    """Um papel (vereador, prefeito ou vice) numa cidade: ver CAMPOS.

    O valor típico por pessoa (vm) é a mediana da média do mês (t ÷ q), só nos meses entre os últimos 12 do período em
    que: a quantidade na folha é a `esperada` (as cadeiras da Câmara; 1 para prefeito e vice), porque, com outra
    quantidade (suplente que assumiu, quem saiu no meio do mês, outra pessoa no mesmo cargo), a média deixa de ser o
    valor de um cargo ocupado o mês inteiro; e não há 13º nem férias (onde a fonte separa, `separa_13`; onde não separa,
    dezembro fica de fora). Com menos de MIN_MESES meses assim, não há vm."""
    q = _por_mes(g, meses_, "quantidade")
    t = _por_mes(g, meses_, "valor_total")
    e = {"q": comum.rle([_r(v) for v in q]), "t": comum.rle([_r(v) for v in t])}
    partes = {}
    for col, chave in (("indenizatorio", "i"), ("decimo", "d"), ("ferias", "fe")):
        s = _por_mes(g, meses_, col)
        partes[col] = s
        if any(v is not None and v > 0 for v in s):
            e[chave] = comum.rle([_r(v) if v is not None and v > 0 else None for v in s])
    com_valor = [i for i, v in enumerate(t) if v is not None and v > 0]
    e["u"] = meses_[com_valor[-1]] if com_valor else None
    if com_valor:
        ult = g[g.ano_mes == e["u"]]
        e["g"] = " / ".join(dict.fromkeys(limpar_cargo(c) for x in ult.cargo.astype(str) for c in x.split(" / ")))

        def normal(i):
            if separa_13:
                return not any((partes[c][i] or 0) > 0 for c in ("decimo", "ferias"))
            return meses_[i] % 100 != 12
        recentes = [i for i in com_valor if i >= len(meses_) - MESES_TIPICO]  # os últimos 12 meses do período
        bons = [i for i in recentes if q[i] and esperado and int(q[i]) == esperado and normal(i)]
        if len(bons) >= MIN_MESES:
            e["vm"] = _r(_mediana([t[i] / q[i] for i in bons]))
            e["vmn"] = len(bons)
            if "i" in e:  # sem a parte indenizatória (auxílio-alimentação e outras), onde a fonte separa
                e["vmr"] = _r(_mediana([(t[i] - (partes["indenizatorio"][i] or 0)) / q[i] for i in bons]))
    if gn is not None and len(gn):
        mm = int(gn.ano_mes.max())
        ult = gn[gn.ano_mes == mm]
        lista = list(dict.fromkeys(zip(ult.nome.astype(str), ult.cargo.fillna("").astype(str).map(limpar_cargo))))
        lista = list({n: (n, c) for n, c in lista}.values())  # o mesmo nome com dois cargos: fica um
        e["pm"] = mm
        e["ps"] = _pessoas(lista, papel, candidatos)
    return e


CAMPOS = {
    "m": "cidades, pelo código do IBGE",
    "n": "nome (na cidade: o nome da cidade; na pessoa: o nome de urna em 2024, quando casou com o TSE, senão o nome da folha)",
    "cad": "cadeiras de vereador da cidade (eleitos em 2024, TSE)",
    "c": "vereadores: o cargo de vereador (e o de presidente da Câmara) na folha da Câmara",
    "pf": "prefeito: o cargo de prefeito na folha da Prefeitura", "vp": "vice-prefeito: o cargo de vice na folha da Prefeitura",
    "q": "quantas pessoas estavam no cargo em cada mês, de meta.inicio a meta.ultimo_mes, em pares [valor, meses seguidos] "
         "(null = sem o dado)",
    "t": "total bruto pago ao cargo em cada mês (soma de todas as pessoas, antes dos descontos), em reais, no mesmo formato",
    "i": "parte indenizatória dentro de t (auxílio-alimentação e outras), só onde a fonte separa",
    "d": "13º salário dentro de t, só onde a fonte separa",
    "fe": "férias (e o terço de férias) dentro de t, só onde a fonte separa",
    "u": "último mês com valor",
    "g": "cargo como está na folha no último mês (mais de um, separados por /)",
    "vm": "valor típico por pessoa no cargo: a mediana de t dividido por q, entre os últimos 12 meses do período (até "
          "meta.ultimo_mes), só nos meses em que a quantidade (q) era a esperada (as cadeiras, cad, para vereadores; 1 "
          "para prefeito e vice) e sem 13º nem férias (onde a fonte separa; onde não separa, sem dezembro). Precisa de 3 "
          "meses assim; senão, não há vm. Para vereadores é uma média, e não o salário de uma pessoa",
    "vmn": "quantos meses entraram no vm",
    "vmr": "o mesmo vm sem a parte indenizatória (i), só onde a fonte separa: é o que se compara com o teto da Constituição",
    "pm": "mês da lista de nomes (ps)", "ps": "quem estava no cargo no mês pm, pela folha (só o nome; sem valor por pessoa)",
    "nc": "nome civil, como está na folha (só quando é diferente de n)", "pt": "partido na eleição de 2024 (TSE), só quando o nome casou sem dúvida",
    "gn": "gênero no TSE (M/F), quando o nome casou", "pr": "1 = presidente da Câmara (pelo cargo na folha)",
    "uc": "último mês com a folha da Câmara no tribunal", "up": "último mês com a folha da Prefeitura no tribunal",
    "sc": "meses sem a folha da Câmara no tribunal (o município ainda não tinha mandado quando o robô leu)",
    "sp": "meses sem a folha da Prefeitura no tribunal (idem)",
    "zc": "meses em que a folha da Câmara veio sem o cargo de vereador",
    "f": "endereço da fonte daquela cidade",
}


def montar_site(uf, cfg):
    """site/dados/interior-cargo/<uf>.json a partir de dados/municipios_tce/<uf>/. cfg: tribunal, fonte, url, nota,
    notas, orgaos (os órgãos lidos: camara e, onde a fonte separa o prefeito, prefeitura) e link (função cod_ibge -> link
    da fonte da cidade, ou None)."""
    fontes = comum.ler_fontes(uf)
    if not len(fontes):
        log(f"TCE {uf}: nada gravado ainda em {comum.pasta(uf).relative_to(RAIZ)}")
        return None
    df = ler(uf)
    nomes = ler_nomes(uf)
    df = df.astype({"cod_ibge": int, "ano_mes": int}) if len(df) else df
    nomes = nomes.astype({"cod_ibge": int, "ano_mes": int}) if len(nomes) else nomes
    fontes = fontes.astype({"cod_ibge": int, "ano_mes": int})
    cidades = {v[0]: v for v in comum.municipios(uf).values()}
    ultimo = comum.ultimo_publicado(fontes, len(cidades)) or int(fontes.ano_mes.max())
    lidos = fontes.groupby("ano_mes").cod_ibge.nunique()
    inicio = max(comum.INICIO, min([int(mm) for mm, n in lidos.items() if n >= 0.9 * len(cidades) and mm <= ultimo]
                                   or [comum.INICIO]))
    meses_ = comum.meses(inicio, ultimo)
    df = df[df.ano_mes.isin(meses_)] if len(df) else df
    # os nomes podem ser de um mês depois de ultimo_mes (o último que a cidade já mandou): pm diz o mês
    nomes = nomes[nomes.ano_mes >= inicio] if len(nomes) else nomes
    candidatos = comum.tse(uf)
    cad = cadeiras()
    m = {}
    for cod in sorted(fontes.cod_ibge.unique()):
        f = fontes[(fontes.cod_ibge == cod) & (fontes.ano_mes.isin(meses_))]
        g = df[df.cod_ibge == cod] if len(df) else df
        gn = nomes[nomes.cod_ibge == cod] if len(nomes) else nomes
        tse_c = candidatos.get(int(cod), [])
        e = {"n": cidades.get(int(cod), (cod, str(cod)))[1]}
        if cad.get(int(cod)):
            e["cad"] = int(cad[int(cod)])
        for orgao, sigla in (("camara", "c"), ("prefeitura", "p")):
            if orgao not in cfg["orgaos"]:
                continue
            fo = f[f.orgao == orgao]
            com = {int(x) for x in fo[fo.linhas_fonte.fillna(0) > 0].ano_mes}
            e["u" + sigla] = max(com) if com else None
            sem = [mm for mm in meses_ if mm in set(fo.ano_mes) and mm not in com]
            if sem:
                e["s" + sigla] = sem
        papeis = (("vereador", "c", "camara"), ("prefeito", "pf", "prefeitura"), ("vice", "vp", "prefeitura"))
        for papel, chave, orgao in papeis:
            if orgao not in cfg["orgaos"]:
                continue
            gp = g[(g.papel == papel) & (g.orgao == orgao)] if len(g) else g
            if not len(gp):
                continue
            gnp = gn[(gn.papel == papel) & (gn.orgao == orgao)] if len(gn) else None
            e[chave] = _bloco(gp, gnp, meses_, papel, tse_c, e.get("cad") if papel == "vereador" else 1,
                              cfg.get("separa_13", False))
        if "camara" in cfg["orgaos"]:
            gv = g[(g.papel == "vereador")] if len(g) else g
            com_ver = set(gv[gv.valor_total.fillna(0) > 0].ano_mes.astype(int)) if len(gv) else set()
            fo = f[(f.orgao == "camara") & (f.linhas_fonte.fillna(0) > 0)]
            vazios = [mm for mm in meses_ if mm in set(fo.ano_mes.astype(int)) and mm not in com_ver]
            if vazios:
                e["zc"] = vazios
        link = cfg["link"](int(cod)) if cfg.get("link") else None
        if link:
            e["f"] = link
        m[str(int(cod))] = e
    papeis = ["vereador"] + (["prefeito", "vice"] if "prefeitura" in cfg["orgaos"] else [])
    saida = {"meta": {"uf": uf, "tribunal": cfg["tribunal"], "tipo": "cargo", "papeis": papeis, "fonte": cfg["fonte"],
                      "url": cfg["url"],
                      "inicio": inicio, "ultimo_mes": ultimo, "fora": [mm for mm in meses_ if mm not in lidos.index],
                      "meses": len(meses_), "gerado_em": comum.agora(), "nota": cfg["nota"], "notas": cfg.get("notas", []),
                      "fonte_partido": "TSE, candidatos de 2024 (partido da eleição, só quando o nome da folha é o de um "
                                       "único candidato da cidade, igual ou só com outra grafia: Souza/Sousa, sem o \"de\")",
                      "fonte_cadeiras": "TSE, vereadores eleitos em 2024",
                      "campos": CAMPOS},
             "m": m}
    SITE.mkdir(parents=True, exist_ok=True)
    destino = SITE / f"{uf.lower()}.json"
    tmp = destino.with_suffix(".tmp")
    tmp.write_text(json.dumps(saida, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(destino)
    log(f"TCE {uf}: {destino.relative_to(RAIZ)} ({destino.stat().st_size / 1e3:.0f} KB, {len(m)} cidades, "
        f"último mês {ultimo})")
    return saida


# ---------------------------------------------------------------- checagens
def checar(uf, saida=None):
    """Resumo no log: cidades com o cargo de vereador no último mês, quantidade x cadeiras, valor típico por vereador
    (mediana do estado), cidades em que ele passa do teto da Constituição (a conferir: é uma média, que pode ter 13º,
    férias, o presidente ou parte indenizatória) e prefeitos e vices encontrados."""
    if saida is None:
        saida = json.loads((SITE / f"{uf.lower()}.json").read_text(encoding="utf-8"))
    meta, m = saida["meta"], saida["m"]
    ult = meta["ultimo_mes"]
    pop = {v[0]: v[2] for v in comum.municipios(uf).values()}
    serie = lambda r: [v for v, n in r for _ in range(n)]
    r = {"cidades": len(m), "com_vereador_no_ultimo": 0, "quantidade_igual": 0, "quantidade_diferente": [],
         "acima_do_teto": [], "prefeitos": 0, "vices": 0, "com_nomes": 0}
    tipicos = []
    for cod, e in m.items():
        c = e.get("c")
        if c and c.get("u") == ult:
            r["com_vereador_no_ultimo"] += 1
            q = serie(c["q"])[-1]
            if q == e.get("cad"):
                r["quantidade_igual"] += 1
            else:
                r["quantidade_diferente"].append((e["n"], q, e.get("cad")))
            if c.get("ps"):
                r["com_nomes"] += 1
        if c and c.get("vm"):
            tipicos.append(c["vm"])
            teto = comum.teto_vereador(pop.get(int(cod), 0))
            v = c.get("vmr", c["vm"])
            if v > teto + 1:
                r["acima_do_teto"].append((e["n"], v, teto))
        r["prefeitos"] += 1 if (e.get("pf") or {}).get("u") == ult else 0
        r["vices"] += 1 if (e.get("vp") or {}).get("u") == ult else 0
    med = sorted(tipicos)[len(tipicos) // 2] if tipicos else None
    log(f"TCE {uf}: {r['com_vereador_no_ultimo']} de {len(m)} câmaras com o cargo de vereador em "
        f"{ult % 100:02d}/{ult // 100} ({r['quantidade_igual']} com tantas pessoas quanto cadeiras, "
        f"{len(r['quantidade_diferente'])} com número diferente; {r['com_nomes']} com os nomes); valor típico por "
        f"vereador: mediana do estado R$ {med}; acima do teto (a conferir, é uma média): {len(r['acima_do_teto'])}; "
        f"prefeito no último mês: {r['prefeitos']}, vice: {r['vices']}")
    if r["quantidade_diferente"]:
        log("  quantidade x cadeiras: " + "; ".join(f"{n}: {q} x {c}" for n, q, c in r["quantidade_diferente"][:15]))
    return r
