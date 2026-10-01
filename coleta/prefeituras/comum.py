"""Parte comum dos robôs das prefeituras (uma cidade por arquivo nesta pasta).

Cada cidade entrega uma tabela (pandas) com uma linha por pessoa, cargo e mês, tirada da folha de pagamento que a
Prefeitura publica com o nome de cada servidor:

- aaaamm:  mês de referência da folha (AAAAMM)
- tp:      "pr" prefeito, "vp" vice, "se" secretário municipal, "sb" subprefeito
- nome:    nome como está na folha (em maiúsculas, às vezes abreviado)
- pasta:   secretaria (ou subprefeitura), já com o nome bonito ("Secretaria Municipal de Educação")
- salario: o pagamento normal do mês (subsídio, vencimento, verba de representação)
- decimo:  13º salário (adiantamento, parcela ou complemento)
- outros:  todo o resto (1/3 de férias, auxílios, atrasados, acertos da saída)
- bruta:   o total bruto do mês (salario + decimo + outros)
- cedido:  1 se a folha diz que a pessoa é servidora de outro órgão, que paga o salário (a folha mostra só parte)

`montar()` devolve (meta da cidade, pessoas) no mesmo formato de site/dados/prefeituras.json, e `escrever()`
junta as cidades nesse arquivo. A Prefeitura não publica gastos por pessoa (carro oficial, viagens, equipe):
aqui entra só o que cada um recebe.
"""
import csv
import io
import json
import re
from collections import Counter
from datetime import datetime

import pandas as pd

from ..config import CACHE, RAIZ
from ..util import TempoEsgotado, log, normalizar_nome

SAIDA = RAIZ / "site" / "dados" / "prefeituras.json"
FOTOS = RAIZ / "site" / "fotos"
TSE_ZIP = CACHE / "municipios" / "consulta_cand_2024.zip"
COLUNAS = ["aaaamm", "tp", "nome", "pasta", "salario", "decimo", "outros", "bruta", "cedido"]


# ---------------------------------------------------------------- números e textos
def num(t):
    """'34.700,46', '7,924.88', '24444.7100', '3.200' ou um número -> float."""
    if isinstance(t, (int, float)):
        return 0.0 if pd.isna(t) else round(float(t), 2)
    t = re.sub(r"[^\d.,-]", "", str(t or ""))
    if not t:
        return 0.0
    if "," in t and "." in t:
        dec = "," if t.rfind(",") > t.rfind(".") else "."
    elif "," in t:
        dec = ","
    elif "." in t:
        dec = "" if re.search(r"^\d{1,3}(\.\d{3})+$", t) else "."  # "3.200" é milhar; "24444.7100" é decimal
    else:
        dec = ""
    sinal = "-" if t.startswith("-") else ""
    if dec:
        inteiro, _, fracao = t.rpartition(dec)
        t = sinal + re.sub(r"\D", "", inteiro) + "." + re.sub(r"\D", "", fracao)
    else:
        t = sinal + re.sub(r"\D", "", t)
    try:
        return round(float(t), 2)
    except ValueError:
        return 0.0


_ACENTOS = {
    "EDUCACAO": "Educação", "SAUDE": "Saúde", "HABITACAO": "Habitação", "GESTAO": "Gestão", "JUSTICA": "Justiça",
    "SEGURANCA": "Segurança", "RELACOES": "Relações", "ASSIST": "Assistência", "ASSISTENCIA": "Assistência", "DESENV": "Desenvolvimento",
    "ECONOMICO": "Econômico", "EFICIENCIA": "Eficiência", "DEFICIENCIA": "Deficiência", "CIDADAN": "Cidadania",
    "CIDADANIA": "Cidadania", "TRANSP": "Transporte", "TRANSPORTE": "Transporte", "OB": "Obras", "CRIATIV": "Criativa",
    "COMUNICACAO": "Comunicação", "INOVACAO": "Inovação", "ESTRATEGICOS": "Estratégicos", "POLITICAS": "Políticas",
    "PUBLICAS": "Públicas", "SE": "Sé", "SAO": "São", "BUTANTA": "Butantã", "JACANA": "Jaçanã", "TREMEMBE": "Tremembé",
    "BRASILANDIA": "Brasilândia", "O": "Ó", "LIMAO": "Limão", "JARAGUA": "Jaraguá", "CARRAO": "Carrão",
    "M": "M'", "ITAIM": "Itaim", "GUAIANASES": "Guaianases", "LICENCIAMENTO": "Licenciamento", "ADMINISTRACAO": "Administração",
    "GOVERNO": "Governo", "MUNICIPAL": "Municipal", "ESPECIAL": "Especial", "URBANA": "Urbana", "ECONOMIA": "Economia",
    "INTERNACIONAIS": "Internacionais", "INSTITUCIONAIS": "Institucionais", "ESPORTES": "Esportes", "LAZER": "Lazer",
    "MULHERES": "Mulheres", "PESSOA": "Pessoa", "ALIMENTAR": "Alimentar", "IGUALDADE": "Igualdade", "RACIAL": "Racial",
    "TECNOLOGIA": "Tecnologia", "CIENCIA": "Ciência", "FAZENDA": "Fazenda", "CASA": "Casa", "CIVIL": "Civil",
    "LOGISTICA": "Logística", "ORCAMENTO": "Orçamento", "PREVENCAO": "Prevenção", "MOBILIDADE": "Mobilidade",
    "SERVICOS": "Serviços", "PUBLICOS": "Públicos", "TURISMO": "Turismo", "FINANCAS": "Finanças", "CONTROLADORIA": "Controladoria",
    "PROCURADORIA": "Procuradoria", "JUVENTUDE": "Juventude", "HABITAÇÃO": "Habitação", "ESPORTE": "Esporte",
    "AGRICULTURA": "Agricultura", "ABASTECIMENTO": "Abastecimento", "INFRAESTRUTURA": "Infraestrutura", "PLANEJAMENTO": "Planejamento",
    "PATRIMONIAL": "Patrimonial", "ARTICULACAO": "Articulação", "POLITICA": "Política", "INSTITUCIONAL": "Institucional",
    "TRANSFORMACAO": "Transformação", "QUALIFICACAO": "Qualificação", "ORDEM": "Ordem", "PUBLICA": "Pública", "PARTICIPACAO": "Participação",
    "CONTROLE": "Controle", "PREVIDENCIA": "Previdência", "ACAO": "Ação", "INOVACOES": "Inovações", "EXECUCAO": "Execução",
    "COMUNICACOES": "Comunicações", "HABITACIONAL": "Habitacional", "REGULARIZACAO": "Regularização", "FUNDIARIA": "Fundiária",
    "PROTECAO": "Proteção", "DEFESA": "Defesa", "ANIMAL": "Animal", "SAUDE": "Saúde", "URBANISTICO": "Urbanístico", "SUSTENTABILIDADE": "Sustentabilidade", "DIREITOS": "Direitos", "HUMANOS": "Humanos",
}
_PEQUENAS = {"DE", "DA", "DO", "DAS", "DOS", "E"}


def bonito(texto):
    """'SECRETARIA MUNICIPAL DE EDUCACAO' -> 'Secretaria Municipal de Educação' (textos da folha, sem acento)."""
    saida = []
    for i, w in enumerate(re.split(r"(\s+|/|,)", str(texto or "").strip())):
        if not w.strip() or w in ("/", ","):
            saida.append(w)
            continue
        u = normalizar_nome(w)
        if u in _PEQUENAS and i:
            saida.append(u.lower())
        elif u in _ACENTOS:
            saida.append(_ACENTOS[u])
        elif w != w.upper():
            saida.append(w)  # já veio com maiúsculas e minúsculas (e acentos): fica como está
        else:
            saida.append(w.capitalize())
    t = re.sub(r"\bM'?\s?[Bb]oi\b", "M'Boi", "".join(saida))
    return re.sub(r"\bDo Ó\b", "do Ó", t)


_MINUSCULAS = {"da", "de", "do", "das", "dos", "e"}
# a folha vem sem acentos; estes nomes quase sempre têm (os que às vezes não têm, como Luis e Angela, ficam como estão)
_NOMES_ACENTO = {
    "jose": "José", "joao": "João", "andre": "André", "antonio": "Antônio", "fabricio": "Fabrício", "sergio": "Sérgio",
    "rogerio": "Rogério", "marcio": "Márcio", "flavia": "Flávia", "katia": "Kátia", "decio": "Décio", "alvaro": "Álvaro",
    "vinicius": "Vinícius", "valerio": "Valério", "conceicao": "Conceição", "falcao": "Falcão", "antao": "Antão",
    "franca": "França", "celia": "Célia", "araujo": "Araújo", "goncalves": "Gonçalves", "simoes": "Simões",
    "patricia": "Patrícia", "lucia": "Lúcia", "julio": "Júlio", "claudio": "Cláudio", "claudia": "Cláudia",
    "fabio": "Fábio", "flavio": "Flávio", "mario": "Mário", "otavio": "Otávio", "helio": "Hélio", "barbara": "Bárbara", "sonia": "Sônia",
    "vania": "Vânia", "monica": "Mônica", "cicero": "Cícero", "sebastiao": "Sebastião", "estevao": "Estevão",
    "assuncao": "Assunção", "romao": "Romão", "simao": "Simão", "galvao": "Galvão", "brandao": "Brandão", "junior": "Júnior",
    "damiao": "Damião", "cecilia": "Cecília", "marilia": "Marília", "leticia": "Letícia", "vitoria": "Vitória",
    "gloria": "Glória", "aurelio": "Aurélio", "emilio": "Emílio", "rubia": "Rúbia", "tarcisio": "Tarcísio",
    "virginia": "Virgínia", "eugenio": "Eugênio", "inacio": "Inácio", "ignacio": "Ignácio", "anisio": "Anísio",
    "roldao": "Roldão", "leao": "Leão", "magalhaes": "Magalhães", "guimaraes": "Guimarães", "loureiro": "Loureiro",
}


def titulo(nome):
    return " ".join(w if w in _MINUSCULAS and i else _NOMES_ACENTO.get(w, w.capitalize()) for i, w in enumerate(str(nome).lower().split()))


# nomes femininos que não terminam em "a" e masculinos que terminam (ajustar quando aparecer alguém novo)
_FEMININOS = {"ELISABETE", "ERIKA", "CIBELE", "REGINA", "SILVIA", "JULIANA", "ANGELA", "ELIANA", "MARCELA", "LUCIANA", "ANA", "RAQUEL",
              "BEATRIZ", "ISABEL", "IRIS", "LIZ", "INES", "ALICE", "CRISTIANE", "DENISE", "ELAINE", "GISELE", "LILIAN", "MIRIAM", "RUTH",
              "SUELI", "SIMONE", "SOLANGE", "VIVIANE", "JAQUELINE", "ALINE", "ROSE", "ROSELI", "ELIZABETH", "CARMEN", "KARIN",
              "EUNICE", "ELISETE", "DAMARIS", "THAMYRIS", "IRENE", "JANETE", "CLARICE", "LUCIENE", "MICHELE", "NOEMI",
              "GLAUCE", "CARMEM", "CRISTHINE", "CHRISTINE", "ADRIANE", "JOANNA", "LILIANE", "IVONE", "ROSANE", "MARLENE",
              "CARMEN", "SHIRLEY", "RIANE", "ROSANI", "ANISIA", "EDILENE", "ARLENE", "CLEIDE", "IVANI", "NOELI", "ADELE", "GRACE", "MIRIAN", "LEIDE", "NEIDE", "IARA", "CRISTIANE", "MARIANE", "TATIANE", "DAYANE",
              "ROSILENE", "ELIANE", "JOSIANE", "LUCIANE", "DAIANE", "ISABELLE", "MICHELLE", "GABRIELLE", "DANIELLE", "RACHEL",
              "IVETE", "DANIELE", "YRAGUACY", "LEIDIMAR", "MIDIANY", "IVONI"}
_MASCULINOS = {"LUCA", "JOSHUA", "NICOLA", "BATISTA", "GARCIA", "ANDREA", "COSTA", "SOUZA", "ELIAS"}


def feminino(nome, genero=None):
    """Pelo campo de gênero da folha, se houver; senão, pelo primeiro nome."""
    g = normalizar_nome(genero or "")
    if g.startswith("FEM"):
        return True
    if g.startswith("MASC"):
        return False
    p = normalizar_nome(nome).split()[0] if nome else ""
    if p in _FEMININOS:
        return True
    if p in _MASCULINOS:
        return False
    return p.endswith("A")


def _em(lugar):
    """"na Secretaria de Governo", "no Gabinete do Prefeito"."""
    masc = ("Gabinete", "Instituto", "Procon", "Fundo", "Conselho", "Centro", "Departamento", "Escritório", "Núcleo")
    return f"{'no' if lugar.split(' ')[0] in masc else 'na'} {lugar}"


def cargo_nome(tp, pasta, fem, cidade, lotado=False, especial=False):
    """cidade: "de São Paulo", "do Recife".

    lotado: a folha diz só onde o secretário está lotado, não a pasta que ele comanda (por exemplo, os secretários
    regionais de Fortaleza, todos lotados na Secretaria de Governo) -> "Secretário municipal, lotado na ...".
    especial: em São Paulo, quem é secretário fora de uma secretaria (no Gabinete do Prefeito) é "Secretário Especial".
    """
    if tp == "pr":
        return f"{'Prefeita' if fem else 'Prefeito'} {cidade}"
    if tp == "vp":
        return f"{'Vice-prefeita' if fem else 'Vice-prefeito'} {cidade}"
    if tp == "sb":
        return f"{'Subprefeita' if fem else 'Subprefeito'} ({pasta})"
    sec = "Secretária" if fem else "Secretário"
    if not pasta.startswith("Secretaria") and especial:
        return f"{sec} Especial ({pasta})"
    if lotado or not pasta.startswith("Secretaria"):
        return f"{sec} municipal, {'lotada' if fem else 'lotado'} {_em(pasta)}"
    return re.sub(r"^Secretaria\b", sec, pasta)


# ---------------------------------------------------------------- TSE: prefeito e vice
def eleitos_executivo(uf, municipio):
    """{nome civil normalizado: (nome de urna, partido)} do prefeito e do vice eleitos em 2024."""
    import zipfile
    saida = {}
    if not TSE_ZIP.exists():
        return saida
    alvo = normalizar_nome(municipio)
    with zipfile.ZipFile(TSE_ZIP) as z, z.open(f"consulta_cand_2024_{uf}.csv") as f:
        for l in csv.DictReader(io.TextIOWrapper(f, encoding="latin1"), delimiter=";"):
            if normalizar_nome(l["NM_UE"]) != alvo or l["CD_CARGO"] not in ("11", "12"):
                continue
            if l["DS_SIT_TOT_TURNO"].startswith("ELEITO"):
                saida[normalizar_nome(l["NM_CANDIDATO"])] = (l["NM_URNA_CANDIDATO"].strip(), l["SG_PARTIDO"])
            elif l["CD_CARGO"] == "12" and l["SG_PARTIDO"] and l["DS_SITUACAO_CANDIDATURA"] == "APTO":
                # o vice não tem "eleito" no turno: guarda todos os vices aptos; só o que estiver na folha é usado
                saida.setdefault(normalizar_nome(l["NM_CANDIDATO"]), (l["NM_URNA_CANDIDATO"].strip(), l["SG_PARTIDO"]))
    return saida


def _no_tse(nome, tse):
    n = normalizar_nome(nome)
    if n in tse:
        return tse[n]
    from ..vereadores.comum import compativel  # nome abreviado na folha ("JOAO HENRIQUE DE A LIMA CAMPOS")
    achados = [v for k, v in tse.items() if compativel(n, k)]
    return achados[0] if len(achados) == 1 else (None, None)


# ---------------------------------------------------------------- vereador que foi para a Prefeitura
def _vereadores(cod):
    """{nome civil normalizado: (id, nome parlamentar)} dos vereadores da cidade em site/dados/camaras.json."""
    arq = RAIZ / "site" / "dados" / "camaras.json"
    if not arq.exists():
        return {}
    d = json.loads(arq.read_text(encoding="utf-8"))
    return {normalizar_nome(p.get("nc") or p["n"]): (p["id"], p["n"]) for p in d["p"] if p.get("cid") == cod}


def _achar_vereador(nome, vereadores):
    n = normalizar_nome(nome)
    if n in vereadores:
        return vereadores[n]
    from ..vereadores.comum import compativel
    achados = [v for k, v in vereadores.items() if compativel(n, k)]
    return achados[0] if len(achados) == 1 else None


# ---------------------------------------------------------------- montagem
_ORDEM = {"pr": 0, "vp": 1, "se": 2, "sb": 3}


def _r(v):
    return int(round(float(v)))


def montar(cfg, linhas):
    """cfg: cod, n, uf, de ("de São Paulo"), casa, inicio, fonte, pagina, notas, salario_nota, credito_camara."""
    if linhas is None or not len(linhas):
        return None
    linhas = linhas.copy()
    for c in ("salario", "decimo", "outros", "bruta", "cedido"):
        linhas[c] = pd.to_numeric(linhas[c], errors="coerce").fillna(0) if c in linhas else 0
    linhas["aaaamm"] = linhas.aaaamm.astype(int)
    linhas = linhas[linhas.aaaamm >= cfg["inicio"]]
    ultimo = int(linhas.aaaamm.max())
    anos = sorted({str(a // 100) for a in linhas.aaaamm})
    cod = cfg["cod"]
    tse = eleitos_executivo(cfg["uf"], cfg["n"])
    vereadores = {**_vereadores(cod), **(cfg["vereadores"]() if cfg.get("vereadores") else {})}
    pessoas = []
    # mesma pessoa escrita com e sem "da"/"de" em meses diferentes: junta pelo nome sem essas palavras
    chave = lambda n: " ".join(w for w in normalizar_nome(n).split() if w not in _PEQUENAS)
    for _, g in linhas.assign(chave=linhas.nome.map(chave)).groupby("chave"):
        g = g.assign(ordem=g.tp.map(_ORDEM)).sort_values(["aaaamm", "ordem"])
        nome_n = normalizar_nome(g.nome.iloc[-1])
        ult = g[g.aaaamm == g.aaaamm.max()].iloc[0]  # no último mês, o cargo mais alto (vice que também é secretário: vice)
        tp = ult.tp
        fem = feminino(ult.nome, ult.get("genero") if "genero" in g else None)
        urna, partido = _no_tse(ult.nome, tse) if tp in ("pr", "vp") or g.tp.isin(["pr", "vp"]).any() else (None, None)
        ver = _achar_vereador(ult.nome, vereadores)
        exibido = titulo(urna) if urna else ver[1] if ver else titulo(ult.nome)
        mes = g.groupby("aaaamm")[["salario", "decimo", "outros", "bruta"]].sum()
        # quem saiu: os acertos do mês da saída (férias, 13º proporcional...) ficam fora das médias, à parte
        # (só o que passa do normal dele, e se passar de R$ 3 mil)
        saida = 0.0
        extras = mes.decimo + mes.outros
        if int(ult.aaaamm) != ultimo and len(mes):
            normal = float(extras.iloc[:-1].median()) if len(mes) > 1 else 0.0
            excesso = float(extras.iloc[-1]) - normal
            if excesso >= 3000:
                saida = excesso
                fator = normal / float(extras.iloc[-1]) if float(extras.iloc[-1]) else 0.0
                mes.loc[mes.index[-1], ["decimo", "outros"]] = [mes.decimo.iloc[-1] * fator, mes.outros.iloc[-1] * fator]
                mes.loc[mes.index[-1], "bruta"] = mes.salario.iloc[-1] + normal
        serie = [[int(am), _r(r.bruta), 0, 0, 0, 0] for am, r in mes.iterrows()]

        def bloco(filtro):
            s = mes[[filtro(am) for am in mes.index]]
            if not len(s):
                return None
            cats = {k: _r(v) for k, v in (("salario", s.salario.sum()), ("decimo_terceiro", s.decimo.sum()),
                                          ("outros_rendimentos", s.outros.sum())) if _r(v)}
            return {"m": len(s), "mg": int((s.bruta > 0).sum()), "mc": 0, "me": 0, "g": _r(s.bruta.sum()), "c": 0, "e": 0,
                    "pm": 0, "mp": 0, "pu": 0, "ep": 0, "cats": cats}

        per = {}
        for a in anos:
            b = bloco(lambda am, a=a: str(am // 100) == a)
            if b:
                per[a] = b
        per["leg"] = bloco(lambda am: True)
        # cargos ocupados (em ordem), com o primeiro e o último mês de cada um
        cargos = []
        nome_cargo = lambda r: cargo_nome(r.tp, r.pasta, fem, cfg["de"], bool(getattr(r, "lotado", 0)), cfg.get("especial", False))
        for am, gm in g.groupby("aaaamm", sort=True):
            nomes = list(dict.fromkeys(nome_cargo(r) for r in gm.itertuples()))
            if len(nomes) > 1 and gm.tp.iloc[0] in ("pr", "vp"):
                # prefeito ou vice que também é secretário no mesmo mês: um cargo só, "Vice-prefeito do Recife e secretário de ..."
                nomes = [" e ".join([nomes[0]] + [n[0].lower() + n[1:] for n in nomes[1:]])]
            if cargos and cargos[-1][0] in nomes:  # continua no mesmo cargo: ele primeiro
                nomes.remove(cargos[-1][0])
                cargos[-1][2] = int(am)
            for nome_c in nomes:
                cargos.append([nome_c, int(am), int(am)])
        pid = f"pre-{cod}-{re.sub(r'[^a-z0-9]+', '-', nome_n.lower()).strip('-')}"
        cedido = int(g.groupby("aaaamm").cedido.max().sum())
        pessoas.append({
            "id": pid, "k": "p", "cid": cod, "tp": tp, "n": exibido, "nc": titulo(ult.nome),
            "g": cargos[-1][0], "pa": ult.pasta, "pt": partido, "uf": cfg["uf"],
            **({"lot": 1} if tp == "se" and cargos[-1][0].startswith(("Secretário municipal, lotado", "Secretária municipal, lotada")) else {}),
            "f": None, "x": 1 if int(ult.aaaamm) == ultimo else 0,
            "o": cfg.get("pagina") or cfg["fonte"], "per": per, "t": serie, "dt": {}, "cg": cargos,
            **({"rel": ver[0]} if ver else {}),
            **({"ced": cedido} if cedido else {}),
            **({"q": [1, _r(saida)]} if saida >= 1 else {}),
        })
    pessoas.sort(key=lambda p: (_ORDEM[p["tp"]], normalizar_nome(p["n"])))
    meta = {"n": cfg["n"], "uf": cfg["uf"], "de": cfg["de"], "casa": cfg["casa"], "inicio": cfg["inicio"], "ultimo_mes": ultimo, "anos": anos,
            "fonte": cfg["fonte"], "salario_nota": cfg.get("salario_nota"), "notas": cfg.get("notas") or [],
            "credito_camara": cfg.get("credito_camara") or f"Câmara Municipal {cfg['de']}", "pagina_camara": cfg.get("pagina_camara")}
    return meta, pessoas


# ---------------------------------------------------------------- fotos (Wikimedia Commons, licença livre)
def fotos(pessoas):
    """Só para prefeito, vice e secretários; usa a mesma busca e as mesmas regras do governo federal."""
    from .. import fotos as F
    antigo = F.CARGO_OK
    F.CARGO_OK = re.compile(r"prefeit|mayor|secret", re.I)
    try:
        # prefeito e vice primeiro; no máximo 40 buscas por semana
        pessoas = sorted(pessoas, key=lambda p: (_ORDEM[p["tp"]], -p["x"]))
        return F._governo_commons([{"id": p["id"], "nome": p["n"], "nome_civil": p["nc"], "casa": "executivo"}
                                   for p in pessoas if p["tp"] in ("pr", "vp", "se") and not p.get("rel")], limite=40)
    finally:
        F.CARGO_OK = antigo


def _por_fotos(pessoas, metas):
    from ..fotos import CREDITOS
    creditos = json.loads(CREDITOS.read_text(encoding="utf-8")).get("fotos", {}) if CREDITOS.exists() else {}
    for p in pessoas:
        if (FOTOS / f"{p['id']}.webp").exists():
            p["f"] = f"fotos/{p['id']}.webp"
            c = creditos.get(p["id"])
            if c:
                p["fc"] = {"a": c.get("autor"), "l": c.get("licenca"), "u": c.get("pagina")}
        elif p.get("rel") and (FOTOS / f"{p['rel']}.webp").exists():
            # quem também é vereador usa a foto oficial da Câmara Municipal
            m = metas[str(p["cid"])]
            p["f"] = f"fotos/{p['rel']}.webp"
            p["fc"] = {"a": m["credito_camara"], "u": m.get("pagina_camara")}


def escrever(resultados, baixar_fotos=True):
    """resultados: [(meta, pessoas)] -> site/dados/prefeituras.json."""
    todas = [p for _, ps in resultados for p in ps]
    metas = {str(ps[0]["cid"]): meta for meta, ps in resultados if ps}
    if baixar_fotos:
        try:
            novas = fotos(todas)
            if novas:
                log(f"  {novas} fotos novas das prefeituras (Wikimedia Commons)")
        except TempoEsgotado:
            raise
        except Exception as e:  # noqa: BLE001 — foto é opcional
            log(f"  Fotos das prefeituras: {e}")
    _por_fotos(todas, metas)
    dados = {"meta": {"gerado_em": datetime.now().isoformat(timespec="seconds"), "tipos": [], "categorias": {}, "cidades": metas}, "p": todas}
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for meta, ps in resultados:
        n = Counter(p["tp"] for p in ps if p["x"])
        sub = f", {n['sb']} subprefeitos" if n["sb"] else ""
        log(f"  Prefeitura {meta['de']}: no cargo em {meta['ultimo_mes'] % 100:02d}/{meta['ultimo_mes'] // 100}: "
            f"{n['pr']} prefeito, {n['vp']} vice, {n['se']} secretários{sub}")
    log(f"Site: {SAIDA.relative_to(RAIZ)} ({SAIDA.stat().st_size / 1e3:.0f} KB, {len(resultados)} cidades, {len(todas)} pessoas)")
    return dados
