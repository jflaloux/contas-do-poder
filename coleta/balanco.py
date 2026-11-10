"""Balanço do mandato 2023–2026 de deputados federais e senadores (desde fev/2023): site/dados/balanco.json e
site/dados/balanco.csv (dados abertos, CC BY 4.0).

Roda no fim da etapa "site" (`coleta/site.py`), com os mesmos lançamentos que viram os perfis (depois de tirar os
pagamentos fora do mandato e o salário dos meses como ministro): o total de cada pessoa é o mesmo do perfil, no período
todo ("Mandato todo"), menos a equipe estimada do Senado, que no balanço conta pelos dias no cargo (o perfil guarda o mês
inteiro, campo e.eb).

Componentes, como a base já agrupa (dados/processados/metadados.json, "categorias"):
  r  recebeu: o grupo "ganha" (salário, 13º, férias, auxílios, ajuda de custo e outros pagamentos), bruto;
     a ajuda de custo (pagamento único, na posse e no fim do mandato) entra no total e fica fora da média por mês,
     como no perfil;
  c  cota parlamentar (Câmara: CEAP; Senado: CEAPS), com a % do limite (só na Câmara, ver LIMITES);
  o  outros gastos do mandato: diárias de viagens oficiais e, no Senado, as passagens fora da CEAPS (ATC 2/2023),
     correios e impulsionamento (informados por ano e divididos pelos meses);
  e  equipe do gabinete (Câmara: verba de gabinete; Senado: estimativa pelos assessores ligados ao gabinete, que no
     balanço conta pelos dias no cargo e fica fora da ordem e das comparações).

Meses no cargo: pelos dias em exercício, das datas oficiais (Câmara: histórico do deputado nos dados abertos; Senado:
os exercícios do senador). Um mês com 15 dias no cargo conta 0,5. A média por mês de cada componente é o total dele
dividido pelos meses no cargo dentro da faixa de meses que a fonte já publicou (a verba de gabinete da Câmara, por
exemplo, sai com meses de atraso).
"""
import calendar
import statistics
from datetime import date, datetime, timedelta

import pandas as pd

from .config import LEGISLATURA, RAIZ
from .util import baixar, gravar_csv, gravar_json, ler_json, log

SAIDA = RAIZ / "site" / "dados" / "balanco.json"
SAIDA_CSV = RAIZ / "site" / "dados" / "balanco.csv"
HISTORICO = RAIZ / "dados" / "referencia" / "camara_historico.json"  # o mesmo que coleta/site.py usa
LIMITES = RAIZ / "dados" / "referencia" / "limites_cota_camara_historico.csv"
TETO_VERBA = RAIZ / "dados" / "referencia" / "teto_verba_gabinete_camara.csv"
OUTROS_SENADO = RAIZ / "dados" / "senado" / "outros_gastos.csv"  # coleta/senado.py (outros gastos lidos, por senador e ano)
API_CAMARA = "https://dadosabertos.camara.leg.br/api/v2"
INICIO, FIM = date(2023, 2, 1), date(2027, 1, 31)
REFRESCAR_DIAS = 28  # histórico de quem está no cargo: lido de novo depois disto
MAX_POR_RODADA = 150  # históricos lidos por rodada (fora os que faltam ou mudaram de situação)
MESES_MINIMOS = 3  # para entrar na mediana do estado (como a comparação com os colegas no site)


# ---------------------------------------------------------------- meses no cargo
def _aaaamm(d):
    return d.year * 100 + d.month


def _dias(intervalos, ate):
    """Os dias no cargo (entre INICIO e FIM, até `ate`) a partir de intervalos [(início, fim)] de datas (fim incluído)."""
    dias = set()
    for ini, fim in intervalos:
        ini, fim = max(ini, INICIO), min(fim, ate, FIM)
        while ini <= fim:
            dias.add(ini)
            ini += timedelta(days=1)
    return dias


def _fracoes(intervalos, ate):
    """{AAAAMM: fração do mês no cargo} a partir de intervalos [(início, fim)] de datas (fim incluído)."""
    por_mes = {}
    for d in _dias(intervalos, ate):
        por_mes[_aaaamm(d)] = por_mes.get(_aaaamm(d), 0) + 1
    return {m: n / calendar.monthrange(m // 100, m % 100)[1] for m, n in por_mes.items()}


EXERCICIO = {"Exercício", "CONVOCADO"}  # o suplente convocado às vezes não ganha o evento "Exercício" depois


def _eventos(eventos):
    """Eventos da legislatura com situação, em ordem de data. A ordem da API vale no mesmo dia ("SUPLENCIA" e
    "Exercício" no mesmo dia: o que vem depois na lista é o que vale), por isso a ordenação é só pela data."""
    return sorted(((dt[:10], sit) for dt, leg, sit in eventos if leg == LEGISLATURA and sit), key=lambda x: x[0])


def _intervalos_camara(eventos, hoje):
    """Intervalos em exercício na legislatura pelo histórico da Câmara: da posse ("Exercício"; "CONVOCADO" só quando não vem
    "Exercício" depois) até o dia do evento seguinte com outra situação (licença, suplência, vacância, suspensão). O dia da posse e o do
    afastamento contam, como na cota (Ato da Mesa nº 43/2009, arts. 11 e 12)."""
    evs = _eventos(eventos)
    saida, desde = [], None
    for k, (dt, sit) in enumerate(evs):
        d = date.fromisoformat(dt)
        if sit in EXERCICIO and desde is None:
            desde = d
            if sit == "CONVOCADO":  # a convocação não é a posse: com "Exercício" depois (antes de sair), vale a posse
                for dt2, sit2 in evs[k + 1:]:
                    if sit2 not in EXERCICIO:
                        break
                    if sit2 == "Exercício":
                        desde = date.fromisoformat(dt2)
                        break
        elif sit not in EXERCICIO and desde is not None:
            saida.append((desde, d))
            desde = None
    if desde is not None:
        saida.append((desde, max(desde, hoje)))
    return saida


def meses_em_exercicio(eventos, hoje=None):
    """{AAAAMM} com pelo menos um dia em exercício na legislatura (o mês da posse e o da saída contam)."""
    hoje = hoje or date.today()
    return set(_fracoes(_intervalos_camara(eventos, hoje), hoje))


def meses_em_licenca(eventos, hoje=None):
    """{AAAAMM} com pelo menos um dia de licença (evento "Licença" até o evento seguinte) na legislatura: o deputado
    licenciado continua no mandato e pode ficar com o salário dele (secretário de Estado, por exemplo)."""
    hoje = hoje or date.today()
    saida, desde = [], None
    for dt, sit in _eventos(eventos):
        d = date.fromisoformat(dt)
        if desde is not None:
            saida.append((desde, d))
            desde = None
        if sit == "Licença":
            desde = d
    if desde is not None:
        saida.append((desde, max(desde, hoje)))
    return set(_fracoes(saida, hoje))


def meses_depois_da_saida(eventos, hoje=None):
    """{AAAAMM}: o mês seguinte a cada saída do exercício (onde a folha põe os acertos da saída: os dias do mês anterior,
    o 13º e as férias proporcionais)."""
    hoje = hoje or date.today()
    saida = set()
    for ini, fim in _intervalos_camara(eventos, hoje):
        if fim < hoje:
            a, m = fim.year, fim.month
            saida.add(a * 100 + m + 1 if m < 12 else (a + 1) * 100 + 1)
    return saida


def _no_fim(eventos):
    """True se o último evento da legislatura deixa o deputado em exercício."""
    evs = _eventos(eventos)
    return bool(evs) and evs[-1][1] in EXERCICIO


def atualizar_historicos(deputados, maximo=MAX_POR_RODADA):
    """Lê na API da Câmara o histórico (posse, licença, afastamento, reassunção...) de quem falta em
    dados/referencia/camara_historico.json, de quem mudou de situação (em exercício hoje ≠ o que o histórico guardado
    diz) e, até `maximo` por rodada, de quem está no cargo e foi lido há mais de REFRESCAR_DIAS dias."""
    guardado = ler_json(HISTORICO) if HISTORICO.exists() else {}
    datas = guardado.setdefault("_lido_em", {})
    hoje = date.today()
    urgentes, velhos = [], []
    for p in deputados:
        num = p["id"].split("-")[1]
        if num not in guardado:
            urgentes.append(num)
        elif _no_fim(guardado[num]) != bool(p.get("em_exercicio")):
            urgentes.append(num)
        else:
            lido = date.fromisoformat(datas.get(num, "2000-01-01"))
            if (hoje - lido).days > REFRESCAR_DIAS and (p.get("em_exercicio") or lido < date(2027, 2, 1)):
                velhos.append((lido, num))
    fila = urgentes + [n for _, n in sorted(velhos)][: max(0, (maximo or 10**6) - len(urgentes))]
    if not fila:
        return guardado
    log(f"Balanço: lendo o histórico de {len(fila)} deputados na API da Câmara ({len(urgentes)} faltavam ou mudaram)")
    lidos = 0
    for num in fila:
        try:
            d = baixar(f"{API_CAMARA}/deputados/{num}/historico", headers={"Accept": "application/json"}).json()["dados"]
        except Exception as e:  # noqa: BLE001 — fica o guardado (ou a pessoa sem meses, avisada no log)
            log(f"Balanço: histórico do deputado {num} indisponível ({e})")
            continue
        guardado[num] = [[x["dataHora"][:10], x.get("idLegislatura"), x.get("situacao")] for x in d]
        datas[num] = hoje.isoformat()
        lidos += 1
    if lidos:
        HISTORICO.parent.mkdir(parents=True, exist_ok=True)
        # a API devolve o histórico inteiro de novo: menos eventos que o guardado é a Câmara que refez a lista
        gravar_json(HISTORICO, guardado, compacto=False, indent=1, motivo="histórico relido inteiro na API da Câmara")
    return guardado


def _intervalos_senado(exercicios, hoje):
    """Intervalos em exercício do senador (a API dá início e fim de cada exercício; quem está no cargo vem com o fim no
    dia da coleta)."""
    saida = []
    for x in exercicios or []:
        if not x.get("inicio"):
            continue
        ini = date.fromisoformat(x["inicio"][:10])
        fim = date.fromisoformat(x["fim"][:10]) if x.get("fim") else hoje
        saida.append((ini, max(ini, fim)))
    return saida


# ---------------------------------------------------------------- limite da cota da Câmara
def _vigencias():
    """{uf: [(desde, valor), ...]} e a lista das normas, de dados/referencia/limites_cota_camara_historico.csv."""
    d = pd.read_csv(LIMITES)
    vig = {}
    for r in d.sort_values("desde").itertuples():
        vig.setdefault(r.uf, []).append((date.fromisoformat(r.desde), float(r.limite_mensal)))
    normas = (d.drop_duplicates("desde").sort_values("desde")[["desde", "norma", "url_norma", "url_valores"]]
              .to_dict("records"))
    return vig, normas


def _valor_no_dia(vig_uf, d):
    em_vigor = [v for desde, v in vig_uf if desde <= d]
    return em_vigor[-1] if em_vigor else vig_uf[0][1]


def limite_dos_dias(vig_uf, dias):
    """Limite da cota nos dias com direito a ela: cada dia vale o limite em vigor naquele dia ÷ os dias do mês (a cota
    é proporcional aos dias em exercício, Ato da Mesa nº 43/2009, art. 11; em fev/2026 o limite mudou no dia 20)."""
    return sum(_valor_no_dia(vig_uf, d) / calendar.monthrange(d.year, d.month)[1] for d in dias)


def limite_do_mes(vig_uf, aaaamm):
    """Limite do mês inteiro (com a mudança no meio do mês pelos dias)."""
    a, m = divmod(aaaamm, 100)
    return limite_dos_dias(vig_uf, [date(a, m, dia) for dia in range(1, calendar.monthrange(a, m)[1] + 1)])


def _teto_verba():
    """[(AAAAMM, valor)] do disponível mensal da verba de gabinete da Câmara (dados/referencia/teto_verba_gabinete_camara.csv)."""
    if not TETO_VERBA.exists():
        return []
    d = pd.read_csv(TETO_VERBA)
    return sorted((int(x.replace("-", "")), float(v)) for x, v in zip(d.desde, d.valor_mensal))


def _teto_no_mes(teto, am):
    em_vigor = [v for desde, v in teto if desde <= am]
    return em_vigor[-1] if em_vigor else None


def _outros_lidos():
    """{(cod do senador, ano)} com os outros gastos do mandato lidos (API ou página de transparência), de
    dados/senado/outros_gastos.csv. None se o arquivo ainda não existe."""
    if not OUTROS_SENADO.exists():
        return None
    d = pd.read_csv(OUTROS_SENADO)
    return {(int(c), int(a)) for c, a in zip(d.id_senador, d.ano)}


# ---------------------------------------------------------------- componentes
COMPONENTES = {
    "r": "Recebeu (salário, 13º, férias, auxílios, ajuda de custo e outros pagamentos, bruto)",
    "c": "Cota parlamentar (Câmara: CEAP; Senado: CEAPS)",
    "o": "Outros gastos do mandato (diárias de viagens oficiais; no Senado, também passagens fora da CEAPS, correios e impulsionamento)",
    "e": "Equipe do gabinete (Câmara: verba de gabinete; Senado: estimativa pelos assessores, proporcional aos dias no cargo)",
}
PARTES_DO_TOTAL = {"d": ("r", "c", "o", "e"), "s": ("r", "c", "o")}  # no Senado, a ordem e a comparação ficam sem a equipe estimada


def _componente(lanc):
    comp = pd.Series("o", index=lanc.index)
    comp[lanc.grupo == "ganha"] = "r"
    comp[lanc.categoria == "cota_parlamentar"] = "c"
    comp[lanc.grupo == "equipe"] = "e"
    return comp


def _r(v):
    return int(round(float(v)))


def _mediana(xs):
    xs = [x for x in xs if x is not None and not pd.isna(x)]
    return statistics.median(xs) if xs else None


# ---------------------------------------------------------------- montagem
def calcular(lanc, politicos, historicos, hoje=None):
    """(pessoas, faixas, mensal, publicados): uma linha por deputado/senador com os totais e as médias, a faixa de meses
    de cada componente em cada casa, o valor de cada pessoa, mês e componente (para a conferência) e os meses publicados.

    Meses publicados de cada componente em cada casa: os meses com pelo menos metade das pessoas do mês mais cheio
    (a Câmara não publica a verba de gabinete de dez/2024: o mês fica fora da média da equipe). "Outros" segue a folha.

    Peso de cada mês na média (só meses publicados):
      - recebeu: mês sem nenhum pagamento na fonte não entra (o mês de posse de vários suplentes; meses seguidos sem
        pagamento de algumas deputadas); com pagamento, a fração do mês no cargo ou, se maior, o salário do mês ÷ o
        subsídio (licenciado que ficou com o salário do mandato);
      - cota, outros gastos e equipe da Câmara: a fração do mês no cargo (a cota é proporcional aos dias em exercício,
        Ato da Mesa nº 43/2009, art. 11); num mês sem nenhum dia no cargo e com valor positivo (licença médica sem
        suplente convocado, que conta como exercício pelo art. 12), o mês inteiro. O limite da cota conta só os dias
        em exercício (o gasto de um mês sem exercício fica no total, sem criar limite);
      - equipe do Senado: a estimativa de cada mês vezes a fração do mês no cargo (a estimativa liga a folha à lotação
        atual dos servidores e põe o mês inteiro em quem estava no cargo um dia só), dividida pelos meses no cargo.
    Média com menos de 1 mês no divisor: não há (só o total)."""
    from .camara import subsidio
    hoje = hoje or date.today()
    l = lanc[lanc.id_politico.str[:4].isin(["dep-", "sen-"])].copy()
    l["comp"] = _componente(l)
    l["am"] = (l.ano * 100 + l.mes.fillna(0)).astype(int)
    l["k"] = l.id_politico.str[0]
    if (l.mes.isna()).any():
        log(f"Balanço: {int(l.mes.isna().sum())} lançamentos sem mês entram só nos totais")
    mensal = l.groupby(["k", "id_politico", "am", "comp"]).valor.sum().unstack("comp").fillna(0.0)
    for c in COMPONENTES:
        if c not in mensal:
            mensal[c] = 0.0
    mensal = mensal.reset_index()
    sal = l[l.categoria == "salario"].groupby(["id_politico", "am"]).valor.sum()

    publicados, faixas = {}, {}
    for k, g in mensal[mensal.am > 0].groupby("k"):
        pub = {}
        for c in ("r", "c", "e"):
            n = g[g[c].abs() > 0.5].groupby("am").id_politico.nunique()
            pub[c] = {int(m) for m, q in n.items() if q >= max(1, int(n.max() / 2))} if len(n) else set()
        pub["o"] = pub["r"]
        publicados[k] = pub
        faixas[k] = {c: [min(v), max(v)] if v else None for c, v in pub.items()}

    vig, _ = _vigencias()
    teto = _teto_verba()
    lidos_senado = _outros_lidos()
    pessoas = []
    ult_folha = max(f["r"][1] for f in faixas.values())
    ate_dia = min(hoje, date(ult_folha // 100, ult_folha % 100, calendar.monthrange(ult_folha // 100, ult_folha % 100)[1]))
    por_id = {pid: g.set_index("am") for pid, g in mensal.groupby("id_politico")}
    totais = l.groupby(["id_politico", "comp"]).valor.sum()
    unico = l[l.categoria == "ajuda_de_custo"].groupby("id_politico").valor.sum()
    rateado = l[l.rateado.fillna(False).astype(bool)].groupby(["id_politico", "comp"]).valor.sum()
    for p in politicos:
        if p["casa"] not in ("camara", "senado"):
            continue
        pid, k = p["id"], "d" if p["casa"] == "camara" else "s"
        num = pid.split("-")[1]
        if k == "d":
            ev = historicos.get(num)
            if ev is None:
                log(f"Balanço: {pid} sem histórico da Câmara; fica sem meses no cargo")
            intervalos = _intervalos_camara(ev or [], ate_dia)
        else:
            intervalos = _intervalos_senado(p.get("exercicios"), ate_dia)
        dias = _dias(intervalos, ate_dia)
        fr = _fracoes(intervalos, ate_dia)
        mm = por_id.get(pid, pd.DataFrame(columns=list(COMPONENTES)))
        tot = {c: float(totais.get((pid, c), 0.0)) for c in COMPONENTES}
        if not fr and not any(abs(v) >= 1 for v in tot.values()):
            continue
        pub = publicados[k]
        u = float(unico.get(pid, 0.0))
        linha = {"id": pid, "k": k, "nome": p["nome"], "uf": p.get("uf"), "partido": p.get("partido"),
                 "x": bool(p.get("em_exercicio")),
                 "suplente": "uplente" in str(p.get("condicao_eleitoral") or p.get("participacao") or ""),
                 "rel": p.get("relacionado"), "pagina_oficial": p.get("pagina_oficial"),
                 "mc": sum(fr.values()), "de": min(fr) if fr else None, "ate": max(fr) if fr else None, "u": u}

        def valor(c, m):
            return float(mm[c].get(m, 0.0)) if c in mm and m in mm.index else 0.0
        if k == "s":  # a equipe estimada do Senado conta pelos dias no cargo
            linha["e_estimada"] = tot["e"]
            tot["e"] = sum(valor("e", m) * fr.get(m, 0.0) for m in mm.index)
        pesos, sem_pagamento = {}, 0
        for c in COMPONENTES:
            meses = sorted(m for m in set(fr) | set(mm.index) if m in pub[c])
            peso, no_periodo = {}, 0.0
            for m in meses:
                v = valor(c, m)
                if c == "r":
                    if abs(v) < 1:
                        sem_pagamento += 1 if fr.get(m, 0.0) > 0 else 0
                        w = 0.0
                    else:
                        w = max(fr.get(m, 0.0), min(1.0, max(0.0, float(sal.get((pid, m), 0.0)) / subsidio(m))))
                elif c == "e" and k == "s":
                    w = fr.get(m, 0.0)
                    v *= w
                else:
                    w = fr.get(m, 0.0) or (1.0 if v > 0.5 else 0.0)
                no_periodo += v
                if w > 0:
                    peso[m] = w
            pesos[c] = peso
            n = sum(peso.values())
            linha[c] = tot[c]
            linha[c + "_n"] = n
            linha[c + "_m"] = (no_periodo - (u if c == "r" else 0.0)) / n if n >= 1 else None
            linha[c + "_fora"] = tot[c] - no_periodo  # fora dos meses publicados (ou sem mês): só no total
            linha[c + "_rat"] = float(rateado.get((pid, c), 0.0))
        linha["r_sem_pagamento"] = sem_pagamento
        linha["c_lim"] = linha["c_pct"] = linha["e_teto"] = linha["e_pct"] = None
        if k == "d" and p.get("uf") in vig:
            lim = limite_dos_dias(vig[p["uf"]], [d for d in dias if _aaaamm(d) in pub["c"]])
            linha["c_lim"] = lim
            linha["c_pct"] = (tot["c"] - linha["c_fora"]) / lim * 100 if lim > 0 else None
        if k == "d" and teto:
            t = sum(w * (_teto_no_mes(teto, m) or 0.0) for m, w in pesos["e"].items())
            linha["e_teto"] = t or None
            linha["e_pct"] = (tot["e"] - linha["e_fora"]) / t * 100 if t > 0 else None
        linha["o_incompleto"] = None
        if k == "s" and lidos_senado is not None:
            anos = {m // 100 for m in fr}
            linha["o_incompleto"] = any((int(num), a) not in lidos_senado for a in anos)
        partes = PARTES_DO_TOTAL[k]
        linha["menos_de_3"] = [c for c in COMPONENTES if linha[c + "_n"] < MESES_MINIMOS]
        linha["ok"] = all(linha[c + "_n"] >= MESES_MINIMOS for c in partes)
        linha["ok_todas"] = all(linha[c + "_n"] >= MESES_MINIMOS for c in COMPONENTES)
        pessoas.append(linha)
    return pd.DataFrame(pessoas), faixas, mensal, publicados


# ---------------------------------------------------------------- arquivos do site
FONTES = [
    {"nome": "Câmara dos Deputados: dados abertos (deputados, histórico de exercício, cota parlamentar)", "url": "https://dadosabertos.camara.leg.br/swagger/api.html"},
    {"nome": "Câmara dos Deputados: consulta da cota parlamentar", "url": "https://www.camara.leg.br/cota-parlamentar/"},
    {"nome": "Câmara dos Deputados: página de cada deputado (remuneração, contracheque detalhado, verba de gabinete)", "url": "https://www.camara.leg.br/deputados/quem-sao"},
    {"nome": "Câmara dos Deputados: auxílio-moradia", "url": "https://www.camara.leg.br/moradia/detalhamento"},
    {"nome": "Câmara dos Deputados: limites da cota (Ato da Mesa nº 43/2009, com a tabela do Ato da Mesa nº 270/2023)", "url": "https://www2.camara.leg.br/legin/int/atomes/2009/atodamesa-43-21-maio-2009-588364-normaatualizada-cd-mesa.html"},
    {"nome": "Câmara dos Deputados: limites da cota desde 20/2/2026 (Ato da Mesa nº 244/2026; valores no guia para jornalistas)", "url": "https://www2.camara.leg.br/comunicacao/assessoria-de-imprensa/guia-para-jornalistas/cota-parlamentar"},
    {"nome": "Senado Federal: dados abertos (senadores e exercícios)", "url": "https://legis.senado.leg.br/dadosabertos/docs/"},
    {"nome": "Senado Federal: folha de pagamento (dados abertos administrativos)", "url": "https://adm.senado.gov.br/adm-dadosabertos/swagger-ui/index.html"},
    {"nome": "Senado Federal: Portal da Transparência, CEAPS e outros gastos de cada senador", "url": "https://www6g.senado.leg.br/transparencia/sen/"},
    {"nome": "Decreto Legislativo nº 172/2022 (subsídio de deputados e senadores)", "url": "https://www2.camara.leg.br/legin/fed/decleg/2022/decretolegislativo-172-21-dezembro-2022-793529-publicacaooriginal-166604-pl.html"},
]
TETO_FONTE = ("Estimado pela página de cada deputado na Câmara (gasto do mês e percentual do disponível da verba de gabinete): "
              "mediana do gasto ÷ percentual entre os deputados com 50% ou mais gasto no mês. Não achamos o ato da Mesa com os valores.")


def _mes_txt(am):
    nomes = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
    return f"{nomes[am % 100 - 1]}/{am // 100}" if am else ""


def _ultimo(faixas):
    return max((x or [0, 0])[1] for f in faixas.values() for x in f.values())


def _lacunas(publicados, faixas):
    """{casa: {parte: [AAAAMM, ...]}}: meses dentro da faixa que a fonte não publicou (dez/2024 da verba de gabinete)."""
    saida = {}
    for k, pub in publicados.items():
        for c, meses in pub.items():
            if not meses or c == "o":
                continue
            a, b = min(meses), max(meses)
            todos = [x for x in range(a, b + 1) if 1 <= x % 100 <= 12]
            falta = [x for x in todos if x not in meses]
            if falta:
                saida.setdefault(k, {})[c] = falta
    return saida


def _ressalvas(faixas, lacunas, teto):
    fd, fs = faixas.get("d", {}), faixas.get("s", {})
    falta_e = ", ".join(_mes_txt(m) for m in lacunas.get("d", {}).get("e", []))
    tetos = "; ".join(f"R$ {v:,.0f} desde {_mes_txt(a)}".replace(",", ".") for a, v in teto)
    return [
        f"Período: mandato 2023–2026, de fev/2023 a {_mes_txt(_ultimo(faixas))}. "
        "Os senadores eleitos em 2022 têm mandato até 2031: o balanço conta só o que cada um exerceu desde 1º/2/2023. "
        "Os dados são parciais: vão até o último mês "
        f"que cada fonte publicou (Câmara: folha até {_mes_txt((fd.get('r') or [0, 0])[1])}, cota até {_mes_txt((fd.get('c') or [0, 0])[1])}, "
        f"verba de gabinete até {_mes_txt((fd.get('e') or [0, 0])[1])}; Senado: folha até {_mes_txt((fs.get('r') or [0, 0])[1])}, "
        f"CEAPS até {_mes_txt((fs.get('c') or [0, 0])[1])}). O balanço é refeito a cada atualização semanal.",
        "Valores brutos, como as fontes publicam. Não entram o imposto de renda, a previdência nem o valor líquido de ninguém.",
        "Meses no cargo: pelos dias em exercício, das datas oficiais da Câmara (histórico de cada deputado, a partir da posse) "
        "e do Senado (exercícios de cada senador). Um mês com metade dos dias no cargo conta meio mês.",
        "Média por mês: o total de cada parte dividido pelos meses no cargo dentro dos meses que a fonte já publicou. "
        "Quem teve mandato curto se compara pela média por mês, não pelo total, e só entra nas comparações quem tem 3 meses "
        "ou mais em cada parte que forma o total; com menos de 1 mês não há média. Nos meses de licença (médica ou para ser "
        "secretário de Estado, por exemplo), entra na conta o que a fonte mostra: o salário, quando a pessoa ficou com o "
        "salário do mandato (o mês conta pela parte do subsídio paga), e o gabinete e a cota, quando continuaram funcionando "
        "(o mês conta inteiro). Por isso cada parte diz por quantos meses foi dividida.",
        "Meses no cargo sem nenhum pagamento na fonte não entram na média do que recebeu.",
        "A ajuda de custo (paga de uma vez, na posse e no fim do mandato) entra no total recebido e fica fora da média por mês.",
        "Os valores mudaram no período: o subsídio subiu em abr/2023, fev/2024 e fev/2025 (Decreto Legislativo nº 172/2022), "
        f"o limite da cota da Câmara em fev/2026 e o valor mensal da verba de gabinete da Câmara também ({tetos}). Quem esteve "
        "no cargo só no fim do período tende a ter média por mês maior.",
        "Cota parlamentar: os 3 últimos meses ainda podem receber notas (o prazo é de 90 dias).",
        "Câmara: desde ago/2025 as passagens compradas pelo sistema da Câmara (SIGEPA) não aparecem nos arquivos de dados "
        "abertos da cota. Usamos o total mensal da consulta oficial da cota no site da Câmara e mostramos a diferença como "
        "\"passagens aéreas e itens sem detalhe\".",
        "Câmara: % do limite da cota = o que foi usado ÷ a soma dos limites do estado nos dias em exercício (Ato da Mesa nº "
        "270/2023 até 19/2/2026; Ato da Mesa nº 244/2026 desde 20/2/2026). A % pode passar de 100: além da cota, o deputado "
        "tem direito ao reembolso de até quatro trechos aéreos por mês entre o estado e Brasília (Ato da Mesa nº 43/2009, art. 2º, "
        "§ 3º), e essas passagens aparecem no total da cota que a Câmara publica; líderes, vice-líderes, presidentes de "
        "comissão e suplentes da Mesa têm um adicional mensal (art. 1º, § 1º) que não entra no limite que usamos; e notas "
        "lançadas num mês sem exercício entram no gasto, sem limite. O saldo de um mês passa para o seguinte dentro do mesmo "
        "ano (art. 13). A cota de quem entra ou sai no meio do mês é proporcional aos dias (art. 11), e o limite também.",
        "Câmara: % do valor da verba de gabinete = o que a equipe custou ÷ o valor mensal disponível nos meses no cargo. O "
        "valor disponível é estimado pela própria página de cada deputado (gasto do mês e percentual do disponível).",
        (f"Câmara: a página de cada deputado não traz a verba de gabinete de {falta_e}; esse mês fica fora da média da equipe."
         if falta_e else None),
        "Câmara: a página oficial mostra R$ 0,00 de verba de gabinete para a maioria dos suplentes que ficaram poucos meses; "
        "a mediana da equipe por estado conta só quem teve equipe.",
        "Senado: o limite da CEAPS de cada senador soma uma verba fixa ao valor de cinco trechos aéreos entre Brasília e a "
        "capital do estado (Senado, perguntas frequentes) e foi atualizado na legislatura (Ato do Presidente nº 8/2025, em "
        "vigor em 1º/3/2025); o Senado não publica a tabela por estado em formato aberto, e por isso o balanço não traz a % "
        "do limite dos senadores.",
        "Senado: o custo da equipe é uma estimativa: a folha de pagamento ligada à lotação atual (ou à última) de cada "
        "servidor comissionado, pelo nome (homônimos ficam de fora). No balanço, a estimativa de cada mês conta pelos dias "
        "no cargo, e a ordem e as comparações do Senado usam o total sem a equipe estimada.",
        "Senado: os outros gastos do mandato de quem não está no cargo vêm da página de transparência de cada senador (a "
        "API do Senado só responde para quem está em exercício). Ano sem esse quadro lido fica marcado como incompleto.",
        "A folha oficial do Senado traz valores negativos na coluna do 13º para três senadores; o balanço soma como a fonte "
        "publica.",
        "Partes informadas só por ano (o auxílio-moradia da Câmara; as passagens fora da CEAPS, os correios e o "
        "impulsionamento do Senado) são divididas pelos meses: o total do período é o da fonte, a divisão por mês é "
        "aproximada (≈). Em 2023, o valor do ano pode incluir janeiro, que ainda era da legislatura anterior.",
        "Deputado ou senador que foi ministro: os meses como ministro ficam na página de ministro (o salário pago pelo "
        "Congresso nesses meses não aparece aqui, para não contar duas vezes).",
        "Sem agregados por partido. O partido é o atual, como no perfil.",
    ]


def _bloco(df, c, lim=False):
    """Soma do componente, mediana da média por mês (de quem tem MESES_MINIMOS meses na parte) e número de pessoas na
    mediana. Equipe: só quem teve equipe (como a comparação com os colegas no perfil), porque a página oficial mostra
    R$ 0,00 de verba de gabinete para a maioria dos suplentes que ficaram poucos meses."""
    com_meses = df[(df[c + "_n"] >= MESES_MINIMOS) & df[c + "_m"].notna()]
    if c == "e":
        com_meses = com_meses[com_meses.e > 0.5]
    b = {"s": _r(df[c].sum()), "md": _r(_mediana(com_meses[c + "_m"].tolist()) or 0), "n": int(len(com_meses))}
    if lim and df.c_lim.notna().any():
        tem = df[df.c_lim.notna() & (df.c_lim > 0)]
        b["pct"] = round(float(tem.c.sum() / tem.c_lim.sum() * 100), 1) if len(tem) else None
        b["pmd"] = round(float(_mediana(com_meses.c_pct.tolist()) or 0), 1)
    if c == "e" and df.e_pct.notna().any():
        b["pmd"] = round(float(_mediana(com_meses.e_pct.tolist()) or 0), 1)
    return b


def _tm(df, partes):
    return df[[c + "_m" for c in partes]].fillna(0).sum(axis=1)


def _agregado(df, k):
    tot = df.r + df.c + df.o + df.e
    tm = _tm(df, COMPONENTES)
    b = {"n": int(len(df)), "x": int(df.x.sum()), "r": _bloco(df, "r"), "c": _bloco(df, "c", lim=True),
         "o": _bloco(df, "o"), "e": _bloco(df, "e"),
         "t": {"s": _r(tot.sum()), "md": _r(_mediana(tm[df.ok_todas].tolist()) or 0), "n": int(df.ok_todas.sum())}}
    if k == "s":
        b["t"]["ss"] = _r((df.r + df.c + df.o).sum())
        b["t"]["mds"] = _r(_mediana(_tm(df, PARTES_DO_TOTAL["s"])[df.ok].tolist()) or 0)
        b["t"]["ns"] = int(df.ok.sum())
    return b


def _sem_nan(x):
    """NaN (campo vazio que passou pelo pandas) vira null: JSON não tem NaN."""
    if isinstance(x, float) and x != x:
        return None
    if isinstance(x, dict):
        return {k: _sem_nan(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_sem_nan(v) for v in x]
    return x


def _n(v):
    return round(float(v), 2)


def _pessoa_json(r, enderecos):
    def comp(c):
        d = {"t": _r(r[c]), "m": None if pd.isna(r[c + "_m"]) else _r(r[c + "_m"]), "n": _n(r[c + "_n"])}
        if abs(r[c + "_rat"]) >= 1:
            d["a"] = _r(r[c + "_rat"])
        return d
    item = {"id": r.id, "k": r.k, "n": r.nome, "uf": r.uf, "pt": r.partido, "x": int(r.x), "su": int(r.suplente),
            "mc": _n(r.mc), "de": None if pd.isna(r.de) else int(r.de), "ate": None if pd.isna(r.ate) else int(r.ate),
            "r": comp("r"), "u": _r(r.u), "c": comp("c"), "o": comp("o"), "e": comp("e")}
    if r.r_sem_pagamento:
        item["r"]["sp"] = int(r.r_sem_pagamento)
    if r.c_pct is not None and not pd.isna(r.c_pct):
        item["c"]["l"] = _r(r.c_lim)
        item["c"]["p"] = round(float(r.c_pct), 1)
    if r.e_pct is not None and not pd.isna(r.e_pct):
        item["e"]["l"] = _r(r.e_teto)
        item["e"]["p"] = round(float(r.e_pct), 1)
    if r.k == "s":
        item["e"]["est"] = 1
        item["e"]["eb"] = _r(r.e_estimada)  # a estimativa do mês inteiro (a do perfil)
        if r.o_incompleto:
            item["o"]["inc"] = 1
    tm = sum(0 if pd.isna(r[c + "_m"]) else r[c + "_m"] for c in COMPONENTES)
    item["t"] = {"t": _r(r.r + r.c + r.o + r.e), "m": _r(tm), "ok": int(bool(r.ok))}
    if r.k == "s":
        item["t"]["ts"] = _r(r.r + r.c + r.o)
        item["t"]["ms"] = _r(sum(0 if pd.isna(r[c + "_m"]) else r[c + "_m"] for c in PARTES_DO_TOTAL["s"]))
    if r.menos_de_3:
        item["m3"] = list(r.menos_de_3)
    if isinstance(r.rel, str) and r.rel:
        item["rel"] = r.rel
    if enderecos.get(r.id):
        item["url"] = enderecos[r.id]
    return item


COLUNAS_CSV = [
    ("id", "id"), ("nome", "nome"), ("casa", "casa"), ("uf", "uf"), ("partido", "partido_atual"),
    ("x", "no_cargo_hoje"), ("condicao", "condicao"), ("mc", "meses_no_cargo"), ("de", "primeiro_mes_no_cargo"),
    ("ate", "ultimo_mes_no_cargo"),
    ("r", "recebeu_total"), ("u", "recebeu_ajuda_de_custo"), ("r_m", "recebeu_media_mensal_sem_ajuda_de_custo"), ("r_n", "recebeu_meses"),
    ("r_sem_pagamento", "recebeu_meses_no_cargo_sem_pagamento"),
    ("c", "cota_total"), ("c_m", "cota_media_mensal"), ("c_n", "cota_meses"), ("c_lim", "cota_limite_no_periodo"), ("c_pct", "cota_pct_do_limite"),
    ("o", "outros_gastos_mandato_total"), ("o_m", "outros_gastos_mandato_media_mensal"), ("o_n", "outros_gastos_mandato_meses"),
    ("o_inc", "outros_gastos_mandato_incompleto"),
    ("e", "equipe_gabinete_total"), ("e_m", "equipe_gabinete_media_mensal"), ("e_n", "equipe_gabinete_meses"),
    ("e_teto", "equipe_gabinete_valor_disponivel_no_periodo"), ("e_pct", "equipe_gabinete_pct_do_disponivel"),
    ("e_est", "equipe_gabinete_estimada"),
    ("total", "total"), ("total_m", "total_media_mensal"), ("ts", "total_sem_equipe_estimada"), ("ms", "total_sem_equipe_estimada_media_mensal"),
    ("ok", "entra_nas_comparacoes"), ("m3", "partes_com_menos_de_3_meses"),
    ("pagina", "pagina_contas_do_poder"), ("pagina_oficial", "pagina_oficial"),
]
NOMES_PARTES = {"r": "recebeu", "c": "cota", "o": "outros gastos", "e": "equipe"}


def _csv(df, enderecos):
    d = df.copy()
    d["casa"] = d.k.map({"d": "Câmara dos Deputados", "s": "Senado Federal"})
    d["condicao"] = d.suplente.map({True: "suplente", False: "titular"})
    d["x"] = d.x.map({True: "sim", False: "não"})
    d["total"] = d.r + d.c + d.o + d.e
    d["total_m"] = _tm(d, COMPONENTES)
    senado = d.k == "s"
    d["ts"] = (d.r + d.c + d.o).where(senado)
    d["ms"] = _tm(d, PARTES_DO_TOTAL["s"]).where(senado)
    d["e_est"] = senado.map({True: "sim", False: "não"})
    d["o_inc"] = d.o_incompleto.map(lambda v: "sim" if v is True else "não" if v is False else "")
    d["ok"] = d.ok.map({True: "sim", False: "não"})
    d["m3"] = d.menos_de_3.map(lambda xs: "; ".join(NOMES_PARTES[c] for c in xs))
    d["pagina"] = ["https://contasdopoder.com/" + enderecos[i] if enderecos.get(i) else "" for i in d.id]
    d["de"] = d.de.map(lambda v: "" if pd.isna(v) else f"{int(v) // 100}-{int(v) % 100:02d}")
    d["ate"] = d.ate.map(lambda v: "" if pd.isna(v) else f"{int(v) // 100}-{int(v) % 100:02d}")
    for c in COMPONENTES:  # média em branco abaixo do mínimo de meses
        d[c + "_m"] = d[c + "_m"].where(d[c + "_n"] >= MESES_MINIMOS)
    for c in ("r", "u", "r_m", "c", "c_m", "c_lim", "o", "o_m", "e", "e_m", "e_teto", "total", "total_m", "ts", "ms"):
        d[c] = d[c].map(lambda v: "" if v is None or pd.isna(v) else f"{float(v):.2f}")
    for c in ("mc", "r_n", "c_n", "o_n", "e_n", "c_pct", "e_pct"):
        d[c] = d[c].map(lambda v: "" if v is None or pd.isna(v) else f"{float(v):.2f}" if c.endswith("_n") or c == "mc" else f"{float(v):.1f}")
    d = d.sort_values(["casa", "uf", "nome"])
    return d[[a for a, _ in COLUNAS_CSV]].rename(columns=dict(COLUNAS_CSV))


def executar(lanc, politicos, meta):
    """Grava site/dados/balanco.json e site/dados/balanco.csv. Chamado no fim de coleta/site.py, com os lançamentos já
    ajustados como nos perfis."""
    deputados = [p for p in politicos if p["casa"] == "camara"]
    historicos = atualizar_historicos(deputados)
    df, faixas, _, publicados = calcular(lanc, politicos, historicos)
    if df.empty:
        log("Balanço: nenhuma pessoa; fica o arquivo anterior")
        return None
    enderecos = (ler_json(RAIZ / "site" / "dados" / "enderecos.json") or {}).get("p", {}) if (RAIZ / "site" / "dados" / "enderecos.json").exists() else {}
    _, normas = _vigencias()
    teto = _teto_verba()
    lacunas = _lacunas(publicados, faixas)
    gerado = meta.get("gerado_em") or datetime.now().isoformat(timespec="seconds")
    dep = df[df.k == "d"]
    dados = {
        "meta": {
            "gerado_em": gerado, "atualizado": datetime.fromisoformat(gerado).strftime("%d/%m/%Y"),
            "periodo": [202302, _ultimo(faixas)], "faixas": faixas, "lacunas": lacunas, "componentes": COMPONENTES,
            "partes_do_total": {k: list(v) for k, v in PARTES_DO_TOTAL.items()},
            "meses_minimos_mediana": MESES_MINIMOS,
            # pela % arredondada que a página mostra (com a conta exata, 100,0% mostrado contava como acima)
            "acima_100": int(((dep.c_n >= MESES_MINIMOS) & (dep.c_pct.round(1) > 100)).sum()),
            "limites_cota_camara": [{"desde": n["desde"], "norma": n["norma"], "url": n["url_norma"], "valores": n["url_valores"]} for n in normas],
            "teto_verba_gabinete": [{"desde": a, "valor": v} for a, v in teto], "teto_verba_gabinete_fonte": TETO_FONTE,
            "fontes": FONTES, "ressalvas": [x for x in _ressalvas(faixas, lacunas, teto) if x],
            "csv": "dados/balanco.csv", "licenca": "CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/deed.pt-br), citando \"Contas do Poder\" e as fontes originais",
        },
        "p": [_pessoa_json(pd.Series(r), enderecos) for r in df.sort_values(["k", "nome"]).to_dict("records")],
        "casa": {k: _agregado(g, k) for k, g in df.groupby("k")},
        "uf": {k: {uf: _agregado(gg, k) for uf, gg in g.groupby("uf")} for k, g in df.groupby("k")},
    }
    dados = _sem_nan(dados)
    if gravar_json(SAIDA, dados, grupo="k"):
        log(f"Balanço: {SAIDA.relative_to(RAIZ)} ({SAIDA.stat().st_size / 1e3:.0f} KB, {len(df)} pessoas)")
    gravar_csv(_csv(df, enderecos), SAIDA_CSV, encoding="utf-8-sig", lineterminator="\r\n")
    return df
