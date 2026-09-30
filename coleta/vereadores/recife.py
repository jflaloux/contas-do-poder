"""Câmara Municipal do Recife: vereador por vereador.

Fontes (dados abertos da Câmara, sem cadastro):
- Mandatos (titulares e suplentes da legislatura), nome parlamentar, partido e foto:
  https://e-processo.recife.pe.leg.br/@@legislaturas/<id> (JSON)
- Folha de pagamento nominal, mês a mês, em CSV (vereadores e assessores; a lotação do assessor é "VER. <nome>"):
  https://transparenciacamara.recife.pe.gov.br/codigos/web/camara/remuneracaoServidores_csv.php?ano=&mes=
  Guardamos só o bruto de cada vereador e, dos gabinetes, o número de pessoas, o custo bruto e os cargos.
  O CPF vem mascarado e não é guardado; os descontos também não.
- Verba Indenizatória (a "CEAP" do Recife): por tipo de despesa e por mês, sem fornecedor:
  https://transparencia.recife.pe.leg.br/++api++/legislativo/verba-indenizatoria/<ano>/formdata?codVereador=
- Nome completo e gênero: TSE (eleição de 2024).
"""
import io
import json
import re
import time

import pandas as pd

from ..config import CACHE, DADOS
from ..util import TempoEsgotado, _sessao, cache_valido, log, normalizar_nome, verificar_prazo
from . import comum

COD = 2611606
INICIO = 202501
EPROC = "https://e-processo.recife.pe.leg.br"
TRANSP = "https://transparencia.recife.pe.leg.br/++api++/legislativo"
FOLHA = "https://transparenciacamara.recife.pe.gov.br/codigos/web/camara/remuneracaoServidores_csv.php"
PASTA = DADOS / "municipios" / "recife"
C = CACHE / "cmrecife"
REBAIXAR = 3
SUBSIDIO = 23428.64
# Em ago/2026 a folha traz também R$ 18.980 (o subsídio da legislatura 2021–2024) para vereadores e ex-vereadores
# daquela legislatura. Não é do mandato atual: fica de fora (e o site avisa).
DA_LEGISLATURA_PASSADA = {18980.00, 17082.00}
CFG = {
    "cod": COD, "n": "Recife", "uf": "PE", "casa": "Câmara Municipal do Recife", "vagas": 39, "inicio": INICIO,
    "subsidio": [[202501, SUBSIDIO]],
    "verba_nome": "Verba Indenizatória", "verba_mes": {"2025": 16000.0, "2026": 16000.0},
    "verba_regra": "Reembolso de despesas do mandato, até R$ 16 mil por mês. O que passa do limite é pago pelo próprio vereador.",
    "verba_notas": ["A Câmara publica a verba por tipo de despesa e por mês, sem o nome dos fornecedores.",
                    "Quando o vereador apresenta mais que o limite, a diferença sai do bolso dele: aqui cada tipo de despesa é reduzido na mesma proporção, para a soma dar o que a Câmara pagou."],
    "salario_nota": "Subsídio de R$ 23.428,64 por mês desde janeiro de 2025 (o presidente da Câmara recebe 50% a mais). Valores brutos da folha da Câmara, com 13º e 1/3 de férias.",
    "equipe_nota": "Assessores lotados no gabinete, pela folha de pagamento da Câmara (valor bruto).",
    "credito_foto": "Câmara Municipal do Recife", "pagina": "https://www.recife.pe.leg.br/",
    "fontes": {"mandatos": f"{EPROC}/@@legislaturas", "folha": "https://transparenciacamara.recife.pe.gov.br/",
               "verba": "https://transparencia.recife.pe.leg.br/legislativo/verba-indenizatoria"},
    "notas": ["Em ago/2026 a folha da Câmara traz também pagamentos de R$ 18.980 (o salário da legislatura 2021–2024) a vereadores e ex-vereadores daquela legislatura. Não entram aqui, porque não são do mandato atual."],
}


def _pedir(url, arquivo=None, dias=None, params=None, texto=False):
    if arquivo is not None and cache_valido(arquivo, dias):
        t = arquivo.read_text(encoding="utf-8")
        return t if texto else json.loads(t)
    verificar_prazo()
    for tentativa in range(6):
        try:
            r = _sessao().get(url, params=params, timeout=120)
            if r.status_code >= 500 and tentativa >= 1:
                r.raise_for_status()  # erro do próprio sistema da Câmara: não adianta insistir
            r.raise_for_status()
            t = r.content.decode("utf-8-sig", errors="replace") if texto else r.text
            break
        except Exception as e:  # um dos servidores da Câmara às vezes mostra um certificado vencido: tentar de novo resolve
            resp = getattr(e, "response", None)
            if tentativa == 5 or (resp is not None and resp.status_code >= 500 and tentativa >= 1):
                raise
            time.sleep(3 + 5 * tentativa)
    time.sleep(1.5)
    if arquivo is not None:
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_text(t, encoding="utf-8")
    return t if texto else json.loads(t)


def _valor(t):
    t = re.sub(r"[^\d,]", "", str(t or ""))
    return float(t.replace(",", ".")) if t else 0.0


# ---------------------------------------------------------------- coleta
def mandatos():
    legs = _pedir(f"{EPROC}/@@legislaturas", C / "legislaturas.json", 7).get("items") or []
    atual = next((l for l in legs if l.get("atual")), None) or max(legs, key=lambda l: l.get("start") or "")
    itens = _pedir(f"{EPROC}/@@legislaturas/{atual['id']}", C / f"legislatura_{atual['id']}.json", 5).get("items") or []
    linhas = {}
    for i in itens:
        x = linhas.setdefault(i["id"], {"parlamentar": int(i["id"]), "nome": (i.get("title") or "").strip(), "titular": False,
                                         "partido": ((i.get("partido") or [{}])[0] or {}).get("token", ""), "foto": i.get("url_foto") or "",
                                         "votos": i.get("votos") or ""})
        x["titular"] = x["titular"] or i.get("mandato") == "Titular"
    df = pd.DataFrame(list(linhas.values()))
    PASTA.mkdir(parents=True, exist_ok=True)
    df.to_csv(PASTA / "mandatos.csv", index=False)
    comum.fotos(COD, [(r.parlamentar, r.foto) for r in df.itertuples() if r.foto])
    return df


def folha():
    """Bruto de cada vereador por mês; dos gabinetes, pessoas e custo bruto por mês; cargos do último mês."""
    ate = comum.ultimo_mes_fechado()
    recentes = comum.menos_meses(ate, REBAIXAR)
    arq_v, arq_g, arq_c = PASTA / "folha_vereadores.csv", PASTA / "folha_gabinetes.csv", PASTA / "cargos_gabinetes.csv"
    fv = pd.read_csv(arq_v) if arq_v.exists() else pd.DataFrame(columns=["ano", "mes", "nome", "funcao", "valor"])
    fg = pd.read_csv(arq_g) if arq_g.exists() else pd.DataFrame(columns=["ano", "mes", "lotacao", "pessoas", "custo"])
    feitos = set(fg.ano * 100 + fg.mes) if len(fg) else set()
    ultimo = None
    for a, m in comum.meses(INICIO, ate):
        am = a * 100 + m
        if am in feitos and am <= recentes:
            continue
        t = _pedir(FOLHA, params={"ano": a, "mes": f"{m:02d}", "nome": "", "cpf": "", "matricula": "", "categoria": "", "cargo": ""}, texto=True)
        d = pd.read_csv(io.StringIO(t), sep=";", dtype=str).fillna("")
        if not len(d):
            continue  # mês ainda não publicado
        d.columns = [normalizar_nome(c) for c in d.columns]
        lot = d["LOTACAO SECRETARIA/DIRETORIA"].str.strip()
        ver = d[d.CATEGORIA.str.contains("VEREAD") | d.CARGO.str.strip().eq("VEREADOR")]
        v_linhas = [{"ano": a, "mes": m, "nome": n.strip(), "funcao": f.strip(), "valor": _valor(v)}
                    for n, f, v in zip(ver.NOME, ver.FUNCAO, ver["TOTAL DE VANTAGENS"])]
        gab = d[lot.str.match(r"^VER\b\.?") & ~lot.eq("VEREADORES") & ~d.index.isin(ver.index)]
        g_linhas = [{"ano": a, "mes": m, "lotacao": k, "pessoas": len(g), "custo": round(g["TOTAL DE VANTAGENS"].map(_valor).sum(), 2)}
                    for k, g in gab.groupby(gab["LOTACAO SECRETARIA/DIRETORIA"].str.strip())]
        fv = pd.concat([fv[(fv.ano * 100 + fv.mes) != am], pd.DataFrame(v_linhas)], ignore_index=True)
        fg = pd.concat([fg[(fg.ano * 100 + fg.mes) != am], pd.DataFrame(g_linhas)], ignore_index=True)
        ultimo = (a, m, gab)
        PASTA.mkdir(parents=True, exist_ok=True)
        fv.to_csv(arq_v, index=False)
        fg.to_csv(arq_g, index=False)
        log(f"  Recife: folha de {m:02d}/{a} ({len(d)} pessoas, {len(ver)} linhas de vereador)")
    if ultimo:
        a, m, gab = ultimo
        cargos = gab.groupby([gab["LOTACAO SECRETARIA/DIRETORIA"].str.strip(), gab.FUNCAO.str.strip().map(_cargo)]).size()
        pd.DataFrame([{"ano": a, "mes": m, "lotacao": l, "cargo": c, "pessoas": int(n)} for (l, c), n in cargos.items()]).to_csv(arq_c, index=False)


_CARGOS = [(r"COORD\s*GAB", "Assessor parlamentar (coordenação do gabinete)"), (r"COORD\s*LEG", "Assessor parlamentar (coordenação legislativa)"),
           (r"SEC\s*PARL", "Assessor parlamentar (secretaria)"), (r"ESPECIA", "Assessor parlamentar especial"),
           (r"APOIO", "Assessor de apoio parlamentar"), (r"GABI", "Assessor parlamentar de gabinete")]


def _cargo(funcao):
    for padrao, nome in _CARGOS:
        if re.search(padrao, funcao or ""):
            return nome
    return "Outros (servidor à disposição, sem função informada)" if normalizar_nome(funcao) in ("", "SEM INFORMACAO") else comum.titulo(funcao)


def verba():
    """Verba Indenizatória: tipo de despesa × mês, por vereador e ano (o ano corrente é baixado de novo)."""
    ate = comum.ultimo_mes_fechado()
    linhas, erros = [], []
    for ano in range(INICIO // 100, ate // 100 + 1):
        dias = 5 if ano == ate // 100 else None
        try:
            lista = (_pedir(f"{TRANSP}/verba-indenizatoria/{ano}", C / f"verba_lista_{ano}.json", dias).get("_vereadores") or {}).get("data") or []
        except TempoEsgotado:
            raise
        except Exception as e:  # noqa: BLE001 — a página do ano fora do ar: segue com os outros anos
            log(f"  Recife: a lista da verba de {ano} não abriu ({e})")
            erros.append({"ano": ano, "token": "", "nome": ""})
            continue
        for v in lista:
            try:
                d = _pedir(f"{TRANSP}/verba-indenizatoria/{ano}/formdata", C / f"verba_{ano}_{v['token']}.json", dias, params={"codVereador": v["token"]})
            except TempoEsgotado:
                raise
            except Exception as e:  # noqa: BLE001 — a página de um vereador pode dar erro no site da Câmara
                log(f"  Recife: verba de {v['title']} em {ano} não abriu ({e})")
                erros.append({"ano": ano, "token": v["token"], "nome": v["title"].strip()})
                continue
            dados = d.get("data") or {}
            totais = {normalizar_nome(t.get("descricao")): t for t in dados.get("totals") or []}
            pago = next((t for k, t in totais.items() if k.startswith("CEAP PAGA")), {})
            apresentado = next((t for k, t in totais.items() if k.startswith("TOTAL APRESENTADO")), {})
            for m in range(1, 13):
                chave = f"valor_{m:02d}"
                ap, pg = _valor(apresentado.get(chave)), _valor(pago.get(chave))
                if not ap and not pg:
                    continue
                fator = pg / ap if ap else 0.0
                for it in dados.get("items") or []:
                    x = _valor(it.get(chave))
                    if x:
                        linhas.append({"ano": ano, "mes": m, "token": v["token"], "nome": v["title"].strip(), "tipo": it["descricao"].strip(),
                                       "apresentado": x, "valor": round(x * fator, 2)})
    PASTA.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(linhas).to_csv(PASTA / "verba.csv", index=False)
    pd.DataFrame(erros, columns=["ano", "token", "nome"]).to_csv(PASTA / "verba_erros.csv", index=False)
    log(f"  Recife: verba indenizatória, {len(linhas)} linhas (tipo × mês)")


def coletar():
    mandatos()
    folha()
    verba()


# ---------------------------------------------------------------- montagem
_TIPOS_RECIFE = [(r"ALUGUEL|CONDOM|CELPE|COMPESA|IPTU|INTERNET|ESCRIT", "Escritório (aluguel, contas, internet)"),
                 (r"LOCACAO DE AUTOMOVEL|PECAS", "Aluguel de carro e peças"), (r"PASSAGE|HOSPED|LOCOMOCAO", "Passagens, hospedagem e transporte"),
                 (r"CONSULT|ASSESS|PESQUISA", "Consultorias e assessorias"), (r"MOVEIS|SOFTWARE|EQUIPAMENT", "Móveis, equipamentos e software"),
                 (r"GRAFIC|COPIA", "Serviços gráficos e cópias"), (r"EXPEDIENTE", "Material de escritório"),
                 (r"DIVULG|PUBLICID", "Divulgação do mandato"), (r"COMBUST", "Combustível"), (r"ASSINATURA|JORNA|REVISTA", "Jornais, revistas e assinaturas")]


def _tipo(desc):
    d = normalizar_nome(desc)
    for padrao, nome in _TIPOS_RECIFE:
        if re.search(padrao, d):
            return nome
    return comum.tipo_curto(desc)


def _categorias(valor, funcao, mes):
    """Bruto do mês -> salário (até o subsídio; 1,5× para o presidente) e o resto (13º em dezembro; férias e outros)."""
    base = SUBSIDIO * (1.5 if "PRESIDENTE" == normalizar_nome(funcao) else 1)
    if valor <= base * 1.01:
        return [("salario", valor)]
    if mes == 12:
        return [("salario", base), ("decimo_terceiro", valor - base)]
    return [("salario", base), ("outros_rendimentos", valor - base)]


def montar(tipos):
    if not (PASTA / "mandatos.csv").exists():
        return None
    ate = comum.ultimo_mes_fechado()
    mand = pd.read_csv(PASTA / "mandatos.csv", dtype={"partido": str}).fillna("")
    fv = pd.read_csv(PASTA / "folha_vereadores.csv").fillna("") if (PASTA / "folha_vereadores.csv").exists() else pd.DataFrame(columns=["ano", "mes", "nome", "funcao", "valor"])
    fg = pd.read_csv(PASTA / "folha_gabinetes.csv") if (PASTA / "folha_gabinetes.csv").exists() else pd.DataFrame(columns=["ano", "mes", "lotacao", "pessoas", "custo"])
    fc = pd.read_csv(PASTA / "cargos_gabinetes.csv") if (PASTA / "cargos_gabinetes.csv").exists() else pd.DataFrame(columns=["ano", "mes", "lotacao", "cargo", "pessoas"])
    vb = pd.read_csv(PASTA / "verba.csv") if (PASTA / "verba.csv").exists() else None
    tse = comum.candidatos_tse("PE", "Recife")
    linhas_v = []
    for r in mand.itertuples():
        t = comum.achar_no_tse(r.nome, tse)
        linhas_v.append({"codigo": int(r.parlamentar), "nome": r.nome, "nome_civil": comum.titulo(t["nome"]) if t is not None else "",
                         "partido": r.partido or (t["partido"] if t is not None else ""), "genero": t["genero"] if t is not None else "",
                         "eleito": "eleito" if str(r.titular) == "True" else "suplente",
                         "pagina": f"https://transparencia.recife.pe.leg.br/legislativo/vereadores/item/{int(r.parlamentar)}", "civil_tse": t["nome"] if t is not None else ""})
    ver = pd.DataFrame(linhas_v)
    sem_tse = [r.nome for r in ver.itertuples() if not r.civil_tse]
    if sem_tse:
        log(f"  Recife: sem nome no TSE: {', '.join(sem_tse)}")

    # folha: nome da folha (abreviado) -> vereador, pelo nome completo do TSE
    def pelocivil_tse(nome):
        achados = [r.codigo for r in ver.itertuples() if r.civil_tse and comum.compativel(nome, r.civil_tse)]
        return achados[0] if len(achados) == 1 else None
    fv = fv[~(((fv.ano * 100 + fv.mes) >= 202502) & fv.valor.round(2).isin(DA_LEGISLATURA_PASSADA))] if len(fv) else fv
    # jan/2025: valores pequenos são acertos da legislatura passada (férias e dias de dezembro), pagos a quem saiu
    fv = fv[~(((fv.ano * 100 + fv.mes) == 202501) & (fv.valor < SUBSIDIO / 2))] if len(fv) else fv
    fv = fv.assign(codigo=fv.nome.map(pelocivil_tse)) if len(fv) else fv.assign(codigo=pd.Series(dtype=float))
    ultimo_folha = int((fv.ano * 100 + fv.mes).max()) if len(fv) else None
    ganha_l, pagos = [], {}
    for r in fv[fv.codigo.notna()].itertuples():
        for c, v in _categorias(float(r.valor), r.funcao, int(r.mes)):
            ganha_l.append({"ano": int(r.ano), "mes": int(r.mes), "codigo": int(r.codigo), "categoria": c, "valor": round(v, 2)})
        if r.valor > 0:
            pagos.setdefault(int(r.codigo), set()).add(int(r.ano) * 100 + int(r.mes))
    fora = sorted(set(fv[fv.codigo.isna() & ((fv.ano * 100 + fv.mes) >= 202502)].nome)) if len(fv) else []
    if fora:
        log(f"  Recife: na folha como vereador e fora da legislatura atual: {', '.join(fora)}")
    ganha = pd.DataFrame(ganha_l, columns=["ano", "mes", "codigo", "categoria", "valor"])
    # no cargo: os meses pagos como vereador
    linhas_m = []
    for r in ver.itertuples():
        for de, fim in comum.periodos_de_meses(pagos.get(r.codigo, set()), ultimo_folha or ate):
            linhas_m.append({"codigo": r.codigo, "inicio": de, "fim": fim})
    mandatos_df = pd.DataFrame(linhas_m, columns=["codigo", "inicio", "fim"])

    # gabinetes: "VER. KARI SANTOS" -> nome parlamentar; "VER. ROMERO JATOBA CAVALCANTI NETO" -> nome completo
    def achar_gabinete(lot):
        chave = comum.chave_nome(re.sub(r"^VER\.?\s*", "", lot.strip(), flags=re.I))
        palavras = set(chave.split())
        achados = [r.codigo for r in ver.itertuples()
                   if comum.chave_nome(r.nome) == chave or (r.civil_tse and comum.compativel(chave, r.civil_tse))
                   or (palavras and palavras <= set(comum.chave_nome(f"{r.nome} {r.civil_tse}").split()))]
        return achados[0] if len(set(achados)) == 1 else None
    lot_cod = {lot: achar_gabinete(lot) for lot in set(fg.lotacao) | set(fc.lotacao)}
    sem = sorted(l for l, c in lot_cod.items() if c is None)
    if sem:
        log(f"  Recife: gabinetes sem vereador identificado: {', '.join(sem)}")
    equipe = fg.assign(codigo=fg.lotacao.map(lot_cod))
    equipe = equipe[equipe.codigo.notna()].groupby(["ano", "mes", "codigo"])[["pessoas", "custo"]].sum().reset_index().astype({"codigo": int})
    cargos = fc.assign(codigo=fc.lotacao.map(lot_cod))
    cargos = cargos[cargos.codigo.notna()].groupby(["codigo", "cargo"]).pessoas.sum().reset_index().astype({"codigo": int})

    # verba: nome da lista da verba ("Alcides Teixeira") -> nome parlamentar ("Alcides Teixeira Neto")
    def pelo_nome(nome):
        k = comum.chave_nome(nome)
        exato = [r.codigo for r in ver.itertuples() if comum.chave_nome(r.nome) == k]
        if exato:
            return exato[0]
        p = set(k.split())
        achados = [r.codigo for r in ver.itertuples() if p <= set(comum.chave_nome(f"{r.nome} {r.civil_tse}").split())
                   or set(comum.chave_nome(r.nome).split()) <= p]
        return achados[0] if len(set(achados)) == 1 else None
    despesas = None
    if vb is not None and len(vb):
        vb = vb.assign(codigo=vb.nome.map(pelo_nome), tipo=vb.tipo.map(_tipo), fornecedor="", cnpj_cpf="")
        sem_v = sorted(set(vb[vb.codigo.isna()].nome))
        if sem_v:
            log(f"  Recife: na verba e não na legislatura: {', '.join(sem_v)}")
        despesas = vb[vb.codigo.notna()].astype({"codigo": int})[["ano", "mes", "codigo", "tipo", "fornecedor", "cnpj_cpf", "valor"]]
    ultimo = min(ate, ultimo_folha or ate)
    ultimo_eq = f"{int(fc.mes.iloc[0]):02d}/{int(fc.ano.iloc[0])}" if len(fc) else ""
    notas, verba_fora = list(CFG["notas"]), []
    # ano em que a página da verba deu erro (para todos ou para alguns): a verba desse ano fica de fora para todos,
    # para não comparar quem tem a verba contada com quem não tem
    if (PASTA / "verba_erros.csv").exists():
        err = pd.read_csv(PASTA / "verba_erros.csv").fillna("")
        for ano, g in err.groupby("ano"):
            quem = sorted({ver.set_index("codigo").nome.get(pelo_nome(n), n) for n in g.nome if n})
            verba_fora.append(str(int(ano)))
            if despesas is not None:
                despesas = despesas[despesas.ano != int(ano)]
            quem_txt = (f" para {len(quem)} vereadores ({', '.join(quem)})" if len(quem) <= 12 else f" para {len(quem)} vereadores") if quem else ""
            notas.append(f"No site da Câmara, a página da verba de {int(ano)} dá erro{quem_txt}. Para não comparar vereadores com e sem a verba, "
                         f"a verba de {int(ano)} fica de fora para todos, até a Câmara corrigir.")
    cfg = dict(CFG, ultimo_mes=ultimo, equipe_em=ultimo_eq, notas=notas, verba_fora=verba_fora)
    return comum.montar(cfg, tipos, ver.drop(columns=["civil_tse"]), mandatos_df, ganha=ganha, despesas=despesas, equipe=equipe, cargos=cargos)
