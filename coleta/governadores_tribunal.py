"""Governador em exercício pago por outro órgão: o que ele recebe pela folha do órgão de origem.

No Rio de Janeiro, desde 23/03/2026 o governador em exercício é o presidente do Tribunal de Justiça (Ricardo Couto de
Castro, desembargador), por decisão do STF. Ele não recebe o subsídio de governador pela folha do Estado: continua
recebendo pelo Tribunal de Justiça, onde é desembargador. A folha do TJ-RJ vem do DadosJusBr (https://dadosjusbr.org,
licença CC BY 4.0), que copia todo mês a planilha que o tribunal manda ao Painel de Remuneração dos Magistrados do CNJ:
o mesmo leitor do Judiciário (coleta/judiciario/dadosjusbr.py), com as mesmas partes (subsídio, vantagens pessoais e
eventuais, abono de permanência, indenizações, férias, 13º; diárias à parte; descontos, nunca).

Grava dados/governadores/outro_orgao/<uf>.csv (vai para o Git), uma linha por mês, e anexar() põe e.ot no estado de
site/dados/governadores.json:
    e.ot = {"i": índice em e.oc, "orgao": nome do órgão, "como": o cargo lá, "lotacao": a lotação na folha,
            "de": AAAAMM do primeiro mês no governo, "falta": meses no governo sem a folha no DadosJusBr,
            "u": página da fonte, "credito": o crédito do DadosJusBr,
            "nota": frase pronta, "m": [[aaaamm, recebido, subsídio, vantagens, 13º, férias, indenizações, diárias,
            1 se o mês é só em parte no governo, endereço do pacote do mês], ...]}
Recebido = a soma das partes, sem as diárias (como no Judiciário). Os meses antes do governo não entram.
"""
import csv
import io
import json
import zipfile

from .config import DADOS, RAIZ
from .judiciario import comum as JC
from .judiciario import dadosjusbr as DJ
from .util import log

PASTA = DADOS / "governadores" / "outro_orgao"
SITE = RAIZ / "site" / "dados" / "governadores.json"
# uf -> quem, em que órgão; "ocupante": o nome em "ocupantes" de dados/governadores/governadores.json
CASOS = {
    "RJ": {"ocupante": "Ricardo Couto", "nome_folha": "RICARDO COUTO DE CASTRO", "dadosjusbr": "tjrj",
           "orgao": "Tribunal de Justiça do Estado do Rio de Janeiro", "como": "desembargador",
           "u": "https://dadosjusbr.org"},
}
CREDITO = "Folha do tribunal copiada pelo DadosJusBr (dadosjusbr.org), licença CC BY 4.0"
COLUNAS = ["aaaamm", "nome", "cargo", "lotacao", *JC.PARTES, "total_bruto", "diarias", "parcial", "fonte"]
REFAZER = 2  # os 2 últimos meses publicados são lidos de novo (a folha pode ser corrigida)


def arquivo(uf):
    return PASTA / f"{uf.lower()}.csv"


def _ler(uf):
    arq = arquivo(uf)
    if not arq.exists():
        return {}
    with open(arq, encoding="utf-8", newline="") as f:
        return {int(r["aaaamm"]): r for r in csv.DictReader(f)}


def _mes_da_pessoa(caso, am):
    """As partes do que o órgão pagou à pessoa no mês (pelo nome na folha), ou None se ela não está na folha."""
    url = f"{DJ.S3}/{caso['dadosjusbr']}/datapackage/{caso['dadosjusbr']}-{am // 100}-{am % 100}.zip"
    z = zipfile.ZipFile(io.BytesIO(DJ._get(url).content))
    texto = lambda n: io.StringIO(z.read(n).decode("utf-8"))
    alvo = JC.normalizar_nome(caso["nome_folha"])
    pessoa = next((r for r in csv.DictReader(texto("contracheque.csv"), delimiter=";")
                   if JC.normalizar_nome(r.get("nome")) == alvo), None)
    if not pessoa:
        return None
    partes, diarias = {p: 0.0 for p in JC.PARTES}, 0.0
    for r in csv.DictReader(texto("remuneracao.csv"), delimiter=";"):
        if r["id_contracheque"] != pessoa["id_contracheque"] or not r["tipo"].startswith("R"):
            continue  # só o que é pago; os descontos não são lidos
        parte, v = DJ._parte("TJ", r["categoria"], r["item"]), JC.numero(r["valor"])
        if parte is None or not v:
            continue
        if parte == "diarias":
            diarias += v
        else:
            partes[parte] = round(partes[parte] + v, 2)
    return {"aaaamm": am, "nome": pessoa["nome"], "cargo": pessoa.get("funcao") or "", "lotacao": pessoa.get("local_trabalho") or "",
            **partes, "total_bruto": round(sum(partes.values()), 2), "diarias": round(diarias, 2), "fonte": url}


def _ocupante(curado_uf, caso):
    ocs = sorted(curado_uf["ocupantes"], key=lambda o: (o["de"], {"gov": 0, "exercicio": 0, "vice": 1}[o["cargo"]]))
    i = next(i for i, o in enumerate(ocs) if o["nome"] == caso["ocupante"])
    return i, ocs[i]


def coletar():
    """Lê do DadosJusBr os meses em que a pessoa governou (do mês da posse ao último publicado; os 2 últimos de novo)."""
    curado = {e["uf"]: e for e in json.loads((DADOS / "governadores" / "governadores.json").read_text(encoding="utf-8"))}
    for uf, caso in CASOS.items():
        _, o = _ocupante(curado[uf], caso)
        de = int(o["de"][:4] + o["de"][5:7])
        ate = int(o["ate"][:4] + o["ate"][5:7]) if o.get("ate") else 999912
        coletas = DJ._get(f"{DJ.API}/{caso['dadosjusbr']}").json().get("coletas") or []
        disp = sorted(am for am in (int(c["ano"]) * 100 + int(c["mes"]) for c in coletas) if de <= am <= ate)
        lidos = _ler(uf)
        fazer = [am for am in disp if am not in lidos] + [am for am in disp[-REFAZER:] if am in lidos]
        for am in fazer:
            r = _mes_da_pessoa(caso, am)
            if r is None:
                log(f"  {uf}: {caso['nome_folha']} não está na folha do {caso['dadosjusbr']} de {am}")
                continue
            r["parcial"] = 1 if am == de and not o["de"].endswith("-01") else 0
            lidos[am] = r
        PASTA.mkdir(parents=True, exist_ok=True)
        with open(arquivo(uf), "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, COLUNAS)
            w.writeheader()
            w.writerows(lidos[am] for am in sorted(lidos))
        if lidos:
            log(f"  {uf}: {caso['ocupante']} pela folha do {caso['dadosjusbr']} (DadosJusBr), {len(lidos)} meses "
                f"({min(lidos)} a {max(lidos)}), lidos agora {len(fazer)}")


def anexar(estado_site, curado_uf):
    """Põe e.ot no estado do site, se ele tem um caso e meses lidos."""
    uf = estado_site["uf"]
    caso = CASOS.get(uf)
    lidos = _ler(uf) if caso else {}
    if not lidos:
        return estado_site
    i, o = _ocupante(curado_uf, caso)
    n = lambda v: round(float(v or 0), 2)
    m = []
    for am in sorted(lidos):
        r = lidos[am]
        vantagens = n(r["vantagens_pessoais"]) + n(r["vantagens_eventuais"]) + n(r["abono_permanencia"]) + n(r["outras"])
        m.append([am, n(r["total_bruto"]), n(r["subsidio"]), round(vantagens, 2), n(r["decimo_terceiro"]), n(r["ferias"]),
                  n(r["indenizacoes"]), n(r["diarias"]), int(r["parcial"] or 0), r["fonte"]])
    lot = lidos[max(lidos)]["lotacao"]
    de = int(o["de"][:4] + o["de"][5:7])
    falta = [am for am in JC.meses(de, max(lidos)) if am not in lidos]  # meses no governo que o DadosJusBr não tem
    estado_site["ot"] = {
        "i": i, "orgao": caso["orgao"], "como": caso["como"], "lotacao": lot,
        "de": de, "falta": falta, "u": caso["u"], "credito": CREDITO,
        "nota": (f"Governa em exercício desde {o['de'][8:10]}/{o['de'][5:7]}/{o['de'][:4]} e recebe pelo {caso['orgao']}, onde é "
                 f"{caso['como']}, não o subsídio de governador. Valores brutos da folha do tribunal, antes dos descontos; "
                 "as diárias ficam à parte."),
        "m": m,
    }
    return estado_site


def so_anexar():
    """Põe e.ot no site/dados/governadores.json que já existe, sem refazer o resto (refazer o arquivo fora da rodada
    muda mais do que se quer)."""
    dados = json.loads(SITE.read_text(encoding="utf-8"))
    curado = {e["uf"]: e for e in json.loads((DADOS / "governadores" / "governadores.json").read_text(encoding="utf-8"))}
    for e in dados["e"]:
        anexar(e, curado[e["uf"]])
        if e["uf"] in CASOS and curado[e["uf"]].get("recebe"):
            e["recebe"] = curado[e["uf"]]["recebe"]
            e["notas"] = curado[e["uf"]].get("notas") or []
    SITE.write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log(f"Site: {SITE.relative_to(RAIZ)}: pagamento pelo órgão de origem anexado em {', '.join(e['uf'] for e in dados['e'] if 'ot' in e)}")
