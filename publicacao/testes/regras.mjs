// Testes das REGRAS de cálculo com casos inventados e de CONCORDÂNCIA entre o que o site mostra em cada lugar.
// A regra do pagamento único (a ajuda de custo de deputado e senador sai do "por mês", da posição e do ranking) existe em dois códigos: o app.js
// (a página viva, o ranking e o Comparar) e o gerar.mjs (o HTML pronto de cada página). Este teste confere que dão o MESMO número, e o número certo.
//
//   node publicacao/testes/regras.mjs
//
// 1) Concordância no site de verdade (só Node): para cada deputado, senador e "tudo junto" com página, o valor do topo do HTML pronto
//    (publicar/<endereço>.html) é o que a regra manda (conta feita aqui, de outro jeito, com os números de site/dados/dados.json). Precisa do build.
// 1b) Textos com contagens e coberturas (index.html): o que está escrito é o que os dados dizem.
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
const UNICO_DE = { d: ["ajuda_de_custo"], s: ["ajuda_de_custo"], v: ["pagamento_unico"] };
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

// ------------------------------------------------------------------ 1b) textos do index.html que dependem dos dados
console.log("\n-- Textos com contagens e coberturas: o que está escrito é o que os dados dizem");
{
  const html = fs.readFileSync(path.join(PUBLICAR, "index.html"), "utf8");
  const spans = [...html.matchAll(/<span data-dado="([a-z0-9-]+)">([^<]*)<\/span>/g)].map((m) => [m[1], m[2].replace(/&amp;/g, "&")]);
  const valor = (k) => (spans.find(([c]) => c === k) || [])[1];
  const nomes = (t) => String(t || "").split(/, | e /).filter(Boolean);
  const nomesMeta = (arq) => Object.values(lerDados(arq).meta.cidades).map((c) => c.n).filter(Boolean);
  const MUN = lerDados("municipios.json").m, GOV = lerDados("governadores.json").e;
  const mesmos = (a, b) => JSON.stringify([...a].sort()) === JSON.stringify([...b].sort());
  confere("o número de câmaras no texto é o de municipios.json", valor("n-cidades") === MUN.length.toLocaleString("pt-BR"), `${valor("n-cidades")} x ${MUN.length}`);
  confere("o número de vereadores no texto é o da soma de municipios.json (em milhares)", valor("n-vereadores") === `${Math.round(MUN.reduce((t, r) => t + (r[5] || 0), 0) / 1000)} mil`, valor("n-vereadores"));
  const cam = nomesMeta("camaras.json").filter((n) => n !== "São Paulo"), pre = nomesMeta("prefeituras.json");
  confere("as capitais com vereador por vereador (fora São Paulo) são as de camaras.json, e o número por extenso bate", mesmos(nomes(valor("capitais-camaras")), cam) && valor("n-capitais-camaras") === ["", "uma", "duas", "três", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez", "onze", "doze", "treze", "catorze", "quinze", "dezesseis", "dezessete", "dezoito", "dezenove", "vinte"][cam.length], `${valor("capitais-camaras")} (${valor("n-capitais-camaras")}) x ${cam.length}`);
  confere("as capitais com Prefeitura são as de prefeituras.json, e o número por extenso bate", mesmos(nomes(valor("capitais-prefeituras")), pre) && valor("n-capitais-prefeituras") === ["", "uma", "duas", "três", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez", "onze", "doze"][pre.length], `${valor("capitais-prefeituras")} (${valor("n-capitais-prefeituras")}) x ${pre.length}`);
  const semFolha = GOV.filter((e) => !(e.m && e.m.length)).map((e) => e.uf);
  confere("os estados com a folha mês a mês são os de governadores.json (número e quem fica de fora)", valor("n-folha") === String(GOV.length - semFolha.length) && mesmos(nomes(valor("sem-folha")), semFolha.map((u) => ({ AP: "Amapá", MT: "Mato Grosso", TO: "Tocantins" })[u] || u)), `${valor("n-folha")}; fora: ${valor("sem-folha")} x ${semFolha}`);
  // o interior: o texto fixo fala em "Paraíba e Ceará" (valor por pessoa); o resto (ES, PE, RJ) vem da pasta interior-cargo/
  const lista = (pasta) => fs.readdirSync(path.join(SITE, "dados", pasta)).filter((a) => /^[a-z]{2}\.json$/.test(a)).map((a) => a.slice(0, 2).toUpperCase());
  confere("o texto fixo \"Na Paraíba e no Ceará\" (valor por pessoa) ainda é verdade: só PB e CE em interior/", mesmos(lista("interior"), ["PB", "CE"]), lista("interior").join(","));
  const cargo = lista("interior-cargo"), nomeUF = { ES: "Espírito Santo", PE: "Pernambuco", RJ: "Rio de Janeiro" };
  confere("os estados \"por cargo\" do texto são os de interior-cargo/", cargo.every((u) => (valor("interior-cargo-estados") || "").includes(nomeUF[u] || "?")) && nomes(valor("interior-cargo-estados")).length === cargo.length, `${valor("interior-cargo-estados")} x ${cargo}`);
  const CHAVES = ["n-cidades", "n-vereadores", "n-capitais-camaras", "capitais-camaras", "n-capitais-prefeituras", "capitais-prefeituras", "n-folha", "sem-folha", "interior-cargo-estados", "interior-cargo-estados-baixo", "verba-fora"];
  confere("todo <span data-dado> do index.html é uma chave que o gerar.mjs calcula (nenhum ficou só com o valor de reserva, sem conferência)", spans.every(([c]) => CHAVES.includes(c)) && CHAVES.every((c) => spans.some(([k]) => k === c) || c === "verba-fora"), spans.map(([c]) => c).join(","));
  // a página "Para a imprensa": pronta no HTML (sem JavaScript), com os links, a licença e o modelo de citação, e sem nome de pessoa nem o usuário do GitHub
  const imprensa = fs.existsSync(path.join(PUBLICAR, "imprensa.html")) ? fs.readFileSync(path.join(PUBLICAR, "imprensa.html"), "utf8") : "";
  const miolo = (/<section class="bloco" id="imprensa"[\s\S]*?<\/section>/.exec(imprensa) || [""])[0]; // só a página (o resto é o modelo comum, com o rodapé e as fontes)
  confere("/imprensa existe no HTML pronto, com os quatro links, a licença, o modelo de citação e o contato", ["/sobre", "/atualizacao", "/correcoes", "/dados-abertos"].every((l) => miolo.includes(`href="${l}"`)) && /CC BY 4\.0/.test(miolo) && /consultado em &lt;data&gt;/.test(miolo) && /mailto:contato@contasdopoder\.com/.test(miolo), imprensa ? "faltam links ou texto" : "imprensa.html não existe");
  confere("/imprensa não tem o nome de ninguém nem o usuário do GitHub", imprensa !== "" && !/Laloux|Jean-François|jflaloux|github\.com/i.test(miolo), "achei nome ou github");
  confere("a /imprensa está ligada no rodapé de toda página e na /sobre", /href="\/imprensa"/.test(html) && /href="\/imprensa"/.test(fs.readFileSync(path.join(PUBLICAR, "sobre.html"), "utf8")), "sem o link");
  // texto velho que já foi corrigido: não pode voltar
  const dadosAbertos = fs.readFileSync(path.join(PUBLICAR, "dados-abertos.html"), "utf8");
  confere("a descrição de judiciario.json não diz mais que está fora das páginas do site", !/fora das páginas do site/.test(dadosAbertos) && !/fora das páginas do site/.test(html), "ainda tem o texto velho");
  // A pendência da verba das Câmaras (Recife e Maceió: `verba_fora`): confere a cobertura que existe DE VERDADE (as despesas dos vereadores), e não o limite
  // legal da verba (`verba_mes`, que existe mesmo quando as despesas faltam: foi assim que a pendência do Recife saiu por engano em 04/10/2026).
  {
    const CAMS = lerDados("camaras.json"), ver = CAMS.p.filter((p) => p.k === "v");
    const gastoDe = (cod) => ver.filter((p) => String(p.cid) === String(cod)).filter((p) => Object.entries(p.per).some(([a, r]) => a !== "leg" && (r.c || 0) > 0)).length;
    const fora = Object.entries(CAMS.meta.cidades).filter(([, c]) => (c.verba_fora || []).length);
    const pend = (/<li id="pendencia-verba">[\s\S]*?<\/li>/.exec(html) || [""])[0];
    confere(`a pendência da verba está na página inicial quando alguma Câmara tem verba fora (${fora.map(([, c]) => c.n).join(", ") || "nenhuma"}) e some quando nenhuma tem`, (fora.length > 0) === (pend !== ""), `${fora.length} cidades, pendência ${pend ? "presente" : "ausente"}`);
    confere("a pendência diz o nome de cada Câmara e os anos que ficam de fora", fora.every(([, c]) => pend.includes(c.n) && c.verba_fora.every((a) => pend.includes(a))), pend.slice(0, 200));
    confere("e é verdade: nessas cidades NENHUM vereador tem despesa (c) nos anos de fora (a verba existe só como limite)", fora.every(([cod, c]) => ver.filter((p) => String(p.cid) === cod).every((p) => c.verba_fora.every((a) => !((p.per[a] || {}).c > 0)))), fora.map(([cod, c]) => `${c.n}: ${gastoDe(cod)} com despesa`).join("; "));
    const semAviso = Object.entries(CAMS.meta.cidades).filter(([cod, c]) => c.verba_nome && !(c.verba_fora || []).length && gastoDe(cod) === 0);
    confere("e o contrário: cidade que tem verba (verba_nome) e nenhum vereador com despesa, mas sem verba_fora, não pode existir (seria uma falta sem aviso)", semAviso.length === 0, semAviso.map(([, c]) => c.n).join(", "));
  }
}

// ------------------------------------------------------------------ 1c) o termo da busca sem resultado que vai ao Google Analytics
console.log("\n-- Busca sem resultado: só nome vai ao Analytics (lista branca termoMedivel, lida do app.js)");
{
  const fonte = fs.readFileSync(path.join(SITE, "app.js"), "utf8");
  const sem = /  const semAcento = [^\n]*\n/.exec(fonte), fn = /  function termoMedivel\(valor\) \{[\s\S]*?\n  \}\n/.exec(fonte);
  confere("o app.js tem semAcento e termoMedivel (o teste os lê de lá)", !!sem && !!fn, "não achei no app.js");
  if (sem && fn) {
    const termoMedivel = new Function(`${sem[0]}${fn[0]} return termoMedivel;`)();
    const passa = [["São José dos Campos", "sao jose dos campos"], ["d'Ávila", "d'avila"], ["Dr. João", "dr. joao"], ["  Maria   da  Penha ", "maria da penha"],
      ["Ana-Maria d’Ávila", "ana-maria d’avila"], ["Luiz Inácio Lula da Silva", "luiz inacio lula da silva"], ["Santa Rita do Passa Quatro", "santa rita do passa quatro"],
      ["abcdefghij ".repeat(4) + "abcdef", "abcdefghij ".repeat(4) + "abcdef"] /* 50 caracteres */, ["um dois tres quatro cinco seis", "um dois tres quatro cinco seis"] /* 6 palavras */];
    const barra = ["123.456.789-00", "12345678900", "12 34 56 78 90 1", "1.2.3.4.5.6.7.8.9.0.1", "11 9 8765 4321", "fulano@gmail.com", "https://exemplo.com/a", "joao 13", "lula 2026",
      "", "  ", "x", "ze", "123", ".ana", "-ana", "a".repeat(26), "um dois tres quatro cinco seis sete" /* 7 palavras */, "abcdefghij ".repeat(4) + "abcdefg" /* 51 caracteres */,
      "meu cpf é um dois três quatro cinco seis sete oito nove zero um", "rua das flores quinhentos e vinte tres apto trinta", "ana/maria", "ana_maria", "ana, maria", "ana\nmaria?"];
    const erradosPassa = passa.filter(([e, s]) => termoMedivel(e) !== s).map(([e, s]) => `${JSON.stringify(e)} devia dar ${JSON.stringify(s)} e deu ${JSON.stringify(termoMedivel(e))}`);
    confere(`os ${passa.length} termos que têm cara de nome passam, sem acento e em minúsculas`, erradosPassa.length === 0, erradosPassa.join(" | "));
    const erradosBarra = barra.filter((e) => termoMedivel(e) !== null).map((e) => `${JSON.stringify(e)} passou como ${JSON.stringify(termoMedivel(e))}`);
    confere(`os ${barra.length} termos com número, e-mail, endereço, texto longo, curto ou comprido demais não vão (e não são cortados)`, erradosBarra.length === 0, erradosBarra.join(" | "));
    confere("medirBuscaVazia usa termoMedivel e não corta o texto (sem slice, sem a regra antiga)", /const termo = termoMedivel\(valor\);/.test(fonte) && !/@\|\\d\{3\}/.test(fonte), "o envio não passa pelo filtro");
  }
}

// ------------------------------------------------------------------ 1d) o HTML pronto de vereador de Câmara sem a verba lida
console.log("\n-- Câmara sem a verba na fonte que lemos: o HTML pronto diz \"não publicados\" (a mesma regra do app.js)");
{
  const END = lerDados("enderecos.json").p, CAMS = lerDados("camaras.json");
  const html = (id) => { const arq = path.join(PUBLICAR, `${END[id]}.html`); return fs.existsSync(arq) ? fs.readFileSync(arq, "utf8") : ""; };
  const primeiroDe = (cod) => CAMS.p.find((p) => p.k === "v" && String(p.cid) === String(cod) && END[p.id]);
  const nao = Object.entries(CAMS.meta.cidades).filter(([, c]) => !c.verba_nome && !c.sem_verba).map(([cod]) => cod);
  const com = Object.entries(CAMS.meta.cidades).filter(([, c]) => c.verba_nome).map(([cod]) => cod);
  const erradas = [];
  for (const cod of nao) { const p = primeiroDe(cod), h = p ? html(p.id) : "";
    if (!/resumo-parte--texto"><strong>não publicados<\/strong>/.test(h) || !/Os gastos do mandato não aparecem na fonte que lemos/.test(h) || /em gastos do mandato<\/span>/.test(h)) erradas.push(`${CAMS.meta.cidades[cod].n}: o topo do HTML pronto não diz não publicados`); }
  for (const cod of com) { const p = primeiroDe(cod), h = p ? html(p.id) : "";
    if (/resumo-parte--texto/.test(h)) erradas.push(`${CAMS.meta.cidades[cod].n}: tem verba e o HTML pronto diz não publicados`); }
  confere(`o HTML pronto de ${nao.map((c) => CAMS.meta.cidades[c].n).join(" e ") || "nenhuma cidade"} (sem a verba lida) diz "não publicados", e o das ${com.length} cidades com verba não`, nao.length >= 2 && erradas.length === 0, erradas.join(" | "));
}

// ------------------------------------------------------------------ 1e) pagamento único de vereador: o HTML pronto e a regra dizem o mesmo número
console.log("\n-- Pagamento único de vereador (Vitória e Cuiabá): fora do por mês, no HTML pronto");
{
  const END = lerDados("enderecos.json").p, CAMS = lerDados("camaras.json");
  const com = CAMS.p.filter((p) => p.k === "v" && p.un && p.un.length && END[p.id]);
  const erradas = [];
  for (const p of com) {
    const kPadrao = p.per["2025"] && p.per["2025"].m >= 1 ? "2025" : "2026";
    const r = p.per[kPadrao]; if (!r) continue;
    const esperado = String(Math.round((r.mg ? (r.g - unicoDe(p, kPadrao, new Map())) / r.mg : 0) + (r.mc ? r.c / r.mc : 0)));
    const arq = path.join(PUBLICAR, `${END[p.id]}.html`); if (!fs.existsSync(arq)) { erradas.push(`${p.id}: sem HTML pronto`); continue; }
    const mostrado = digitos((/<p class="resumo-valor">([^<]*)<\/p>/.exec(fs.readFileSync(arq, "utf8")) || [])[1]);
    if (mostrado !== esperado) erradas.push(`${p.n} (${kPadrao}): HTML ${mostrado} x conta ${esperado}`);
  }
  confere(`o valor do topo do HTML pronto dos ${com.length} vereadores com pagamento único é o da regra (sem o pagamento)`, com.length >= 16 && erradas.length === 0, erradas.slice(0, 4).join(" | "));
  const A = CAMS.p.find((p) => p.id === "ver-3205309-80002283949"), U = A && A.un && A.un[0];
  confere("Armandinho Fontoura: o pagamento único é o que a imprensa noticiou (R$ 215.190,24 em dez/2025), com o link de jornal e origem imprensa", !!U && U[0] === 202512 && Math.abs(U[1] - 215190.24) < 0.01 && U[4] === "imprensa" && /^https:\/\/www\.folhavitoria\.com\.br\//.test(U[3]), JSON.stringify(U));
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
// "tudo junto" (ministro e deputado) INVENTADO, com a ajuda de custo DIFERENTE nos dois cargos (ministro R$ 9.000, deputado R$ 46.366): só a do mandato sai do "por mês".
// (O caso de verdade, André Fufuca, tem a mesma ajuda, R$ 39.293, no conjunto e no mandato: uma conta que tirasse a ajuda inteira do conjunto daria o mesmo número.)
const moldeMin = D.p.find((p) => p.k === "e" && p.tp === "mi" && p.x), moldeJ = D.p.find((p) => p.id === "jun-215400");
const depDC = caso("dep-9990008", "Zzcaso Dois Cargos Parlamentar", molde, { m: 6, mg: 6, mc: 6, me: 6, cats: { salario: 278196, ajuda_de_custo: 46366, decimo_terceiro: 23183, cota_parlamentar: 240000, assessores_gabinete: 700000 } });
const minDC = caso("exe-9990009", "Zzcaso Dois Cargos Ministro", moldeMin, { m: 6, mg: 6, mc: 6, me: 0, cats: { salario: 324563, ajuda_de_custo: 9000, decimo_terceiro: 27000, viagens_oficiais: 120000 } });
minDC.c = 120000; minDC.per["2025"].c = 120000; minDC.per.leg = minDC.per["2025"]; minDC.tp = "mi"; delete minDC.per["2025"].cats.cota_parlamentar;
minDC.t = minDC.t.map(([mes, g]) => [mes - 6, g, Math.round(120000 / 6), 0, 0, 0]);   // o ministério vem antes: jan a jun de 2025
const juntoDC = JSON.parse(JSON.stringify(moldeJ));
{
  const a = minDC.per["2025"], b = depDC.per["2025"], cats = {};
  for (const [k, v] of [...Object.entries(a.cats), ...Object.entries(b.cats)]) cats[k] = (cats[k] || 0) + v;
  const r = { m: 12, mg: 12, mc: 12, me: 6, g: a.g + b.g, c: a.c + b.c, e: b.e, pm: b.pm, mp: b.mp, pu: b.pu, ep: b.ep, cats };
  delete juntoDC.aj; delete juntoDC.nv; delete juntoDC.im;
  Object.assign(juntoDC, { id: "jun-9990008", n: "Zzcaso Dois Cargos", nc: "Zzcaso Dois Cargos", f: null, x: 1, per: { "2025": r, leg: r }, t: [...minDC.t, ...depDC.t], dt: {},
    tr: [[202501, 202506, "e"], [202507, 202512, "d"]], cg: [{ id: minDC.id, g: "Ministro do Esporte", x: 0, de: 202501, ate: 202506, ex: 6 }, { id: depDC.id, g: "Deputado federal", x: 1, de: 202507, ate: 202512, ex: 6 }] });
  depDC.j = juntoDC.id; minDC.j = juntoDC.id;
  minDC.n = "Zzcaso Dois Cargos"; depDC.n = "Zzcaso Dois Cargos"; // o mesmo nome nos três, como na vida real
}
const senador = caso("sen-9990007", "Zzcaso Senador Unico", moldeS, { m: 6, mg: 6, mc: 6, me: 6, cats: { salario: 278196, ajuda_de_custo: 46366, decimo_terceiro: 23183, cota_parlamentar: 230000, assessores_gabinete: 700000 } });
senador.aj = { "2025": [[202507, 46366]], leg: [[202507, 46366]] };
const todos = [...novos, senador, depDC, minDC, juntoDC];
const slugs = Object.fromEntries([...CASOS.map(([id, , slug]) => [id, `zzcaso-${slug}`]), ["sen-9990007", "zzcaso-senador-unico"], ["jun-9990008", "zzcaso-dois-cargos"], ["dep-9990008", "zzcaso-dois-cargos/deputado"], ["exe-9990009", "zzcaso-dois-cargos/ministro"]]);
fs.writeFileSync(path.join(DADOS_T, "dados.json"), JSON.stringify({ ...D, p: [...D.p, ...todos] }));
// correções inventadas, para conferir os tipos de página de `paginas`: cidade pelo código IBGE (existente, inexistente e malformado), governador/uf e id de político
fs.writeFileSync(path.join(DADOS_T, "correcoes.json"), JSON.stringify({ intro: "Correções de teste.", c: [
  { data: "2026-10-04", titulo: "Correção de cidade válida", texto: ["Texto da cidade."], paginas: ["cidade/3550308"] },
  { data: "2026-10-03", titulo: "Código de cidade que não existe", texto: ["Texto do código inexistente."], paginas: ["cidade/9999999", "cidade/abc", "governador/sp"] },
  { data: "2026-10-02", titulo: "Caso inventado do deputado", texto: ["Texto do deputado."], paginas: ["dep-9990003"] }] }));
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
    for (let i = 0; i < 120; i++) { await espera(250); if (await pg.avaliar(`!!document.querySelector(${JSON.stringify(esperaSel)}) && !document.querySelector(".carregando")`).catch(() => false)) break; }
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

  console.log("\n-- Correções por tipo de página: cidade (código IBGE), governador, político; código inexistente não quebra");
  {
    const htmlCor = fs.readFileSync(path.join(SAIDA_T, "correcoes.html"), "utf8");
    const idxT = fs.readFileSync(path.join(SAIDA_T, "index.html"), "utf8");
    confere("/correcoes (HTML pronto): a correção da cidade 3550308 leva à página da cidade, com o nome", /<a href="\/cidade\/sao-paulo-sp">Câmara Municipal de São Paulo \(SP\)<\/a>/.test(htmlCor), htmlCor.slice(htmlCor.indexOf("Correção de cidade"), htmlCor.indexOf("Correção de cidade") + 400));
    const blocoInex = (/Código de cidade que não existe[\s\S]*?<\/li>/.exec(htmlCor) || [""])[0];
    confere("código de cidade que não existe (9999999) e malformado (abc): sem link, sem erro; o governador e o político da mesma lista têm link", !/cidade\/9999999|cidade\/abc/.test(blocoInex) && /href="\/governador\/sp">Governo de São Paulo</.test(blocoInex) && /href="\/zzcaso-unico-sem-mes">Zzcaso Unico Sem Mes</.test(htmlCor), blocoInex.slice(0, 400));
    confere("a <meta name=\"correcoes-paginas\"> lista as páginas com correção (o app só baixa o correcoes.json nelas)", /<meta name="correcoes-paginas" content="cidade\/3550308 cidade\/9999999 cidade\/abc governador\/sp dep-9990003">/.test(idxT), (/<meta name="correcoes-paginas"[^>]*>/.exec(idxT) || [])[0]);
    let pg = await abrir("/correcoes", "ol.correcoes li");
    const t = await pg.avaliar(`[...document.querySelectorAll("ol.correcoes li")].map((li) => ({ titulo: li.querySelector("h2").textContent, links: [...li.querySelectorAll(".correcao__paginas a")].map((a) => a.getAttribute("href") + "|" + a.textContent) }))`);
    confere("/correcoes (o app): o mesmo — a cidade tem link com o nome; o código inexistente e o malformado não têm; sem exceção", JSON.stringify(t.find((x) => /cidade válida/.test(x.titulo)).links) === JSON.stringify(["/cidade/sao-paulo-sp|Câmara Municipal de São Paulo (SP)"]) && t.find((x) => /não existe/.test(x.titulo)).links.length === 1 && /^\/governador\/sp\|/.test(t.find((x) => /não existe/.test(x.titulo)).links[0]), JSON.stringify(t));
    await pg.fechar();
    for (const [caminho, titulo, rotulo] of [["/cidade/sao-paulo-sp", "Correção de cidade válida", "cidade (código IBGE)"], ["/governador/sp", "Código de cidade que não existe", "governador (uf)"], [`/${slugs["dep-9990003"]}`, "Caso inventado do deputado", "político (id)"]]) {
      pg = await abrir(caminho, "#erro");
      await espera(800);
      const av = await pg.avaliar(`(() => { const c = document.querySelector("#correcoes-desta-pagina"); return c ? { visivel: !c.hidden, texto: c.textContent.replace(/\\s+/g, " ") } : null; })()`);
      confere(`página de ${rotulo}: o aviso "esta página já foi corrigida" aparece, com a data e o título`, !!av && av.visivel && /Esta página já foi corrigida\./.test(av.texto) && av.texto.includes(titulo) && /\d{2}\/\d{2}\/2026/.test(av.texto), JSON.stringify(av));
      await pg.fechar();
    }
    pg = await abrir("/cidade/fortaleza-ce", "#erro");
    await espera(500);
    confere("página sem correção (Fortaleza): sem aviso", await pg.avaliar(`!document.querySelector("#correcoes-desta-pagina")`));
    await pg.fechar();
  }

  console.log("\n-- Dois cargos inventados, com a ajuda de custo diferente em cada cargo");
  {
    const R25 = juntoDC.per["2025"], certo = esperado(juntoDC);
    const errado = Math.round((R25.g - R25.cats.ajuda_de_custo) / R25.mg + R25.c / R25.mc);          // a conta errada: tirar a ajuda INTEIRA do conjunto (ministro + deputado)
    const semTirar = Math.round(R25.g / R25.mg + R25.c / R25.mc);                                   // e a errada de não tirar nada
    confere(`o caso é forte: a conta certa (${certo}) difere da que tira a ajuda inteira do conjunto (${errado}) e da que não tira nada (${semTirar}) por mais de R$ 500`, Math.abs(certo - errado) >= 500 && Math.abs(certo - semTirar) >= 500, `${certo} ${errado} ${semTirar}`);
    confere("no registro do conjunto a ajuda é a soma dos dois cargos (55.366), e no do mandato é só a do deputado (46.366)", R25.cats.ajuda_de_custo === 55366 && depDC.per["2025"].cats.ajuda_de_custo === 46366 && minDC.per["2025"].cats.ajuda_de_custo === 9000, JSON.stringify([R25.cats.ajuda_de_custo, depDC.per["2025"].cats.ajuda_de_custo, minDC.per["2025"].cats.ajuda_de_custo]));
    const pg = await abrir(`/${slugs[juntoDC.id]}`);
    const L = await lerPagina(pg);
    confere(`${juntoDC.n}: a página mostra ${certo} (só a ajuda do mandato, R$ 46.366, sai do por mês)`, digitos(L.topo) === String(certo), `${L.topo} (a conta errada daria ${errado})`);
    confere("a nota fala da ajuda do mandato (R$ 46.366), nunca da soma dos dois cargos (R$ 55.366)", /ajuda de custo de R\$\s46\.366/.test(L.nota) && !/55\.366/.test(L.nota), L.nota);
    confere("o \"Custo por mês\" no fim da lista é o mesmo", digitos(L.total) === String(certo), L.total);
    await pg.fechar();
  }

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
