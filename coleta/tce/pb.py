"""TCE-PB: a folha de pagamento de todas as prefeituras e câmaras da Paraíba (223 municípios).

Fonte: Portal de Dados Abertos do TCE-PB (https://dados-abertos.tce.pb.gov.br/), "Dados consolidados" > "Servidores":
um ZIP por ano com um CSV de todo o estado (servidores-AAAA.csv; em 2026, ~400 MB, ou ~70 MB zipado), atualizado todo
dia, com o que cada município manda ao Tribunal (sistema Sagres). Cada linha: município, unidade gestora (Prefeitura,
Câmara, fundos, autarquias), CPF mascarado (não é lido), nome, tipo de cargo ("Eletivos", "Cargo Comissionado"...),
cargo, valor do mês, data de admissão, matrícula e mês. O arquivo só é baixado de novo quando muda (ETag).

- O valor é o total das vantagens do mês (o bruto), sem as rubricas: não dá para separar salário, 13º e férias. Vem
  no formato brasileiro, com ponto de milhar e vírgula decimal, sem zeros à direita ("9.300" é R$ 9.300,00).
- Vereadores: unidade gestora da Câmara e cargo de vereador, escrito de muitos jeitos ("VEREADOR", "VEREADOR(A)
  PRESIDENTE", "VEREADORES", "V E R E A D O R"; ver comum.eh_vereador). Os assessores ("ASSESSOR DE GABINETE DE
  VEREADOR") ficam de fora. Algumas câmaras põem o vereador com outro tipo de cargo (Pedro Régis: "Função de
  confiança"): vale o cargo.
- Prefeito e vice: fora da Câmara, cargo de prefeito ou vice ("PREFEITO MUNICIPAL", "VICE-PREFEITO(A)"), e não quem
  trabalha no gabinete deles.
- Secretários: fora da Câmara, só quando o cargo diz "secretário municipal" ou "secretário de" uma pasta (saúde,
  educação, finanças...). Ficam de fora o secretário adjunto, executivo, escolar, de gabinete, particular e o
  "secretário" sem mais nada, que pode ser outro cargo: a lista de cada cidade pode estar incompleta.
- Uma pessoa com duas linhas no mês (dois vínculos) fica com a soma, numa linha só. O cargo fica como a folha escreve,
  sem o código interno do município ("00000001 - VEREADORA" -> "VEREADORA"; algumas câmaras usam "VEREADORA" para
  todos).
- Dezembro de 2025 não está nos arquivos do Tribunal (o arquivo de 2025, gerado em 06/02/2026, vai até novembro): o
  mês aparece sem a folha e entra quando o Tribunal publicar.
"""
import csv
import io
import json
import re
import zipfile

from ..config import HOJE
from ..util import _sessao, log, normalizar_nome, numero_br, verificar_prazo
from . import comum

UF = "PB"
PORTAL = "https://dados-abertos.tce.pb.gov.br/"
URL = "https://download.tce.pb.gov.br/dados-abertos/dados-consolidados/servidores/servidores-{ano}.zip"
# o mesmo arquivo, só de um município (código do TCE: os 3 últimos dígitos da unidade gestora, "101014" = Câmara de
# Areia); é o endereço que vai em fontes.csv e no site, para quem quiser conferir uma cidade
URL_CIDADE = "https://download.tce.pb.gov.br/dados-abertos/dados-por-municipio/{tce}/servidores/servidores-{ano}.zip"
CACHE = comum.CACHE_TCE / "pb"
# nomes que o TCE-PB escreve diferente do IBGE (chave do nome no TCE -> nome no IBGE), preenchido depois de conferir o log
NOMES_DIFERENTES = {}

_PASTAS = re.compile(
    r"(SAUDE|EDUCACAO|FINANCAS|FAZENDA|ADMINISTRACAO|INFRA|AGRICULTURA|AGROPECUARIA|TRANSPORTE|CULTURA|COMUNICACAO|"
    r"ASSISTENCIA|ACAOSOCIAL|DESENVOLVIMENTO|MEIOAMBIENTE|PLANEJAMENTO|ESPORTE|TURISMO|OBRAS|GOVERNO|ARTICULACAO|"
    r"CONTROLEINTERNO|CONTROLADORIA|RECURSOSHIDRICOS|JUVENTUDE|MULHER|HABITACAO|SEGURANCA|TRABALHO|INDUSTRIA|COMERCIO|"
    r"TRIBUTACAO|RECEITA|SERVICOSURBANOS|SERVICOSPUBLICOS|URBANISMO|DEFESACIVIL|POLITICAS|DIREITOSHUMANOS|CIENCIA|"
    r"TECNOLOGIA|PESCA|ABASTECIMENTO|PROTECAO|EMPREENDEDORISMO|IMPRENSA|LAZER|PATRIMONIO|SANEAMENTO|MOBILIDADE|"
    r"TRANSITO|ORDEMPUBLICA|RELACOES|CIDADANIA|EVENTOS|JUSTICA|CASACIVIL|GESTAO|SUSTENTABILIDADE|TRIBUTOS|ECONOMIA|"
    r"RECURSOSHUMANOS|ASSUNTOS|ESTRADAS|LIMPEZA|ENERGIA|AGUA|HABITACIONAL|IGUALDADE|PROMOCAO|INCLUSAO|ESPORTIVA)")
_NAO_SECRETARIO = re.compile(r"ADJUNT|EXECUTIV|ESCOLA|CRECHE|GABINETE|PARTICULAR|PESSOAL|ADMINISTRATIV|CHEFE|JUNIOR|"
                             r"SUBSECRET|AUXILIAR|GERAL|PARLAMENTAR|CONSELHO|JUNTA|COMISSAO|DIRETOR|NUCLEO|SETOR|"
                             r"CLINIC|HOSPITAL|ESCRITORIO|SUBPREFEITURA|DISTRITO|REGIONAL|INTERIN|SUBSTITUT|ACADEMIC|"
                             r"EXPEDIENTE|PROFESSOR|JUDIC")
_TIPOS_FORA = {"Contratação por excepcional interesse público", "Inativos/Pensionistas",
               "Benefício previdenciário temporário"}


def papel_secretario(cargo, tipo):
    """"secretario" quando o cargo é claramente o de secretário municipal ("SECRETÁRIO MUNICIPAL DE SAÚDE",
    "SECRETÁRIA DE EDUCAÇÃO", "SECRETÁRIO(A) MUNICIPAL"), senão None."""
    if tipo in _TIPOS_FORA:
        return None
    c = comum.so_letras(cargo)
    if not c.startswith("SECRETARI") or _NAO_SECRETARIO.search(c):
        return None
    resto = c[len("SECRETARI"):]
    for genero in ("OA", "AO", "O", "A"):
        if not resto.startswith(genero):
            continue
        r = resto[len(genero):]
        if r.startswith(("MUNICIPAL", "MUNICIAL")):
            return "secretario"
        if any(r.startswith(p) and _PASTAS.match(r[len(p):]) for p in ("DOS", "DAS", "DE", "DA", "DO")):
            return "secretario"
    return None


def _baixar(ano):
    """O ZIP do ano em dados/cache/tce/pb/ (só baixa de novo se mudou: pergunta com o ETag da última vez)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    destino, info = CACHE / f"servidores-{ano}.zip", CACHE / f"servidores-{ano}.json"
    antes = json.loads(info.read_text()) if info.exists() and destino.exists() else {}
    cab = {"If-None-Match": antes["etag"]} if antes.get("etag") else {}
    url = URL.format(ano=ano)
    r = _sessao().get(url, headers=cab, stream=True, timeout=180)
    if r.status_code == 304:
        r.close()
        return destino, antes
    if r.status_code in (403, 404):  # o arquivo do ano ainda não existe (o servidor responde 403 ou 404)
        r.close()
        return None, {}
    r.raise_for_status()
    tmp = destino.with_suffix(".part")
    with open(tmp, "wb") as f:
        for pedaco in r.iter_content(1 << 20):
            f.write(pedaco)
            verificar_prazo()
    tmp.replace(destino)
    depois = {"etag": r.headers.get("ETag"), "modificado": r.headers.get("Last-Modified"), "baixado_em": comum.agora()}
    info.write_text(json.dumps(depois))
    log(f"  TCE-PB: {url} ({destino.stat().st_size / 1e6:.0f} MB, atualizado em {depois['modificado']})")
    return destino, depois


def _cidades():
    cid = comum.municipios(UF)
    cid.update({k: cid[comum.chave_cidade(v)] for k, v in NOMES_DIFERENTES.items()})
    return cid


def extrair(caminho):
    """Lê o CSV do ano: (linhas por pessoa e mês, {(cod, orgao, mes): linhas na fonte}, nomes sem código do IBGE)."""
    cidades = _cidades()
    contagem, pessoas, sem_codigo = {}, {}, set()
    with zipfile.ZipFile(caminho) as z:
        nome_csv = next(i.filename for i in z.infolist() if i.filename.endswith(".csv"))
        with z.open(nome_csv) as f:
            leitor = csv.reader(io.TextIOWrapper(f, encoding="utf-8-sig", newline=""), delimiter=";")
            cab = next(leitor)
            i = {c: k for k, c in enumerate(cab)}
            iM, iUG, iN, iT, iC, iV, iAM = (i["nome_municipio"], i["descricao_unidade_gestora"], i["nome_servidor"],
                                            i["tipo_cargo"], i["descricao_cargo"], i["valor_vantagem"], i["ano_mes"])
            ug_camara, codigos = {}, {}
            for n, l in enumerate(leitor):
                if n % 200000 == 0:
                    verificar_prazo()
                try:
                    am = int(l[iAM])
                except (ValueError, IndexError):
                    continue
                if am < comum.INICIO:
                    continue
                cid = cidades.get(comum.chave_cidade(l[iM]))
                if cid is None:
                    if l[iM].strip():
                        sem_codigo.add(l[iM])
                    continue
                ug = l[iUG]
                if ug not in ug_camara:
                    ug_camara[ug] = "CAMARA" in normalizar_nome(ug)
                    cod_ug = l[i["codigo_unidade_gestora"]].strip()
                    if re.fullmatch(r"\d{6}", cod_ug):
                        codigos.setdefault(cid[0], set()).add(cod_ug[-3:])
                orgao = "camara" if ug_camara[ug] else "prefeitura"
                chave = (cid[0], orgao, am)
                contagem[chave] = contagem.get(chave, 0) + 1
                cargo, tipo = l[iC], l[iT]
                c = cargo.upper()
                if not any(p in c for p in ("VER", "PREF", "SECRET", "PRESID", "V E R", "P R E")):
                    continue
                if orgao == "camara":
                    papel = "vereador" if comum.eh_vereador(cargo, eletivo=(tipo == "Eletivos")) else None
                else:
                    papel = comum.papel_prefeitura(cargo) or papel_secretario(cargo, tipo)
                if not papel:
                    continue
                valor = numero_br(l[iV])
                if valor is None:
                    continue
                nome = re.sub(r"\s+", " ", l[iN]).strip().upper()
                k = (cid[0], orgao, am, nome, papel)
                p = pessoas.setdefault(k, {"cod_ibge": cid[0], "municipio": cid[1], "orgao": orgao, "ano_mes": am,
                                           "nome": nome, "cargo": [], "papel": papel, "valor_bruto": 0.0,
                                           "unidade": []})
                p["valor_bruto"] = round(p["valor_bruto"] + valor, 2)
                cargo_limpo = re.sub(r"^\s*\d+\s*-\s*", "", re.sub(r"\s+", " ", cargo)).strip()  # sem o código interno
                if cargo_limpo not in p["cargo"]:
                    p["cargo"].append(cargo_limpo)
                if orgao == "prefeitura" and ug not in p["unidade"]:  # na Câmara, a unidade é sempre a própria Câmara
                    p["unidade"].append(ug)
    linhas = [{**p, "cargo": " / ".join(p["cargo"]), "unidade": " / ".join(p["unidade"])} for p in pessoas.values()]
    tce = {c: next(iter(v)) for c, v in codigos.items() if len(v) == 1}  # código do município no TCE, quando é um só
    return linhas, contagem, sem_codigo, tce


def coletar():
    """Baixa o arquivo de cada ano desde 2025 (só se mudou) e grava os meses que faltam e os 2 últimos. O arquivo de um
    ano que não mudou desde a última leitura completa não é lido de novo (o de 2025 tem ~550 MB descompactado)."""
    cidades = sorted({v[0] for v in _cidades().values()})
    anos = []
    for ano in range(comum.INICIO // 100, HOJE.year + 1):
        caminho, info = _baixar(ano)
        if caminho is None:
            log(f"  TCE-PB: ainda não há o arquivo de {ano}")
            continue
        anos.append((ano, caminho, info))
    # meses de cada ano: do arquivo já lido (se não mudou) ou lendo o arquivo
    lidos = {}
    for ano, caminho, info in anos:
        if info.get("extraido") and info.get("extraido") == info.get("etag") and info.get("meses"):
            continue
        lidos[ano] = extrair(caminho)
    disponiveis = sorted({m for _, _, info in anos if info.get("extraido") == info.get("etag") for m in info.get("meses", [])}
                         | {m for _, cont, _, _ in lidos.values() for (_, o, m) in cont if o == "camara"})
    if not disponiveis:
        log("  TCE-PB: nenhum mês no arquivo")
        return 0
    fazer = comum.blocos_a_fazer(UF, cidades, ["camara", "prefeitura"], disponiveis)
    # um ano que não mudou só é lido de novo se ainda há blocos dele nunca lidos (o arquivo é o mesmo: reler os vazios
    # ou os 2 últimos meses não traria nada novo)
    ja = {(int(c), o, int(m)) for c, o, m in zip(*[comum.ler_fontes(UF)[k] for k in ("cod_ibge", "orgao", "ano_mes")])}
    total = 0
    for ano, caminho, info in anos:
        do_ano = {k for k in fazer if k[2] // 100 == ano}
        if ano not in lidos:
            do_ano -= ja
            if not do_ano:
                log(f"  TCE-PB {ano}: o arquivo não mudou desde a última leitura")
                continue
            lidos[ano] = extrair(caminho)
        linhas, contagem, sem, tce = lidos[ano]
        if sem:
            log(f"  TCE-PB: {len(sem)} municípios sem código do IBGE: {', '.join(sorted(sem))}")
        n_por = {}
        for l in linhas:
            k = (l["cod_ibge"], l["orgao"], l["ano_mes"])
            n_por[k] = n_por.get(k, 0) + 1
        url = lambda c: URL_CIDADE.format(tce=tce[c], ano=ano) if c in tce else URL.format(ano=ano)
        blocos = [{"cod_ibge": c, "orgao": o, "ano_mes": m, "linhas_fonte": contagem.get((c, o, m), 0),
                   "pessoas": n_por.get((c, o, m), 0), "url": url(c), "lido_em": comum.agora()}
                  for (c, o, m) in sorted(do_ano)]
        chaves = {(b["cod_ibge"], b["orgao"], b["ano_mes"]) for b in blocos}
        n, nb = comum.gravar(UF, [l for l in linhas if (l["cod_ibge"], l["orgao"], l["ano_mes"]) in chaves], blocos)
        total += n
        log(f"  TCE-PB {ano}: {n} linhas em {nb} blocos (cidade, órgão e mês) lidos agora")
        # este arquivo (ETag) já foi lido por inteiro: na próxima vez, se não mudar, não é lido de novo
        info = {**info, "extraido": info.get("etag"), "meses": sorted({m for (_, o, m) in contagem if o == "camara"})}
        (CACHE / f"servidores-{ano}.json").write_text(json.dumps(info))
    return total


CFG = {
    "tribunal": "TCE-PB",
    "fonte": "Tribunal de Contas do Estado da Paraíba (TCE-PB), Portal de Dados Abertos: a folha de pagamento que cada "
             "município manda ao Tribunal (Servidores, dados consolidados)",
    "url": PORTAL,
    "nota": "Valor bruto do mês na folha que o município manda ao Tribunal de Contas da Paraíba, antes dos descontos. "
            "A folha do Tribunal não separa salário, 13º, férias e outros pagamentos: um mês com valor maior pode ter "
            "13º, férias ou atrasados.",
    "notas": ["Cada município manda a sua folha ao Tribunal todo mês; o mês que ainda não foi mandado aparece sem valor.",
              "Dezembro de 2025 não está nos arquivos de dados abertos do Tribunal (o arquivo de 2025 vai até "
              "novembro): o mês aparece sem valor em todas as cidades.",
              "Secretários municipais: só quem tem na folha o cargo de secretário municipal ou de secretário de uma "
              "pasta (saúde, educação...). A lista de cada cidade pode estar incompleta.",
              "Partido: o da eleição de 2024 (TSE), quando o nome da folha é exatamente o de um único candidato da "
              "cidade."],
    "secretarios": True,
    "nome_cortado": False,
    "link_da_fonte": True,  # cada cidade leva o endereço do arquivo da cidade no TCE-PB (o do último mês da Câmara)
}


def montar():
    return comum.montar_site(UF, CFG)
