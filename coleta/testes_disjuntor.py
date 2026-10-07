"""Testes do disjuntor por site (util._pedir, SessaoEducada, baixar): site que não responde para de ser tentado. Usa um
servidor falso no próprio computador (127.0.0.1) e endereços inventados; não abre a internet.

    python3 -m coleta.testes_disjuntor
"""
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

from . import util


class _Resposta(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/robots.txt":
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(500 if self.path == "/erro" else 200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *_):
        pass


def executar():
    falhas, total = [], 0

    def caso(nome, ok):
        nonlocal total
        total += 1
        if not ok:
            falhas.append(nome)

    servidor = HTTPServer(("127.0.0.1", 0), _Resposta)
    porta = servidor.server_address[1]
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    vivo = f"http://127.0.0.1:{porta}"
    # porta fechada: a conexão é recusada na hora (o mesmo tratamento de um site que não responde)
    morto = "http://127.0.0.1:9"
    s = util._sessao()

    # 1. site vivo: responde, e erro 500 não conta como site fora do ar
    caso("responde", s.get(f"{vivo}/ok", timeout=5).text == "ok")
    for _ in range(util.DISJUNTOR_FALHAS + 2):
        s.get(f"{vivo}/erro", timeout=5)
    caso("500 não abre o disjuntor", s.get(f"{vivo}/ok", timeout=5).status_code == 200)

    # 2. site morto: as primeiras falhas são tentativas de verdade; depois, falha na hora (HostIndisponivel)
    tipos = []
    for _ in range(util.DISJUNTOR_FALHAS + 3):
        try:
            util.baixar(f"{morto}/x", tentativas=1, timeout=3)
        except requests.RequestException as e:
            tipos.append(type(e).__name__)
    caso("falhas de conexão comuns primeiro", "HostIndisponivel" not in tipos[:util.DISJUNTOR_FALHAS - 1])
    caso("depois o disjuntor abre", tipos[-1] == "HostIndisponivel")
    t0 = time.time()
    try:
        util.baixar(f"{morto}/x", tentativas=4, timeout=3)
    except requests.RequestException as e:
        caso("baixar não repete nem espera com o disjuntor aberto", isinstance(e, util.HostIndisponivel) and time.time() - t0 < 1)
    caso("HostIndisponivel é erro de conexão comum", issubclass(util.HostIndisponivel, requests.exceptions.ConnectionError))

    # 3. outro site não é afetado
    caso("outro site continua", s.get(f"{vivo}/ok", timeout=5).status_code == 200)

    # 4. passada a pausa, um pedido tenta de novo (e o site que voltou reabre o disjuntor)
    util._disjuntor["http://127.0.0.1:9"]["aberto_ate"] = time.time() - 1
    try:
        util.baixar(f"{morto}/x", tentativas=1, timeout=3)
    except requests.RequestException as e:
        caso("depois da pausa tenta de verdade", not isinstance(e, util.HostIndisponivel))
    caso("e fecha de novo se falhar", util._disjuntor["http://127.0.0.1:9"]["aberto_ate"] > time.time())

    # 5. o prazo para abrir a conexão vale quando a chamada passa só um número
    visto = {}

    def falso(*a, **kw):
        visto.update(kw)
        raise requests.exceptions.ConnectTimeout()
    try:
        util._pedir("http://exemplo.invalido", falso, timeout=90)
    except requests.exceptions.ConnectTimeout:
        pass
    caso("timeout vira (conexão, leitura)", visto.get("timeout") == (util.CONEXAO_TIMEOUT, 90))
    visto.clear()
    try:
        util._pedir("http://exemplo2.invalido", falso)
    except requests.exceptions.ConnectTimeout:
        pass
    caso("sem timeout, ganha um", isinstance(visto.get("timeout"), tuple))

    servidor.shutdown()
    print(f"{total - len(falhas)}/{total} casos certos" + (f"; falharam: {falhas}" if falhas else ""))
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(executar())
