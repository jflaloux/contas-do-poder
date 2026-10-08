"""Câmara Municipal de Vitória: vereador por vereador.

Fontes (sem cadastro; só abrem de dentro do Brasil, conferido em 08/10/2026; o robots.txt da Câmara tem "Disallow: /",
que é uma convenção e não lei: lemos com pausa, ver README, "Robôs e robots.txt"):
- Folha mensal, nome por nome: a API do Portal da Transparência, https://www.cmv.es.gov.br/transparencia/api/servidores
  (documentada em https://www.cmv.es.gov.br/transparencia/api/webservice), com cargo=VEREADOR, o mês e o ano. O filtro
  de ano que vale é `ano` (o `competencia_ano` da documentação é ignorado, e a API devolve o ano corrente: conferido em
  08/10/2026). Traz nome, matrícula, admissão, demissão, o total de rendimentos do mês, o 13º e as férias; para os
  vereadores, as outras rubricas vêm zeradas (o total não separa o subsídio do auxílio-alimentação). Guardamos só isso:
  nunca INSS, IRRF, descontos nem a data de nascimento.
- Quem está em exercício hoje, nome parlamentar, partido e foto: a lista do Processo Legislativo Eletrônico da Câmara,
  https://camarasempapel.cmv.es.gov.br/api/Vereador/?v=2&qtd=100 (a mesma da página
  https://camarasempapel.cmv.es.gov.br/parlamentares.aspx; situação "Ativo"; quem já saiu fica como "Suplente").
- Subsídio: R$ 17.681,99 desde jan/2025 (o valor de todos os meses inteiros na folha; projeto de lei 62/2023 da Câmara).
- Cota parlamentar: a Câmara informa que não instituiu cotas parlamentares de jan/2023 a set/2026
  (https://www.cmv.es.gov.br/transparencia/documento?tipo=10028): não há verba de gabinete.
- Nome civil, nome de urna, partido (quando a lista da Câmara não tem) e gênero: TSE (eleição de 2024).

Plano de queda (fonte que só tem um caminho; escrito em 08/10/2026, também em dados/referencia/plano-de-queda.json):
- API fora do ar ou com outro formato: o robô mantém o que já gravou (gravação segura) e o site fica até o último mês
  lido. A reserva é automática: o TCE-ES tem o valor por cargo da Câmara de Vitória (site/dados/interior-cargo/es.json,
  RESERVAS_TCE em coleta/situacao.py); se a fonte própria falhar ou ficar 2 meses atrás, a página da cidade passa a
  mostrar o valor do TCE-ES, com aviso.
- Lista de vereadores fora do ar: fica a última lista gravada (em_exercicio.csv); sem lista, o "no cargo" sai da folha.
- Conserto só se couber em cerca de 1 hora; passou disso, a fonte vai para onde.CONGELADAS.
"""
import json
import re

import pandas as pd

from ..config import CACHE, DADOS
from ..util import TempoEsgotado, _sessao, cache_valido, dormir, gravar_csv, log, normalizar_nome, verificar_prazo
from ..assembleias import comum as acomum
from . import comum

COD = 3205309
INICIO = 202501
SITE = "https://www.cmv.es.gov.br"
API = f"{SITE}/transparencia/api/servidores"
DOC_API = f"{SITE}/transparencia/api/webservice"
COTAS = f"{SITE}/transparencia/documento?tipo=10028"
FOLHA_PAGINA = f"{SITE}/transparencia/rh/servidores/?cargo=VEREADOR&situacao=Ativo"
SPL = "https://camarasempapel.cmv.es.gov.br"
LISTA_API = f"{SPL}/api/Vereador/?v=2&qtd=100"
LISTA = f"{SPL}/parlamentares.aspx"
PASTA = DADOS / "municipios" / "vitoria"
C = CACHE / "cmv"
REBAIXAR = 3  # os últimos meses da folha são baixados de novo (a Câmara ainda pode acertar)
VAGAS = 21
SUBSIDIO = 17681.99
CFG = {
    "cod": COD, "n": "Vitória", "uf": "ES", "casa": "Câmara Municipal de Vitória", "vagas": VAGAS, "inicio": INICIO,
    "subsidio": [[202501, SUBSIDIO]],
    "salario_nota": ("Valor do mês na folha da Câmara. A folha publicada traz um total por vereador: aqui, até o subsídio "
                     "(R$ 17.681,99) é salário, e o que passa dele aparece em outros pagamentos (a Câmara informa que paga "
                     "auxílio-alimentação aos vereadores, e a folha não separa as parcelas). O 13º vem à parte."),
    "verba_nome": None, "verba_mes": {},
    "sem_verba": "A Câmara de Vitória informa que não instituiu cota parlamentar de janeiro de 2023 a setembro de 2026: não há verba de gabinete.",
    "conferir_gastos": False,  # sem verba de gabinete: não há gasto do mês para conferir
    "equipe_nota": None,
    "credito_foto": "Câmara Municipal de Vitória", "pagina": LISTA,
    "notas": ["Quem estava no cargo em cada mês: quem aparece na folha da Câmara no mês (com as datas de posse e de saída da "
              "folha). Quem está em exercício hoje: a lista de vereadores da Câmara.",
              "A folha lista os secretários de gabinete parlamentar, mas não diz de qual gabinete cada um é: a equipe de cada "
              "vereador não aparece aqui.",
              "A Câmara de Vitória informa que não instituiu cota parlamentar de janeiro de 2023 a setembro de 2026."],
    "fontes": {"folha": FOLHA_PAGINA, "api": DOC_API, "lista": LISTA, "cotas": COTAS},
}
COLUNAS = ["ano", "mes", "matricula", "nome", "admissao", "demissao", "total", "decimo_terceiro", "ferias"]


def _num(v):
    try:
        return round(float(v or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _get_json(url, arquivo=None, dias=None, **params):
    """JSON da resposta, com novas tentativas; guarda no cache (arquivo) e usa o cache se ainda vale."""
    if arquivo is not None and cache_valido(arquivo, dias):
        return json.loads(arquivo.read_text(encoding="utf-8"))
    verificar_prazo()
    for tentativa in range(3):
        try:
            r = _sessao().get(url, params=params or None, timeout=120)
            r.raise_for_status()
            d = r.json()
            break
        except TempoEsgotado:
            raise
        except Exception:
            if tentativa == 2:
                raise
            dormir(10 + 10 * tentativa)
    if arquivo is not None:
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return d


# ---------------------------------------------------------------- coleta
def _folha_mes(a, m, dias):
    """Linhas dos vereadores na folha de um mês (lista vazia se o mês ainda não saiu)."""
    saida, pagina = [], 1
    while True:
        d = _get_json(API, C / f"folha_{a}{m:02d}_{pagina}.json", dias, competencia_mes=m, competencia_ano=a, ano=a,
                      cargo="VEREADOR", page=pagina, page_size=100)
        for x in d.get("registros") or []:
            if not x or "VEREADOR" not in str(x.get("cargo") or "").upper():
                continue
            if str(x.get("competencia_ano")) != str(a) or str(x.get("competencia_mes")).lstrip("0") != str(m):
                raise RuntimeError(f"a API devolveu {x.get('competencia_mes')}/{x.get('competencia_ano')} para {m:02d}/{a}")
            saida.append({"ano": a, "mes": m, "matricula": str(x.get("matricula") or "").strip(),
                          "nome": " ".join(str(x.get("nome") or "").split()), "admissao": x.get("admissao_data") or "",
                          "demissao": x.get("demissao_data") or "", "total": _num(x.get("total_rendimentos")),
                          "decimo_terceiro": _num(x.get("decimoterceiro")), "ferias": _num(x.get("ferias"))})
        if not d.get("pagina_proxima") or pagina >= 5:
            break
        pagina += 1
    return saida


def folha():
    """Folha dos vereadores, mês a mês. Os meses que já estão em dados/municipios/vitoria/ não são baixados de novo (só os
    REBAIXAR últimos)."""
    ate = comum.ultimo_mes_fechado()
    recentes = comum.menos_meses(ate, REBAIXAR)
    arq = PASTA / "folha.csv"
    velha = pd.read_csv(arq, dtype={"matricula": str}) if arq.exists() else pd.DataFrame(columns=COLUNAS)
    feitos = set(velha.ano * 100 + velha.mes) if len(velha) else set()
    linhas = []
    for a, m in comum.meses(INICIO, ate):
        am = a * 100 + m
        if am in feitos and am <= recentes:
            linhas += velha[(velha.ano * 100 + velha.mes) == am].to_dict("records")
            continue
        novas = _folha_mes(a, m, 5 if am > recentes else None)
        if not novas and am in feitos:  # o mês sumiu da consulta: fica o que estava gravado
            linhas += velha[(velha.ano * 100 + velha.mes) == am].to_dict("records")
            continue
        linhas += novas
    df = pd.DataFrame(linhas, columns=COLUNAS)
    PASTA.mkdir(parents=True, exist_ok=True)
    gravar_csv(df.sort_values(["ano", "mes", "nome"]), arq)
    ult = int((df.ano * 100 + df.mes).max()) if len(df) else None
    log(f"  Vitória: folha com {len(df)} linhas de vereadores, até {ult}")


def lista():
    """Nome parlamentar, nome civil, partido, foto e situação (a lista do Processo Legislativo Eletrônico da Câmara)."""
    d = _get_json(LISTA_API)
    linhas = []
    for x in d.get("dados") or []:
        linhas.append({"id": x.get("ID"), "nome": " ".join(str(x.get("nome_parlamentar") or "").split()),
                       "nome_civil": " ".join(str(x.get("nome") or "").split()), "partido": x.get("partido_sigla") or "",
                       "situacao": x.get("situacao") or "", "foto": x.get("foto") or "",
                       "pagina": f"{SPL}/parlamentar.aspx?id={x.get('ID')}" if x.get("ID") else ""})
    df = pd.DataFrame(linhas, columns=["id", "nome", "nome_civil", "partido", "situacao", "foto", "pagina"])
    ativos = df[df.situacao.str.upper().str.startswith("ATIVO")]
    if not 0.8 * VAGAS <= len(ativos) <= 1.2 * VAGAS:  # página quebrada: não tira ninguém do cargo nem põe ninguém
        log(f"  Vitória: a lista de vereadores veio com {len(ativos)} em exercício para {VAGAS} vagas; fica a que estava gravada")
        return
    PASTA.mkdir(parents=True, exist_ok=True)
    gravar_csv(df, PASTA / "site_vereadores.csv")
    acomum.gravar_em_exercicio(PASTA, list(ativos.nome), VAGAS, LISTA)
    log(f"  Vitória: {len(ativos)} vereadores em exercício na lista da Câmara ({len(df)} na lista)")


def coletar():
    lista()
    folha()


# ---------------------------------------------------------------- montagem
def _categorias(total, decimo, ferias):
    """[(categoria, valor)]: o 13º e as férias à parte; do resto, até o subsídio é salário e o que passa dele, outros
    pagamentos (a folha não separa o auxílio-alimentação)."""
    resto = round(total - decimo - ferias, 2)
    saida = []
    if decimo:
        saida.append(("decimo_terceiro", decimo))
    if ferias:
        saida.append(("ferias", ferias))
    if resto:
        sal = min(resto, SUBSIDIO) if resto > 0 else resto
        saida.append(("salario", round(sal, 2)))
        if resto - sal >= 0.005:
            saida.append(("outros_rendimentos", round(resto - sal, 2)))
    return saida


def montar(tipos):
    arq = PASTA / "folha.csv"
    if not arq.exists():
        return None
    fol = pd.read_csv(arq, dtype={"matricula": str}).fillna({"admissao": "", "demissao": "", "matricula": ""})
    if not len(fol):
        return None
    site = (pd.read_csv(PASTA / "site_vereadores.csv").fillna("") if (PASTA / "site_vereadores.csv").exists()
            else pd.DataFrame(columns=["id", "nome", "nome_civil", "partido", "situacao", "foto", "pagina"]))
    tse = comum.candidatos_tse("ES", "Vitória")
    por_civil = [(n, i) for i, n in enumerate(tse.nome)] if len(tse) else []

    def no_tse(nome_civil):
        i = comum.achar_parecido(nome_civil, por_civil, 0.9) if por_civil else None
        return tse.iloc[i].to_dict() if i is not None else None

    # quem é quem: a matrícula liga os meses (o nome vem abreviado em 2025 e inteiro em 2026: "CAMILLO AUGUSTO M.O.NEVES");
    # o nome mais longo de cada matrícula casa com o TSE; o código é o SQ da candidatura (como em João Pessoa)
    fol["chave"] = [m if m else normalizar_nome(n) for m, n in zip(fol.matricula, fol.nome)]
    nome_da = {k: max(g.nome, key=len) for k, g in fol.groupby("chave")}
    codigos, info = {}, {}
    for k, nome in sorted(nome_da.items()):
        t = no_tse(nome)
        cod = int(t["sq"]) if t else acomum.codigo_de(nome, None)
        codigos[k] = cod
        info.setdefault(cod, {"t": t, "nome": nome})
    fol["codigo"] = fol.chave.map(codigos)
    sem_tse = sorted({v["nome"] for v in info.values() if v["t"] is None})
    if sem_tse:
        log(f"  Vitória: sem candidatura no TSE de 2024: {', '.join(sem_tse)}")

    # a lista da Câmara traz o nome civil: casa com o nome da folha (e, para conferir, o nome parlamentar com o de urna)
    opcoes = [(v["nome"], c) for c, v in info.items()] + [(v["t"]["nome"], c) for c, v in info.items() if v["t"]]
    site_cod = {}
    for r in site.itertuples():
        c = comum.achar_parecido(r.nome_civil, opcoes, 0.88) or comum.achar_parecido(
            r.nome, [(v["t"]["nome_urna"], c) for c, v in info.items() if v["t"]], 0.9)
        if c is None:
            if str(r.situacao).upper().startswith("ATIVO"):
                log(f"  Vitória: na lista da Câmara e não na folha: {r.nome}")
            continue
        site_cod[c] = r
    ultimo = int((fol.ano * 100 + fol.mes).max())
    ate = comum.ultimo_mes_fechado()
    nomes_lista = acomum.ler_em_exercicio(PASTA)
    ativos = {normalizar_nome(n) for n in (nomes_lista or [])}
    atual = {c: (c in site_cod and normalizar_nome(site_cod[c].nome) in ativos) for c in info} if nomes_lista else None

    ver, mandatos, fotos = [], [], []
    for c in sorted(set(fol.codigo)):
        v, s = info[c], site_cod.get(c)
        t = v["t"]
        nome = s.nome if s is not None else (comum.titulo(t["nome_urna"]) if t else comum.titulo(v["nome"]))
        if s is not None and s.foto:
            fotos.append((c, s.foto))
        ver.append({"codigo": c, "nome": nome, "nome_civil": comum.titulo(t["nome"]) if t else comum.titulo(v["nome"]),
                    "partido": (s.partido if s is not None and s.partido else "") or (t["partido"] if t else ""),
                    "genero": t["genero"] if t else "", "eleito": t["situacao"] if t else "",
                    "pagina": (s.pagina if s is not None and s.pagina else "") or LISTA})
        g = fol[fol.codigo == c]
        # meses na folha com algum valor (mês com R$ 0: licença sem subsídio, fora do cargo)
        com_valor = g[g.total.abs() >= 0.5]
        for i, f in comum.periodos_de_meses(com_valor.ano * 100 + com_valor.mes, ultimo):
            mandatos.append({"codigo": c, "inicio": i, "fim": f})
    mandatos = _acertar_periodos(mandatos, fol, ultimo, atual)
    comum.fotos(COD, fotos)
    linhas = []
    for r in fol.itertuples():
        for cat, val in _categorias(float(r.total), float(r.decimo_terceiro), float(r.ferias)):
            linhas.append({"ano": int(r.ano), "mes": int(r.mes), "codigo": int(r.codigo), "categoria": cat, "valor": val})
    ganha = pd.DataFrame(linhas, columns=["ano", "mes", "codigo", "categoria", "valor"])
    cfg = dict(CFG, ultimo_mes=min(ate, ultimo), subsidio_folha=True)
    return comum.montar(cfg, tipos, pd.DataFrame(ver), pd.DataFrame(mandatos), ganha=ganha)


def _acertar_periodos(mandatos, fol, ultimo, atual):
    """Os períodos saem dos meses na folha; aqui ganham o dia certo e o "hoje":
    - começo no meio do mês: a data de admissão da folha (Gilson Gomes Neto, 08/04/2025);
    - saída no meio do mês: a data de demissão da folha (16/05/2025);
    - quem está na lista de hoje da Câmara e não tem período aberto: um período novo começa no mês seguinte ao último da folha;
    - quem tem período aberto e não está na lista de hoje: o período fecha no último mês da folha."""
    from calendar import monthrange
    fol = fol.assign(am=fol.ano * 100 + fol.mes)
    adm = {c: pd.to_datetime(g.admissao, format="%d/%m/%Y", errors="coerce").max() for c, g in fol.groupby("codigo")}
    dem = {c: pd.to_datetime(g.demissao, format="%d/%m/%Y", errors="coerce").max() for c, g in fol.groupby("codigo")}

    def fim_do_mes(aaaamm):
        a, m = divmod(int(aaaamm), 100)
        return f"{a}-{m:02d}-{monthrange(a, m)[1]:02d}"

    for p in mandatos:
        d = adm.get(p["codigo"])
        if d is not None and not pd.isna(d) and d.strftime("%Y-%m") == p["inicio"][:7] and d.day > 1:
            p["inicio"] = d.strftime("%Y-%m-%d")
        if p["fim"]:
            s = dem.get(p["codigo"])
            p["fim"] = (s.strftime("%Y-%m-%d") if s is not None and not pd.isna(s) and s.strftime("%Y-%m") == p["fim"][:7]
                        else fim_do_mes(p["fim"][:7].replace("-", "")))
    if not atual:
        return mandatos
    seguinte = comum.mes_seguinte(ultimo)
    for cod, hoje in atual.items():
        ps = [p for p in mandatos if p["codigo"] == cod]
        aberto = [p for p in ps if not p["fim"]]
        if hoje and ps and not aberto:
            mandatos.append({"codigo": cod, "inicio": f"{seguinte // 100}-{seguinte % 100:02d}-01", "fim": ""})
        elif not hoje and aberto:
            for p in aberto:
                p["fim"] = fim_do_mes(ultimo)
    return mandatos
