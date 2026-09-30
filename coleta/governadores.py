"""Governadores e vice-governadores dos 27 estados: o salário (subsídio) de cada cargo, quem o ocupa e se dá para
conferir na folha de pagamento do Estado.

Não há uma fonte nacional com o salário dos governadores: cada Assembleia Legislativa fixa o do seu estado, por lei
(ou decreto legislativo), e cada Estado publica a folha de pagamento no seu portal, cada um de um jeito. Por isso a
base é um arquivo mantido à mão, dados/governadores/governadores.json, com a fonte de cada valor:

- "subsidio": uma linha por valor, com o cargo (gov, vice, sec), o mês em que passou a valer (desde), o valor bruto, a
  norma e o link da fonte, e a confiança:
    lei        o valor está no texto da lei ou do decreto legislativo;
    folha      o valor foi conferido na folha de pagamento do Estado;
    tabela     o valor está na tabela oficial de remuneração dos cargos (sem a lei);
    calculado  cálculo nosso a partir da lei (um reajuste em %, ou uma porcentagem do subsídio do governador);
    imprensa   não achamos a lei nem a folha: é o valor informado pela imprensa.
- "ocupantes": quem foi governador, vice ou governador em exercício desde 2023, com as datas (e o nome civil, que
  ajuda a achar a foto, e "fem" para as mulheres: "governadora").
- "folha": se a folha nominal do Estado abriu para o nosso robô, e o que ela mostrou.
- "notas": o que for preciso explicar sobre o estado.

Para atualizar: quando sair uma lei nova, acrescente uma linha em "subsidio"; quando mudar o governador, feche a linha
dele em "ocupantes" (ate) e abra outra. Este robô confere o arquivo, escolhe o valor em vigor e gera
site/dados/governadores.json. As fotos vêm do Wikimedia Commons (licença livre), como as do governo federal.
"""
import json
import re
from datetime import date, datetime

from .config import DADOS, RAIZ
from .util import TempoEsgotado, log, normalizar_nome

ARQUIVO = DADOS / "governadores" / "governadores.json"
SAIDA = RAIZ / "site" / "dados" / "governadores.json"
FOTOS = RAIZ / "site" / "fotos"
CONFIANCAS = {"lei", "folha", "tabela", "calculado", "imprensa"}
SITUACOES = {"aberta", "painel", "token", "bloqueada", "suspensa", "nao_testada"}
UFS = {"AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN",
       "RO", "RR", "RS", "SC", "SE", "SP", "TO"}


def _mes(aaaa_mm):
    a, m = aaaa_mm.split("-")[:2]
    return int(a) * 100 + int(m)


def _conferir(estados):
    """Erros de preenchimento do arquivo à mão (a publicação para se houver algum)."""
    erros = []
    if {e["uf"] for e in estados} != UFS:
        erros.append(f"estados faltando ou a mais: {sorted(UFS ^ {e['uf'] for e in estados})}")
    for e in estados:
        uf = e["uf"]
        if not any(s["cargo"] == "gov" for s in e["subsidio"]):
            erros.append(f"{uf}: sem subsídio do governador")
        for s in e["subsidio"]:
            if s["cargo"] not in ("gov", "vice", "sec") or s["confianca"] not in CONFIANCAS:
                erros.append(f"{uf}: cargo ou confiança inválidos em {s}")
            if not re.match(r"^\d{4}-\d{2}$", s["desde"]) or not 8000 <= s["valor"] <= 50000:
                erros.append(f"{uf}: data ou valor estranhos em {s}")
            if not str(s.get("fonte") or "").startswith("http"):
                erros.append(f"{uf}: sem link da fonte em {s}")
        chefes = [o for o in e["ocupantes"] if o["cargo"] in ("gov", "exercicio") and not o.get("ate")]
        if len(chefes) != 1:
            erros.append(f"{uf}: {len(chefes)} governadores no cargo hoje (deve ser 1)")
        for o in e["ocupantes"]:
            if o["cargo"] not in ("gov", "vice", "exercicio") or not re.match(r"^\d{4}-\d{2}-\d{2}$", o["de"]):
                erros.append(f"{uf}: ocupante com cargo ou data inválidos: {o}")
        if e["folha"]["situacao"] not in SITUACOES:
            erros.append(f"{uf}: situação da folha inválida")
    return erros


def _vigente(subsidio, cargo, ate):
    xs = sorted((s for s in subsidio if s["cargo"] == cargo and _mes(s["desde"]) <= ate), key=lambda s: s["desde"])
    return xs[-1] if xs else None


def _br(v):
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _slug(nome):
    return re.sub(r"[^a-z0-9]+", "-", normalizar_nome(nome).lower()).strip("-")


def _fotos(estados, baixar):
    """Foto do governador e do vice no cargo hoje (Wikimedia Commons, licença livre)."""
    from . import fotos as F
    pessoas = [o for e in estados for o in (e["gov"], e["vice"]) if o]
    if baixar:
        antigo = F.CARGO_OK
        F.CARGO_OK = re.compile(r"govern|vice|prefeit|deputad|senad|mayor|member of", re.I)
        try:
            novas = F._governo_commons([{"id": o["id"], "nome": o["n"], "nome_civil": o.get("nc"), "casa": "executivo"} for o in pessoas], limite=60)
            if novas:
                log(f"  {novas} fotos novas de governadores e vices (Wikimedia Commons)")
        except TempoEsgotado:
            raise
        except Exception as ex:  # noqa: BLE001 — foto é opcional
            log(f"  Fotos dos governadores: {ex}")
        finally:
            F.CARGO_OK = antigo
    creditos = json.loads(F.CREDITOS.read_text(encoding="utf-8")).get("fotos", {}) if F.CREDITOS.exists() else {}
    for o in pessoas:
        if (FOTOS / f"{o['id']}.webp").exists():
            o["f"] = f"fotos/{o['id']}.webp"
            c = creditos.get(o["id"])
            if c:
                o["fc"] = {"a": c.get("autor"), "l": c.get("licenca"), "u": c.get("pagina")}


# ---------------------------------------------------------------- mês a mês, pela folha do Estado (coleta/folhas_estaduais)
def _tokens(nome):
    return {w for w in normalizar_nome(nome or "").split() if len(w) > 2 and w not in ("DOS", "DAS", "DE", "DA", "DO")}


def _quem(e, tp, aaaamm, nome_folha):
    """Ocupante (do arquivo curado) de uma linha da folha: o do mesmo cargo naquele mês (ou vizinho), com o nome mais
    parecido. Devolve o índice em e["ocupantes"] ou None."""
    cargos = ("gov", "exercicio") if tp == "gov" else ("vice",)
    tok = _tokens(nome_folha)
    melhor = None
    for folga in (0, 1):
        for i, o in enumerate(e["ocupantes"]):
            if o["cargo"] not in cargos:
                continue
            de = _mes(o["de"])
            ate = _mes(o["ate"]) if o.get("ate") else 999912
            if not (_menos(de, folga) <= aaaamm <= _mais(ate, folga)):
                continue
            nota = len(tok & (_tokens(o.get("folha_nome")) | _tokens(o.get("civil")) | _tokens(o["nome"])))
            if melhor is None or nota > melhor[0]:
                melhor = (nota, i)
        if melhor and melhor[0] > 0:
            return melhor[1]
    return melhor[1] if melhor else None


def _menos(am, n):
    a, m = divmod(am, 100)
    for _ in range(n):
        a, m = (a - 1, 12) if m == 1 else (a, m - 1)
    return a * 100 + m


def _mais(am, n):
    a, m = divmod(am, 100)
    for _ in range(n):
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    return a * 100 + m


def _serie(e):
    """Linhas do site para o estado: [aaaamm, tp, índice do ocupante, recebido, salário, 13º, férias, auxílios, outros,
    abate-teto, marca] (parte que a folha não separa = None; marca: "s" = mês da saída, com os acertos; "a" = o 13º
    de dezembro já sem o adiantamento pago antes). Recebido = bruto menos o abate-teto."""
    import pandas as pd
    from .folhas_estaduais import comum as FC
    arq = FC.arquivo(e["uf"])
    if not arq.exists():
        return None
    df = pd.read_csv(arq)
    if not len(df):
        return None
    partes = ["salario", "decimo", "ferias", "beneficios", "outros"]
    # uma linha por pessoa, cargo e mês (algumas folhas trazem mais de uma: folha normal e a do 13º, por exemplo)
    df["redutor"] = df.redutor.fillna(0)
    agg = {k: (lambda s: None if s.isna().all() else float(s.fillna(0).sum())) for k in partes}
    g = df.groupby(["aaaamm", "tp", "nome"], as_index=False).agg({**agg, "redutor": "sum", "bruto": "sum"})
    linhas = []
    for r in g.itertuples(index=False):
        i = _quem(e, r.tp, int(r.aaaamm), r.nome)
        linhas.append({"am": int(r.aaaamm), "tp": r.tp, "i": i, "nome": r.nome, **{k: getattr(r, k) for k in partes},
                       "redutor": float(r.redutor), "bruto": float(r.bruto), "marca": ""})
    # 13º: quando dezembro traz o 13º inteiro e parte dele já tinha sido paga antes no ano (o adiantamento), a folha
    # desconta o adiantamento em dezembro; tiramos também aqui, para o 13º não contar duas vezes
    por_pessoa = {}
    for l in linhas:
        por_pessoa.setdefault((l["i"], l["nome"]), []).append(l)
    for ls in por_pessoa.values():
        salarios = sorted(l["salario"] for l in ls if l["salario"])
        mediana = salarios[len(salarios) // 2] if salarios else 0
        for ano in {l["am"] // 100 for l in ls}:
            do_ano = sorted((l for l in ls if l["am"] // 100 == ano and l["decimo"]), key=lambda l: l["am"])
            if len(do_ano) < 2 or not mediana:
                continue
            ultimo = max(do_ano, key=lambda l: l["decimo"])
            antes = sum(l["decimo"] for l in do_ano if l["am"] < ultimo["am"])
            if antes and ultimo["decimo"] >= 0.9 * mediana and antes <= ultimo["decimo"] + 1:
                ultimo["decimo"] -= antes
                ultimo["bruto"] -= antes
                ultimo["marca"] += "a"
        # mês da saída: o último mês no cargo, com o valor bem acima do normal (férias não tiradas, 13º proporcional)
        for tp in {l["tp"] for l in ls}:
            do_cargo = sorted((l for l in ls if l["tp"] == tp), key=lambda l: l["am"])
            o = e["ocupantes"][do_cargo[-1]["i"]] if do_cargo[-1]["i"] is not None else None
            if not o or not o.get("ate"):
                continue
            valores = sorted(l["bruto"] - l["redutor"] for l in do_cargo)
            normal = valores[len(valores) // 2]
            for l in do_cargo[-2:]:
                if l["am"] >= _menos(_mes(o["ate"]), 0) and l["bruto"] - l["redutor"] > 1.5 * normal:
                    l["marca"] += "s"
    r2 = lambda v: None if v is None else round(v, 2)
    return [[l["am"], l["tp"], l["i"], r2(l["bruto"] - l["redutor"]), *[r2(l[k]) for k in partes], r2(l["redutor"]), l["marca"]]
            for l in sorted(linhas, key=lambda l: (l["am"], l["tp"] != "gov", l["i"] if l["i"] is not None else 99))]


def executar(baixar_fotos=True):
    estados = json.loads(ARQUIVO.read_text(encoding="utf-8"))
    erros = _conferir(estados)
    if erros:
        raise ValueError("dados/governadores/governadores.json com problemas:\n  " + "\n  ".join(erros))
    hoje = date.today()
    agora = hoje.year * 100 + hoje.month
    saida = []
    for e in sorted(estados, key=lambda x: x["uf"]):
        uf = e["uf"]
        # a mesma ordem no site ("oc") e nas linhas da folha ("m", que apontam para o ocupante pelo índice)
        e = {**e, "ocupantes": sorted(e["ocupantes"], key=lambda o: (o["de"], {"gov": 0, "exercicio": 0, "vice": 1}[o["cargo"]]))}
        chefe = next(o for o in e["ocupantes"] if o["cargo"] in ("gov", "exercicio") and not o.get("ate"))
        vice = next((o for o in e["ocupantes"] if o["cargo"] == "vice" and not o.get("ate")), None)
        pessoa = lambda o: {"id": f"gov-{uf.lower()}-{_slug(o['nome'])}", "n": o["nome"], "nc": o.get("civil"), "pt": o.get("partido"), "de": o["de"],
                            "ex": 1 if o["cargo"] == "exercicio" else 0, **({"fem": 1} if o.get("fem") else {}),
                            **({"obs": o["obs"]} if o.get("obs") else {})}
        g, v = _vigente(e["subsidio"], "gov", agora), _vigente(e["subsidio"], "vice", agora)
        s = _vigente(e["subsidio"], "sec", agora)
        saida.append({
            "uf": uf,
            "gov": pessoa(chefe),
            "vice": pessoa(vice) if vice else None,
            # valor em vigor hoje: [valor, desde (AAAAMM), confiança, norma, fonte]
            "v": [g["valor"], _mes(g["desde"]), g["confianca"], g["norma"], g["fonte"]],
            "vv": [v["valor"], _mes(v["desde"]), v["confianca"], v["norma"], v["fonte"]] if v else None,
            "vs": [s["valor"], _mes(s["desde"]), s["confianca"], s["norma"], s["fonte"]] if s else None,
            # a história: [cargo, desde, valor, confiança, norma, fonte]
            "h": [[x["cargo"], _mes(x["desde"]), x["valor"], x["confianca"], x["norma"], x["fonte"]]
                  for x in sorted(e["subsidio"], key=lambda x: (x["desde"], x["cargo"]))],
            "oc": [{"n": o["nome"], "pt": o.get("partido"), "c": o["cargo"], "de": o["de"], "ate": o.get("ate"), **({"fem": 1} if o.get("fem") else {}),
                    **({"obs": o["obs"]} if o.get("obs") else {})}
                   for o in e["ocupantes"]],
            "folha": {"s": e["folha"]["situacao"], "u": e["folha"].get("url"), **({"c": e["folha"]["conferido"]} if e["folha"].get("conferido") else {})},
            **({"recebe": e["recebe"]} if e.get("recebe") else {}),
            "notas": e.get("notas") or [],
        })
        m = _serie(e)
        if m:
            from .folhas_estaduais import ESTADOS, NOTAS
            saida[-1]["m"] = m
            saida[-1]["mf"] = {"u": ESTADOS[uf].FONTE, "nota": NOTAS.get(uf, "")}
    _fotos([x for x in saida], baixar_fotos)
    dados = {"meta": {"gerado_em": datetime.now().isoformat(timespec="seconds"), "mes": agora,
                      "fonte": "https://github.com/jflaloux/contas-do-poder/blob/main/dados/governadores/governadores.json"},
             "e": saida}
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    vals = sorted(x["v"][0] for x in saida)
    conf = {}
    for x in saida:
        conf[x["v"][2]] = conf.get(x["v"][2], 0) + 1
    log(f"Site: {SAIDA.relative_to(RAIZ)} ({SAIDA.stat().st_size / 1e3:.0f} KB): 27 governadores, subsídio de "
        f"{_br(vals[0])} a {_br(vals[-1])}; valores por {', '.join(f'{k} {n}' for k, n in sorted(conf.items()))}")
    return dados


def coletar():
    from . import folhas_estaduais
    folhas_estaduais.coletar()  # o mês a mês pela folha dos estados em que ela abre
    executar(baixar_fotos=True)
