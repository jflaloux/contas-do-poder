"""STM pela consulta oficial (Remuneração de Servidores da Justiça Militar da União), só nos meses que o DadosJusBr não tem.

Fonte: https://www2.stm.jus.br/rem_web/index.php/ctrl_remuneracao (só abre de dentro do Brasil; o robots.txt pede que
robôs não entrem em /rem_web/, o que é uma convenção e não lei: lemos com pausa, ver o README, "Robôs e robots.txt"). O
formulário traz um campo de controle da sessão, que a própria página entrega; a consulta é por mês e ano, na aba
"Ministros Ativos" (de_tipo=MIN, de_situacao=ATIV), 15 linhas por página (POST em /pesquisa/<página>). Cada linha é uma
folha (normal, suplementar...) de um ministro, e o "Detalhamento de Remuneração" da própria página dá os itens por grupo
(Vantagens Pessoais, Subsídio, Indenizações, Vantagens Eventuais). Os descontos e o líquido não são lidos; o "teto
constitucional" (abate-teto, valor negativo) fica de fora, como nos outros órgãos (valores antes do abate-teto).

Por que complemento: o STM vem do DadosJusBr (a planilha que o STM manda ao Painel do CNJ), que não tem jan, mar e abr/2026.
Conferido em 08/10/2026: em ago/2026, os totais dos 15 ministros pela consulta oficial são iguais aos do DadosJusBr. Os meses
lidos aqui ficam em fontes.csv com o endereço da consulta; se o DadosJusBr publicar o mês depois, ele não é lido de novo
(a não ser os 2 últimos meses).

Uso: python3 -m coleta.judiciario stm_oficial 120
"""
import re
import html as html_lib

from ..util import _sessao, dormir, log, verificar_prazo
from ..vereadores.comum import ultimo_mes_fechado
from . import comum, dadosjusbr

SIGLA = "STM"
CONSULTA = "https://www2.stm.jus.br/rem_web/index.php/ctrl_remuneracao"
PESQUISA = f"{CONSULTA}/pesquisa"
CARGO = "Ministro do Superior Tribunal Militar"
PAUSA = 2
NOTA = "consulta oficial do STM (Remuneração de Servidores, aba Ministros Ativos), no mês que o DadosJusBr não tem"
GRUPOS = ("Remuneração Paradigma", "Vantagens Pessoais", "Subsídio, Diferença de Subsídio, Função de Confiança ou Cargo em Comissão",
          "Indenizações", "Vantagens Eventuais", "Gratificações")


def _txt(t):
    return re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<script.*?</script>|<style.*?</style>", "", t, flags=re.S)))).strip()


def _valor(t):
    neg = "-" in t
    v = float(re.sub(r"[^\d,]", "", t).replace(",", ".") or 0)
    return -v if neg else v


def _parte(grupo, item):
    """Em que parte entra um item; None = fica de fora (abate-teto)."""
    i = comum.normalizar_nome(item)
    if grupo.startswith("Subsídio"):
        return "subsidio" if i.startswith("SUBSIDIO") else "outras"
    if grupo == "Vantagens Pessoais":
        return "abono_permanencia" if i.startswith("ABONO DE PERMANENCIA") else "vantagens_pessoais"
    if grupo == "Indenizações":
        return "indenizacoes"
    if grupo == "Vantagens Eventuais":
        if "TETO CONSTITUCIONAL" in i:
            return None
        if "FERIAS" in i:
            return "ferias"
        if "(13" in i or "NATALINA" in i:
            return "decimo_terceiro"
        return "vantagens_eventuais"
    return "outras"


def _folhas(html):
    """[{nome, lotacao, folha, itens: [(grupo, item, valor)], total}] de cada "Detalhamento de Remuneração" da página."""
    saida = []
    marcas = [m.start() for m in re.finditer(r'id="detalhes\d+"', html)] + [len(html)]
    for a, b in zip(marcas, marcas[1:]):
        x = _txt(html[a:b])
        nome = re.search(r"Nome: (.*?) Cargo:", x)
        if not nome:
            continue
        cargo = re.search(r"Cargo: (.*?) Função", x)
        lot = re.search(r"Lotação: (.*?) Folha:", x)
        folha = re.search(r"Folha: (.*?) Cálculo dos Rendimentos", x)
        tot = re.search(r"Total de Rendimentos (-?R\$ ?-?[\d\.,]+)", x)
        rend = x[x.find("Cálculo dos Rendimentos") + len("Cálculo dos Rendimentos"): x.find("Total de Rendimentos")]
        itens = []
        for bloco in re.split(r" ?TOTAL -?R\$ ?-?[\d\.,]+ ?", rend):
            bloco = bloco.strip()
            grupo = next((g for g in GRUPOS if bloco.startswith(g)), None)
            if not grupo:
                continue
            for item, v in re.findall(r"(.+?) (-?R\$ ?-?[\d\.,]+)\s*", bloco[len(grupo):].strip()):
                itens.append((grupo, item.strip(), _valor(v)))
        saida.append({"nome": nome.group(1).strip(), "cargo": cargo.group(1).strip() if cargo else "",
                      "lotacao": lot.group(1).strip() if lot else "", "folha": folha.group(1).strip() if folha else "",
                      "itens": itens, "total": _valor(tot.group(1)) if tot else None})
    return saida


def mes(am):
    """As linhas de um mês (um ministro por linha, somando as folhas do mês), pela consulta oficial."""
    s = _sessao()
    verificar_prazo()
    r = s.get(CONSULTA, timeout=60)
    r.raise_for_status()
    tok = re.search(r'type="hidden" id="(\w+)" name="(\w+)" value="([0-9a-f]+)"', r.text)
    if not tok:
        raise RuntimeError("a página da consulta do STM veio sem o campo de controle")
    dados = {tok.group(2): tok.group(3), "mes": str(am % 100), "ano": str(am // 100), "nome": "", "ctrl_input": "1",
             "de_tipo": "MIN", "de_situacao": "ATIV", "pesquisar": "Consultar"}
    folhas, vistas = [], set()
    for pagina in range(1, 7):  # a primeira página é /pesquisa/0; as seguintes, /pesquisa/2, /pesquisa/3...
        dormir(PAUSA)
        verificar_prazo()
        r = s.post(f"{PESQUISA}/{0 if pagina == 1 else pagina}", data=dados, timeout=120)
        r.raise_for_status()
        novas = [f for f in _folhas(r.content.decode("latin1")) if (f["nome"], f["folha"], f["total"]) not in vistas]
        if not novas:
            break
        for f in novas:
            vistas.add((f["nome"], f["folha"], f["total"]))
        folhas += novas
    por = {}
    for f in folhas:
        if not f["cargo"].upper().startswith("MINISTRO DO SUPERIOR TRIBUNAL MILITAR"):
            continue
        soma = round(sum(v for _, _, v in f["itens"]), 2)
        if f["total"] is not None and abs(soma - f["total"]) > max(5.0, 0.01 * abs(f["total"])):
            raise RuntimeError(f"STM {am}: os itens de {f['nome']} ({f['folha']}) somam {soma}, e o total diz {f['total']}")
        if f["total"] is not None and abs(soma - f["total"]) > 0.05:  # a própria página às vezes não fecha por centavos ou reais
            log(f"  STM {am}: itens de {f['nome']} ({f['folha']}) somam {soma}; o total da página é {f['total']} (vale a soma dos itens)")
        p = por.setdefault(f["nome"], {"lotacao": f["lotacao"], "partes": {}, "itens": []})
        for grupo, item, v in f["itens"]:
            parte = _parte(grupo, item)
            if parte is None or not v:
                continue
            p["partes"][parte] = round(p["partes"].get(parte, 0.0) + v, 2)
            if parte in ("indenizacoes", "vantagens_eventuais", "vantagens_pessoais", "ferias"):
                p["itens"].append((grupo, " ".join(item.split()), v))
    return [comum.linha(SIGLA, am, nome, CARGO, p["lotacao"], {x: p["partes"].get(x, 0.0) for x in comum.PARTES},
                        0.0, p["itens"], CONSULTA, NOTA) for nome, p in sorted(por.items())]


def coletar():
    """Os meses de INICIO até o último mês fechado que nem o DadosJusBr nem a consulta oficial já deram (e, dos lidos aqui,
    os 2 últimos de novo, se a leitura tem mais de 3 dias)."""
    fontes = comum.ler_fontes(SIGLA)
    lidos = {int(x["ano_mes"]): x for x in fontes if int(x.get("pessoas") or 0) > 0}
    try:
        disp = set(dadosjusbr.disponiveis(SIGLA))
    except Exception as e:  # noqa: BLE001 — sem a lista do DadosJusBr, vale o que já foi lido
        log(f"  STM (oficial): a lista do DadosJusBr não abriu ({type(e).__name__}); só os meses que faltam no arquivo")
        disp = set()
    ate = ultimo_mes_fechado()
    nossos = sorted(m for m, x in lidos.items() if "stm.jus.br" in (x.get("url") or ""))
    refazer = set(nossos[-2:])
    fazer = [m for m in comum.meses(comum.INICIO, ate) if m not in disp and (m not in lidos or m in refazer)]
    linhas, lidos_agora = [], []
    try:
        for am in fazer:
            ls = mes(am)
            if not ls:
                continue
            linhas += ls
            lidos_agora.append({"ano_mes": am, "pessoas": len(ls), "url": CONSULTA})
    finally:
        n = comum.gravar(SIGLA, linhas, lidos_agora)
        if lidos_agora:
            log(f"  STM pela consulta oficial: {len(lidos_agora)} meses ({', '.join(str(x['ano_mes']) for x in lidos_agora)}), {n} linhas")
    return n
