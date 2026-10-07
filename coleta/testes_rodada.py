"""Testes de rotina/etapa-github.sh (tempo de cada etapa, prazo geral, códigos de saída) e do passo de conferência do
workflow, com um `python` e um `timeout` de mentira num PATH temporário. Não coleta nada nem abre a internet.

    python3 -m coleta.testes_rodada
"""
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SCRIPT = RAIZ / "rotina" / "etapa-github.sh"
WORKFLOW = RAIZ / ".github" / "workflows" / "atualizar-dados.yml"


def executar():
    falhas, total = [], 0

    def caso(nome, ok):
        nonlocal total
        total += 1
        if not ok:
            falhas.append(nome)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "bin").mkdir()
        # python de mentira: grava os argumentos e sai com STUB_RC; timeout de mentira: tira as opções e roda o resto
        (tmp / "bin" / "python").write_text('#!/bin/bash\necho "$@" >> "$RUNNER_TEMP/chamadas.txt"\nexit "${STUB_RC:-0}"\n')
        (tmp / "bin" / "timeout").write_text('#!/bin/bash\n[ "$1" = "-k" ] && shift 2\nshift\nexec "$@"\n')
        for f in (tmp / "bin").iterdir():
            f.chmod(0o755)

        def rodar(etapa, minutos, rc=0, essencial="", prazo_em=None):
            for f in ("etapas.txt", "chamadas.txt"):
                (tmp / f).unlink(missing_ok=True)
            env = {**os.environ, "PATH": f"{tmp / 'bin'}:{os.environ['PATH']}", "RUNNER_TEMP": str(tmp), "STUB_RC": str(rc)}
            env.pop("PRAZO_FIM", None)
            if prazo_em is not None:
                env["PRAZO_FIM"] = str(int(time.time()) + prazo_em)
            r = subprocess.run(["bash", str(SCRIPT), etapa, str(minutos), essencial], cwd=RAIZ, env=env, capture_output=True, text=True)
            ler = lambda f: (tmp / f).read_text().strip() if (tmp / f).exists() else ""
            return r.returncode, ler("etapas.txt"), ler("chamadas.txt"), r.stdout

        # o script nunca termina com erro, e anota código e duração
        for rc in (0, 1, 3, 5, 124, 137):
            sai, etapas, _, _ = rodar("tce", 10, rc=rc)
            caso(f"código {rc}: o script sai com 0", sai == 0)
            caso(f"código {rc}: anotado", re.fullmatch(rf"tce {rc} \d+", etapas) is not None)
        # o tempo máximo da etapa vai para --tempo-max (em segundos)
        _, _, chamadas, _ = rodar("senado", 10)
        caso("--tempo-max em segundos", chamadas == "coletar.py senado --tempo-max 600")
        # prazo geral: com PRAZO_FIM daqui a 80 min e reserva de 70, sobram 10 min: a etapa de 40 min recebe 10
        _, _, chamadas, _ = rodar("tce", 40, prazo_em=80 * 60)
        caso("o prazo geral encurta a etapa", re.fullmatch(r"coletar.py tce --tempo-max (5[89]\d|600)", chamadas) is not None)
        # sem sobra (menos de 2 min depois da reserva): pulada, e anotada
        sai, etapas, chamadas, _ = rodar("tce", 40, prazo_em=71 * 60)
        caso("sem sobra, a etapa é pulada", sai == 0 and chamadas == "" and etapas == "tce pulada-por-tempo 0")
        # etapa essencial ignora o prazo geral
        _, etapas, chamadas, _ = rodar("padronizar", 30, essencial="essencial", prazo_em=60)
        caso("essencial roda mesmo sem prazo", chamadas == "coletar.py padronizar --tempo-max 1800" and etapas.startswith("padronizar 0"))

    # o orçamento do workflow cabe no job (conta do pior caso do cabeçalho de etapa-github.sh)
    texto = WORKFLOW.read_text(encoding="utf-8")
    job = int(re.search(r"timeout-minutes: (\d+)", texto).group(1))
    prazo = int(re.search(r"PRAZO_FIM=\$\(\( \$\(date \+%s\) \+ (\d+) \* 60", texto).group(1))
    reserva = int(re.search(r'RESERVA_MIN="\$\{RESERVA_MIN:-(\d+)\}"', SCRIPT.read_text(encoding="utf-8")).group(1))
    essenciais = sum(int(m.group(1)) for m in re.finditer(r"etapa-github.sh \w+ (\d+) essencial", texto))
    caso("as etapas essenciais cabem na reserva (com 20 min para conferir e salvar)", essenciais + 20 <= reserva)
    pior = (prazo - reserva) + 3 + essenciais + 9 + 20
    caso(f"o pior caso ({pior} min) cabe no job ({job} min)", pior < job)

    # o passo de conferência recusa salvar com padronizar/site com erro ou etapa com código 5
    gate = re.search(r"grep -Eq '([^']+)' \"\$RUNNER_TEMP/etapas.txt\"", texto).group(1)
    for linha, deve in (("padronizar 1 12", True), ("site 2 3", True), ("camara 5 0", True), ("senado 5 2", True),
                        ("tce 3 9000", False), ("padronizar 0 100", False), ("camara 0 50", False), ("tce 124 9000", False),
                        ("fotos 15 90", False), ("site 0 10", False), ("bens pulada-por-tempo 0", False)):
        r = subprocess.run(["grep", "-Eq", gate], input=linha + "\n", text=True)
        caso(f"gate com {linha!r}", (r.returncode == 0) == deve)

    print(f"{total - len(falhas)}/{total} casos certos" + (f"; falharam: {falhas}" if falhas else ""))
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(executar())
