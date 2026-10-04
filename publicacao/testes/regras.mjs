// Testes das REGRAS de cálculo com casos inventados e de CONCORDÂNCIA entre o que o site mostra em cada lugar.
// A regra do pagamento único (a ajuda de custo de deputado e senador sai do "por mês", da posição e do ranking) existe em dois códigos: o app.js
// (a página viva, o ranking e o Comparar) e o gerar.mjs (o HTML pronto de cada página). Este teste confere que dão o MESMO número, e o número certo.
//
//   node publicacao/testes/regras.mjs
//
// 1) Concordância no site de verdade (só Node): para cada deputado, senador e "tudo junto" com página, o valor do topo do HTML pronto
//    (publicar/<endereço>.html) é o que a regra manda (conta feita aqui, de outro jeito, com os números de site/dados/dados.json). Precisa do build.
// 2) Casos inventados (Chrome): um build à parte (GERAR_SAIDA/GERAR_DADOS, sem tocar em publicar/) com deputados e um senador inventados: poucos meses
//    (2 e 3), pagamento único com e sem o mês na fonte, devolução (valor negativo) e mais um "tudo junto" de verdade; em cada um, o HTML pronto, a
//    página, o ranking e o Comparar dizem o mesmo número, que é o da conta feita aqui.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import http from "node:http";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { abrirNavegador, espera } from "./cdp.mjs";

const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const SITE = path.join(RAIZ, "site");
const lerDados = (a) => JSON.parse(fs.readFileSync(path.join(SITE, "dados", a), "utf8"));
let falhas = 0, total = 0;
const confere = (nome, ok, detalhe = "") => { total++; if (!ok) falhas++; console.log(`${ok ? "ok    " : "FALHOU"} ${nome}${ok ? "" : `  ← ${detalhe}`}`); };
const digitos = (t) => String(t || "").replace(/[^0-9-]/g, "");

// ------------------------------------------------------------------ a conta, feita aqui de outro jeito (nada de importar o app.js)
const UNICO_DE = { d: ["ajuda_de_custo"], s: ["ajuda_de_custo"] };
const anoPadrao = (p) => (p.per["2025"] && p.per["2025"].m >= 1 ? "2025" : Object.keys(p.per).filter((a) => a !== "leg" && p.per[a] && p.per[a].m > 0).sort().pop());
// o que sai do "por mês": a ajuda de custo do parlamentar (em "tudo junto", a do mandato, que é o 2º cargo)
function unicoDe(p, k, porId) {
  const q = p.k === "j" ? porId.get(((p.cg || [])[1] || {}).id) : p;
  const cats = q && q.per[k] ? q.per[k].cats || {} : {};
  return q && UNICO_DE[q.k] ? UNICO_DE[q.k].reduce((s, c) => s + (cats[c] || 0), 0) : 0;
}
const custoMes = (p, k, porId) => { const r = p.per[k]; return (r.mg ? (r.g - unicoDe(p, k, porId)) / r.mg : 0) + (r.mc ? r.c / r.mc : 0); };

// ------------------------------------------------------------------ 1) o HTML pronto do site de verdade
console.log("-- O HTML pronto (gerar.mjs) segue a regra em todas as páginas de deputado, senador e \"tudo junto\"");
const PUBLICAR = path.join(RAIZ, "publicar");
if (!fs.existsSync(path.join(PUBLICAR, "index.html"))) { console.log("publicar/ não existe: rode antes node publicacao/gerar.mjs"); process.exit(1); }
{
  const D = lerDados("dados.json"), END = lerDados("enderecos.json").p, porId = new Map(D.p.map((p) => [p.id, p]));
  let n = 0, comUnico = 0; const erradas = [];
  for (const p of D.p) {
    if (!["d", "s", "j"].includes(p.k) || !END[p.id]) continue;
    const k = anoPadrao(p); if (!k) continue;
    const arq = path.join(PUBLICAR, `${END[p.id]}.html`);
    if (!fs.existsSync(arq)) { erradas.push(`${p.id}: sem ${END[p.id]}.html`); continue; }
    const html = fs.readFileSync(arq, "utf8");
    const mostrado = digitos((/<p class="resumo-valor">([^<]*)<\/p>/.exec(html) || [])[1]);
    const esperado = String(Math.round(custoMes(p, k, porId)));
    n++; if (unicoDe(p, k, porId)) comUnico++;
    if (mostrado !== esperado) erradas.push(`${p.id} (${p.n}, ${k}): HTML ${mostrado} x conta ${esperado}`);
  }
  confere(`o valor do topo do HTML pronto é o da regra em ${n} páginas (${comUnico} com pagamento único no período padrão)`, erradas.length === 0 && n > 600, `${erradas.length} diferentes: ${erradas.slice(0, 4).join(" | ")}`);
  // a tabela de quem tem pagamento único tem de ser a MESMA nos dois códigos
  const tabApp = /const UNICOS = (\{[^}]*\});/.exec(fs.readFileSync(path.join(SITE, "app.js"), "utf8")), tabGerar = /const UNICOS = (\{[^}]*\});/.exec(fs.readFileSync(path.join(RAIZ, "publicacao", "gerar.mjs"), "utf8"));
  const norm = (m) => m && JSON.stringify(Function(`return ${m[1]}`)());
  confere("a tabela UNICOS é a mesma no app.js e no gerar.mjs", !!tabApp && !!tabGerar && norm(tabApp) === norm(tabGerar), `${tabApp && tabApp[1]} x ${tabGerar && tabGerar[1]}`);
}

// ------------------------------------------------------------------ 2) casos inventados, num build à parte
console.log("\n-- Casos inventados (build à parte, sem tocar em publicar/)");
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "regras-"));
const DADOS_T = path.join(TMP, "dados"), SAIDA_T = path.join(TMP, "publicar");
fs.mkdirSync(DADOS_T, { recursive: true });
const D = lerDados("dados.json"), END = lerDados("enderecos.json");
const molde = D.p.find((p) => p.id === "dep-143084");               // um deputado de verdade, de molde
const moldeS = D.p.find((p) => p.k === "s" && p.x);                  // e um senador
const caso = (id, nome, base, ano) => {
  const p = JSON.parse(JSON.stringify(base));
  const { m, mg, mc, me, cats } = ano;
  const g = Object.entries(cats).filter(([c]) => ["salario", "ajuda_de_custo", "decimo_terceiro", "auxilio_moradia"].includes(c)).reduce((s, [, v]) => s + v, 0);
  const c = cats.cota_parlamentar || 0, e = cats.assessores_gabinete || 0;
  const r = { m, mg, mc, me, g, c, e, pm: me * 18, mp: me, pu: 18, ep: e, cats };
  delete p.aj; delete p.im; delete p.rel; delete p.j;
  Object.assign(p, { id, n: nome, nc: nome, f: null, x: 1, per: { "2025": r, leg: r } });
  const meses = Array.from({ length: m }, (_, i) => 202500 + 13 - m + i); // os m últimos meses de 2025
  p.t = meses.map((mes) => [mes, Math.round(g / mg), Math.round(c / mc), Math.round(e / Math.max(1, me)), 18, 0]); p.dt = {};
  return p;
};
const CASOS = [
  ["dep-9990001", "Zzcaso Poucos Dois", "poucos2", { m: 2, mg: 2, mc: 2, me: 2, cats: { salario: 92732, cota_parlamentar: 80000, assessores_gabinete: 240000 } }],
  ["dep-9990002", "Zzcaso Poucos Tres", "poucos3", { m: 3, mg: 3, mc: 3, me: 3, cats: { salario: 139098, cota_parlamentar: 120000, assessores_gabinete: 360000 } }],
  ["dep-9990003", "Zzcaso Unico Sem Mes", "unico-sem-mes", { m: 5, mg: 5, mc: 5, me: 5, cats: { salario: 231830, ajuda_de_custo: 46366, decimo_terceiro: 19319, cota_parlamentar: 200000, assessores_gabinete: 590000 } }],
  ["dep-9990004", "Zzcaso Unico Com Mes", "unico-com-mes", { m: 5, mg: 5, mc: 5, me: 5, cats: { salario: 231830, ajuda_de_custo: 46366, decimo_terceiro: 19319, cota_parlamentar: 200000, assessores_gabinete: 590000 } }, { "2025": [[202509, 46366]], leg: [[202509, 46366]] }],
  ["dep-9990005", "Zzcaso Devolucao", "devolucao", { m: 11, mg: 11, mc: 11, me: 11, cats: { salario: 510026, ajuda_de_custo: -39293, decimo_terceiro: 42000, cota_parlamentar: 450000, assessores_gabinete: 1300000 } }],
  ["dep-9990006", "Zzcaso Ano Inteiro", "ano-inteiro", { m: 12, mg: 12, mc: 12, me: 12, cats: { salario: 556392, ajuda_de_custo: 0, decimo_terceiro: 46366, cota_parlamentar: 520000, assessores_gabinete: 1400000 } }],
];
const novos = CASOS.map(([id, nome, , ano, aj]) => { const p = caso(id, nome, molde, ano); if (aj) p.aj = aj; return p; });
// um senador com pagamento único (a regra vale para os dois)
const senador = caso("sen-9990007", "Zzcaso Senador Unico", moldeS, { m: 6, mg: 6, mc: 6, me: 6, cats: { salario: 278196, ajuda_de_custo: 46366, decimo_terceiro: 23183, cota_parlamentar: 230000, assessores_gabinete: 700000 } });
senador.aj = { "2025": [[202507, 46366]], leg: [[202507, 46366]] };
const todos = [...novos, senador];
const slugs = Object.fromEntries([...CASOS.map(([id, , slug]) => [id, `zzcaso-${slug}`]), ["sen-9990007", "zzcaso-senador-unico"]]);
fs.writeFileSync(path.join(DADOS_T, "dados.json"), JSON.stringify({ ...D, p: [...D.p, ...todos] }));
fs.writeFileSync(path.join(DADOS_T, "enderecos.json"), JSON.stringify({ ...END, p: { ...END.p, ...slugs } }));
const build = spawnSync(process.execPath, [path.join(RAIZ, "publicacao", "gerar.mjs")], { env: { ...process.env, GERAR_SAIDA: SAIDA_T, GERAR_DADOS: DADOS_T }, encoding: "utf8", cwd: RAIZ });
confere("o build à parte com os dados inventados termina sem erro", build.status === 0 && fs.existsSync(path.join(SAIDA_T, "zzcaso-unico-sem-mes.html")), `${build.status} ${(build.stderr || build.stdout || "").slice(-300)}`);
if (build.status !== 0) { console.log(`\n${total - falhas} de ${total} conferências sem falha.`); process.exit(1); }

// o que a regra manda, para cada caso (conta feita aqui)
const porIdT = new Map([...D.p, ...todos].map((p) => [p.id, p]));
const esperado = (p) => Math.round(custoMes(p, "2025", porIdT));
const unicoNum = (p) => unicoDe(p, "2025", porIdT);
for (const p of todos) {
  const html = fs.readFileSync(path.join(SAIDA_T, `${slugs[p.id]}.html`), "utf8");
  const valor = digitos((/<p class="resumo-valor">([^<]*)<\/p>/.exec(html) || [])[1]);
  const texto = (/<meta name="description" content="([^"]*)"/.exec(html) || [])[1] || "";
  const noTexto = /custou (R\$[\s ][0-9.]+) por mês/.exec(texto);
  confere(`${p.n}: o HTML pronto mostra ${esperado(p)} (topo) e o mesmo valor na descrição`, valor === String(esperado(p)) && (!noTexto || digitos(noTexto[1]) === String(esperado(p))), `topo ${valor}, descrição "${texto.slice(0, 120)}", esperado ${esperado(p)}`);
}

// o servidor e o navegador
const PORTA = 8600 + Math.floor(Math.random() * 300);
const srv = spawn(process.execPath, [path.join(RAIZ, "publicacao", "servir.mjs")], { env: { ...process.env, PORT: String(PORTA), PUBLICAR_DIR: SAIDA_T }, stdio: "ignore" });
const nav = await abrirNavegador();
try {
  await espera(1000);
  const abrir = async (caminho, esperaSel = "#contracheque .conta__resumo .resumo-valor") => {
    const pg = await nav.novaPagina();
    await pg.cmd("Page.enable"); await pg.cmd("Runtime.enable"); await pg.cmd("Network.enable");
    await pg.cmd("Network.setBlockedURLs", { urls: ["*googletagmanager.com*", "*google-analytics.com*"] });
    await pg.cmd("Emulation.setDeviceMetricsOverride", { width: 1280, height: 900, deviceScaleFactor: 1, mobile: false });
    await pg.cmd("Page.navigate", { url: `http://localhost:${PORTA}${caminho}` });
    for (let i = 0; i < 80; i++) { await espera(250); if (await pg.avaliar(`!!document.querySelector(${JSON.stringify(esperaSel)}) && !document.querySelector(".carregando")`).catch(() => false)) break; }
    await espera(500);
    return pg;
  };
  const lerPagina = (pg) => pg.avaliar(`(() => { const est = [...document.querySelectorAll("#ranking .estatistica")].map((e) => e.innerText.replace(/\\s+/g, " "));
    return { topo: (document.querySelector("#contracheque .conta__resumo .resumo-valor") || {}).textContent || "", nota: (document.querySelector("#contracheque .conta__resumo-nota") || {}).innerText || "",
      bolso: (document.querySelector("#contracheque .resumo-parte--ganha strong") || {}).textContent || "", total: (document.querySelector("#contracheque .total__valor") || {}).textContent || "",
      posicao: (document.querySelector("#contracheque .posicao-faixa__frase") || {}).innerText || "", rankEst: est, rankTexto: (document.querySelector("#ranking") || {}).innerText || "",
      unico: (document.querySelector("#contracheque .unico") || {}).innerText || "" }; })()`);
  const comparar = async (pg, nomeOutro) => {
    await pg.avaliar(`(() => { const i = document.querySelector("#busca-comparar"); i.focus(); i.value = ${JSON.stringify(nomeOutro)}; i.dispatchEvent(new Event("input", { bubbles: true })); })()`);
    await espera(400);
    await pg.avaliar(`(() => { const b = [...document.querySelectorAll("#comparar .sugestao")].find((x) => x.textContent.includes(${JSON.stringify(nomeOutro)})); if (b) b.click(); })()`);
    await espera(1200);
    return pg.avaliar(`(() => { const t = document.querySelector("#comparar table"); if (!t) return null; const linhas = Object.fromEntries([...t.querySelectorAll("tbody tr")].map((tr) => [tr.children[0].textContent, [...tr.children].slice(1, 3).map((x) => x.textContent)])); return linhas; })()`);
  };

  console.log("\n-- A página, o ranking e o Comparar dizem o mesmo número que o HTML pronto");
  for (const p of todos.filter((x) => x.k === "d")) {
    const pg = await abrir(`/${slugs[p.id]}`);
    const L = await lerPagina(pg);
    const esp = String(esperado(p)), uni = unicoNum(p), noRank = p.per["2025"].m < 3;
    confere(`${p.n}: a página mostra o topo ${esp}`, digitos(L.topo) === esp, `${L.topo}`);
    confere(`${p.n}: o "Custo por mês" no fim da lista é o mesmo (${esp})`, digitos(L.total) === esp, `${L.total}`);
    if (noRank) confere(`${p.n}: com menos de 3 meses, fora do ranking (e a página diz isso)`, /não entra nesta lista/.test(L.rankTexto) && !L.posicao, JSON.stringify([L.rankTexto.slice(0, 160), L.posicao]));
    else confere(`${p.n}: o ranking traz o mesmo valor (${esp}) e a posição`, L.rankEst.some((t) => /Custo por mês/i.test(t) && digitos(t.replace(/Mediana.*/i, "")) === esp) && L.rankEst.some((t) => /Posição/i.test(t) && /\d+º de \d+/.test(t)), JSON.stringify(L.rankEst));
    if (uni > 0) confere(`${p.n}: a nota diz "fora desta média" com o valor da ajuda${p.aj ? " e o mês da fonte" : " e sem inventar o mês"}`,
      /Fora desta média: ajuda de custo de/.test(L.nota) && digitos(L.nota.replace(/Contando com ela.*/, "")).includes(String(uni)) && (p.aj ? /paga de uma vez em set\/2025/.test(L.nota) : /paga de uma vez no período/.test(L.nota) && !/ em [a-z]{3}\/20/i.test(L.nota.replace(/Contando.*/, ""))), L.nota);
    if (uni < 0) confere(`${p.n}: valor negativo (devolução): a nota diz que é devolução ou acerto e o por mês sobe`, /devolução ou acerto de ajuda de custo/.test(L.nota) && esperado(p) > Math.round(p.per["2025"].g / p.per["2025"].mg + p.per["2025"].c / p.per["2025"].mc), `${L.nota} | ${esperado(p)}`);
    if (uni === 0) confere(`${p.n}: sem pagamento único, sem nota e sem asterisco`, L.nota === "" && !(await pg.avaliar(`!!document.querySelector("#contracheque .resumo-sinal")`)));
    // Comparar: este deputado contra o do "ano inteiro" (e contra o da devolução), lado a lado
    if (p.id !== "dep-9990006") {
      const out = todos.find((x) => x.id === "dep-9990006");
      const t = await comparar(pg, out.n);
      const linha = t && t["Custo por mês"];
      confere(`${p.n}: o Comparar traz o mesmo valor dos dois (${esp} e ${esperado(out)})`, !!linha && digitos(linha[0]) === esp && digitos(linha[1]) === String(esperado(out)), JSON.stringify(t));
    }
    await pg.fechar();
  }
  const pgS = await abrir(`/${slugs["sen-9990007"]}`);
  const LS = await lerPagina(pgS), espS = String(esperado(senador));
  confere(`${senador.n}: a regra vale para o senador (topo ${espS}, nota da ajuda, mês da fonte)`, digitos(LS.topo) === espS && /paga de uma vez em jul\/2025/.test(LS.nota), JSON.stringify([LS.topo, LS.nota]));
  await pgS.fechar();

  console.log("\n-- Dois cargos (ministro e parlamentar), de verdade: a página e a conta dizem o mesmo");
  const j = D.p.find((p) => p.k === "j" && p.per["2023"] && unicoDe(p, "2023", porIdT) > 0 && END.p[p.id]);
  if (j) {
    const pg = await abrir(`/${END.p[j.id]}?periodo=2023`);
    const L = await lerPagina(pg);
    confere(`${j.n} (dois cargos, 2023): o topo é ${Math.round(custoMes(j, "2023", porIdT))} (só a ajuda do mandato sai)`, digitos(L.topo) === String(Math.round(custoMes(j, "2023", porIdT))), `${L.topo}`);
    await pg.fechar();
  } else confere("há um \"tudo junto\" com ajuda de custo para testar", false, "nenhum encontrado nos dados");
} finally {
  await nav.fechar();
  srv.kill();
  fs.rmSync(TMP, { recursive: true, force: true });
}
console.log(`\n${total - falhas} de ${total} conferências sem falha.`);
process.exit(falhas ? 1 : 0);
