"""TCE-ES: o total pago aos vereadores, ao prefeito e ao vice de cada município do Espírito Santo (78 municípios), mês a
mês, e os nomes de quem estava em cada cargo.

Fonte: Portal de Dados Abertos do Governo do Espírito Santo (https://dados.es.gov.br/), conjunto "Área temática:
pessoal" do Tribunal de Contas (TCE-ES), com o que cada órgão estadual e municipal manda ao Tribunal pelo sistema
CidadES. O robots.txt do portal (CKAN) não deixa robôs usarem a API (/api/) e pede 10 s entre os pedidos: os arquivos
são achados pela página do conjunto (util.recursos_ckan) e baixados de lá. Dois arquivos interessam, atualizados todo
dia:

- "Vantagens e descontos AAAA - Nº semestre" (ZIP com um CSV, ~10 a 30 MB): para cada unidade gestora (Câmara,
  Prefeitura, fundos, secretarias), mês, cargo, tipo de vínculo e verba (subsídio, 13º, férias, auxílio-alimentação,
  imposto, empréstimo...), o valor somado de todas as pessoas. Sem nomes e sem quantidade de pessoas. O CSV tem o cargo
  sem aspas, às vezes com ";" ou quebra de linha dentro: cada registro é montado pelas 4 primeiras e as 5 últimas
  colunas (ver _registros);
- "Vínculo AAAA - Nº trimestre" (CSV de ~200 MB): cada pessoa com vínculo em cada mês (nome, CPF mascarado, unidade,
  cargo, tipo de vínculo). Daqui sai a quantidade de pessoas em cada cargo e os nomes. O CPF não é lido.

Só o tipo de vínculo eletivo interessa ("Cargo político derivado de mandato eletivo" no primeiro arquivo, "Eletivo" no
segundo): na Câmara, com o cargo de vereador ou de presidente da Câmara (vereador); fora da Câmara, com o cargo de
prefeito ou vice (cargo.papel_prefeitura). O total é a soma das vantagens (remuneratórias e indenizatórias), sem os
descontos; a parte indenizatória, o 13º e as férias ficam separados quando a verba diz. Cada município classifica as
verbas do seu jeito (a Câmara de Vitória põe o subsídio como "Outros adicionais"), por isso o total é a soma de todas.

Cada arquivo só é baixado de novo quando muda (ETag; o portal entrega os arquivos de um armazenamento S3, que responde
304 quando não mudou), e o que interessa dele fica num extrato pequeno no cache (dados/cache/tce/es/); o arquivo grande
é apagado depois de lido. Um arquivo que não baixou deixa os meses dele como estavam.
"""
import csv
import io
import json
import re
import zipfile

import pandas as pd

from ..config import HOJE
from ..util import TempoEsgotado, _sessao, _texto_perdas, log, normalizar_nome, perdas_de_cobertura, recursos_ckan, verificar_prazo
from . import cargo, comum

UF = "ES"
PAGINA = "https://dados.es.gov.br/dataset/area-tematica-pessoal"
CACHE = comum.CACHE_TCE / "es"
ELETIVO_VANT = "Cargo político derivado de mandato eletivo"
ELETIVO_VINC = "Eletivo"
_NUM = re.compile(r"^-?\d+(,\d+)?$")
_ARQ = [("vantagens", re.compile(r"Vantagens e descontos (\d{4}) - (\d)º semestre"), 6),
        ("vinculo", re.compile(r"V[íi]nculo (\d{4}) - (\d)º trimestre"), 3)]


def _orgao(ug):
    return "camara" if normalizar_nome(ug).startswith("CAMARA") else "prefeitura"


def _papel(orgao, cargo_):
    return cargo.papel_camara(cargo_) if orgao == "camara" else cargo.papel_prefeitura(cargo_)


def arquivos():
    """[(tipo, ano, parte, nome, url)] dos arquivos de 2025 em diante, pela página do conjunto de dados."""
    saida = []
    for r in recursos_ckan(PAGINA):
        for tipo, rx, meses_por in _ARQ:
            m = rx.fullmatch(r["name"].strip())
            if not m:
                continue
            ano, parte = int(m.group(1)), int(m.group(2))
            ultimo_mes = ano * 100 + parte * meses_por
            if ultimo_mes >= comum.INICIO:
                saida.append((tipo, ano, parte, f"{tipo}-{ano}-{parte}", r["url"]))
    return saida


# ---------------------------------------------------------------- leitura dos arquivos
def _registros(arquivo):
    """Os registros do CSV de vantagens e descontos (dentro do ZIP): [esfera, unidade, ano, mês, cargo, vínculo,
    natureza, tipo, verba, valor]. O cargo pode ter ";" e quebra de linha sem aspas: junta as linhas até ter 10 colunas
    ou mais, com um número na última, e o cargo é o que fica entre as 4 primeiras e as 5 últimas."""
    with zipfile.ZipFile(arquivo) as z:
        nome = next(i.filename for i in z.infolist() if i.filename.lower().endswith(".csv"))
        with z.open(nome) as f:
            texto = io.TextIOWrapper(f, encoding="latin1", newline="")
            next(texto)  # cabeçalho
            buf = ""
            for n, linha in enumerate(texto):
                if n % 200000 == 0:
                    verificar_prazo()
                linha = linha.rstrip("\r\n")
                buf = f"{buf} {linha}" if buf else linha
                p = buf.split(";")
                if len(p) >= 10 and _NUM.match(p[-1].strip()):
                    yield p[:4] + [";".join(p[4:-5])] + p[-5:]
                    buf = ""


def extrair_vantagens(arquivo):
    """(eletivos, contagem): as vantagens do vínculo eletivo, somadas por unidade, mês, cargo, natureza e verba; e
    quantas linhas cada unidade municipal tinha em cada mês (para saber se o município mandou a folha)."""
    soma, contagem = {}, {}
    for esfera, ug, ano, mes, cargo_, vinculo, natureza, tipo, verba, valor in _registros(arquivo):
        if esfera.startswith("Estado do"):
            continue
        am = int(ano) * 100 + int(mes)
        k = (esfera, ug, am)
        contagem[k] = contagem.get(k, 0) + 1
        if vinculo.strip() != ELETIVO_VANT or tipo.strip() != "Vantagem":
            continue
        k = (esfera, ug, am, cargo.limpar_cargo(cargo_), natureza.strip(), verba.strip())
        soma[k] = soma.get(k, 0.0) + float(valor.replace(",", "."))
    el = pd.DataFrame([(*k, round(v, 2)) for k, v in soma.items()],
                      columns=["esfera", "ug", "ano_mes", "cargo", "natureza", "verba", "valor"])
    ct = pd.DataFrame([(*k, v) for k, v in contagem.items()], columns=["esfera", "ug", "ano_mes", "linhas"])
    return el, ct


def extrair_vinculo(arquivo):
    """As pessoas com vínculo eletivo em unidades municipais: município, unidade, mês, cargo e nome (o CPF, que vem
    mascarado, não é lido)."""
    saida = set()
    with open(arquivo, encoding="latin1", newline="") as f:
        leitor = csv.reader(f, delimiter=";")
        cab = next(leitor)
        i = {c.strip().lstrip("﻿"): k for k, c in enumerate(cab)}
        iN, iM, iU, iC, iT, iA, iMes = (i["NomeServidor"], i["Município"], i["NomeUnidadeGestora"], i["NomeCargo"],
                                        i["TipoVinculo"], i["AnoReferencia"], i["MesReferencia"])
        for n, l in enumerate(leitor):
            if n % 200000 == 0:
                verificar_prazo()
            if len(l) <= iMes or l[iT].strip() != ELETIVO_VINC or l[iM].startswith("Estado do"):
                continue
            saida.add((l[iM].strip(), l[iU].strip(), int(l[iA]) * 100 + int(l[iMes]), cargo.limpar_cargo(l[iC]),
                       re.sub(r"\s+", " ", l[iN]).strip().upper()))
    return pd.DataFrame(sorted(saida), columns=["esfera", "ug", "ano_mes", "cargo", "nome"])


def _estado():
    a = CACHE / "arquivos.json"
    return json.loads(a.read_text()) if a.exists() else {}


def _extratos(nome, tipo):
    base = CACHE / nome
    if tipo == "vantagens":
        return [base.with_suffix(".eletivos.csv"), base.with_suffix(".contagem.csv")]
    return [base.with_suffix(".eletivos.csv")]


def atualizar(tipo, nome, url):
    """Baixa o arquivo se mudou (ETag) e refaz o extrato. Devolve True se o extrato existe (novo ou de antes)."""
    estado = _estado()
    antes = estado.get(nome, {})
    extratos = _extratos(nome, tipo)
    tem = all(e.exists() for e in extratos)
    cab = {"If-None-Match": antes["etag"]} if antes.get("etag") and tem else {}
    CACHE.mkdir(parents=True, exist_ok=True)
    r = _sessao().get(url, headers=cab, stream=True, timeout=600)
    if r.status_code == 304:
        r.close()
        return True
    r.raise_for_status()
    bruto = CACHE / (nome + (".zip" if tipo == "vantagens" else ".csv"))
    parcial = bruto.with_suffix(bruto.suffix + ".part")
    with open(parcial, "wb") as f:
        for pedaco in r.iter_content(1 << 20):
            f.write(pedaco)
            verificar_prazo()
    parcial.replace(bruto)
    etag = r.headers.get("ETag")
    if etag and etag == antes.get("etag") and tem:
        bruto.unlink()
        return True
    log(f"  TCE-ES: {nome} ({bruto.stat().st_size / 1e6:.0f} MB, atualizado em {r.headers.get('Last-Modified')})")
    try:
        trocar_extratos(nome, list(zip(extrair_vantagens(bruto) if tipo == "vantagens" else [extrair_vinculo(bruto)],
                                       extratos)))
    finally:
        bruto.unlink()  # o arquivo grande não fica no cache: só o extrato
    estado = _estado()
    estado[nome] = {"etag": etag, "modificado": r.headers.get("Last-Modified"), "lido_em": comum.agora()}
    (CACHE / "arquivos.json").write_text(json.dumps(estado, indent=1))
    return True


def trocar_extratos(nome, novos, entidade="esfera"):
    """Troca os extratos do arquivo (todos ou nenhum). Extrato vazio é falha (o arquivo do Tribunal veio só com o
    cabeçalho); extrato que perde cobertura em relação ao anterior (um mês que some, mais de 20% dos municípios de um
    mês) também: o erro sobe, e quem chama fica com o extrato anterior (ou deixa os meses como estavam)."""
    vazios = [arq.name for df, arq in novos if not len(df)]
    if vazios:
        raise RuntimeError(f"{nome}: o arquivo veio sem linhas ({', '.join(vazios)})")
    tmps = []
    try:
        for df, arq in novos:
            tmp = arq.parent / f".novo.{arq.name}"
            df.to_csv(tmp, index=False)
            tmps.append((tmp, arq))
        perdas = [p for tmp, arq in tmps if arq.exists()
                  for p in perdas_de_cobertura(arq, tmp, entidade=entidade if "esfera" in pd.read_csv(tmp, nrows=0).columns else None)]
        if perdas:
            raise RuntimeError(f"{nome}: o extrato novo perde cobertura ({_texto_perdas(perdas)})")
        for tmp, arq in tmps:
            tmp.replace(arq)
    finally:
        for tmp, _ in tmps:
            if tmp.exists():
                tmp.unlink()


# ---------------------------------------------------------------- montagem
def _cidades():
    return comum.municipios(UF)


def coletar():
    cidades = _cidades()
    cods = sorted({v[0] for v in cidades.values()})
    vant, cont, vinc, sem = [], [], [], set()
    erros = []
    vinc_falhou = set()  # meses dos arquivos de vínculo que não baixaram e não têm extrato de antes
    for tipo, ano, parte, nome, url in arquivos():
        try:
            atualizar(tipo, nome, url)
        except TempoEsgotado:
            raise
        except Exception as e:  # noqa: BLE001 — um arquivo que não baixou deixa os meses dele como estavam
            erros.append(f"{nome}: {e}")
            ex = _extratos(nome, tipo)
            if all(x.exists() for x in ex):  # o extrato da leitura anterior (o último dado bom) continua valendo
                log(f"  TCE-ES: {nome} não baixou ({e}); fica o extrato da leitura anterior")
            else:
                if tipo == "vinculo":
                    vinc_falhou |= {ano * 100 + m for m in range((parte - 1) * 3 + 1, parte * 3 + 1)}
                log(f"  TCE-ES: {nome} não baixou ({e}); os meses dele ficam como estavam")
                continue
        ex = _extratos(nome, tipo)
        if tipo == "vantagens":
            vant.append(pd.read_csv(ex[0], dtype={"cargo": str, "verba": str}))
            cont.append(pd.read_csv(ex[1]))
        else:
            vinc.append(pd.read_csv(ex[0], dtype={"cargo": str, "nome": str}))
    if not cont:
        raise RuntimeError("TCE-ES: nenhum arquivo de vantagens: " + "; ".join(erros))
    vant, cont = pd.concat(vant, ignore_index=True), pd.concat(cont, ignore_index=True)
    vinc = pd.concat(vinc, ignore_index=True) if vinc else pd.DataFrame(columns=["esfera", "ug", "ano_mes", "cargo", "nome"])

    def cod(esfera):
        c = cidades.get(comum.chave_cidade(esfera))
        if c is None:
            sem.add(esfera)
        return c[0] if c else None
    for df in (vant, cont, vinc):
        df["cod_ibge"] = df.esfera.map(cod)
        df["orgao"] = df.ug.map(_orgao)
    if sem:
        log(f"  TCE-ES: {len(sem)} municípios sem código do IBGE: {', '.join(sorted(map(str, sem)))}")
    vant = vant[vant.cod_ibge.notna()].copy()
    cont = cont[cont.cod_ibge.notna()]
    vinc = vinc[vinc.cod_ibge.notna()].copy()
    vant["papel"] = [_papel(o, c) for o, c in zip(vant.orgao, vant.cargo)]
    vinc["papel"] = [_papel(o, c) for o, c in zip(vinc.orgao, vinc.cargo)]
    fora = vant[vant.papel.isna() & (vant.orgao == "camara")]
    if len(fora):
        log(f"  TCE-ES: cargos eletivos na Câmara que não são de vereador (fora): "
            + ", ".join(sorted(set(fora.cargo))[:10]))
    vant, vinc = vant[vant.papel.notna()], vinc[vinc.papel.notna()]
    meses_vinc = set(vinc.ano_mes.astype(int))
    ultimo_mes = HOJE.year * 100 + HOJE.month
    # linhas: uma por cidade, órgão, mês e papel (os cargos do papel juntos: VEREADOR e VEREADOR PRESIDENTE, por exemplo)
    linhas = []
    pessoas = vinc.groupby(["cod_ibge", "orgao", "ano_mes", "papel"]).nome.nunique().to_dict()
    # meses cujo vínculo não baixou: a quantidade gravada antes continua (não vira "sem quantidade")
    antes = cargo.ler(UF)
    q_antes = ({(int(c), o, int(m), p): q for c, o, m, p, q in
                zip(antes.cod_ibge, antes.orgao, antes.ano_mes, antes.papel, antes.quantidade) if int(m) in vinc_falhou}
               if vinc_falhou and len(antes) else {})
    for (c, o, am, papel), g in vant.groupby(["cod_ibge", "orgao", "ano_mes", "papel"]):
        nat, verba = g.natureza.fillna(""), g.verba.fillna("").map(normalizar_nome)
        q = pessoas.get((c, o, am, papel))
        if int(am) in vinc_falhou:
            q = q_antes.get((int(c), o, int(am), papel))
            q = None if q is None or pd.isna(q) else int(q)
        linhas.append({"cod_ibge": int(c), "municipio": cidades[comum.chave_cidade(g.esfera.iloc[0])][1], "orgao": o,
                       "ano_mes": int(am), "papel": papel, "cargo": " / ".join(dict.fromkeys(g.cargo)),
                       "quantidade": q if q is not None else (None if int(am) not in meses_vinc else 0),
                       "valor_total": round(g.valor.sum(), 2),
                       "indenizatorio": round(g.valor[nat.str.startswith("Indeniz")].sum(), 2),
                       "decimo": round(g.valor[verba.str.contains(r"13")].sum(), 2),
                       "ferias": round(g.valor[verba.str.contains("FERIAS")].sum(), 2),
                       "unidade": " / ".join(dict.fromkeys(g.ug))})
    # quem está no vínculo eletivo e não aparece nas vantagens do mês (não recebeu pelo cargo eletivo, ou o município
    # ainda não mandou as vantagens): entra com a quantidade e sem valor
    com_valor = {(l["cod_ibge"], l["orgao"], l["ano_mes"], l["papel"]) for l in linhas}
    sem_valor = [k for k in pessoas if (int(k[0]), k[1], int(k[2]), k[3]) not in com_valor]
    for (c, o, am, papel), g in vinc.groupby(["cod_ibge", "orgao", "ano_mes", "papel"]):
        if (int(c), o, int(am), papel) in com_valor:
            continue
        linhas.append({"cod_ibge": int(c), "municipio": cidades[comum.chave_cidade(g.esfera.iloc[0])][1], "orgao": o,
                       "ano_mes": int(am), "papel": papel, "cargo": " / ".join(dict.fromkeys(g.cargo)),
                       "quantidade": g.nome.nunique(), "valor_total": None, "indenizatorio": None, "decimo": None,
                       "ferias": None, "unidade": " / ".join(dict.fromkeys(g.ug))})
    # meses cujo vínculo não baixou: as linhas só de vínculo (pessoas no cargo, sem valor no mês) gravadas antes ficam
    if vinc_falhou and len(antes):
        com_linha = {(l["cod_ibge"], l["orgao"], l["ano_mes"], l["papel"]) for l in linhas}
        for r in antes[antes.ano_mes.astype(int).isin(vinc_falhou) & antes.valor_total.isna()].to_dict("records"):
            if (int(r["cod_ibge"]), r["orgao"], int(r["ano_mes"]), r["papel"]) not in com_linha:
                linhas.append({**r, "cod_ibge": int(r["cod_ibge"]), "ano_mes": int(r["ano_mes"]),
                               "quantidade": None if pd.isna(r["quantidade"]) else int(r["quantidade"])})
    # blocos: todos os meses com a folha de alguém no arquivo de vantagens, para todas as cidades
    ct = cont.groupby(["cod_ibge", "orgao", "ano_mes"]).linhas.sum().to_dict()
    meses_vant = sorted({int(m) for m in cont.ano_mes if int(m) <= ultimo_mes and int(m) >= comum.INICIO})
    n_por = {}
    for l in linhas:
        k = (l["cod_ibge"], l["orgao"], l["ano_mes"])
        n_por[k] = n_por.get(k, 0) + int(l["quantidade"] or 0)
    agora = comum.agora()
    blocos = [{"cod_ibge": c, "orgao": o, "ano_mes": m, "linhas_fonte": int(ct.get((c, o, m), 0)),
               "pessoas": n_por.get((c, o, m), 0), "url": PAGINA, "lido_em": agora}
              for m in meses_vant for c in cods for o in ("camara", "prefeitura")]
    nomes = [{"cod_ibge": int(c), "orgao": o, "ano_mes": int(am), "papel": p, "nome": n, "cargo": cg}
             for c, o, am, p, n, cg in zip(vinc.cod_ibge, vinc.orgao, vinc.ano_mes, vinc.papel, vinc.nome, vinc.cargo)]
    blocos_nomes = {(b["cod_ibge"], b["orgao"], b["ano_mes"]) for b in blocos if b["ano_mes"] in meses_vinc}
    n, nb = cargo.gravar(UF, linhas, blocos, nomes, blocos_nomes, manter_data=True)
    log(f"  TCE-ES: {len(linhas)} linhas (cidade, órgão, mês e cargo) em {nb} blocos, {len(nomes)} nomes; "
        f"{len(sem_valor)} com pessoas no cargo e sem valor no mês (entram sem valor)")
    if erros:
        raise RuntimeError("TCE-ES: arquivos que não baixaram (os meses deles ficaram como estavam): " + "; ".join(erros))
    return len(linhas)


CFG = {
    "tribunal": "TCE-ES",
    "fonte": "Tribunal de Contas do Estado do Espírito Santo (TCE-ES), no Portal de Dados Abertos do Espírito Santo: "
             "vantagens e descontos por unidade, cargo e mês, e o vínculo de cada pessoa (Área temática: pessoal)",
    "url": PAGINA,
    "nota": "O Tribunal de Contas do Espírito Santo publica, para cada Câmara e Prefeitura e cada mês, o total pago a cada "
            "cargo (a soma de todas as pessoas, antes dos descontos) e, em outro arquivo, quem estava em cada cargo. Não "
            "publica o valor de cada vereador: o valor por pessoa é uma média (o total do cargo dividido pela quantidade "
            "de pessoas), e não o salário de um vereador. Para prefeito e vice, com uma pessoa só no cargo, o total é o "
            "valor dela.",
    "notas": ["O total soma todas as vantagens do mês: subsídio, 13º, férias, auxílios e outras, como o município "
              "classificou. O 13º, as férias e a parte indenizatória (auxílio-alimentação, por exemplo) aparecem à "
              "parte quando a verba diz.",
              "A quantidade é a de pessoas com vínculo eletivo naquele cargo no mês; pode ser diferente do número de "
              "cadeiras (suplente que assumiu, quem saiu no meio do mês).",
              "Cada município manda a sua folha ao Tribunal todo mês; o mês que ainda não foi mandado aparece sem valor.",
              "Partido: o da eleição de 2024 (TSE), quando o nome da folha é o de um único candidato da cidade."],
    "orgaos": ("camara", "prefeitura"),
    "separa_13": True,  # a verba diz o que é 13º e férias
    "link": None,
}


def montar():
    return cargo.montar_site(UF, CFG)


checar = cargo.checar
