#!/usr/bin/env node
// Testes do site: abre cada tipo de página no Chrome (celular e computador, tema claro e escuro) e confere
//   1. funcional: sem erro no console, sem exceção, sem arquivo que não carrega (404), título, um só h1, página
//      terminada (sem "Carregando…"), sem rolagem horizontal, sem cookies próprios (a /sobre diz que não há) e o que cada
//      página tem de mostrar;
//   2. CLS (quanto a página pula enquanto carrega): até 0,1 ("bom", pelo Google);
//   3. axe-core (acessibilidade, contraste incluído): nenhuma violação. O axe não vem com o repositório: veja --baixar-axe.
//   4. Google Analytics só em produção: o gtag carrega em contasdopoder.com e www.contasdopoder.com e em mais nenhum endereço.
// O LCP e o tempo de cada página saem no relatório, sem valer como falha.
//
// Uso (da raiz do repositório; antes, node publicacao/gerar.mjs):
//   node publicacao/testes/rodar.mjs                   roda tudo, com o servidor local (publicacao/servir.mjs) numa porta própria
//   node publicacao/testes/rodar.mjs --completo        os 4 perfis (celular e computador, claro e escuro) em vez de 2
//   node publicacao/testes/rodar.mjs --paginas=atualizacao,indice     só estas (nomes da lista abaixo)
//   node publicacao/testes/rodar.mjs --analytics       com --paginas, roda também a conferência do Google Analytics (sem --paginas ela já roda; --sem-analytics a corta)
//   node publicacao/testes/rodar.mjs --url=http://localhost:8000      usa um servidor que já está rodando (a conferência do Analytics só roda em localhost)
//   node publicacao/testes/rodar.mjs --capturas=/tmp/capturas         guarda uma imagem de cada página
//   node publicacao/testes/rodar.mjs --baixar-axe      baixa o axe-core (uma vez) para o cache e roda
// Precisa só do Node (22 ou mais novo) e do Chrome. Nenhum pacote do npm; nada disso entra no build do Cloudflare Pages.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import crypto from "node:crypto";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { abrirNavegador, espera } from "./cdp.mjs";

const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const SITE = path.join(RAIZ, "site"), PUBLICAR = path.join(RAIZ, "publicar");
const arg = (nome) => { const a = process.argv.find((x) => x === `--${nome}` || x.startsWith(`--${nome}=`)); return a === undefined ? null : a.includes("=") ? a.split("=").slice(1).join("=") : true; };

// ------------------------------------------------------------------ axe-core
const AXE_VERSAO = "4.10.2";
const AXE_URL = `https://cdnjs.cloudflare.com/ajax/libs/axe-core/${AXE_VERSAO}/axe.min.js`;
const AXE_SHA256 = process.env.AXE_SHA256 || "b511cd9dec01c76f4b2ad1723b66b6db37d4c2eb4ed199076e1829d9ee7b75e3"; // do axe.min.js 4.10.2 do cdnjs, baixado em 02/10/2026; a baixa só grava o arquivo se bater
const AXE_ARQ = process.env.AXE_JS || path.join(os.homedir(), ".cache", "contas-do-poder", `axe-core-${AXE_VERSAO}.min.js`);
async function baixarAxe() {
  console.log(`Baixando o axe-core ${AXE_VERSAO} de ${AXE_URL} para ${AXE_ARQ}`);
  const r = await fetch(AXE_URL);
  if (!r.ok) throw new Error(`o servidor respondeu ${r.status}`);
  const corpo = Buffer.from(await r.arrayBuffer());
  const hash = crypto.createHash("sha256").update(corpo).digest("hex");
  console.log(`  ${corpo.length} bytes, SHA-256 ${hash}`);
  if (AXE_SHA256 && hash !== AXE_SHA256) throw new Error("a impressão digital não bate com AXE_SHA256: arquivo não gravado");
  fs.mkdirSync(path.dirname(AXE_ARQ), { recursive: true });
  fs.writeFileSync(AXE_ARQ, corpo);
}

// ------------------------------------------------------------------ as páginas
const lerDados = (arq) => JSON.parse(fs.readFileSync(path.join(SITE, "dados", arq), "utf8"));
const ENDERECOS = lerDados("enderecos.json").p;
const primeiro = (prefixo) => { const id = Object.keys(ENDERECOS).filter((k) => k.startsWith(prefixo)).sort()[0]; return id ? `/${ENDERECOS[id]}` : null; };
// o que cada página tem de ter (seletor e quantidade mínima); sem "ter", só valem as conferências comuns
const PAGINAS = [
  { nome: "inicio", url: "/", ter: [["#chips-info", 1]] },
  { nome: "deputado-federal", url: primeiro("dep-") },
  { nome: "senador", url: primeiro("sen-") },
  { nome: "ministro", url: primeiro("exe-") },
  { nome: "ministro-deputado", url: primeiro("jun-") },
  { nome: "vereador-capital", url: primeiro("ver-") },
  { nome: "prefeitura", url: primeiro("pre-") },
  { nome: "deputado-estadual", url: primeiro("est-") },
  { nome: "governador", url: primeiro("gov-") },
  { nome: "judiciario-pessoa", url: primeiro("jud-") },
  { nome: "cidade-capital", url: "/cidade/sao-paulo-sp" },
  { nome: "cidade-interior", url: "/cidade/abaiara-ce" },
  { nome: "cidade-pequena", url: "/cidade/acrelandia-ac" },
  { nome: "governador-com-viagens", url: ENDERECOS["gov-mg-mateus-simoes"] ? `/${ENDERECOS["gov-mg-mateus-simoes"]}` : null, ter: [["#viagens h2", 1], ["#viagens .estatistica", 2], ["#viagens details table", 1]] },
  { nome: "governador-sem-viagens", url: ENDERECOS["gov-sp-tarcisio-de-freitas"] ? `/${ENDERECOS["gov-sp-tarcisio-de-freitas"]}` : null, ter: [["#viagens h2", 1]] },
  { nome: "estado", url: "/governador/sp", ter: [["#governador", 1]] },
  { nome: "estado-assembleia", url: "/governador/go", ter: [["#governador", 1], ["#assembleia", 1]] },
  { nome: "judiciario", url: "/judiciario", ter: [["#judiciario", 1]] },
  { nome: "indice", url: "/indice", ter: [["#indice", 1]] },
  { nome: "dados-abertos", url: "/dados-abertos", ter: [[".copias li", 5], ["#dados-abertos tbody tr", 10]] },
  { nome: "correcoes", url: "/correcoes", ter: [["ol.correcoes > li", 1]] },
  { nome: "sobre", url: "/sobre", ter: [["#sobre h2", 5], ["#sobre a[href^='mailto:']", 1]] },
  { nome: "atualizacao", url: "/atualizacao", ter: [["#atualizacao tbody tr", 50], ["#atualizacao .estatistica", 2]] },
  { nome: "endereco-inexistente", url: "/pagina-que-nao-existe" },
].filter((p) => p.url);

const TODOS_PERFIS = [
  { nome: "celular-claro", largura: 390, altura: 844, mobile: true, escala: 2, tema: "light" },
  { nome: "computador-escuro", largura: 1280, altura: 800, mobile: false, escala: 1, tema: "dark" },
  { nome: "celular-escuro", largura: 390, altura: 844, mobile: true, escala: 2, tema: "dark" },
  { nome: "computador-claro", largura: 1280, altura: 800, mobile: false, escala: 1, tema: "light" },
];
const PERFIS = arg("completo") ? TODOS_PERFIS : TODOS_PERFIS.slice(0, 2);
const LIMITE_CLS = 0.1;

// o que roda antes de qualquer script da página: mede o CLS e o LCP
const INICIO = `(() => {
  window.__m = { cls: 0, lcp: 0 };
  try { new PerformanceObserver((l) => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__m.cls += e.value; }).observe({ type: "layout-shift", buffered: true }); } catch (e) {}
  try { new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__m.lcp = e.startTime; }).observe({ type: "largest-contentful-paint", buffered: true }); } catch (e) {}
})();`;

// ------------------------------------------------------------------ uma página, num perfil
async function testar(nav, base, pg, perfil, axe, capturas) {
  const falhas = [], avisos = [];
  const t0 = Date.now();
  const pagina = await nav.novaPagina();
  const { cmd, eventos, avaliar } = pagina;
  const local = new URL(base).host;
  let abertas = 0, ultimaAtividade = Date.now();
  const externos = new Set(), meus = new Set();
  const parar = eventos((metodo, p) => {
    if (metodo === "Runtime.exceptionThrown") {
      const d = p.exceptionDetails; falhas.push(`exceção: ${(d.exception && d.exception.description) || d.text}`.split("\n")[0].slice(0, 200));
    } else if (metodo === "Runtime.consoleAPICalled" && (p.type === "error" || p.type === "assert")) {
      const t = p.args.map((a) => a.value ?? a.description ?? "").join(" ");
      if (!/ERR_BLOCKED_BY_CLIENT/.test(t)) falhas.push(`console.error: ${t.slice(0, 200)}`);
    } else if (metodo === "Log.entryAdded" && p.entry.level === "error") {
      let host = ""; try { host = new URL(p.entry.url).host; } catch { /* sem endereço */ }
      if (host && host !== local) return; // arquivo de fora, que o teste bloqueia
      if (!/ERR_BLOCKED_BY_CLIENT/.test(p.entry.text)) falhas.push(`registro: ${p.entry.text} ${p.entry.url || ""}`.slice(0, 200));
    } else if (metodo === "Network.requestWillBeSent") {
      // só os pedidos ao próprio site contam para "a rede ficou quieta" (os de fora, como os do Google Analytics, são bloqueados)
      let h = ""; try { h = new URL(p.request.url).host; } catch { /* sem endereço */ }
      if (h === local) { meus.add(p.requestId); abertas++; ultimaAtividade = Date.now(); }
    } else if (metodo === "Network.loadingFinished" || metodo === "Network.loadingFailed") {
      if (meus.delete(p.requestId)) { abertas = Math.max(0, abertas - 1); ultimaAtividade = Date.now(); }
    } else if (metodo === "Network.responseReceived") {
      const r = p.response, h = new URL(r.url).host;
      const caminho = new URL(r.url).pathname;
      if (h === local && r.status >= 400) falhas.push(`arquivo não carregou (${r.status}): ${caminho}`);
      // o servidor local (como o Cloudflare Pages) devolve a página inicial para o que não existe: um .json que veio como HTML é arquivo que falta
      else if (h === local && /\.(json|js|css|webp|png|svg)$/.test(caminho) && /text\/html/.test(r.mimeType || "")) falhas.push(`arquivo que não existe (veio uma página HTML): ${caminho}`);
    } else if (metodo === "Fetch.requestPaused") {
      const h = new URL(p.request.url).host;
      if (h === local || /^(data|blob):/.test(p.request.url)) cmd("Fetch.continueRequest", { requestId: p.requestId }).catch(() => {});
      else { externos.add(h); cmd("Fetch.failRequest", { requestId: p.requestId, errorReason: "BlockedByClient" }).catch(() => {}); }
    }
  });
  try {
    await Promise.all([cmd("Page.enable"), cmd("Runtime.enable"), cmd("Log.enable"), cmd("Network.enable")]);
    // nada de fora: o teste não pode contar visita no Google Analytics nem depender de internet
    await cmd("Fetch.enable", { patterns: [{ urlPattern: "*" }] });
    await cmd("Emulation.setDeviceMetricsOverride", { width: perfil.largura, height: perfil.altura, deviceScaleFactor: perfil.escala, mobile: perfil.mobile });
    await cmd("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: perfil.tema }] });
    await cmd("Page.addScriptToEvaluateOnNewDocument", { source: INICIO });
    const carregou = new Promise((ok) => { const f = eventos((m) => { if (m === "Page.loadEventFired") { f(); ok(); } }); });
    await cmd("Page.navigate", { url: base + pg.url });
    let relogio;
    await Promise.race([carregou, new Promise((_, erro) => { relogio = setTimeout(() => erro(new Error("a página não terminou de carregar em 30 s")), 30000); })]).finally(() => clearTimeout(relogio));

    // espera a página terminar: a rede quieta por meio segundo e o "Carregando…" fora
    const limite = Date.now() + 25000;
    for (;;) {
      const pronta = abertas === 0 && Date.now() - ultimaAtividade > 500
        && await avaliar(`!document.querySelector(".carregando") && document.querySelector("#app") && document.querySelector("#app").children.length > 0`);
      if (process.env.DEPURAR) console.log(`   [${((Date.now() - t0) / 1000).toFixed(1)} s] abertas=${abertas} quieta há ${Date.now() - ultimaAtividade} ms`);
      if (pronta) break;
      if (Date.now() > limite) { falhas.push(`a página não terminou de carregar em 25 s (${abertas} pedidos abertos)`); break; }
      await espera(150);
    }
    // desce até o fim e volta: o que carrega com a rolagem também conta no CLS
    await avaliar(`window.scrollTo(0, document.documentElement.scrollHeight)`); await espera(600);
    await avaliar(`window.scrollTo(0, 0)`); await espera(400);

    const m = await avaliar(`(() => {
      const visivel = (e) => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
      return { cls: window.__m.cls, lcp: window.__m.lcp, titulo: document.title, h1: [...document.querySelectorAll("h1")].filter(visivel).length,
        cookies: document.cookie, letras: [...document.fonts].filter((f) => f.status === "loaded").length, sobra: document.documentElement.scrollWidth - document.documentElement.clientWidth, carregando: !!document.querySelector(".carregando"),
        contagens: ${JSON.stringify((pg.ter || []).map(([s]) => s))}.map((s) => document.querySelectorAll(s).length) };
    })()`);
    if (!/Contas do Poder/.test(m.titulo)) falhas.push(`título sem "Contas do Poder": "${m.titulo}"`);
    if (m.h1 !== 1) falhas.push(`${m.h1} títulos h1 visíveis (deve ser 1)`);
    if (m.carregando) falhas.push('o "Carregando…" continua na tela');
    if (m.cookies) falhas.push(`o site criou cookies (a página /sobre diz que não usa cookies próprios): ${m.cookies.slice(0, 80)}`);
    if (m.sobra > 1) falhas.push(`rolagem horizontal: a página é ${m.sobra} px mais larga que a tela`);
    (pg.ter || []).forEach(([sel, minimo], i) => { if (m.contagens[i] < minimo) falhas.push(`esperava ${minimo} de "${sel}" e achei ${m.contagens[i]}`); });
    if (pg.url.startsWith("/cidade/")) {
      // o parágrafo em destaque vai pronto no HTML (gerar.mjs, destaqueCidade) para a primeira pintura: tem de ser igual ao do app.js
      try {
        const html = await (await fetch(base + pg.url)).text();
        const pronto = ((/<p class="destaque">([^<]*)<\/p>/.exec(html) || [])[1] || "").replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"');
        const vivo = await avaliar(`(document.querySelector("#cidade p.destaque") || {}).textContent || ""`);
        if (pronto !== vivo) falhas.push(`o destaque pronto no HTML difere do do app.js: "${pronto.slice(0, 90)}" x "${vivo.slice(0, 90)}"`);
      } catch (e) { falhas.push(`não consegui conferir o destaque da cidade: ${e.message}`); }
    }
    if (m.cls > LIMITE_CLS) falhas.push(`CLS ${m.cls.toFixed(3)} (o limite é ${LIMITE_CLS})`);
    if ([...externos].some((h) => /googletagmanager|google-analytics/.test(h))) falhas.push("o site pediu o Google Analytics fora da produção (o gtag só pode carregar em contasdopoder.com)");
    if (externos.size) falhas.push(`o site pediu algo de fora (as letras e tudo o mais são do próprio site): ${[...externos].join(", ")}`);
    if (m.letras < 2) falhas.push(`as letras do site não carregaram (${m.letras} arquivos de letra prontos; esperava 2 ou mais)`);

    let violacoes = null;
    if (axe) {
      await avaliar(axe);
      violacoes = await avaliar(`axe.run(document, { resultTypes: ["violations"] }).then((r) => r.violations.map((v) => ({ id: v.id, impacto: v.impact, n: v.nodes.length, alvo: v.nodes[0].target.join(" "), html: v.nodes[0].html.slice(0, 120) })))`);
      violacoes.forEach((v) => falhas.push(`axe ${v.id} (${v.impacto}, ${v.n}): ${v.alvo} ${v.html}`));
    }
    if (capturas) {
      const { data } = await cmd("Page.captureScreenshot", { format: "png", captureBeyondViewport: true });
      fs.mkdirSync(capturas, { recursive: true });
      fs.writeFileSync(path.join(capturas, `${pg.nome}-${perfil.nome}.png`), Buffer.from(data, "base64"));
    }
    return { pg, perfil, falhas, cls: m.cls, lcp: m.lcp, axe: violacoes ? violacoes.length : null, externos: [...externos], ms: Date.now() - t0 };
  } catch (e) {
    falhas.push(e.message);
    return { pg, perfil, falhas, cls: null, lcp: null, axe: null, externos: [...externos], ms: Date.now() - t0 };
  } finally {
    parar();
    await pagina.fechar();
  }
}

// ------------------------------------------------------------------ Google Analytics só em produção
// O Chrome do teste leva estes nomes ao servidor local (HOSTS_ANALYTICS, em principal()): o gtag tem de carregar em
// contasdopoder.com e www.contasdopoder.com e em mais nenhum endereço (localhost, prévias do Cloudflare Pages, nomes parecidos).
const HOSTS_ANALYTICS = [["contasdopoder.com", true], ["www.contasdopoder.com", true], ["localhost", false], ["127.0.0.1", false], ["xcontasdopoder.com", false], ["contasdopoder.com.exemplo.com", false]];
const REGRAS_DNS = `--host-resolver-rules=${HOSTS_ANALYTICS.filter(([h]) => /\.com/.test(h)).map(([h]) => `MAP ${h} 127.0.0.1`).join(", ")}`;
async function testarAnalytics(nav, base) {
  const porta = new URL(base).port, resultados = [];
  for (const [host, ligado] of HOSTS_ANALYTICS) {
    const falhas = [], pagina = await nav.novaPagina(), externos = new Set();
    const parar = pagina.eventos((metodo, p) => {
      if (metodo !== "Fetch.requestPaused") return;
      const h = new URL(p.request.url).host;
      if (h.replace(/:\d+$/, "") === host || /^(data|blob):/.test(p.request.url)) pagina.cmd("Fetch.continueRequest", { requestId: p.requestId }).catch(() => {});
      else { externos.add(h); pagina.cmd("Fetch.failRequest", { requestId: p.requestId, errorReason: "BlockedByClient" }).catch(() => {}); }
    });
    try {
      await Promise.all([pagina.cmd("Page.enable"), pagina.cmd("Runtime.enable"), pagina.cmd("Network.enable")]);
      await pagina.cmd("Fetch.enable", { patterns: [{ urlPattern: "*" }] });
      await pagina.cmd("Network.setCacheDisabled", { cacheDisabled: true });
      const carregou = new Promise((ok) => { const f = pagina.eventos((m) => { if (m === "Page.loadEventFired") { f(); ok(); } }); });
      await pagina.cmd("Page.navigate", { url: `http://${host}:${porta}/` });
      await carregou; await espera(2500);
      const r = await pagina.avaliar(`({ gtag: typeof gtag, camadas: (window.dataLayer || []).map((x) => x[0]), titulo: document.title })`);
      const pediu = externos.has("www.googletagmanager.com");
      if (ligado) {
        if (r.gtag !== "function") falhas.push("o gtag não existe, e em produção deveria");
        if (!r.camadas.includes("js") || !r.camadas.includes("config")) falhas.push(`o dataLayer não tem "js" e "config" (tem: ${r.camadas.join(", ") || "nada"})`);
        if (!pediu) falhas.push("não pediu o gtag.js ao googletagmanager.com");
      } else {
        if (r.gtag !== "undefined") falhas.push("o gtag existe, e fora da produção não deveria");
        if (r.camadas.length) falhas.push(`o dataLayer tem eventos (${r.camadas.join(", ")})`);
        if ([...externos].some((h) => /googletagmanager|google-analytics/.test(h))) falhas.push("pediu o Google Analytics");
      }
      if (!/Contas do Poder/.test(r.titulo)) falhas.push(`a página não abriu (título "${r.titulo}")`);
    } catch (e) { falhas.push(e.message); } finally { parar(); await pagina.fechar(); }
    resultados.push({ host, ligado, falhas });
  }
  return resultados;
}

// ------------------------------------------------------------------ servidor local e relatório
async function subirServidor() {
  const porta = 8700 + Math.floor(Math.random() * 200);
  const proc = spawn(process.execPath, [path.join(RAIZ, "publicacao", "servir.mjs")], { env: { ...process.env, PORT: String(porta) }, stdio: ["ignore", "pipe", "inherit"] });
  await new Promise((ok, erro) => {
    proc.stdout.on("data", (b) => { if (String(b).includes("localhost")) ok(); });
    proc.on("exit", (c) => erro(new Error(`o servidor local saiu (código ${c}); a porta ${porta} está ocupada?`)));
    setTimeout(() => erro(new Error("o servidor local não subiu em 10 s")), 10000);
  });
  return { base: `http://localhost:${porta}`, parar: () => proc.kill(), vivo: () => proc.exitCode === null && proc.signalCode === null };
}

// Antes de cada página (e depois de qualquer falha): o servidor segue de pé e a página inicial abre? Se não, para tudo com
// um aviso claro, em vez de deixar cada página falhar por conta própria. A causa mais comum é o build (gerar.mjs) rodando
// ao mesmo tempo: ele apaga e refaz publicar/, de onde o servidor lê.
async function verificarServidor(servidor) {
  const parou = (motivo) => new Error(`${motivo} Se o build (node publicacao/gerar.mjs) rodou ao mesmo tempo, espere ele terminar e rode os testes de novo: ele apaga e refaz publicar/.`);
  if (servidor.vivo && !servidor.vivo()) throw parou("O servidor local parou no meio dos testes.");
  let r;
  try { r = await fetch(`${servidor.base}/`, { signal: AbortSignal.timeout(5000) }); }
  catch (e) { throw parou(`Não consegui falar com o servidor (${e.message}).`); }
  if (r.status !== 200) throw parou(`O servidor respondeu ${r.status} à página inicial (publicar/ vazia ou sendo refeita?).`);
}

async function principal() {
  if (arg("baixar-axe")) await baixarAxe();
  let axe = fs.existsSync(AXE_ARQ) ? fs.readFileSync(AXE_ARQ, "utf8") : null;
  if (axe && AXE_SHA256 && crypto.createHash("sha256").update(axe).digest("hex") !== AXE_SHA256 && !process.env.AXE_JS) {
    console.log(`O arquivo ${AXE_ARQ} não tem a impressão digital esperada (AXE_SHA256): não vou usá-lo. Apague-o e rode com --baixar-axe.`);
    axe = null;
  }
  if (!arg("url") && !fs.existsSync(path.join(PUBLICAR, "index.html"))) throw new Error("Falta a pasta publicar/: rode antes node publicacao/gerar.mjs");
  const filtro = arg("paginas") && String(arg("paginas")).split(",");
  const paginas = filtro ? PAGINAS.filter((p) => filtro.includes(p.nome)) : PAGINAS;
  if (!paginas.length) throw new Error(`nenhuma página com esse nome. Nomes: ${PAGINAS.map((p) => p.nome).join(", ")}`);

  const servidor = arg("url") ? { base: String(arg("url")).replace(/\/$/, ""), parar() {} } : await subirServidor();
  const nav = await abrirNavegador([REGRAS_DNS]);
  const sair = async () => { await nav.fechar(); servidor.parar(); };
  process.on("SIGINT", async () => { await sair(); process.exit(130); });
  console.log(`Servidor: ${servidor.base} · Chrome: ${nav.exe}`);
  console.log(`${paginas.length} páginas × ${PERFIS.length} perfis (${PERFIS.map((p) => p.nome).join(", ")}) · axe-core: ${axe ? AXE_VERSAO : "NÃO RODA (sem o arquivo; use --baixar-axe)"}\n`);

  const resultados = [];
  try {
    for (const pg of paginas) {
      for (const perfil of PERFIS) {
        await verificarServidor(servidor).catch((e) => { throw new Error(`${e.message} Parei antes de ${pg.nome} (${perfil.nome}), com ${resultados.length} conferências feitas.`); });
        const r = await testar(nav, servidor.base, pg, perfil, axe, arg("capturas"));
        resultados.push(r);
        const marca = r.falhas.length ? "FALHOU" : "ok    ";
        console.log(`${marca} ${pg.nome.padEnd(22)} ${perfil.nome.padEnd(18)} CLS ${r.cls === null ? "—" : r.cls.toFixed(3)}  LCP ${r.lcp ? (r.lcp / 1000).toFixed(1) + " s" : "—"}  axe ${r.axe === null ? "—" : r.axe}  ${(r.ms / 1000).toFixed(1)} s`);
        r.falhas.forEach((f) => console.log(`         - ${f}`));
        if (r.falhas.length) await verificarServidor(servidor).catch((e) => { throw new Error(`${e.message} A falha acima de ${pg.nome} (${perfil.nome}) pode ser consequência disso.`); });
      }
    }

    if (!arg("sem-analytics") && (!filtro || arg("analytics")) && /^http:\/\/localhost:\d+$/.test(servidor.base)) {
      await verificarServidor(servidor);
      console.log("\nGoogle Analytics só em produção:");
      for (const a of await testarAnalytics(nav, servidor.base)) {
        resultados.push({ pg: { nome: `analytics ${a.host}` }, perfil: { nome: "-" }, falhas: a.falhas, cls: null, lcp: null, axe: null, externos: [], ms: 0 });
        console.log(`${a.falhas.length ? "FALHOU" : "ok    "} ${a.host.padEnd(32)} ${a.ligado ? "gtag ligado (produção)" : "gtag desligado"}`);
        a.falhas.forEach((f) => console.log(`         - ${f}`));
      }
    }
  } finally { await sair(); }

  const ruins = resultados.filter((r) => r.falhas.length), externos = new Set(resultados.flatMap((r) => r.externos));
  const cls = resultados.map((r) => r.cls).filter((c) => c !== null), lcp = resultados.map((r) => r.lcp).filter(Boolean);
  console.log(`\n${resultados.length - ruins.length} de ${resultados.length} conferências sem falha.`);
  if (cls.length) console.log(`CLS: maior ${Math.max(...cls).toFixed(3)} (limite ${LIMITE_CLS}). LCP local: maior ${(Math.max(...lcp, 0) / 1000).toFixed(1)} s (sem limite; mede o servidor local, não a internet).`);
  if (externos.size) console.log(`Pedidos a sites de fora, bloqueados no teste: ${[...externos].join(", ")}.`);
  if (!axe) console.log("ATENÇÃO: o axe-core não rodou. Rode uma vez com --baixar-axe (baixa ~0,5 MB do cdnjs para ~/.cache) ou aponte AXE_JS para o axe.min.js.");
  process.exit(ruins.length ? 1 : 0);
}

principal().catch((e) => { console.error(`Erro: ${e.message}`); process.exit(2); });
