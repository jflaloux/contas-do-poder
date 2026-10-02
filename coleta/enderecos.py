"""O endereço de cada página de político: contasdopoder.com/guilherme-boulos em vez de contasdopoder.com/#jun-4154185.

Um endereço, depois de publicado, não deve mudar: ele está em links compartilhados e no Google. Por isso o arquivo
site/dados/enderecos.json (vai para o Git) guarda o endereço de cada id, e cada rodada só dá endereço novo para quem
ainda não tem:

- o endereço é o nome, sem acento: "guilherme-boulos";
- quem tem dois cargos (a página "tudo junto", jun-...) fica com o nome, e cada cargo separado, com o cargo depois:
  "guilherme-boulos/ministro" e "guilherme-boulos/deputado";
- nomes iguais: quem chegou primeiro fica com o nome; o outro ganha o cargo e, se ainda repetir, o estado
  ("joao-carlos-vereador", "joao-carlos-vereador-rn");
- se o endereço de alguém muda (um deputado que vira ministro passa a ser "nome/deputado"), o antigo continua
  funcionando: vai para "antigos", e o site leva para o novo.

Governadores, vices e governadores em exercício têm página por pessoa ("gov-sp-tarcisio-de-freitas"), e
os deputados estaduais ("est-35-300607"), também: entram aqui com os outros.

Cidades (cidade/sao-paulo-sp) e estados (governador/sp) não precisam de registro: o nome da cidade não se repete no
mesmo estado. O site monta esses endereços sozinho, e publicacao/gerar.mjs cria uma página pronta para cada endereço.
"""
import json
import re
import unicodedata

from .config import RAIZ
from .util import log

ARQ = RAIZ / "site" / "dados" / "enderecos.json"
FONTES = [RAIZ / "site" / "dados" / f for f in ("dados.json", "camaras.json", "prefeituras.json", "assembleias.json")]
GOVERNADORES = RAIZ / "site" / "dados" / "governadores.json"
# código IBGE das UFs cujos deputados estaduais foram publicados pelo id antes de ganhar o endereço pelo nome:
# SP, MG, RJ, BA, PE, CE, PB, GO, SC, MS, RO, TO, SE, ES, RS e AP
EST_PELO_ID = {"35", "31", "33", "29", "26", "23", "25", "52", "42", "50", "11", "17", "28", "32", "43", "16"}
# primeiros pedaços de endereço que não podem ser nome de político (pastas e rotas do site)
RESERVADOS = {"cidade", "governador", "dados", "fotos", "entenda", "fontes", "sobre", "busca", "ranking", "correcoes"}
# quem fica com o nome quando dois chegam juntos: "tudo junto", Congresso, governo federal, governadores, prefeituras,
# câmaras, Assembleias (os deputados estaduais, "est-", também têm k "e")
PRIORIDADE = {"j": 0, "d": 1, "s": 2, "e": 3, "g": 4, "p": 5, "v": 6}


def _prioridade(p):
    return 7 if p["id"].startswith("est-") else PRIORIDADE.get(p["k"], 9)


def _governadores():
    """Uma página por pessoa que foi governador, vice ou governador em exercício desde 2023 (o id é da pessoa: quem foi
    vice e depois governador tem uma página só). O cargo do endereço, se o nome repetir, é o último dela."""
    if not GOVERNADORES.exists():
        return {}
    pessoas = {}
    for e in json.loads(GOVERNADORES.read_text(encoding="utf-8"))["e"]:
        for o in sorted(e.get("oc", []), key=lambda o: o["de"]):
            if not o.get("id"):
                continue
            f = o.get("fem")
            g = {"vice": "Vice-governadora" if f else "Vice-governador"}.get(o["c"], "Governadora" if f else "Governador")
            pessoas[o["id"]] = {"id": o["id"], "k": "g", "n": o["n"], "uf": e["uf"], "g": g}
    return pessoas


def slug(texto):
    t = unicodedata.normalize("NFD", str(texto or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def cargo_curto(p):
    """"deputado", "senadora", "ministro", "vice-prefeito", "secretario"... (a primeira palavra do cargo)."""
    if p["id"].startswith("est-"):  # "deputado-estadual", para não confundir com o deputado federal
        return "deputada-estadual" if (p.get("g") or "").startswith("Deputada") else "deputado-estadual"
    c = slug((p.get("g") or "").split()[0] if p.get("g") else "")
    if c.startswith("ministr"):
        return "ministra" if c.startswith("ministra") else "ministro"
    return c or {"d": "deputado", "s": "senador", "e": "governo", "g": "governador", "v": "vereador", "p": "prefeitura"}.get(p["k"], "cargo")


def _ler():
    if ARQ.exists():
        d = json.loads(ARQ.read_text(encoding="utf-8"))
        return d.get("p", {}), d.get("saidos", {}), d.get("antigos", {})
    return {}, {}, {}


def executar():
    pessoas = {}
    for f in FONTES:
        if f.exists():
            for p in json.loads(f.read_text(encoding="utf-8"))["p"]:
                pessoas[p["id"]] = p
    pessoas.update(_governadores())
    if not pessoas:
        return
    atuais, saidos, antigos = _ler()
    registro = {**saidos, **atuais}  # tudo que já teve endereço, inclusive quem saiu dos dados
    # cargos separados de quem tem dois cargos: o endereço vem do "tudo junto"
    do_junto = {c["id"]: j["id"] for j in pessoas.values() if j["k"] == "j" for c in j.get("cg", []) if c["id"] in pessoas}

    novo, ocupado = {}, {}

    def ocupar(pid, cam):
        novo[pid] = cam
        ocupado[cam] = pid

    # 1) quem já tinha endereço de um pedaço só fica com ele. Os cargos separados de quem tem dois cargos ficam de fora:
    # quando um deputado vira ministro, o nome dele passa para a página "tudo junto" (é a mesma pessoa), e o deputado
    # vira "nome/deputado"
    ordem = sorted((pid for pid in pessoas if pid not in do_junto), key=lambda pid: (_prioridade(pessoas[pid]), pid))
    for pid in ordem:
        cam = registro.get(pid)
        if cam and "/" not in cam and cam not in ocupado:
            ocupar(pid, cam)
    # 2) quem ainda não tem endereço: o nome; se repetir, nome-cargo; depois nome-cargo-uf; por fim, o id
    for pid in ordem:
        if pid in novo:
            continue
        p = pessoas[pid]
        base = slug(p["n"]) or pid
        cargo = cargo_curto(p)
        uf = slug(p.get("uf") or "")
        for cam in (base, f"{base}-{cargo}", f"{base}-{cargo}-{uf}" if uf else None, f"{base}-{slug(pid)}"):
            if cam and cam not in ocupado and cam.split("/")[0] not in RESERVADOS:
                ocupar(pid, cam)
                break
    # 3) os cargos separados: "nome-do-tudo-junto/cargo"
    for pid, jid in sorted(do_junto.items()):
        cam = f"{novo[jid]}/{cargo_curto(pessoas[pid])}"
        if cam in ocupado:
            cam = f"{novo[jid]}/{slug(pid)}"
        ocupar(pid, cam)

    # os deputados estaduais dos 16 primeiros estados foram publicados pelo id (/est-35-300607) até 02/10/2026: o id
    # continua valendo e leva ao nome. Os dos outros 11 estados já entraram com o nome, e o id não vira redirecionamento
    # (o _redirects do Cloudflare Pages aceita no máximo 2.000)
    for pid, cam in novo.items():
        if pid.startswith("est-") and cam != pid and pid.split("-")[1] in EST_PELO_ID:
            antigos.setdefault(pid, pid)
    antigos = {c: pid for c, pid in antigos.items() if not (c == pid and pid.startswith("est-") and pid.split("-")[1] not in EST_PELO_ID)}
    # endereços que mudaram continuam valendo (vão para o novo); os que alguém ocupou agora deixam de ser antigos
    for pid, cam in registro.items():
        if pid in novo and novo[pid] != cam and cam not in ocupado:
            antigos[cam] = pid
    antigos = {c: pid for c, pid in antigos.items() if c not in ocupado}
    saidos = {pid: cam for pid, cam in registro.items() if pid not in pessoas}
    ARQ.write_text(json.dumps({"p": dict(sorted(novo.items())), "antigos": dict(sorted(antigos.items())),
                               "saidos": dict(sorted(saidos.items()))}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    mudaram = sum(1 for pid, cam in registro.items() if pid in novo and novo[pid] != cam)
    log(f"Endereços: {len(novo)} páginas de políticos ({len(novo) - len([p for p in novo if p in registro])} novas, "
        f"{mudaram} mudaram, {len(antigos)} endereços antigos redirecionados)")
