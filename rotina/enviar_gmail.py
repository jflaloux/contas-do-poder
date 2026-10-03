#!/usr/bin/env python3
"""Envio de e-mail aprovado no painel dos agentes, pela conta do projeto. Só envia com a aprovação do painel.

O painel (http://localhost:4777) chama este script:
    --listar            JSON com os e-mails prontos para aprovar: os blocos com a caixa ```email do arquivo de rascunhos
                        (o mesmo leitor de rascunhos_gmail.py), cada um com o hash do que vai sair. Os já enviados (pelo
                        log) não aparecem.
    --enviar=<hash>     relê o arquivo, acha o e-mail com esse hash exato (se o texto, o destinatário ou a conversa
                        mudaram, o hash muda e o envio é recusado), confere a data "a-partir-de", o log (nada vai duas
                        vezes) e a conta, e envia. Só envia com CDP_PAINEL_APROVADO=1 no ambiente, que o painel põe depois
                        da confirmação de quem aprova (janela do macOS).
    --enviados          JSON com os últimos 50 envios do log.
A saída é só JSON no stdout: {"ok": true, ...} ou {"ok": false, "erro": "..."} (código de saída 1).

Log: ENVIOS-CONTATO.jsonl na raiz (fora do Git), uma linha por envio (ts, hash, bloco, para, cc, assunto, id, thread).
O script não edita o arquivo de rascunhos. A conta é a do projeto (gmail_comum.conta_ok: a conta gravada; a pessoal é
recusada); sem autorização válida, não abre autorização nenhuma: diz para rodar caixa_gmail.py --nova-autorizacao.
"""
import argparse
import base64
import contextlib
import fcntl
import hashlib
import html
import json
import re
import sys
from datetime import date, datetime
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import formataddr, formatdate
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gmail_comum as gc  # noqa: E402
import rascunhos_gmail as rg  # noqa: E402
from gmail_comum import CONFIG, REMETENTE  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
LOG = RAIZ / "ENVIOS-CONTATO.jsonl"
FUSO = ZoneInfo("America/Sao_Paulo")


# ------------------------------------------------------------------------------------------------------------ log
def ler_log(arq):
    if not Path(arq).exists():
        return []
    saida = []
    for l in Path(arq).read_text(encoding="utf-8").splitlines():
        if l.strip():
            try:
                saida.append(json.loads(l))
            except ValueError:
                pass
    return saida


def _norm(assunto):
    return " ".join((assunto or "").split()).lower()


# ------------------------------------------------------------------------------------------------- os e-mails prontos
def _campos(r, nome, s, conta):
    """O que sai, campo por campo (é o que o hash cobre)."""
    resposta, assunto, para = None, r.assunto, list(r.para)
    if r.responde_a:
        resposta = rg.conversa(s, r.responde_a, {REMETENTE.lower(), conta.lower()})
        assunto, para = resposta["assunto"], para or resposta["para"]
    return {"de": formataddr((nome, REMETENTE)) if nome else REMETENTE, "para": para, "cc": list(r.cc), "assunto": assunto,
            "texto": rg.texto_puro(r.corpo), "html": rg.html_do_corpo(r.corpo), "thread": r.responde_a or None,
            "in_reply_to": (resposta or {}).get("in_reply_to") or None, "references": (resposta or {}).get("references") or None}


def _hash(c):
    return hashlib.sha256(json.dumps(c, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _conteudo(c):
    """O hash só do conteúdo (destinatários, assunto, texto e conversa), sem o remetente e sem os cabeçalhos de resposta:
    depois que uma resposta sai, a conversa ganha uma mensagem nova e o hash completo muda, mas o conteúdo é o mesmo e o
    e-mail não pode aparecer de novo como pronto."""
    return _hash({k: c[k] for k in ("para", "cc", "assunto", "texto", "html", "thread")})


def _liberado(a_partir_de, hoje):
    if not a_partir_de:
        return True
    try:
        return hoje >= date.fromisoformat(a_partir_de)
    except ValueError:
        return False


def prontos(s, arquivo, nome, conta, log, hoje=None):
    """[(item para o painel, campos)] de cada bloco com a caixa ```email, inclusive os já enviados (marcados)."""
    hoje = hoje or datetime.now(FUSO).date()
    enviados = {e.get("hash") for e in log} | {e.get("conteudo") for e in log if e.get("conteudo")}
    saida = []
    for r in rg.ler(arquivo):
        if r.formato != "novo" or r.fora:
            continue
        c = _campos(r, nome, s, conta)
        h = _hash(c)
        avisos = list(r.avisos)
        if not c["para"]:
            avisos.append("sem destinatário")
        for e in log:
            if e.get("hash") != h and set(map(str.lower, e.get("para", []))) == set(map(str.lower, c["para"])) \
                    and _norm(e.get("assunto")) == _norm(c["assunto"]):
                avisos.append(f"já foi enviado antes um e-mail para {', '.join(c['para'])} com o mesmo assunto ({e.get('ts', '')[:16]})")
        if r.a_partir_de and not _liberado(r.a_partir_de, hoje) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", r.a_partir_de):
            avisos.append(f"só pode ir a partir de {r.a_partir_de[8:10]}/{r.a_partir_de[5:7]}/{r.a_partir_de[:4]}")
        links = list(dict.fromkeys(html.unescape(x) for x in re.findall(r'href="(https?://[^"]+)"', c["html"])))
        item = {"hash": h, "bloco": f"{r.numero}. {r.titulo}" if r.numero is not None else r.titulo, "para": c["para"],
                "cc": c["cc"], "assunto": c["assunto"], "texto": c["texto"], "html": c["html"], "links": links,
                "responde_a": c["thread"], "a_partir_de": r.a_partir_de or None,
                "liberado": bool(c["para"]) and _liberado(r.a_partir_de, hoje),
                "ja_enviado": h in enviados or _conteudo(c) in enviados, "avisos": avisos}
        saida.append((item, c))
    return saida


def mime(c):
    """O e-mail como ele sai (multipart/alternative, UTF-8), a partir dos mesmos campos do hash."""
    msg = EmailMessage(policy=SMTP)
    msg["From"] = c["de"]
    msg["To"] = ", ".join(c["para"])
    if c["cc"]:
        msg["Cc"] = ", ".join(c["cc"])
    msg["Subject"] = c["assunto"]
    if c["in_reply_to"]:
        msg["In-Reply-To"] = c["in_reply_to"]
        msg["References"] = c["references"] or c["in_reply_to"]
    msg["Date"] = formatdate(localtime=True)
    msg.set_content(c["texto"], subtype="plain", charset="utf-8", cte="quoted-printable")
    msg.add_alternative(c["html"], subtype="html", charset="utf-8", cte="quoted-printable")
    return msg


# --------------------------------------------------------------------------------------------------------- ações
def _conectar(a, sessao_fn):
    s = (sessao_fn or (lambda c: gc.sessao(c, False, "", script="enviar_gmail.py", interativo=False)))(Path(a.config))
    # script="caixa_gmail.py": a autorização se refaz no terminal, por esse script (este não abre autorização)
    nome, conta = gc.conta_ok(s, REMETENTE, "", a.config, script="caixa_gmail.py", nada="Nada foi enviado.")
    return s, nome, conta


def listar(a, sessao_fn=None):
    s, nome, conta = _conectar(a, sessao_fn)
    itens = [i for i, _ in prontos(s, a.arquivo, nome, conta, ler_log(a.log)) if not i["ja_enviado"]]
    return {"ok": True, "conta": conta, "remetente": formataddr((nome, REMETENTE)) if nome else REMETENTE, "itens": itens}


def enviar(a, sessao_fn=None):
    import os
    if os.environ.get(gc.APROVACAO) != "1":
        raise RuntimeError("envio recusado: falta a aprovação do painel")
    s, nome, conta = _conectar(a, sessao_fn)
    trava = Path(str(a.log) + ".lock")
    trava.parent.mkdir(parents=True, exist_ok=True)
    with open(trava, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)  # dois cliques ao mesmo tempo não enviam duas vezes
        log = ler_log(a.log)
        ja = next((e for e in log if e.get("hash") == a.enviar), None)
        if ja:
            raise RuntimeError(f"este e-mail já foi enviado em {ja.get('ts', '')[:16]} (mensagem {ja.get('id')}); nada foi enviado")
        achado = next(((i, c) for i, c in prontos(s, a.arquivo, nome, conta, log) if i["hash"] == a.enviar), None)
        if achado is None:
            raise RuntimeError("nenhum e-mail pronto com esse hash: o texto, o destinatário ou a conversa mudaram depois da "
                               "aprovação. Liste de novo e aprove de novo; nada foi enviado")
        item, c = achado
        if item["ja_enviado"]:
            raise RuntimeError("um e-mail com o mesmo conteúdo já foi enviado (veja --enviados); nada foi enviado")
        if not c["para"]:
            raise RuntimeError("e-mail sem destinatário; nada foi enviado")
        if not _liberado(item["a_partir_de"], datetime.now(FUSO).date()):
            raise RuntimeError(f"este e-mail só pode ir a partir de {item['a_partir_de']}; nada foi enviado")
        raw = base64.urlsafe_b64encode(mime(c).as_bytes()).decode("ascii")
        res = gc.enviar_aprovado(s, {"raw": raw, **({"threadId": c["thread"]} if c["thread"] else {})})
        linha = {"ts": datetime.now(FUSO).isoformat(timespec="seconds"), "hash": item["hash"], "bloco": item["bloco"],
                 "para": c["para"], "cc": c["cc"], "assunto": c["assunto"], "id": res.get("id"), "thread": res.get("threadId"),
                 "conteudo": _conteudo(c)}
        with open(a.log, "a", encoding="utf-8") as lf:
            lf.write(json.dumps(linha, ensure_ascii=False) + "\n")
    return {"ok": True, "id": res.get("id"), "thread": res.get("threadId"), "para": c["para"], "assunto": c["assunto"]}


def enviados(a, sessao_fn=None):
    return {"ok": True, "envios": list(reversed(ler_log(a.log)))[:50]}


def main(argv=None, sessao_fn=None):
    ap = argparse.ArgumentParser(description="Envio aprovado no painel dos agentes (saída em JSON).")
    acao = ap.add_mutually_exclusive_group(required=True)
    acao.add_argument("--listar", action="store_true")
    acao.add_argument("--enviar", metavar="HASH")
    acao.add_argument("--enviados", action="store_true")
    ap.add_argument("--arquivo", default=str(rg.ARQUIVO))
    ap.add_argument("--log", default=str(LOG))
    ap.add_argument("--config", default=str(CONFIG))

    def erro_de_uso(msg):
        raise SystemExit(f"uso: {msg}")
    ap.error = erro_de_uso
    saida_real = sys.stdout
    try:
        with contextlib.redirect_stdout(sys.stderr):  # o stdout é só do JSON
            a = ap.parse_args(argv)
            r = (listar if a.listar else enviados if a.enviados else enviar)(a, sessao_fn)
        codigo = 0
    except SystemExit as e:
        r, codigo = {"ok": False, "erro": str(e.code) if e.code not in (None, 0) else "parou"}, 1
    except Exception as e:  # noqa: BLE001
        r, codigo = {"ok": False, "erro": f"{e}"}, 1
    saida_real.write(json.dumps(r, ensure_ascii=False) + "\n")
    saida_real.flush()
    return codigo


if __name__ == "__main__":
    sys.exit(main())
