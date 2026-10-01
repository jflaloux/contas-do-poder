// Monta a pasta publicar/, que é o que o Cloudflare Pages publica: uma cópia de site/ mais uma página HTML pronta para
// cada endereço do site (/guilherme-boulos, /governador/sp, /cidade/sao-paulo-sp), o sitemap.xml e os redirecionamentos.
//
// Por que páginas prontas: o Google e as prévias de link (WhatsApp, X, Facebook) leem o HTML que o servidor entrega, e
// muitos não rodam JavaScript. Cada página sai com o seu título, a sua descrição e um resumo em texto; depois que carrega,
// o site funciona como antes (app.js desenha tudo). Na página de um político, o resumo pronto é o topo do contracheque
// (nome, custo por mês e de onde ele vem), para a primeira tela já mostrar o principal enquanto o resto carrega.
//
// Dados mais leves: em publicar/dados/indice/ ficam dados.json e camaras.json sem a série mês a mês (t) e sem o
// detalhe dos gastos (dt) de cada pessoa, que vão para publicar/dados/pessoa/<id>.json e só são baixados ao abrir a
// página daquela pessoa. Os arquivos inteiros continuam em publicar/dados/ (para quem reutiliza os dados).
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
const num = (v, casas = 0) => v.toLocaleString("pt-BR", { maximumFractionDigits: casas, minimumFractionDigits: casas });
const smTxt = (v) => (v >= 10 ? num(v, 0) : num(v, 1));
const daRaiz = (u) => (u && !/^(https?:|data:|\/)/.test(u) ? `/${u}` : u);
function iniciais(nome) {
  const p = nome.replace(/^(Dr|Dra|Delegad[oa]|Coronel|Capitão|Pastor[a]?|Sargento|Professor[a]?|Missionário|General|Cabo|Major|Tenente)\.?\s+/i, "").split(/\s+/);
  return ((p[0] || "")[0] + (p.length > 1 ? p[p.length - 1][0] : "")).toUpperCase();
}
// arquivos que o app.js baixa ao abrir qualquer página: o navegador começa a baixar junto com o app.js
const PRELOAD = ["/dados/indice/dados.json", "/dados/indice/camaras.json", "/dados/prefeituras.json", "/dados/governadores.json", "/dados/enderecos.json"];
const preloads = (extras = []) => [...PRELOAD, ...extras].map((u) => `<link rel="preload" href="${esc(u)}" as="fetch" crossorigin>`).join("\n");

// ------------------------------------------------------------------ a página pronta
// troca, no index.html, o título, a descrição, o endereço oficial e as prévias, e põe um resumo em texto no lugar do
// "Carregando..." (o app.js apaga o resumo quando desenha a página). Toda página daqui é "interna" (body.interna: sem
// a abertura da página inicial; o título h1 é o do resumo).
function pagina(caminho, titulo, descricao, corpo, { extras = [], carregando = true } = {}) {
  const url = `${DOMINIO}/${caminho}`;
  const trocas = [
    [/<body>/, '<body class="interna">'],
    // a pergunta da página inicial fica escondida nas páginas internas: sai como parágrafo, para o único h1 ser o nome
    // (o app.js volta a fazer dela um h1 se a pessoa for para a página inicial sem recarregar)
    [/<h1 id="titulo-abertura">([\s\S]*?)<\/h1>/, '<p id="titulo-abertura">$1</p>'],
    [/<\/head>/, `${preloads(extras)}\n</head>`],
    [/<title>[^<]*<\/title>/, `<title>${esc(titulo)}</title>`],
    [/<meta name="description" content="[^"]*">/, `<meta name="description" content="${esc(descricao)}">`],
    [/<link rel="canonical" href="[^"]*">/, `<link rel="canonical" href="${esc(url)}">`],
    [/<meta property="og:title" content="[^"]*">/, `<meta property="og:title" content="${esc(titulo)}">`],
    [/<meta property="og:description" content="[^"]*">/, `<meta property="og:description" content="${esc(descricao)}">`],
    [/<meta property="og:url" content="[^"]*">/, `<meta property="og:url" content="${esc(url)}">`],
    [/(<main id="app"[^>]*>)[\s\S]*?(<\/main>)/, `$1\n    ${corpo}${carregando ? '\n    <p class="carregando">Carregando os números oficiais…</p>' : ""}\n  $2`],
  ];
  let html = MODELO;
  for (const [de, para] of trocas) {
    if (!de.test(html)) throw new Error(`index.html mudou: não achei ${de}`);
    html = html.replace(de, para);
  }
  return html;
}
const resumoHTML = (rotulo, nome, texto) =>
  `<article class="cartao conta"><div class="conta__topo"><div><p class="rotulo">${esc(rotulo)}</p><h1 class="conta__nome">${esc(nome)}</h1></div></div>`
  + `<p class="conta__texto">${esc(texto)}</p></article>`;

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
// o mesmo topo de contracheque que o app.js desenha (secContracheque/resumoTopo), com os números do período padrão
const partidoUF = (p) => {
  const cid = p.cid ? cidades[p.cid] : null;
  if (p.k === "e") return p.pt ? `${p.pt} · governo federal` : "Governo federal";
  if (p.k === "v") return `${p.pt || "sem partido"} · ${(cid || {}).n || "vereador"}`;
  if (p.k === "p") return p.pt || `Prefeitura ${cid ? deCidade(p.cid, cid.n) : ""}`;
  return `${p.pt || "sem partido"}-${p.uf}`;
};
const gastosNome = (p) => ({ e: "gastos do cargo", j: "gastos dos cargos", p: "gastos do cargo" })[p.k] || "gastos do mandato";
const nomeK = (k) => (k === anoAtual ? `em ${k} (até ${MESES[(ultimoMes % 100) - 1]})` : `em ${k}`);
function previaPessoa(p, k, r, texto) {
  const foto = p.f ? `<img src="${esc(daRaiz(p.f))}" alt="" referrerpolicy="no-referrer">` : "";
  const rotulo = { e: "Contracheque do cargo", j: "Contracheque dos dois cargos, somados", p: "Contracheque do cargo" }[p.k] || "Contracheque do mandato";
  let resumo = "";
  if (r) {
    const gm = r.mg ? r.g / r.mg : 0, cm = r.mc ? r.c / r.mc : 0, salMin = (D.meta.salario_minimo || {})[k];
    // a barra dividida (bolso e gastos) e o valor embaixo de cada pedaço, como no app.js (resumoTopo)
    const parte = `${(gm + cm > 0 ? (gm / (gm + cm)) * 100 : 100).toFixed(1)}%`;
    const partes = p.k === "p"
      ? '<div class="resumo-divisao" style="--parte:100%" aria-hidden="true"><span class="resumo-divisao__ganha"></span></div>'
        + `<ul class="resumo-partes resumo-partes--um"><li class="resumo-parte--ganha"><strong>${esc(reais(gm))}</strong><span>tudo para o bolso</span></li></ul>`
      : `<div class="resumo-divisao" style="--parte:${parte}" aria-hidden="true"><span class="resumo-divisao__ganha"></span><span class="resumo-divisao__custa"></span></div>`
        + `<ul class="resumo-partes" style="--parte:${parte}" aria-label="De onde vem o custo"><li class="resumo-parte--ganha"><strong>${esc(reais(gm))}</strong><span>para o bolso</span></li>`
        + `<li class="resumo-parte--custa"><strong>${esc(reais(cm))}</strong><span>em ${gastosNome(p)}</span></li></ul>`;
    resumo = `<div class="conta__resumo"><div class="conta__resumo-principal"><p class="rotulo">${p.k === "p" ? "Recebe por mês" : "Custo por mês"} ${esc(nomeK(k))}</p>`
      + `<p class="resumo-valor">${esc(reais(gm + cm))}</p>${partes}${salMin ? `<p class="resumo-sm">${smTxt((gm + cm) / salMin)} salários mínimos por mês</p>` : ""}</div></div>`;
  }
  return `<article class="cartao conta" id="previa" data-id="${esc(p.id)}" data-k="${esc(k || "")}">`
    + `<div class="conta__topo"><span class="avatar avatar--g" aria-hidden="true">${esc(iniciais(p.n))}${foto}</span>`
    + `<div><p class="rotulo">${rotulo}</p><h1 class="conta__nome">${esc(p.n)}</h1><div class="conta__sub"><span>${esc(`${p.g} · ${partidoUF(p)}`)}</span>`
    + `${p.x ? '<span class="etiqueta">No cargo</span>' : '<span class="etiqueta etiqueta--fora">Fora do cargo hoje</span>'}</div></div></div>`
    + resumo
    + `<p class="conta__texto">${esc(texto)}</p>`
    + '<p class="carregando" role="status">Carregando os números oficiais…</p></article>';
}
// quem tem a série mês a mês (t) num arquivo à parte (dados/pessoa/<id>.json): dados.json e camaras.json; as prefeituras
// continuam inteiras (o app usa o mês a mês de todos na página da cidade)
const separados = new Set([...D.p, ...CAM.p].filter((p) => p.t).map((p) => p.id));
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
  const extras = separados.has(p.id) ? [`/dados/pessoa/${encodeURIComponent(p.id)}.json`] : [];
  paginas.push([caminho, pagina(caminho, titulo, texto, previaPessoa(p, k, r, texto), { extras, carregando: false })]);
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
      + `<h2 class="h3">${esc(c.titulo)}</h2>${(c.texto || []).map((t) => `<p>${esc(t)}</p>`).join("")}`
      + (links.length ? `<p class="correcao__paginas pequeno">${links.length === 1 ? "Página corrigida" : `Páginas corrigidas (${links.length})`}: ${links.join(", ")}</p>` : "")
      + "</li>";
  });
  const corpo = `<section class="bloco" id="correcoes"><p class="rotulo">Transparência do site</p><h1 class="titulo-pagina">Correções</h1><p class="discreto">${esc(COR.intro || "")}</p>`
    + `<ol class="correcoes">${itens.join("")}</ol></section>`;
  const texto = `Os erros do site que já corrigimos: o que estava errado, o que mudou e quais páginas foram afetadas. ${lista.length} ${lista.length === 1 ? "correção" : "correções"} até agora.`;
  paginas.push(["correcoes", pagina("correcoes", "Correções | Contas do Poder", texto, corpo)]);
}

// ------------------------------------------------------------------ índice de acesso aos salários dos governadores (/indice)
// de site/dados/indice.json: a lista dos estados com o índice em texto (o app.js desenha as barras e os critérios)
const IDX = ler("indice.json", null);
if (IDX && Array.isArray(IDX.estados) && IDX.estados.length) {
  const M = IDX.meta || {};
  const dataBR = (d) => String(d || "").split("-").reverse().join("/");
  const n2 = (v) => (v === null || v === undefined ? "a conferir" : num(v, 2));
  const com = IDX.estados.filter((e) => e.indice !== null && e.indice !== undefined && !(e.a_conferir || []).length)
    .sort((a, b) => b.indice - a.indice || a.nome.localeCompare(b.nome, "pt-BR"));
  const sem = IDX.estados.filter((e) => !com.includes(e)).sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR"));
  const itens = [...com, ...sem].map((e) => `<li><a href="/governador/${esc(e.uf.toLowerCase())}">${esc(e.nome)}</a>: `
    + (com.includes(e) ? `índice ${n2(e.indice)} (completude ${n2(e.completude)}, facilidade ${n2(e.facilidade)})` : "a conferir") + "</li>");
  const titulo = M.titulo || "Índice de acesso aos salários dos governadores";
  const corpo = `<section class="bloco" id="indice"><div class="indice-topo"><p class="rotulo">Governadores</p><h1 class="titulo-pagina">${esc(titulo)}</h1>`
    + (M.pergunta ? `<p class="lide">${esc(M.pergunta)}</p>` : "")
    + `<p class="pequeno">Conferido em ${esc(dataBR(M.conferido_em))}.</p></div><ol class="indice-previa">${itens.join("")}</ol>`
    + (M.como || []).map((c) => `<p class="discreto">${esc(c)}</p>`).join("") + "</section>";
  const texto = `${M.pergunta || titulo} A nota de cada um dos 27 estados, critério por critério, com a prova de cada nota. Conferido em ${dataBR(M.conferido_em)}.`;
  paginas.push(["indice", pagina("indice", `${titulo} | Contas do Poder`, texto, corpo, { extras: ["/dados/indice.json"] })]);
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
// dados mais leves (ver o começo do arquivo): o detalhe dos gastos vai com o nome de cada tipo, e não com o índice na
// lista de tipos do arquivo (as câmaras têm uma lista própria)
const comNomes = (dt, tipos) => Object.fromEntries(Object.entries(dt || {}).map(([k, cats]) =>
  [k, Object.fromEntries(Object.entries(cats).map(([c, xs]) => [c, xs.map(([i, v]) => [tipos[i] ?? String(i), v])]))]));
let nPessoa = 0;
fs.mkdirSync(path.join(SAIDA, "dados", "indice"), { recursive: true });
fs.mkdirSync(path.join(SAIDA, "dados", "pessoa"), { recursive: true });
for (const [arq, dados] of [["dados.json", D], ["camaras.json", CAM]]) {
  if (!dados || !dados.p || !dados.p.length) continue;
  const tipos = (dados.meta && dados.meta.tipos) || [];
  fs.writeFileSync(path.join(SAIDA, "dados", "indice", arq), JSON.stringify({ ...dados, p: dados.p.map(({ t, dt, ...resto }) => resto) }));
  for (const p of dados.p) {
    if (!p.t) continue;
    fs.writeFileSync(path.join(SAIDA, "dados", "pessoa", `${p.id}.json`), JSON.stringify({ t: p.t, dt: comNomes(p.dt, tipos) }));
    nPessoa++;
  }
}
fs.writeFileSync(path.join(SAIDA, "index.html"), MODELO.replace(/<\/head>/, `${preloads()}\n</head>`));
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
console.log(`publicar/: ${paginas.length} páginas prontas (${pessoas.filter((p) => END.p[p.id]).length} políticos, ${GOV.e.length} estados, ${vistos.size} cidades), sitemap com ${urls.length} endereços, ${redir.length} redirecionamentos, ${nPessoa} arquivos por pessoa`);
