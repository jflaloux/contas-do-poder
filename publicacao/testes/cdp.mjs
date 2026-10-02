// Controle mínimo do Chrome pelo protocolo DevTools (CDP), sem nenhuma dependência: usa só o Node (o WebSocket vem
// pronto desde o Node 22) e o Chrome ou o Chromium que já estiver no computador. Quem quiser outro navegador aponta a
// variável CHROME para o executável.
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const CAMINHOS = [
  process.env.CHROME,
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/Applications/Chromium.app/Contents/MacOS/Chromium",
  "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
  "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium", "/usr/bin/chromium-browser",
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
].filter(Boolean);

export const achar = () => CAMINHOS.find((c) => fs.existsSync(c)) || null;
export const espera = (ms) => new Promise((r) => setTimeout(r, ms));

export async function abrirNavegador() {
  const exe = achar();
  if (!exe) throw new Error("Não achei o Chrome: instale o Google Chrome ou aponte a variável CHROME para o executável.");
  const perfil = fs.mkdtempSync(path.join(os.tmpdir(), "contas-testes-chrome-"));
  const proc = spawn(exe, ["--headless=new", "--remote-debugging-port=0", `--user-data-dir=${perfil}`, "--no-first-run",
    "--no-default-browser-check", "--disable-extensions", "--disable-gpu", "about:blank"], { stdio: "ignore" });
  const arq = path.join(perfil, "DevToolsActivePort");
  for (let i = 0; i < 100 && !fs.existsSync(arq); i++) await espera(100);
  if (!fs.existsSync(arq)) { proc.kill(); throw new Error("O Chrome não abriu a porta de controle."); }
  const [porta, caminho] = fs.readFileSync(arq, "utf8").trim().split("\n");
  const ws = new WebSocket(`ws://127.0.0.1:${porta}${caminho}`);
  await new Promise((ok, erro) => { ws.onopen = ok; ws.onerror = () => erro(new Error("Não consegui falar com o Chrome.")); });

  let id = 0;
  const pendentes = new Map(), ouvintes = new Set();
  ws.onmessage = (m) => {
    const msg = JSON.parse(m.data);
    if (msg.id) {
      const p = pendentes.get(msg.id);
      if (!p) return;
      pendentes.delete(msg.id);
      msg.error ? p.erro(new Error(`${p.metodo}: ${msg.error.message}`)) : p.ok(msg.result);
    } else ouvintes.forEach((f) => f(msg));
  };
  const enviar = (metodo, params = {}, sessionId) => new Promise((ok, erro) => {
    const n = ++id;
    pendentes.set(n, { ok, erro, metodo });
    ws.send(JSON.stringify({ id: n, method: metodo, params, ...(sessionId ? { sessionId } : {}) }));
  });

  async function novaPagina() {
    const { targetId } = await enviar("Target.createTarget", { url: "about:blank" });
    const { sessionId } = await enviar("Target.attachToTarget", { targetId, flatten: true });
    const cmd = (metodo, params) => enviar(metodo, params, sessionId);
    const eventos = (f) => { const g = (msg) => { if (msg.sessionId === sessionId) f(msg.method, msg.params); }; ouvintes.add(g); return () => ouvintes.delete(g); };
    const avaliar = async (expressao) => {
      const r = await cmd("Runtime.evaluate", { expression: expressao, awaitPromise: true, returnByValue: true });
      if (r.exceptionDetails) throw new Error((r.exceptionDetails.exception && r.exceptionDetails.exception.description) || r.exceptionDetails.text);
      return r.result.value;
    };
    const fechar = () => enviar("Target.closeTarget", { targetId }).catch(() => {});
    return { cmd, eventos, avaliar, fechar };
  }

  async function fechar() {
    try { ws.close(); } catch { /* já fechou */ }
    proc.kill();
    await espera(300);
    fs.rmSync(perfil, { recursive: true, force: true });
  }
  return { novaPagina, fechar, exe };
}
