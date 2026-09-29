"""Junta Câmara e Senado numa base única.

Saídas em dados/processados/:
- politicos.json    — quem é quem (um registro por político)
- lancamentos.csv.gz — uma linha por político · ano · mês · grupo · categoria · descrição · valor · rateado
- equipe.csv        — quantas pessoas trabalharam no gabinete em cada mês
- resumo.json       — totais prontos para o site (por político, por ano e na legislatura)
- metadados.json    — data da coleta, fontes, regras e pendências conhecidas

Grupos:
- "ganha": o que vai para o bolso do parlamentar (salário, 13º, auxílios, ajuda de custo)
- "custa": despesas dele pagas com dinheiro público (cota: passagens, combustível, alimentação,
           escritório, divulgação...; diárias; outros gastos do mandato)
  -> "ganha" + "custa" = o custo do parlamentar
- "equipe": salários das pessoas que trabalham no gabinete (dinheiro que vai para outras pessoas)

Tudo por mês: alguns valores só são informados por ano (auxílio-moradia da Câmara; passagens, correios e
outros gastos do Senado). Dividimos o total do ano igualmente pelos meses em que o parlamentar recebeu
salário naquele ano. É uma aproximação: essas linhas ficam com rateado=True e a descrição diz o total do ano.
"""
from datetime import datetime

import pandas as pd

from .config import BRUTOS, CACHE, INICIO_LEGISLATURA, LEGISLATURA, PROCESSADOS, REFERENCIA, ULTIMO_MES
from .util import ler_json, log, normalizar_nome, salvar_json

SALARIO_MINIMO = {2023: 1320.00, 2024: 1412.00, 2025: 1518.00, 2026: 1621.00}

CATEGORIAS = {
    # grupo "ganha"
    "salario": ("ganha", "Salário (subsídio bruto)"),
    "decimo_terceiro": ("ganha", "13º salário"),
    "auxilio_moradia": ("ganha", "Auxílio-moradia"),
    "auxilios": ("ganha", "Auxílios (inclui auxílio-moradia)"),
    "ajuda_de_custo": ("ganha", "Ajuda de custo e outras verbas indenizatórias"),
    "outros_rendimentos": ("ganha", "Outros pagamentos"),
    "jetons": ("ganha", "Jetons (conselhos de estatais e outros)"),
    # grupo "custa" (despesas do próprio parlamentar)
    "cota_parlamentar": ("custa", "Cota parlamentar"),
    "diarias": ("custa", "Diárias de viagens oficiais"),
    "outros_gastos_mandato": ("custa", "Outros gastos do mandato"),
    "viagens_oficiais": ("custa", "Viagens oficiais (diárias e passagens)"),
    # grupo "equipe" (vai para outras pessoas)
    "assessores_gabinete": ("equipe", "Equipe do gabinete"),
}


def _na_legislatura(df):
    inicio = INICIO_LEGISLATURA[0] * 100 + INICIO_LEGISLATURA[1]
    return df[(df["ano"] * 100 + df["mes"].fillna(12)) >= inicio]


def _linha(id_, ano, mes, categoria, descricao, valor, fonte):
    grupo, _ = CATEGORIAS[categoria]
    return {"id_politico": id_, "ano": int(ano), "mes": (int(mes) if pd.notna(mes) else None),
            "grupo": grupo, "categoria": categoria, "descricao": descricao,
            "valor": round(float(valor), 2), "fonte": fonte, "rateado": False}


def _ratear_anuais(L):
    """Transforma cada valor anual (mes=None) em valores mensais.

    O total do ano é dividido igualmente pelos meses em que o parlamentar recebeu salário naquele ano;
    se não houver nenhum, pelos meses com algum valor; em último caso, pelos meses do ano dentro da
    legislatura. Os centavos que sobram vão para o último mês, para o total do ano continuar exato.
    """
    inicio = INICIO_LEGISLATURA[0] * 100 + INICIO_LEGISLATURA[1]
    fim = ULTIMO_MES[0] * 100 + ULTIMO_MES[1]
    com_salario, com_algo = {}, {}
    for l in L:
        if l["mes"] is None:
            continue
        chave = (l["id_politico"], l["ano"])
        com_algo.setdefault(chave, set()).add(l["mes"])
        if l["categoria"] == "salario" and l["valor"] > 0:
            com_salario.setdefault(chave, set()).add(l["mes"])
    saida, sem_mes = [], 0
    for l in L:
        if l["mes"] is not None:
            saida.append(l)
            continue
        chave = (l["id_politico"], l["ano"])
        meses = sorted(com_salario.get(chave) or com_algo.get(chave) or ())
        if not meses:
            sem_mes += 1
            meses = [m for m in range(1, 13) if inicio <= l["ano"] * 100 + m <= fim]
        n = len(meses)
        parte = round(l["valor"] / n, 2)
        total = f"{l['valor']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        descricao = f"{l['descricao']} (R$ {total} no ano, dividido por {n} {'mês' if n == 1 else 'meses'})"
        for i, m in enumerate(meses):
            v = parte if i < n - 1 else round(l["valor"] - parte * (n - 1), 2)
            saida.append(dict(l, mes=m, valor=v, rateado=True, descricao=descricao))
    if sem_mes:
        log(f"  {sem_mes} valores anuais sem nenhum mês de referência: divididos pelos meses do ano")
    return saida


# ---------------------------------------------------------------- Câmara
def _camara():
    deps = ler_json(BRUTOS / "camara_deputados.json")
    pid = {d["id"]: f"dep-{d['id']}" for d in deps}
    L = []

    rem = _na_legislatura(pd.read_csv(BRUTOS / "camara_remuneracao.csv"))
    for r in rem.itertuples():
        if r.id_deputado in pid and r.valor:
            L.append(_linha(pid[r.id_deputado], r.ano, r.mes, "salario", "Salário mensal bruto", r.valor,
                            "camara_remuneracao"))

    verba = _na_legislatura(pd.read_csv(BRUTOS / "camara_verba_gabinete.csv"))
    for r in verba.itertuples():
        if r.id_deputado in pid and r.gasto:
            L.append(_linha(pid[r.id_deputado], r.ano, r.mes, "assessores_gabinete",
                            "Verba de gabinete usada (salários de secretários parlamentares)", r.gasto,
                            "camara_verba_gabinete"))

    cota = pd.read_csv(BRUTOS / "camara_cota.csv")
    for r in cota.itertuples():
        if r.id_deputado in pid and r.valor:
            L.append(_linha(pid[r.id_deputado], r.ano, r.mes, "cota_parlamentar", r.tipo.strip().capitalize(), r.valor,
                            "camara_cota"))

    # Lacuna dos dados abertos (desde ago/2025): completa com a diferença para o total mensal do site oficial.
    site = pd.read_csv(BRUTOS / "camara_cota_site.csv")
    soma_csv = cota.groupby(["id_deputado", "ano", "mes"])["valor"].sum()
    for r in site.itertuples():
        if r.id_deputado not in pid or pd.isna(r.total_site):
            continue
        dif = round(r.total_site - soma_csv.get((r.id_deputado, r.ano, r.mes), 0.0), 2)
        if dif >= 1:
            L.append(_linha(pid[r.id_deputado], r.ano, r.mes, "cota_parlamentar",
                            "Passagens aéreas e outros itens sem detalhe nos dados abertos (diferença para o site oficial)",
                            dif, "camara_cota"))

    mor = pd.read_csv(BRUTOS / "camara_moradia.csv")
    for r in mor.itertuples():
        if r.id_deputado in pid and r.auxilio_moradia:
            L.append(_linha(pid[r.id_deputado], r.ano, None, "auxilio_moradia", "Auxílio-moradia",
                            r.auxilio_moradia, "camara_moradia"))

    dias_imovel = {(pid[r.id_deputado], int(r.ano)): int(r.dias_imovel_funcional)
                   for r in mor.itertuples() if r.id_deputado in pid}

    politicos = []
    for d in deps:
        feminino = d.get("sexo") == "F"
        politicos.append({
            "id": pid[d["id"]], "casa": "camara",
            "cargo": "Deputada federal" if feminino else "Deputado federal",
            "nome": d["nome"], "nome_civil": d.get("nome_civil"), "sexo": d.get("sexo"),
            "partido": d.get("partido"), "uf": d.get("uf"), "foto": d.get("foto"),
            "em_exercicio": d["em_exercicio"], "pagina_oficial": d["pagina_oficial"],
            "data_nascimento": d.get("data_nascimento"),
            "naturalidade": ", ".join(x for x in (d.get("municipio_nascimento"), d.get("uf_nascimento")) if x) or None,
            "escolaridade": d.get("escolaridade"),
            "condicao_eleitoral": d.get("condicao_eleitoral"),
            "imovel_funcional_dias": {str(a): v for (p, a), v in dias_imovel.items() if p == pid[d["id"]] and v},
        })
    return politicos, L


# ---------------------------------------------------------------- Senado
def _senado():
    sens = [s for s in ler_json(CACHE / "senado" / "senadores_v2.json") if s["exerceu_na_legislatura"]]
    pid = {s["id"]: f"sen-{s['id']}" for s in sens}
    L = []

    folha = _na_legislatura(pd.read_csv(BRUTOS / "senado_folha.csv"))
    colunas = [
        ("remuneracao_basica", "salario", "Salário mensal bruto"),
        ("vantagens_pessoais", "outros_rendimentos", "Vantagens pessoais"),
        ("funcao_comissionada", "outros_rendimentos", "Função comissionada"),
        ("gratificacao_natalina", "decimo_terceiro", "Gratificação natalina (13º)"),
        ("horas_extras", "outros_rendimentos", "Horas extras"),
        ("outras_eventuais", "outros_rendimentos", "Outras remunerações eventuais"),
        ("abono_permanencia", "outros_rendimentos", "Abono de permanência"),
        ("auxilios", "auxilios", "Auxílios (inclui auxílio-moradia)"),
        ("vantagens_indenizatorias", "ajuda_de_custo", "Vantagens indenizatórias (ex.: ajuda de custo)"),
        ("diarias", "diarias", "Diárias de viagens oficiais"),
    ]
    liquido = []
    for r in folha.itertuples():
        if r.id_senador not in pid:
            continue
        fonte = "senado_folha"
        for col, cat, desc in colunas:
            v = getattr(r, col)
            if v:
                L.append(_linha(pid[r.id_senador], r.ano, r.mes, cat, f"{desc} — folha {r.tipo_folha.lower()}", v, fonte))
        liquido.append({"id_politico": pid[r.id_senador], "ano": r.ano, "mes": r.mes, "liquido": r.remuneracao_liquida})

    ceaps = pd.read_csv(BRUTOS / "senado_ceaps.csv")
    ceaps = ceaps[ceaps["ano"] * 100 + ceaps["mes"] >= INICIO_LEGISLATURA[0] * 100 + INICIO_LEGISLATURA[1]]
    for r in ceaps.itertuples():
        if r.id_senador in pid and r.valor:
            L.append(_linha(pid[r.id_senador], r.ano, r.mes, "cota_parlamentar", r.tipo, r.valor,
                            "senado_transparencia"))

    outros = pd.read_csv(BRUTOS / "senado_outros_gastos.csv")
    # Diárias já vêm da folha de pagamento; não somar duas vezes.
    outros = outros[~outros["tipo"].str.contains("Diárias", case=False)]
    for r in outros.itertuples():
        if r.id_senador in pid and r.valor:
            L.append(_linha(pid[r.id_senador], r.ano, None, "outros_gastos_mandato", r.tipo, r.valor,
                            "senado_transparencia"))

    gab = _na_legislatura(pd.read_csv(BRUTOS / "senado_assessores_gabinete.csv"))
    for r in gab.itertuples():
        if r.id_senador in pid and r.valor:
            L.append(_linha(pid[r.id_senador], r.ano, r.mes, "assessores_gabinete",
                            f"Salários de {r.pessoas} assessores comissionados do gabinete e escritórios (estimativa)",
                            r.valor, "senado_folha"))

    ben = pd.read_csv(BRUTOS / "senado_beneficios.csv")
    imovel = {(pid[r.id_senador], str(r.ano)): r.utilizacao for r in ben.itertuples()
              if r.id_senador in pid and r.beneficio == "Imóvel Funcional"}

    politicos = []
    for s in sens:
        feminino = s.get("sexo") == "F"
        politicos.append({
            "id": pid[s["id"]], "casa": "senado",
            "cargo": "Senadora" if feminino else "Senador",
            "nome": s["nome"], "nome_civil": s.get("nome_civil"), "sexo": s.get("sexo"),
            "partido": s.get("partido"), "uf": s.get("uf"), "foto": s.get("foto"),
            "em_exercicio": s["em_exercicio"], "pagina_oficial": s["pagina_oficial"],
            "data_nascimento": s.get("data_nascimento"),
            "naturalidade": ", ".join(x for x in (s.get("municipio_nascimento"), s.get("uf_nascimento")) if x) or None,
            "participacao": s.get("participacao"),
            "exercicios": s.get("exercicios"),
            "imovel_funcional": {a: u for (p, a), u in imovel.items() if p == pid[s["id"]]},
        })
    return politicos, L, liquido


# ---------------------------------------------------------------- Executivo (presidente, vice, ministros)
# Nome da pasta a partir do órgão (ou da unidade, para os ministérios dentro da Presidência).
# Ordem importa: o primeiro trecho encontrado vence.
PASTAS = [
    ("CASA CIVIL", "-chefe da Casa Civil"), ("RELACOES INSTITUCIONAIS", "-chefe da Secretaria de Relações Institucionais"),
    ("SECRETARIA-GERAL", "-chefe da Secretaria-Geral da Presidência"), ("SECRETARIA GERAL", "-chefe da Secretaria-Geral da Presidência"),
    ("COMUNICACAO SOCIAL", "-chefe da Secretaria de Comunicação Social"), ("SEGURANCA INSTITUCIONAL", "-chefe do Gabinete de Segurança Institucional"),
    ("ADVOCACIA-GERAL", "@Advogado-Geral da União"), ("CONTROLADORIA", " da Controladoria-Geral da União"),
    ("FAZENDA", " da Fazenda"), ("PLANEJAMENTO", " do Planejamento e Orçamento"), ("GESTAO E INOV", " da Gestão e da Inovação em Serviços Públicos"),
    ("SAUDE", " da Saúde"), ("EDUCACAO", " da Educação"), ("DEFESA", " da Defesa"), ("JUSTICA", " da Justiça e Segurança Pública"),
    ("RELACOES EXTERIORES", " das Relações Exteriores"), ("MEIO AMBIENTE", " do Meio Ambiente e Mudança do Clima"),
    ("MINAS E ENERGIA", " de Minas e Energia"), ("TURISMO", " do Turismo"), ("ESPORTE", " do Esporte"),
    ("MULHER", " das Mulheres"), ("IGUALDADE RACIAL", " da Igualdade Racial"), ("POVOS INDIGENAS", " dos Povos Indígenas"),
    ("DIR HUM", " dos Direitos Humanos e da Cidadania"), ("DIREITOS HUMANOS", " dos Direitos Humanos e da Cidadania"),
    ("TRABALHO", " do Trabalho e Emprego"), ("PREVIDENCIA", " da Previdência Social"), ("CIDADES", " das Cidades"),
    ("INTEG", " da Integração e do Desenvolvimento Regional"), ("DESENVOLVIMENTO REGIONAL", " da Integração e do Desenvolvimento Regional"),
    ("TRANSPORTES", " dos Transportes"), ("PORTOS", " de Portos e Aeroportos"),
    ("CIENCIA", " da Ciência, Tecnologia e Inovação"), ("COMUNICACOES", " das Comunicações"), ("DESENV AGR", " do Desenvolvimento Agrário e Agricultura Familiar"),
    ("DESENVOLVIMENTO AGRARIO", " do Desenvolvimento Agrário e Agricultura Familiar"), ("PESCA", " da Pesca e Aquicultura"),
    ("AGRICULTURA", " da Agricultura e Pecuária"), ("IND COMERCIO", " do Desenvolvimento, Indústria, Comércio e Serviços"),
    ("INDUSTRIA", " do Desenvolvimento, Indústria, Comércio e Serviços"), ("EMPREEND", " do Empreendedorismo, da Microempresa e da Empresa de Pequeno Porte"),
    ("ASSIS SOCI", " do Desenvolvimento e Assistência Social, Família e Combate à Fome"),
    ("DESENVOLVIMENTO SOCIAL", " do Desenvolvimento e Assistência Social, Família e Combate à Fome"),
    ("CULTURA", " da Cultura"),  # por último: "AGRICULTURA" e "AQUICULTURA" também contêm "CULTURA"
]
INICIO_GOVERNO = 20230101  # só entra quem foi nomeado neste governo (ex-ministros do governo anterior ficam de fora)


def _nome_cargo(c, feminino):
    """'ministro' + órgão -> 'Ministra da Saúde'; presidente e vice pelo nome do cargo."""
    if c["cargo"] == "presidente":
        return "Presidenta da República" if feminino else "Presidente da República"
    if c["cargo"] == "vice":
        return "Vice-presidente da República"
    alvo = normalizar_nome(f"{c.get('uorg') or ''} {c.get('orgao') or ''}")
    for trecho, sufixo in PASTAS:
        if trecho in alvo:
            if sufixo.startswith("@"):
                return sufixo[1:].replace("Advogado", "Advogada") if feminino else sufixo[1:]
            return ("Ministra" if feminino else "Ministro") + sufixo
    return ("Ministra" if feminino else "Ministro") + " de Estado"


def _executivo(politicos_congresso, lanc_congresso):
    arq = BRUTOS / "executivo_pessoas.json"
    if not arq.exists():
        log("  Executivo: sem dados (rode `coletar.py executivo`)")
        return [], []
    pessoas = ler_json(arq)
    cargos = pd.read_csv(BRUTOS / "executivo_cargos.csv", dtype={"id_portal": str})
    rem = pd.read_csv(BRUTOS / "executivo_remuneracao.csv", dtype={"id_portal": str})
    # 13º: o Portal mostra o adiantamento (em geral em junho) e, no fim do ano, o 13º inteiro (o adiantamento
    # é descontado à parte). Para não contar duas vezes, o último pagamento do ano fica só com a diferença.
    rem = rem.sort_values(["id_portal", "ano", "mes"]).reset_index(drop=True)
    for (_, _), g in rem[rem.natalina > 0].groupby(["id_portal", "ano"]):
        if len(g) < 2:
            continue
        antes, ultimo_i = g.natalina.iloc[:-1].sum(), g.index[-1]
        if rem.at[ultimo_i, "natalina"] >= 1.5 * antes:
            rem.at[ultimo_i, "natalina"] = round(rem.at[ultimo_i, "natalina"] - antes, 2)
    jet = pd.read_csv(BRUTOS / "executivo_jetons.csv", dtype={"id_portal": str})
    via = pd.read_csv(BRUTOS / "executivo_viagens.csv", dtype={"id_portal": str})
    ref = pd.read_csv(REFERENCIA / "executivo.csv").set_index("nome_no_portal").to_dict("index")

    # só cargos deste governo: data de nomeação a partir de 01/01/2023
    nomeacao = pd.to_datetime(cargos["nomeacao"], format="%d/%m/%Y", errors="coerce")
    cargos = cargos[(nomeacao.dt.year * 10000 + nomeacao.dt.month * 100 + nomeacao.dt.day) >= INICIO_GOVERNO]
    cargos = _na_legislatura(cargos)

    # ligação com o Congresso (ministro que é deputado ou senador licenciado), pelo nome civil
    congresso = {}
    for p in politicos_congresso:
        for n in (p.get("nome_civil"), p.get("nome")):
            if n:
                congresso.setdefault(normalizar_nome(n), p)
    ganha_congresso = lanc_congresso[(lanc_congresso.grupo == "ganha") & (~lanc_congresso.rateado)] if len(lanc_congresso) else lanc_congresso

    # Depois de sair: quem deixa o cargo pode receber por até 6 meses ("quarentena") e segue no cadastro
    # como "ministro de Estado". Nesses meses, outra pessoa nomeada depois ocupa a mesma pasta. Só olhamos
    # os últimos meses de cada um (os primeiros meses de 2023 têm nomes de órgãos antigos e confundiriam).
    cargos = cargos.assign(data=nomeacao.reindex(cargos.index),
                           pasta=[_nome_cargo(c, False) for c in cargos.to_dict("records")])
    mi = cargos[cargos.cargo == "ministro"]
    ult_nomeacao = mi.groupby(["pasta", "ano", "mes"])["data"].max()
    fora = set()
    for _, g in mi.groupby("id_portal"):
        minha = g["data"].max()
        meses_p = sorted(set(zip(g.ano, g.mes)))
        for a, m in reversed(meses_p[-7:]):  # até 6 meses de quarentena + o mês da troca
            linhas = g[(g.ano == a) & (g.mes == m)]
            if all(ult_nomeacao.get((r.pasta, a, m), r.data) > minha for r in linhas.itertuples()):
                fora |= set(linhas.index)
            else:
                break
    no_cargo = cargos[~cargos.index.isin(fora)]
    quarentena = cargos[cargos.index.isin(fora)]

    politicos, L, sem_nome = [], [], []
    ultimo = max(p["ultimo_mes_publicado"] for p in pessoas)
    for p in pessoas:
        cc = no_cargo[no_cargo.id_portal == p["id"]]
        if cc.empty:
            continue
        pid = f"exe-{p['id']}"
        chave_meses = {(int(a), int(m)) for a, m in zip(cc.ano, cc.mes)}
        qq = quarentena[quarentena.id_portal == p["id"]]
        meses_q = {(int(a), int(m)) for a, m in zip(qq.ano, qq.mes)} - chave_meses
        rem_q = rem[(rem.id_portal == p["id"]) & [(a, m) in meses_q for a, m in zip(rem.ano, rem.mes)]]
        total_q = float((rem_q.bruta + rem_q.abate_teto + rem_q.natalina + rem_q.abate_natalina + rem_q.ferias + rem_q.eventuais).sum())
        nn = normalizar_nome(p["nome"])
        par = congresso.get(nn)
        r = ref.get(nn)
        if r:
            nome, sexo = r["nome"], r["sexo"]
        elif par:
            nome, sexo = par["nome"], par.get("sexo")
        else:
            partes = p["nome"].title().split()
            nome, sexo = f"{partes[0]} {partes[-1]}", ("F" if partes[0].endswith("a") else "M")
            sem_nome.append(p["nome"])
        feminino = sexo == "F"
        # salário e outros pagamentos (Portal)
        for x in rem[rem.id_portal == p["id"]].itertuples():
            if (x.ano, x.mes) not in chave_meses:
                continue
            for valor, cat, desc in (
                (x.bruta + x.abate_teto, "salario", "Salário (remuneração básica bruta, já com o abate-teto)"),
                (x.natalina + x.abate_natalina, "decimo_terceiro", "13º salário (gratificação natalina)"),
                (x.ferias, "outros_rendimentos", "Adicional de férias"),
                (x.eventuais, "outros_rendimentos", "Outras remunerações eventuais"),
                (x.indenizatorias, "ajuda_de_custo", "Verbas indenizatórias"),
            ):
                if abs(valor) >= 0.01:
                    L.append(_linha(pid, x.ano, x.mes, cat, desc, valor, "portal_remuneracao"))
        for x in jet[jet.id_portal == p["id"]].itertuples():
            if (x.ano, x.mes) in chave_meses and x.valor:
                L.append(_linha(pid, x.ano, x.mes, "jetons", f"Jetons: {x.empresa.title()}", x.valor, "portal_jetons"))
        for x in via[via.id_portal == p["id"]].itertuples():
            valor = x.diarias + x.passagens + x.outros - x.devolucao
            if (x.ano, x.mes) in chave_meses and valor >= 0.01:
                L.append(_linha(pid, x.ano, x.mes, "viagens_oficiais",
                                f"{x.viagens} {'viagem' if x.viagens == 1 else 'viagens'} (diárias R$ {x.diarias:,.2f}, passagens R$ {x.passagens:,.2f})"
                                .replace(",", "X").replace(".", ",").replace("X", "."), valor, "portal_viagens"))
        # quem é deputado ou senador licenciado pode receber o salário pelo Congresso
        if par is not None and len(ganha_congresso):
            g = ganha_congresso[ganha_congresso.id_politico == par["id"]]
            casa = "Câmara" if par["casa"] == "camara" else "Senado"
            for x in g.itertuples():
                if (int(x.ano), int(x.mes)) in chave_meses:
                    L.append(_linha(pid, x.ano, x.mes, x.categoria, f"{x.descricao} — pago pelo {casa}", x.valor, x.fonte))
        ultimo_cargo = cc[(cc.ano * 100 + cc.mes) == (cc.ano * 100 + cc.mes).max()]
        tipos = set(ultimo_cargo.cargo)
        nomes_cargo = [_nome_cargo(c, feminino) for c in ultimo_cargo.to_dict("records")]
        if "vice" in tipos and len(nomes_cargo) > 1:
            outro = next(n for n, c in zip(nomes_cargo, ultimo_cargo.cargo) if c != "vice")
            cargo = f"Vice-presidente e {outro[0].lower()}{outro[1:]}"
        else:
            cargo = nomes_cargo[0]
        politicos.append({
            "id": pid, "casa": "executivo",
            "tipo": "presidente" if "presidente" in tipos else "vice" if "vice" in tipos else "ministro",
            "cargo": cargo, "nome": nome, "nome_civil": p["nome"].title(), "sexo": sexo,
            "partido": par.get("partido") if par else None, "uf": None, "foto": None,
            "em_exercicio": (ultimo // 100, ultimo % 100) in chave_meses,
            "pagina_oficial": f"https://portaldatransparencia.gov.br/servidores/{p['id']}",
            "meses_no_cargo": [a * 100 + m for a, m in sorted(chave_meses)],
            "relacionado": par["id"] if par is not None else None,
            "ultimo_mes_publicado": ultimo,
            "quarentena": {"meses": len(rem_q), "total": round(total_q, 2)} if total_q >= 1 else None,
        })
    if sem_nome:
        log(f"  Executivo: {len(sem_nome)} nomes sem apelido conhecido (complete dados/referencia/executivo.csv): {', '.join(sem_nome)}")
    log(f"  Executivo: {len(politicos)} pessoas, {len(L)} lançamentos")
    return politicos, L


# ---------------------------------------------------------------- tamanho da equipe
def _equipe(ids):
    """Pessoas no gabinete por mês. Câmara: secretários parlamentares (pagos pela verba de gabinete);
    CNE aparece à parte. Senado: comissionados do gabinete e escritórios encontrados na folha (estimativa)."""
    partes = []
    arq = BRUTOS / "camara_pessoal.csv"
    if arq.exists():
        c = pd.read_csv(arq)
        c["id_politico"] = "dep-" + c["id_deputado"].astype(str)
        partes.append(c.rename(columns={"secretarios": "pessoas"})[["id_politico", "ano", "mes", "pessoas", "cne"]])
    s_ = pd.read_csv(BRUTOS / "senado_assessores_gabinete.csv")
    s_["id_politico"] = "sen-" + s_["id_senador"].astype(str)
    s_["cne"] = 0
    partes.append(s_[["id_politico", "ano", "mes", "pessoas", "cne"]])
    eq = _na_legislatura(pd.concat(partes, ignore_index=True))
    eq = eq[eq["id_politico"].isin(ids) & ((eq["pessoas"] > 0) | (eq["cne"] > 0))]
    return eq.sort_values(["id_politico", "ano", "mes"])


# ---------------------------------------------------------------- resumo
def _resumo(politicos, lanc, equipe):
    df = pd.DataFrame(lanc)
    limites = pd.read_csv(REFERENCIA / "limites_cota_camara.csv").set_index("uf")["limite_mensal"].to_dict()
    mensal = (df[df.mes.notna()].groupby(["id_politico", "ano", "mes", "grupo"])["valor"].sum().unstack("grupo").fillna(0.0))
    for g in ("ganha", "custa", "equipe"):
        if g not in mensal:
            mensal[g] = 0.0
    mensal = mensal.reset_index()
    saida = {}

    def bloco(d, mm, eq, ano=None):
        g = round(d.loc[d.grupo == "ganha", "valor"].sum(), 2)
        c = round(d.loc[d.grupo == "custa", "valor"].sum(), 2)
        e = round(d.loc[d.grupo == "equipe", "valor"].sum(), 2)
        mg, mc, me = int((mm.ganha > 0).sum()), int((mm.custa > 0).sum()), int((mm.equipe > 0).sum())
        meses_e = mm[mm.equipe > 0][["ano", "mes"]]
        eq_ok = eq.merge(meses_e, on=["ano", "mes"])          # meses com custo e com contagem de pessoas
        pessoa_meses = int(eq_ok["pessoas"].sum())
        e_ok = float(mm.merge(eq_ok[["ano", "mes"]], on=["ano", "mes"]).equipe.sum())
        out = {
            "meses_com_salario": mg, "meses_com_despesas": mc, "meses_com_equipe": me,
            "ganha": g, "despesas": c, "equipe": e,
            "ganha_por_mes": round(g / mg, 2) if mg else None,
            "despesas_por_mes": round(c / mc, 2) if mc else None,
            "custo_dele_por_mes": round((g / mg if mg else 0) + (c / mc if mc else 0), 2),
            "equipe_por_mes": round(e / me, 2) if me else None,
            "pessoas_na_equipe_media": round(pessoa_meses / len(eq_ok), 1) if len(eq_ok) else None,
            "media_por_pessoa_por_mes": round(e_ok / pessoa_meses, 2) if pessoa_meses else None,
            "categorias": {k: round(v, 2) for k, v in d.groupby("categoria")["valor"].sum().items()},
        }
        if ano:
            out["salarios_minimos_ganha_por_mes"] = round(g / mg / SALARIO_MINIMO[ano], 1) if mg else None
        return out

    for p in politicos:
        pid = p["id"]
        d, mm, eq = df[df.id_politico == pid], mensal[mensal.id_politico == pid], equipe[equipe.id_politico == pid]
        por_ano = {str(int(a)): bloco(d[d.ano == a], mm[mm.ano == a], eq[eq.ano == a], int(a)) for a in sorted(d.ano.unique())}
        cota_por_tipo = (d[d.categoria == "cota_parlamentar"].groupby("descricao")["valor"].sum()
                         .sort_values(ascending=False).round(2))
        leg = bloco(d, mm, eq)
        leg["cota_por_tipo"] = cota_por_tipo.head(12).to_dict()
        item = {"legislatura": leg, "por_ano": por_ano}
        if p["casa"] == "camara" and p.get("uf") in limites:
            item["limite_mensal_cota_atual"] = limites[p["uf"]]
        saida[pid] = item
    return saida


def executar():
    log("Padronizando...")
    pc, lc = _camara()
    ps, ls, liquido = _senado()
    lanc = _ratear_anuais(lc + ls)
    pe, le = _executivo(pc + ps, pd.DataFrame(lanc))
    # ligação de volta: deputado/senador que foi ministro
    for e in pe:
        if e["relacionado"]:
            for p in pc + ps:
                if p["id"] == e["relacionado"]:
                    p["relacionado"] = e["id"]
    politicos = pc + ps + pe
    lanc = lanc + le

    # Deixa de fora quem não tem nenhum pagamento na legislatura (ex.: suplente que só aparece na lista)
    com_dados = {l["id_politico"] for l in lanc}
    politicos = [p for p in politicos if p["id"] in com_dados]
    ids = {p["id"] for p in politicos}
    lanc = [l for l in lanc if l["id_politico"] in ids]

    PROCESSADOS.mkdir(parents=True, exist_ok=True)
    salvar_json(PROCESSADOS / "politicos.json", politicos)
    pd.DataFrame(lanc).sort_values(["id_politico", "ano", "mes", "grupo", "categoria"]) \
        .to_csv(PROCESSADOS / "lancamentos.csv.gz", index=False)
    pd.DataFrame(liquido).to_csv(PROCESSADOS / "senado_salario_liquido.csv", index=False)
    equipe = _equipe(ids)
    equipe.to_csv(PROCESSADOS / "equipe.csv", index=False)
    salvar_json(PROCESSADOS / "resumo.json", _resumo(politicos, lanc, equipe))
    salvar_json(PROCESSADOS / "metadados.json", {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "legislatura": LEGISLATURA,
        "periodo": f"{INICIO_LEGISLATURA[1]:02d}/{INICIO_LEGISLATURA[0]} até hoje",
        "salario_minimo": SALARIO_MINIMO,
        "categorias": {k: {"grupo": g, "nome": n} for k, (g, n) in CATEGORIAS.items()},
        "grupos": {
            "ganha": "Vai para o bolso do parlamentar: salário, 13º, auxílios, ajuda de custo.",
            "custa": "Despesas do próprio parlamentar pagas com dinheiro público: cota, diárias, outros gastos.",
            "equipe": "Salários das pessoas que trabalham no gabinete.",
        },
        "rateio": {
            "regra": "Valores informados só por ano são divididos igualmente pelos meses em que o parlamentar "
                     "recebeu salário naquele ano (coluna rateado=True em lancamentos.csv.gz). É uma aproximação.",
            "auxilio_moradia": "A Câmara informa o auxílio-moradia de cada deputado por ano.",
            "outros_gastos_mandato": "O Senado informa passagens, correios e outros gastos do mandato por ano.",
        },
        "fontes_por_lancamento": {
            "_como_usar": "troque {id} pelo número do político (sem 'dep-'/'sen-'), {ano} e {mes}",
            "camara_remuneracao": "https://www.camara.leg.br/deputados/{id}/remuneracao?ano={ano}",
            "camara_verba_gabinete": "https://www.camara.leg.br/deputados/{id}/verba-gabinete?ano={ano}",
            "camara_cota": "https://www.camara.leg.br/cota-parlamentar/consulta-cota-parlamentar?ideDeputado={id}&dataInicio=01{ano}&dataFim=12{ano}",
            "camara_moradia": "https://www.camara.leg.br/moradia/detalhamento",
            "senado_folha": "https://adm.senado.gov.br/adm-dadosabertos/api/v1/servidores/remuneracoes/{ano}/{mes}/csv",
            "senado_transparencia": "https://www6g.senado.leg.br/transparencia/sen/{id}/?ano={ano}",
            "portal_remuneracao": "https://portaldatransparencia.gov.br/servidores/{id}",
            "portal_jetons": "https://portaldatransparencia.gov.br/download-de-dados/servidores ({ano}{mes}_Honorarios_Jetons)",
            "portal_viagens": "https://portaldatransparencia.gov.br/viagens/consulta",
        },
        "fontes": {
            "camara_api": "https://dadosabertos.camara.leg.br/swagger/api.html",
            "camara_cota": "https://www.camara.leg.br/cotas/",
            "camara_paginas": "https://www.camara.leg.br/deputados/{id}/remuneracao e /verba-gabinete",
            "camara_moradia": "https://www.camara.leg.br/moradia/detalhamento",
            "senado_legis": "https://legis.senado.leg.br/dadosabertos/docs/",
            "senado_adm": "https://adm.senado.gov.br/adm-dadosabertos/swagger-ui/index.html",
            "portal_transparencia": "https://portaldatransparencia.gov.br/download-de-dados",
        },
        "pendencias": [
            "Câmara: 13º salário e ajuda de custo dos deputados ainda não coletados (no Senado já estão).",
            "Câmara: diárias de viagens oficiais (missão oficial) ainda não coletadas.",
            "Senado: 'outros gastos do mandato' (passagens, correios, impulsionamento) só existem na API para quem está em exercício hoje.",
            "Câmara: limites da cota por estado valem para o ano atual; faltam os valores históricos.",
            "Senado: custo dos assessores é ESTIMADO ligando a folha de pagamento à lotação atual (ou última) de cada "
            "servidor comissionado, pelo nome. É mais preciso para os meses recentes; homônimos são descartados.",
            "Cota parlamentar: os 3 últimos meses ainda podem receber notas (prazo de 90 dias).",
            "Auxílio-moradia (Câmara) e outros gastos do mandato (Senado) são informados por ano e divididos "
            "igualmente pelos meses com salário: o valor de cada mês é aproximado. Em 2023, o total do ano pode incluir "
            "janeiro, que ainda era da legislatura anterior.",
            "Câmara: desde ago/2025 as passagens compradas pelo sistema da Câmara (SIGEPA) não aparecem nos arquivos de "
            "dados abertos. Completamos com a diferença para o total mensal do site oficial, sem detalhe por tipo.",
            "Câmara 2023–2024: em ~2% dos meses a soma dos arquivos fica um pouco ACIMA do total do site; mantivemos os arquivos.",
            "Governo federal: o Portal da Transparência publica os salários com cerca de 2 meses de atraso.",
            "Governo federal: o arquivo de salários de dezembro de 2024 do Portal veio incompleto; esse mês fica sem salário.",
            "Governo federal: viagens em aviões da FAB e do avião presidencial não têm custo publicado; entram só "
            "diárias e passagens compradas. Por isso o presidente aparece praticamente só com o salário.",
            "Governo federal: ministro que é deputado ou senador licenciado pode receber o salário pelo Congresso; "
            "nesses meses usamos o salário pago pela Câmara ou pelo Senado.",
            "Governo federal: ex-ministros podem receber até 6 meses de 'quarentena' depois de sair; esses meses ainda "
            "não são separados dos meses no cargo.",
        ],
    })
    n_dep = sum(p["casa"] == "camara" for p in politicos)
    n_sen = sum(p["casa"] == "senado" for p in politicos)
    n_exe = sum(p["casa"] == "executivo" for p in politicos)
    log(f"Base pronta: {n_dep} deputados, {n_sen} senadores, {n_exe} do governo federal, {len(lanc)} lançamentos.")
