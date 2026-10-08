"""Testes do disjuntor por site (util._pedir, SessaoEducada, baixar), do robots.txt (que não impede pedidos, só dá as
pausas) e dos sites que pediram para parar. Usa servidores falsos no
próprio computador (127.0.0.1) e funções inventadas; não abre a internet.

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
            if getattr(self.server, "robots", None):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(self.server.robots.encode())
            else:
                self.send_response(404)
                self.end_headers()
            return
        self.send_response(500 if self.path == "/erro" else 200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *_):
        pass


def _servidor(robots=None):
    s = HTTPServer(("127.0.0.1", 0), _Resposta)
    s.robots = robots
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s, f"http://127.0.0.1:{s.server_address[1]}"


def _limpar():
    util._disjuntor.clear()
    util._robots.clear()
    util._robots_falhou.clear()
    util._ultimo_pedido.clear()


def executar():
    falhas, total = [], 0

    def caso(nome, ok):
        nonlocal total
        total += 1
        if not ok:
            falhas.append(nome)

    def levanta(funcao, tipo):
        """O tipo de erro que a função levanta (None se não levantar)."""
        try:
            funcao()
        except tipo as e:
            return e
        except Exception as e:  # noqa: BLE001
            return None if not isinstance(e, tipo) else e
        return None

    s1, vivo = _servidor()
    s2, vivo_crawl = _servidor(robots="User-agent: *\nCrawl-delay: 1\n")
    s4, vivo_proibe = _servidor(robots="User-agent: *\nDisallow: /\n")
    fechado = "http://127.0.0.1:9"  # porta fechada: a conexão é recusada na hora
    morto = fechado
    s = util._sessao()
    N = util.DISJUNTOR_FALHAS

    # 1. site vivo responde, e erro 500 não conta como site fora do ar
    _limpar()
    caso("responde", s.get(f"{vivo}/ok", timeout=5).text == "ok")
    for _ in range(N + 2):
        s.get(f"{vivo}/erro", timeout=5)
    caso("500 não abre o disjuntor", s.get(f"{vivo}/ok", timeout=5).status_code == 200)

    # 2. site que caiu depois de o robots.txt ter sido lido: as primeiras falhas são tentativas de verdade; depois,
    # falha na hora (HostIndisponivel)
    _limpar()
    s3, caido = _servidor()
    s.get(f"{caido}/ok", timeout=5)  # lê (e guarda) o robots.txt dele
    s3.shutdown()
    s3.server_close()
    morto = caido
    tipos = []
    for _ in range(N + 3):
        try:
            util.baixar(f"{morto}/x", tentativas=1, timeout=3)
        except requests.RequestException as e:
            tipos.append(type(e).__name__)
    caso("só levantou erro de conexão", len(tipos) == N + 3)
    caso("falhas comuns primeiro", "HostIndisponivel" not in tipos[:N - 1])
    caso("depois o disjuntor abre", tipos[-1] == "HostIndisponivel")
    t0 = time.time()
    e = levanta(lambda: util.baixar(f"{morto}/x", tentativas=4, timeout=3), requests.RequestException)
    caso("baixar não repete nem espera com o disjuntor aberto", isinstance(e, util.HostIndisponivel) and time.time() - t0 < 1)
    caso("HostIndisponivel é erro de conexão comum", issubclass(util.HostIndisponivel, requests.exceptions.ConnectionError))
    caso("outro site continua", s.get(f"{vivo}/ok", timeout=5).status_code == 200)

    # 3. passada a pausa, um pedido tenta de novo e fecha de novo se falhar
    util._disjuntor[morto]["aberto_ate"] = time.time() - 1
    e = levanta(lambda: util.baixar(f"{morto}/x", tentativas=1, timeout=3), requests.RequestException)
    caso("depois da pausa tenta de verdade", e is not None and not isinstance(e, util.HostIndisponivel))
    caso("e fecha de novo se falhar", util._disjuntor[morto]["aberto_ate"] > time.time())

    # 4. recuperação: o site que volta a responder zera a contagem
    _limpar()
    origem = "http://recupera.invalido"

    def cai():
        raise requests.exceptions.ConnectionError("fora")
    for _ in range(N - 1):
        levanta(lambda: util._pedir(origem, lambda **k: cai()), requests.RequestException)
    caso("quase abrindo", util._disjuntor[origem]["falhas"] == N - 1)
    util._pedir(origem, lambda **k: "ok")
    caso("resposta zera a contagem", util._disjuntor[origem]["falhas"] == 0)
    for _ in range(N - 1):
        levanta(lambda: util._pedir(origem, lambda **k: cai()), requests.RequestException)
    caso("e precisa de N falhas seguidas outra vez", util._disjuntor[origem]["aberto_ate"] == 0)

    # 5. erro de certificado (SSLError é um ConnectionError) não fecha o site: o servidor respondeu
    _limpar()
    origem = "https://certificado.invalido"

    def ssl():
        raise requests.exceptions.SSLError("certificado")
    for _ in range(N + 3):
        levanta(lambda: util._pedir(origem, lambda **k: ssl()), requests.exceptions.SSLError)
    caso("SSLError não abre o disjuntor", util._disjuntor.get(origem, {}).get("aberto_ate", 0) == 0)

    # 6. falha no destino de um redirecionamento é do destino, não da origem pedida
    _limpar()
    origem, destino = "http://origem.invalido", "http://destino.invalido"

    def redireciona():
        e = requests.exceptions.ConnectionError("destino fora")
        e.request = requests.Request("GET", f"{destino}/x").prepare()
        raise e
    for _ in range(N + 1):
        levanta(lambda: util._pedir(origem, lambda **k: redireciona()), requests.RequestException)
    caso("a falha vai para o destino do redirecionamento", util._disjuntor[destino]["aberto_ate"] > time.time())
    caso("a origem pedida não é suspensa", util._disjuntor.get(origem, {}).get("aberto_ate", 0) == 0)

    # 7. isolamento: o site fechado não suspende o vizinho (outra porta, mesma máquina)
    _limpar()
    morto = caido
    s.get(f"{vivo}/ok", timeout=5)
    for _ in range(N):
        levanta(lambda: util.baixar(f"{morto}/x", tentativas=1, timeout=3), requests.RequestException)
    caso("vizinho continua", s.get(f"{vivo}/ok", timeout=5).status_code == 200)

    # 8. robots.txt que não abre: o site fica fechado por um tempo (sem tentar de novo a cada pedido), nem o endereço com
    # pausa própria abre
    _limpar()
    morto = fechado
    e = levanta(lambda: s.get(f"{morto}/pagina", timeout=3), requests.exceptions.ConnectionError)
    caso("robots inacessível vira erro de conexão", e is not None and not isinstance(e, util.SiteParado))
    caso("e fica guardado por um tempo", morto in util._robots_falhou and morto not in util._robots)
    antes = util._disjuntor.get(morto, {}).get("falhas", 0)
    levanta(lambda: s.get(f"{morto}/outra", timeout=3), requests.exceptions.ConnectionError)
    caso("sem nova consulta ao robots.txt dentro do prazo", util._disjuntor.get(morto, {}).get("falhas", 0) == antes)
    util._robots_falhou[morto]["quando"] -= util.ROBOTS_INACESSIVEL_SEGUNDOS + 1
    levanta(lambda: s.get(f"{morto}/outra", timeout=3), requests.exceptions.ConnectionError)
    caso("passado o prazo, tenta ler o robots.txt de novo", util._disjuntor[morto]["falhas"] > antes)
    util.PAUSAS.append((f"{morto}/", 0))
    try:
        _limpar()
        e = levanta(lambda: s.get(f"{morto}/pagina", timeout=3), requests.exceptions.ConnectionError)
        caso("a pausa própria não abre o site se o robots.txt não abriu", e is not None)
    finally:
        util.PAUSAS.pop()

    # 9. Crawl-delay do robots.txt é respeitado entre os pedidos
    _limpar()
    s.get(f"{vivo_crawl}/a", timeout=5)
    t0 = time.time()
    s.get(f"{vivo_crawl}/b", timeout=5)
    caso("Crawl-delay de 1 s entre pedidos", time.time() - t0 >= 0.9)

    # 9b. robots.txt que proíbe tudo não impede o pedido (regra de 08/10/2026): só pede uma pausa entre os pedidos
    _limpar()
    caso("Disallow: / não bloqueia", s.get(f"{vivo_proibe}/a", timeout=5).text == "ok")
    t0 = time.time()
    s.get(f"{vivo_proibe}/b", timeout=5)
    caso("e o pedido seguinte espera a pausa", time.time() - t0 >= util.PAUSA_SE_O_ROBOTS_PROIBE * 0.9)
    caso("SiteParado não é BloqueadoRobots (que saiu)", not hasattr(util, "BloqueadoRobots"))
    caso("lista de exceções saiu", not hasattr(util, "EXCECOES_ROBOTS"))

    # 9c. site que pediu para parar: nenhum pedido sai, nem ao robots.txt
    _limpar()
    util.SITES_PARADOS.append((f"{vivo}/", "teste: o órgão pediu para parar"))
    try:
        e = levanta(lambda: s.get(f"{vivo}/ok", timeout=5), util.SiteParado)
        caso("site parado levanta SiteParado", isinstance(e, util.SiteParado))
        caso("sem pedido nem ao robots.txt", vivo not in util._robots)
    finally:
        util.SITES_PARADOS.pop()
    caso("tirado da lista, volta a abrir", s.get(f"{vivo}/ok", timeout=5).text == "ok")

    # 10. o prazo para abrir a conexão vale quando a chamada passa só um número, e a função recebe a tupla
    _limpar()
    visto = {}

    def falso(*a, **kw):
        visto.update(kw)
        raise requests.exceptions.ConnectTimeout()
    levanta(lambda: util._pedir("http://exemplo.invalido", falso, timeout=90), requests.exceptions.ConnectTimeout)
    caso("timeout vira (conexão, leitura)", visto.get("timeout") == (util.CONEXAO_TIMEOUT, 90))
    visto.clear()
    levanta(lambda: util._pedir("http://exemplo2.invalido", falso), requests.exceptions.ConnectTimeout)
    caso("sem timeout, ganha um", isinstance(visto.get("timeout"), tuple))

    s1.shutdown()
    s2.shutdown()
    s4.shutdown()
    _limpar()
    print(f"{total - len(falhas)}/{total} casos certos" + (f"; falharam: {falhas}" if falhas else ""))
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(executar())
