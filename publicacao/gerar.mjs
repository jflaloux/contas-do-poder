// Monta a pasta publicar/, que é o que o Cloudflare Pages publica: uma cópia de site/ mais uma página HTML pronta para
// cada endereço do site (/guilherme-boulos, /governador/sp, /cidade/sao-paulo-sp), o sitemap.xml e os redirecionamentos.
//
// Por que páginas prontas: o Google e as prévias de link (WhatsApp, X, Facebook) leem o HTML que o servidor entrega, e
// muitos não rodam JavaScript. Cada página sai com o seu título, a sua descrição e um resumo em texto; depois que carrega,
// o site funciona como antes (app.js desenha tudo).
//
// Uso: node publicacao/gerar.mjs      (sem dependências; Node 18 ou mais novo)
// No Cloudflare Pages: comando de build "node publicacao/gerar.mjs", pasta de saída "publicar".
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SITE = path.join(RAIZ, "site");
const SAIDA = path.join(RAIZ, "publicar");

const ler = (arq, padrao) => { try { return JSON.parse(fs.readFileSync(path.join(SITE, "dados", arq), "utf8")); } catch { return padrao; } };
const D = ler("dados.json");
const CAM = ler("camaras.json", { meta: { cidades: {} }, p: [] });
const PRE = ler("prefeituras.json", { meta: { cidades: {} }, p: [] });
const GOV = ler("governadores.json", { e: [] });
const MUN = ler("municipios.json", { m: [] });
const END = ler("enderecos.json", { p: {}, antigos: {} });
const MODELO = fs.readFileSync(path.join(SITE, "index.html"), "utf8");
const DOMINIO = ((MODELO.match(/<meta name="endereco-do-site" content="([^"]*)"/) || [])[1] || "https://contasdopoder.com/").replace(/\/+$/, "");

// ------------------------------------------------------------------ textos (os mesmos do site)
const ESTADOS = { AC: "Acre", AL: "Alagoas", AM: "Amazonas", AP: "Amapá", BA: "Bahia", CE: "Ceará", DF: "Distrito Federal", ES: "Espírito Santo", GO: "Goiás", MA: "Maranhão", MG: "Minas Gerais", MS: "Mato Grosso do Sul", MT: "Mato Grosso", PA: "Pará", PB: "Paraíba", PE: "Pernambuco", PI: "Piauí", PR: "Paraná", RJ: "Rio de Janeiro", RN: "Rio Grande do Norte", RO: "Rondônia", RR: "Roraima", RS: "Rio Grande do Sul", SC: "Santa Catarina", SE: "Sergipe", SP: "São Paulo", TO: "Tocantins" };
const ART_UF = { AC: "o", AP: "o", AM: "o", BA: "a", CE: "o", DF: "o", ES: "o", MA: "o", MT: "o", MS: "o", PA: "o", PB: "a", PR: "o", PI: "o", RJ: "o", RN: "o", RS: "o", TO: "o" };
const COM_ARTIGO = new Set([2611606, 3304557]); // do Recife, do Rio de Janeiro
const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const deUF = (uf) => (ART_UF[uf] ? `d${ART_UF[uf]} ${ESTADOS[uf]}` : `de ${ESTADOS[uf]}`);
const deCidade = (cod, n) => (COM_ARTIGO.has(+cod) ? `do ${n}` : `de ${n}`);
const semAcento = (t) => String(t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
const slugTxt = (t) => semAcento(t).replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
const fmt = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
const reais = (v) => fmt.format(Math.round(v)).replace(/\s/g, " ");
const esc = (t) => String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const ultimoMes = D.meta.ultimo_mes;
const anoAtual = String(Math.floor(ultimoMes / 100));
const quando = (k) => (k === anoAtual ? `Em ${k} (até ${MESES[(ultimoMes % 100) - 1]})` : `Em ${k}`);

// ------------------------------------------------------------------ a página pronta
// troca, no index.html, o título, a descrição, o endereço oficial e as prévias, e põe um resumo em texto no lugar do
// "Carregando..." (o app.js apaga o resumo quando desenha a página)
function pagina(caminho, titulo, descricao, corpo) {
  const url = `${DOMINIO}/${caminho}`;
  const trocas = [
    [/<title>[^<]*<\/title>/, `<title>${esc(titulo)}</title>`],
    [/<meta name="description" content="[^"]*">/, `<meta name="description" content="${esc(descricao)}">`],
    [/<link rel="canonical" href="[^"]*">/, `<link rel="canonical" href="${esc(url)}">`],
    [/<meta property="og:title" content="[^"]*">/, `<meta property="og:title" content="${esc(titulo)}">`],
    [/<meta property="og:description" content="[^"]*">/, `<meta property="og:description" content="${esc(descricao)}">`],
    [/<meta property="og:url" content="[^"]*">/, `<meta property="og:url" content="${esc(url)}">`],
    [/(<main id="app"[^>]*>)[\s\S]*?(<\/main>)/, `$1\n    ${corpo}\n    <p class="carregando">Carregando os números oficiais…</p>\n  $2`],
  ];
  let html = MODELO;
  for (const [de, para] of trocas) {
    if (!de.test(html)) throw new Error(`index.html mudou: não achei ${de}`);
    html = html.replace(de, para);
  }
  return html;
}
const resumoHTML = (rotulo, nome, texto) =>
  `<article class="cartao conta"><p class="rotulo">${esc(rotulo)}</p><h2>${esc(nome)}</h2><p>${esc(texto)}</p></article>`;

const paginas = []; // [caminho, html]

// ------------------------------------------------------------------ políticos
const cidades = { ...(CAM.meta.cidades || {}), ...(PRE.meta.cidades || {}) };
const pessoas = [...D.p, ...CAM.p, ...PRE.p];
const porId = new Map(pessoas.map((p) => [p.id, p]));
function periodoPadrao(p) {
  if (p.per["2025"] && p.per["2025"].m >= 1) return "2025";
  const anos = Object.keys(p.per).filter((a) => p.per[a] && p.per[a].m > 0).sort();
  return anos[anos.length - 1];
}
function rotuloPessoa(p) {
  const cid = p.cid ? cidades[p.cid] : null;
  if (p.k === "v") return `${p.g} ${cid ? deCidade(p.cid, cid.n) : ""}${p.pt ? ` · ${p.pt}` : ""}`.replace(/\s+/g, " ").trim();
  if (p.k === "p") return /Prefeit/.test(p.g) || !cid ? p.g : `${p.g} · Prefeitura ${deCidade(p.cid, cid.n)}`;
  if (p.k === "e") return `${p.g}${p.pt ? ` · ${p.pt}` : ""}`;
  return `${p.g}${p.pt || p.uf ? ` · ${[p.pt, p.uf].filter(Boolean).join("-")}` : ""}`;
}
const GASTOS = { d: "em gastos do mandato (cota parlamentar e outros)", s: "em gastos do mandato (cota parlamentar e outros)", e: "em viagens oficiais", j: "em gastos dos cargos", v: "com a verba do gabinete" };
const FONTE = { d: "da Câmara dos Deputados", s: "do Senado Federal", e: "do Portal da Transparência", j: "do Congresso e do Portal da Transparência" };
for (const p of pessoas) {
  const caminho = END.p[p.id];
  if (!caminho) continue;
  const k = periodoPadrao(p);
  const r = k && p.per[k];
  const rotulo = rotuloPessoa(p);
  let texto;
  if (!r) texto = `${rotulo}. Veja quanto recebe e quanto custa por mês, com números oficiais.`;
  else {
    const gm = r.mg ? r.g / r.mg : 0, cm = r.mc ? r.c / r.mc : 0;
    const fonte = p.k === "v" ? `da ${(cidades[p.cid] || {}).casa || "Câmara Municipal"}` : p.k === "p" ? `da Prefeitura ${deCidade(p.cid, (cidades[p.cid] || {}).n || "")}` : FONTE[p.k];
    if (p.k === "p") texto = `${rotulo}. ${quando(k)}, recebeu ${reais(gm)} por mês, em média (bruto), pela folha de pagamento ${fonte}. Veja mês a mês e compare com os colegas.`;
    else if (!cm) texto = `${rotulo}. ${quando(k)}, recebeu ${reais(gm)} por mês, em média (salário e auxílios, bruto). Números oficiais ${fonte}, com o link de cada valor.`;
    else texto = `${rotulo}. ${quando(k)}, custou ${reais(gm + cm)} por mês: ${reais(gm)} para o bolso (salário e auxílios) e ${reais(cm)} ${GASTOS[p.k]}. Números oficiais ${fonte}, com o link de cada valor.`;
  }
  const titulo = `${p.n}: ${p.k === "p" ? "quanto recebe" : "quanto ganha e quanto custa"} | Contas do Poder`;
  paginas.push([caminho, pagina(caminho, titulo, texto, resumoHTML(rotulo, p.n, texto))]);
}

// ------------------------------------------------------------------ governadores
const ordemGov = [...GOV.e].sort((a, b) => b.v[0] - a.v[0]);
for (const e of GOV.e) {
  const caminho = `governador/${e.uf.toLowerCase()}`;
  const fem = !!e.gov.fem;
  const cargo = e.gov.ex ? (fem ? "Governadora em exercício" : "Governador em exercício") : fem ? "Governadora" : "Governador";
  const pos = ordemGov.findIndex((x) => x.uf === e.uf) + 1;
  const texto = `${cargo} ${deUF(e.uf)}: ${e.gov.n}${e.gov.pt ? ` (${e.gov.pt})` : ""}. O salário do cargo é de ${reais(e.v[0])} por mês, bruto, o ${pos}º maior entre os 27 estados.`
    + `${e.vv ? ` O do vice é de ${reais(e.vv[0])}.` : ""}${e.m && e.m.length ? " Veja também o que foi pago mês a mês, pela folha de pagamento do Estado." : ""} Com a fonte de cada valor.`;
  const titulo = `Salário do governador ${deUF(e.uf)} (${e.gov.n}) | Contas do Poder`;
  paginas.push([caminho, pagina(caminho, titulo, texto, resumoHTML(`Governo ${deUF(e.uf)}`, e.gov.n, texto))]);
}

// ------------------------------------------------------------------ cidades (as 5.570 câmaras municipais)
const vistos = new Set();
for (const [cod, n, uf, pop, , nv, custo, ano] of MUN.m) {
  const caminho = `cidade/${slugTxt(n)}-${uf.toLowerCase()}`;
  if (vistos.has(caminho)) continue; // não acontece (o nome não se repete no mesmo estado), mas não pode sobrescrever
  vistos.add(caminho);
  const de = deCidade(cod, n);
  const extras = [CAM.meta.cidades && CAM.meta.cidades[cod] ? "quanto recebe e quanto gasta cada vereador" : null,
    PRE.meta.cidades && PRE.meta.cidades[cod] ? "quanto recebem o prefeito, o vice e os secretários" : null].filter(Boolean);
  const texto = (custo > 0
    ? `Em ${ano}, a Câmara Municipal ${de} (${uf}) custou ${reais(custo)}: ${reais(custo / 12)} por mês${pop ? `, ${reais(custo / pop)} por habitante no ano` : ""}${nv ? `, com ${nv} vereadores` : ""}.`
    : `O gasto da Câmara Municipal ${de} (${uf}) não aparece nas contas entregues ao Tesouro Nacional.`)
    + ` Veja o teto do salário do vereador${extras.length ? `, ${extras.join(" e ")}` : ""} e compare com as outras cidades.`;
  const titulo = `Câmara Municipal ${de} (${uf}): quanto custa | Contas do Poder`;
  paginas.push([caminho, pagina(caminho, titulo, texto, resumoHTML(`Câmara Municipal · ${ESTADOS[uf] || uf}`, `${n} (${uf})`, texto))]);
}

// ------------------------------------------------------------------ correções (/correcoes, de site/dados/correcoes.json)
const COR = ler("correcoes.json", null);
if (COR) {
  const link = (ref) => {
    const g = /^governador\/([a-z]{2})$/.exec(ref);
    if (g) return `<a href="/${ref}">${esc(`Governo ${deUF(g[1].toUpperCase())}`)}</a>`;
    const p = porId.get(ref);
    return p && END.p[ref] ? `<a href="/${esc(END.p[ref])}">${esc(p.n)}</a>` : null;
  };
  const dataBR = (d) => d.split("-").reverse().join("/");
  const lista = (COR.c || []).map((c, i) => ({ ...c, i })).sort((a, b) => b.data.localeCompare(a.data) || a.i - b.i);
  const itens = lista.map((c) => {
    const links = (c.paginas || []).map(link).filter(Boolean);
    return `<li class="cartao correcao"><p class="rotulo">${esc(dataBR(c.data))}${c.aviso ? ` · avisado por ${esc(c.aviso)}` : ""}</p>`
      + `<h3>${esc(c.titulo)}</h3>${(c.texto || []).map((t) => `<p>${esc(t)}</p>`).join("")}`
      + (links.length ? `<p class="correcao__paginas pequeno">${links.length === 1 ? "Página corrigida" : `Páginas corrigidas (${links.length})`}: ${links.join(", ")}</p>` : "")
      + "</li>";
  });
  const corpo = `<section class="bloco" id="correcoes"><p class="rotulo">Transparência do site</p><h2>Correções</h2><p class="discreto">${esc(COR.intro || "")}</p>`
    + `<ol class="correcoes">${itens.join("")}</ol></section>`;
  const texto = `Os erros do site que já corrigimos: o que estava errado, o que mudou e quais páginas foram afetadas. ${lista.length} ${lista.length === 1 ? "correção" : "correções"} até agora.`;
  paginas.push(["correcoes", pagina("correcoes", "Correções | Contas do Poder", texto, corpo)]);
}

// ------------------------------------------------------------------ grava
// cópia simples, arquivo por arquivo (o fs.cpSync do Node 22 falha em algumas pastas montadas, como as de máquinas virtuais)
function copiar(de, para) {
  fs.mkdirSync(para, { recursive: true });
  for (const e of fs.readdirSync(de, { withFileTypes: true })) {
    const a = path.join(de, e.name), b = path.join(para, e.name);
    if (e.isDirectory()) copiar(a, b);
    else if (e.isFile()) fs.writeFileSync(b, fs.readFileSync(a));
  }
}
fs.rmSync(SAIDA, { recursive: true, force: true });
copiar(SITE, SAIDA);
for (const [caminho, html] of paginas) {
  const arq = path.join(SAIDA, `${caminho}.html`);
  fs.mkdirSync(path.dirname(arq), { recursive: true });
  fs.writeFileSync(arq, html);
}
// sitemap.xml: a página inicial e todas as páginas prontas
const dia = String(D.meta.gerado_em || new Date().toISOString()).slice(0, 10);
const urls = ["", ...paginas.map(([c]) => c)].map((c) => `<url><loc>${esc(`${DOMINIO}/${c}`)}</loc><lastmod>${dia}</lastmod></url>`);
fs.writeFileSync(path.join(SAIDA, "sitemap.xml"), `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls.join("\n")}\n</urlset>\n`);
// endereços que mudaram (site/dados/enderecos.json, "antigos"): redirecionamento permanente para o atual
const redir = Object.entries(END.antigos || {}).filter(([, id]) => END.p[id]).map(([velho, id]) => `/${velho} /${END.p[id]} 301`);
if (redir.length) fs.writeFileSync(path.join(SAIDA, "_redirects"), `${redir.join("\n")}\n`);
console.log(`publicar/: ${paginas.length} páginas prontas (${pessoas.filter((p) => END.p[p.id]).length} políticos, ${GOV.e.length} estados, ${vistos.size} cidades), sitemap com ${urls.length} endereços, ${redir.length} redirecionamentos`);
