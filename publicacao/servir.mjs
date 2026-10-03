// Servidor local para ver o site como o Cloudflare Pages publica (endereços /nome, /cidade/..., /governador/...).
// Uso: node publicacao/gerar.mjs && node publicacao/servir.mjs   e abra http://localhost:8000
// Regras do Pages imitadas: arquivo existente; senão /caminho.html; senão /caminho/index.html; senão os
// redirecionamentos de _redirects; senão o index.html (o app decide o que mostrar).
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import zlib from "node:zlib";
import { fileURLToPath } from "node:url";

const PASTA = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "publicar");
const PORTA = Number(process.env.PORT || process.argv[2] || 8000);
const TIPOS = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".json": "application/json",
  ".svg": "image/svg+xml", ".png": "image/png", ".webp": "image/webp", ".jpg": "image/jpeg", ".xml": "application/xml", ".txt": "text/plain; charset=utf-8", ".woff2": "font/woff2" };
// como o Cloudflare Pages, comprime o que é texto (os dados em JSON ficam ~3 vezes menores): sem isso, o servidor local pesa mais que o de verdade
const COMPRIMIVEL = new Set([".html", ".js", ".css", ".json", ".svg", ".xml", ".txt"]);
const redir = new Map();
try {
  for (const l of fs.readFileSync(path.join(PASTA, "_redirects"), "utf8").split("\n")) { const [de, para] = l.trim().split(/\s+/); if (de && para) redir.set(de, para); }
} catch { /* sem redirecionamentos */ }
const arquivo = (rel) => { const a = path.join(PASTA, rel); return a.startsWith(PASTA) && fs.existsSync(a) && fs.statSync(a).isFile() ? a : null; };

// publicar/ vazia ou arquivo que some no meio da leitura (o gerar.mjs apaga e refaz a pasta): 503 com aviso, sem derrubar o servidor
const indisponivel = (res, texto) => {
  if (!res.headersSent) res.writeHead(503, { "Content-Type": "text/plain; charset=utf-8", "Retry-After": "5" });
  res.end(`${texto}\n`);
};
http.createServer((req, res) => {
  try {
    const url = new URL(req.url, "http://x");
    const rel = decodeURIComponent(url.pathname);
    if (redir.has(rel)) { res.writeHead(301, { Location: redir.get(rel) + url.search }); res.end(); return; }
    const a = arquivo(rel) || arquivo(`${rel.replace(/\/$/, "")}.html`) || arquivo(path.join(rel, "index.html")) || arquivo("index.html");
    if (!a) { indisponivel(res, "publicar/ está vazia ou sendo refeita (node publicacao/gerar.mjs). Espere o build terminar e tente de novo."); return; }
    const ext = path.extname(a), cabecalhos = { "Content-Type": TIPOS[ext] || "application/octet-stream" };
    const leitura = fs.createReadStream(a).on("error", () => indisponivel(res, "O arquivo sumiu durante a leitura (o build está refazendo publicar/?)."));
    if (COMPRIMIVEL.has(ext) && /\bgzip\b/.test(String(req.headers["accept-encoding"] || ""))) {
      res.writeHead(200, { ...cabecalhos, "Content-Encoding": "gzip", Vary: "Accept-Encoding" });
      leitura.pipe(zlib.createGzip({ level: 6 })).pipe(res);
    } else {
      res.writeHead(200, cabecalhos);
      leitura.pipe(res);
    }
  } catch (e) {
    indisponivel(res, `Pedido inválido ou erro no servidor local: ${e.message}`);
  }
}).listen(PORTA, () => console.log(`http://localhost:${PORTA} (pasta publicar/)`));
