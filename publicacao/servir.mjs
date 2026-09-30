// Servidor local para ver o site como o Cloudflare Pages publica (endereços /nome, /cidade/..., /governador/...).
// Uso: node publicacao/gerar.mjs && node publicacao/servir.mjs   e abra http://localhost:8000
// Regras do Pages imitadas: arquivo existente; senão /caminho.html; senão /caminho/index.html; senão os
// redirecionamentos de _redirects; senão o index.html (o app decide o que mostrar).
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const PASTA = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "publicar");
const PORTA = Number(process.env.PORT || process.argv[2] || 8000);
const TIPOS = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".json": "application/json",
  ".svg": "image/svg+xml", ".png": "image/png", ".webp": "image/webp", ".jpg": "image/jpeg", ".xml": "application/xml", ".txt": "text/plain; charset=utf-8" };
const redir = new Map();
try {
  for (const l of fs.readFileSync(path.join(PASTA, "_redirects"), "utf8").split("\n")) { const [de, para] = l.trim().split(/\s+/); if (de && para) redir.set(de, para); }
} catch { /* sem redirecionamentos */ }
const arquivo = (rel) => { const a = path.join(PASTA, rel); return a.startsWith(PASTA) && fs.existsSync(a) && fs.statSync(a).isFile() ? a : null; };

http.createServer((req, res) => {
  const url = new URL(req.url, "http://x");
  const rel = decodeURIComponent(url.pathname);
  if (redir.has(rel)) { res.writeHead(301, { Location: redir.get(rel) + url.search }); res.end(); return; }
  const a = arquivo(rel) || arquivo(`${rel.replace(/\/$/, "")}.html`) || arquivo(path.join(rel, "index.html")) || arquivo("index.html");
  res.writeHead(200, { "Content-Type": TIPOS[path.extname(a)] || "application/octet-stream" });
  fs.createReadStream(a).pipe(res);
}).listen(PORTA, () => console.log(`http://localhost:${PORTA} (pasta publicar/)`));
