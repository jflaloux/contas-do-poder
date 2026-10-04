// Monta a pasta publicar/, que é o que o Cloudflare Pages publica: uma cópia de site/ mais uma página HTML pronta para
// cada endereço do site (/guilherme-boulos, /governador/sp, /cidade/sao-paulo-sp), o sitemap.xml e os redirecionamentos.
//
// Por que páginas prontas: o Google e as prévias de link (WhatsApp, X, Facebook) leem o HTML que o servidor entrega, e
// muitos não rodam JavaScript. Cada página sai com o seu título, a sua descrição e um resumo em texto; depois que carrega,
// o site funciona como antes (app.js desenha tudo). Na página de um político, o resumo pronto é o topo do contracheque
// (nome, custo por mês e de onde ele vem), para a primeira tela já mostrar o principal enquanto o resto carrega.
//
// Dados mais leves: em publicar/dados/indice/ ficam dados.json, camaras.json e assembleias.json sem a série mês a mês
// (t) e sem o detalhe dos gastos (dt) de cada pessoa, que vão para publicar/dados/pessoa/<id>.json e só são baixados ao
// abrir a página daquela pessoa (com o nome de cada tipo de gasto e de cada fornecedor: por isso a lista meta.tipos das
// câmaras e das Assembleias, com milhares de fornecedores, não vai na versão leve). Os arquivos inteiros continuam em
// publicar/dados/ (para quem reutiliza os dados).
//
// Governadores e vices: cada pessoa de governadores.json (e.oc) vira uma pessoa como as da Prefeitura (só o que vai para o
// bolso), em publicar/dados/indice/governadores-pessoas.json, com o mês a mês em publicar/dados/pessoa/<id>.json (ver
// pessoasGovernadores).
//
// Uso: node publicacao/gerar.mjs      (sem dependências; Node 18 ou mais novo)
// No fim, confere os limites do Cloudflare Pages (arquivos, redirecionamentos, tamanho): perto deles, avisa; acima, o
// build falha (ver o fim do arquivo).
// No Cloudflare Pages: comando de build "node publicacao/gerar.mjs", pasta de saída "publicar".
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";

const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SITE = path.join(RAIZ, "site");
const SAIDA = path.join(RAIZ, "publicar");

const ler = (arq, padrao) => { try { return JSON.parse(fs.readFileSync(path.join(SITE, "dados", arq), "utf8")); } catch { return padrao; } };
const D = ler("dados.json");
const CAM = ler("camaras.json", { meta: { cidades: {} }, p: [] });
const PRE = ler("prefeituras.json", { meta: { cidades: {} }, p: [] });
// deputados estaduais: no arquivo vêm com k = "e" (que no site é o governo federal); aqui, como no app.js, viram "a"
const ASS = ler("assembleias.json", { meta: { estados: {} }, p: [] });
const deputadosEstaduais = (ASS.p || []).map((p) => ({ ...p, k: "a" }));
const GOV = ler("governadores.json", { e: [] });
// Judiciário (tribunais superiores, CNJ e PGR): uma página por pessoa e órgão, com k = "t"; o mês a mês (t, tc, ti, nm)
// fica só em dados/judiciario.json, que o app baixa ao abrir uma página do Judiciário (sem arquivo por pessoa: o
// Cloudflare Pages tem limite de arquivos). A lista leve, sem ele, vai em dados/indice/judiciario.json
const JUD = ler("judiciario.json", { meta: { orgaos: {} }, p: [] });
const ORGAOS_J = (JUD.meta && JUD.meta.orgaos) || {};
const judiciario = (JUD.p || []).map((p) => ({ ...p, k: "t" }));
const MUN = ler("municipios.json", { m: [] });
const END = ler("enderecos.json", { p: {}, antigos: {} });
// interior: a folha que cada município manda ao Tribunal de Contas do estado (site/dados/interior/<uf>.json; hoje PB e
// CE). Vai inteiro para publicar/ (o app baixa o do estado ao abrir uma cidade dele); aqui, a lista dos estados vai
// numa <meta> de cada página (o app não baixa o que não existe) e o valor típico do vereador, no texto da cidade
const PASTA_INT = path.join(SITE, "dados", "interior");
const UFS_INT = fs.existsSync(PASTA_INT) ? fs.readdirSync(PASTA_INT).filter((a) => /^[a-z]{2}\.json$/.test(a)).map((a) => a.slice(0, 2)).sort() : [];
const INTERIOR = Object.fromEntries(UFS_INT.map((u) => [u.toUpperCase(), ler(`interior/${u}.json`, null)]).filter(([, d]) => d && d.m));
// interior por cargo (ES, PE, RJ): o Tribunal de Contas só publica o total pago a cada cargo e quantas pessoas estavam nele
// (site/dados/interior-cargo/<uf>.json, outro formato que o de interior/). Mesma ideia: a lista dos estados numa <meta>, e a
// média por vereador (sempre "em média") no texto da cidade
const PASTA_CARGO = path.join(SITE, "dados", "interior-cargo");
const UFS_CARGO = fs.existsSync(PASTA_CARGO) ? fs.readdirSync(PASTA_CARGO).filter((a) => /^[a-z]{2}\.json$/.test(a)).map((a) => a.slice(0, 2)).sort() : [];
const CARGO = Object.fromEntries(UFS_CARGO.map((u) => [u.toUpperCase(), ler(`interior-cargo/${u}.json`, null)]).filter(([, d]) => d && d.m));
let MODELO = fs.readFileSync(path.join(SITE, "index.html"), "utf8"); // com os números da abertura: ver numerosHTML
const DOMINIO = ((MODELO.match(/<meta name="endereco-do-site" content="([^"]*)"/) || [])[1] || "https://contasdopoder.com/").replace(/\/+$/, "");

// ------------------------------------------------------------------ textos (os mesmos do site)
const ESTADOS = { AC: "Acre", AL: "Alagoas", AM: "Amazonas", AP: "Amapá", BA: "Bahia", CE: "Ceará", DF: "Distrito Federal", ES: "Espírito Santo", GO: "Goiás", MA: "Maranhão", MG: "Minas Gerais", MS: "Mato Grosso do Sul", MT: "Mato Grosso", PA: "Pará", PB: "Paraíba", PE: "Pernambuco", PI: "Piauí", PR: "Paraná", RJ: "Rio de Janeiro", RN: "Rio Grande do Norte", RO: "Rondônia", RR: "Roraima", RS: "Rio Grande do Sul", SC: "Santa Catarina", SE: "Sergipe", SP: "São Paulo", TO: "Tocantins" };
const ART_UF = { AC: "o", AP: "o", AM: "o", BA: "a", CE: "o", DF: "o", ES: "o", MA: "o", PA: "o", PB: "a", PR: "o", PI: "o", RJ: "o", RN: "o", RS: "o", TO: "o" }; // "de Mato Grosso", como no nome oficial
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
// o último mês com dados: o da Câmara, da Prefeitura ou da Assembleia da pessoa (cada uma publica num ritmo) ou o geral
const ultimoDe = (p) => ((!p ? null : p.k === "v" ? (CAM.meta.cidades || {})[p.cid] : p.k === "p" ? (PRE.meta.cidades || {})[p.cid]
  : p.k === "a" ? ((ASS.meta || {}).estados || {})[p.uf] : p.k === "g" ? { ultimo_mes: p.um } : p.k === "t" ? ORGAOS_J[p.org] : null) || {}).ultimo_mes || ultimoMes;
const quando = (k, p) => { const u = ultimoDe(p); return String(Math.floor(u / 100)) === k ? `Em ${k} (até ${MESES[(u % 100) - 1]})` : `Em ${k}`; };
const dataBR = (d) => String(d || "").split("-").reverse().join("/"); // "2026-10-01" → "01/10/2026"
const num = (v, casas = 0) => v.toLocaleString("pt-BR", { maximumFractionDigits: casas, minimumFractionDigits: casas });
const smTxt = (v) => (v >= 10 ? num(v, 0) : num(v, 1));
const daRaiz = (u) => (u && !/^(https?:|data:|\/)/.test(u) ? `/${u}` : u);
function iniciais(nome) {
  const p = nome.replace(/^(Dr|Dra|Delegad[oa]|Coronel|Capitão|Pastor[a]?|Sargento|Professor[a]?|Missionário|General|Cabo|Major|Tenente)\.?\s+/i, "").split(/\s+/);
  return ((p[0] || "")[0] + (p.length > 1 ? p[p.length - 1][0] : "")).toUpperCase();
}
// ------------------------------------------------------------------ governadores e vices como pessoas
// Cada governador e vice desde 2023 (e.oc; o id é a pessoa, não o cargo: o vice que virou governador tem uma página só)
// vira uma pessoa no formato das da Prefeitura: só o que vai para o bolso, mês a mês, desde jan/2025.
// - Onde a folha do Estado abre (e.m: [aaaamm, cargo, índice em e.oc, recebido, salário, 13º, férias, auxílios,
//   outros, abate-teto, marca]): o que ela pagou, bruto, já sem o abate-teto. O salário é o recebido menos as outras
//   partes (o abate-teto sai dele); onde a folha não separa as partes (salário vazio), o mês inteiro fica num item só.
//   A linha do mês da saída (marca "s", com os acertos: férias não tiradas, 13º proporcional) fica fora das médias e
//   do mês a mês, como na página do estado: vai em qs, com o valor.
// - No Amapá, em Mato Grosso e no Tocantins (sem folha): o salário da lei (e.h) proporcional aos dias no cargo (de
//   e.oc; a data de saída é o dia em que o próximo assume). Quem esteve só "em exercício" fica sem valores: sem a folha,
//   não dá para saber quem pagou. Nesses estados, hoje, não há ninguém assim.
// gp: em cada período, o grupo de comparação ("g": governador ou em exercício; "gv": vice), ou null se a pessoa teve os
// dois cargos no período (aí fica fora das comparações). tr: o cargo em cada trecho de meses (a faixa do mês a mês).
const CARGO_G = { gov: ["Governador", "Governadora"], vice: ["Vice-governador", "Vice-governadora"], exercicio: ["Governador em exercício", "Governadora em exercício"] };
const INICIO_G = 202501;
const mesDe = (d) => Number(d.slice(0, 4)) * 100 + Number(d.slice(5, 7));
const proxMes = (m) => (m % 100 === 12 ? m + 89 : m + 1);
const mesAnt = (m) => (m % 100 === 1 ? m - 89 : m - 1);
const diaUTC = (d) => Date.UTC(+d.slice(0, 4), +d.slice(5, 7) - 1, +d.slice(8, 10));
// dias de [de, ate) dentro do mês m, e quantos dias o mês tem
function diasNoCargo(de, ate, m) {
  const ini = Date.UTC(Math.floor(m / 100), (m % 100) - 1, 1), fim = Date.UTC(Math.floor(m / 100), m % 100, 1);
  const a = Math.max(ini, diaUTC(de)), b = Math.min(fim, ate ? diaUTC(ate) : fim);
  return [Math.max(0, Math.round((b - a) / 864e5)), Math.round((fim - ini) / 864e5)];
}
const CATS_G = {
  ferias: { grupo: "ganha", nome: "Férias" },
  auxilios_folha: { grupo: "ganha", nome: "Auxílios e benefícios" },
  folha_total: { grupo: "ganha", nome: "Pagamento do mês (a folha não separa salário, 13º e férias)" },
};
function pessoasGovernadores() {
  const fimGeral = mesAnt(Math.floor(((GOV.meta || {}).mes) || proxMes(ultimoMes))); // o último mês fechado
  const lista = [];
  for (const e of GOV.e) {
    const folha = !!(e.m && e.m.length);
    const ini = folha ? Math.min(...e.m.map((x) => x[0])) : INICIO_G;
    const um = folha ? Math.max(...e.m.map((x) => x[0])) : fimGeral;
    for (const id of [...new Set(e.oc.map((o) => o.id).filter(Boolean))]) {
      const ocs = e.oc.map((o, i) => [o, i]).filter(([o]) => o.id === id);
      const idx = new Set(ocs.map(([, i]) => i));
      const ult = ocs[ocs.length - 1][0], fem = ocs.some(([o]) => o.fem) ? 1 : 0;
      const meses = new Map(), qs = [];
      const somar = (m, c, cats) => {
        const x = meses.get(m) || { v: 0, cats: {}, cargos: {} };
        for (const [k, v] of Object.entries(cats)) if (v) { x.cats[k] = (x.cats[k] || 0) + v; x.v += v; x.cargos[c] = (x.cargos[c] || 0) + v; }
        meses.set(m, x);
      };
      if (folha) {
        for (const x of e.m) {
          if (!idx.has(x[2])) continue;
          const c = e.oc[x[2]].c;
          if (String(x[10] || "").includes("s")) { qs.push([x[0], c, Math.round(x[3])]); continue; }
          const parte = (i) => x[i] || 0;
          const partes = { decimo_terceiro: parte(5), ferias: parte(6), auxilios_folha: parte(7), outros_rendimentos: parte(8) };
          let resto = x[3] - Object.values(partes).reduce((a, v) => a + v, 0);
          if (resto < 0) { // o abate-teto maior que o salário: as partes encolhem na mesma proporção
            const f = x[3] / (x[3] - resto);
            for (const k of Object.keys(partes)) partes[k] *= f;
            resto = 0;
          }
          somar(x[0], c, { [x[4] == null ? "folha_total" : "salario"]: resto, ...partes });
        }
      } else {
        for (const [o] of ocs) {
          if (o.c === "exercicio") continue;
          const ate = o.ate ? Math.min(um, mesDe(o.ate)) : um;
          for (let m = Math.max(ini, mesDe(o.de)); m <= ate; m = proxMes(m)) {
            const lei = e.h.filter((x) => x[0] === o.c && x[1] <= m).sort((a, b) => a[1] - b[1]).pop();
            const [d, n] = diasNoCargo(o.de, o.ate, m);
            if (lei && d > 0) somar(m, o.c, { salario: (lei[2] * d) / n });
          }
        }
      }
      const per = {}, t = [], papel = {}, trechos = [];
      const vazio = () => ({ m: 0, mg: 0, mc: 0, me: 0, g: 0, c: 0, e: 0, pm: 0, mp: 0, pu: 0, ep: 0, cats: {} });
      for (const m of [...meses.keys()].sort((a, b) => a - b)) {
        const x = meses.get(m);
        if (x.v < 1) continue;
        const cargo = Object.entries(x.cargos).sort((a, b) => b[1] - a[1])[0][0]; // no mês da troca, o de maior valor
        for (const k of [String(Math.floor(m / 100)), "leg"]) {
          const r = per[k] || (per[k] = vazio());
          r.m++; r.mg++; r.g += x.v;
          for (const [c, v] of Object.entries(x.cats)) r.cats[c] = (r.cats[c] || 0) + v;
          (papel[k] || (papel[k] = new Set())).add(cargo === "vice" ? "gv" : "g");
        }
        t.push([m, Math.round(x.v), 0, 0, 0, 0]);
        const tr = trechos[trechos.length - 1];
        if (tr && tr[2] === cargo && proxMes(tr[1]) === m) tr[1] = m; else trechos.push([m, m, cargo]);
      }
      for (const r of Object.values(per)) {
        r.g = Math.round(r.g);
        r.cats = Object.fromEntries(Object.entries(r.cats).map(([c, v]) => [c, Math.round(v)]).filter(([, v]) => v));
      }
      const atual = (e.gov && e.gov.id === id) || (e.vice && e.vice.id === id);
      const tp = ult.c;
      lista.push({
        id, k: "g", uf: e.uf, tp, n: ult.n, nc: ocs.map(([o]) => o.nc).find(Boolean) || null, pt: ult.pt || null, fem,
        f: ocs.map(([o]) => o.f).reverse().find(Boolean) || null, fc: ocs.map(([o]) => o.fc).reverse().find(Boolean) || null,
        g: `${CARGO_G[tp][fem]} ${deUF(e.uf)}`, x: atual ? 1 : 0,
        o: (folha ? (e.mf && e.mf.u) || (e.folha && e.folha.u) : e.v && e.v[4]) || (e.folha && e.folha.u) || null,
        fonte: folha ? "folha" : "lei", ini, um,
        cg: ocs.map(([o]) => [o.c, o.de, o.ate || null]),
        gp: Object.fromEntries(Object.entries(papel).map(([k, s]) => [k, s.size === 1 ? [...s][0] : null])),
        ...(new Set(trechos.map((x) => x[2])).size > 1 ? { tr: trechos } : {}),
        ...(qs.length ? { qs } : {}),
        ...(ocs.some(([o]) => o.rel && o.rel.length) ? { rel: ocs.flatMap(([o]) => o.rel || [])[0] } : {}),
        per, t,
      });
    }
  }
  return lista;
}
const governadores = GOV.e.length ? pessoasGovernadores() : [];

// arquivos que o app.js baixa ao abrir qualquer página: o navegador começa a baixar junto com o app.js
const PRELOAD = ["/dados/indice/dados.json", "/dados/indice/camaras.json", "/dados/prefeituras.json", "/dados/governadores.json", "/dados/enderecos.json",
  ...((ASS.p || []).length ? ["/dados/indice/assembleias.json"] : []), ...(governadores.length ? ["/dados/indice/governadores-pessoas.json"] : []),
  ...(judiciario.length ? ["/dados/indice/judiciario.json"] : [])];
const preloads = (extras = []) => [...PRELOAD, ...extras].map((u) => `<link rel="preload" href="${esc(u)}" as="fetch" crossorigin>`).join("\n");

// ------------------------------------------------------------------ quando os dados foram gerados
// A data mais recente ("AAAA-MM-DD") entre os arquivos de dados e a situacao.json (refeita no fim de cada rodada): é o
// "atualizado em" dos números da abertura e do rodapé. O app.js a lê de <meta name="dados-atualizados">.
const DATA_ATUALIZADA = (() => {
  const brutas = [D.meta, CAM.meta, PRE.meta, ASS.meta, JUD.meta, GOV.meta, ler("situacao.json", {})].map((m) => String((m && m.gerado_em) || "").slice(0, 10));
  const datas = brutas.filter((d) => /^\d{4}-\d{2}-\d{2}$/.test(d)).sort();
  if (datas.length) return datas[datas.length - 1];
  return String(D.meta.atualizado || "").split("/").reverse().join("-"); // "01/10/2026" -> "2026-10-01"
})();

// ------------------------------------------------------------------ os números da abertura
// Os mesmos blocos que o app.js põe em #chips-info (montarCabecalho), já no HTML: assim a abertura tem a altura certa
// desde o começo e não cresce quando o app.js chega (a página não pula). Mudando o texto lá, mude aqui.
function numerosHTML() {
  // cada número leva ao grupo dele (como no app.js: ALVO_NUMERO)
  const numero = (n, texto, href) => `<a class="numero" href="${href}"><strong>${n.toLocaleString("pt-BR")}</strong><span>${esc(texto)}</span></a>`; // 1.064
  const noCargo = (xs, f) => xs.filter((p) => p.x && f(p)).length;
  const camaras = Object.entries(CAM.meta.cidades || {}), prefs = Object.entries(PRE.meta.cidades || {});
  const ests = [...new Set(deputadosEstaduais.map((p) => p.uf))].filter((uf) => ((ASS.meta || {}).estados || {})[uf]);
  const nomeCid = ([cod, c]) => deCidade(cod, c.n);
  return [
    numero(noCargo(D.p, (p) => p.k === "d" || p.k === "s"), "deputados e senadores no cargo", "/#ranking"),
    numero(noCargo(D.p, (p) => p.k === "e"), "no governo federal", "/#governo"),
    GOV.e.length ? numero(GOV.e.length, "governadores", "/#governadores") : "",
    judiciario.length ? numero(noCargo(judiciario, () => true), "nos tribunais superiores, no CNJ e na PGR", "/judiciario") : "",
    ests.length ? numero(noCargo(deputadosEstaduais, () => true), ests.length === 1 ? `deputados estaduais ${deUF(ests[0])}` : `deputados estaduais em ${ests.length} estados`, "/#ranking") : "",
    camaras.length ? numero(noCargo(CAM.p, () => true), camaras.length === 1 ? `vereadores ${nomeCid(camaras[0])}` : `vereadores em ${camaras.length} capitais`, "/#ranking") : "",
    prefs.length ? numero(noCargo(PRE.p, () => true), prefs.length === 1 ? "na Prefeitura" : `nas prefeituras de ${prefs.length} capitais`, "/#ranking") : "",
    // o 8º quadro leva à página de atualização dos dados (no app.js: o número "x")
    numero(`${MESES[(ultimoMes % 100) - 1]}/${Math.floor(ultimoMes / 100)}`, `último mês dos dados · atualizado em ${DATA_ATUALIZADA.slice(8, 10)}/${DATA_ATUALIZADA.slice(5, 7)}`, "/atualizacao"),
  ].join("");
}
// situação das fontes (situacao.json): as congeladas (o app diz "Folha até ...: a fonte parou de publicar") e os códigos das cidades que
// têm uma reserva pelo Tribunal de Contas (o app só lê a situação nelas)
const SITUACAO0 = ler("situacao.json", { fontes: [], reservas: {} });
const FONTES_CONGELADAS = (SITUACAO0.fontes || []).filter((f) => f.situacao === "congelada" && f.ultimo_mes).map((f) => `${f.id}:${f.ultimo_mes}`).join(" ");
const CIDS_RESERVA = [...new Set(Object.values(SITUACAO0.reservas || {}).map((r) => String(r.cid)))].join(" ");
MODELO = MODELO.replace(/<\/head>/, `<meta name="fontes-congeladas" content="${esc(FONTES_CONGELADAS)}">\n<meta name="reservas-tce" content="${esc(CIDS_RESERVA)}">\n<meta name="dados-interior" content="${UFS_INT.join(" ")}">\n<meta name="dados-interior-cargo" content="${UFS_CARGO.join(" ")}">\n<meta name="dados-atualizados" content="${DATA_ATUALIZADA}">\n</head>`);
{
  const vazio = '<div class="numeros" id="chips-info"></div>';
  if (!MODELO.includes(vazio)) throw new Error("index.html mudou: não achei o #chips-info vazio");
  MODELO = MODELO.replace(vazio, `<div class="numeros" id="chips-info">${numerosHTML()}</div>`);
}

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
const resumoHTML = (rotulo, nome, texto, extra = "") =>
  `<article class="cartao conta"><div class="conta__topo"><div><p class="rotulo">${esc(rotulo)}</p><h1 class="conta__nome">${esc(nome)}</h1></div></div>`
  + `<p class="conta__texto">${esc(texto)}</p>${extra}</article>`;

const paginas = []; // [caminho, html]

// ------------------------------------------------------------------ políticos
const cidades = { ...(CAM.meta.cidades || {}), ...(PRE.meta.cidades || {}) };
const estados = (ASS.meta && ASS.meta.estados) || {};
const pessoas = [...D.p, ...CAM.p, ...PRE.p, ...deputadosEstaduais, ...governadores, ...judiciario];
// quem só tem o que vai para o bolso (a Prefeitura e o governo do estado não publicam os gastos por pessoa)
const soBolso = (p) => p.k === "p" || p.k === "g" || p.k === "t"; // Judiciário: as diárias ficam à parte, fora do total
const porId = new Map(pessoas.map((p) => [p.id, p]));
function periodoPadrao(p) {
  if (p.per["2025"] && p.per["2025"].m >= 1) return "2025";
  const anos = Object.keys(p.per).filter((a) => a !== "leg" && p.per[a] && p.per[a].m > 0).sort(); // "leg" é o mandato todo
  return anos[anos.length - 1];
}
function rotuloPessoa(p) {
  const cid = p.cid ? cidades[p.cid] : null;
  if (p.k === "v") return `${p.g} ${cid ? deCidade(p.cid, cid.n) : ""}${p.pt ? ` · ${p.pt}` : ""}`.replace(/\s+/g, " ").trim();
  if (p.k === "p") return /Prefeit/.test(p.g) || !cid ? p.g : `${p.g} · Prefeitura ${deCidade(p.cid, cid.n)}`;
  if (p.k === "a") return `${p.g} ${deUF(p.uf)}${p.pt ? ` · ${p.pt}` : ""}`;
  if (p.k === "g") return `${p.g}${p.pt ? ` · ${p.pt}` : ""}`;
  if (p.k === "t") return p.g;
  if (p.k === "e") return `${p.g}${p.pt ? ` · ${p.pt}` : ""}`;
  return `${p.g}${p.pt || p.uf ? ` · ${[p.pt, p.uf].filter(Boolean).join("-")}` : ""}`;
}
const GASTOS = { d: "em gastos do mandato (cota parlamentar e outros)", s: "em gastos do mandato (cota parlamentar e outros)", e: "em viagens oficiais", j: "em gastos dos cargos", v: "com a verba do gabinete", a: "com a verba do gabinete" };
// Judiciário: a folha do órgão (ou a cópia dela no DadosJusBr)
const fonteJ = (p) => { const o = ORGAOS_J[p.org] || {}; return `da folha ${o.sigla === "PGR" ? "do MPF" : `do ${o.sigla || p.org}`}${o.via === "DadosJusBr" ? " (via DadosJusBr)" : ""}`; };
const FONTE = { d: "da Câmara dos Deputados", s: "do Senado Federal", e: "do Portal da Transparência", j: "do Congresso e do Portal da Transparência" };
// o mesmo topo de contracheque que o app.js desenha (secContracheque/resumoTopo), com os números do período padrão
const partidoUF = (p) => {
  const cid = p.cid ? cidades[p.cid] : null;
  if (p.k === "e") return p.pt ? `${p.pt} · governo federal` : "Governo federal";
  if (p.k === "v") return `${p.pt || "sem partido"} · ${(cid || {}).n || "vereador"}`;
  if (p.k === "p") return p.pt || `Prefeitura ${cid ? deCidade(p.cid, cid.n) : ""}`;
  if (p.k === "a" || p.k === "g") return p.pt ? `${p.pt}-${p.uf}` : p.uf;
  if (p.k === "t") return (ORGAOS_J[p.org] || {}).n || p.org;
  return `${p.pt || "sem partido"}-${p.uf}`;
};
const gastosNome = (p) => ({ e: "gastos do cargo", j: "gastos dos cargos", p: "gastos do cargo", g: "gastos do cargo", t: "diárias" })[p.k] || "gastos do mandato";
// governador sem a folha (Amapá, Mato Grosso e Tocantins): o salário da lei, e não o que foi pago
const rotuloValor = (p) => (p.k === "g" && p.fonte === "lei" ? "Salário do cargo por mês" : soBolso(p) ? "Recebe por mês" : "Custo por mês");
const nomeK = (k, p) => quando(k, p).replace(/^Em/, "em");
// pagamento único (ver UNICOS no app.js): a ajuda de custo de deputado e senador, paga de uma vez, fica fora do "por mês"
const UNICOS = { d: ["ajuda_de_custo"], s: ["ajuda_de_custo"] };
const somaUnicos = (p, k, r) => {
  const q = p.k === "j" ? porId.get(((p.cg || [])[1] || {}).id) : p;
  const lista = q && UNICOS[q.k];
  if (!lista) return 0;
  const cats = q === p ? r.cats : ((q.per || {})[k] || {}).cats || {};
  return lista.reduce((s, c) => s + (cats[c] || 0), 0);
};
function previaPessoa(p, k, r, texto) {
  const foto = p.f ? `<img src="${esc(daRaiz(p.f))}" alt="" referrerpolicy="no-referrer">` : "";
  const rotulo = { e: "Contracheque do cargo", j: "Contracheque dos dois cargos, somados", p: "Contracheque do cargo", g: "Contracheque do cargo", t: "Contracheque do cargo" }[p.k] || "Contracheque do mandato";
  let resumo = "";
  if (r) {
    const gm = r.mg ? (r.g - somaUnicos(p, k, r)) / r.mg : 0, cm = r.mc ? r.c / r.mc : 0, salMin = (D.meta.salario_minimo || {})[k];
    // a barra dividida (bolso e gastos) e o valor embaixo de cada pedaço, como no app.js (resumoTopo)
    const parte = `${(gm + cm > 0 ? (gm / (gm + cm)) * 100 : 100).toFixed(1)}%`;
    const partes = soBolso(p)
      ? '<div class="resumo-divisao" style="--parte:100%" aria-hidden="true"><span class="resumo-divisao__ganha"></span></div>'
        + `<ul class="resumo-partes resumo-partes--um"><li class="resumo-parte--ganha"><strong>${esc(reais(gm))}</strong><span>tudo para o bolso</span></li></ul>`
      : `<div class="resumo-divisao" style="--parte:${parte}" aria-hidden="true"><span class="resumo-divisao__ganha"></span><span class="resumo-divisao__custa"></span></div>`
        + `<ul class="resumo-partes" style="--parte:${parte}" aria-label="De onde vem o custo"><li class="resumo-parte--ganha"><strong>${esc(reais(gm))}</strong><span>para o bolso</span></li>`
        + `<li class="resumo-parte--custa"><strong>${esc(reais(cm))}</strong><span>em ${gastosNome(p)}</span></li></ul>`;
    const gk = p.k === "g" ? (p.gp || {})[k] : undefined;
    const como = gk === undefined ? "" : gk === null ? ` (como vice e como ${CARGO_G.gov[p.fem].toLowerCase()})` : (gk === "gv") !== (p.tp === "vice") ? ` (como ${CARGO_G[gk === "gv" ? "vice" : "gov"][p.fem].toLowerCase()})` : "";
    // a mesma ordem do app.js (resumoTopo): o total (com o salário mínimo) junto do número e, embaixo, a divisão bolso e gastos
    resumo = `<div class="conta__resumo"><div class="conta__resumo-total"><p class="rotulo">${rotuloValor(p)} ${esc(nomeK(k, p))}${esc(como)}</p>`
      + `<p class="resumo-valor">${esc(reais(gm + cm))}</p>${salMin ? `<div class="resumo-linha"><p class="resumo-sm">${smTxt((gm + cm) / salMin)} salários mínimos por mês</p></div>` : ""}</div>`
      + `<div class="conta__resumo-origem">${partes}</div></div>`;
  }
  return `<article class="cartao conta" id="previa" data-id="${esc(p.id)}" data-k="${esc(k || "")}">`
    + `<div class="conta__topo"><span class="avatar avatar--g" aria-hidden="true">${esc(iniciais(p.n))}${foto}</span>`
    + `<div><p class="rotulo">${rotulo}</p><h1 class="conta__nome">${esc(p.n)}</h1><div class="conta__sub"><span>${esc(`${p.g} · ${partidoUF(p)}`)}</span>`
    + `${p.x ? '<span class="etiqueta">No cargo</span>' : '<span class="etiqueta etiqueta--fora">Fora do cargo hoje</span>'}</div></div></div>`
    + resumo
    + `<p class="conta__texto">${esc(texto)}</p>`
    + '<p class="carregando" role="status">Carregando os números oficiais…</p></article>';
}
// quem tem a série mês a mês (t) num arquivo à parte (dados/pessoa/<id>.json): dados.json, camaras.json e
// assembleias.json; as prefeituras continuam inteiras (o app usa o mês a mês de todos na página da cidade)
const separados = new Set([...D.p, ...CAM.p, ...deputadosEstaduais, ...governadores.filter((p) => p.t.length)].filter((p) => p.t).map((p) => p.id));
for (const p of pessoas) {
  // deputado estadual ainda sem nome no enderecos.json: a página fica no próprio id (/est-35-300607), que o app também
  // abre; quando ganhar um nome, o id vai para "antigos" (e vira redirecionamento)
  const caminho = END.p[p.id] || (p.k === "a" ? p.id : null);
  if (!caminho) continue;
  const k = periodoPadrao(p);
  const r = k && p.per[k];
  const rotulo = rotuloPessoa(p);
  let texto;
  if (!r && p.k === "g") texto = `${rotulo}. Não há pagamentos a ${p.n} na folha de pagamento ${deUF(p.uf)} publicada até ${MESES[(p.um % 100) - 1]}/${Math.floor(p.um / 100)}. Veja o salário do cargo e as notas sobre o estado.`;
  else if (!r) texto = `${rotulo}. Veja quanto recebe e quanto custa por mês, com números oficiais.`;
  else {
    const gm = r.mg ? (r.g - somaUnicos(p, k, r)) / r.mg : 0, cm = r.mc ? r.c / r.mc : 0;
    const fonte = p.k === "v" ? `da ${(cidades[p.cid] || {}).casa || "Câmara Municipal"}` : p.k === "a" ? `da ${(estados[p.uf] || {}).casa || "Assembleia Legislativa"}`
      : p.k === "p" ? `da Prefeitura ${deCidade(p.cid, (cidades[p.cid] || {}).n || "")}` : p.k === "t" ? fonteJ(p) : FONTE[p.k];
    // no Congresso e no governo federal, o bolso tem também o 13º (vereador e deputado estadual com o salário da lei, não)
    const bolso = ["d", "s", "e", "j"].includes(p.k) ? "salário, 13º e auxílios" : p.k === "t" ? "bruto, antes do abate-teto" : "salário e auxílios";
    // governador que era vice no período (ou teve os dois cargos nele): diz em qual cargo
    const gk = p.k === "g" ? (p.gp || {})[k] : null, grupoG = gk === "gv" ? "vice-governadores" : "governadores";
    const como = p.k !== "g" ? "" : gk === null ? " (como vice e como governador)" : (gk === "gv") !== (p.tp === "vice") ? ` (como ${CARGO_G[gk === "gv" ? "vice" : "gov"][p.fem].toLowerCase()})` : "";
    if (p.k === "g" && p.fonte === "lei") texto = `${rotulo}. ${quando(k, p)}${como}, o salário oficial do cargo foi de ${reais(gm)} por mês, em média (bruto), pelos dias no cargo. O Estado não publica a folha de pagamento em dados abertos. Com a fonte de cada valor.`;
    else if (p.k === "g") texto = `${rotulo}. ${quando(k, p)}${como}, recebeu ${reais(gm)} por mês, em média (bruto), pela folha de pagamento ${deUF(p.uf)}. Veja mês a mês${gk ? ` e compare com os outros ${grupoG}` : ""}.`;
    else if (p.k === "p") texto = `${rotulo}. ${quando(k, p)}, recebeu ${reais(gm)} por mês, em média (bruto), pela folha de pagamento ${fonte}. Veja mês a mês e compare com os colegas.`;
    else if (p.k === "t") texto = `${rotulo}. ${quando(k, p)}, recebeu ${reais(gm)} por mês, em média (bruto, antes do abate-teto), pela folha ${fonteJ(p).replace(/^da folha /, "")}${cm ? `, mais ${reais(cm)} por mês em diárias de viagem` : ""}. Veja o contracheque de cada mês, com o link da fonte.`;
    else if (!cm) texto = `${rotulo}. ${quando(k, p)}, recebeu ${reais(gm)} por mês, em média (${bolso}, bruto). Números oficiais ${fonte}, com o link de cada valor.`;
    else texto = `${rotulo}. ${quando(k, p)}, custou ${reais(gm + cm)} por mês: ${reais(gm)} para o bolso (${bolso}) e ${reais(cm)} ${GASTOS[p.k]}. Números oficiais ${fonte}, com o link de cada valor.`;
  }
  const titulo = `${p.n}: ${soBolso(p) ? "quanto recebe" : "quanto ganha e quanto custa"} | Contas do Poder`;
  const extras = [...(separados.has(p.id) ? [`/dados/pessoa/${encodeURIComponent(p.id)}.json`] : p.k === "t" ? ["/dados/judiciario.json"] : []),
    ...(p.k === "d" || p.k === "s" ? ["/dados/atividade.json"] : [])]; // presença e projetos (um arquivo, só nessas páginas)
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
    + `${e.vv ? ` O do vice é de ${reais(e.vv[0])}.` : ""}${e.m && e.m.length ? " Veja também o que foi pago mês a mês, pela folha de pagamento do Estado." : ""}`
    + `${estados[e.uf] ? ` E quanto ganha e quanto custa cada um dos ${deputadosEstaduais.filter((p) => p.uf === e.uf && p.x).length} ${e.uf === "DF" ? "deputados distritais" : "deputados estaduais"}.` : ""} Com a fonte de cada valor.`;
  const titulo = `Salário do governador ${deUF(e.uf)} (${e.gov.n}) | Contas do Poder`;
  paginas.push([caminho, pagina(caminho, titulo, texto, resumoHTML(`Governo ${deUF(e.uf)}`, e.gov.n, texto))]);
}

// ------------------------------------------------------------------ cidades (as 5.569 câmaras municipais)
// o valor típico de um vereador pela folha do interior: a mediana, entre os vereadores na folha do último mês, da
// mediana dos meses com valor nos últimos 12 de cada um (o mesmo cálculo do app.js, tipicoInt)
const medianaN = (xs) => { const a = xs.filter((x) => x != null).sort((x, y) => x - y); const m = Math.floor(a.length / 2); return !a.length ? null : a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2; };
function vereadorInterior(cod, uf) {
  const d = INTERIOR[uf], c = d && d.m[String(cod)];
  if (!c || !c.v || !c.v.length || (CAM.meta.cidades || {})[cod]) return null;
  const M = d.meta, limite = (() => { const t = Math.floor(M.ultimo_mes / 100) * 12 + (M.ultimo_mes % 100) - 13; return Math.floor(t / 12) * 100 + (t % 12) + 1; })();
  const tipico = (q) => {
    const s = q.t.flatMap(([v, n]) => Array(n).fill(v)).map((v, i) => { const t = Math.floor(M.inicio / 100) * 12 + (M.inicio % 100) - 1 + i; return [Math.floor(t / 12) * 100 + (t % 12) + 1, v]; }).filter(([, v]) => v != null);
    const ult = s.filter(([m]) => m > limite);
    return medianaN((ult.length ? ult : s).map(([, v]) => v));
  };
  const agora = c.v.filter((q) => q.x);
  return { med: medianaN(agora.map(tipico)), n: agora.length, tribunal: M.tribunal, prefeitura: !(PRE.meta.cidades || {})[cod] && (c.pf || []).some((q) => q.x) };
}
// O parágrafo em destaque da página da cidade (o mesmo texto do app.js, secCidade): vai pronto no HTML, porque é o maior
// bloco de texto da página. Se ele só chegasse com o app.js (a página espera uns 600 KB de dados), o LCP (o momento em que
// a parte principal aparece) passaria da primeira pintura, ~0,8 s, para ~4,7 s no celular com rede lenta. O teste do site
// confere que o texto pronto e o do app.js são iguais.
const FAIXAS = (MUN.meta || {}).faixas_teto || [];
const faixaDe = (pop) => FAIXAS.findIndex(([lim]) => lim === null || pop <= lim);
const porHabMes = (custo, pop) => custo / pop / 12;
const reaisC = (v) => v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" }).replace(/ /g, " ");
const nomeFaixa = (i) => {
  const ant = i ? FAIXAS[i - 1][0] : 0, lim = FAIXAS[i][0];
  const num = (v) => v.toLocaleString("pt-BR", { maximumFractionDigits: 0 });
  return lim === null ? `mais de ${num(ant)} habitantes` : i === 0 ? `até ${num(lim)} habitantes` : `entre ${num(ant + 1)} e ${num(lim)} habitantes`;
};
const medianaCid = (xs) => medianaN(xs);
const medFaixa = FAIXAS.map((_, i) => medianaCid(MUN.m.filter((r) => r[6] > 0 && r[3] > 0 && faixaDe(r[3]) === i).map((r) => porHabMes(r[6], r[3]))));
const temCustoCid = (r) => r[6] > 0 && r[3] > 0 && !(porHabMes(r[6], r[3]) < 0.3 * medFaixa[faixaDe(r[3])]); // sem o "suspeito" do app.js
const valoresFaixa = FAIXAS.map((_, i) => MUN.m.filter((r) => temCustoCid(r) && faixaDe(r[3]) === i).map((r) => porHabMes(r[6], r[3])));
function destaqueCidade(cod, n, pop, custo) {
  if (!FAIXAS.length || !(custo > 0 && pop > 0) || !temCustoCid([cod, n, "", pop, 0, 0, custo])) return "";
  const faixa = faixaDe(pop), vs = valoresFaixa[faixa], meu = porHabMes(custo, pop);
  if (vs.length <= 1) return "";
  const outras = Math.max(1, vs.length - 1);
  let abaixo = 0, acima = 0;
  for (const v of vs) { if (v < meu) abaixo++; else if (v > meu) acima++; }
  const pct = Math.floor((abaixo / outras) * 100), pctMais = Math.floor((acima / outras) * 100);
  const texto = `Por habitante, a Câmara ${deCidade(cod, n)} custa ${pctMais < 50 ? `mais que ${pct}%` : `menos que ${pctMais}%`} das outras ${outras} cidades do mesmo tamanho (${nomeFaixa(faixa)}). A mediana delas é ${reaisC(medianaCid(vs))} por habitante, por mês.`;
  return `<div class="cidade__corpo"><p class="destaque">${esc(texto)}</p></div>`;
}
const vistos = new Set();
for (const [cod, n, uf, pop, , nv, custo, ano] of MUN.m) {
  const caminho = `cidade/${slugTxt(n)}-${uf.toLowerCase()}`;
  if (vistos.has(caminho)) continue; // não acontece (o nome não se repete no mesmo estado), mas não pode sobrescrever
  vistos.add(caminho);
  const de = deCidade(cod, n);
  const vi = vereadorInterior(cod, uf);
  // ES, PE, RJ: o total pago ao cargo de vereador e a média por pessoa (nunca "o vereador recebe"); prefeito e vice só no ES e em PE
  const dc = CARGO[uf], cg = dc && !(CAM.meta.cidades || {})[cod] ? dc.m[String(cod)] : null;
  const cgPref = dc && !(PRE.meta.cidades || {})[cod] && dc.m[String(cod)] && (dc.meta.papeis || []).includes("prefeito") && (dc.m[String(cod)].pf || dc.m[String(cod)].vp);
  const extras = [CAM.meta.cidades && CAM.meta.cidades[cod] ? "quanto recebe e quanto gasta cada vereador" : vi ? "quanto recebe cada vereador em cada mês" : cg && cg.c ? "quanto a Câmara paga ao cargo de vereador" : null,
    PRE.meta.cidades && PRE.meta.cidades[cod] ? "quanto recebem o prefeito, o vice e os secretários" : vi && vi.prefeitura ? "quanto recebem o prefeito e o vice" : cgPref ? "quanto a Prefeitura paga ao prefeito e ao vice" : null].filter(Boolean);
  const texto = (custo > 0
    ? `Em ${ano}, a Câmara Municipal ${de} (${uf}) custou ${reais(custo)}: ${reais(custo / 12)} por mês${pop ? `, ${reais(custo / pop)} por habitante no ano` : ""}${nv ? `, com ${nv} vereadores` : ""}.`
    : `O gasto da Câmara Municipal ${de} (${uf}) não aparece nas contas entregues ao Tesouro Nacional.`)
    + (vi && vi.med ? ` Um vereador recebe ${reais(vi.med)} por mês (valor típico, bruto, na folha que a Câmara manda ao ${vi.tribunal}).` : "")
    + (!vi && cg && cg.c && cg.c.vm ? ` Em média, a Câmara paga ${reais(cg.c.vm)} por ${(dc.meta.papeis || []).includes("prefeito") ? "vereador" : "agente político"} por mês (o total pago ao cargo dividido pelas pessoas no cargo, pelo que informa ao ${dc.meta.tribunal}).` : "")
    + ` Veja o teto do salário do vereador${extras.length ? `, ${extras.join(" e ")}` : ""} e compare com as outras cidades.`;
  const titulo = `Câmara Municipal ${de} (${uf}): quanto custa | Contas do Poder`;
  paginas.push([caminho, pagina(caminho, titulo, texto, resumoHTML(`Câmara Municipal · ${ESTADOS[uf] || uf}`, `${n} (${uf})`, texto, destaqueCidade(cod, n, pop, custo)))]);
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

// ------------------------------------------------------------------ Índice de Transparência dos estados (/indice)
// de site/dados/indice_transparencia.json: a lista dos estados com o índice geral e o de cada bloco (cada fonte do
// estado: governo, Assembleia, prefeitura e Câmara da capital) em texto; os estados com algum bloco a conferir vêm à
// parte, com o índice parcial. O app.js desenha as barras e os critérios. O texto do contexto e os nomes dos blocos da
// capital ("Prefeitura do Recife") são os mesmos do app.js (textoContextoIndice, tituloBloco): mudando um, mude o outro
const IDX = ler("indice_transparencia.json", null);
if (IDX && Array.isArray(IDX.estados) && IDX.estados.length) {
  const M = IDX.meta || {}, BL = M.blocos || [];
  const nulo = (v) => v === null || v === undefined;
  const n2 = (v) => (nulo(v) ? "a conferir" : num(v, 2));
  const com = IDX.estados.filter((e) => !nulo(e.indice) && !(e.a_conferir || []).length)
    .sort((a, b) => Number(b.indice.toFixed(2)) - Number(a.indice.toFixed(2)) || a.nome.localeCompare(b.nome, "pt-BR")); // como no app.js
  const sem = IDX.estados.filter((e) => !com.includes(e)).sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR"));
  // o link de cada bloco para a página do site com os números daquela fonte, quando ela existe (a da capital do estado)
  const capital = (meta, e) => Object.values((meta && meta.cidades) || {}).find((c) => c.uf === e.uf && (!e.capital || c.n === e.capital));
  const listaE = (xs) => (xs.length <= 1 ? xs.join("") : `${xs.slice(0, -1).join(", ")} e ${xs[xs.length - 1]}`);
  const deNome = (n) => `${["Recife", "Rio de Janeiro"].includes(n) ? "do" : "de"} ${n}`;
  const tituloBloco = (b, x) => (!x || !x.cidade ? b.titulo
    : / da capital$/.test(b.titulo) ? `${b.titulo.replace(/ da capital$/, "")} ${deNome(x.cidade)}` : `${b.titulo} (${x.cidade})`);
  const linkBloco = (e, b) => {
    const uf = e.uf.toLowerCase();
    if (b.id === "governo" && GOV.e.some((g) => g.uf === e.uf)) return `/governador/${uf}`;
    if (b.id === "assembleia" && estados[e.uf] && GOV.e.some((g) => g.uf === e.uf)) return `/governador/${uf}#assembleia`;
    const c = b.id === "prefeitura" ? capital(PRE.meta, e) : b.id === "camara" ? capital(CAM.meta, e) : null;
    return c ? `/cidade/${slugTxt(c.n)}-${uf}` : null;
  };
  const blocoTxt = (e, b) => {
    const x = (e.blocos || {})[b.id] || {}, u = linkBloco(e, b);
    const t = tituloBloco(b, x), nome = u && !x.nao_se_aplica ? `<a href="${esc(u)}">${esc(t)}</a>` : esc(t);
    return `${nome} ${x.nao_se_aplica ? "não se aplica" : nulo(x.indice) ? "a conferir" : `${n2(x.indice)} (completude ${n2(x.completude)}, facilidade ${n2(x.facilidade)})`}`;
  };
  const nFontes = IDX.estados.reduce((a, e) => a + BL.filter((b) => { const x = (e.blocos || {})[b.id]; return x && !x.nao_se_aplica; }).length, 0);
  const contexto = `Não existe uma base nacional com esses números. Cada órgão publica os seus no próprio portal, do seu jeito: em planilha, em página, em PDF, às vezes só depois de um CAPTCHA. Para reunir tudo, entramos em cada uma das ${nFontes} fontes dos ${IDX.estados.length} estados, baixamos os dados (com um robô, onde o portal deixa) e conferimos. O índice mede esse caminho: o que cada fonte mostra e como dá para obter os dados.`;
  const item = (e) => `<li><strong>${esc(e.nome)}</strong>: `
    + (com.includes(e) ? `índice ${n2(e.indice)}` : nulo(e.indice_parcial) ? "índice geral a conferir"
      : `índice parcial ${n2(e.indice_parcial)}, com ${e.blocos_com_nota} de ${e.blocos_que_valem} blocos`)
    + (BL.length ? `; ${BL.map((b) => blocoTxt(e, b)).join("; ")}` : "") + "</li>";
  const listaSem = sem.length ? `<h2 class="h3">Com algum bloco a conferir</h2><p class="discreto">Fora da ordem acima. O índice parcial é a média só dos blocos que já têm nota; o índice geral sai quando todos tiverem.</p><ul class="indice-previa">${sem.map(item).join("")}</ul>` : "";
  const titulo = M.titulo || "Índice de Transparência dos estados";
  const corpo = `<section class="bloco" id="indice"><div class="indice-topo"><p class="rotulo">Estados</p><h1 class="titulo-pagina">${esc(titulo)}</h1>`
    + (M.pergunta ? `<p class="lide">${esc(M.pergunta)}</p>` : "")
    + `<p class="indice-topo__contexto">${esc(contexto)}</p>`
    + `<p class="pequeno">Conferido em ${esc(dataBR(M.conferido_em))}. ${com.length} estados com índice geral${sem.length ? `; em ${sem.length === 1 ? esc(sem[0].nome) : `${sem.length} (${esc(listaE(sem.map((e) => e.nome)))})`}, algum bloco ainda está a conferir` : ""}.</p></div>`
    + `<ol class="indice-previa">${com.map(item).join("")}</ol>${listaSem}`
    + (M.como || []).map((c) => `<p class="discreto">${esc(c)}</p>`).join("") + "</section>";
  const texto = `${M.pergunta || titulo} Não existe uma base nacional: são ${nFontes} fontes oficiais, cada uma publicada do seu jeito. A nota de cada uma, critério por critério, com a prova. Conferido em ${dataBR(M.conferido_em)}.`;
  paginas.push(["indice", pagina("indice", `${titulo} | Contas do Poder`, texto, corpo, { extras: ["/dados/indice_transparencia.json"] })]);
}


// ------------------------------------------------------------------ Judiciário (/judiciario)
// Os 7 órgãos (STF, STJ, TST, STM, TSE, CNJ e PGR), com quem está no cargo e a média por mês desde jan/2025; o app.js
// desenha a mesma página com o último mês de cada um e quem saiu
if (judiciario.length) {
  const mesTxt = (m) => `${MESES[(m % 100) - 1]}/${Math.floor(m / 100)}`;
  const lide = "Quanto recebe quem está no topo da Justiça: os ministros do STF, do STJ, do TST, do STM e do TSE, os conselheiros do CNJ e o procurador-geral da República. Mês a mês desde jan/2025, pela folha de pagamento de cada órgão, com o link da fonte de cada mês.";
  const bloco = ([sigla, o]) => {
    const ps = judiciario.filter((p) => p.org === sigla && p.x).sort((a, b) => a.n.localeCompare(b.n, "pt-BR"));
    const linha = (p) => {
      const r = p.per.leg, med = r && r.mg ? r.g / r.mg : 0;
      return `<li><a href="/${esc(END.p[p.id] || p.id)}">${esc(p.n)}</a> <small>${esc(p.g)}${med ? ` · ${esc(reais(med))} por mês, em média, desde jan/2025` : ""}</small></li>`;
    };
    return `<h2 class="h3">${esc(o.n)} (${esc(sigla)})</h2><p class="discreto">${ps.length} no cargo · dados até ${mesTxt(o.ultimo_mes)}${o.via === "DadosJusBr" ? " · via DadosJusBr" : ""}</p><ul class="lista">${ps.map(linha).join("")}</ul>`;
  };
  const corpo = '<section class="bloco" id="judiciario" aria-labelledby="t-judiciario"><p class="rotulo">Justiça</p><h1 id="t-judiciario" class="titulo-pagina">Judiciário</h1>'
    + `<p class="lide">${esc(lide)}</p>${Object.entries(ORGAOS_J).map(bloco).join("")}</section>`;
  paginas.push(["judiciario", pagina("judiciario", "Judiciário: quanto recebem os ministros dos tribunais superiores, o CNJ e a PGR | Contas do Poder", lide, corpo, { extras: ["/dados/judiciario.json"] })]);
}

// ------------------------------------------------------------------ dados abertos (/dados-abertos)
// Os dados não dependem deste site: as cópias públicas (COPIAS) e cada arquivo de site/dados/, com o tamanho e a
// impressão digital (SHA-256), para qualquer cópia poder ser conferida. O manifesto (publicar/dados/manifesto.json) é
// o que o app.js lê para desenhar a página; aqui, a mesma página pronta, para quem não roda JavaScript.
// Uma cópia nova (Zenodo, Software Heritage, um espelho do repositório): uma linha em COPIAS.
const COPIAS = [
  { nome: "GitHub", url: "https://github.com/jflaloux/contas-do-poder", texto: "O código do site, os robôs que coletam os dados e os próprios dados, com o histórico de cada mudança." },
  { nome: "Pacote completo (ZIP)", url: "https://github.com/jflaloux/contas-do-poder/archive/refs/heads/main.zip", texto: "Tudo o que está no GitHub num arquivo só, na versão mais recente." },
  { nome: "Zenodo (CERN), com DOI", url: "https://doi.org/10.5281/zenodo.23109646", texto: "Cópia permanente de cada versão publicada no GitHub (a primeira, de 02/10/2026), guardada pelo CERN. O DOI não muda e leva sempre à versão mais nova." },
  { nome: "Software Heritage", url: "https://archive.softwareheritage.org/browse/origin/?origin_url=https://github.com/jflaloux/contas-do-poder", texto: "Arquivo universal de código-fonte, mantido pela Inria e apoiado pela Unesco. Guarda o repositório com o histórico de cada mudança (primeira cópia em 02/10/2026); o endereço mostra a cópia mais nova." },
  { nome: "Codeberg", url: "https://codeberg.org/jflaloux/contas-do-poder", texto: "Cópia do repositório numa plataforma europeia sem fins lucrativos, fora do GitHub (a primeira, de 02/10/2026). Cada versão vai para o GitHub e para o Codeberg ao mesmo tempo." },
  { nome: "Internet Archive", url: "https://web.archive.org/web/*/contasdopoder.com/*", texto: "As páginas do site guardadas pelo Wayback Machine, com a data de cada cópia." },
];
const DESCRICAO_ARQ = {
  "dados.json": "Deputados federais, senadores, presidente, vice e ministros: o que vai para o bolso e os gastos de cada um, mês a mês.",
  "camaras.json": "Vereadores das capitais com dados abertos de cada um: salário, verba do gabinete e equipe, mês a mês.",
  "prefeituras.json": "Prefeito, vice e secretários das capitais com a folha aberta: o que cada um recebe, mês a mês.",
  "assembleias.json": "Deputados estaduais e distritais: salário, verba do gabinete e equipe, mês a mês.",
  "governadores.json": "Governadores e vices: o salário do cargo (com a lei de cada valor), quem governou desde 2023 e a folha mês a mês.",
  "municipios.json": "As 5.569 cidades: o gasto da Câmara Municipal (Siconfi), a população, o número de vereadores e o salário médio (IBGE).",
  "indice_transparencia.json": "O Índice de Transparência: a nota de cada fonte de cada estado, critério por critério, com a prova.",
  "judiciario.json": "Judiciário (tribunais superiores, CNJ e PGR), ainda fora das páginas do site.",
  "enderecos.json": "O endereço de cada página do site (e os endereços antigos, que redirecionam).",
  "correcoes.json": "Os erros do site já corrigidos: o que estava errado e o que mudou.",
  "atividade.json": "Presença no Plenário e projetos de cada deputado federal e senador desde fev/2023: X de Y, sem nota nem ranking, com a fonte (a Câmara conta por dia de sessão e o Senado por votação nominal: contas diferentes).",
  "situacao.json": "A situação de cada fonte: até que mês vão os dados, quando foram lidos pela última vez e o motivo de qualquer atraso (página Atualização dos dados).",
};
const descricaoArq = (a) => DESCRICAO_ARQ[a]
  || (/^interior\/([a-z]{2})\.json$/.test(a) ? `${ESTADOS[a.slice(9, 11).toUpperCase()] || a}: vereadores, prefeito e vice de cada cidade, pela folha que o município manda ao Tribunal de Contas, mês a mês.` : "")
  || (/^interior-cargo\/([a-z]{2})\.json$/.test(a) ? `${ESTADOS[a.slice(15, 17).toUpperCase()] || a}: ${a.startsWith("interior-cargo/rj") ? "total pago aos agentes políticos de cada Câmara" : "total pago ao cargo de vereador, prefeito e vice de cada cidade"} e quantas pessoas estavam no cargo, mês a mês, pela folha que o município manda ao Tribunal de Contas (o tribunal não publica o valor de cada pessoa).` : "")
  || (/^vereadores\/([A-Z]{2})\.json$/.test(a) ? `Vereadores eleitos em 2024 em cada cidade ${deUF(a.slice(11, 13))} (TSE).` : "");
function manifesto() {
  const arquivos = [];
  const andar = (pasta, rel) => {
    for (const e of fs.readdirSync(pasta, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      const a = path.join(pasta, e.name), r = rel ? `${rel}/${e.name}` : e.name;
      if (e.isDirectory()) andar(a, r);
      else if (e.isFile() && /\.json$/.test(e.name)) {
        const conteudo = fs.readFileSync(a);
        arquivos.push({ arquivo: r, bytes: conteudo.length, sha256: createHash("sha256").update(conteudo).digest("hex"), descricao: descricaoArq(r) });
      }
    }
  };
  andar(path.join(SITE, "dados"), "");
  return { gerado_em: new Date().toISOString().slice(0, 19), site: DOMINIO, copias: COPIAS, arquivos }; // a data desta publicação
}
const MANIFESTO = manifesto();
const tamanhoTxt = (b) => (b >= 1048576 ? `${(b / 1048576).toFixed(1).replace(".", ",")} MB` : `${Math.max(1, Math.round(b / 1024))} KB`);
{
  const lide = "Este site é uma forma de ler dados que já são públicos. Os dados, os robôs que os coletam e o código do site têm cópias públicas e verificáveis fora daqui. Qualquer pessoa pode baixar tudo, conferir com as fontes oficiais e publicar de novo. Se este endereço sair do ar, os dados continuam disponíveis.";
  const linha = (a) => `<tr><td><a href="/dados/${esc(a.arquivo)}" download>${esc(a.arquivo)}</a>${a.descricao ? `<small class="tabela-gov__obs">${esc(a.descricao)}</small>` : ""}<span class="hash">${a.sha256}</span></td><td class="num">${tamanhoTxt(a.bytes)}</td></tr>`;
  const corpo = '<section class="bloco" id="dados-abertos" aria-labelledby="t-dados"><p class="rotulo">Transparência do site</p>'
    + '<h1 id="t-dados" class="titulo-pagina">Dados abertos: baixe tudo</h1>'
    + `<p class="lide">${esc(lide)}</p><h2 class="h3">Onde estão as cópias</h2><ul class="copias">`
    + COPIAS.map((c) => `<li><a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.nome)}&nbsp;↗</a> <span>${esc(c.texto)}</span></li>`).join("")
    + `</ul><h2 class="h3">Os arquivos de dados</h2><table class="tabela-gov tabela-dados"><thead><tr><th>Arquivo e impressão digital (SHA-256)</th><th class="num">Tamanho</th></tr></thead><tbody>`
    + MANIFESTO.arquivos.map(linha).join("") + '</tbody></table><p class="nota">Até que mês vão os dados de cada fonte e quando foram lidos pela última vez: <a href="/atualizacao">atualização dos dados</a>. O que o site é, a privacidade e como pedir uma correção: <a href="/sobre">sobre e privacidade</a>.</p></section>';
  const titulo = "Dados abertos: baixe tudo | Contas do Poder";
  paginas.push(["dados-abertos", pagina("dados-abertos", titulo, lide, corpo, { extras: ["/dados/manifesto.json"] })]);
}

// ------------------------------------------------------------------ atualização dos dados (/atualizacao, de site/dados/situacao.json)
// Cada fonte do site: até que mês vão os dados e a situação da última leitura. A frase de cada situação vem pronta do
// arquivo (feito pelo robô no fim de cada rodada). Mesma página do app.js (secAtualizacao), para quem não roda JavaScript.
const SIT = ler("situacao.json", null);
if (SIT && (SIT.fontes || []).length) {
  const sit = SIT.situacoes || {}, fontes = SIT.fontes;
  const mes = (m) => `${MESES[(m % 100) - 1]}/${Math.floor(m / 100)}`;
  const conta = {};
  fontes.forEach((f) => { conta[f.situacao] = (conta[f.situacao] || 0) + 1; });
  const quando = SIT.gerado_em ? dataBR(String(SIT.gerado_em).slice(0, 10)) : "";
  const fechado = SIT.ultimo_mes_fechado ? mes(SIT.ultimo_mes_fechado) : "";
  // a frase pronta começa, às vezes, com o próprio rótulo ("Atraso da própria fonte: ..."): ao lado do rótulo, só o motivo
  const motivo = (f) => { const r = `${sit[f.situacao] || ""}: `, t = f.texto || ""; const m = t.startsWith(r) ? t.slice(r.length) : t; return m.charAt(0).toUpperCase() + m.slice(1); };
  const linha = (f) => `<tr><td><a href="${esc(f.url)}" target="_blank" rel="noopener">${esc(f.nome)}&nbsp;↗</a>`
    + (f.via ? `<small class="tabela-gov__obs">Dados pelo ${esc(f.via)}${f.via === "DadosJusBr" ? " (CC BY 4.0)" : ""}</small>` : "") + "</td>"
    + `<td data-rotulo="Dados até">${f.ultimo_mes ? mes(f.ultimo_mes) : "—"}</td>`
    + `<td data-rotulo="Última coleta">${f.ultima_coleta ? dataBR(f.ultima_coleta) : "—"}</td>`
    + `<td data-rotulo="Situação"><span class="${f.situacao === "em_dia" ? "etiqueta" : f.situacao === "congelada" ? "etiqueta etiqueta--fora" : "etiqueta etiqueta--estimativa"}">${esc(sit[f.situacao] || f.situacao)}</span>`
    + (f.situacao !== "em_dia" && f.texto ? `<small class="tabela-gov__obs">${esc(motivo(f))}</small>` : "") + "</td></tr>";
  const tabela = (nome, lista) => `<table class="tabela-atualizacao"><caption class="visualmente-oculto">${esc(nome)}</caption>`
    + "<thead><tr><th>Fonte</th><th>Dados até</th><th>Última coleta</th><th>Situação</th></tr></thead>"
    + `<tbody>${lista.map(linha).join("")}</tbody></table>`;
  const fora = fontes.filter((f) => f.situacao !== "em_dia");
  const lide = "Cada órgão publica os dados no seu ritmo. Aqui está, fonte por fonte, até que mês vão os números do site e quando foram lidos pela última vez.";
  const corpo = '<section class="bloco" id="atualizacao" aria-labelledby="t-atualizacao"><p class="rotulo">Transparência do site</p>'
    + '<h1 id="t-atualizacao" class="titulo-pagina">Atualização dos dados</h1>'
    + `<p class="lide">${esc(lide)}</p>`
    + '<div class="estatisticas">' + Object.keys(sit).filter((s) => conta[s]).map((s) =>
      `<div class="estatistica"><span class="rotulo">${esc(sit[s])}</span><span class="estatistica__valor">${conta[s]}</span><span class="estatistica__comp">${conta[s] === 1 ? "fonte" : "fontes"}</span></div>`).join("") + "</div>"
    + `<p class="discreto pequeno">${[quando ? `Lista refeita em ${quando}.` : "", fechado ? `O último mês fechado é ${fechado}.` : ""].filter(Boolean).join(" ")}</p>`
    + (fora.length ? `<h2 class="h3">Fontes que não estão em dia</h2><p class="discreto">Cada uma também aparece no grupo dela, mais abaixo.</p>${tabela("Fontes que não estão em dia", fora)}` : "")
    + (SIT.grupos || []).map((g) => {
      const lista = fontes.filter((f) => f.grupo === g.id);
      return lista.length ? `<h2 class="h3">${esc(g.nome)} (${lista.length})</h2>${tabela(g.nome, lista)}` : "";
    }).join("")
    + '<h2 class="h3">Como ler esta página</h2><ul class="lista">'
    + "<li><strong>Dados até: </strong>o último mês com dados no site.</li>"
    + "<li><strong>Última coleta: </strong>o dia da última leitura da fonte que deu certo. O traço (—) quer dizer que ainda não há registro dessa leitura.</li>"
    + `<li><strong>${esc(sit.em_dia || "Em dia")}: </strong>os dados vão até menos de 3 meses antes do último mês fechado${fechado ? ` (${fechado})` : ""}. Várias fontes publicam cada mês com 1 ou 2 meses de atraso, e isso conta como em dia.</li>`
    + `<li><strong>${esc(sit.atraso_fonte || "Atraso da própria fonte")}: </strong>o órgão publica com atraso ou deixou de mostrar o dado; o motivo está ao lado.</li>`
    + `<li><strong>${esc(sit.congelada || "Congelada")}: </strong>a fonte parou de publicar o que o site mostra; o site fica com o último dado e a coleta tenta de novo a cada três meses.</li>`
    + `<li><strong>${esc(sit.atrasada || "Atrasada")}: </strong>os dados vão até 3 meses ou mais antes do último mês fechado, sem motivo conhecido.</li>`
    + `<li><strong>${esc(sit.falhou || "A coleta falhou")}: </strong>a última leitura da fonte não deu certo; o site mostra os últimos dados obtidos.</li></ul>`
    + '<p class="nota">Os robôs leem as fontes toda semana. Esta lista em JSON, para quem quiser conferir ou reaproveitar: <a href="/dados/situacao.json" download>situacao.json</a>. Os arquivos de dados e as cópias públicas estão em <a href="/dados-abertos">dados abertos</a>.</p></section>';
  const titulo = "Atualização dos dados: até que mês vai cada fonte | Contas do Poder";
  paginas.push(["atualizacao", pagina("atualizacao", titulo, lide, corpo, { extras: ["/dados/situacao.json"] })]);
}

// ------------------------------------------------------------------ sobre e privacidade (/sobre, de site/sobre.json)
// O texto fica em site/sobre.json (o app.js lê o mesmo arquivo): aqui, a página pronta em HTML. Dentro do texto só há
// [texto](endereço), para links.
{
  let SB = null;
  try { SB = JSON.parse(fs.readFileSync(path.join(SITE, "sobre.json"), "utf8")); } catch { /* sem a página */ }
  if (SB && (SB.blocos || []).length) {
    const comLinks = (txt) => esc(txt).replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_, t, u) => (/^https?:/.test(u)
      ? `<a href="${u}" target="_blank" rel="noopener">${t}&nbsp;↗</a>` : `<a href="${u}">${t}</a>`));
    const corpo = '<section class="bloco" id="sobre" aria-labelledby="t-sobre"><p class="rotulo">Transparência do site</p>'
      + `<h1 id="t-sobre" class="titulo-pagina">${esc(SB.titulo)}</h1><p class="lide">${esc(SB.lide)}</p>`
      + SB.blocos.map((b) => `<h2 class="h3" id="${esc(b.id)}">${esc(b.h)}</h2>` + (b.c || []).map((x) => (x.ul
        ? `<ul class="lista">${x.ul.map((li) => `<li>${comLinks(li)}</li>`).join("")}</ul>` : `<p>${comLinks(x.p)}</p>`)).join("")).join("")
      + (SB.atualizado ? `<p class="nota">Atualizado em ${esc(SB.atualizado)}.</p>` : "") + "</section>";
    paginas.push(["sobre", pagina("sobre", "Sobre e privacidade | Contas do Poder", SB.lide, corpo, { carregando: false })]);
  }
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
for (const [arq, dados] of [["dados.json", D], ["camaras.json", CAM], ["assembleias.json", ASS]]) {
  if (!dados || !dados.p || !dados.p.length) continue;
  const tipos = (dados.meta && dados.meta.tipos) || [];
  // dados.json fica com a lista de tipos (o app junta as outras a ela); nas câmaras e nas Assembleias, ela só serve ao
  // detalhe, que vai com os nomes no arquivo de cada pessoa
  const metaLeve = arq === "dados.json" ? dados.meta : Object.fromEntries(Object.entries(dados.meta || {}).filter(([k]) => k !== "tipos"));
  fs.writeFileSync(path.join(SAIDA, "dados", "indice", arq), JSON.stringify({ ...dados, meta: metaLeve, p: dados.p.map(({ t, dt, ...resto }) => resto) }));
  for (const p of dados.p) {
    if (!p.t) continue;
    fs.writeFileSync(path.join(SAIDA, "dados", "pessoa", `${p.id}.json`), JSON.stringify({ t: p.t, dt: comNomes(p.dt, tipos) }));
    nPessoa++;
  }
}
// governadores e vices (ver pessoasGovernadores): a lista sem o mês a mês, e o arquivo de cada um
// Judiciário: a lista sem o mês a mês (que fica em dados/judiciario.json), com o último mês de cada um (u)
if (judiciario.length) {
  fs.writeFileSync(path.join(SAIDA, "dados", "indice", "judiciario.json"), JSON.stringify({
    // sem a lista dos nomes das parcelas e sem o link de cada mês (só servem ao detalhe, no arquivo inteiro)
    meta: { ...Object.fromEntries(Object.entries(JUD.meta).filter(([k]) => k !== "tipos")),
      orgaos: Object.fromEntries(Object.entries(ORGAOS_J).map(([s, o]) => [s, Object.fromEntries(Object.entries(o).filter(([k]) => k !== "fonte_mes"))])) },
    p: JUD.p.map(({ t, tc, ti, nm, dt, ...resto }) => { const u = (t || []).filter((x) => x[1]).pop(); return { ...resto, ...(u ? { u: [u[0], u[1]] } : {}) }; }),
  }));
}
if (governadores.length) {
  fs.writeFileSync(path.join(SAIDA, "dados", "indice", "governadores-pessoas.json"), JSON.stringify({
    meta: { inicio: Math.min(...governadores.map((p) => p.ini)), ultimo_mes: Math.max(...governadores.map((p) => p.um)), categorias: CATS_G },
    // quem não tem nenhum mês (como quem não aparece na folha) leva o t vazio: o app não procura o arquivo dele
    p: governadores.map(({ t, ...resto }) => (t.length ? resto : { ...resto, t })),
  }));
  for (const p of governadores) {
    if (!p.t.length) continue;
    fs.writeFileSync(path.join(SAIDA, "dados", "pessoa", `${p.id}.json`), JSON.stringify({ t: p.t, dt: {} }));
    nPessoa++;
  }
}
fs.writeFileSync(path.join(SAIDA, "dados", "manifesto.json"), JSON.stringify(MANIFESTO, null, 1));
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
console.log(`publicar/: ${paginas.length} páginas prontas (${pessoas.filter((p) => END.p[p.id] || p.k === "a").length} políticos, ${GOV.e.length} estados, ${vistos.size} cidades), sitemap com ${urls.length} endereços, ${redir.length} redirecionamentos, ${nPessoa} arquivos por pessoa`);

// ------------------------------------------------------------------ limites do Cloudflare Pages
// O Pages recusa a publicação com mais de 20.000 arquivos (plano Free; 100.000 nos pagos), mais de 2.000
// redirecionamentos no _redirects ou um arquivo de mais de 25 MiB (developers.cloudflare.com/pages/platform/limits/).
// Melhor o build falhar aqui, dizendo onde está o volume, do que o Cloudflare recusar a publicação sem explicar (o site
// no ar continua o anterior). Aviso a partir de 90% de cada limite. Em outro plano: LIMITE_ARQUIVOS=100000 nas
// variáveis do projeto no Cloudflare.
{
  const LIMITE = { arquivos: Number(process.env.LIMITE_ARQUIVOS) || 20000, redir: 2000, tamanho: 25 * 1024 * 1024 };
  const porPasta = new Map();
  let total = 0, maior = ["", 0];
  const andar = (pasta, rel) => {
    for (const e of fs.readdirSync(pasta, { withFileTypes: true })) {
      const a = path.join(pasta, e.name), r = rel ? `${rel}/${e.name}` : e.name;
      if (e.isDirectory()) { andar(a, r); continue; }
      total++;
      // a pasta de cima (cidade/, fotos/...); dentro de dados/, a de baixo (dados/pessoa/, dados/indice/...)
      const partes = r.split("/");
      const chave = partes.length === 1 ? "raiz" : partes[0] === "dados" && partes.length > 2 ? `dados/${partes[1]}/` : `${partes[0]}/`;
      porPasta.set(chave, (porPasta.get(chave) || 0) + 1);
      const tam = fs.statSync(a).size;
      if (tam > maior[1]) maior = [r, tam];
    }
  };
  andar(SAIDA, "");
  const mil = (n) => n.toLocaleString("pt-BR");
  // as pastas grandes, uma a uma; as pequenas (como /nome/ministro, de quem tem dois cargos), somadas
  const ordem = [...porPasta].sort((a, b) => b[1] - a[1]), grandes = ordem.filter(([, n]) => n >= 20), pequenas = ordem.filter(([, n]) => n < 20);
  const pastas = [...grandes.map(([p, n]) => `${p} ${mil(n)}`),
    ...(pequenas.length ? [`outras ${pequenas.length} pastas ${mil(pequenas.reduce((a, [, n]) => a + n, 0))}`] : [])].join(", ");
  console.log(`Cloudflare Pages: ${mil(total)} de ${mil(LIMITE.arquivos)} arquivos (${pastas}); ${mil(redir.length)} de ${mil(LIMITE.redir)} redirecionamentos; maior arquivo ${maior[0]} (${(maior[1] / 1048576).toFixed(1)} MB)`);
  const erros = [], avisos = [];
  const conferir = (n, lim, oQue) => {
    if (n > lim) erros.push(`${oQue}: ${mil(n)}, acima do limite de ${mil(lim)}`);
    else if (n >= lim * 0.9) avisos.push(`${oQue}: ${mil(n)}, perto do limite de ${mil(lim)}`);
  };
  conferir(total, LIMITE.arquivos, "arquivos em publicar/");
  conferir(redir.length, LIMITE.redir, "linhas no _redirects");
  conferir(maior[1], LIMITE.tamanho, `tamanho de ${maior[0]} (bytes)`);
  for (const a of avisos) console.warn(`AVISO: ${a}`);
  if (erros.length) {
    for (const e of erros) console.error(`ERRO: ${e}`);
    console.error("O Cloudflare Pages recusaria esta publicação. Veja a contagem por pasta acima.");
    process.exit(1);
  }
}
