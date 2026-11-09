"""Balanço do mandato de deputados federais e senadores (fev/2023 a jan/2027): site/dados/balanco.json e
site/dados/balanco.csv (dados abertos, CC BY 4.0).

Roda no fim da etapa "site" (`coleta/site.py`), com os mesmos lançamentos que viram os perfis (depois de tirar os
pagamentos fora do mandato e o salário dos meses como ministro): o total de cada pessoa é o mesmo do perfil, no período
todo ("Mandato todo").

Componentes, como a base já agrupa (dados/processados/metadados.json, "categorias"):
  r  recebeu: o grupo "ganha" (salário, 13º, férias, auxílios, ajuda de custo e outros pagamentos), bruto;
     a ajuda de custo (pagamento único, na posse e no fim do mandato) entra no total e fica fora da média por mês,
     como no perfil;
  c  cota parlamentar (Câmara: CEAP; Senado: CEAPS), com a % do limite (só na Câmara, ver LIMITES);
  o  outros gastos do mandato: diárias de viagens oficiais e, no Senado, as passagens fora da CEAPS (ATC 2/2023),
     correios e impulsionamento (informados por ano e divididos pelos meses);
  e  equipe do gabinete (Câmara: verba de gabinete; Senado: estimativa pelos assessores ligados ao gabinete).

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
API_CAMARA = "https://dadosabertos.camara.leg.br/api/v2"
INICIO, FIM = date(2023, 2, 1), date(2027, 1, 31)
REFRESCAR_DIAS = 28  # histórico de quem está no cargo: lido de novo depois disto
MAX_POR_RODADA = 150  # históricos lidos por rodada (fora os que faltam ou mudaram de situação)
MESES_MINIMOS = 3  # para entrar na mediana do estado (como a comparação com os colegas no site)


# ---------------------------------------------------------------- meses no cargo
def _aaaamm(d):
    return d.year * 100 + d.month


def _fracoes(intervalos, ate):
    """{AAAAMM: fração do mês no cargo} a partir de intervalos [(início, fim)] de datas (fim incluído)."""
    dias = set()
    for ini, fim in intervalos:
        ini, fim = max(ini, INICIO), min(fim, ate, FIM)
        while ini <= fim:
            dias.add(ini)
            ini += timedelta(days=1)
    por_mes = {}
    for d in dias:
        por_mes[_aaaamm(d)] = por_mes.get(_aaaamm(d), 0) + 1
    return {m: n / calendar.monthrange(m // 100, m % 100)[1] for m, n in por_mes.items()}


EXERCICIO = {"Exercício", "CONVOCADO"}  # o suplente convocado às vezes não ganha o evento "Exercício" depois


def _eventos(eventos):
    """Eventos da legislatura com situação, em ordem de data. A ordem da API vale no mesmo dia ("SUPLENCIA" e
    "Exercício" no mesmo dia: o que vem depois na lista é o que vale), por isso a ordenação é só pela data."""
    return sorted(((dt[:10], sit) for dt, leg, sit in eventos if leg == LEGISLATURA and sit), key=lambda x: x[0])


def _intervalos_camara(eventos, hoje):
    """Intervalos em exercício na legislatura pelo histórico da Câmara: de um evento "Exercício" ou "CONVOCADO" até o
    dia do evento seguinte com outra situação (licença, suplência, vacância, suspensão). O dia da posse e o do
    afastamento contam, como na cota (Ato da Mesa nº 43/2009, arts. 11 e 12)."""
    saida, desde = [], None
    for dt, sit in _eventos(eventos):
        d = date.fromisoformat(dt)
        if sit in EXERCICIO and desde is None:
            desde = d
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


def limite_do_mes(vig_uf, aaaamm):
    """Limite mensal em vigor no mês; se mudou no meio do mês, a média dos dois valores pelos dias."""
    a, m = divmod(aaaamm, 100)
    n = calendar.monthrange(a, m)[1]
    soma = 0.0
    for dia in range(1, n + 1):
        d = date(a, m, dia)
        soma += [v for desde, v in vig_uf if desde <= d][-1] if any(desde <= d for desde, _ in vig_uf) else vig_uf[0][1]
    return soma / n


# ---------------------------------------------------------------- componentes
COMPONENTES = {
    "r": "Recebeu (salário, 13º, férias, auxílios, ajuda de custo e outros pagamentos, bruto)",
    "c": "Cota parlamentar (Câmara: CEAP; Senado: CEAPS)",
    "o": "Outros gastos do mandato (diárias de viagens oficiais; no Senado, também passagens fora da CEAPS, correios e impulsionamento)",
    "e": "Equipe do gabinete (Câmara: verba de gabinete; Senado: estimativa pelos assessores)",
}


def _componente(lanc):
    comp = pd.Series("o", index=lanc.index)
    comp[lanc.grupo == "ganha"] = "r"
    comp[lanc.categoria == "cota_parlamentar"] = "c"
    comp[lanc.grupo == "equipe"] = "e"
    return comp


def _faixa(meses_por_pessoa, minimo):
    """(primeiro, último) mês com pelo menos `minimo` pessoas."""
    ok = sorted(m for m, n in meses_por_pessoa.items() if n >= minimo)
    return [ok[0], ok[-1]] if ok else None


def _r(v):
    return int(round(float(v)))


def _mediana(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


# ---------------------------------------------------------------- montagem
def calcular(lanc, politicos, historicos, hoje=None):
    """(pessoas, faixas, mensal): uma linha por deputado/senador com os totais e as médias, as faixas de meses de cada
    componente em cada casa e o valor de cada pessoa, mês e componente (para a conferência).

    Peso de cada mês na média (dentro da faixa publicada do componente):
      - recebeu: a fração do mês no cargo ou, se maior, o salário do mês ÷ o subsídio (deputado licenciado para ser
        secretário de Estado pode ficar com o salário do mandato; o mês de posse paga só os dias);
      - cota, outros gastos e equipe: a fração do mês no cargo (a cota da Câmara é proporcional aos dias em exercício,
        Ato da Mesa nº 43/2009, art. 11, e a verba de gabinete do mês de posse ou de saída também vem proporcional); num
        mês sem nenhum dia no cargo e com valor (licença médica sem suplente convocado, que conta como exercício pelo
        art. 12; gabinete que continua na licença), o mês inteiro. O limite da cota usa os mesmos pesos."""
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

    # faixa de meses publicada de cada componente em cada casa: os meses com pelo menos metade das pessoas do mês
    # mais cheio. "Outros" (diárias, que vêm da folha) segue a folha.
    faixas = {}
    for k, g in mensal[mensal.am > 0].groupby("k"):
        f = {}
        for c in ("r", "c", "e"):
            n = g[g[c].abs() > 0.5].groupby("am").id_politico.nunique()
            f[c] = _faixa(n.to_dict(), max(1, int(n.max() / 2))) if len(n) else None
        f["o"] = f["r"]
        faixas[k] = f

    vig, _ = _vigencias()
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
        fr = _fracoes(intervalos, ate_dia)
        mm = por_id.get(pid, pd.DataFrame(columns=list(COMPONENTES)))
        tot = {c: float(totais.get((pid, c), 0.0)) for c in COMPONENTES}
        if not fr and not any(abs(v) >= 1 for v in tot.values()):
            continue
        f = faixas[k]
        u = float(unico.get(pid, 0.0))
        linha = {"id": pid, "k": k, "nome": p["nome"], "uf": p.get("uf"), "partido": p.get("partido"),
                 "x": bool(p.get("em_exercicio")),
                 "suplente": "uplente" in str(p.get("condicao_eleitoral") or p.get("participacao") or ""),
                 "rel": p.get("relacionado"), "pagina_oficial": p.get("pagina_oficial"),
                 "mc": sum(fr.values()), "de": min(fr) if fr else None, "ate": max(fr) if fr else None, "u": u}
        pesos = {}
        for c in COMPONENTES:
            a, b = f[c] or (0, 0)
            meses = sorted(m for m in set(fr) | set(mm.index) if a <= m <= b)
            peso = {}
            for m in meses:
                v = float(mm[c].get(m, 0.0)) if c in mm else 0.0
                if c == "r":
                    s_ = float(sal.get((pid, m), 0.0))
                    w = max(fr.get(m, 0.0), min(1.0, max(0.0, s_ / subsidio(m))))
                else:  # a cota é proporcional aos dias em exercício (Ato da Mesa nº 43/2009, art. 11); a equipe também
                    w = fr.get(m, 0.0) or (1.0 if v > 0.5 else 0.0)
                if w > 0:
                    peso[m] = w
            pesos[c] = peso
            n = sum(peso.values())
            no_periodo = float(mm.loc[[m for m in mm.index if a <= m <= b], c].sum()) if c in mm and len(mm) else 0.0
            linha[c] = tot[c]
            linha[c + "_n"] = n
            linha[c + "_m"] = (no_periodo - (u if c == "r" else 0.0)) / n if n > 0 else None
            linha[c + "_fora"] = tot[c] - no_periodo  # fora da faixa publicada (ou sem mês): só no total
            linha[c + "_rat"] = float(rateado.get((pid, c), 0.0))
        if k == "d" and p.get("uf") in vig:
            lim = sum(w * limite_do_mes(vig[p["uf"]], m) for m, w in pesos["c"].items())
            linha["c_lim"] = lim
            usado = tot["c"] - linha["c_fora"]
            linha["c_pct"] = usado / lim * 100 if lim > 0 else None
        else:
            linha["c_lim"] = linha["c_pct"] = None
        pessoas.append(linha)
    return pd.DataFrame(pessoas), faixas, mensal


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


def _mes_txt(am):
    nomes = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
    return f"{nomes[am % 100 - 1]}/{am // 100}" if am else ""


def _ressalvas(faixas):
    fd, fs = faixas.get("d", {}), faixas.get("s", {})
    return [
        "Período: o mandato que começou em 1º/2/2023 e termina em 31/1/2027. Os dados são parciais: vão até o último mês "
        f"que cada fonte publicou (Câmara: folha até {_mes_txt((fd.get('r') or [0, 0])[1])}, cota até {_mes_txt((fd.get('c') or [0, 0])[1])}, "
        f"verba de gabinete até {_mes_txt((fd.get('e') or [0, 0])[1])}; Senado: folha até {_mes_txt((fs.get('r') or [0, 0])[1])}, "
        f"CEAPS até {_mes_txt((fs.get('c') or [0, 0])[1])}). O balanço é refeito a cada atualização semanal.",
        "Valores brutos, como as fontes publicam. Não entram o imposto de renda, a previdência nem o valor líquido de ninguém.",
        "Meses no cargo: pelos dias em exercício, das datas oficiais da Câmara (histórico de cada deputado) e do Senado "
        "(exercícios de cada senador). Um mês com metade dos dias no cargo conta meio mês.",
        "Média por mês: o total de cada parte dividido pelos meses no cargo dentro dos meses que a fonte já publicou. "
        "Quem teve mandato curto se compara pela média por mês, não pelo total. Nos meses de licença (médica ou para ser "
        "secretário de Estado, por exemplo), entra na conta o que a fonte mostra: o salário, quando a pessoa ficou com o "
        "salário do mandato (o mês conta pela parte do subsídio paga), e o gabinete e a cota, quando continuaram funcionando "
        "(o mês conta inteiro). Por isso cada parte diz por quantos meses foi dividida.",
        "A ajuda de custo (paga de uma vez, na posse e no fim do mandato) entra no total recebido e fica fora da média por mês.",
        "Os valores mudaram no período: o subsídio subiu em abr/2023, fev/2024 e fev/2025 (Decreto Legislativo nº 172/2022) e "
        "o limite da cota da Câmara em fev/2026. Quem esteve no cargo só no fim do período tende a ter média por mês maior.",
        "Cota parlamentar: os 3 últimos meses ainda podem receber notas (o prazo é de 90 dias).",
        "Câmara: desde ago/2025 as passagens compradas pelo sistema da Câmara (SIGEPA) não aparecem nos arquivos de dados "
        "abertos da cota. Usamos o total mensal da consulta oficial da cota no site da Câmara e mostramos a diferença como "
        "\"passagens aéreas e itens sem detalhe\".",
        "Câmara: % do limite da cota = o que foi usado ÷ a soma dos limites mensais do estado nos meses no cargo (Ato da Mesa "
        "nº 270/2023 até 19/2/2026; Ato da Mesa nº 244/2026 desde 20/2/2026). A % pode passar de 100: além da cota, o deputado "
        "tem direito ao reembolso de até quatro trechos aéreos por mês entre o estado e Brasília (Ato da Mesa nº 43/2009, art. 2º, "
        "§ 3º), e essas passagens aparecem no total da cota que a Câmara publica; líderes, vice-líderes, presidentes de "
        "comissão e suplentes da Mesa têm um adicional mensal (art. 1º, § 1º) que não entra no limite que usamos. O saldo de "
        "um mês passa para o seguinte dentro do mesmo ano (art. 13). A cota de quem entra ou sai no meio do mês é "
        "proporcional aos dias (art. 11), e o limite também.",
        "Senado: o limite da CEAPS de cada senador soma uma verba fixa ao valor de cinco trechos aéreos entre Brasília e a "
        "capital do estado (Senado, perguntas frequentes) e foi atualizado na legislatura (Ato do Presidente nº 8/2025, em "
        "vigor em 1º/3/2025); o Senado não publica a tabela por estado em formato aberto, e por isso o balanço não traz a % "
        "do limite dos senadores.",
        "Senado: o custo da equipe é uma estimativa: a folha de pagamento ligada à lotação de cada servidor comissionado, "
        "pelo nome (homônimos ficam de fora). Quando o titular se licencia (para ser ministro, por exemplo), a equipe "
        "lotada no gabinete dele continua na conta dele.",
        "Câmara: a página oficial mostra R$ 0,00 de verba de gabinete para a maioria dos suplentes que ficaram poucos meses; "
        "a mediana da equipe por estado conta só quem teve equipe.",
        "Partes informadas só por ano (o auxílio-moradia da Câmara; as passagens fora da CEAPS, os correios e o "
        "impulsionamento do Senado) são divididas pelos meses: o total do período é o da fonte, a divisão por mês é "
        "aproximada (≈). Em 2023, o valor do ano pode incluir janeiro, que ainda era da legislatura anterior.",
        "Deputado ou senador que foi ministro: os meses como ministro ficam na página de ministro (o salário pago pelo "
        "Congresso nesses meses não aparece aqui, para não contar duas vezes).",
        "Sem agregados por partido. O partido é o atual, como no perfil.",
    ]


def _bloco(df, c, lim=False):
    """Soma do componente, mediana da média por mês (de quem teve MESES_MINIMOS meses no cargo) e número de pessoas na
    mediana. Equipe: só quem teve equipe (como a comparação com os colegas no perfil), porque a página oficial mostra
    R$ 0,00 de verba de gabinete para a maioria dos suplentes que ficaram poucos meses."""
    com_meses = df[df[c + "_n"] >= MESES_MINIMOS]
    if c == "e":
        com_meses = com_meses[com_meses.e > 0.5]
    b = {"s": _r(df[c].sum()), "md": _r(_mediana(com_meses[c + "_m"].dropna().tolist()) or 0), "n": int(len(com_meses))}
    if lim and df.c_lim.notna().any():
        tem = df[df.c_lim.notna() & (df.c_lim > 0)]
        b["pct"] = round(float(tem.c.sum() / tem.c_lim.sum() * 100), 1) if len(tem) else None  # noqa
        b["pmd"] = round(float(_mediana(com_meses.c_pct.dropna().tolist()) or 0), 1)
    return b


def _agregado(df):
    tot = df.r + df.c + df.o + df.e
    tm = df[["r_m", "c_m", "o_m", "e_m"]].fillna(0).sum(axis=1)
    ok = df.mc >= MESES_MINIMOS
    return {"n": int(len(df)), "x": int(df.x.sum()), "r": _bloco(df, "r"), "c": _bloco(df, "c", lim=True),
            "o": _bloco(df, "o"), "e": _bloco(df, "e"),
            "t": {"s": _r(tot.sum()), "md": _r(_mediana(tm[ok].tolist()) or 0), "n": int(ok.sum())}}


def _sem_nan(x):
    """NaN (campo vazio que passou pelo pandas) vira null: JSON não tem NaN."""
    if isinstance(x, float) and x != x:
        return None
    if isinstance(x, dict):
        return {k: _sem_nan(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_sem_nan(v) for v in x]
    return x


def _pessoa_json(r, enderecos):
    def comp(c):
        d = {"t": _r(r[c]), "m": None if pd.isna(r[c + "_m"]) else _r(r[c + "_m"]), "n": round(float(r[c + "_n"]), 1)}
        if abs(r[c + "_rat"]) >= 1:
            d["a"] = _r(r[c + "_rat"])
        return d
    item = {"id": r.id, "k": r.k, "n": r.nome, "uf": r.uf, "pt": r.partido, "x": int(r.x), "su": int(r.suplente),
            "mc": round(float(r.mc), 1), "de": None if pd.isna(r.de) else int(r.de), "ate": None if pd.isna(r.ate) else int(r.ate),
            "r": comp("r"), "u": _r(r.u), "c": comp("c"), "o": comp("o"), "e": comp("e")}
    if r.c_pct is not None and not pd.isna(r.c_pct):
        item["c"]["l"] = _r(r.c_lim)
        item["c"]["p"] = round(float(r.c_pct), 1)
    tm = sum(0 if pd.isna(r[c + "_m"]) else r[c + "_m"] for c in COMPONENTES)
    item["t"] = {"t": _r(r.r + r.c + r.o + r.e), "m": _r(tm)}
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
    ("c", "cota_total"), ("c_m", "cota_media_mensal"), ("c_n", "cota_meses"), ("c_lim", "cota_limite_no_periodo"), ("c_pct", "cota_pct_do_limite"),
    ("o", "outros_gastos_mandato_total"), ("o_m", "outros_gastos_mandato_media_mensal"), ("o_n", "outros_gastos_mandato_meses"),
    ("e", "equipe_gabinete_total"), ("e_m", "equipe_gabinete_media_mensal"), ("e_n", "equipe_gabinete_meses"),
    ("total", "total"), ("total_m", "total_media_mensal"), ("pagina", "pagina_contas_do_poder"), ("pagina_oficial", "pagina_oficial"),
]


def _csv(df, enderecos):
    d = df.copy()
    d["casa"] = d.k.map({"d": "Câmara dos Deputados", "s": "Senado Federal"})
    d["condicao"] = d.suplente.map({True: "suplente", False: "titular"})
    d["x"] = d.x.map({True: "sim", False: "não"})
    d["total"] = d.r + d.c + d.o + d.e
    d["total_m"] = d[["r_m", "c_m", "o_m", "e_m"]].fillna(0).sum(axis=1)
    d["pagina"] = ["https://contasdopoder.com/" + enderecos[i] if enderecos.get(i) else "" for i in d.id]
    d["de"] = d.de.map(lambda v: "" if pd.isna(v) else f"{int(v) // 100}-{int(v) % 100:02d}")
    d["ate"] = d.ate.map(lambda v: "" if pd.isna(v) else f"{int(v) // 100}-{int(v) % 100:02d}")
    for c in ("r", "u", "r_m", "c", "c_m", "c_lim", "o", "o_m", "e", "e_m", "total", "total_m"):
        d[c] = d[c].map(lambda v: "" if v is None or pd.isna(v) else f"{float(v):.2f}")
    for c in ("mc", "r_n", "c_n", "o_n", "e_n", "c_pct"):
        d[c] = d[c].map(lambda v: "" if v is None or pd.isna(v) else f"{float(v):.1f}")
    d = d.sort_values(["casa", "uf", "nome"])
    return d[[a for a, _ in COLUNAS_CSV]].rename(columns=dict(COLUNAS_CSV))


def executar(lanc, politicos, meta):
    """Grava site/dados/balanco.json e site/dados/balanco.csv. Chamado no fim de coleta/site.py, com os lançamentos já
    ajustados como nos perfis."""
    deputados = [p for p in politicos if p["casa"] == "camara"]
    historicos = atualizar_historicos(deputados)
    df, faixas, _ = calcular(lanc, politicos, historicos)
    if df.empty:
        log("Balanço: nenhuma pessoa; fica o arquivo anterior")
        return None
    enderecos = (ler_json(RAIZ / "site" / "dados" / "enderecos.json") or {}).get("p", {}) if (RAIZ / "site" / "dados" / "enderecos.json").exists() else {}
    _, normas = _vigencias()
    gerado = meta.get("gerado_em") or datetime.now().isoformat(timespec="seconds")
    dados = {
        "meta": {
            "gerado_em": gerado, "atualizado": datetime.fromisoformat(gerado).strftime("%d/%m/%Y"),
            "periodo": [202302, 202701], "faixas": faixas, "componentes": COMPONENTES,
            "meses_minimos_mediana": MESES_MINIMOS,
            "limites_cota_camara": [{"desde": n["desde"], "norma": n["norma"], "url": n["url_norma"], "valores": n["url_valores"]} for n in normas],
            "fontes": FONTES, "ressalvas": _ressalvas(faixas),
            "csv": "dados/balanco.csv", "licenca": "CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/deed.pt-br), citando \"Contas do Poder\" e as fontes originais",
        },
        "p": [_pessoa_json(pd.Series(r), enderecos) for r in df.sort_values(["k", "nome"]).to_dict("records")],
        "casa": {k: _agregado(g) for k, g in df.groupby("k")},
        "uf": {k: {uf: _agregado(gg) for uf, gg in g.groupby("uf")} for k, g in df.groupby("k")},
    }
    dados = _sem_nan(dados)
    if gravar_json(SAIDA, dados, grupo="k"):
        log(f"Balanço: {SAIDA.relative_to(RAIZ)} ({SAIDA.stat().st_size / 1e3:.0f} KB, {len(df)} pessoas)")
    gravar_csv(_csv(df, enderecos), SAIDA_CSV, encoding="utf-8-sig", lineterminator="\r\n")
    return df
