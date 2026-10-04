"""Parte comum dos robôs dos Tribunais de Contas: a folha de pagamento de todos os municípios de um estado.

Os municípios mandam a folha ao Tribunal de Contas do estado, e alguns tribunais publicam essa folha, com o nome de
cada pessoa, para todos os municípios de uma vez. Cada estado é um módulo desta pasta (pb.py, ce.py) com `coletar()`,
que grava em dados/municipios_tce/<uf>/ (vai para o Git) só as linhas destes cargos:

- vereadores (pagos pela Câmara), prefeito e vice-prefeito e, onde a folha diz claramente o cargo, os secretários
  municipais;
- uma linha por pessoa, órgão e mês, com o valor bruto e, quando a fonte separa, as partes do bruto (salário, 13º,
  férias, outros). Nunca o CPF (nem mascarado, nem cifrado), nunca descontos (imposto, previdência, empréstimos) e
  nunca o líquido.

Arquivos de cada estado:
- <ano>.csv: as linhas (COLUNAS), por cidade, órgão, mês e nome;
- fontes.csv: um registro por cidade, órgão e mês já lido (FONTES): quantas linhas a folha daquele órgão tinha na
  fonte (0 = o município ainda não tinha mandado a folha daquele mês ao tribunal), quantas pessoas entraram e o
  endereço da fonte.

O robô só lê o que falta: os meses que ainda não estão em fontes.csv, os que vieram vazios (o município pode mandar
depois) e os 2 últimos publicados de novo (a folha pode ser corrigida); esses dois só se a última leitura tem mais de
3 dias, para a coleta em partes não repetir o que acabou de ler. `montar_site(uf, cfg)` junta tudo com os candidatos
de 2024 do TSE (nome de urna e partido, só quando o nome casa sem dúvida) e escreve site/dados/interior/<uf>.json.
"""
import csv
import io
import json
import re
import zipfile
from datetime import datetime, timedelta

import pandas as pd

from ..config import CACHE, DADOS, RAIZ
from ..util import gravar_csv, gravar_json, log, normalizar_nome

PASTA = DADOS / "municipios_tce"
CACHE_TCE = CACHE / "tce"
SITE = RAIZ / "site" / "dados" / "interior"
INICIO = 202501
REFAZER = 2        # últimos meses publicados lidos de novo toda semana (a folha pode ser corrigida)
DIAS_RELER = 3     # ... se a última leitura tem mais de 3 dias

# orgao: camara ou prefeitura (a prefeitura inclui fundos, autarquias e secretarias); papel: vereador, prefeito, vice
# ou secretario. valor_bruto: o total pago no mês, antes dos descontos. salario, decimo (13º), ferias e outros: as
# partes do bruto, só quando a fonte separa (vazio quando não separa). unidade: a unidade gestora (PB) ou o órgão (CE)
# que pagou, como a fonte escreve.
COLUNAS = ["cod_ibge", "municipio", "orgao", "ano_mes", "nome", "cargo", "papel", "valor_bruto", "salario", "decimo",
           "ferias", "outros", "unidade"]
PARTES = ["salario", "decimo", "ferias", "outros"]
FONTES = ["cod_ibge", "orgao", "ano_mes", "linhas_fonte", "pessoas", "url", "lido_em"]
CHAVE = ["cod_ibge", "orgao", "ano_mes"]
TAMANHO_NOME = 40  # o cadastro do SIM (Ceará) guarda até 40 letras do nome

# teto do salário do vereador (Constituição, art. 29, VI): % do subsídio do deputado estadual (no máximo 75% do
# federal, R$ 46.366,19), pela população (os mesmos números de coleta/site.py)
DEPUTADO_ESTADUAL = round(46366.19 * 0.75, 2)
FAIXAS_TETO = [(10_000, 0.20), (50_000, 0.30), (100_000, 0.40), (300_000, 0.50), (500_000, 0.60), (float("inf"), 0.75)]


# ---------------------------------------------------------------- meses
def mes_mais(aaaamm, n=1):
    a, m = divmod(int(aaaamm), 100)
    t = a * 12 + (m - 1) + n
    return (t // 12) * 100 + t % 12 + 1


def meses(inicio, fim):
    saida, m = [], int(inicio)
    while m <= int(fim):
        saida.append(m)
        m = mes_mais(m)
    return saida


def agora():
    return datetime.now().strftime("%Y-%m-%dT%H:%M")


# ---------------------------------------------------------------- arquivos
def pasta(uf):
    return PASTA / uf.lower()


def _ler_csv(caminho, colunas):
    if not caminho.exists():
        return pd.DataFrame(columns=colunas)
    return pd.read_csv(caminho, dtype={"nome": str, "cargo": str, "unidade": str, "municipio": str, "url": str,
                                       "lido_em": str, "orgao": str, "papel": str})


def ler(uf):
    """Todas as linhas gravadas do estado (todos os anos)."""
    partes = [_ler_csv(a, COLUNAS) for a in sorted(pasta(uf).glob("[0-9][0-9][0-9][0-9].csv"))]
    partes = [p for p in partes if len(p)]
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=COLUNAS)


def ler_fontes(uf):
    return _ler_csv(pasta(uf) / "fontes.csv", FONTES)


def _escrever(df, caminho, colunas, ordem, motivo=None):
    """Gravação segura (util.gravar_csv): devolve False se recusou (fica o arquivo anterior)."""
    return gravar_csv(df[colunas].sort_values(ordem), caminho, float_format="%.2f", motivo=motivo)


def gravar(uf, linhas, blocos):
    """Troca, nos arquivos do estado, os blocos lidos agora (cidade, órgão, mês) pelas linhas novas.
    linhas: [dict com COLUNAS]; blocos: [dict com FONTES]. Devolve (linhas gravadas, blocos gravados)."""
    if not blocos:
        return 0, 0
    novos = pd.DataFrame(blocos, columns=FONTES).drop_duplicates(CHAVE, keep="last")
    chaves = set(zip(novos.cod_ibge.astype(int), novos.orgao, novos.ano_mes.astype(int)))
    tem = lambda df: [(int(c), o, int(m)) in chaves for c, o, m in zip(df.cod_ibge, df.orgao, df.ano_mes)]
    velhas = ler(uf)
    if len(velhas):
        velhas = velhas[[not t for t in tem(velhas)]]
    novas = pd.DataFrame(linhas, columns=COLUNAS)
    novas = novas[[t for t in tem(novas)]] if len(novas) else novas
    juntas = [x.astype({c: float for c in ["valor_bruto"] + PARTES}) for x in (velhas, novas) if len(x)]
    if juntas:
        df = pd.concat(juntas, ignore_index=True).astype({"cod_ibge": int, "ano_mes": int})
        gravados = [_escrever(g, pasta(uf) / f"{ano}.csv", COLUNAS, ["cod_ibge", "orgao", "ano_mes", "papel", "nome"])
                    for ano, g in df.groupby(df.ano_mes // 100)]
        if not all(gravados):  # recusado por perda de cobertura: os blocos não contam como lidos (são lidos de novo)
            return 0, 0
    fontes = ler_fontes(uf)
    if len(fontes):
        fontes = fontes[[not t for t in tem(fontes)]]
    fontes = pd.concat([x for x in (fontes, novos) if len(x)], ignore_index=True)
    _escrever(fontes.astype({"cod_ibge": int, "ano_mes": int}), pasta(uf) / "fontes.csv", FONTES, CHAVE)
    return len(novas), len(novos)


def ultimo_publicado(fontes, n_cidades):
    """O mês mais recente em que pelo menos metade das câmaras do estado já tem a folha no tribunal (None se nenhum)."""
    if not len(fontes):
        return None
    cam = fontes[(fontes.orgao == "camara") & (fontes.linhas_fonte.fillna(0) > 0)]
    por_mes = cam.groupby(cam.ano_mes.astype(int)).cod_ibge.nunique()
    validos = por_mes[por_mes >= n_cidades / 2]
    return int(validos.index.max()) if len(validos) else None


def blocos_a_fazer(uf, cods, orgaos, disponiveis):
    """{(cod_ibge, orgao, mes)} a ler: nunca lidos; lidos vazios (o município pode mandar depois) ou entre os REFAZER
    últimos meses publicados (e os seguintes), quando a última leitura tem mais de DIAS_RELER dias."""
    f = ler_fontes(uf)
    lidos = {}
    if len(f):
        for c, o, m, n, quando in zip(f.cod_ibge, f.orgao, f.ano_mes, f.linhas_fonte.fillna(0), f.lido_em):
            lidos[(int(c), o, int(m))] = (n, str(quando))
    ult = ultimo_publicado(f, len(set(cods)))
    recentes = {m for m in disponiveis if ult is None or m > mes_mais(ult, -REFAZER)}
    limite = (datetime.now() - timedelta(days=DIAS_RELER)).strftime("%Y-%m-%dT%H:%M")
    fazer = set()
    for c in cods:
        for o in orgaos:
            for m in disponiveis:
                k = (int(c), o, int(m))
                if k not in lidos:
                    fazer.add(k)
                elif lidos[k][1] < limite and (m in recentes or lidos[k][0] == 0):
                    fazer.add(k)
    return fazer


# ---------------------------------------------------------------- municípios (código do IBGE)
def chave_cidade(nome):
    t = normalizar_nome(nome).replace("-", " ").replace("'", " ").replace("´", " ").replace("`", " ")
    return re.sub(r"\s+", " ", t).strip()


def municipios(uf):
    """{chave do nome: (cod_ibge, nome, população)} das cidades do estado (dados/municipios/municipios.csv, do Siconfi)."""
    mu = pd.read_csv(DADOS / "municipios" / "municipios.csv")
    mu = mu[mu.uf == uf]
    return {chave_cidade(r.nome): (int(r.cod_ibge), r.nome, int(r.populacao or 0)) for r in mu.itertuples()}


def teto_vereador(populacao):
    for limite, pct in FAIXAS_TETO:
        if populacao <= limite:
            return round(DEPUTADO_ESTADUAL * pct, 2)
    return round(DEPUTADO_ESTADUAL * 0.75, 2)


# ---------------------------------------------------------------- cargos (nomes da folha)
def so_letras(cargo):
    """"00000002 - VEREADOR(A) PRESIDENTE" -> "VEREADORAPRESIDENTE" (sem o código, sem acento, só letras)."""
    t = re.sub(r"^\s*\d+\s*-\s*", "", str(cargo or ""))
    return re.sub(r"[^A-Z]", "", normalizar_nome(t))


_PREFEITO = re.compile(r"(VICE)?PREFEIT(O|A|OA)(MUNICIPAL|CONSTITUCIONAL|ELETIVO|ELE|EMEXERCICIO|INTERINO|INTERINA|"
                       r"LICENCAMEDICA)?")
_VEREADOR = re.compile(r"^(VEREADOR|VERADOR|SUPLENTEDEVEREADOR)")
_PRESIDENTE_CAMARA = re.compile(r"PRESIDENTE(DACAMARA|DACAMARAMUNICIPAL|EMEXERCICIO)?")


def papel_prefeitura(cargo):
    """"prefeito" ou "vice" quando o cargo é o de prefeito ou vice ("PREFEITO MUNICIPAL", "VICE-PREFEITO(A)"), e não um
    cargo que só tem a palavra (assessor do prefeito, chefe de gabinete do vice-prefeito, subprefeito)."""
    m = _PREFEITO.fullmatch(so_letras(cargo))
    if not m:
        return None
    return "vice" if m.group(1) else "prefeito"


def eh_vereador(cargo, eletivo=True):
    """Cargo de vereador ("VEREADOR", "VEREADOR(A) PRESIDENTE", "VEREADORES", "V E R E A D O R"...), e não de quem
    trabalha para o vereador ("ASSESSOR DE GABINETE DE VEREADOR"). "PRESIDENTE" sozinho só vale para quem está entre
    os eletivos da Câmara."""
    c = so_letras(cargo)
    return bool(_VEREADOR.match(c)) or (eletivo and bool(_PRESIDENTE_CAMARA.fullmatch(c)))


def eh_presidente(cargo):
    c = so_letras(cargo)
    return "PRESIDENTE" in c and "VICEPRESIDENTE" not in c


def titulo(nome):
    from ..vereadores.comum import titulo as _t
    return _t(re.sub(r"\s+", " ", str(nome or "")).strip())


# ---------------------------------------------------------------- TSE (candidatos de 2024)
TSE_ZIP = CACHE / "municipios" / "consulta_cand_2024.zip"  # o mesmo arquivo do robô das câmaras (municipios.py)
_CARGOS_TSE = {"11": "prefeito", "12": "vice", "13": "vereador"}


def chave_nome(nome):
    t = normalizar_nome(nome).replace(".", " ").replace("-", " ").replace("'", " ")
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z ]", "", t)).strip()


def tse(uf):
    """{cod_ibge: [{nome, urna, partido, cargo, situacao, data, genero}]}: candidatos a prefeito, vice e vereador de 2024
    (e das eleições suplementares que já estão no arquivo) de cada cidade. Do arquivo só saem nome, nome de urna,
    partido, cargo, gênero e resultado (o arquivo traz o CPF, que não é lido)."""
    from ..municipios import TSE, _NOMES_DIFERENTES
    from ..util import baixar
    if not TSE_ZIP.exists():
        log("TCE: arquivo de candidatos do TSE (~60 MB)")
        TSE_ZIP.parent.mkdir(parents=True, exist_ok=True)
        TSE_ZIP.write_bytes(baixar(TSE, timeout=600).content)
    cod = {k: v[0] for k, v in municipios(uf).items()}
    for k, v in _NOMES_DIFERENTES.items():
        if k.startswith(uf + "|"):
            cod[k.split("|", 1)[1]] = v
    saida, sem = {}, set()
    with zipfile.ZipFile(TSE_ZIP) as z, z.open(f"consulta_cand_2024_{uf}.csv") as f:
        for l in csv.DictReader(io.TextIOWrapper(f, encoding="latin1"), delimiter=";"):
            cargo = _CARGOS_TSE.get(l["CD_CARGO"])
            if not cargo:
                continue
            c = cod.get(chave_cidade(l["NM_UE"]))
            if c is None:
                sem.add(l["NM_UE"])
                continue
            sit = l["DS_SIT_TOT_TURNO"]
            situacao = ("eleito" if sit in ("ELEITO", "ELEITO POR QP", "ELEITO POR MÉDIA") else
                        "suplente" if sit == "SUPLENTE" else "turno" if sit == "2º TURNO" else "outro")
            d, m, a = l["DT_ELEICAO"].split("/")
            saida.setdefault(c, []).append({"sq": l["SQ_CANDIDATO"], "nome": l["NM_CANDIDATO"].strip(),
                                            "urna": l["NM_URNA_CANDIDATO"].strip(), "partido": l["SG_PARTIDO"],
                                            "cargo": cargo, "situacao": situacao, "data": f"{a}{m}{d}",
                                            "turno": l["NR_TURNO"], "genero": l["DS_GENERO"][:1]})
    if sem:
        log(f"  TSE {uf}: {len(sem)} cidades sem código do IBGE: {', '.join(sorted(sem)[:10])}")
    # o 2º turno repete o candidato: fica a linha com o resultado final (a do maior turno)
    for c, lista in saida.items():
        melhor = {}
        for x in lista:
            if x["sq"] not in melhor or x["turno"] > melhor[x["sq"]]["turno"]:
                melhor[x["sq"]] = x
        saida[c] = list(melhor.values())
    return saida


_PARTICULAS = {"DE", "DA", "DO", "DAS", "DOS", "E", "D"}


def chave_forte(nome):
    """Para casar o mesmo nome escrito de jeitos um pouco diferentes na folha e no TSE: sem as partículas (de, da,
    dos...), com S = Z, I = Y, V = W, F = PH, T = TH e sem letras dobradas ("Maria de Souza" = "Maria Sousa")."""
    t = " ".join(p for p in chave_nome(nome).split() if p not in _PARTICULAS)
    for a, b in (("PH", "F"), ("TH", "T"), ("Y", "I"), ("W", "V"), ("Z", "S")):
        t = t.replace(a, b)
    return re.sub(r"([A-Z])\1+", r"\1", t)


_CARGO_OK = {"vereador": lambda c: c["cargo"] == "vereador" and c["situacao"] in ("eleito", "suplente"),
             "prefeito": lambda c: c["cargo"] in ("prefeito", "vice") and c["situacao"] == "eleito",
             "vice": lambda c: c["cargo"] == "vice" and c["situacao"] == "eleito"}


def casar_tse(nome, papel, candidatos, truncado=False, forte=False, excluir=()):
    """O candidato do TSE da mesma cidade com o mesmo nome civil, só se for um só (homônimo = sem partido) e o cargo
    bater: vereador com eleito ou suplente a vereador; prefeito com o prefeito eleito (ou o vice eleito, que assume);
    vice com o vice eleito. Primeiro o nome exato (sem acentos e pontuação). `truncado`: o nome da folha está cortado
    (cadastro de 40 letras no Ceará): vale o começo do nome, se tiver pelo menos 30 letras. `forte`: sem o exato,
    vale o nome com pelo menos 3 partes que só muda na grafia (chave_forte), entre os candidatos que não casaram com
    outra pessoa da folha (`excluir`, os SQ já usados). Senão, None."""
    k = chave_nome(nome)
    ok = _CARGO_OK.get(papel)
    if not k or not candidatos or not ok:
        return None
    regras = ["exato"] + (["cortado"] if truncado and len(k) >= 30 else []) + (["forte"] if forte else [])
    for regra in regras:
        if regra == "exato":
            achados = [c for c in candidatos if chave_nome(c["nome"]) == k]
        elif regra == "cortado":
            achados = [c for c in candidatos if chave_nome(c["nome"]).startswith(k)]
        else:
            kf = chave_forte(nome)
            if len(kf.split()) < 3:
                return None
            achados = [c for c in candidatos if chave_forte(c["nome"]) == kf and c["sq"] not in excluir]
        if not achados:
            continue
        # a mesma pessoa pode ser candidata duas vezes (eleição de 2024 e suplementar): conta como uma, se o partido
        # é o mesmo
        if len({(chave_forte(c["nome"]), c["partido"]) for c in achados}) != 1:
            return None
        validos = sorted([c for c in achados if ok(c)], key=lambda c: c["data"])
        return validos[-1] if validos else None
    return None


# ---------------------------------------------------------------- site
def _r(v):
    return None if v is None or pd.isna(v) else int(round(float(v)))


def rle(serie):
    """[6000, 6000, None, 6500] -> [[6000, 2], [None, 1], [6500, 1]]: cada par é um valor e quantos meses seguidos ele
    se repete (a série quase sempre é o mesmo valor todo mês)."""
    saida = []
    for v in serie:
        if saida and saida[-1][0] == v:
            saida[-1][1] += 1
        else:
            saida.append([v, 1])
    return saida


def _pessoas(g, meses_, ultimo, tse_cidade, papel_padrao, nome_cortado):
    """Uma entrada por pessoa (ver CAMPOS)."""
    saida = []
    idx = {m: i for i, m in enumerate(meses_)}
    # primeiro quem casa pelo nome exato; depois, pela grafia (chave_forte), só com os candidatos que sobraram
    papeis = {nome: gp[gp.ano_mes == gp.ano_mes.max()].papel.iloc[0] for nome, gp in g.groupby("nome", sort=False)}
    talvez = lambda n: nome_cortado and len(n) >= 35
    exatos = {n: casar_tse(n, p, tse_cidade, truncado=talvez(n)) for n, p in papeis.items()}
    usados = {c["sq"] for c in exatos.values() if c}
    for nome, gp in g.groupby("nome", sort=False):
        por_mes = gp.groupby("ano_mes").agg(valor_bruto=("valor_bruto", "sum"),
                                            decimo=("decimo", lambda s: s.sum(min_count=1)))
        t = [None] * len(meses_)
        d = [None] * len(meses_)
        for m, r in por_mes.iterrows():
            if int(m) in idx:
                t[idx[int(m)]] = _r(r.valor_bruto)
                if pd.notna(r.decimo) and r.decimo > 0:
                    d[idx[int(m)]] = _r(r.decimo)
        ult = gp[gp.ano_mes == gp.ano_mes.max()]
        cargos = [re.sub(r"^\s*\d+\s*-\s*", "", c).strip() for x in ult.cargo.astype(str) for c in x.split(" / ")]
        cargo = " / ".join(dict.fromkeys(cargos))
        papel = ult.papel.iloc[0] if len(ult) else papel_padrao
        # nome cortado: com 40 letras, é certo (o campo do cadastro do Ceará); com 35 ou mais, pode ser (o sistema do
        # município corta antes): vale o começo do nome para casar com o TSE, e o "…" só quando é certo
        cortado = nome_cortado and len(nome) >= TAMANHO_NOME
        c = exatos.get(nome) or casar_tse(nome, papel, tse_cidade, truncado=talvez(nome), forte=True, excluir=usados)
        if c and not exatos.get(nome):
            usados.add(c["sq"])
        if c:
            # o nome completo do TSE só quando o da folha está cortado; senão, o da folha
            completo = c["nome"] if nome_cortado and chave_nome(c["nome"]).startswith(chave_nome(nome)) else nome
            e = {"n": titulo(c["urna"]), "nc": titulo(completo), "pt": c["partido"]}
            if c.get("genero") in ("M", "F"):
                e["gn"] = c["genero"]
        else:
            e = {"n": titulo(nome) + ("…" if cortado else "")}
        if e.get("nc") == e["n"]:
            del e["nc"]
        e["g"] = cargo
        if papel == "vereador" and eh_presidente(cargo):
            e["pr"] = 1
        e["x"] = 1 if ultimo is not None and int(gp.ano_mes.max()) == ultimo else 0
        e["t"] = rle(t)
        if any(v is not None for v in d):
            e["d"] = rle(d)
        saida.append(e)
    return sorted(saida, key=lambda e: (-e["x"], normalizar_nome(e["n"])))


CAMPOS = {
    "m": "cidades, pelo código do IBGE",
    "n": "nome (na cidade: o nome da cidade; na pessoa: o nome de urna em 2024, quando casou com o TSE, senão o nome da folha)",
    "nc": "nome civil, como está na folha (ou o completo do TSE, quando a folha corta o nome); só quando é diferente de n",
    "pt": "partido na eleição de 2024 (TSE), só quando o nome casou sem dúvida",
    "gn": "gênero no TSE (M/F), quando o nome casou (a folha às vezes escreve VEREADORA para todos)",
    "g": "cargo como está na folha (último mês)",
    "pr": "1 = presidente da Câmara (pelo cargo na folha)",
    "x": "1 = está na folha do último mês da cidade (uc para vereadores, up para prefeito, vice e secretários)",
    "t": "valor bruto de cada mês, em reais, de meta.inicio a meta.ultimo_mes, em pares [valor, meses seguidos] "
         "([[null, 2], [6000, 18]] = sem valor em jan e fev/2025, R$ 6.000 nos 18 meses seguintes; null = não aparece)",
    "d": "13º salário dentro do bruto de cada mês, no mesmo formato de t (só quando a fonte separa e houve)",
    "uc": "último mês com vereadores na folha da Câmara",
    "up": "último mês com prefeito, vice ou secretário na folha da Prefeitura",
    "sc": "meses sem a folha da Câmara no tribunal (o município ainda não tinha mandado quando o robô leu)",
    "sp": "meses sem a folha da Prefeitura no tribunal (idem)",
    "zc": "meses em que a folha da Câmara veio sem nenhum vereador",
    "zp": "meses em que a folha da Prefeitura veio sem prefeito, vice nem secretário",
    "v": "vereadores", "pf": "prefeito (mais de um, se mudou)", "vp": "vice-prefeito",
    "sec": "secretários municipais (só onde a folha diz o cargo)",
    "f": "endereço da fonte daquela cidade",
    "fora": "(meta) meses do período que o tribunal não publicou para nenhuma cidade (na Paraíba, dez/2025)",
}


def montar_site(uf, cfg):
    """site/dados/interior/<uf>.json a partir de dados/municipios_tce/<uf>/. cfg: tribunal, fonte, url, nota, notas,
    secretarios (bool), nome_cortado (bool: o nome pode vir cortado) e link_da_fonte (bool: cada cidade leva o endereço
    da fonte do último mês da Câmara)."""
    df = ler(uf)
    fontes = ler_fontes(uf)
    if not len(fontes):
        log(f"TCE {uf}: nada gravado ainda em {pasta(uf).relative_to(RAIZ)}")
        return None
    df = df.astype({"cod_ibge": int, "ano_mes": int}) if len(df) else df
    fontes = fontes.astype({"cod_ibge": int, "ano_mes": int})
    cidades = {v[0]: v for v in municipios(uf).values()}
    ultimo = ultimo_publicado(fontes, len(cidades)) or int(fontes.ano_mes.max())
    # o primeiro mês já lido em pelo menos 90% das cidades (enquanto a primeira leitura não chega a jan/2025, os
    # meses mais antigos ficam fora do site)
    lidos = fontes.groupby("ano_mes").cod_ibge.nunique()
    inicio = max(INICIO, min([int(mm) for mm, n in lidos.items() if n >= 0.9 * len(cidades) and mm <= ultimo] or [INICIO]))
    meses_ = meses(inicio, ultimo)
    df = df[df.ano_mes <= ultimo] if len(df) else df
    candidatos = tse(uf)
    m = {}
    for cod in sorted(fontes.cod_ibge.unique()):
        f = fontes[(fontes.cod_ibge == cod) & (fontes.ano_mes.isin(meses_))]
        g = df[df.cod_ibge == cod] if len(df) else df
        tse_c = candidatos.get(int(cod), [])
        e = {"n": cidades.get(int(cod), (cod, str(cod)))[1]}
        for orgao, sigla in (("camara", "c"), ("prefeitura", "p")):
            fo = f[f.orgao == orgao]
            com = set(fo[fo.linhas_fonte > 0].ano_mes)
            com_gente = set(g[g.orgao == orgao].ano_mes) if len(g) else set()
            e["u" + sigla] = int(max(com_gente)) if com_gente else None
            # sem a folha: o mês foi lido e o município ainda não tinha mandado (mês ainda não lido não entra)
            sem = [mm for mm in meses_ if mm in set(fo.ano_mes) and mm not in com]
            if sem:
                e["s" + sigla] = sem
            vazios = [mm for mm in meses_ if mm in com and mm not in com_gente]
            if vazios:
                e["z" + sigla] = vazios
        gv = g[(g.orgao == "camara") & (g.papel == "vereador")] if len(g) else g
        e["v"] = _pessoas(gv, meses_, e["uc"], tse_c, "vereador", cfg.get("nome_cortado")) if len(gv) else []
        for papel, chave in (("prefeito", "pf"), ("vice", "vp")):
            gp = g[g.papel == papel] if len(g) else g
            e[chave] = _pessoas(gp, meses_, e["up"], tse_c, papel, cfg.get("nome_cortado")) if len(gp) else []
        if cfg.get("secretarios"):
            gs = g[g.papel == "secretario"] if len(g) else g
            e["sec"] = _pessoas(gs, meses_, e["up"], [], "secretario", cfg.get("nome_cortado")) if len(gs) else []
        if cfg.get("link_da_fonte"):
            fc = f[(f.orgao == "camara") & (f.linhas_fonte > 0)].sort_values("ano_mes")
            if len(fc) and isinstance(fc.url.iloc[-1], str):
                e["f"] = fc.url.iloc[-1]
        m[str(int(cod))] = e
    saida = {"meta": {"uf": uf, "tribunal": cfg["tribunal"], "fonte": cfg["fonte"], "url": cfg["url"],
                      "inicio": inicio, "ultimo_mes": ultimo,
                      "fora": [mm for mm in meses_ if mm not in lidos.index], "meses": len(meses_), "gerado_em": agora(),
                      "nota": cfg["nota"], "notas": cfg.get("notas", []),
                      "fonte_partido": "TSE, candidatos de 2024 (partido da eleição, só quando o nome da folha é o "
                                       "de um único candidato da cidade, igual ou só com outra grafia: Souza/Sousa, "
                                       "sem o \"de\")",
                      "campos": CAMPOS},
             "m": m}
    SITE.mkdir(parents=True, exist_ok=True)
    destino = SITE / f"{uf.lower()}.json"
    if gravar_json(destino, saida):
        log(f"TCE {uf}: {destino.relative_to(RAIZ)} ({destino.stat().st_size / 1e3:.0f} KB, {len(m)} cidades, "
            f"último mês {ultimo})")
    return saida


# ---------------------------------------------------------------- checagens
def checar(uf, saida=None):
    """Checagens de sanidade: vereadores no último mês x cadeiras (eleitos em 2024, TSE), cidades sem prefeito, valores
    acima do teto constitucional do vereador (a conferir, não é erro: o bruto pode ter 13º, férias ou atrasados) e
    nomes que casaram com o TSE. Devolve um dict e escreve o resumo no log."""
    if saida is None:
        saida = json.loads((SITE / f"{uf.lower()}.json").read_text(encoding="utf-8"))
    meta, m = saida["meta"], saida["m"]
    meses_ = meses(meta["inicio"], meta["ultimo_mes"])
    ver = pd.read_csv(DADOS / "municipios" / "vereadores.csv")
    cadeiras = ver.groupby("cod_ibge").size().to_dict()
    pop = {v[0]: v[2] for v in municipios(uf).values()}
    r = {"cidades": len(m), "cadeiras_diferentes": [], "sem_vereador_no_ultimo": [], "sem_prefeito_no_ultimo": [],
         "acima_do_teto": [], "acima_do_teto_no_mes": [], "vereadores_no_cargo": 0, "com_partido": 0, "prefeitos_com_partido": 0, "prefeitos": 0,
         "vices": 0, "secretarios": 0, "cidades_com_secretarios": 0, "cidades_por_mes": {}}
    serie = lambda p: [v for v, n in p["t"] for _ in range(n)]
    for i, mm in enumerate(meses_):
        r["cidades_por_mes"][mm] = sum(1 for e in m.values() if any(serie(p)[i] is not None for p in e["v"]))
    for cod, e in m.items():
        no = [p for p in e["v"] if p["x"]]
        r["vereadores_no_cargo"] += len(no)
        r["com_partido"] += sum(1 for p in no if p.get("pt"))
        if e.get("uc") != meta["ultimo_mes"]:
            r["sem_vereador_no_ultimo"].append((e["n"], e.get("uc")))
        elif len(no) != cadeiras.get(int(cod), 0):
            r["cadeiras_diferentes"].append((e["n"], len(no), cadeiras.get(int(cod), 0)))
        pf = [p for p in e["pf"] if p["x"]]
        r["prefeitos"] += len(pf)
        r["vices"] += sum(1 for p in e["vp"] if p["x"])
        sec = [p for p in e.get("sec", []) if p["x"]]
        r["secretarios"] += len(sec)
        r["cidades_com_secretarios"] += 1 if sec else 0
        r["prefeitos_com_partido"] += sum(1 for p in pf if p.get("pt"))
        if not pf or e.get("up") != meta["ultimo_mes"]:
            r["sem_prefeito_no_ultimo"].append((e["n"], e.get("up")))
        teto = teto_vereador(pop.get(int(cod), 0))
        for p in e["v"]:
            valores = [v for v in serie(p) if v is not None]
            if not valores:
                continue
            mediano = sorted(valores)[len(valores) // 2]
            if mediano > teto + 1:  # o valor de todo mês passa do teto
                r["acima_do_teto"].append((e["n"], p.get("nc", p["n"]), "todo mês", mediano, teto, p.get("pr", 0)))
            else:
                for i, v in enumerate(serie(p)):
                    if v is not None and v > teto + 1:
                        r["acima_do_teto_no_mes"].append((e["n"], p.get("nc", p["n"]), meses_[i], v, teto, p.get("pr", 0)))
    log(f"TCE {uf}: {r['vereadores_no_cargo']} vereadores no cargo ({r['com_partido']} com partido), "
        f"{r['prefeitos']} prefeitos ({r['prefeitos_com_partido']} com partido), {r['vices']} vices, "
        f"{r['secretarios']} secretários em {r['cidades_com_secretarios']} cidades; cidades com vereadores por mês: "
        + ", ".join(f"{k % 100:02d}/{k // 100}: {v}" for k, v in r["cidades_por_mes"].items()))
    log(f"  sem vereadores no último mês: {len(r['sem_vereador_no_ultimo'])}; número diferente das cadeiras: "
        f"{len(r['cadeiras_diferentes'])}; sem prefeito no último mês: {len(r['sem_prefeito_no_ultimo'])}; "
        f"vereadores acima do teto todo mês (a conferir): {len(r['acima_do_teto'])}, dos quais "
        f"{sum(1 for x in r['acima_do_teto'] if x[5])} presidentes da Câmara; meses isolados acima do teto: "
        f"{len(r['acima_do_teto_no_mes'])}")
    return r
