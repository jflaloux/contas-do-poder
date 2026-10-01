/* Contas do Poder — protótipo. Um projeto Contas do Brasil.
   Site estático: lê dados/dados.json (gerado por `python3 coletar.py site`) e monta a página no navegador.
   Endereços: #dep-123 ou #sen-456 escolhem o parlamentar; #dep-123~2024 escolhe também o período. */
"use strict";
(() => {
  // ================================================================== utilidades
  const $ = (sel, raiz = document) => raiz.querySelector(sel);
  const SVG = "http://www.w3.org/2000/svg";
  function h(tag, attrs, ...filhos) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") e.className = v;
      else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
      else if (v === true) e.setAttribute(k, "");
      else e.setAttribute(k, v);
    }
    for (const f of filhos.flat(Infinity)) {
      if (f === null || f === undefined || f === false) continue;
      e.append(f instanceof Node ? f : document.createTextNode(String(f)));
    }
    return e;
  }
  // acrescenta filhos ignorando vazios e achatando listas
  function add(el, ...filhos) {
    for (const f of filhos.flat(Infinity)) if (f !== null && f !== undefined && f !== false) el.append(f);
    return el;
  }
  function s(tag, attrs) {
    const e = document.createElementNS(SVG, tag);
    for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, v);
    return e;
  }
  const fmtBRL = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
  const reais = (v) => fmtBRL.format(Math.round(v)).replace(/ /g, " ");
  const num = (v, casas = 0) => v.toLocaleString("pt-BR", { maximumFractionDigits: casas, minimumFractionDigits: casas });
  function compacto(v) {
    const a = Math.abs(v);
    if (a >= 1e9) return `R$ ${num(v / 1e9, 1)} bi`;
    if (a >= 1e6) return `R$ ${num(v / 1e6, 1)} mi`;
    if (a >= 1e3) return `R$ ${num(v / 1e3, a >= 1e5 ? 0 : 1)} mil`;
    return reais(v);
  }
  const sm = (v) => (v >= 10 ? num(v, 0) : num(v, 1));
  const semAcento = (t) => (t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  // arquivo do site (foto, dados) a partir da raiz: a página pode estar em /nome ou em /nome/cargo
  const daRaiz = (u) => (u && !/^(https?:|data:|\/)/.test(u) ? `/${u}` : u);
  const slugTxt = (t) => semAcento(t).replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
  const MESES_LONGOS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];
  const ESTADOS = { AC: "Acre", AL: "Alagoas", AM: "Amazonas", AP: "Amapá", BA: "Bahia", CE: "Ceará", DF: "Distrito Federal", ES: "Espírito Santo", GO: "Goiás", MA: "Maranhão", MG: "Minas Gerais", MS: "Mato Grosso do Sul", MT: "Mato Grosso", PA: "Pará", PB: "Paraíba", PE: "Pernambuco", PI: "Piauí", PR: "Paraná", RJ: "Rio de Janeiro", RN: "Rio Grande do Norte", RO: "Rondônia", RR: "Roraima", RS: "Rio Grande do Sul", SC: "Santa Catarina", SE: "Sergipe", SP: "São Paulo", TO: "Tocantins" };
  const UFS = Object.keys(ESTADOS);
  const ORDEM_GANHA = ["salario", "decimo_terceiro", "jetons", "auxilio_moradia", "auxilios", "ajuda_de_custo", "outros_rendimentos"];
  const ORDEM_CUSTA = ["cota_parlamentar", "diarias", "outros_gastos_mandato", "viagens_oficiais", "verba_gabinete"];
  const ORDEM_EQUIPE = ["assessores_gabinete"];
  function iniciais(nome) {
    const p = nome.replace(/^(Dr|Dra|Delegad[oa]|Coronel|Capitão|Pastor[a]?|Sargento|Professor[a]?|Missionário|General|Cabo|Major|Tenente)\.?\s+/i, "").split(/\s+/);
    return ((p[0] || "")[0] + (p.length > 1 ? p[p.length - 1][0] : "")).toUpperCase();
  }
  function hashNum(t) { let x = 0; for (const c of t) x = (x * 31 + c.charCodeAt(0)) >>> 0; return x; }

  // ================================================================== estado
  const S = {
    D: null, porId: new Map(), sel: null, cidade: null, gov: null, extra: null, periodo: null, outro: null, ufLista: "", origem: null, carregado: false,
    rank: { casa: null, metrica: "custo", periodo: null, uf: "", noCargo: true, completo: false },
  };
  let observadores = [];

  // ================================================================== Google Analytics (só se o gtag estiver carregado)
  const evento = (nome, params = {}) => { try { if (typeof gtag === "function") gtag("event", nome, params); } catch (e) { /* segue sem medir */ } };
  const casaTxt = (p) => ({ d: "deputado", s: "senador", e: "governo", j: "dois cargos", v: "vereador", p: "prefeitura" })[p.k];

  // ================================================================== cidades com cada político (capitais)
  // dados/camaras.json: vereador por vereador; dados/prefeituras.json: prefeito, vice, secretários e subprefeitos
  const CAM = { cidades: {}, prefeituras: {} };
  const SP = 3550308;
  const camaraDe = (cod) => CAM.cidades[String(cod)] || null;
  const prefeituraDe = (cod) => CAM.prefeituras[String(cod)] || null;
  // cidades com vereador por vereador, por ordem alfabética (São Paulo primeiro)
  const cidadesCamara = () => Object.entries(CAM.cidades).map(([cod, c]) => ({ ...c, cod: +cod }))
    .sort((a, b) => (b.cod === SP) - (a.cod === SP) || a.n.localeCompare(b.n, "pt"));
  const cidadesPrefeitura = () => Object.entries(CAM.prefeituras).map(([cod, c]) => ({ ...c, cod: +cod }))
    .sort((a, b) => (b.cod === SP) - (a.cod === SP) || a.n.localeCompare(b.n, "pt"));
  // Grupo de comparação: "d", "s", "e", "j" ou, para vereadores e prefeituras, o tipo mais o código da cidade
  // ("v3550308"): vereador só se compara com vereador da mesma cidade.
  const grupo = (p) => (p.k === "v" || p.k === "p" ? `${p.k}${p.cid}` : p.k);
  const tipoG = (g) => (g ? g[0] : g);
  const cidG = (g) => (g && g.length > 1 ? +g.slice(1) : null);
  const infoG = (g) => (tipoG(g) === "v" ? camaraDe(cidG(g) || SP) : tipoG(g) === "p" ? prefeituraDe(cidG(g) || SP) : null);
  const cidadeDe = (p) => (p.k === "v" ? camaraDe(p.cid) : p.k === "p" ? prefeituraDe(p.cid) : null);
  // "de São Paulo", mas "do Recife" e "do Rio de Janeiro"
  const COM_ARTIGO = new Set([2611606, 3304557]);
  const deCidade = (c) => (c && COM_ARTIGO.has(+c.cod) ? `do ${c.n}` : `de ${c ? c.n : ""}`);
  const deCid = (cod) => deCidade({ n: (camaraDe(cod) || prefeituraDe(cod) || {}).n || "", cod });
  const listaE = (xs) => (xs.length <= 1 ? xs.join("") : `${xs.slice(0, -1).join(", ")} e ${xs[xs.length - 1]}`);
  // junta à lista de políticos; os tipos de gasto vêm numa lista própria, então os índices mudam
  function juntarMunicipal(D, CD, onde) {
    if (!CD || !CD.p) return;
    const desloc = D.meta.tipos.length;
    D.meta.tipos.push(...(CD.meta.tipos || []));
    Object.assign(D.meta.categorias, CD.meta.categorias || {});
    CAM[onde] = CD.meta.cidades || {};
    for (const p of CD.p) {
      for (const k of Object.keys(p.dt || {})) for (const c of Object.keys(p.dt[k])) p.dt[k][c] = p.dt[k][c].map(([i, v]) => [i + desloc, v]);
      D.p.push(p);
    }
  }

  // ================================================================== contas
  const meta = () => S.D.meta;
  const anoAtual = () => String(Math.floor(meta().ultimo_mes / 100));
  const mesAtual = () => meta().ultimo_mes % 100;
  // primeiro e último mês com dados de cada grupo (vereadores de SP: mandato desde jan/2025, dados até o último mês fechado)
  function limitesGrupo(g) {
    const c = infoG(g);
    return c ? [c.inicio, c.ultimo_mes] : [202302, meta().ultimo_mes];
  }
  const anosGrupo = (g) => { const [ini, fim] = limitesGrupo(g); return meta().anos.filter((a) => a >= String(Math.floor(ini / 100)) && a <= String(Math.floor(fim / 100))); };
  // g = grupo ("d", "s", "e", "j", "v"); sem g, vale o de quem está escolhido na página
  function nomePeriodo(k, curto, g) {
    if (g === undefined) { const q = S.sel && S.porId.get(S.sel); g = q ? grupo(q) : null; }
    const [ini, fim] = limitesGrupo(g);
    const aIni = String(Math.floor(ini / 100)), mIni = ini % 100, aFim = String(Math.floor(fim / 100)), mFim = fim % 100;
    if (k === "leg") return curto ? "Mandato todo" : `de ${MESES[mIni - 1]}/${aIni} a ${MESES[mFim - 1]}/${aFim}`;
    if (k === aFim) return curto ? `${k} (até ${MESES[mFim - 1]})` : `em ${k} (até ${MESES[mFim - 1]})`;
    if (k === aIni && mIni > 1) return curto ? k : `em ${k} (desde ${MESES_LONGOS[mIni - 1]})`;
    return curto ? k : `em ${k}`;
  }
  const periodos = (p) => [...meta().anos.filter((a) => p.per[a] && p.per[a].m > 0), "leg"];
  // Resumo de um período. "Custo total" = o que vai para o bolso (ganha) + os gastos do mandato (custa).
  // A equipe do gabinete (dinheiro que vai para outras pessoas) fica separada.
  function resumo(p, k) {
    const r = p && p.per[k];
    if (!r || !r.m) return null;
    const gm = r.mg ? r.g / r.mg : 0, cm = r.mc ? r.c / r.mc : 0, em = r.me ? r.e / r.me : 0;
    return {
      m: r.m, mg: r.mg, mc: r.mc, me: r.me, g: r.g, c: r.c, e: r.e, cats: r.cats,
      gm, cm, em, tm: gm + cm,
      pessoas: r.mp ? r.pm / r.mp : 0, pessoasHoje: r.pu, porPessoa: r.pm ? (r.ep ?? r.e) / r.pm : 0,
    };
  }
  function porMes(r, cat) {
    const div = ORDEM_GANHA.includes(cat) ? r.mg : ORDEM_EQUIPE.includes(cat) ? r.me : r.mc;
    return div ? (r.cats[cat] || 0) / div : 0;
  }
  // parte (%) de quem trabalha no Brasil que ganha menos que x salários mínimos por mês (PNAD Contínua do IBGE, em
  // meta().renda.grade: pares [x, %]). Interpola em linha reta entre os pontos, o que dá um valor um pouco menor que o real
  // (a curva é côncava); arredonda para baixo e para em 99,9%, porque a pesquisa capta mal as rendas mais altas.
  function acimaDeQuemTrabalha(x) {
    const R = meta().renda, g = R && R.grade;
    if (!g || !(x > 0)) return null;
    let v = g[g.length - 1][1];
    if (x <= g[0][0]) v = (g[0][1] * x) / g[0][0];
    else for (let i = 1; i < g.length; i++) if (x <= g[i][0]) { const [x0, y0] = g[i - 1], [x1, y1] = g[i]; v = y0 + ((y1 - y0) * (x - x0)) / (x1 - x0); break; }
    return Math.min(99.9, Math.floor(v * 10) / 10);
  }
  const pctPop = (v) => `${num(v, v >= 99 || v % 1 ? 1 : 0)}%`;
  const TXT_POP = "dos brasileiros que trabalham";
  const frasePop = (xsm, antes) => { const v = acimaDeQuemTrabalha(xsm); return v === null ? "" : `${antes}${pctPop(v)} ${TXT_POP}`; };
  function estatisticaPop(xsm, depois) {
    const v = acimaDeQuemTrabalha(xsm);
    return v === null ? null : estatistica("Ganha mais que", pctPop(v), h("span", null, `${TXT_POP}${depois ? `, ${depois}` : ""} `, h("a", { href: "#entenda", class: "pequeno", onclick: (ev) => { ev.preventDefault(); evento("como_renda"); const d = document.getElementById("entenda-renda"); if (d) { d.open = true; d.scrollIntoView({ block: "center" }); } } }, "(como?)")));
  }
  // em salários mínimos de cada ano (o salário mínimo muda todo ano)
  function emSalariosMinimos(p, k, campo) {
    const anos = k === "leg" ? meta().anos : [k];
    const um = (chave, meses) => {
      let soma = 0, n = 0;
      for (const a of anos) { const r = p.per[a]; if (!r || !r[meses]) continue; soma += r[chave] / meta().salario_minimo[a]; n += r[meses]; }
      return n ? soma / n : 0;
    };
    if (campo === "g") return um("g", "mg");
    if (campo === "c") return um("c", "mc");
    if (campo === "e") return um("e", "me");
    return um("g", "mg") + um("c", "mc"); // custo dele
  }
  function periodoPadrao(p) {
    if (p.per["2025"] && p.per["2025"].m >= 1) return "2025";
    const anos = periodos(p).filter((k) => k !== "leg");
    return anos.length ? anos[anos.length - 1] : "leg";
  }
  const nomeCat = (k) => (meta().categorias[k] || { nome: k }).nome;
  const plural = (g) => {
    const t = tipoG(g), c = infoG(g);
    if (t === "v") return `vereadores ${deCid(cidG(g) || SP)}`;
    if (t === "p") return `integrantes da Prefeitura ${deCid(cidG(g) || SP)}`;
    return { d: "deputados", s: "senadores", e: "ministros" }[g];
  };
  // governo federal: "cargo" em vez de "mandato", viagens em vez de cota
  const gastosNome = (p) => ({ e: "Gastos do cargo", j: "Gastos dos cargos", p: "Gastos do cargo" })[p.k] || "Gastos do mandato";
  const gastosDetalhe = (p) => ({ e: "viagens oficiais", j: "cota, viagens e outros", v: "verba do gabinete", p: "não publicados por pessoa" })[p.k] || "cota parlamentar e outros";
  const fonteDados = (p) => (p.k === "v" ? `da ${(cidadeDe(p) || {}).casa || "Câmara Municipal"}` : p.k === "p" ? `da Prefeitura ${deCid(p.cid)}`
    : { e: "do Portal da Transparência", j: "do Congresso e do Portal da Transparência" }[p.k] || "da Câmara e do Senado");
  // Prefeitura: nome curto do cargo ("Educação", "Subprefeitura Lapa", "Prefeito")
  const pastaCurtaP = (q) => ({ pr: q.g.startsWith("Prefeita") ? "Prefeita" : "Prefeito", vp: q.g.startsWith("Vice-prefeita") ? "Vice-prefeita" : "Vice-prefeito" })[q.tp]
    || (q.tp === "sb" ? `Subprefeitura ${q.pa}` : /^Secretaria \(/.test(q.pa || "") ? (q.pa || "").replace(/^Secretaria \((.*)\)$/, "$1")
      : `${q.lot ? "lotação: " : ""}${(q.pa || "").replace(/^Secretaria (Municipal |Especial |Mun )?(d[aoe]s? |de )?/, "")}`);
  // "tudo junto" (dois cargos): a casa do cargo no Congresso, para os avisos de deputado/senador
  const casaBase = (p) => (p.k === "j" ? (S.porId.get(p.cg[1].id) || {}).k : p.k);
  const fmtMes = (m) => (m ? `${MESES[(m % 100) - 1]}/${Math.floor(m / 100)}` : "");
  const cargoNoMes = (p, aaaamm) => { const f = (p.tr || []).find(([a, b]) => aaaamm >= a && aaaamm <= b); return f ? f[2] : null; };
  const nomeRel = (id) => { const q = S.porId.get(id); return q ? q.g.toLowerCase() : ""; };
  function mediana(xs) {
    const a = xs.filter((x) => x !== null && !isNaN(x)).sort((x, y) => x - y);
    if (!a.length) return null;
    const m = Math.floor(a.length / 2);
    return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2;
  }
  const cacheMed = new Map();
  function colegas(casa, k) {
    if (casa === "j") return { lista: [], n: 0, gm: null, cm: null, tm: null, em: null, pessoas: null, porPessoa: null, cat: {} };
    const chave = casa + k;
    if (cacheMed.has(chave)) return cacheMed.get(chave);
    const lista = S.D.p.filter((p) => grupo(p) === casa && (casa !== "e" || p.tp === "mi") && !p.ced).map((p) => ({ p, r: resumo(p, k) })).filter((x) => x.r && x.r.m >= 3);
    const rs = lista.map((x) => x.r);
    const comEquipe = rs.filter((r) => r.me > 0);
    const out = {
      lista, n: rs.length, gm: mediana(rs.map((r) => r.gm)), cm: mediana(rs.map((r) => r.cm)), tm: mediana(rs.map((r) => r.tm)),
      em: mediana(comEquipe.map((r) => r.em)), pessoas: mediana(comEquipe.filter((r) => r.pessoas).map((r) => r.pessoas)),
      porPessoa: mediana(comEquipe.filter((r) => r.porPessoa).map((r) => r.porPessoa)), cat: {},
    };
    for (const c of [...ORDEM_GANHA, ...ORDEM_CUSTA, ...ORDEM_EQUIPE]) out.cat[c] = mediana(rs.map((r) => porMes(r, c)));
    cacheMed.set(chave, out);
    return out;
  }
  // "Custa menos que 57% dos deputados" ou "Custa mais que 57%"; no topo e no fim, "o maior" / "o menor". Sem cor de
  // bom/ruim: a frase e a régua mostram onde a pessoa fica, e quem lê tira as conclusões
  const acimaDaMediana = (pos) => pos.pctMais < 50;
  // metade ou mais dos colegas com exatamente o mesmo valor (por exemplo, quando só entra o subsídio, igual para todos):
  // "mais que X%" enganaria, porque o lugar no ranking vira sorteio entre os empatados
  const empatado = (pos) => pos.n > 2 && pos.iguais >= (pos.n - 1) / 2;
  const fraseposicao = (p, pos) => {
    const g = plural(grupo(p)), verbo = p.k === "p" ? "Recebe" : "Custa";
    if (empatado(pos)) return `${verbo} o mesmo que ${pos.iguais} dos outros ${pos.n - 1} ${g}`;
    if (pos.pos === 1) return p.k === "p" ? `É quem mais recebe entre os ${g}` : `É o maior custo entre os ${g}`;
    if (pos.pos === pos.n) return p.k === "p" ? `É quem menos recebe entre os ${g}` : `É o menor custo entre os ${g}`;
    return acimaDaMediana(pos) ? `${verbo} mais que ${pos.pct}% dos ${g}` : `${verbo} menos que ${pos.pctMais}% dos ${g}`;
  };
  // faixa dos colegas (em quartos) e a régua com o lugar da pessoa, do que menos custa ao que mais custa
  function blocoPosicao(p, k, pos) {
    const igual = empatado(pos);
    // no empate, a marca fica no meio do grupo dos empatados
    const lugar = pos.n > 1 ? (1 - (pos.pos - 1 + (igual ? pos.iguais / 2 : 0)) / (pos.n - 1)) * 100 : 50;
    const quarto = Math.min(3, Math.floor(lugar / 25));
    const verbo = p.k === "p" ? ["menos recebem", "mais recebem"] : ["menos custam", "mais custam"];
    const faixa = [`entre os 25% que ${verbo[0]}`, "abaixo da mediana", "acima da mediana", `entre os 25% que ${verbo[1]}`][quarto];
    return h("div", { class: "destaque destaque--posicao" },
      h("p", { style: "margin:0" }, igual ? `${fraseposicao(p, pos)} ${nomePeriodo(k, false)}.` : `${fraseposicao(p, pos)} ${nomePeriodo(k, false)} (${pos.pos}º de ${pos.n}): ${faixa}.`),
      h("div", { class: "regua", role: "img", "aria-label": `Posição entre os ${plural(grupo(p))}: ${faixa}` },
        h("div", { class: "regua__trilho" }, [0, 1, 2, 3].map((i) => h("span", { class: `regua__quarto${i === quarto ? " regua__quarto--eu" : ""}` })),
          h("span", { class: "regua__marca", style: `left:${lugar.toFixed(1)}%` })),
        h("div", { class: "regua__legenda" }, h("span", null, `← ${verbo[0]}`), h("span", null, "mediana"), h("span", null, `${verbo[1]} →`))));
  }
  // grupo pequeno (menos de 5 com dados, como a Prefeitura do Rio, com só o prefeito e o vice): sem mediana nem
  // posição, porque "1º de 2: entre os 25% que mais recebem" não diz nada
  const POUCOS = 5;
  function colegasDe(p, k) {
    const C = p.ced ? null : colegas(grupo(p), k);
    return C && C.n >= POUCOS ? C : { cat: {}, tm: null, n: C ? C.n : 0 };
  }
  function posicao(p, k) {
    const C = colegas(grupo(p), k);
    const eu = C.lista.find((x) => x.p.id === p.id);
    if (!eu || C.n < POUCOS) return null;
    const acima = C.lista.filter((x) => x.r.tm > eu.r.tm).length;
    const abaixo = C.lista.filter((x) => x.r.tm < eu.r.tm).length;
    // arredonda para baixo: o 3º de 555 "custa mais que 99%", nunca "mais que 100%"
    const iguais = Math.max(0, C.n - 1 - acima - abaixo);
    return { pos: acima + 1, n: C.n, pct: Math.floor((abaixo / Math.max(1, C.n - 1)) * 100), pctMais: Math.floor((acima / Math.max(1, C.n - 1)) * 100), iguais };
  }

  // ================================================================== peças
  function avatar(p, tam) {
    const d = h("span", { class: "avatar" + (tam ? ` avatar--${tam}` : ""), "aria-hidden": "true" }, iniciais(p.n));
    if (p.f) {
      const img = h("img", { src: daRaiz(p.f), alt: "", loading: "lazy", referrerpolicy: "no-referrer" });
      img.addEventListener("error", () => img.remove());
      d.append(img);
    }
    return d;
  }
  const partidoUF = (p) => (p.k === "e" ? (p.pt ? `${p.pt} · governo federal` : "Governo federal")
    : p.k === "v" ? `${p.pt || "sem partido"} · ${(cidadeDe(p) || {}).n || "vereador"}` : p.k === "p" ? p.pt || `Prefeitura ${deCid(p.cid)}` : `${p.pt || "sem partido"}-${p.uf}`);
  const etiquetaCargo = (p) => (p.x ? h("span", { class: "etiqueta" }, "No cargo") : h("span", { class: "etiqueta etiqueta--fora" }, "Fora do cargo hoje"));
  // lista de pessoas em linhas (nome em cima, cargo embaixo), em colunas no computador: não quebra como as pílulas
  const pessoaLinha = (q, sub, href, aoClicar) => h("a", { class: "pessoa-linha", href, onclick: aoClicar },
    avatar(q, "p"), h("span", { class: "pessoa-linha__texto" }, h("span", { class: "pessoa-linha__nome" }, q.n), sub ? h("small", null, sub) : null));
  const listaPessoas = (itens) => h("div", { class: "pessoas-lista" }, itens);
  // lista longa que começa fechada ("Ver os 38 ministros"); abrir é medido como abrir_lista
  const listaFechada = (titulo, nome, conteudo) => h("details", { class: "pessoas-mais", ontoggle: (e) => { if (e.target.open) evento("abrir_lista", { lista: nome }); } },
    h("summary", null, titulo), conteudo);
  function pilulas(opcoes, atual, aoEscolher, rotulo, classe) {
    return h("div", { class: classe || "pilulas", role: "group", "aria-label": rotulo },
      opcoes.map(([v, t]) => h("button", { type: "button", class: "pilula", "aria-pressed": String(v === atual), onclick: () => aoEscolher(v) }, t)));
  }
  // diferença para a mediana dos colegas: seta e tom neutro (a cor não diz se é bom ou ruim)
  function seloComp(v, med, texto) {
    if (!med || !v) return null;
    const dif = (v - med) / med;
    const pct = Math.round(dif * 100);
    const cls = pct > 2 ? "acima" : pct < -2 ? "abaixo" : "igual";
    const txt = cls === "acima" ? `▲ ${pct}%` : cls === "abaixo" ? `▼ ${-pct}%` : `${pct > 0 ? "+" : pct < 0 ? "−" : ""}${Math.abs(pct)}%`;
    const fala = cls === "acima" ? `${pct}% acima da` : cls === "abaixo" ? `${-pct}% abaixo da` : "praticamente igual à";
    return h("span", { class: "item__detalhe" }, h("span", { class: `selo-comp selo-comp--${cls}`, "aria-hidden": "true" }, txt),
      h("span", { "aria-hidden": "true" }, `${texto} ${reais(med)}`),
      h("span", { class: "visualmente-oculto" }, `${fala} ${texto.replace(/^vs\.\s*/, "")}, ${reais(med)}`));
  }
  // Rosa ("aviso") só para dado que falta ou que a fonte não publica; explicação e fato vão na caixa neutra ("caixa-nota").
  // Os textos das câmaras vêm dos dados: é aviso quando dizem que algo não aparece ou não entra.
  const avisoOuNota = (texto) => (/não (aparece|aparecem|entra|entram|abre|é publicad|são publicad)/i.test(texto || "") ? "aviso" : "caixa-nota");
  // tabela larga que rola para o lado: alcançável pelo teclado, com nome para o leitor de tela
  const rolagem = (rotulo, ...filhos) => h("div", { class: "rolagem", tabindex: "0", role: "region", "aria-label": rotulo }, ...filhos);
  function barra(rotulo, valorTexto, fracao, classe) {
    return h("div", { class: "barra" },
      h("div", { class: "barra__topo" }, h("span", null, rotulo), h("span", { class: "num" }, valorTexto)),
      h("div", { class: "barra__trilho" }, h("span", { class: `barra__fill ${classe || ""}`, style: `width:${Math.max(0.5, Math.min(100, fracao * 100))}%` })));
  }
  function estatistica(rotulo, valor, comp) {
    return h("div", { class: "estatistica" }, h("span", { class: "rotulo" }, rotulo), h("span", { class: "estatistica__valor" }, valor), comp ? h("span", { class: "estatistica__comp" }, comp) : null);
  }
  function seletorUF(id, atual, aoMudar, primeiro) {
    return h("select", { id, onchange: (e) => aoMudar(e.target.value) },
      h("option", { value: "", selected: !atual }, primeiro || "Todos os estados"),
      UFS.map((u) => h("option", { value: u, selected: u === atual }, `${ESTADOS[u]} (${u})`)));
  }
  // rola até a seção. Dentro da mesma página, com animação; ao abrir outra página (político, cidade, estado), de uma
  // vez: a animação longa (de lá de baixo da página inicial até o topo) era interrompida por um resto de rolagem do
  // trackpad ou pelo conteúdo que ainda carregava, e a pessoa ficava no pé da página nova
  const irPara = (id, deUmaVez) => {
    const e = document.getElementById(id);
    if (!e) return;
    if (!deUmaVez) { e.scrollIntoView({ block: "start" }); return; }
    const raiz = document.documentElement, antes = raiz.style.scrollBehavior;
    raiz.style.scrollBehavior = "auto";
    e.scrollIntoView({ block: "start" });
    raiz.style.scrollBehavior = antes;
  };
  const buscaTexto = (p) => p._b || (p._b = semAcento(`${p.n} ${p.nc || ""} ${p.pt || ""} ${p.uf} ${ESTADOS[p.uf] || ""} ${p.g}`));
  function encontrar(q, filtro) {
    const termos = semAcento(q).trim().split(/\s+/).filter(Boolean);
    if (!termos.length) return [];
    const achados = S.D.p.filter((p) => p.k !== "j" && (!filtro || filtro(p)) && termos.every((t) => buscaTexto(p).includes(t)));
    const ids = new Set(achados.map((p) => p.id));
    // mesma pessoa em dois cargos (ex.: deputado licenciado que é ministro): mostra só uma vez, o cargo atual
    return achados.filter((p) => {
      const o = p.rel && ids.has(p.rel) ? S.porId.get(p.rel) : null;
      return !o || (p.x && !o.x) || (!!p.x === !!o.x && (p.k === "e" || p.k === "p"));
    }).map((p) => (p.j && S.porId.get(p.j)) || p).sort((a, b) => b.x - a.x || a.n.localeCompare(b.n, "pt-BR"));
  }
  // governador pelo nome dele (ou do vice) ou pelo nome do estado
  function encontrarGov(q) {
    const termos = semAcento(q).trim().split(/\s+/).filter(Boolean);
    if (!termos.length || semAcento(q).trim().length < 3) return [];
    return GOV.e.filter((e) => { const t = semAcento(`${e.gov.n} ${e.gov.nc || ""} ${ESTADOS[e.uf]} governador governadora`); return termos.every((x) => t.includes(x)); }).slice(0, 2);
  }
  // campo de busca com lista de sugestões (teclado: setas, Enter, Esc)
  // o que as pessoas procuram e não acham: manda o termo 1,5 s depois de parar de digitar, uma vez por termo. Não manda
  // nada que pareça e-mail ou número de documento (só nomes de políticos, cidades, cargos...)
  let buscaTimer = null;
  const buscasMedidas = new Set();
  function medirBuscaVazia(valor) {
    clearTimeout(buscaTimer);
    buscaTimer = setTimeout(() => {
      const termo = semAcento(valor.trim()).toLowerCase().slice(0, 50);
      if (termo.length < 3 || buscasMedidas.has(termo) || /@|\d{3}/.test(termo)) return;
      buscasMedidas.add(termo);
      evento("busca_sem_resultado", { termo });
    }, 1500);
  }
  function ligarBusca(input, caixa, aoEscolher, filtro, comCidades, origemBusca = "busca") {
    let itens = [], ativo = -1;
    // a lista de sugestões é uma listbox (cada sugestão é uma option), para o leitor de tela
    caixa.setAttribute("role", "listbox");
    if (!caixa.hasAttribute("aria-label")) caixa.setAttribute("aria-label", "Sugestões");
    const fechar = () => { caixa.hidden = true; ativo = -1; };
    const marcar = () => [...caixa.children].forEach((b, i) => b.setAttribute("aria-selected", String(i === ativo)));
    input.addEventListener("input", () => {
      const pol = encontrar(input.value, filtro).slice(0, comCidades ? 6 : 8);
      const cid = comCidades ? encontrarCidades(input.value) : [];
      const govs = comCidades ? encontrarGov(input.value) : [];
      itens = [...govs, ...pol, ...cid];
      caixa.textContent = "";
      govs.forEach((e) => caixa.append(h("button", { type: "button", class: "sugestao", role: "option", onclick: () => { fechar(); input.value = ""; S.origem = origemBusca; navegar(urlGov(e.uf)); } },
        avatar({ n: e.gov.n, f: e.gov.f }, "p"), h("span", null, e.gov.n, h("small", null, `${tituloGov(e)} ${deUF(e.uf)}${partidoTxt(e.gov).replace(/[()]/g, "").replace(/^ /, " · ")}`)))));
      cid.forEach((c) => caixa.append(h("button", { type: "button", class: "sugestao sugestao--cidade", role: "option", onclick: () => { fechar(); input.value = ""; irParaCidade(c, origemBusca); } },
        iconeCidade(avatarCidade("p")), h("span", null, `Câmara Municipal de ${c.n} (${c.uf})`, h("small", null, `${c.nv} vereadores · ${num(c.pop, 0)} habitantes`)))));
      pol.forEach((p) => caixa.append(h("button", { type: "button", class: "sugestao", role: "option", onclick: () => { fechar(); input.value = ""; aoEscolher(p); } },
        avatar(p, "p"), h("span", null, p.n, h("small", null, `${p.g} · ${partidoUF(p)}${p.x ? "" : " · fora do cargo"}${p.rel && S.porId.get(p.rel) ? ` · também ${nomeRel(p.rel)}` : ""}`)))));
      if (input.value.trim().length >= 2 && !itens.length) {
        caixa.append(h("p", { class: "pequeno discreto", style: "padding:8px", role: "option", "aria-disabled": "true", "aria-selected": "false" }, "Ninguém encontrado. Confira a grafia."));
        medirBuscaVazia(input.value);
      }
      caixa.hidden = !caixa.children.length;
      ativo = -1;
    });
    input.addEventListener("keydown", (e) => {
      if (caixa.hidden) return;
      if (e.key === "ArrowDown") { ativo = Math.min(itens.length - 1, ativo + 1); marcar(); e.preventDefault(); }
      else if (e.key === "ArrowUp") { ativo = Math.max(0, ativo - 1); marcar(); e.preventDefault(); }
      else if (e.key === "Enter" && itens.length) {
        const botoes = [...caixa.querySelectorAll("button")];
        (botoes[Math.max(0, ativo)] || botoes[0]).click(); e.preventDefault();
      }
      else if (e.key === "Escape") fechar();
    });
    document.addEventListener("click", (e) => { if (!caixa.contains(e.target) && e.target !== input) fechar(); });
  }

  // ================================================================== gráficos
  function escala(max, n = 4) {
    const bruto = max / n;
    const pot = Math.pow(10, Math.floor(Math.log10(bruto)));
    const passo = [1, 2, 2.5, 5, 10].map((f) => f * pot).find((x) => x >= bruto) || bruto;
    const topo = Math.ceil(max / passo) * passo;
    const ticks = [];
    for (let v = 0; v <= topo + 1e-6; v += passo) ticks.push(v);
    return { ticks, topo };
  }
  // Eixo de min a max com números redondos, sem começar do zero (para pontos: a posição é que conta, não o tamanho).
  // Se todos têm o mesmo valor, volta ao eixo do zero.
  function escalaFaixa(min, max, n = 4) {
    if (!(max > min)) return { ...escala(max, n), base: 0, casas: 0 };
    const bruto = (max - min) / n;
    const pot = Math.pow(10, Math.floor(Math.log10(bruto)));
    const passo = [1, 2, 2.5, 5, 10].map((f) => f * pot).find((x) => x >= bruto) || bruto;
    // as pontas vão até a metade do passo mais próxima (41 e 103 mil: de 40 a 110 mil, com marcas em 40, 60, 80 e 100)
    const meio = passo / 2;
    const base = Math.max(min >= 0 ? 0 : -Infinity, Math.floor(min / meio) * meio), topo = Math.ceil(max / meio) * meio;
    const casas = Math.max(0, -Math.floor(Math.log10(passo) + 1e-9)) + (Math.round(passo / pot * 10) === 25 ? 1 : 0);
    const ticks = [];
    for (let v = Math.ceil(base / passo - 1e-9) * passo; v <= topo + passo * 1e-6; v += passo) ticks.push(Math.round(v * 1e6) / 1e6);
    return { ticks, topo, base, casas };
  }
  function colunaArredondada(x, y, w, alt, r) {
    if (alt <= 0) return "";
    r = Math.min(r, w / 2, alt);
    return `M${x},${y + alt}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + alt}Z`;
  }
  function dica(caixa) {
    let d = caixa.querySelector(".dica");
    if (!d) { d = h("div", { class: "dica", hidden: true, role: "status" }); caixa.append(d); }
    return d;
  }
  function posicionarDica(caixa, d, x, y) {
    const larg = caixa.clientWidth, dw = d.offsetWidth || 160;
    d.style.left = `${Math.max(4, Math.min(larg - dw - 4, x - dw / 2))}px`;
    d.style.top = `${Math.max(4, y - d.offsetHeight - 10)}px`;
  }
  function aoRedimensionar(caixa, desenhar) {
    let largura = 0;
    const ro = new ResizeObserver(() => { const w = caixa.clientWidth; if (Math.abs(w - largura) > 8) { largura = w; desenhar(); } });
    ro.observe(caixa); observadores.push(ro);
  }
  // Colunas mês a mês, empilhando as séries dadas (de baixo para cima)
  function graficoColunas(caixa, pontos, series, linhasDica, faixa) {
    const desenhar = () => {
      caixa.querySelectorAll("svg").forEach((x) => x.remove());
      const W = Math.max(260, caixa.clientWidth), H = faixa ? 250 : 240;
      const m = { t: 10, r: 4, b: faixa ? 38 : 28, l: 62 };
      const iw = W - m.l - m.r, ih = H - m.t - m.b;
      const soma = (p) => series.reduce((acc, se) => acc + (p[se.k] || 0), 0);
      const { ticks, topo } = escala(Math.max(1, ...pontos.map(soma)), 4);
      const y = (v) => m.t + ih - (v / topo) * ih;
      const svg = s("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Valores mês a mês" });
      for (const t of ticks) {
        svg.append(s("line", { class: t === 0 ? "base" : "grade", x1: m.l, x2: W - m.r, y1: y(t), y2: y(t) }));
        const tx = s("text", { x: m.l - 8, y: y(t) + 4, "text-anchor": "end" }); tx.textContent = t === 0 ? "0" : compacto(t); svg.append(tx);
      }
      const banda = iw / pontos.length, bw = Math.min(24, Math.max(2, banda * 0.64));
      const variosAnos = new Set(pontos.map((p) => Math.floor(p.aaaamm / 100))).size > 1;
      const cada = Math.max(1, Math.ceil(34 / banda));
      const d = dica(caixa);
      pontos.forEach((p, i) => {
        const cx = m.l + banda * i + banda / 2, x = cx - bw / 2;
        const g = s("g", { class: "coluna" });
        const ativos = series.filter((se) => (p[se.k] || 0) > 0);
        let base = 0;
        ativos.forEach((se, j) => {
          const v = p[se.k];
          const yTopo = y(base + v), yBase = y(base) - (j > 0 ? 2 : 0);
          const alt = yBase - yTopo;
          if (alt > 0.3) {
            if (j === ativos.length - 1) g.append(s("path", { class: se.cls, d: colunaArredondada(x, yTopo, bw, alt, 4) }));
            else g.append(s("rect", { class: se.cls, x, y: yTopo, width: bw, height: alt }));
          }
          base += v;
        });
        const fx = faixa ? faixa(p) : null;
        if (fx) svg.append(s("rect", { class: `faixa-cargo faixa-cargo--${fx}`, x: m.l + banda * i + 0.5, y: m.t + ih + 4, width: Math.max(1, banda - 1), height: 9, rx: 2 }));
        g.append(s("rect", { class: "alvo", x: m.l + banda * i, y: m.t, width: banda, height: ih }));
        const mostrar = () => {
          svg.querySelectorAll(".coluna.ativa").forEach((c) => c.classList.remove("ativa"));
          g.classList.add("ativa");
          d.hidden = false; d.textContent = "";
          const mes = p.aaaamm % 100, ano = Math.floor(p.aaaamm / 100);
          add(d, h("div", null, `${MESES[mes - 1]}/${ano}`), linhasDica(p));
          posicionarDica(caixa, d, cx + 12, y(soma(p)) + 14);
        };
        g.addEventListener("pointerenter", mostrar); g.addEventListener("pointerdown", mostrar);
        svg.append(g);
        const mes = p.aaaamm % 100, ano = Math.floor(p.aaaamm / 100);
        let rot = null;
        if (variosAnos) { if (mes === 1 || i === 0) rot = String(ano); } else if (i % cada === 0) rot = MESES[mes - 1];
        if (rot) {
          const tx = s("text", { x: variosAnos ? m.l + banda * i : cx, y: H - 8, "text-anchor": variosAnos ? "start" : "middle" });
          tx.textContent = rot; svg.append(tx);
          if (variosAnos && mes === 1) svg.append(s("line", { class: "grade", x1: m.l + banda * i, x2: m.l + banda * i, y1: m.t, y2: H - m.b + 4 }));
        }
      });
      svg.addEventListener("pointerleave", () => { d.hidden = true; svg.querySelectorAll(".coluna.ativa").forEach((c) => c.classList.remove("ativa")); });
      caixa.prepend(svg);
    };
    aoRedimensionar(caixa, desenhar); desenhar();
  }
  const linhaDica = (cor, valor, texto) => h("div", null, h("span", { class: "traco", style: `background:var(--${cor})` }), h("strong", null, valor), ` ${texto}`);
  // dica ao lado do ponteiro (não em cima do ponto)
  function dicaPerto(caixa, d, ev) {
    const rc = caixa.getBoundingClientRect();
    const x = ev.clientX - rc.left, y = ev.clientY - rc.top;
    const dw = d.offsetWidth || 160, dh = d.offsetHeight || 40;
    let left = x + 16;
    if (left + dw > caixa.clientWidth - 4) left = x - dw - 16;
    d.style.left = `${Math.max(4, left)}px`;
    d.style.top = `${Math.max(-dh / 2, y - dh / 2)}px`;
  }
  // Pontos: cada colega é um ponto na horizontal (valor); a pessoa escolhida aparece destacada.
  // pares: [{id, n, sub, v}]; clicar num ponto abre a página daquela pessoa.
  function graficoPontos(caixa, euId, pares, fmt) {
    const desenhar = () => {
      caixa.querySelectorAll("svg").forEach((x) => x.remove());
      if (!pares.length) return;
      const W = Math.max(260, caixa.clientWidth);
      const m = { t: 44, r: 14, b: 28, l: 14 };
      const iw = W - m.l - m.r;
      const vs = pares.map((p) => p.v);
      const { ticks, topo, base, casas } = escalaFaixa(Math.min(...vs), Math.max(...vs), 4);
      const x = (v) => m.l + ((v - base) / (topo - base)) * iw;
      // enxame: quem tem valores parecidos fica na mesma coluna, empilhado para cima e para baixo do meio (do menor para
      // o maior, sempre na mesma ordem); a altura do gráfico acompanha a pilha mais alta
      const raio = W < 520 ? 2.6 : 3.4, passo = raio * 2 + 1;
      const cont = new Map(), pilha = new Map();
      for (const q of [...pares].sort((a, b) => a.v - b.v || (a.id < b.id ? -1 : 1))) {
        const b = Math.round(x(q.v) / passo), n = cont.get(b) || 0;
        cont.set(b, n + 1);
        pilha.set(q.id, { cx: b * passo, k: n % 2 ? Math.ceil(n / 2) : -n / 2 });
      }
      const maxK = Math.max(1, ...[...pilha.values()].map((d) => Math.abs(d.k)));
      const ih = Math.max(W < 520 ? 120 : 100, (2 * maxK + 1) * passo + 16), H = m.t + ih + m.b, meio = m.t + ih / 2;
      const rotulo = (t) => (t === 0 ? "0" : fmt === reais ? compacto(t).replace(/,0 (mil|mi|bi)$/, " $1") : fmt === reaisC ? `R$ ${num(t, casas)}` : num(t, casas));
      const svg = s("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Onde cada um fica" });
      // rótulos do eixo: se encostam (celular estreito), tenta sem o "R$ " e, se ainda encostam, um sim, um não
      const ancora = (t) => (x(t) < m.l + 30 ? "start" : x(t) > W - m.r - 30 ? "end" : "middle");
      const cabem = (textos) => {
        let fimAnt = -Infinity;
        return ticks.every((t, i) => {
          if (textos[i] === null) return true;
          const larg = textos[i].length * 6.6, a = ancora(t); // fonte mono de 11 px
          const ini = a === "start" ? x(t) : a === "end" ? x(t) - larg : x(t) - larg / 2;
          const ok = ini >= fimAnt + 8; fimAnt = ini + larg; return ok;
        });
      };
      const cheios = ticks.map(rotulo), curtos = cheios.map((t) => t.replace(/^R\$ /, ""));
      const textos = [cheios, curtos, curtos.map((t, i) => ((ticks.length - 1 - i) % 2 ? null : t))].find(cabem) || curtos.map((t, i) => (i % 3 ? null : t));
      ticks.forEach((t, i) => {
        svg.append(s("line", { class: "grade", x1: x(t), x2: x(t), y1: m.t - 6, y2: H - m.b }));
        if (textos[i] === null) return;
        const tx = s("text", { x: x(t), y: H - 8, "text-anchor": ancora(t) });
        tx.textContent = textos[i]; svg.append(tx);
      });
      const pos = pares.map((p) => { const d = pilha.get(p.id); return { ...p, cx: d.cx, cy: meio + d.k * passo }; });
      for (const p of pos) if (p.id !== euId) svg.append(s("circle", { class: "ponto", cx: p.cx, cy: p.cy, r: raio }));
      // a mediana: linha tracejada, com o nome embaixo do nome da pessoa
      const med = mediana(vs);
      if (med !== null && pares.length > 2) {
        const mx = x(med);
        svg.append(s("line", { class: "mediana-linha", x1: mx, x2: mx, y1: 26, y2: H - m.b }));
        const tm = s("text", { x: mx + (mx > W * 0.8 ? -5 : 5), y: 36, "text-anchor": mx > W * 0.8 ? "end" : "start" }); tm.textContent = "mediana"; svg.append(tm);
      }
      const meu = pos.find((p) => p.id === euId);
      if (meu) {
        // linha do nome até o ponto e até o eixo, e um anel em volta: dá para achar a pessoa no meio dos outros
        svg.append(s("line", { class: "guia-linha", x1: meu.cx, x2: meu.cx, y1: 20, y2: meu.cy - 13 }));
        svg.append(s("circle", { class: "ponto--anel", cx: meu.cx, cy: meu.cy, r: 13 }));
        svg.append(s("circle", { class: "ponto--eu", cx: meu.cx, cy: meu.cy, r: 7.5 }));
        const tx = s("text", { class: "forte", x: meu.cx, y: 14, "text-anchor": meu.cx < W * 0.2 ? "start" : meu.cx > W * 0.8 ? "end" : "middle" });
        tx.textContent = `${meu.n}: ${fmt === reais ? compacto(meu.v) : fmt(meu.v)}`; svg.append(tx);
      }
      const destaque = s("circle", { class: "ponto--ativo", r: 5, cx: 0, cy: 0, visibility: "hidden" });
      svg.append(destaque);
      const d = dica(caixa);
      let atual = null;
      const achar = (ev) => {
        const r = svg.getBoundingClientRect();
        const px = (ev.clientX - r.left) * (W / r.width), py = (ev.clientY - r.top) * (H / r.height);
        let melhor = null, dist = Infinity;
        for (const p of pos) { const dd = (p.cx - px) ** 2 + (p.cy - py) ** 2; if (dd < dist) { dist = dd; melhor = p; } }
        return dist <= 900 ? melhor : null;
      };
      const mostrar = (ev) => {
        atual = achar(ev);
        if (!atual) { d.hidden = true; destaque.setAttribute("visibility", "hidden"); svg.style.cursor = ""; return; }
        destaque.setAttribute("cx", atual.cx); destaque.setAttribute("cy", atual.cy); destaque.setAttribute("visibility", "visible");
        svg.style.cursor = "pointer";
        d.hidden = false; d.textContent = "";
        d.append(h("div", null, h("strong", null, fmt(atual.v)), fmt === reais ? " por mês" : ""), h("div", null, `${atual.n} (${atual.sub})`));
        dicaPerto(caixa, d, ev);
      };
      svg.addEventListener("pointermove", mostrar);
      svg.addEventListener("pointerdown", mostrar);
      svg.addEventListener("click", (ev) => { const p = achar(ev); if (p && p.id !== euId) { S.origem = "grafico"; navegar(urlPessoa(p)); } });
      svg.addEventListener("pointerleave", () => { d.hidden = true; destaque.setAttribute("visibility", "hidden"); });
      caixa.prepend(svg);
    };
    aoRedimensionar(caixa, desenhar); desenhar();
  }
  // ================================================================== compartilhar
  const endereco = () => (($('meta[name="endereco-do-site"]') || {}).content || "").replace(/#.*$/, "");
  const dominio = () => endereco().replace(/^https?:\/\//, "").replace(/\/$/, "") || "contasdopoder.com";
  const pessoasTxt = (n) => `${num(n, n < 10 && n % 1 ? 1 : 0)} ${Math.round(n) === 1 ? "pessoa" : "pessoas"}`;
  // endereços das páginas: /guilherme-boulos (site/dados/enderecos.json), /cidade/sao-paulo-sp, /governador/sp. O período
  // vai em ?periodo=2025 (ou ?periodo=mandato) quando não é o padrão da pessoa.
  const origem = () => endereco().replace(/\/+$/, "");
  const END = { porId: new Map(), porCaminho: new Map(), antigos: {} };
  const caminhoDe = (p) => END.porId.get(p.id) || p.id;
  const urlPessoa = (p, k) => `/${caminhoDe(p)}${k && k !== periodoPadrao(p) ? `?periodo=${k === "leg" ? "mandato" : k}` : ""}`;
  const urlCidade = (c) => `/cidade/${slugTxt(c.n)}-${c.uf.toLowerCase()}`;
  const urlGov = (uf) => `/governador/${uf.toLowerCase()}`;
  function urlDe(id, k) {
    if (id.startsWith("gov-")) return urlGov(id.slice(4));
    if (id.startsWith("cid-")) { const c = CID.porId.get(id); return c ? urlCidade(c) : `/${id}`; }
    const p = S.porId.get(id);
    return p ? urlPessoa(p, k) : `/${id}`;
  }
  const linkDe = (p, k) => (endereco() ? `${origem()}${urlPessoa(p, k)}` : "");
  // o aviso curto da imagem, conforme o que a Câmara de cada cidade publica
  function avisoVereador(p) {
    const c = cidadeDe(p) || {};
    return [c.subsidio_folha ? "Salário pela folha de pagamento da Câmara." : "Salário igual para todos.",
      c.equipe_custo ? null : c.equipe_aviso || (p.eq ? "O custo da equipe do gabinete não é publicado." : "A equipe de cada gabinete não é publicada.")].filter(Boolean).join(" ");
  }
  function textoCompartilhar(p, k) {
    const r = resumo(p, k), pos = posicao(p, k);
    const link = linkDe(p, k);
    return [
      `*${p.n}* (${p.g}, ${partidoUF(p)}) ${nomePeriodo(k, false)}:`,
      `${p.k === "p" ? "Recebe" : "Custo total"}: *${reais(r.tm)} por mês*`,
      `• Vai para o bolso: ${reais(r.gm)} por mês (${sm(emSalariosMinimos(p, k, "g"))} salários mínimos${frasePop(emSalariosMinimos(p, k, "g"), ", mais que ")})`,
      r.cats.jetons ? `  (inclui ${reais(porMes(r, "jetons"))} por mês de jetons de conselhos)` : null,
      p.k === "p" ? `• ${gastosNome(p)}: não publicados por pessoa` : `• ${gastosNome(p)}: ${reais(r.cm)} por mês (${gastosDetalhe(p)})`,
      r.em ? `À parte, a equipe do gabinete: ${pessoasTxt(r.pessoas)}, ${reais(r.em)} por mês` : null,
      !r.em && p.k === "v" && p.eq ? `À parte, a equipe do gabinete: ${pessoasTxt(p.eq.n)} (a Câmara não publica o custo)` : null,
      pos ? fraseposicao(p, pos) : null,
      "",
      `Tudo com dados abertos oficiais ${fonteDados(p)}.`,
      `${p.k === "v" ? "Veja também os outros vereadores, os deputados e os senadores" : p.k === "p" ? "Veja também os vereadores, os deputados e os senadores" : "Veja também o seu deputado, os senadores e os ministros"}: ${link || "Contas do Poder"}`,
    ].filter((x) => x !== null).join("\n");
  }

  // ------------------------------------------------------------------ imagem para compartilhar
  // 1080×1350 (4:5): aparece inteira numa conversa do WhatsApp ou do Telegram e também serve para status e stories.
  // A foto precisa vir do próprio site (site/fotos/): foto de outro endereço "suja" o canvas e o navegador não deixa copiar.
  // Há uma imagem para cada político, cada governador e cada Câmara Municipal. As peças são as mesmas: o topo com a
  // marca, a cabeça (foto, nome e cargo), o valor grande, a régua da posição, os cartões e o rodapé com o endereço da
  // própria página (quem recebe a imagem não consegue clicar, mas consegue digitar).
  function carregarImagem(src) {
    return new Promise((ok) => { const img = new Image(); img.onload = () => ok(img); img.onerror = () => ok(null); img.src = src; });
  }
  async function esperarFontes() {
    // as fontes carregam sem travar a página (index.html): espera a folha de estilo delas, por no máximo 3 s
    const css = document.querySelector('link[href*="fonts.googleapis.com/css2"][media="print"]');
    if (css) await new Promise((ok) => { css.addEventListener("load", ok, { once: true }); setTimeout(ok, 3000); });
    try { await Promise.all(['700 64px "Barlow Condensed"', '600 60px "Barlow Condensed"', '600 30px "Barlow"', '400 24px "Barlow"', '700 24px "Barlow"'].map((f) => document.fonts.load(f))); } catch (e) { /* usa a fonte do sistema */ }
  }
  // a tela com o fundo, a faixa e a marca; devolve o contexto e as peças de desenho
  async function novaTela() {
    await esperarFontes();
    const W = 1080, H = 1350, M = 72, cv = document.createElement("canvas");
    cv.width = W; cv.height = H;
    const g = cv.getContext("2d");
    const t = {
      cv, g, W, H, M, folga: 0, blocos: 0, fixo: {},
      // as letras e as cores do site (estilo.css): Barlow Condensed nos títulos e números, Barlow no texto; a faixa escura
      // de fundo, verde-água para o bolso, âmbar para os gastos e azul-acinzentado para a equipe
      DISP: '"Barlow Condensed", "Barlow", sans-serif', BODY: '"Barlow", system-ui, sans-serif', MONO: '"Barlow Condensed", "Barlow", sans-serif',
      C: { fundo: "#0f2b3c", cartao: "#163a4f", ink: "#f1f6f8", ink2: "#c9d7e0", linha: "rgba(201,215,224,.4)", marca: "#3ee0b4", hi: "#3ee0b4", ganha: "#3ee0b4", custa: "#ffc266", equipe: "#8fb0c9", regua: "#3ee0b4" },
    };
    const C = t.C;
    t.caixa = (x, y, w, alt, raio) => { g.beginPath(); if (g.roundRect) g.roundRect(x, y, w, alt, raio); else g.rect(x, y, w, alt); };
    t.quebra = (texto, x, y, max, lh, maxLinhas) => {
      let linha = "", n = 0;
      for (const w of texto.split(" ")) {
        const tx = linha ? `${linha} ${w}` : w;
        if (g.measureText(tx).width > max && linha && n < maxLinhas - 1) { g.fillText(linha, x, y); y += lh; n++; linha = w; } else linha = tx;
      }
      g.fillText(linha, x, y); return y + lh;
    };
    t.direita = (tx, x, y) => g.fillText(tx, x - g.measureText(tx).width, y);
    // escreve um valor seguido de "/mês" menor, na mesma linha de base
    t.comMes = (valor, x, y, fonte, tamanho, cor) => {
      g.fillStyle = cor; g.font = fonte; g.fillText(valor, x, y);
      const w = g.measureText(valor).width;
      g.fillStyle = C.ink2; g.font = `500 ${tamanho}px ${t.BODY}`; g.fillText("/mês", x + w + 6, y);
      return w + 6 + g.measureText("/mês").width;
    };
    t.bolinha = (cor, x, y) => { g.fillStyle = cor; g.beginPath(); g.arc(x, y, 11, 0, 7); g.fill(); };
    t.png = () => new Promise((ok) => cv.toBlob(ok, "image/png"));
    g.fillStyle = C.fundo; g.fillRect(0, 0, W, H);
    // a marca: a rosca (bolso e gastos) e o nome em duas linhas, como no cabeçalho do site
    const lx = M + 30, ly = 84, lr = 22, volta = Math.PI * 2, ini = -Math.PI / 2, vao = 0.07;
    g.lineWidth = 11;
    g.strokeStyle = C.ganha; g.beginPath(); g.arc(lx, ly, lr, ini, ini + volta * 0.558 - vao); g.stroke();
    g.strokeStyle = C.custa; g.beginPath(); g.arc(lx, ly, lr, ini + volta * 0.558, ini + volta - vao); g.stroke();
    g.textBaseline = "middle"; g.font = `700 34px ${t.DISP}`;
    g.fillStyle = C.ink; g.fillText("contas", M + 70, 68);
    g.fillStyle = C.ganha; g.fillText("do poder", M + 70, 99);
    g.textBaseline = "alphabetic";
    return t;
  }
  // foto (ou iniciais, ou o desenho do prédio da Câmara), rótulo, nome e cargo; devolve onde a próxima parte começa
  async function cabecaImagem(t, { foto, nome, rotulo, sub, linhasSub = 2, predio }) {
    const { g, W, M, C } = t;
    const fy = 148, fw = 150, fh = 200;
    const img = foto && foto.startsWith("fotos/") ? await carregarImagem(daRaiz(foto)) : null;
    g.save(); t.caixa(M, fy, fw, fh, 20); g.clip();
    g.fillStyle = C.cartao; g.fillRect(M, fy, fw, fh);
    if (img) g.drawImage(img, M, fy, fw, fh);
    else if (predio) {
      g.translate(M + fw / 2 - 48, fy + fh / 2 - 48); g.scale(4, 4); g.fillStyle = C.ganha;
      g.fill(new Path2D("M12 2 2 7v2h20V7L12 2Zm-7 9v7h3v-7H5Zm5.5 0v7h3v-7h-3ZM16 11v7h3v-7h-3ZM2 20v2h20v-2H2Z"));
    } else { g.fillStyle = C.ganha; g.font = `700 72px ${t.DISP}`; g.textAlign = "center"; g.fillText(iniciais(nome), M + fw / 2, fy + fh / 2 + 24); g.textAlign = "left"; }
    g.restore();
    const tx = M + fw + 32, tmax = W - M - tx, grande = nome.length <= 22;
    g.fillStyle = C.ink2; g.font = `600 24px ${t.BODY}`; g.fillText(rotulo, tx, fy + 28);
    g.fillStyle = "#ffffff"; g.font = `700 ${grande ? 68 : 58}px ${t.DISP}`;
    let y = t.quebra(nome, tx, fy + 90, tmax, grande ? 66 : 58, 3);
    g.fillStyle = C.ink2; g.font = `500 30px ${t.BODY}`; y = t.quebra(sub, tx, y + 2, tmax, 38, linhasSub);
    return { y: Math.max(y + 30, fy + fh + 62), temFoto: !!img };
  }
  // o valor grande, com o rótulo em cima
  function valorImagem(t, y, rotulo, valor, porMes = true) {
    const { g, M, C } = t;
    g.fillStyle = C.ink2; g.font = `600 28px ${t.BODY}`; g.fillText(rotulo, M, y);
    let tam = 150; g.font = `700 ${tam}px ${t.MONO}`;
    while (g.measureText(valor).width > t.W - 2 * M - (porMes ? 90 : 0) && tam > 80) { tam -= 4; g.font = `700 ${tam}px ${t.MONO}`; }
    if (porMes) t.comMes(valor, M - 4, y + 124, `700 ${tam}px ${t.MONO}`, 36, "#ffffff");
    else { g.fillStyle = "#ffffff"; g.fillText(valor, M - 4, y + 124); }
    return y + 144;
  }
  // a frase da posição e a régua dos quatro quartos, como na página: sempre no mesmo tom (índigo claro), sem verde nem
  // vermelho. lugar: de 0 (o que menos custa) a 100 (o que mais custa)
  function reguaImagem(t, y, frase, lugar, verbo) {
    const { g, W, M, C } = t;
    const quarto = Math.min(3, Math.floor(lugar / 25)), larg = W - 2 * M;
    let tam = 34; g.font = `700 ${tam}px ${t.BODY}`;
    while (g.measureText(frase).width > larg && tam > 24) { tam -= 2; g.font = `700 ${tam}px ${t.BODY}`; }
    g.fillStyle = "#ffffff"; g.fillText(frase, M, y + 32);
    const ry = y + 50, alt = 16, vao = 8, seg = (larg - 3 * vao) / 4;
    for (let i = 0; i < 4; i++) {
      g.fillStyle = i === quarto ? C.regua : "rgba(201,215,224,.2)";
      t.caixa(M + i * (seg + vao), ry, seg, alt, alt / 2); g.fill();
    }
    const mx = M + (larg * lugar) / 100;
    g.fillStyle = C.fundo; g.beginPath(); g.arc(mx, ry + alt / 2, 15, 0, 7); g.fill();
    g.fillStyle = "#ffffff"; g.beginPath(); g.arc(mx, ry + alt / 2, 11, 0, 7); g.fill();
    g.fillStyle = C.regua; g.beginPath(); g.arc(mx, ry + alt / 2, 6, 0, 7); g.fill();
    g.fillStyle = C.ink2; g.font = `500 21px ${t.BODY}`;
    g.fillText(`← ${verbo[0]}`, M, ry + alt + 28);
    g.textAlign = "center"; g.fillText("mediana", M + larg / 2, ry + alt + 28); g.textAlign = "left";
    t.direita(`${verbo[1]} →`, W - M, ry + alt + 28);
    return y + 112;
  }
  // dois cartões lado a lado: [cor, rótulo, valor (null = "não publicados"), detalhe, com "/mês"?]
  function cartoesImagem(t, y, cartoes) {
    const { g, W, M, C } = t;
    const tw = (W - 2 * M - 24) / 2, th = 160;
    cartoes.forEach(([cor, rotulo, valor, detalhe, porMes = true], i) => {
      const x = M + i * (tw + 24);
      g.fillStyle = C.cartao; t.caixa(x, y, tw, th, 20); g.fill();
      t.bolinha(cor, x + 34, y + 38);
      g.fillStyle = C.ink2; g.font = `700 24px ${t.BODY}`; g.fillText(rotulo, x + 56, y + 47);
      if (valor === null) { g.fillStyle = "#ffffff"; g.font = `600 36px ${t.BODY}`; g.fillText("não publicados", x + 24, y + 104); }
      else if (porMes) t.comMes(valor, x + 24, y + 106, `600 54px ${t.MONO}`, 25, "#ffffff");
      else { g.fillStyle = "#ffffff"; g.font = `600 54px ${t.MONO}`; g.fillText(valor, x + 24, y + 106); }
      g.fillStyle = C.ink2; g.font = `400 24px ${t.BODY}`;
      let d = detalhe;
      while (g.measureText(d).width > tw - 40 && d.length > 10) d = d.slice(0, -2);
      g.fillText(d === detalhe ? d : `${d.trim()}…`, x + 24, y + 142);
    });
    return y + th + 18;
  }
  // linhas com bolinha, nome e valor à direita (onde mais gasta, quanto recebeu no mês)
  function linhasImagem(t, y, titulo, linhas, alt = 40, cor) {
    const { g, W, M, C } = t;
    g.fillStyle = C.ink2; g.font = `700 22px ${t.BODY}`; g.fillText(titulo, M, y + 26);
    y += 26;
    for (const [nomeL, valor, porMes = true] of linhas) {
      y += alt;
      t.bolinha(cor || C.custa, M + 8, y - 8);
      g.fillStyle = "#e3ecf1"; g.font = `500 26px ${t.BODY}`;
      let nome = nomeL.replace(/\*$/, "");
      while (g.measureText(nome).width > W - 2 * M - 300 && nome.length > 10) nome = nome.slice(0, -2);
      g.fillText(nome === nomeL.replace(/\*$/, "") ? nome : `${nome.trim()}…`, M + 28, y);
      g.font = `500 26px ${t.BODY}`; const wMes = porMes ? g.measureText("/mês").width + 6 : 0;
      g.font = `600 30px ${t.MONO}`; const wV = g.measureText(valor).width;
      if (porMes) t.comMes(valor, W - M - wMes - wV, y, `600 30px ${t.MONO}`, 22, "#ffffff");
      else { g.fillStyle = "#ffffff"; g.fillText(valor, W - M - wV, y); }
    }
    return y + 26;
  }
  // rodapé: o endereço da própria página e de onde vêm os dados
  function rodapeImagem(t, chamada, caminho, fonte, credito) {
    const { g, W, H, M, C } = t;
    if (credito) { g.fillStyle = "rgba(201,215,224,.75)"; g.font = `400 16px ${t.BODY}`; t.direita(credito, W - M, H - 190); }
    const ry = H - 176;
    g.fillStyle = C.marca; g.fillRect(0, ry, W, H - ry);
    g.fillStyle = "rgba(8,22,31,.85)"; g.font = `700 24px ${t.BODY}`; g.fillText(chamada, M, ry + 46);
    // o domínio e o caminho da página, no mesmo tamanho (diminui até caber; sem caber, só o domínio)
    const dom = dominio(), larg = W - 2 * M;
    let tam = 58;
    const medir = () => { g.font = `700 ${tam}px ${t.DISP}`; return g.measureText(dom + (caminho || "")).width; };
    while (caminho && medir() > larg && tam > 34) tam -= 2;
    const cabe = !caminho || medir() <= larg;
    if (!cabe) tam = 58;
    g.font = `700 ${tam}px ${t.DISP}`; g.fillStyle = "#0b5a46"; g.fillText(dom, M, ry + 106);
    if (caminho && cabe) { const wd = g.measureText(dom).width; g.fillStyle = "#08161f"; g.fillText(caminho, M + wd, ry + 106); }
    g.fillStyle = "rgba(8,22,31,.85)"; g.font = `500 26px ${t.BODY}`; g.fillText(fonte, M, ry + 150);
  }
  const creditoFoto = (fc) => (fc ? (fc.l ? `Foto: ${(fc.a || "Wikimedia Commons").replace(/ from .*$/, "").slice(0, 40)} (${fc.l}), Wikimedia Commons` : `Foto: ${fc.a}`) : null);

  // ---------------------------------------------------------------- imagem de um político (no período escolhido)
  // Duas passadas: a primeira desenha com o espaço normal e mede onde o conteúdo termina. Se sobra espaço antes do
  // rodapé (imagem com poucas informações, como a de uma Câmara pequena), a segunda distribui a sobra entre os blocos
  // (até 80 px entre um e outro). desenhar(t) devolve onde o conteúdo termina; respiro(t) marca cada vão entre blocos.
  const respiro = (t) => { t.blocos++; return t.folga; };
  async function comFolga(desenhar) {
    const t1 = await novaTela();
    const fim = await desenhar(t1);
    const sobra = t1.H - 214 - fim;
    if (!t1.blocos || sobra < 30) return t1.png();
    const t2 = await novaTela();
    Object.assign(t2, { folga: Math.min(80, Math.floor(sobra / t1.blocos)), fixo: t1.fixo });
    await desenhar(t2);
    return t2.png();
  }
  async function imagemPessoa(p, k) {
    const r = resumo(p, k), pos = posicao(p, k);
    if (!r) return null;
    return comFolga(async (t) => {
    const { g, W, H, M, C } = t;
    const cab = await cabecaImagem(t, {
      foto: p.f, nome: p.n, sub: `${p.g} · ${partidoUF(p)}`, linhasSub: p.k === "e" || p.k === "j" || p.k === "p" ? 3 : 2,
      rotulo: { e: "CONTRACHEQUE DO CARGO", j: "DOIS CARGOS, SOMADOS", p: "CONTRACHEQUE DO CARGO" }[p.k] || "CONTRACHEQUE DO MANDATO",
    });
    let y = valorImagem(t, cab.y + respiro(t), `${p.k === "p" ? "QUANTO RECEBE POR MÊS" : "CUSTO POR MÊS"} · ${nomePeriodo(k, true).toUpperCase()}`, reais(r.tm));
    // a barra dividida: o que vai para o bolso e os gastos, como no topo da página
    if (p.k !== "p" && r.tm > 0) {
      const larg = W - 2 * M, wg = r.cm > 0 ? Math.max(12, Math.min(larg - 12, (larg * r.gm) / r.tm)) : larg;
      g.fillStyle = C.ganha; t.caixa(M, y + 2, wg - (r.cm > 0 ? 4 : 0), 14, 5); g.fill();
      if (r.cm > 0) { g.fillStyle = C.custa; t.caixa(M + wg + 4, y + 2, larg - wg - 4, 14, 5); g.fill(); }
      y += 30;
    }
    if (pos) {
      const igual = empatado(pos);
      const frase = igual ? `${p.k === "p" ? "Recebe" : "Custa"} o mesmo que ${pos.iguais} dos outros ${pos.n - 1} ${plural(grupo(p))}`
        : p.k === "p" ? (pos.pos === 1 ? "Quem mais recebe na Prefeitura" : acimaDaMediana(pos) ? `Recebe mais que ${pos.pct}% da Prefeitura` : `Recebe menos que ${pos.pctMais}% da Prefeitura`)
        : pos.pos === 1 ? `O maior custo entre os ${plural(grupo(p))}` : pos.pos === pos.n ? `O menor custo entre os ${plural(grupo(p))}`
        : acimaDaMediana(pos) ? `Custa mais que ${pos.pct}% dos ${plural(grupo(p))}` : `Custa menos que ${pos.pctMais}% dos ${plural(grupo(p))}`;
      const lugar = pos.n > 1 ? (1 - (pos.pos - 1 + (igual ? pos.iguais / 2 : 0)) / (pos.n - 1)) * 100 : 50;
      y = reguaImagem(t, y + respiro(t), frase, lugar, p.k === "p" ? ["menos recebem", "mais recebem"] : ["menos custam", "mais custam"]);
    } else y += 4;
    // as duas partes do custo dele; vereador de Câmara que não publica a verba (ou publicou incompleta, e ela ficou de
    // fora): "não publicados", não R$ 0
    const cid = p.k === "v" ? cidadeDe(p) || {} : {};
    const semVerba = p.k === "v" && (!cid.verba_nome || (cid.verba_fora || []).some((a) => k === "leg" || a === k));
    y = cartoesImagem(t, y + respiro(t), [
      [C.ganha, "VAI PARA O BOLSO", reais(r.gm), `${sm(emSalariosMinimos(p, k, "g"))} salários mínimos`],
      [C.custa, gastosNome(p).toUpperCase(), p.k === "p" || semVerba ? null : reais(r.cm),
        p.k === "p" ? "carro oficial, viagens, equipe" : semVerba ? (cid.verba_nome ? "publicação incompleta" : "sem dados abertos") : gastosDetalhe(p)]]);
    // onde mais gasta: os 3 maiores tipos de gasto, por mês (menos, se não couber: a equipe e o aviso vêm embaixo, e o
    // rodapé começa em H - 176)
    const altEquipe = r.em ? 110 : p.k === "v" && p.eq ? 92 : 0;
    // (na segunda passada, com mais espaço entre os blocos, vale o número de linhas da primeira: ver comFolga)
    const livre = H - 232 - y - altEquipe - 52;
    const linhaG = t.fixo.linhaG ?? (Math.floor(livre / 3) >= 40 ? 40 : Math.max(34, Math.floor(livre / 3)));
    const cabem = t.fixo.cabem ?? Math.max(0, Math.min(3, Math.floor(livre / linhaG)));
    Object.assign(t.fixo, { linhaG, cabem });
    const maiores = cabem ? maioresGastos(p, k, cabem) : [];
    if (maiores.length) y = linhasImagem(t, y + respiro(t), `${gastosNome(p).toUpperCase()}: ONDE MAIS GASTA`, maiores.map(([n, v]) => [n, reais(v)]), linhaG);
    // equipe: à parte (borda tracejada, fora da soma)
    if (r.em) {
      y += respiro(t);
      const eh = 110;
      g.strokeStyle = C.linha; g.lineWidth = 2; g.setLineDash([10, 8]); t.caixa(M + 1, y + 1, W - 2 * M - 2, eh - 2, 20); g.stroke(); g.setLineDash([]);
      t.bolinha(C.equipe, M + 34, y + 40);
      g.fillStyle = C.ink2; g.font = `700 24px ${t.BODY}`; g.fillText("À PARTE: EQUIPE DO GABINETE", M + 56, y + 49);
      g.fillStyle = C.ink2; g.font = `400 24px ${t.BODY}`;
      g.fillText(`${r.pessoas ? pessoasTxt(r.pessoas) : "Assessores"}${r.porPessoa ? ` · ${reais(r.porPessoa)} por pessoa` : ""}${casaBase(p) === "s" ? " (estimativa)" : ""}`, M + 24, y + 88);
      g.font = `500 24px ${t.BODY}`; const wMes = g.measureText("/mês").width + 6;
      g.font = `600 48px ${t.MONO}`; const wValor = g.measureText(reais(r.em)).width;
      t.comMes(reais(r.em), W - M - 24 - wMes - wValor, y + 66, `600 48px ${t.MONO}`, 24, "#ffffff");
      y += eh;
    } else if (p.k === "v" && p.eq) {
      y += respiro(t);
      const eh = 92;
      g.strokeStyle = C.linha; g.lineWidth = 2; g.setLineDash([10, 8]); t.caixa(M + 1, y + 1, W - 2 * M - 2, eh - 2, 20); g.stroke(); g.setLineDash([]);
      t.bolinha(C.equipe, M + 34, y + 46);
      g.fillStyle = C.ink2; g.font = `700 24px ${t.BODY}`; g.fillText("À PARTE: EQUIPE DO GABINETE", M + 56, y + 55);
      g.fillStyle = "#ffffff"; g.font = `600 30px ${t.MONO}`; t.direita(pessoasTxt(p.eq.n), W - M - 24, y + 57);
      y += eh;
    }
    const aviso = p.k === "v" ? avisoVereador(p)
      : p.k === "p" ? "A Prefeitura publica só o que cada um recebe, não os gastos por pessoa."
      : p.k === "j" ? "Soma dos dois cargos, sem contar o salário duas vezes."
      : p.k === "d" ? "Para deputados, ainda faltam o 13º, a ajuda de custo e as diárias."
      : p.tp === "pr" ? "O avião presidencial e a estrutura da Presidência não entram na conta."
      : p.k === "e" ? `${r.cats.jetons ? `O bolso inclui ${reais(porMes(r, "jetons"))} por mês de jetons. ` : ""}Voos da FAB não têm custo publicado.` : null;
    if (aviso) { g.fillStyle = C.ink2; g.font = `400 22px ${t.BODY}`; g.fillText(aviso, M, Math.min(y + 34, H - 196)); }
    rodapeImagem(t, "VEJA O MÊS A MÊS E A FONTE DE CADA NÚMERO EM", `/${caminhoDe(p)}`, `Tudo com dados abertos oficiais ${fonteDados(p)}`, cab.temFoto ? creditoFoto(p.fc) : null);
    return aviso ? Math.min(y + 34, H - 196) : y;
    });
  }

  // ---------------------------------------------------------------- imagem de um governador
  async function imagemGov(e) {
    return comFolga(async (t) => {
    const { g, M, H, C } = t;
    const fem = govFem(e), p = posGov(e), R = rankingGov("v"), med = mediana(GOV.e.map((x) => x.v[0]));
    const smAtual = meta().salario_minimo["2026"] || meta().salario_minimo[anoAtual()];
    const cab = await cabecaImagem(t, { foto: e.gov.f, nome: e.gov.n, rotulo: `GOVERNO ${deUF(e.uf).toUpperCase()}`, sub: `${tituloGov(e)} ${deUF(e.uf)}${e.gov.pt ? ` · ${e.gov.pt}` : ""}` });
    let y = valorImagem(t, cab.y + respiro(t), `SALÁRIO ${fem ? "DA GOVERNADORA" : "DO GOVERNADOR"} · BRUTO, ${e.v[2] === "imprensa" ? `VALOR DE ${fmtMes(e.v[1])}` : `DESDE ${fmtMes(e.v[1])}`}`.toUpperCase(), reaisC(e.v[0]));
    const frase = p.pos === 1 ? "O maior salário de governador do país" : p.pos === p.n ? "O menor salário de governador do país" : `O ${p.pos}º maior salário de governador entre os 27 estados`;
    y = reguaImagem(t, y + respiro(t), frase, p.n > 1 ? (1 - (p.pos - 1) / (p.n - 1)) * 100 : 50, ["menores salários", "maiores salários"]);
    const pop = acimaDeQuemTrabalha(e.v[0] / smAtual);
    y = cartoesImagem(t, y + respiro(t), [
      [C.ganha, "EM SALÁRIOS MÍNIMOS", num(e.v[0] / smAtual, 1), pop !== null ? `mais que ${pctPop(pop)} de quem trabalha` : `salários mínimos de ${reais(smAtual)}`, false],
      e.vv ? [C.regua, e.vice && e.vice.fem ? "VICE-GOVERNADORA" : "VICE-GOVERNADOR", reais(e.vv[0]), e.vice ? `${e.vice.n}${e.vice.pt ? ` (${e.vice.pt})` : ""}` : "cargo vago hoje"]
        : [C.regua, "MEDIANA DOS 27 ESTADOS", reais(med), `o maior: ${ESTADOS[R[0].uf]}`]]);
    // o que recebeu de fato no último mês da folha (onde a folha do Estado abre para o robô)
    const ls = (e.m || []).filter((x) => x[1] === "gov");
    if (ls.length) {
      const ult = Math.max(...ls.map((x) => x[0])), doMes = ls.filter((x) => x[0] === ult);
      y = linhasImagem(t, y + respiro(t), `PELA FOLHA DE PAGAMENTO ${deUF(e.uf).toUpperCase()}`, doMes.map((x) => [`${e.oc[x[2]] ? e.oc[x[2]].n : e.gov.n} recebeu em ${fmtMes(ult)}`, reaisC(x[3]), false]), 40, C.ganha);
    }
    if (e.recebe) {
      g.fillStyle = C.ink2; g.font = `400 24px ${t.BODY}`;
      y = t.quebra(`${e.recebe.texto}.`, M, Math.min(y + 40, H - 240), t.W - 2 * M, 32, 2);
    }
    const fonte = { lei: "Fonte: lei estadual que fixa o subsídio", folha: "Fonte: folha de pagamento do Estado", tabela: "Fonte: tabela oficial de remuneração do Estado",
      calculado: "Fonte: cálculo nosso a partir da lei estadual", imprensa: "Fonte: valor informado pela imprensa" }[e.v[2]] || "Fonte: lei e folha de pagamento do Estado";
    rodapeImagem(t, ls.length ? "VEJA A LEI, O MÊS A MÊS E OS OUTROS 26 ESTADOS EM" : "VEJA A LEI, A HISTÓRIA DO VALOR E OS OUTROS 26 ESTADOS EM", urlGov(e.uf), fonte, cab.temFoto ? creditoFoto(e.gov.fc) : null);
    return y;
    });
  }

  // ---------------------------------------------------------------- imagem de uma Câmara Municipal
  async function imagemCidade(c) {
    if (!temCusto(c)) return null;
    return comFolga(async (t) => {
    const { C } = t;
    const cp = comparacaoCidade(c);
    const cab = await cabecaImagem(t, { predio: true, nome: `${c.n} (${c.uf})`, rotulo: "CÂMARA MUNICIPAL", sub: `${num(c.pop, 0)} habitantes · ${c.nv} vereadores${c.cap ? " · capital" : ""}` });
    let y = valorImagem(t, cab.y + respiro(t), `CUSTO DA CÂMARA POR MÊS · ${c.ano}`, compacto(c.custo / 12));
    if (cp.pct !== null) {
      const frase = `Por habitante, custa ${cp.pctMais < 50 ? `mais que ${cp.pct}%` : `menos que ${cp.pctMais}%`} das cidades do mesmo tamanho`;
      y = reguaImagem(t, y + respiro(t), frase, cp.lugar, ["custam menos", "custam mais"]);
    } else y += 4;
    y = cartoesImagem(t, y + respiro(t), [
      [C.custa, "POR HABITANTE", reaisC(porHabMes(c)), cp.med ? `mediana: ${reaisC(cp.med)}` : "por mês"],
      [C.regua, "CÂMARA POR VEREADOR", compacto(c.custo / 12 / Math.max(1, c.nv)), `o gasto todo ÷ ${c.nv}; não é o salário`]]);
    // o salário do vereador e, embaixo, o salário médio da cidade (IBGE), cada um com o seu ano. Sem o salário de verdade
    // (fora das capitais com vereador por vereador), só o teto, sem o salário médio ao lado
    const anoSm = (CID.meta || {}).salario_medio_ano, real = salarioReal(c);
    y = linhasImagem(t, y + respiro(t), real ? (c.sm > 0 ? "SALÁRIO DO VEREADOR E SALÁRIO MÉDIO DA CIDADE" : "SALÁRIO DE CADA VEREADOR") : "TETO DO SALÁRIO DE UM VEREADOR DAQUI", [
      real ? (real.folha ? ["vereador, mediana de 2025 (folha da Câmara)", reais(real.v)] : [`vereador, desde ${fmtMes(real.desde)}`, reaisC(real.v)])
        : ["no máximo, pela Constituição (o salário pode ser menor)", reais(tetoVereador(c.pop))],
      real && c.sm > 0 ? [`salário médio na cidade em ${anoSm} (IBGE)`, reais(c.sm)] : null].filter(Boolean), 40, C.ganha);
    rodapeImagem(t, "VEJA OS DETALHES E COMPARE COM OUTRAS CIDADES EM", urlCidade(c), `Dados abertos: ${listaE(["Tesouro Nacional (Siconfi)", "TSE", real ? "Câmara Municipal" : null, real && c.sm > 0 ? "IBGE" : null].filter(Boolean))}`);
    return y;
    });
  }
  const arquivoNome = (nome) => `contas-do-poder-${semAcento(nome).replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")}.png`;

  // ------------------------------------------------------------------ compartilhar a imagem
  // "Compartilhar" (o botão fixo no canto da tela, no celular; o cartão ao lado dos números, no computador) abre uma
  // janela com a imagem: a pessoa vê o que vai mandar e escolhe enviar (o menu do aparelho: WhatsApp, Telegram...),
  // copiar (para colar no WhatsApp Web) ou baixar. A imagem é feita logo depois que a página aparece, quando o navegador
  // está livre: o toque em "Enviar imagem" não espera (o celular só abre o menu de compartilhar dentro do próprio toque).
  // spec: { chave, gerar, arquivo, alt, legenda, textoZap, medir: {conteudo, ...} }
  const imagens = new Map(), prontas = new Map();
  const ocioso = (fn) => ("requestIdleCallback" in window ? requestIdleCallback(fn, { timeout: 1500 }) : setTimeout(fn, 400));
  function obterImagem(spec) {
    if (!imagens.has(spec.chave)) {
      const pr = new Promise((ok) => ocioso(ok)).then(spec.gerar).then((blob) => {
        const a = { blob, url: blob ? URL.createObjectURL(blob) : null };
        prontas.set(spec.chave, a);
        return a;
      });
      pr.catch(() => imagens.delete(spec.chave));
      imagens.set(spec.chave, pr);
      // guarda só as últimas 8 imagens
      while (imagens.size > 8) {
        const velha = imagens.keys().next().value;
        const a = prontas.get(velha);
        if (a && a.url) URL.revokeObjectURL(a.url);
        imagens.delete(velha); prontas.delete(velha);
      }
    }
    return imagens.get(spec.chave);
  }
  const podeCopiarImagem = () => !!(navigator.clipboard && navigator.clipboard.write && window.ClipboardItem);
  const podeEnviarArquivo = () => { try { return !!(navigator.canShare && navigator.canShare({ files: [new File([""], "x.png", { type: "image/png" })] })); } catch (e) { return false; } };
  const noCelular = () => matchMedia("(pointer: coarse)").matches;
  // no iPhone vai só a imagem: com texto junto, o WhatsApp do iPhone nem sempre manda os dois (o endereço da página já
  // está na imagem)
  const ehIOS = () => /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const medirComp = (spec, metodo, onde) => evento("compartilhar", { metodo, onde, ...spec.medir });
  // abre o menu do aparelho com a imagem (precisa estar pronta: chamado dentro do toque)
  function enviarArquivo(spec, a, onde, falhou) {
    const arquivo = new File([a.blob], spec.arquivo, { type: "image/png" });
    const dados = { files: [arquivo] };
    if (spec.legenda && !ehIOS()) dados.text = spec.legenda;
    navigator.share(dados).then(() => medirComp(spec, "enviar_imagem", onde), (e) => { if (e.name !== "AbortError" && falhou) falhou(e); });
  }
  // "Compartilhar" sempre abre a imagem primeiro (a pessoa vê o que vai mandar); lá ficam enviar, copiar e baixar
  function compartilharImagem(spec, onde) {
    evento("abrir_compartilhar", { onde, ...spec.medir });
    janelaImagem(spec, onde);
  }
  // os botões da imagem pronta: no celular, enviar primeiro; no computador, copiar primeiro
  function acoesImagem(spec, a, retorno, onde) {
    const enviar = podeEnviarArquivo() ? () => enviarArquivo(spec, a, onde, () => { retorno.textContent = "Não deu para abrir o menu de compartilhar. Copie ou baixe a imagem."; }) : null;
    const copiar = podeCopiarImagem() ? () => {
      // sem await antes do write: o Safari só deixa copiar dentro do clique
      navigator.clipboard.write([new ClipboardItem({ "image/png": a.blob })]).then(() => {
        medirComp(spec, "copiar_imagem", onde);
        retorno.textContent = noCelular() ? "Imagem copiada. Abra a conversa e cole." : "Imagem copiada. Abra a conversa (no WhatsApp Web, por exemplo) e cole com Ctrl+V ou ⌘+V.";
      }, () => {
        retorno.textContent = noCelular() ? "Não deu para copiar. Toque e segure a imagem para copiar ou salvar." : "O navegador não deixou copiar a imagem. Use “Baixar imagem”.";
      });
    } : null;
    const baixar = () => {
      const l = h("a", { href: a.url, download: spec.arquivo });
      document.body.append(l); l.click(); l.remove();
      medirComp(spec, "baixar_imagem", onde);
      retorno.textContent = "Imagem salva. Agora é só anexar na conversa.";
    };
    const ordem = noCelular() ? [["Enviar imagem…", enviar], ["Baixar imagem", baixar], ["Copiar imagem", copiar]]
      : [["Copiar imagem", copiar], ["Baixar imagem", baixar], ["Enviar…", enviar]];
    return ordem.filter(([, f]) => f).map(([rotulo, f], i) => h("button", { type: "button", class: `botao${i ? " botao--leve" : ""}`, onclick: f }, rotulo));
  }
  const dicaImagem = () => (noCelular()
    ? (podeEnviarArquivo() ? "Toque em “Enviar imagem” e escolha o WhatsApp (ou outro aplicativo). Ou toque e segure a imagem para salvar." : "Toque e segure a imagem para salvar ou compartilhar.")
    : "Copie e cole na conversa do WhatsApp Web, do Telegram ou num e-mail. Ou baixe para anexar.");
  // o resumo em texto, para quem prefere: WhatsApp, copiar o texto e copiar o link
  // aberto (computador, onde há espaço): com o título "Texto"; fechado (celular): dobrado em "Prefere mandar em texto?"
  function opcoesTexto(spec, onde, link, aberto) {
    const retorno = h("p", { class: "compartilhar-img__retorno", role: "status" });
    return h(aberto ? "div" : "details", { class: `texto-zap${aberto ? " janela-img__grupo" : ""}` },
      aberto ? h("h3", null, "Texto") : h("summary", null, "Prefere mandar em texto?"),
      h("p", { class: "pequeno discreto" }, "O mesmo resumo em texto, com o link para ver mais detalhes."),
      h("div", { class: "acoes" },
        h("a", { class: "botao botao--zap", href: `https://wa.me/?text=${encodeURIComponent(spec.textoZap)}`, target: "_blank", rel: "noopener", onclick: () => medirComp(spec, "whatsapp", onde) }, "Mandar no WhatsApp"),
        h("button", { type: "button", class: "botao botao--leve", onclick: () => { medirComp(spec, "copiar_texto", onde); copiarTexto(spec.textoZap, retorno, "Texto copiado. É só colar."); } }, "Copiar texto"),
        link ? h("button", { type: "button", class: "botao botao--leve", onclick: () => { medirComp(spec, "copiar_link", onde); copiarTexto(link, retorno, "Link copiado."); } }, "Copiar link") : null),
      retorno);
  }
  // janela com a imagem (computador, ou celular sem "enviar arquivo")
  let janela = null;
  function janelaImagem(spec, onde) {
    if (!janela) {
      janela = h("dialog", { class: "janela-img", "aria-labelledby": "janela-img-titulo" });
      janela.addEventListener("click", (e) => { if (e.target === janela) janela.close(); });
      document.body.append(janela);
    }
    janela.textContent = "";
    const retorno = h("p", { class: "compartilhar-img__retorno", role: "status" });
    const img = h("img", { class: "compartilhar-img__previa", alt: spec.alt, width: 1080, height: 1350 });
    const quadro = h("div", { class: "compartilhar-img__quadro carregando" }, img);
    const botoes = h("div", { class: "acoes" });
    add(janela, h("div", { class: "janela-img__corpo" },
      h("div", { class: "guia__topo" }, h("h2", { id: "janela-img-titulo", class: "h3" }, "Compartilhar"),
        h("button", { type: "button", class: "fechar", "aria-label": "Fechar", onclick: () => janela.close() }, "×")),
      // no computador, a imagem grande à esquerda e, à direita, a imagem e o texto; no celular, um embaixo do outro
      h("div", { class: "janela-img__grade" }, quadro,
        h("div", { class: "janela-img__lado" },
          h("div", { class: "janela-img__grupo" }, noCelular() ? null : h("h3", null, "Imagem"), h("p", { class: "pequeno discreto" }, dicaImagem()), botoes, retorno),
          spec.textoZap ? opcoesTexto(spec, onde, spec.link, !noCelular()) : null))));
    if (janela.showModal) janela.showModal(); else janela.setAttribute("open", "");
    obterImagem(spec).then((a) => {
      if (!a.blob) { retorno.textContent = "Não deu para gerar a imagem neste navegador."; return; }
      img.src = a.url; quadro.classList.remove("carregando");
      add(botoes, acoesImagem(spec, a, retorno, onde));
    }, () => { retorno.textContent = "Não deu para gerar a imagem neste navegador."; });
  }
  // O convite para compartilhar vem depois dos números principais (a pessoa lê primeiro) e antes dos detalhes (o mês a
  // mês): a prévia da imagem, uma frase e o botão, num bloco discreto.
  function blocoCompartilhar(spec, onde, convite, comTexto) {
    if (!spec) return null;
    const temImg = !!spec.gerar;
    const abrir = () => compartilharImagem(spec, onde);
    let previa = null;
    if (temImg) {
      previa = h("span", { class: "compartilhar-bloco__previa carregando", "aria-hidden": "true", onclick: abrir });
      obterImagem(spec).then((a) => { if (a.url) { previa.classList.remove("carregando"); previa.append(h("img", { src: a.url, alt: "" })); } }, () => {});
    }
    // o texto, na mesma caixa e em letra menor: WhatsApp, copiar o texto, copiar o link
    let texto = null;
    if (comTexto && spec.textoZap) {
      const retorno = h("span", { class: "compartilhar-bloco__retorno", role: "status" });
      texto = h("p", { class: "compartilhar-bloco__links" }, temImg ? "Ou em texto: " : "Em texto: ",
        h("a", { href: `https://wa.me/?text=${encodeURIComponent(spec.textoZap)}`, target: "_blank", rel: "noopener", onclick: () => medirComp(spec, "whatsapp", onde) }, "mandar no WhatsApp"),
        " · ", h("button", { type: "button", class: "link-botao", onclick: () => { medirComp(spec, "copiar_texto", onde); copiarTexto(spec.textoZap, retorno, "Texto copiado. É só colar."); } }, "copiar texto"),
        spec.link ? [" · ", h("button", { type: "button", class: "link-botao", onclick: () => { medirComp(spec, "copiar_link", onde); copiarTexto(spec.link, retorno, "Link copiado."); } }, "copiar link")] : null,
        " ", retorno);
    }
    return h("div", { class: `compartilhar-bloco${temImg ? "" : " compartilhar-bloco--so-texto"}` },
      previa,
      h("div", { class: "compartilhar-bloco__texto" }, h("strong", null, convite),
        temImg ? h("span", null, "Uma imagem pronta para o WhatsApp, com o endereço desta página e a fonte dos dados.") : null),
      temImg ? h("button", { type: "button", class: "botao", onclick: abrir }, "Compartilhar imagem") : null,
      texto);
  }
  // Cidade sem o gasto informado (sem imagem): o texto para compartilhar, no fim do cartão. As outras cidades e os
  // governadores têm a seção "Mande a imagem para quem você quiser" depois do cartão (secCompartilhar)
  const fimCompartilhar = (spec) => (spec && !spec.gerar ? blocoCompartilhar(spec, "fim", "Compartilhe estes números", true) : null);
  // No celular, o botão "Compartilhar" fixo no canto de baixo da tela aparece depois que a pessoa passa pelos números
  // principais (marco) e some enquanto o convite ou a seção da imagem estão na tela. No computador ele não aparece
  // (estilo.css).
  let flutuante = null;
  function botaoFlutuante(spec, marco) {
    if (!flutuante) {
      const icone = s("svg", { viewBox: "0 0 24 24", width: "22", height: "22", "aria-hidden": "true" });
      icone.append(s("path", { d: "M12 15V3m-4.5 4.5L12 3l4.5 4.5M6 11H5v9a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-9h-1", fill: "none", stroke: "currentColor", "stroke-width": "2", "stroke-linecap": "round", "stroke-linejoin": "round" }));
      flutuante = h("button", { type: "button", class: "compartilhar-flutuante", hidden: true, "aria-label": "Compartilhar a imagem desta página" }, icone, h("span", null, "Compartilhar"));
      document.body.append(flutuante);
    }
    flutuante.hidden = true;
    document.body.classList.toggle("com-flutuante", !!spec);
    if (!spec) return;
    flutuante.onclick = () => compartilharImagem(spec, "flutuante");
    const m = marco && document.querySelector(marco);
    if (!m || !("IntersectionObserver" in window)) { flutuante.hidden = false; return; }
    const alvos = [...document.querySelectorAll("#app .compartilhar-bloco, #app #resumo")];
    const vistos = new Set();
    let passou = false;
    const obs = new IntersectionObserver((es) => {
      for (const e of es) {
        if (e.target === m) passou = !e.isIntersecting && e.boundingClientRect.top < 0;
        else if (e.isIntersecting) vistos.add(e.target); else vistos.delete(e.target);
      }
      flutuante.hidden = !passou || vistos.size > 0;
    });
    [m, ...alvos].forEach((a) => obs.observe(a));
    observadores.push(obs);
  }
  // o que cada página compartilha
  function specPessoa(p, k) {
    const r = resumo(p, k);
    if (!r) return null;
    const link = linkDe(p, k);
    return { chave: `p:${p.id}~${k}`, gerar: () => imagemPessoa(p, k), arquivo: arquivoNome(p.n), link,
      alt: `Resumo de ${p.n}: ${p.k === "p" ? "recebe" : "custo de"} ${reais(r.tm)} por mês ${nomePeriodo(k, false)}`,
      legenda: link ? `Mais detalhes e a fonte de cada número: ${link}` : undefined, textoZap: textoCompartilhar(p, k),
      medir: { conteudo: "parlamentar", parlamentar: p.n, casa: casaTxt(p) } };
  }
  function specGov(e) {
    const link = endereco() ? `${origem()}${urlGov(e.uf)}` : "";
    return { chave: `g:${e.uf}`, gerar: () => imagemGov(e), arquivo: arquivoNome(`${tituloGov(e)} ${e.uf} ${e.gov.n}`), link,
      alt: `${tituloGov(e)} ${deUF(e.uf)}: salário de ${reaisC(e.v[0])} por mês`,
      legenda: link ? `Mais detalhes e a fonte de cada número: ${link}` : undefined, textoZap: textoGov(e), medir: { conteudo: "governador", uf: e.uf } };
  }
  function specCidade(c) {
    if (!temCusto(c)) return null;
    const link = endereco() ? `${origem()}${urlCidade(c)}` : "";
    return { chave: `c:${c.cod}`, gerar: () => imagemCidade(c), arquivo: arquivoNome(`camara ${c.n} ${c.uf}`), link,
      alt: `Câmara Municipal ${deCidade(c)}: custo de ${compacto(c.custo / 12)} por mês`,
      legenda: link ? `Mais detalhes e a fonte de cada número: ${link}` : undefined, textoZap: textoCidade(c), medir: { conteudo: "cidade", cidade: c.n, uf: c.uf } };
  }
  async function copiarTexto(conteudo, retorno, msg) {
    try { await navigator.clipboard.writeText(conteudo); retorno.textContent = msg; }
    catch (e) {
      retorno.textContent = "";
      const campo = h("textarea", { readonly: true, rows: 4, "aria-label": "Texto para copiar" }, conteudo);
      retorno.append("Selecione e copie:", campo); campo.select();
    }
  }

  // ================================================================== seções com parlamentar escolhido
  // Quem tem dois cargos: mostra os cargos e deixa escolher "tudo junto" ou cada um separado
  function barraCargos(p, k) {
    const j = p.k === "j" ? p : p.j ? S.porId.get(p.j) : null;
    if (!j) return null;
    const exe = j.cg[0], par = j.cg[1];
    const sub = (c) => {
      if (c === exe) return c.x ? `no cargo desde ${fmtMes(c.de)}` : `de ${fmtMes(c.de)} a ${fmtMes(c.ate)}`;
      const estado = c.x ? "no cargo hoje" : exe.x ? "licenciado: está no ministério" : "fora do cargo hoje";
      return c.ex ? `${estado} · exerceu o mandato ${c.ex} ${c.ex === 1 ? "mês" : "meses"} desde 2023` : estado;
    };
    // custo dele por mês de cada visão, no período escolhido
    const custo = (id) => { const q = S.porId.get(id); const r = q && resumo(q, k); return r ? `${reais(r.tm)}/mês` : `sem dados ${nomePeriodo(k, false)}`; };
    // quantos meses entram em cada média: os cargos costumam ser um depois do outro, então "tudo junto" é a média de
    // todos os meses (fica entre os dois valores), e não a soma; a soma, em totais do período, está em "Como a conta fecha"
    const nMeses = (id) => { const q = S.porId.get(id); const r = q && resumo(q, k); return r ? r.m : 0; };
    const mesesTxt = (n) => `${n} ${n === 1 ? "mês" : "meses"}`;
    const comMeses = (id, onde, texto) => (nMeses(id) ? `${mesesTxt(nMeses(id))} ${onde} · ${texto}` : texto);
    const opcoes = [
      [j.id, "Tudo junto", nMeses(j.id) ? `média dos ${mesesTxt(nMeses(j.id))} nos dois cargos, sem contar nada duas vezes` : "os dois cargos, sem contar nada duas vezes"],
      [exe.id, exe.g, comMeses(exe.id, "no ministério", sub(exe))],
      [par.id, par.g, comMeses(par.id, "no mandato", sub(par))]];
    const alvo = (id) => { const q = S.porId.get(id); return q ? urlPessoa(q, periodos(q).includes(k) ? k : null) : urlDe(id); };
    return h("nav", { class: "cargos", "aria-label": "Cargos desta pessoa" },
      h("p", { class: "rotulo" }, `${j.n} tem dois cargos. Veja juntos ou separados (custo por mês ${nomePeriodo(k, false)}):`),
      h("div", { class: "cargos__lista" }, opcoes.map(([id, titulo, texto]) => h("a", {
        class: "cargo-opcao", href: alvo(id), "aria-current": id === p.id ? "page" : null,
        onclick: () => { S.origem = "cargos"; evento("trocar_cargo", { para: id.split("-")[0], parlamentar: j.n }); },
      }, h("strong", null, titulo), h("span", { class: "cargo-opcao__valor" }, custo(id)), h("small", null, texto)))),
      contaDosCargos(j, k, p.k === "j"));
  }
  const maiuscula = (s) => s.charAt(0).toUpperCase() + s.slice(1);
  // Quantos meses de um período a pessoa passou em cada cargo (j.tr: [[de, até, "e" | "d" | "s"]])
  const proxMes = (m) => (m % 100 === 12 ? (Math.floor(m / 100) + 1) * 100 + 1 : m + 1);
  function mesesPorCargo(j, k) {
    const n = { e: 0, par: 0 };
    for (const [a, b, c] of j.tr || []) for (let m = a; m <= b; m = proxMes(m)) if (k === "leg" || Math.floor(m / 100) === Number(k)) n[c === "e" ? "e" : "par"]++;
    return n;
  }
  // "Por que tudo junto não é a soma?": as três visões lado a lado, linha por linha, e a explicação
  // "Como a conta fecha": as três visões lado a lado, em totais do período (assim ministro + parlamentar = tudo junto).
  // Cada cargo separado só tem o que a pessoa recebeu naquele cargo: o salário pago pelo Congresso nos meses como
  // ministro fica no ministro, e não aparece de novo no deputado/senador.
  function contaDosCargos(j, k, aberto) {
    const [exe, par] = j.cg.map((c) => S.porId.get(c.id));
    // cabeçalho curto (o nome completo de cada cargo já está nos cartões de cima), para caber no celular
    const cols = [[exe, "No ministério", j.cg[0].g], [par, "No mandato", j.cg[1].g], [j, "Tudo junto", "os dois cargos"]].map(([q, nome, longo]) => ({ nome, longo, r: q ? resumo(q, k) : null }));
    if (!cols[2].r) return null;
    const cats = [...ORDEM_GANHA, ...ORDEM_CUSTA].filter((c) => cols.some((x) => x.r && x.r.cats[c]));
    const total = (x, f) => (x.r && Math.abs(f(x.r)) >= 0.5 ? reais(f(x.r)) : "R$ 0");
    const linhas = [
      ...cats.map((c) => [nomeCat(c).replace(/ \(.*\)$/, ""), (r) => r.cats[c] || 0]),
      ["Custo total no período", (r) => r.g + r.c, "total"],
      ["Meses no cargo", null, "meses"],
      ["Custo por mês (média)", (r) => r.tm, "media"],
      ...(cols.some((x) => x.r && x.r.e) ? [["À parte: equipe do gabinete", (r) => r.e]] : []),
    ];
    const n = mesesPorCargo(j, k);
    const cargoPar = j.cg[1].g.toLowerCase(), casaPar = S.porId.get(j.cg[1].id) && S.porId.get(j.cg[1].id).k === "s" ? "o Senado" : "a Câmara";
    const quando = maiuscula(nomePeriodo(k, false));
    const expl = [];
    if (n.par === 0) expl.push(`${quando}, ${j.n} passou os ${n.e} meses no ministério, licenciado do mandato de ${cargoPar}. O salário desses meses foi pago por ${casaPar}, mas é o salário de ministro: aparece só na coluna do ministério. Como ${cargoPar}, sem exercer o mandato, não recebeu nada a mais.`);
    else if (n.e === 0) expl.push(`${quando}, ${j.n} passou os ${n.par} meses exercendo o mandato de ${cargoPar}, fora do ministério.`);
    else expl.push(`${quando}, foram ${n.e} ${n.e === 1 ? "mês" : "meses"} no ministério e ${n.par} ${n.par === 1 ? "mês" : "meses"} exercendo o mandato de ${cargoPar}. Cada coluna tem só os meses daquele cargo: o salário entra uma vez por mês, no cargo em que ele estava; cota e equipe do gabinete, nos meses do mandato; jetons e viagens, nos meses do ministério.`);
    if (n.par === 0 && cols[1].r && cols[1].r.e) expl.push(`${casaPar === "a Câmara" ? "A Câmara" : "O Senado"} ainda registrou ${reais(cols[1].r.e)} com a equipe do gabinete no período, mesmo sem exercer o mandato; como toda equipe, fica à parte.`);
    expl.push("Somando as duas primeiras colunas, dá o “tudo junto”. A média por mês de cada coluna usa só os meses daquele cargo.");
    const celula = (x, f, tipo) => {
      const meses = x === cols[0] ? n.e : x === cols[1] ? n.par : n.e + n.par;
      if (tipo === "meses") return String(meses);
      if (tipo === "media") return x.r && meses ? reais(f(x.r)) : "—";
      return total(x, f);
    };
    return h("details", { class: "conta-cargos", open: aberto || null, ontoggle: (e) => { if (e.target.open) evento("abrir_detalhe", { categoria: "dois_cargos", casa: "dois cargos" }); } },
      h("summary", null, "Como a conta fecha: cada cargo e a soma"),
      rolagem("Cada cargo e a soma", h("table", { class: "comp-tabela conta-cargos__tabela" },
        h("thead", null, h("tr", null, h("th", null, `Total ${nomePeriodo(k, false).replace(/^em /, "em ")}`), cols.map((x) => h("th", { title: x.longo }, x.nome)))),
        h("tbody", null, linhas.map(([nome, f, tipo]) => h("tr", { class: tipo === "total" ? "conta-cargos__total" : tipo ? "conta-cargos__extra" : null },
          h("td", null, nome), cols.map((x) => h("td", { class: "num" }, celula(x, f, tipo)))))))),
      h("p", { class: "pequeno" }, expl.join(" ")));
  }
  // Prefeitura: cargos ocupados desde 2025 (p.cg: [[cargo, de, até]])
  function cargosTxt(p) {
    const ult = (prefeituraDe(p.cid) || {}).ultimo_mes;
    const um = ([g, de, ate]) => `${g} ${p.x && ate === ult ? `desde ${fmtMes(de)}` : de === ate ? `em ${fmtMes(de)}` : `de ${fmtMes(de)} a ${fmtMes(ate)}`}`;
    return p.cg.length > 1 ? `Cargos desde 2025: ${p.cg.map(um).join("; ")}.` : `${um(p.cg[0])}.`;
  }
  // Quem foi vereador e está (ou esteve) na Prefeitura, em momentos diferentes: os dois cargos, com o custo de cada um
  function barraRel(p, k) {
    if ((p.k !== "p" && p.k !== "v") || !p.rel || !S.porId.get(p.rel)) return null;
    const q = S.porId.get(p.rel);
    const [ver, pre] = p.k === "v" ? [p, q] : [q, p];
    const quando = (x) => {
      if (x.k === "v") return ocupacaoTxt(x) ? `no cargo ${ocupacaoTxt(x)}` : "no cargo desde jan/2025";
      const de = x.cg[0][1], ate = x.cg[x.cg.length - 1][2];
      return x.x ? `desde ${fmtMes(de)}` : de === ate ? `em ${fmtMes(de)}` : `de ${fmtMes(de)} a ${fmtMes(ate)}`;
    };
    const custo = (x) => { const r = resumo(x, k); return r ? `${reais(r.tm)}/mês` : `sem dados ${nomePeriodo(k, false, grupo(x))}`; };
    return h("nav", { class: "cargos", "aria-label": "Cargos desta pessoa" },
      h("p", { class: "rotulo" }, `${p.n} teve dois cargos desde 2025, em momentos diferentes (custo por mês ${nomePeriodo(k, false)}):`),
      h("div", { class: "cargos__lista" }, [ver, pre].map((x) => h("a", {
        class: "cargo-opcao", href: urlDe(x.id), "aria-current": x.id === p.id ? "page" : null,
        onclick: () => { S.origem = "cargos"; evento("trocar_cargo", { para: x.id.split("-")[0], parlamentar: p.n }); },
      }, h("strong", null, x.k === "v" ? `${x.g} ${deCid(x.cid)}` : x.g), h("span", { class: "cargo-opcao__valor" }, custo(x)), h("small", null, quando(x))))),
      h("p", { class: "pequeno discreto", style: "margin:0" }, "Não se somam: para ficar na Prefeitura, o vereador se licencia da Câmara, e um suplente assume a cadeira. Cada página mostra só os meses daquele cargo."));
  }
  // vereador: períodos no gabinete (suplente, licença), a data da equipe e o limite da verba
  const dataTxt = (s) => `${s.slice(6, 8)}/${s.slice(4, 6)}/${s.slice(0, 4)}`;
  function ocupacaoTxt(p) {
    const oc = p.oc || [], c = camaraDe(p.cid);
    if (!oc.length || !c || (oc.length === 1 && oc[0][0] <= `${c.inicio}01` && !oc[0][1])) return null;
    return oc.map(([a, b]) => (b ? (a === b ? `em ${dataTxt(a)}` : `de ${dataTxt(a)} a ${dataTxt(b)}`) : `desde ${dataTxt(a)}`)).join("; ");
  }
  const mesEquipe = (c) => { const [m, a] = ((c && c.equipe_em) || "").split("/"); return Number(a) * 100 + Number(m); };
  function limiteVerba(p, k) {
    const anos = k === "leg" ? Object.keys(p.vb || {}) : [k];
    return anos.reduce((a, x) => a + ((p.vb || {})[x] ? p.vb[x][0] : 0), 0);
  }
  function sobraVerba(p, k) {
    const anos = k === "leg" ? Object.keys(p.vb || {}) : [k];
    return anos.map((a) => [a, (p.vb || {})[a] ? p.vb[a][1] : 0]).filter(([, v]) => v > 0);
  }
  // o que importa na primeira tela do celular: o período, o custo por mês, de onde ele vem e a posição entre os colegas
  function resumoTopo(p, k, r, C, pos, trocar) {
    const principal = h("div", { class: "conta__resumo-principal" },
      pilulas(periodos(p).map((x) => [x, nomePeriodo(x, true)]), k, trocar, "Período"));
    if (!r) return h("div", { class: "conta__resumo" }, add(principal, h("p", { class: "discreto" }, "Sem pagamentos registrados neste período.")));
    const recebe = p.k === "p", smT = sm(emSalariosMinimos(p, k, "t"));
    // a barra dividida (bolso e gastos) e, embaixo de cada pedaço, o valor dele (estilo.css: --parte)
    const parte = `${(r.tm > 0 ? (r.gm / r.tm) * 100 : 100).toFixed(1)}%`;
    add(principal,
      h("p", { class: "rotulo" }, `${recebe ? "Recebe por mês" : "Custo por mês"} ${nomePeriodo(k, false)}`),
      h("p", { class: "resumo-valor" }, reais(r.tm)),
      h("div", { class: "resumo-divisao", style: `--parte:${recebe ? "100%" : parte}`, "aria-hidden": "true" },
        h("span", { class: "resumo-divisao__ganha" }), recebe ? null : h("span", { class: "resumo-divisao__custa" })),
      recebe ? h("ul", { class: "resumo-partes resumo-partes--um" }, h("li", { class: "resumo-parte--ganha" }, h("strong", null, reais(r.gm)), h("span", null, "tudo para o bolso")))
        : h("ul", { class: "resumo-partes", style: `--parte:${parte}`, "aria-label": "De onde vem o custo" },
          h("li", { class: "resumo-parte--ganha" }, h("strong", null, reais(r.gm)), h("span", null, "para o bolso")),
          h("li", { class: "resumo-parte--custa" }, h("strong", null, reais(r.cm)), h("span", null, `em ${gastosNome(p).toLowerCase()}`))),
      h("p", { class: "resumo-sm" }, `${smT} salários mínimos por mês`),
      seloComp(r.tm, C.tm, `vs. mediana dos ${plural(grupo(p))}`));
    // à direita (no computador): a posição entre os colegas
    return h("div", { class: "conta__resumo" }, principal, pos ? h("div", { class: "conta__resumo-lado" }, blocoPosicao(p, k, pos)) : null);
  }
  function secContracheque(p, k) {
    const r = resumo(p, k), C = colegasDe(p, k), pos = posicao(p, k);
    const jj = (p.k === "d" || p.k === "s") && p.j ? S.porId.get(p.j) : null; // deputado/senador que também foi ministro
    const trocar = (novo) => { evento("trocar_periodo", { periodo: novo === "leg" ? "mandato" : novo, casa: casaTxt(p) }); S.periodo = novo; S.rank.periodo = novo; trocarEndereco(urlPessoa(p, novo)); render(); };
    const card = h("article", { class: "cartao conta", id: "contracheque" });
    add(card, h("div", { class: "conta__topo" },
      avatar(p, "g"),
      h("div", null,
        h("p", { class: "rotulo" }, { e: "Contracheque do cargo", j: "Contracheque dos dois cargos, somados", p: "Contracheque do cargo" }[p.k] || "Contracheque do mandato"),
        h("h1", { class: "conta__nome" }, p.n),
        h("div", { class: "conta__sub" }, h("span", null, `${p.g} · ${partidoUF(p)}`), etiquetaCargo(p))),
      h("a", { href: p.o, target: "_blank", rel: "noopener", class: "pequeno conta__oficial" }, "Página oficial\u00a0↗")),
      resumoTopo(p, k, r, C, pos, trocar));
    const lado = h("div", { class: "conta__lado" });
    if (r) {
      // deputado/senador que também foi ministro: conta só os meses exercendo o mandato
      add(lado, h("div", { class: "estatisticas" },
        jj ? estatistica("Meses exercendo o mandato", String(mesesPorCargo(jj, k).par), nomePeriodo(k, false))
          : estatistica({ e: "Meses no cargo", j: "Meses nos dois cargos", p: "Meses no cargo" }[p.k] || "Meses de mandato", String(r.m), nomePeriodo(k, false)),
        estatistica("Vai para o bolso", sm(emSalariosMinimos(p, k, "g")), "salários mínimos por mês"),
        estatisticaPop(emSalariosMinimos(p, k, "g"))));
      if (p.im) {
        const anos = k === "leg" ? Object.keys(p.im) : [k];
        const frases = anos.filter((a) => p.im[a]).map((a) => p.k === "d" ? `${a}: apartamento funcional por ${p.im[a]} dias` : `${a}: ${p.im[a] === "Utilizou" ? "usou" : "não usou"} imóvel funcional`);
        if (frases.length) add(lado, h("div", { class: "estatistica" }, h("span", { class: "rotulo" }, "Moradia em Brasília"), frases.map((f) => h("span", { class: "pequeno" }, f))));
      }
      if (r.mg < r.m && p.k !== "e" && p.k !== "j" && p.k !== "p" && !p.j) add(lado, h("p", { class: "nota" }, `Em ${r.m - r.mg} ${r.m - r.mg === 1 ? "mês" : "meses"} não houve salário (licença, por exemplo), mas o gabinete continuou funcionando. Cada média usa os seus próprios meses.`));
      if (p.k === "j") add(lado, h("p", { class: "caixa-nota" }, "Somamos os dois cargos sem contar nada duas vezes: o salário entra uma vez (nos meses como ministro, quem paga é o Congresso); a cota e a equipe do gabinete só nos meses exercendo o mandato; viagens e jetons só nos meses como ministro."));
      if ((p.k === "d" || p.k === "s") && p.j) add(lado, h("p", { class: "nota" }, `Nos meses no ministério, o salário que ${p.k === "d" ? "a Câmara" : "o Senado"} pagou aparece na página de ministro, e não aqui: aqui ficam só os meses exercendo o mandato.`));
      if (casaBase(p) === "d") add(lado, h("p", { class: "aviso" }, "Ainda faltam o 13º, a ajuda de custo e as diárias dos deputados. O valor real que recebem é um pouco maior."));
      if (p.k === "e") {
        const ate = meta().ultimo_mes_executivo;
        add(lado, h("p", { class: "aviso" }, p.tp === "pr"
          ? "O presidente viaja no avião presidencial, e a estrutura da Presidência é paga à parte. Esses custos não aparecem no nome dele: aqui entra o que ele recebe."
          : "Ministros não têm cota parlamentar nem verba de gabinete. Entram o salário, os jetons de conselhos e as viagens oficiais (diárias e passagens). Voos da FAB não têm custo publicado."),
          h("p", { class: "nota" }, `O Portal da Transparência publica os salários com uns 2 meses de atraso: dados até ${MESES[(ate % 100) - 1]}/${Math.floor(ate / 100)}.`));
      }
      if (p.k === "p") {
        const c = prefeituraDe(p.cid);
        add(lado,
          h("p", { class: "nota" }, cargosTxt(p)),
          p.ced ? h("p", { class: "aviso aviso--forte" }, h("strong", null, "Parte do salário (ou todo ele) vem de outro órgão. "),
            `Em ${p.ced} ${p.ced === 1 ? "mês" : "meses"}, a Prefeitura pagou a ${p.n} só uma parte do que o cargo paga, ou nada: ${p.rel ? "como vereador licenciado, pode continuar recebendo pela Câmara" : "quem é servidor de outro órgão costuma continuar recebendo o salário de lá"}. Por isso fica fora das comparações.`) : null,
          h("p", { class: "aviso" }, "A Prefeitura publica quanto cada servidor recebe, mês a mês, com o nome. Não publica os gastos por pessoa (carro oficial, viagens, equipe): aqui entra só o que vai para o bolso."),
          c.salario_nota ? h("p", { class: "nota" }, c.salario_nota) : null,
          (c.notas || []).map((n) => h("p", { class: "nota" }, n)),
          h("p", { class: "nota" }, `Dados da Prefeitura ${deCid(p.cid)} até ${fmtMes(c.ultimo_mes)}.`));
      }
      if (p.k === "v") {
        const c = camaraDe(p.cid), sub = c.subsidio || [], oc = ocupacaoTxt(p);
        const [ultimo, primeiro] = [sub[sub.length - 1], sub[0]];
        const igual = !c.subsidio_folha && ultimo
          ? `O salário é o mesmo para todos os vereadores ${deCid(p.cid)}: ${reaisC(ultimo[1])} por mês desde ${fmtMes(ultimo[0])}${sub.length > 1 ? ` (${reaisC(primeiro[1])} em ${fmtMes(primeiro[0])})` : ""}. ` : "";
        add(lado,
          oc ? h("p", { class: "nota" }, `${p.sup ? "Suplente. " : ""}No cargo ${oc}${p.gab ? ` (gabinete ${p.gab})` : ""}. ${c.subsidio_folha ? "O salário é o que a folha pagou em cada mês." : "O salário conta só os dias no cargo."}`) : null,
          // rosa (aviso) só quando falta parte do que a pessoa recebe; o resto é explicação (caixa neutra)
          igual || c.salario_nota ? h("p", { class: avisoOuNota(c.salario_nota) }, `${igual}${c.salario_nota || ""}`) : null,
          (c.notas || []).map((n) => h("p", { class: "nota" }, n)),
          h("p", { class: "nota" }, `Dados da ${c.casa} até ${fmtMes(c.ultimo_mes)}.`));
      }
      if (p.fc) add(lado, h("p", { class: "nota credito" }, "Foto: ", h("a", { href: p.fc.u, target: "_blank", rel: "noopener" }, p.fc.l ? `${(p.fc.a || "autor no Wikimedia Commons").replace(/ from .*$/, "")} (${p.fc.l})` : p.fc.a), p.fc.l ? `${p.fc.r ? ", recortada" : ""}, via Wikimedia Commons.` : "."));
      if (p.q) add(lado, h("p", { class: "nota" }, p.k === "p"
        ? `No mês da saída, recebeu mais ${reais(p.q[1])} de acertos (férias, 13º proporcional e outros). Esse valor não entra nas médias.`
        : `Depois de deixar o cargo, recebeu mais ${reais(p.q[1])} em ${p.q[0]} ${p.q[0] === 1 ? "mês" : "meses"} (acertos da saída e quarentena). Esse valor não entra nas médias.`));
      if (p.k === "p" && p.rel && !S.porId.get(p.rel)) add(lado, h("p", { class: "nota" }, `${p.n} é vereador ${deCid(p.cid)} e está licenciado da Câmara para ficar na Prefeitura: um suplente ocupa a cadeira.`));
      if (p.rel && !p.j && S.porId.get(p.rel) && p.k !== "p" && p.k !== "v") add(lado, h("p", { class: "nota" },
        p.k === "e" ? `Também é ${nomeRel(p.rel)}. Nos meses como ministro, o salário pode ter sido pago pelo Congresso: aparece aqui. ` : "Também foi do governo federal. ",
        h("a", { href: urlDe(p.rel) }, p.k === "e" ? "Ver o contracheque no Congresso" : `Ver o contracheque como ${nomeRel(p.rel)}`)));
    }
    const cargos = barraCargos(p, k) || barraRel(p, k);
    if (cargos) card.append(cargos);
    if (!lado.children.length) lado.hidden = true;
    const valores = h("div", { class: "conta__valores" }, h("p", { class: "passo", style: "padding:20px 22px 0" }, "Item por item, por mês"));
    if (!r) add(valores, h("p", { class: "discreto", style: "padding:16px 22px" }, "Sem pagamentos registrados neste período."));
    else {
      const txtMed = `mediana dos ${plural(grupo(p))}`;
      const rateados = Object.keys(r.cats).filter((c) => meta().rateio[c]);
      const linhas = (ordem) => ordem.filter((c) => r.cats[c]).map((c) => {
        const valor = h("span", { class: "item__valor" }, `${meta().rateio[c] ? "≈ " : ""}${reais(porMes(r, c))}`);
        const selo = seloComp(porMes(r, c), C.cat[c], `vs. ${txtMed}`);
        const det = detalheCat(p, k, c);
        if (!det) return h("div", { class: "item" }, h("span", { class: "item__nome" }, nomeCat(c)), valor, selo);
        const vpm = c === "viagens_oficiais" ? viagensPorMes(p, k) : null;
        return h("details", { class: "item-abre", ontoggle: (e) => { if (e.target.open) evento("abrir_detalhe", { categoria: c, casa: casaTxt(p) }); } },
          h("summary", { class: "item" }, h("span", { class: "item__nome" }, nomeCat(c), h("span", { class: "item__abre" }, "detalhe")), valor, selo),
          h("div", { class: "subitens" },
            det.linhas.map(([t, v]) => h("div", { class: "subitem" }, h("span", null, t), h("span", { class: "num" }, reais(v / det.div)), h("span", { class: "subitem__pct" }, pctTxt(v, det.total)))),
            vpm ? h("p", { class: "subitens__nota" }, `${num(vpm, vpm < 10 ? 1 : 0)} viagens por mês, em média.`) : null,
            c === "cota_parlamentar" && det.linhas.some(([t]) => t.endsWith("*")) ? h("p", { class: "subitens__nota" }, "* Sem detalhe nos dados abertos desde ago/2025.") : null));
      });
      const titulo = (texto, tipo) => h("div", { class: "grupo-titulo" }, h("span", { class: `chave chave--${tipo}` }), h("span", { class: "rotulo" }, texto));
      add(valores,
        titulo("Vai para o bolso", "ganha"), linhas(ORDEM_GANHA),
        jj && !r.cats.salario ? h("div", { class: "item" }, h("span", { class: "item__nome" }, "Salário"), h("span", { class: "item__valor" }, reais(0)),
          h("span", { class: "item__detalhe" }, "Nos meses no ministério, o salário está na página de ministro. ", h("a", { href: urlDe(jj.cg[0].id) }, "Ver"))) : null,
        titulo(`${gastosNome(p)}, pagos com dinheiro público`, "custa"),
        p.k === "p" ? h("div", { class: "item" }, h("span", { class: "item__nome" }, "Carro oficial, viagens e equipe"), h("span", { class: "item__valor" }, "não publicados"),
          h("span", { class: "item__detalhe" }, "A Prefeitura não informa esses gastos por pessoa.")) : linhas(ORDEM_CUSTA),
        rateados.length ? h("p", { class: "nota", style: "padding:10px 22px 0" },
          `≈ ${rateados.map((c) => meta().rateio[c]).join(" ")} Dividimos o total do ano pelos meses com salário: é uma aproximação.`) : null,
        // a soma no fim da lista, como num contracheque (o resumo e a posição estão no topo do cartão)
        h("div", { class: "total" },
          h("strong", null, p.k === "p" ? "Total por mês" : "Custo por mês"),
          h("span", { class: "total__valor" }, reais(r.tm)),
          h("span", { class: "item__detalhe" }, p.k === "p" ? "tudo para o bolso" : `${reais(r.gm)} para o bolso + ${reais(r.cm)} em ${gastosNome(p).toLowerCase()}`)),
        r.em ? h("div", { class: "equipe-resumo" },
          titulo("À parte: equipe do gabinete (vai para outras pessoas)", "equipe"),
          h("div", { class: "estatisticas", style: "padding:6px 22px 0" },
            estatistica("Custo da equipe", reais(r.em), "por mês"),
            estatistica("Pessoas", num(r.pessoas, r.pessoas < 10 ? 1 : 0), r.pessoasHoje ? `em média; ${r.pessoasHoje} no último mês` : "em média"),
            estatistica("Por pessoa", r.porPessoa ? reais(r.porPessoa) : "—", "por mês, em média")),
          h("p", { class: "nota", style: "padding:8px 22px 0" }, p.k === "v" ? ((camaraDe(p.cid) || {}).equipe_nota || "Assessores do gabinete, pela folha de pagamento da Câmara.")
            : casaBase(p) === "d"
            ? "Secretários parlamentares pagos pela verba de gabinete. Não inclui cargos de natureza especial, pagos pela Câmara quando o deputado tem cargo de liderança."
            : "Assessores comissionados do gabinete e dos escritórios nos estados. Estimativa feita a partir da folha de pagamento do Senado."),
          h("button", { type: "button", class: "link-botao pequeno", style: "margin:6px 22px 0", onclick: () => irPara("equipe") }, "Ver a equipe mês a mês")) : null,
        !r.em && p.k === "v" && p.eq ? h("div", { class: "equipe-resumo" },
          titulo("À parte: equipe do gabinete (vai para outras pessoas)", "equipe"),
          h("div", { class: "estatisticas", style: "padding:6px 22px 0" },
            estatistica("Pessoas", String(p.eq.n), `em ${fmtMes(mesEquipe(camaraDe(p.cid)))}`),
            estatistica("Custo da equipe", "não publicado", p.cid === SP ? "a Câmara só mostra os salários com CPF" : "a Câmara não publica")),
          h("button", { type: "button", class: "link-botao pequeno", style: "margin:6px 22px 0", onclick: () => irPara("equipe") }, "Ver os cargos da equipe")) : null);
    }
    add(card, h("div", { class: "conta__corpo" }, lado, valores));
    return card;
  }
  function pontosDoPeriodo(p, k) {
    const ano = k === "leg" ? null : Number(k);
    return p.t.filter((t) => ano === null || Math.floor(t[0] / 100) === ano).map((t) => ({ aaaamm: t[0], g: t[1], c: t[2], e: t[3], pes: t[4], ra: t[5] || 0 }));
  }
  const nomeMes = (q) => `${MESES[(q.aaaamm % 100) - 1]}/${Math.floor(q.aaaamm / 100)}`;
  function tabela(cabecalho, linhas, rotulo) {
    return h("details", { class: "tabela" }, h("summary", null, "Ver os valores em tabela"),
      rolagem(rotulo || "Valores mês a mês", h("table", null,
        h("thead", null, h("tr", null, cabecalho.map((c) => h("th", null, c)))),
        h("tbody", null, linhas.map((l) => h("tr", null, l.map((v, i) => h("td", { class: i ? "num" : null }, v))))))));
  }
  function notaMensalVereador(p) {
    if (p.cid === SP) return "A verba do gabinete entra no mês da nota. O que não é usado num mês pode ser usado nos meses seguintes do mesmo ano, então há meses acima da média. Os últimos meses ainda podem receber notas.";
    const c = camaraDe(p.cid) || {};
    return [...(c.verba_notas || []).slice(0, 1), c.verba_regra, "Os últimos meses ainda podem mudar."].filter(Boolean).join(" ");
  }
  function secMensal(p, k) {
    const pontos = pontosDoPeriodo(p, k).filter((q) => q.g || q.c);
    if (!pontos.length) return null;
    const caixa = h("div", { class: "grafico" });
    const card = h("article", { class: "cartao", id: "mes-a-mes" },
      h("div", { class: "cartao__cabeca" }, h("div", null, h("h2", { class: "h3" }, "Custo mês a mês"),
        h("p", { class: "pequeno discreto" }, `O que foi para o bolso e os ${gastosNome(p).toLowerCase()} em cada mês, ${nomePeriodo(k, false).replace(/^em /, "")}. A equipe do gabinete aparece à parte.`))),
      h("div", { class: "legenda" }, h("span", null, h("span", { class: "chave chave--ganha" }), "Vai para o bolso"), h("span", null, h("span", { class: "chave chave--custa" }), gastosNome(p)),
        p.k === "j" ? p.cg.map((c) => h("span", null, h("span", { class: `chave chave--faixa faixa-cargo--${S.porId.get(c.id) ? S.porId.get(c.id).k : "e"}` }), `Mês como ${c.g.split(/[ -]/)[0].toLowerCase()}`)) : null),
      caixa,
      tabela(["Mês", "Bolso", gastosNome(p), "Custo total"], pontos.map((q) => [nomeMes(q), reais(q.g), reais(q.c), `${q.ra ? "≈ " : ""}${reais(q.g + q.c)}`])),
      h("ul", { class: "lista nota" },
        pontos.some((q) => q.ra) ? h("li", null, casaBase(p) === "d"
          ? "≈ O auxílio-moradia é informado por ano. Dividimos o total pelos meses com salário, então o valor de cada mês é aproximado."
          : "≈ Passagens, correios e outros gastos do Senado são informados por ano. Dividimos o total pelos meses com salário, então o valor de cada mês é aproximado.") : null,
        (casaBase(p) !== "d" && p.k !== "v" && p.k !== "p") || p.k === "j" ? h("li", null, "Os meses mais altos costumam ter o 13º salário, pago de uma vez.") : null,
        p.k === "p" ? h("li", null, "Meses mais altos: férias, 13º ou pagamentos atrasados, que a Prefeitura soma no mês em que paga.") : null,
        p.k === "v" && ocupacaoTxt(p) ? h("li", null, "Mês com salário menor: o vereador ficou só parte do mês no cargo.") : null,
        p.k === "j" ? h("li", null, "A faixa embaixo das colunas mostra em qual cargo a pessoa estava em cada mês.") : null,
        p.k === "e" ? h("li", null, "As viagens entram no mês em que começaram. Os salários saem no Portal com uns 2 meses de atraso.")
          : p.k === "p" ? h("li", null, "A Prefeitura publica a folha de cada mês no fim do próprio mês.")
          : p.k === "v" ? h("li", null, notaMensalVereador(p))
          : h("li", null, "Os 3 últimos meses ainda podem receber notas da cota.")));
    requestAnimationFrame(() => graficoColunas(caixa, pontos,
      [{ k: "g", cls: "seg-ganha" }, { k: "c", cls: "seg-custa" }],
      (q) => [linhaDica("ganha", reais(q.g), "para o bolso"), linhaDica("custa", reais(q.c), `em ${gastosNome(p).toLowerCase()}`), h("div", null, "Custo total ", h("strong", null, reais(q.g + q.c))),
        q.ra ? h("div", { class: "pequeno" }, `≈ inclui ${reais(q.ra)} de valores informados por ano, divididos por mês`) : null,
        p.k === "j" && cargoNoMes(p, q.aaaamm) ? h("div", { class: "pequeno" }, cargoNoMes(p, q.aaaamm) === "e" ? "Neste mês: ministro" : "Neste mês: no Congresso") : null],
      p.k === "j" ? (q) => cargoNoMes(p, q.aaaamm) : null));
    return card;
  }
  function secEquipe(p, k) {
    const r = resumo(p, k);
    const pontos = pontosDoPeriodo(p, k).filter((q) => q.e);
    if (!r || !r.em || !pontos.length) return null;
    const C = colegas(grupo(p), k);
    const cv = p.k === "v" ? camaraDe(p.cid) : null;
    const maxCargo = p.eq ? Math.max(...p.eq.c.map(([, n]) => n)) : 0;
    const caixa = h("div", { class: "grafico" });
    const card = h("article", { class: "cartao", id: "equipe" },
      h("div", { class: "cartao__cabeca" }, h("div", null, h("h2", { class: "h3" }, "Equipe do gabinete"),
        h("p", { class: "pequeno discreto" }, `Dinheiro público que paga as pessoas que trabalham para ${p.n}. Não vai para o bolso de ${p.n}.`))),
      h("div", { class: "estatisticas" },
        estatistica("Custo da equipe por mês", reais(r.em), C.em ? `Mediana: ${reais(C.em)}` : null),
        estatistica("Pessoas", num(r.pessoas, r.pessoas < 10 ? 1 : 0), C.pessoas ? `Mediana: ${num(C.pessoas, 0)}` : null),
        estatistica("Média por pessoa", r.porPessoa ? reais(r.porPessoa) : "—", C.porPessoa ? `Mediana: ${reais(C.porPessoa)}` : null)),
      caixa,
      tabela(["Mês", "Custo da equipe", "Pessoas", "Por pessoa"], pontos.map((q) => [nomeMes(q), reais(q.e), q.pes ? String(q.pes) : "—", q.pes ? reais(q.e / q.pes) : "—"]), "Equipe do gabinete, mês a mês"),
      p.eq && p.eq.c.length ? h("div", { class: "barras" }, h("div", { class: "barras__cabeca" }, h("span", null, `Cargos em ${fmtMes(mesEquipe(cv))}`), h("span", null, "Pessoas")),
        p.eq.c.map(([cargo, n]) => barra(cargo, String(n), n / maxCargo, "barra__fill--equipe"))) : null,
      h("p", { class: "nota" }, cv ? `${cv.equipe_nota || "Assessores do gabinete, pela folha de pagamento da Câmara."} Contamos quem recebeu no mês, mesmo que só parte dele.` : casaBase(p) === "d"
        ? "Na Câmara, cada deputado tem até R$ 165.806,07 por mês para pagar até 25 secretários parlamentares. Contamos quem trabalhou no gabinete em cada mês, mesmo que só parte dele."
        : "No Senado, os assessores são pagos direto pela folha. Ligamos a folha à lotação de cada comissionado: é uma estimativa, mais precisa nos meses recentes."));
    requestAnimationFrame(() => graficoColunas(caixa, pontos, [{ k: "e", cls: "seg-equipe" }],
      (q) => [linhaDica("equipe", reais(q.e), "com a equipe"), q.pes ? h("div", null, `${q.pes} pessoas · `, h("strong", null, reais(q.e / q.pes)), " por pessoa") : null]));
    return card;
  }
  // Vereador: a Câmara publica quem trabalha em cada gabinete (retrato do mês), mas não os salários sem CPF
  function secEquipeVereador(p) {
    if (!p.eq) return null;
    const c = camaraDe(p.cid);
    const med = mediana(S.D.p.filter((q) => q.k === "v" && q.cid === p.cid && q.eq).map((q) => q.eq.n));
    const max = Math.max(...p.eq.c.map(([, n]) => n));
    return h("article", { class: "cartao", id: "equipe" },
      h("div", { class: "cartao__cabeca" }, h("div", null, h("h2", { class: "h3" }, "Equipe do gabinete"),
        h("p", { class: "pequeno discreto" }, `Quem trabalha para ${p.n}, em ${fmtMes(mesEquipe(c))}. É pago com dinheiro público, mas não vai para o bolso de ${p.n}.`))),
      h("div", { class: "estatisticas" },
        estatistica("Pessoas", String(p.eq.n), med ? `Mediana dos vereadores: ${num(med, 0)}` : null),
        estatistica("Custo da equipe", "não publicado", p.cid === SP ? "a Câmara só mostra os salários para quem informa um CPF" : "a Câmara não publica")),
      h("div", { class: "barras" }, h("div", { class: "barras__cabeca" }, h("span", null, "Cargo"), h("span", null, "Pessoas")),
        p.eq.c.map(([cargo, n]) => barra(cargo, String(n), n / max, "barra__fill--equipe"))),
      h("p", { class: "nota" }, p.cid === SP ? "Cargos de confiança, escolhidos pelo vereador. “Servidor cedido” é funcionário de outro órgão público emprestado à Câmara. A lista é da Câmara, atualizada todo mês; mostramos o mês mais recente."
        : `${c.equipe_nota || "Assessores do gabinete, pela folha de pagamento da Câmara."} Mostramos o mês mais recente.`));
  }
  // ---------------------------------------------------------------- detalhe dos gastos por tipo
  const divisorCat = (r, cat) => (ORDEM_GANHA.includes(cat) ? r.mg : ORDEM_EQUIPE.includes(cat) ? r.me : r.mc);
  // [[nome do tipo, total no período], ...] de uma categoria, com "Outros tipos" para o que sobra
  function detalheCat(p, k, cat) {
    const r = resumo(p, k);
    const d = (p.dt && p.dt[k] && p.dt[k][cat]) || [];
    if (!r || !d.length) return null;
    const base = cat === "fornecedores" ? "verba_gabinete" : cat; // fornecedores: a mesma verba, dividida por quem recebeu
    const total = r.cats[base] || 0;
    const linhas = d.map(([i, v]) => [typeof i === "number" ? meta().tipos[i] : i, v]);
    const resto = total - linhas.reduce((a, [, v]) => a + v, 0);
    if (total && resto > 0 && resto / total >= 0.005) linhas.push([cat === "fornecedores" ? "Outros fornecedores" : "Outros tipos", resto]);
    return { total, linhas, div: divisorCat(r, base) || 1 };
  }
  const pctTxt = (v, total) => { const x = total ? (v / total) * 100 : 0; return x < 1 ? "<1%" : `${num(x, 0)}%`; };
  const viagensPorMes = (p, k) => { const r = resumo(p, k); return p.nv && p.nv[k] && r ? p.nv[k] / r.m : null; };
  // os maiores tipos de gasto por mês (para a imagem): [[nome, valor por mês], ...]
  function maioresGastos(p, k, n) {
    const itens = [];
    for (const c of ORDEM_CUSTA) {
      const det = detalheCat(p, k, c);
      if (det) det.linhas.forEach(([t, v]) => { if (t !== "Outros tipos") itens.push([t, v / det.div]); });
    }
    return itens.sort((a, b) => b[1] - a[1]).slice(0, n);
  }
  function secCota(p, k) {
    const r = resumo(p, k);
    if (!r) return null;
    const G_E = [["viagens_oficiais", "Viagens oficiais (como ministro)", ""], ["jetons", "Jetons, por conselho", "barra__fill--ganha"]];
    const G_P = [["cota_parlamentar", "Cota parlamentar", ""], ["outros_gastos_mandato", "Outros gastos do mandato", ""]];
    const G_V = [["verba_gabinete", "Por tipo de despesa", ""], ["fornecedores", "Para quem foi o dinheiro (maiores fornecedores)", ""]];
    const grupos = (p.k === "e" ? G_E : p.k === "j" ? [...G_P, ...G_E] : p.k === "v" ? G_V : G_P)
      .map(([cat, titulo, cls]) => ({ cat, titulo, cls, det: detalheCat(p, k, cat) })).filter((g) => g.det && g.det.total >= 1);
    if (!grupos.length) return null;
    const notas = [`Média por mês: o total de cada tipo ${nomePeriodo(k, false)} dividido pelos meses. É uma aproximação: os gastos mudam muito de um mês para outro (uma passagem cara num mês, nada no outro).`];
    const estat = [];
    for (const g of grupos) {
      if (g.cat === "cota_parlamentar") {
        estat.push(estatistica("Cota por mês", reais(g.det.total / g.det.div), "em média"));
        if (g.det.linhas.some(([t]) => t.endsWith("*"))) notas.push("* Desde agosto de 2025, a Câmara deixou de publicar nos dados abertos as passagens compradas pelo próprio sistema. Usamos o total do site oficial, que não tem o detalhe por tipo.");
        if (p.k === "d" && k === anoAtual() && meta().limites_cota_camara[p.uf]) {
          const lim = meta().limites_cota_camara[p.uf];
          notas.push(`A cota por mês é ${num((g.det.total / g.det.div / lim) * 100, 0)}% do limite de ${reais(lim)} por mês para ${ESTADOS[p.uf]}.`);
        }
      }
      if (g.cat === "outros_gastos_mandato") notas.push("Outros gastos do mandato: o Senado informa por ano; dividimos pelos meses com salário.");
      if (g.cat === "viagens_oficiais") {
        estat.push(estatistica("Viagens por mês", reais(g.det.total / g.det.div), "diárias e passagens, em média"));
        const vpm = viagensPorMes(p, k);
        if (vpm) estat.push(estatistica("Número de viagens", num(vpm, vpm < 10 ? 1 : 0), `por mês (${p.nv[k]} ${nomePeriodo(k, false)})`));
        notas.push("Voos em aviões da FAB não têm custo publicado: entram só as passagens compradas e as diárias.");
      }
      if (g.cat === "jetons") estat.push(estatistica("Jetons por mês", reais(g.det.total / g.det.div), "vão para o bolso"));
      if (g.cat === "verba_gabinete") {
        const c = camaraDe(p.cid), lim = limiteVerba(p, k);
        estat.push(estatistica("Verba usada por mês", reais(g.det.total / g.det.div), "em média"));
        if (lim) estat.push(estatistica("Do limite", `${num((g.det.total / lim) * 100, 0)}%`, `usou ${reais(g.det.total)} de ${reais(lim)} ${nomePeriodo(k, false)}`));
        const vms = Object.entries(c.verba_mes || {});
        const vm = vms.length && vms.every(([, v]) => Math.abs(v - vms[0][1]) < 1) ? reais(vms[0][1]) : vms.map(([a, v]) => `${reais(v)} em ${a}`).join(" e ");
        notas.push(`${c.verba_nome ? `${c.verba_nome}. ` : ""}${vm ? `Cada vereador pode gastar até ${vm} por mês. ` : ""}${c.verba_regra || ""}`.trim());
        const sobra = sobraVerba(p, k);
        if (sobra.length) notas.push(sobra.map(([a, v]) => `Em ${a}, sobraram ${reais(v)} da verba de ${p.n}, que voltaram para a Câmara.`).join(" "));
        notas.push(...(c.verba_notas || []));
      }
      if (g.cat === "fornecedores" && g.det.linhas.some(([t]) => t.startsWith("Pessoa física"))) notas.push("Pessoa física: aluguel de imóvel pago a uma pessoa. O nome está nos dados da Câmara; aqui não mostramos.");
    }
    const cv = p.k === "v" ? camaraDe(p.cid) || {} : null;
    const titulo = p.k === "e" ? "Viagens e jetons, por mês" : p.k === "j" ? "Para onde vão os gastos dos cargos, por mês" : p.k === "v" ? "Para onde vai a verba do gabinete, por mês"
      : grupos.length > 1 ? "Para onde vão os gastos do mandato, por mês" : "Para onde vai a cota parlamentar, por mês";
    const sub = p.k === "e" ? `Quanto vai para cada tipo por mês, em média, ${nomePeriodo(k, false)}.`
      : p.k === "v" ? `${cv.verba_por_nota ? "Despesas do gabinete pagas com nota fiscal" : "Despesas do gabinete, por tipo (a Câmara não publica os fornecedores)"}. Média por mês ${nomePeriodo(k, false)}.`
      : `Passagens, combustível, alimentação, escritório e outras despesas reembolsadas. Média por mês ${nomePeriodo(k, false)}.`;
    return h("article", { class: "cartao", id: "cota" },
      h("div", { class: "cartao__cabeca" }, h("div", null, h("h2", { class: "h3" }, titulo), h("p", { class: "pequeno discreto" }, sub))),
      h("div", { class: "estatisticas" }, estat),
      grupos.map((g) => {
        const max = Math.max(...g.det.linhas.map(([, v]) => v));
        return h("div", { class: "barras" },
          h("div", { class: "barras__cabeca" }, h("span", null, g.titulo), h("span", null, "Por mês · %")),
          g.det.linhas.map(([t, v]) => barra(t, `${reais(v / g.det.div)}/mês · ${pctTxt(v, g.det.total)}`, v / max, g.cls)));
      }),
      notas.map((n) => h("p", { class: "nota" }, n)));
  }
  function secComparar(p, k) {
    const card = h("article", { class: "cartao", id: "comparar" },
      h("div", { class: "cartao__cabeca" }, h("div", null, h("h2", { class: "h3" }, "Comparar com outro parlamentar"),
        h("p", { class: "pequeno discreto" }, `${Object.keys(CAM.cidades).length ? "Deputado, senador, ministro ou vereador das capitais com dados" : "Da Câmara, do Senado ou do governo federal"}. No mesmo período, quanto o outro custa a mais ou a menos por mês.`))));
    const input = h("input", { type: "search", id: "busca-comparar", placeholder: "Quem? Ex.: Haddad, PT ou Bahia", autocomplete: "off" });
    const sug = h("div", { class: "sugestoes", hidden: true });
    add(card, h("div", { class: "busca-caixa", style: "max-width:520px" }, h("label", { class: "visualmente-oculto", for: "busca-comparar" }, "Comparar com"), input, sug));
    ligarBusca(input, sug, (q) => { evento("comparar", { parlamentar: p.n, outro: q.n }); S.outro = q.id; render(); irPara("comparar"); }, (q) => q.id !== p.id);
    const o = S.outro && S.porId.get(S.outro);
    if (o) {
      const r1 = resumo(p, k), r2 = resumo(o, k);
      if (!r2) add(card, h("p", { class: "discreto" }, `${o.n} não tem mandato ${nomePeriodo(k, false)}. Escolha outro período acima.`));
      else if (r1) {
        const linhas = [
          ["Vai para o bolso", (r) => r.gm, reais], ["Gastos do mandato ou do cargo", (r) => r.cm, reais], ["Jetons", (r) => porMes(r, "jetons"), reais], ["Custo por mês", (r) => r.tm, reais],
          ["Cota parlamentar", (r) => porMes(r, "cota_parlamentar"), reais], ["Verba do gabinete (vereador)", (r) => porMes(r, "verba_gabinete"), reais],
          ["Equipe do gabinete", (r) => r.em, reais], ["Pessoas na equipe", (r) => r.pessoas, (v) => num(v, 0)], ["Por pessoa da equipe", (r) => r.porPessoa, reais]];
        add(card, rolagem("Comparação", h("table", { class: "comp-tabela" },
          h("thead", null, h("tr", null, h("th", null, nomePeriodo(k, true)), h("th", null, p.n), h("th", null, o.n), h("th", null, "Diferença"))),
          h("tbody", null, linhas.filter(([, f]) => f(r1) || f(r2)).map(([nome, f, fmt]) => {
            const a = f(r1), b = f(r2), dif = b - a, pct = a ? Math.round((dif / a) * 100) : null;
            const igual = fmt === reais ? Math.abs(dif) < 1 : Math.abs(dif) < 0.5;
            return h("tr", null, h("td", null, nome), h("td", { class: "num" }, fmt(a)), h("td", { class: "num" }, fmt(b)),
              h("td", { class: igual ? "" : dif > 0 ? "dif-mais" : "dif-menos" }, igual ? "igual" : `${dif > 0 ? "+" : "−"}${fmt(Math.abs(dif))}${pct !== null ? ` (${pct > 0 ? "+" : ""}${pct}%)` : ""}`));
          })))),
          h("div", { class: "acoes" },
            h("a", { href: urlDe(o.id), class: "pequeno", onclick: () => { S.origem = "comparar"; } }, `Ver o contracheque de ${o.n}`),
            h("button", { type: "button", class: "link-botao pequeno", onclick: () => { S.outro = null; render(); irPara("comparar"); } }, "Tirar da comparação")),
          (p.k === "s" || o.k === "s") ? h("p", { class: "nota" }, "A equipe do Senado é uma estimativa. Para deputados, ainda faltam o 13º, a ajuda de custo e as diárias.") : null);
      }
    }
    return card;
  }
  // Resumo para compartilhar: a própria imagem, grande, com enviar / copiar / baixar; o texto fica à parte, para quem prefere.
  // A mesma seção no fim da página do político, da cidade (com o gasto informado) e do governador.
  function secCompartilhar(spec, nota) {
    if (!spec || !spec.gerar) return null;
    const onde = "secao";
    const retorno = h("p", { class: "compartilhar-img__retorno", role: "status" });
    const img = h("img", { class: "compartilhar-img__previa", width: 1080, height: 1350, alt: spec.alt });
    const quadro = h("div", { class: "compartilhar-img__quadro carregando" }, img);
    const botoes = h("div", { class: "acoes" }, h("button", { type: "button", class: "botao", disabled: true }, "Preparando a imagem…"));
    obterImagem(spec).then((a) => {
      botoes.textContent = "";
      if (!a.blob) { retorno.textContent = "Não deu para gerar a imagem neste navegador."; return; }
      img.src = a.url; quadro.classList.remove("carregando");
      add(botoes, acoesImagem(spec, a, retorno, onde));
    }, () => { botoes.textContent = ""; retorno.textContent = "Não deu para gerar a imagem neste navegador."; });
    return h("section", { class: "bloco", id: "resumo" },
      h("p", { class: "rotulo" }, "Resumo para compartilhar"),
      h("h2", null, "Mande a imagem para quem você quiser"),
      h("div", { class: "compartilhar-img" },
        quadro,
        h("div", { class: "compartilhar-img__lado" },
          h("div", { class: "cartao compartilhar-img__opcao" },
            h("h3", null, "Imagem"),
            h("p", { class: "pequeno discreto" }, dicaImagem()),
            botoes, retorno),
          spec.textoZap ? h("div", { class: "cartao compartilhar-img__opcao" }, opcoesTexto(spec, onde, spec.link, true)) : null,
          nota ? h("p", { class: "nota" }, nota) : null)));
  }
  function secResumo(p, k) {
    return secCompartilhar(specPessoa(p, k), `A imagem e o texto mostram o período escolhido no contracheque (${nomePeriodo(k, true)}). Dados abertos oficiais ${fonteDados(p)}.`);
  }

  // ================================================================== câmaras municipais (vereadores)
  // Carregado à parte (dados/municipios.json), para não pesar a primeira visita.
  const CID = { m: null, meta: null, porId: new Map(), ver: {}, carregando: null };
  function carregarCidades() {
    if (!CID.carregando) {
      CID.carregando = fetch("/dados/municipios.json").then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); }).then((d) => {
        CID.meta = d.meta;
        // sm: salário médio mensal do pessoal assalariado formal da cidade (IBGE, Cempre), em reais do ano meta.salario_medio_ano
        CID.m = d.m.map(([cod, n, uf, pop, cap, nv, custo, ano, sm]) => ({ cod, id: `cid-${cod}`, n, uf, pop, cap, nv, custo, ano, sm }));
        CID.m.forEach((c) => CID.porId.set(c.id, c));
        CID.porSlug = new Map(CID.m.map((c) => [urlCidade(c).slice("/cidade/".length), c]));
        // mediana do custo por habitante em cada faixa de população; valor muito abaixo dela é suspeito
        // (parte do gasto da Câmara deve ter sido informada em outra função nas contas da prefeitura)
        CID.med = CID.meta.faixas_teto.map((_, i) => mediana(CID.m.filter((c) => c.custo > 0 && c.pop > 0 && faixaDe(c.pop) === i).map(porHabMes)));
        CID.m.forEach((c) => { c.suspeito = c.custo > 0 && c.pop > 0 && porHabMes(c) < 0.3 * CID.med[faixaDe(c.pop)]; });
        return CID;
      });
    }
    return CID.carregando;
  }
  const carregarVereadores = (uf) => (CID.ver[uf] = CID.ver[uf] || fetch(`/dados/vereadores/${uf}.json`).then((r) => r.json()));
  const reaisC = (v) => v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" }).replace(/ /g, " ");
  const temCusto = (c) => c.custo > 0 && c.pop > 0 && !c.suspeito;
  const porHabMes = (c) => c.custo / c.pop / 12;
  const faixaDe = (pop) => CID.meta.faixas_teto.findIndex(([lim]) => lim === null || pop <= lim);
  const tetoVereador = (pop) => CID.meta.faixas_teto[faixaDe(pop)][1] * CID.meta.teto_deputado_estadual;
  // Salário médio da cidade (IBGE), ao lado do salário do vereador. É de outro ano (meta.salario_medio_ano) que o salário
  // ou o teto de hoje: os dois anos aparecem no texto.
  function estatSalarioMedio(c) {
    if (!(c.sm > 0)) return null;
    const M = CID.meta || {};
    return estatistica("Salário médio na cidade", reais(c.sm), h("span", null, `por mês em ${M.salario_medio_ano || ""}: trabalhadores com carteira e servidores (`,
      h("a", { href: M.link_salario_medio, target: "_blank", rel: "noopener", title: M.fonte_salario_medio || "" }, "IBGE\u00a0↗"), ")"));
  }
  // quanto o salário do vereador (ou o teto) fica acima do salário médio da cidade; oQue diz qual valor e de quando
  function comparaSalarioMedio(c, valor, oQue) {
    if (!(c.sm > 0) || !(valor > 0)) return null;
    const dif = valor / c.sm - 1, pct = Math.round(Math.abs(dif) * 100);
    return estatistica(dif >= 0 ? "Acima do salário médio" : "Abaixo do salário médio", `${dif >= 0 ? "+" : "−"}${num(pct, 0)}%`,
      `${oQue} é ${num(valor / c.sm, 1)} vezes o salário médio da cidade em ${(CID.meta || {}).salario_medio_ano || ""}`);
  }
  // salário mínimo do ano (para o "ganha mais que X% dos brasileiros que trabalham")
  const smDoAno = (ano) => meta().salario_minimo[ano] || meta().salario_minimo[anoAtual()];
  function nomeFaixa(i) {
    const f = CID.meta.faixas_teto, ant = i ? f[i - 1][0] : 0, lim = f[i][0];
    return lim === null ? `mais de ${num(ant, 0)} habitantes` : i === 0 ? `até ${num(lim, 0)} habitantes` : `entre ${num(ant + 1, 0)} e ${num(lim, 0)} habitantes`;
  }
  function encontrarCidades(q, n = 4) {
    if (!CID.m) return [];
    const t = semAcento(q).trim();
    if (t.length < 3) return [];
    return CID.m.filter((c) => semAcento(`${c.n} ${c.uf}`).includes(t) || semAcento(`${c.n} ${ESTADOS[c.uf]}`).includes(t))
      .sort((a, b) => (semAcento(a.n).startsWith(t) ? 0 : 1) - (semAcento(b.n).startsWith(t) ? 0 : 1) || b.pop - a.pop).slice(0, n);
  }
  function avatarCidade(tam) {
    const lado = tam === "g" ? 34 : 18;
    const svg = s("svg", { viewBox: "0 0 24 24", width: lado, height: lado });
    svg.append(s("path", { fill: "currentColor", d: "M12 2 2 7v2h20V7L12 2Zm-7 9v7h3v-7H5Zm5.5 0v7h3v-7h-3ZM16 11v7h3v-7h-3ZM2 20v2h20v-2H2Z" }));
    return h("span", { class: `avatar avatar--${tam} avatar--cidade`, "aria-hidden": "true" }, svg);
  }
  const iconeCidade = (el) => el;
  const irParaCidade = (c, de) => { S.origem = de; navegar(urlCidade(c)); };
  // O que há de errado com os dados de uma cidade (null = nada)
  const anoRecente = () => Math.max(...CID.m.map((c) => c.ano || 0));
  function problemaCidade(c) {
    if (!(c.custo > 0)) return { tipo: "sem", curto: "sem o gasto da Câmara" };
    if (c.suspeito) return { tipo: "suspeito", curto: "valor muito baixo" };
    if (c.ano && c.ano < anoRecente()) return { tipo: "antigo", curto: `contas de ${anoRecente()} não entregues` };
    return null;
  }
  // Tribunal de contas que fiscaliza as prefeituras (BA, GO e PA têm um só para os municípios)
  const tribunal = (uf) => (["BA", "GO", "PA"].includes(uf) ? `Tribunal de Contas dos Municípios do Estado de ${ESTADOS[uf]}` : `Tribunal de Contas do Estado de ${ESTADOS[uf]}`);
  const busca = (q) => `https://www.google.com/search?q=${encodeURIComponent(q)}`;
  function cobrarCidade(c, prob, med) {
    const ano = anoRecente();
    const oQue = prob.tipo === "sem"
      ? `não aparece o gasto da Câmara Municipal (a função 01 – Legislativa está vazia ou zerada, ou a declaração de ${ano} não foi entregue)`
      : prob.tipo === "suspeito"
        ? `o gasto da Câmara Municipal em ${c.ano} aparece como ${reais(c.custo)}, ou ${reaisC(porHabMes(c))} por habitante por mês, muito abaixo das cidades do mesmo tamanho (mediana de ${reaisC(med)}). Parece que parte do gasto foi informada em outra função`
        : `ainda não aparece a declaração de ${ano} (a mais recente é a de ${c.ano})`;
    const msg = [
      `Olá. Sou morador(a) de ${c.n} (${c.uf}).`,
      `Nas contas anuais que a Prefeitura envia ao Tesouro Nacional (Declaração de Contas Anuais, no Siconfi), ${oQue}.`,
      prob.tipo === "antigo" ? `Peço que a declaração de ${ano} seja entregue, como manda a Lei de Responsabilidade Fiscal.`
        : "Peço que verifiquem e, se for o caso, corrijam (retifiquem) a declaração, para que o gasto da Câmara Municipal apareça na função 01 – Legislativa.",
      `Com base na Lei de Acesso à Informação (Lei nº 12.527/2011), peço também o valor total gasto pela Câmara Municipal em ${ano}.`,
      "Obrigado(a).",
    ].join("\n\n");
    const retorno = h("p", { class: "compartilhar-img__retorno", role: "status" });
    const medir = (acao) => evento("cobrar_cidade", { acao, cidade: c.n, uf: c.uf, problema: prob.tipo });
    const link = (texto, q, acao) => h("a", { class: "botao botao--leve", href: busca(q), target: "_blank", rel: "noopener", onclick: () => medir(acao) }, texto);
    return h("div", { class: "cobrar" },
      h("h2", { class: "h3" }, `Mora em ${c.n}? Ajude a corrigir`),
      h("p", null, `Quem envia essas contas ao Tesouro Nacional é a Prefeitura de ${c.n} (setor de contabilidade), pelo Siconfi, até 30 de abril de cada ano. Qualquer pessoa pode pedir a correção.`),
      h("ol", { class: "lista" },
        h("li", null, "Copie a mensagem abaixo."),
        h("li", null, "Mande para a ouvidoria ou o e-SIC (pedido de acesso à informação) da Prefeitura. Vale mandar também para a Câmara Municipal."),
        h("li", null, `Se não responderem em 20 dias (o prazo da Lei de Acesso à Informação), procure o ${tribunal(c.uf)}.`)),
      h("textarea", { class: "cobrar__msg", readonly: true, rows: 12, "aria-label": "Mensagem para a prefeitura" }, msg),
      h("div", { class: "acoes" },
        h("button", { type: "button", class: "botao", onclick: () => { medir("copiar"); copiarTexto(msg, retorno, "Mensagem copiada. Agora é só colar no formulário da ouvidoria ou no e-mail."); } }, "Copiar a mensagem"),
        link("Achar a ouvidoria da Prefeitura", `ouvidoria e-SIC prefeitura de ${c.n} ${c.uf}`, "buscar_prefeitura"),
        link("Achar a Câmara Municipal", `Câmara Municipal de ${c.n} ${c.uf} ouvidoria`, "buscar_camara"),
        link("Achar o tribunal de contas", `${tribunal(c.uf)} ouvidoria`, "buscar_tribunal")),
      retorno);
  }
  function textoCidade(c) {
    const link = endereco() ? `${origem()}${urlCidade(c)}` : "", real = salarioReal(c);
    return [
      `*Câmara Municipal de ${c.n} (${c.uf})*`,
      temCusto(c) ? `Custa *${compacto(c.custo / 12)} por mês* (${reaisC(porHabMes(c))} por habitante, por mês), com ${c.nv} vereadores.` : `${c.nv} vereadores.`,
      real ? (real.folha ? `Um vereador recebe ${reais(real.v)} por mês pela folha da Câmara (mediana de 2025).` : `Cada vereador recebe ${reaisC(real.v)} por mês (desde ${fmtMes(real.desde)}).`)
        : `Um vereador daqui pode ganhar até ${reais(tetoVereador(c.pop))} por mês: é o teto da Constituição, e o salário fixado pela Câmara pode ser menor.`,
      real && c.sm > 0 ? `O salário médio na cidade era de ${reais(c.sm)} por mês em ${(CID.meta || {}).salario_medio_ano} (IBGE).` : null,
      "",
      `Dados abertos oficiais ${listaE(["do Tesouro Nacional", "do TSE", real ? "da Câmara Municipal" : null, real && c.sm > 0 ? "do IBGE" : null].filter(Boolean))}.`,
      `Veja a da sua cidade: ${link || "Contas do Poder"}`,
    ].filter((x) => x !== null).join("\n");
  }
  // O salário de verdade de um vereador da cidade, onde a Câmara publica (capitais com vereador por vereador): o
  // subsídio de hoje, igual para todos, ou, onde vem da folha, a mediana do que foi para o bolso em 2025. Nas outras
  // cidades só existe o teto da Constituição, e o site não compara o teto com nada: o salário pode ser bem menor.
  function salarioReal(c) {
    const cam = camaraDe(c.cod);
    if (!cam) return null;
    const sub = (cam.subsidio || [])[(cam.subsidio || []).length - 1];
    if (sub && !cam.subsidio_folha) return { v: sub[1], ano: anoAtual(), oQue: "o salário de hoje", desde: sub[0], folha: false };
    const C = colegas(`v${c.cod}`, "2025");
    return C.n && C.gm ? { v: C.gm, ano: "2025", oQue: "a mediana de 2025", folha: true } : null;
  }
  // Cidade com os dados de cada vereador (capitais): salário de verdade e a lista com link para cada um
  function vereadoresDaCidade(c) {
    const cam = camaraDe(c.cod);
    if (!cam) return null;
    const todos = S.D.p.filter((q) => q.k === "v" && q.cid === c.cod);
    const agora = todos.filter((q) => q.x).sort((a, b) => a.n.localeCompare(b.n, "pt-BR"));
    const sairam = todos.filter((q) => !q.x).sort((a, b) => a.n.localeCompare(b.n, "pt-BR"));
    const C = colegas(`v${c.cod}`, "2025");
    const sub = (cam.subsidio || [])[(cam.subsidio || []).length - 1];
    const teto = c.pop ? tetoVereador(c.pop) : null;
    const noTeto = sub && teto && Math.abs(sub[1] - teto) < 1;
    const temEquipe = todos.some((q) => q.eq) || cam.equipe_custo;
    // o salário de um vereador: o subsídio de hoje (igual para todos) ou, onde vem da folha, a mediana de 2025
    const sal = salarioReal(c);
    const chip = (q) => h("a", { class: "pessoa-chip", href: urlDe(q.id), onclick: () => { S.origem = "cidade"; } },
      avatar(q, "p"), q.n, h("small", null, `${q.pt || "sem partido"}${q.sup ? " · suplente" : ""}`));
    const partidos = {};
    agora.forEach((q) => { partidos[q.pt] = (partidos[q.pt] || 0) + 1; });
    const mulheres = agora.filter((q) => q.g === "Vereadora").length;
    return [
      h("div", { class: "estatisticas" },
        sub && !cam.subsidio_folha ? estatistica("Salário de cada vereador", reaisC(sub[1]), `por mês desde ${fmtMes(sub[0])}${noTeto ? ", o máximo que a Constituição permite" : ""}`)
          : C.n ? estatistica("Vai para o bolso de um vereador", reais(C.gm), "por mês em 2025, pela folha de pagamento da Câmara (mediana)") : null,
        // ao lado do salário: o salário médio da cidade, quanto acima ele fica e o "ganha mais que X%"
        estatSalarioMedio(c),
        sal ? comparaSalarioMedio(c, sal.v, sal.oQue) : null,
        sal ? estatisticaPop(sal.v / smDoAno(sal.ano)) : null),
      // numa linha à parte: o custo do mandato (salário + verba) e a equipe
      h("div", { class: "estatisticas" },
        C.n ? estatistica("Custo típico de um vereador", reais(C.tm), "por mês em 2025: salário + verba do gabinete (mediana)") : null,
        C.n && C.cm ? estatistica("Verba do gabinete usada", reais(C.cm), `por mês em 2025 (mediana)${(cam.verba_mes || {})["2025"] ? `, de até ${reais(cam.verba_mes["2025"])}` : ""}`) : null,
        C.n && C.em ? estatistica("Equipe de um gabinete", reais(C.em), `por mês em 2025 (mediana), à parte: vai para os assessores`) : null),
      (cam.notas || []).map((n) => h("p", { class: "nota" }, n)),
      h("h2", { class: "h3" }, `Os ${agora.length} vereadores no cargo, um a um`),
      h("p", { class: "discreto pequeno" }, `${Object.entries(partidos).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([pt, n]) => `${pt} ${n}`).join(" · ")} — ${mulheres} ${mulheres === 1 ? "mulher" : "mulheres"} de ${agora.length}. Toque num nome para ver o salário, a verba do gabinete mês a mês${temEquipe ? " e a equipe" : ""}.`),
      h("div", { class: "lista-estado__grupo" }, agora.map(chip)),
      sairam.length ? h("details", { class: "problemas" }, h("summary", null, `Quem ocupou um gabinete e saiu (${sairam.length})`), h("div", { class: "lista-estado__grupo" }, sairam.map(chip))) : null,
    ];
  }
  // a Câmara comparada com as das cidades do mesmo tamanho (faixa de população), por habitante: como na posição dos
  // políticos, "custa menos que X%" abaixo da mediana e "mais que X%" acima (sem cor de bom/ruim), arredondando para
  // baixo; lugar (de 0 a 100) é a posição na régua da imagem
  function comparacaoCidade(c) {
    const faixa = faixaDe(c.pop);
    const mesmos = CID.m.filter((x) => temCusto(x) && faixaDe(x.pop) === faixa);
    const med = mediana(mesmos.map(porHabMes));
    const outras = Math.max(1, mesmos.length - 1);
    const abaixo = mesmos.filter((x) => porHabMes(x) < porHabMes(c)).length, acima = mesmos.filter((x) => porHabMes(x) > porHabMes(c)).length;
    const pct = temCusto(c) && mesmos.length > 1 ? Math.floor((abaixo / outras) * 100) : null;
    const pctMais = pct === null ? null : Math.floor((acima / outras) * 100);
    const lugar = ((abaixo + Math.max(0, outras - abaixo - acima) / 2) / outras) * 100;
    return { faixa, mesmos, med, outras, pct, pctMais, lugar };
  }
  function secCidade(c) {
    const tem = temCusto(c) || c.suspeito;
    const detalhe = vereadoresDaCidade(c);
    const prob = problemaCidade(c);
    if (prob) evento("ver_problema_cidade", { cidade: c.n, uf: c.uf, problema: prob.tipo });
    const { faixa, mesmos, med, outras, pct, pctMais } = comparacaoCidade(c);
    const doEstado = CID.m.filter((x) => x.uf === c.uf && temCusto(x)).sort((a, b) => porHabMes(b) - porHabMes(a));
    const posUF = doEstado.findIndex((x) => x.cod === c.cod);
    const teto = tetoVereador(c.pop);
    const lista = h("div", { class: "vereadores" }, h("p", { class: "discreto pequeno" }, "Carregando os vereadores…"));
    if (!detalhe) carregarVereadores(c.uf).then((d) => {
      const vs = d[String(c.cod)] || [];
      lista.textContent = "";
      if (!vs.length) { lista.append(h("p", { class: "discreto pequeno" }, "Sem a lista de eleitos do TSE para esta cidade.")); return; }
      const partidos = {};
      vs.forEach(([, pt]) => { partidos[pt] = (partidos[pt] || 0) + 1; });
      const mulheres = vs.filter(([, , g]) => g === "F").length;
      add(lista,
        h("p", { class: "discreto pequeno" }, `${Object.entries(partidos).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([pt, n]) => `${pt} ${n}`).join(" · ")} — ${mulheres} ${mulheres === 1 ? "mulher" : "mulheres"} de ${vs.length}.`),
        h("div", { class: "lista-estado__grupo" }, vs.map(([nome, pt]) => h("span", { class: "pessoa-chip pessoa-chip--fixo" }, nome, h("small", null, pt)))));
    }, () => { lista.textContent = "Não foi possível carregar os vereadores."; });
    const caixa = h("div", { class: "grafico" });
    if (tem && mesmos.length > 5) requestAnimationFrame(() => graficoPontos(caixa, c.id, mesmos.map((x) => ({ id: x.id, n: x.n, sub: x.uf, v: porHabMes(x) })), reaisC));
    // imagem só para Câmara com o gasto informado; o texto, para todas
    const spec = specCidade(c) || { textoZap: textoCidade(c), link: endereco() ? `${origem()}${urlCidade(c)}` : "", medir: { conteudo: "cidade", cidade: c.n, uf: c.uf } };
    return h("article", { class: "cartao conta", id: "cidade" },
      h("div", { class: "conta__topo" }, iconeCidade(avatarCidade("g")),
        h("div", null,
          h("p", { class: "rotulo" }, "Câmara Municipal"),
          h("h1", { class: "conta__nome" }, `${c.n} (${c.uf})`),
          h("div", { class: "conta__sub" }, h("span", null, `${num(c.pop, 0)} habitantes · ${c.nv} vereadores${c.cap ? " · capital" : ""}`))),
        null),
      h("div", { class: "cidade__corpo" },
        tem ? h("div", { class: "estatisticas" },
          estatistica("Custo da Câmara por mês", compacto(c.custo / 12), `${compacto(c.custo)} em ${c.ano}`),
          estatistica("Por habitante", reaisC(porHabMes(c)), `por mês (${reais(c.custo / c.pop)} por ano)`),
          estatistica("Custo da Câmara por vereador", compacto(c.custo / 12 / Math.max(1, c.nv)), `por mês: todo o gasto da Câmara dividido pelos ${c.nv} vereadores (não é o salário)`)) :
          h("p", { class: "aviso aviso--forte" }, h("strong", null, "A Prefeitura não informou corretamente o gasto da Câmara. "), `Nas contas que ${c.n} enviou ao Tesouro Nacional, o gasto da Câmara Municipal não aparece (está vazio ou zerado, ou a declaração não foi entregue). Por isso não dá para mostrar quanto a Câmara custa.`),
        c.suspeito ? h("p", { class: "aviso aviso--forte" }, h("strong", null, "Este valor parece errado. "), `É muito menor que o das cidades do mesmo tamanho (mediana de ${reaisC(med)} por habitante, por mês). Provavelmente a Prefeitura informou parte do gasto da Câmara em outra função nas contas enviadas ao Tesouro Nacional. Por isso esta cidade fica fora das comparações.`) : null,
        prob && prob.tipo === "antigo" ? h("p", { class: "aviso" }, h("strong", null, `A Prefeitura ainda não entregou as contas de ${anoRecente()}. `), `Mostramos o gasto de ${c.ano}, o último informado ao Tesouro Nacional.`) : null,
        prob ? cobrarCidade(c, prob, med) : null,
        tem && pct !== null ? h("p", { class: "destaque" }, `Por habitante, a Câmara ${deCidade(c)} custa ${pctMais < 50 ? `mais que ${pct}%` : `menos que ${pctMais}%`} das outras ${outras} cidades do mesmo tamanho (${nomeFaixa(faixa)}). A mediana delas é ${reaisC(med)} por habitante, por mês.`) : null,
        tem && posUF >= 0 ? h("p", { class: "discreto" }, `${posUF + 1}ª mais cara por habitante entre as ${doEstado.length} cidades de ${ESTADOS[c.uf]} com dados.`) : null,
        tem && mesmos.length > 5 ? h("div", null, h("p", { class: "discreto pequeno", style: "margin:0 0 4px" }, `Cada ponto é uma cidade com ${nomeFaixa(faixa)}: custo da Câmara por habitante, por mês. Toque num ponto para ver qual é.`), caixa) : null,
        detalhe || [h("div", { class: "estatisticas" },
          estatistica("Salário máximo do vereador", `até ${reais(teto)}`, "por mês hoje, pela Constituição"),
          estatSalarioMedio(c)),
        h("p", { class: "nota" }, `A Constituição (art. 29) deixa uma cidade com ${nomeFaixa(faixa)} pagar ao vereador até ${num(CID.meta.faixas_teto[faixa][1] * 100, 0)}% do salário do deputado estadual, que é no máximo ${reais(CID.meta.teto_deputado_estadual)}. Esse é o teto: o salário de cada vereador é fixado pela própria Câmara e pode ser menor. Como ainda não há uma fonte nacional com esse salário, aqui não comparamos o teto com o salário médio da cidade.`),
        h("h2", { class: "h3" }, `Os ${c.nv} vereadores eleitos em 2024`), lista],
        fimCompartilhar(spec),
        h("ul", { class: "lista nota" },
          h("li", null, `Custo da Câmara: tudo o que ela gastou em ${c.ano || "no ano"} (salários de vereadores e servidores, prédio, contratos), segundo as contas que a prefeitura entregou ao Tesouro Nacional (Siconfi, função Legislativa). Não é o salário de cada vereador.`),
          detalhe ? h("li", null, "Vereadores: quem ocupa cada gabinete hoje, com os suplentes que assumiram, segundo a própria Câmara. Salário, verba do gabinete e equipe de cada um vêm dos dados abertos da Câmara Municipal.")
            : h("li", null, "Vereadores: eleitos em 2024, segundo o TSE. Quem assumiu depois (suplentes) ainda não aparece."))));
  }
  // Prefeitura: prefeito, vice, secretários (e subprefeitos, em São Paulo), com link para cada um
  function secPrefeitura(c) {
    const pref = prefeituraDe(c.cod);
    if (!pref) return null;
    const todos = S.D.p.filter((q) => q.k === "p" && q.cid === c.cod);
    const agora = todos.filter((q) => q.x), sairam = todos.filter((q) => !q.x);
    const linha = (q) => pessoaLinha(q, pastaCurtaP(q), urlDe(q.id), () => { S.origem = "cidade"; });
    const ultimoValor = (tp) => { const q = agora.find((x) => x.tp === tp && !x.ced); return q ? (q.t.find((t) => t[0] === pref.ultimo_mes) || [])[1] : null; };
    const tipico = (tp) => mediana(agora.filter((x) => x.tp === tp && !x.ced).map((x) => (x.t.find((t) => t[0] === pref.ultimo_mes) || [])[1]).filter(Boolean));
    // grupo com mais de 8 pessoas começa fechado
    const grupo = (titulo, tps, nome) => {
      const g = agora.filter((q) => tps.includes(q.tp));
      if (!g.length) return null;
      return g.length > 8 ? listaFechada(`${titulo} (${g.length})`, nome, listaPessoas(g.map(linha)))
        : [h("p", { class: "rotulo", style: "margin:6px 0 0" }, `${titulo} (${g.length})`), listaPessoas(g.map(linha))];
    };
    return h("section", { class: "bloco", id: "prefeitura" },
      h("p", { class: "rotulo" }, "Prefeitura"),
      h("h2", null, `Quanto recebem o prefeito, os secretários${agora.some((q) => q.tp === "sb") ? " e os subprefeitos" : ""} ${deCid(c.cod)}`),
      h("p", { class: "discreto" }, `Pela folha de pagamento que a Prefeitura publica todo mês, com o nome de cada um. Valores brutos de ${fmtMes(pref.ultimo_mes)}.`),
      h("article", { class: "cartao" },
        h("div", { class: "estatisticas" },
          ultimoValor("pr") ? estatistica(agora.find((x) => x.tp === "pr").g.startsWith("Prefeita") ? "Prefeita" : "Prefeito", reais(ultimoValor("pr")), `em ${fmtMes(pref.ultimo_mes)}`) : null,
          tipico("se") ? estatistica("Secretário municipal", reais(tipico("se")), "típico (mediana)") : null,
          tipico("sb") ? estatistica("Subprefeito", reais(tipico("sb")), "típico (mediana)") : null),
        grupo("Prefeito e vice", ["pr", "vp"], "prefeito"), grupo("Secretários", ["se"], "secretarios"), grupo("Subprefeitos", ["sb"], "subprefeitos"),
        sairam.length ? listaFechada(`Quem passou pela Prefeitura desde 2025 e saiu (${sairam.length})`, "sairam_prefeitura", listaPessoas(sairam.map(linha))) : null,
        h("p", { class: "nota" }, "Só o que cada um recebe: a Prefeitura não publica os gastos por pessoa (carro oficial, viagens, equipe). Quem tem decisão judicial para não aparecer na folha não aparece aqui."),
        pref.salario_nota ? h("p", { class: "nota" }, pref.salario_nota) : null,
        (pref.notas || []).map((n) => h("p", { class: "nota" }, n)),
        h("p", { class: "nota" }, "Fonte: ", h("a", { href: pref.fonte, target: "_blank", rel: "noopener" }, "folha de pagamento publicada pela Prefeitura"), ".")));
  }
  // chamada para as capitais com vereador por vereador ou com a Prefeitura
  function destaqueCapitais(atual) {
    const cods = [...new Set([...cidadesCamara(), ...cidadesPrefeitura()].map((c) => c.cod))];
    const cs = cods.map((cod) => ({ ...(camaraDe(cod) || prefeituraDe(cod)), cod })).filter((c) => !atual || c.cod !== atual.cod)
      .sort((a, b) => (b.cod === SP) - (a.cod === SP) || a.n.localeCompare(b.n, "pt"));
    if (!cs.length) return null;
    const n = S.D.p.filter((q) => q.k === "v" && q.x).length;
    return h("div", { class: "cartao destaque-cidade" },
      h("span", { class: "etiqueta" }, "Novo"),
      h("strong", null, "Capitais, pessoa por pessoa"),
      h("span", { class: "pequeno discreto" }, [
        cidadesCamara().length ? `${n} vereadores em ${cidadesCamara().length} capitais: salário, verba do gabinete mês a mês e, onde a Câmara publica, a equipe de cada gabinete.` : null,
        cidadesPrefeitura().length ? `O prefeito, o vice e os secretários ${cidadesPrefeitura().length === 1 ? deCid(cidadesPrefeitura()[0].cod) : `de ${listaE(cidadesPrefeitura().map((c) => c.n))}`}: quanto cada um recebe, mês a mês.` : null,
      ].filter(Boolean).join(" ")),
      h("div", { class: "lista-estado__grupo" }, cs.map((c) => h("a", { class: "pessoa-chip", href: urlCidade(c), onclick: () => { S.origem = "destaque_capitais"; } },
        c.n, h("small", null, [c.uf, camaraDe(c.cod) ? `${S.D.p.filter((q) => q.k === "v" && q.x && q.cid === c.cod).length} vereadores` : null, prefeituraDe(c.cod) ? "Prefeitura" : null].filter(Boolean).join(" · "))))));
  }
  // Seção da página inicial (e embaixo da página de uma cidade): procurar a cidade e as mais caras do estado
  function secCamaras(atual) {
    const sec = h("section", { class: "bloco", id: "cidades" });
    const corpo = h("div", { style: "display:grid;gap:12px" }, h("p", { class: "discreto" }, "Carregando as câmaras…"));
    let uf = atual ? atual.uf : S.ufLista || "SP", completo = false;
    const input = h("input", { type: "search", id: "busca-cidade", placeholder: "Sua cidade. Ex.: Campinas", autocomplete: "off" });
    const sug = h("div", { class: "sugestoes", hidden: true });
    input.addEventListener("input", () => {
      sug.textContent = "";
      encontrarCidades(input.value, 8).forEach((c) => sug.append(h("button", { type: "button", class: "sugestao", onclick: () => irParaCidade(c, "busca_cidade") },
        iconeCidade(avatarCidade("p")), h("span", null, `${c.n} (${c.uf})`, h("small", null, `${num(c.pop, 0)} habitantes · ${c.nv} vereadores`)))));
      sug.hidden = !sug.children.length;
    });
    const desenhar = () => {
      corpo.textContent = "";
      const todas = CID.m.filter(temCusto);
      const total = todas.reduce((a, c) => a + c.custo, 0), pop = todas.reduce((a, c) => a + c.pop, 0);
      const doEstado = todas.filter((c) => c.uf === uf).sort((a, b) => porHabMes(b) - porHabMes(a));
      const max = Math.max(...doEstado.map(porHabMes), 0.01);
      const linha = (c, pos) => h("a", { class: `rank${atual && c.cod === atual.cod ? " rank--eu" : ""}`, href: urlCidade(c), onclick: () => { S.origem = "ranking_cidades"; } },
        h("span", { class: "rank__pos" }, `${pos}º`),
        h("span", { class: "rank__nome" }, c.n, " ", h("small", null, `${num(c.pop, 0)} hab.`)),
        h("span", { class: "rank__valor" }, reaisC(porHabMes(c))),
        h("span", { class: "barra__trilho" }, h("span", { class: "barra__fill", style: `width:${Math.max(0.5, (porHabMes(c) / max) * 100)}%` })));
      // as 5 mais caras e as 5 mais baratas; o botão mostra todas as cidades do estado numa lista só
      const n = Math.min(5, Math.ceil(doEstado.length / 2));
      add(corpo,
        h("div", { class: "estatisticas" },
          estatistica("Todas as câmaras do Brasil", compacto(total / 12), `por mês, ${num(todas.length, 0)} cidades com dados`),
          estatistica("Por habitante", reaisC(total / pop / 12), "por mês, em média no Brasil"),
          estatistica("Vereadores", num(CID.m.reduce((a, c) => a + c.nv, 0), 0), "eleitos em 2024")),
        h("div", { class: "filtros" }, h("div", { class: "campo" }, h("label", { for: "uf-cidades" }, "Estado"), seletorUF("uf-cidades", uf, (v) => { uf = v || "SP"; completo = false; evento("ver_estado_cidades", { uf }); desenhar(); }, "Escolha o estado"))),
        doEstado.length && completo ? h("article", { class: "cartao" }, h("h3", null, `As ${doEstado.length} cidades de ${ESTADOS[uf]} com dados, da mais cara à mais barata por habitante`),
          h("div", { class: "rank-lista" }, doEstado.map((c, i) => linha(c, i + 1)))) : null,
        doEstado.length && !completo ? h("div", { class: "duas-colunas" },
          h("article", { class: "cartao" }, h("h3", null, `Mais caras por habitante em ${ESTADOS[uf]}`), h("div", { class: "rank-lista" }, doEstado.slice(0, n).map((c, i) => linha(c, i + 1)))),
          h("article", { class: "cartao" }, h("h3", null, "Mais baratas por habitante"), h("div", { class: "rank-lista" }, doEstado.slice(-n).reverse().map((c, i) => linha(c, doEstado.length - i))))) : null,
        doEstado.length > 2 * n && !completo ? h("div", null, h("button", { type: "button", class: "botao botao--leve", onclick: () => { completo = true; evento("abrir_lista", { lista: "cidades", uf }); desenhar(); } },
          `Ver as ${doEstado.length} cidades de ${ESTADOS[uf]}`)) : null,
        h("p", { class: "nota" }, "Custo da Câmara por habitante, por mês. Cidades pequenas costumam custar mais por habitante, porque toda câmara tem pelo menos 9 vereadores e uma estrutura mínima."),
        (() => {
          const comProblema = CID.m.filter((c) => c.uf === uf && problemaCidade(c)).sort((a, b) => a.n.localeCompare(b.n, "pt-BR"));
          const noBrasil = CID.m.filter((c) => problemaCidade(c)).length;
          if (!comProblema.length) return h("p", { class: "nota" }, `Todas as cidades de ${ESTADOS[uf]} informaram o gasto da Câmara. No Brasil, ${num(noBrasil, 0)} cidades têm dados faltando ou estranhos.`);
          return h("details", { class: "cartao problemas" },
            h("summary", null, h("strong", null, `${comProblema.length} ${comProblema.length === 1 ? "cidade" : "cidades"} de ${ESTADOS[uf]} com dados faltando ou estranhos`),
              h("span", { class: "pequeno discreto" }, ` · ${num(noBrasil, 0)} no Brasil. A sua está aqui? Veja como pedir a correção.`)),
            h("div", { class: "lista-estado__grupo" }, comProblema.map((c) => h("a", { class: "pessoa-chip", href: urlCidade(c), onclick: () => { S.origem = "lista_problemas"; } }, c.n, h("small", null, problemaCidade(c).curto)))));
        })());
    };
    carregarCidades().then(desenhar, () => { corpo.textContent = "Não foi possível carregar as câmaras."; });
    add(sec, h("p", { class: "rotulo" }, "Vereadores"),
      h("h2", null, atual ? "Outras câmaras" : "Quanto custa a Câmara da sua cidade"),
      h("p", { class: "discreto" }, `As 5.568 câmaras municipais, com dados do Tesouro Nacional e do TSE. O salário de cada vereador ainda não tem fonte nacional: mostramos o custo da Câmara e o teto do salário${cidadesCamara().length ? `. Em ${listaE(cidadesCamara().map((c) => c.n))}, já dá para ver cada vereador` : ""}.`),
      h("div", { class: "busca-caixa", style: "max-width:520px" }, h("label", { class: "visualmente-oculto", for: "busca-cidade" }, "Procurar cidade"), input, sug),
      destaqueCapitais(atual),
      corpo);
    return sec;
  }

  // ================================================================== seções gerais
  const pastaCurta = (g) => (/^Presidente/.test(g) ? "Presidente" : /^Vice/.test(g) ? "Vice-presidente"
    : /^Advogad/.test(g) ? "Advocacia-Geral da União" : g.replace(/^Ministr[oa](-chefe)?\s+(d[aoe]s?|de)\s+/, ""));
  function secGoverno() {
    const ordem = { pr: 0, vp: 1, mi: 2 };
    const atuais = S.D.p.filter((p) => p.k === "e" && p.x).sort((a, b) => ordem[a.tp] - ordem[b.tp] || a.n.localeCompare(b.n, "pt-BR"));
    if (!atuais.length) return null;
    const ate = meta().ultimo_mes_executivo;
    const linha = (p) => pessoaLinha(p, pastaCurta(p.g), urlPessoa(p), () => { S.origem = "governo"; });
    const topo = atuais.filter((p) => p.tp !== "mi"), mins = atuais.filter((p) => p.tp === "mi");
    return h("section", { class: "bloco", id: "governo" },
      h("p", { class: "rotulo" }, "Governo federal"),
      h("h2", null, "Presidente, vice e ministros"),
      h("p", { class: "discreto" }, `Toque num nome para ver quanto ganha e quanto custa por mês. Dados do Portal da Transparência até ${MESES[(ate % 100) - 1]}/${Math.floor(ate / 100)}.`),
      h("div", { class: "cartao" }, listaPessoas(topo.map(linha)),
        mins.length ? listaFechada(`Ver os ${mins.length} ministros`, "ministros", listaPessoas(mins.map(linha))) : null));
  }
  // ================================================================== governadores (dados/governadores.json)
  // O salário de governador e de vice é fixado por lei em cada estado; o arquivo traz, para cada um, o valor em vigor,
  // a história, quem ocupa o cargo e se a folha do Estado deu para conferir.
  const GOV = { e: [], porUF: {}, meta: null };
  const ART_UF = { AC: "o", AP: "o", AM: "o", BA: "a", CE: "o", DF: "o", ES: "o", MA: "o", MT: "o", MS: "o", PA: "o", PB: "a", PR: "o", PI: "o", RJ: "o", RN: "o", RS: "o", TO: "o" };
  const deUF = (uf) => (ART_UF[uf] ? `d${ART_UF[uf]} ${ESTADOS[uf]}` : `de ${ESTADOS[uf]}`);
  const emUF = (uf) => (ART_UF[uf] ? `n${ART_UF[uf]} ${ESTADOS[uf]}` : `em ${ESTADOS[uf]}`);
  const CONF = {
    lei: ["Lei", "O valor está no texto da lei (ou do decreto legislativo) que fixa o subsídio."],
    folha: ["Conferido na folha", "O valor foi conferido na folha de pagamento do Estado, com o nome de quem recebe."],
    tabela: ["Tabela oficial", "O valor está na tabela oficial de remuneração dos cargos do Estado; não achamos o texto da lei."],
    calculado: ["Cálculo nosso", "Calculamos a partir da lei (um reajuste em porcentagem, ou uma porcentagem do subsídio do governador); ainda não conferimos na folha."],
    imprensa: ["Só pela imprensa", "Não achamos a lei nem conseguimos abrir a folha: é o valor informado pela imprensa. Pode estar desatualizado."],
  };
  const FOLHA_GOV = {
    aberta: "O Estado publica a folha de pagamento com o nome de cada servidor, e nós a conferimos.",
    painel: "O Estado publica a folha com o nome de cada servidor, mas dentro de um painel (Power BI), sem arquivo para baixar. Ainda não conferimos por lá; você pode consultar pelo nome.",
    token: "O Estado publica a folha com o nome de cada servidor, mas os dados só saem pela página do portal (a consulta automática pede uma chave). Ainda não conferimos; você pode consultar pelo nome.",
    bloqueada: "O Estado publica a folha com o nome de cada servidor, mas o portal não abriu para o nosso robô (bloqueia acessos automáticos ou vindos de fora do Brasil, ou pede um cadastro). Você pode consultar pelo nome no portal.",
    suspensa: "O portal da transparência do Estado está fora do ar durante o período eleitoral (Decreto estadual nº 24.400/2026). Voltamos a tentar depois da eleição.",
    nao_testada: "O Estado publica a folha com o nome de cada servidor no portal; ainda não a conferimos.",
    captcha: "O Estado publica a folha com o nome de cada servidor, mas a consulta pede um CAPTCHA (o teste para provar que não é um robô), e nós não contornamos esse tipo de bloqueio. Você pode consultar pelo nome no portal.",
    navegador: "O Estado publica a folha com o nome de cada servidor, mas o portal só funciona clicando na página, sem arquivo para baixar nem acesso para programas. Ainda não automatizamos; você pode consultar pelo nome no portal.",
  };
  const fmtData = (s) => (s ? `${s.slice(8, 10)}/${s.slice(5, 7)}/${s.slice(0, 4)}` : "");
  const mesTxt = (s) => (s ? fmtMes(Number(s.slice(0, 4)) * 100 + Number(s.slice(5, 7))) : "");
  const govFem = (e) => !!e.gov.fem;
  const tituloGov = (e) => (e.gov.ex ? (govFem(e) ? "Governadora em exercício" : "Governador em exercício") : govFem(e) ? "Governadora" : "Governador");
  const seloConf = (c) => h("span", { class: `etiqueta conf conf--${c}`, title: CONF[c][1] }, CONF[c][0]);
  const partidoTxt = (o) => (o.pt ? ` (${o.pt})` : "");
  const rankingGov = (campo) => GOV.e.filter((e) => e[campo]).slice().sort((a, b) => b[campo][0] - a[campo][0] || a.uf.localeCompare(b.uf));
  const posGov = (e, campo = "v") => { const r = rankingGov(campo); return { pos: r.filter((x) => x[campo][0] > e[campo][0]).length + 1, n: r.length }; };
  const tituloCase = (t) => (t || "").toLowerCase().replace(/(^|\s)(\S)/g, (m, a, b) => a + b.toUpperCase()).replace(/\s(De|Da|Do|Das|Dos|E)\s/g, (m) => m.toLowerCase());
  function textoGov(e) {
    const p = posGov(e), link = endereco() ? `${origem()}${urlGov(e.uf)}` : "";
    return [
      `*${tituloGov(e)} ${deUF(e.uf)}: ${e.gov.n}*`,
      `Salário (subsídio) do cargo: *${reaisC(e.v[0])} por mês*, bruto${frasePop(e.v[0] / (meta().salario_minimo["2026"] || meta().salario_minimo[anoAtual()]), ", mais que ")}. É o ${p.pos}º maior entre os 27 estados.`,
      e.recebe ? e.recebe.texto + (e.recebe.bruto ? ` (${reaisC(e.recebe.bruto)} brutos em ${mesTxt(e.recebe.mes)}).` : ".") : null,
      "",
      `Fonte: ${e.v[3].split(";")[0]}.`,
      `Veja o do seu estado: ${link || "Contas do Poder"}`,
    ].filter((x) => x !== null).join("\n");
  }
  // lista dos 27, do maior salário para o menor (na página inicial e embaixo da página de um estado)
  function secGovernadores(atual) {
    if (!GOV.e.length) return null;
    let campo = "v", todos = !!atual; // na página inicial, os 5 maiores e o botão para ver os 27
    const corpo = h("div", { style: "display:grid;gap:12px" });
    const desenhar = () => {
      corpo.textContent = "";
      const r = rankingGov(campo), max = r[0][campo][0];
      const vistos = todos ? r : r.slice(0, 5);
      const valores = r.map((e) => e[campo][0]), med = mediana(valores);
      const linha = (e, i) => h("a", { class: `rank${atual && e.uf === atual.uf ? " rank--eu" : ""}`, href: urlGov(e.uf), onclick: () => { S.origem = "ranking_governadores"; } },
        h("span", { class: "rank__pos" }, `${i + 1}º`),
        h("span", { class: "rank__nome" }, ESTADOS[e.uf], " ", h("small", null, campo === "v" ? `${e.gov.n}${partidoTxt(e.gov)}${e.gov.ex ? ", em exercício" : ""}` : e.vice ? `${e.vice.n}${partidoTxt(e.vice)}` : "cargo vago hoje"), " ", seloConf(e[campo][2]),
          e.recebe && campo === "v" ? h("small", { class: "rank__obs" }, ` · ${e.recebe.curto}${e.recebe.bruto ? ` (${reais(e.recebe.bruto)})` : ""}`) : null,
          e.m ? h("small", { class: "rank__mes" }, " · mês a mês") : null),
        h("span", { class: "rank__valor" }, reaisC(e[campo][0])),
        h("span", { class: "barra__trilho" }, h("span", { class: "barra__fill barra__fill--ganha", style: `width:${Math.max(0.5, (e[campo][0] / max) * 100)}%` })));
      add(corpo,
        h("div", { class: "estatisticas" },
          estatistica("Maior", reais(r[0][campo][0]), `${ESTADOS[r[0].uf]}`),
          estatistica("Mediana dos estados", reais(med), `metade ganha mais, metade menos`),
          estatistica("Menor", reais(r[r.length - 1][campo][0]), `${ESTADOS[r[r.length - 1].uf]}`),
          estatistica("Presidente da República", "R$ 46.366", "por mês, o teto do funcionalismo")),
        pilulas([["v", "Governador"], ["vv", "Vice-governador"]], campo, (v) => { campo = v; evento("ver_governadores", { cargo: v }); desenhar(); }, "Cargo"),
        h("article", { class: "cartao" }, h("div", { class: "rank-lista" }, vistos.map(linha)),
          todos ? null : h("div", null, h("button", { type: "button", class: "botao botao--leve", onclick: () => { todos = true; evento("abrir_lista", { lista: campo === "v" ? "governadores" : "vice_governadores" }); desenhar(); } },
            `Ver os ${r.length} ${campo === "v" ? "governadores" : "vice-governadores"}`))),
        h("details", { class: "nota-dobra" }, h("summary", null, "De onde vem cada valor e o que ele mostra"),
          h("p", { class: "nota" }, "Salário bruto do cargo por mês (o subsídio em vigor hoje), antes do imposto e da previdência. É o valor fixado para o cargo, não necessariamente o que a pessoa recebe: quem é servidor de carreira pode optar pelo salário do cargo de origem (como a governadora de Pernambuco, procuradora do Estado), e o governador em exercício do Rio, desembargador, provavelmente continua recebendo pelo Tribunal de Justiça."),
          h("ul", { class: "lista nota" }, Object.keys(CONF).map((c) => h("li", null, seloConf(c), " ", CONF[c][1])))),
        campo === "vv" ? h("p", { class: "nota" }, `Estados sem vice hoje (o vice virou governador ou o cargo ficou vago) aparecem com o valor do cargo, se a lei o fixa. Em ${listaE(GOV.e.filter((e) => !e.vv).map((e) => ESTADOS[e.uf]))}, não achamos o valor do vice.`) : null);
    };
    desenhar();
    return h("section", { class: "bloco", id: "governadores" },
      h("p", { class: "rotulo" }, "Governadores"),
      h("h2", null, atual ? "Os 27 governadores" : "Quanto ganha cada governador"),
      h("p", { class: "discreto" }, "O salário (subsídio) do governador e do vice é fixado por lei em cada estado, e não há uma fonte nacional com todos. Juntamos, estado por estado, a lei, a tabela oficial ou a folha de pagamento e mostramos de onde veio cada valor. Toque num estado para ver quem governa, a lei e a história do valor."),
      GOV.e.some((e) => e.m) ? h("p", { class: "discreto" }, `Em ${GOV.e.filter((e) => e.m).length} estados, a folha de pagamento abre para o nosso robô, e a página do estado mostra também o que o governador e o vice receberam em cada mês (marcados com "mês a mês").`) : null,
      h("a", { class: "chamada-indice", href: "/indice", onclick: () => { S.origem = atual ? "governador" : "inicio"; } },
        h("span", { class: "rotulo" }, "Índice de Transparência"),
        h("strong", null, "Dá para saber, pela fonte oficial de cada estado, quanto ganham e quanto custam os seus políticos?"),
        h("span", null, "As notas do governo e da Assembleia Legislativa de cada estado, critério por critério, com a prova →")),
      corpo);
  }
  // mês a mês pela folha do Estado: e.m = [[aaaamm, tp, índice em e.oc, recebido, salário, 13º, férias, auxílios, outros, abate-teto, marca]]
  const PARTES_GOV = [[4, "Salário"], [5, "13º"], [6, "Férias"], [7, "Auxílios"], [8, "Outros"]];
  function blocoMensalGov(e) {
    if (!e.m || !e.m.length) return null;
    const temVice = e.m.some((x) => x[1] === "vice");
    let tp = "gov";
    const corpo = h("div", { style: "display:grid;gap:12px;grid-template-columns:minmax(0,1fr)" });
    const nomeOc = (i) => (i == null || !e.oc[i] ? "—" : e.oc[i].n);
    const desenhar = () => {
      corpo.textContent = "";
      const ls = e.m.filter((x) => x[1] === tp);
      if (!ls.length) return;
      const meses = [...new Set(ls.map((x) => x[0]))].sort((a, b) => a - b);
      // uma coluna por mês (no mês da troca, duas pessoas: somadas na coluna, separadas na dica e na tabela)
      const pontos = meses.map((am) => {
        const xs = ls.filter((x) => x[0] === am);
        const sal = xs.reduce((a, x) => a + (x[4] != null ? Math.min(x[4], x[3]) : x[3]), 0);
        const tot = xs.reduce((a, x) => a + x[3], 0);
        return { aaaamm: am, s: sal, x: Math.max(0, tot - sal), xs, i: xs[xs.length - 1][2] };
      });
      const pessoas = [...new Set(pontos.map((p) => p.i))];
      const cor = (i) => (pessoas.indexOf(i) % 2 ? "d" : "e");
      const normais = pontos.filter((p) => !p.xs.some((x) => x[10].includes("s")));
      const ult12 = normais.slice(-12);
      const ano = String(Math.floor(meses[meses.length - 1] / 100) - 1);
      const doAno = pontos.filter((p) => String(Math.floor(p.aaaamm / 100)) === ano);
      const totAno = doAno.reduce((a, p) => a + p.s + p.x, 0), extraAno = doAno.reduce((a, p) => a + p.x, 0);
      const ultimo = pontos[pontos.length - 1];
      const caixa = h("div", { class: "grafico" });
      const colunas = [4, 5, 6, 7, 8, 9].filter((k) => ls.some((x) => x[k]));
      const dinheiro = (v) => (v == null ? "—" : v === 0 ? h("span", { class: "zero" }, reaisC(0)) : reaisC(v));
      add(corpo,
        temVice ? pilulas([["gov", "Governador"], ["vice", "Vice-governador"]], tp, (v) => { tp = v; evento("ver_governador_mes", { uf: e.uf, cargo: v }); desenhar(); }, "Cargo") : null,
        h("div", { class: "estatisticas" },
          estatistica(`Recebeu em ${fmtMes(ultimo.aaaamm)}`, reaisC(ultimo.s + ultimo.x), ultimo.xs.map((x) => nomeOc(x[2])).join(" e ")),
          ult12.length >= 3 ? estatistica("Média por mês", reais(ult12.reduce((a, p) => a + p.s + p.x, 0) / ult12.length), `nos últimos ${ult12.length} meses na folha${normais.length < pontos.length ? ", sem os acertos de saída" : ""}`) : null,
          doAno.length === 12 ? estatistica(`Recebeu em ${ano}`, compacto(totAno), extraAno > 1 ? `${reais(extraAno)} além do salário (13º, férias e outros)` : "só o salário") : null),
        h("div", { class: "legenda" },
          h("span", null, h("span", { class: "chave chave--ganha" }), "Salário (subsídio)"), h("span", null, h("span", { class: "chave chave--extra" }), "13º, férias, auxílios e outros"),
          pessoas.length > 1 ? pessoas.map((i) => h("span", null, h("span", { class: `chave chave--faixa faixa-cargo--${cor(i)}` }), nomeOc(i))) : null),
        caixa,
        h("details", { class: "tabela" }, h("summary", null, "Ver os valores em tabela"),
          rolagem("Quanto recebeu, mês a mês", h("table", { class: "tabela-gov" },
            h("thead", null, h("tr", null, ["Mês", "Quem", "Recebeu", ...colunas.map((k) => (k === 9 ? "Abate-teto" : PARTES_GOV.find(([c]) => c === k)[1]))].map((c, i) => h("th", { class: i > 1 ? "num" : null }, c)))),
            h("tbody", null, ls.slice().reverse().map((x) => h("tr", null, h("td", null, fmtMes(x[0])),
              h("td", null, nomeOc(x[2]), x[10].includes("s") ? h("small", { class: "tabela-gov__obs" }, "mês da saída, com os acertos") : null,
                x[10].includes("a") ? h("small", { class: "tabela-gov__obs" }, "13º já sem o adiantamento pago antes") : null),
              h("td", { class: "num" }, h("strong", null, reaisC(x[3]))), ...colunas.map((k) => h("td", { class: "num" }, k === 9 ? (x[9] ? `− ${reaisC(x[9])}` : "—") : dinheiro(x[k]))))))))),
        h("ul", { class: "lista nota" },
          h("li", null, "Recebeu = o bruto do mês na folha do Estado, já sem o abate-teto, antes do imposto de renda e da previdência. Descontos pessoais não entram."),
          h("li", null, e.mf.nota),
          ls.some((x) => x[10].includes("s")) ? h("li", null, "Quem deixa o cargo recebe no último mês os acertos: férias não tiradas (às vezes de vários anos) e o 13º proporcional. Esse mês fica fora da média.") : null,
          ls.some((x) => x[10].includes("a")) ? h("li", null, "Parte do 13º é paga adiantada no meio do ano, e a folha de dezembro traz o 13º inteiro e desconta o adiantamento. Aqui, dezembro já aparece sem o adiantamento, para o 13º não contar duas vezes.") : null,
          h("li", null, "Fonte: ", h("a", { href: e.mf.u, target: "_blank", rel: "noopener" }, `folha de pagamento ${deUF(e.uf)}`), `, mês a mês desde ${fmtMes(e.m[0][0])}. O robô confere toda semana.`)));
      requestAnimationFrame(() => graficoColunas(caixa, pontos, [{ k: "s", cls: "seg-ganha" }, { k: "x", cls: "seg-extra" }],
        (p) => [...p.xs.map((x) => h("div", null, h("strong", null, nomeOc(x[2])), `: ${reaisC(x[3])}`, x[10].includes("s") ? " (saída, com os acertos)" : "")),
          ...PARTES_GOV.filter(([k]) => p.xs.some((x) => x[k])).map(([k, n]) => h("div", { class: "pequeno" }, `${n}: ${reaisC(p.xs.reduce((a, x) => a + (x[k] || 0), 0))}`)),
          p.xs.some((x) => x[9]) ? h("div", { class: "pequeno" }, `Abate-teto: − ${reaisC(p.xs.reduce((a, x) => a + (x[9] || 0), 0))}`) : null],
        pessoas.length > 1 ? (p) => cor(p.i) : null));
    };
    desenhar();
    return [h("h2", { class: "h3" }, "Quanto recebeu, mês a mês"),
      h("p", { class: "discreto pequeno", style: "margin:0" }, `Pela folha de pagamento ${deUF(e.uf)}, com o nome de cada servidor: o que ${govFem(e) ? "a governadora" : "o governador"} e o vice receberam de fato em cada mês, com 13º, férias e acertos.`),
      corpo];
  }
  // página de um estado: #gov-SP
  function secGovernador(e) {
    const p = posGov(e), med = mediana(GOV.e.map((x) => x.v[0]));
    const sm = meta().salario_minimo["2026"] || meta().salario_minimo[anoAtual()];
    const fem = govFem(e), R = rankingGov("v"), maior = R[0], menor = R[R.length - 1];
    const spec = specGov(e);
    const cargoTxt = (c, f) => ({ gov: f ? "Governadora" : "Governador", vice: f ? "Vice-governadora" : "Vice-governador", exercicio: f ? "Governadora em exercício" : "Governador em exercício", sec: "Secretário de Estado" })[c];
    const lado = (o) => o ? h("span", null, `${o.n}${partidoTxt(o)}`) : null;
    const hist = e.h.filter((x) => x[0] !== "sec");
    const sec = e.h.filter((x) => x[0] === "sec");
    const linhaHist = (x) => h("tr", null,
      h("td", null, fmtMes(x[1])), h("td", null, cargoTxt(x[0])), h("td", { class: "num" }, reaisC(x[2])), h("td", null, seloConf(x[3])),
      h("td", { style: "white-space:normal;min-width:16rem" }, x[4], " ", h("a", { href: x[5], target: "_blank", rel: "noopener" }, "fonte\u00a0↗")));
    const foto = e.gov.fc ? h("p", { class: "nota credito" }, "Foto: ", h("a", { href: e.gov.fc.u, target: "_blank", rel: "noopener" }, e.gov.fc.l ? `${(e.gov.fc.a || "autor no Wikimedia Commons").replace(/ from .*$/, "")} (${e.gov.fc.l})` : e.gov.fc.a), e.gov.fc.l ? ", via Wikimedia Commons." : ".") : null;
    return h("article", { class: "cartao conta", id: "governador" },
      h("div", { class: "conta__topo" }, avatar({ n: e.gov.n, f: e.gov.f }, "g"),
        h("div", null,
          h("p", { class: "rotulo" }, `Governo ${deUF(e.uf)}`),
          h("h1", { class: "conta__nome" }, e.gov.n),
          h("div", { class: "conta__sub" }, h("span", null, `${tituloGov(e)} ${deUF(e.uf)}${partidoTxt(e.gov).replace(/[()]/g, "").replace(/^ /, " · ")} · desde ${fmtData(e.gov.de)}`))),
        null),
      h("div", { class: "cidade__corpo" },
        h("div", { class: "estatisticas" },
          estatistica(`Salário ${fem ? "da governadora" : "do governador"}`, reaisC(e.v[0]), `por mês, bruto, ${e.v[2] === "imprensa" ? `valor de ${fmtMes(e.v[1])}` : `desde ${fmtMes(e.v[1])}`}`),
          estatistica(e.vice && e.vice.fem ? "Vice-governadora" : "Vice-governador", e.vv ? reaisC(e.vv[0]) : "—", e.vice ? `${e.vice.n}${partidoTxt(e.vice)}` : `cargo vago hoje${e.vv ? " (valor do cargo)" : ""}`),
          estatistica("Em salários mínimos", `${num(e.v[0] / sm, 1)}`, `salários mínimos de ${reais(sm)}`),
          estatisticaPop(e.v[0] / sm),
          e.vs ? estatistica("Secretário de Estado", reaisC(e.vs[0]), `por mês, desde ${fmtMes(e.vs[1])}`) : null),
        e.recebe ? h("p", { class: "caixa-nota" }, h("strong", null, `${e.recebe.texto}${e.recebe.bruto ? `: ${reaisC(e.recebe.bruto)} brutos em ${mesTxt(e.recebe.mes)}` : ""}. `),
          e.recebe.bruto ? "Quem é servidor de carreira pode escolher entre o salário do cargo de origem e o subsídio do cargo político. O valor da folha já tem o desconto do teto." : "") : null,
        h("p", { class: "destaque", style: "margin:0" }, p.pos === 1 ? `É o maior salário de governador do país${e.v[0] >= 46366 ? ", igual ao teto do funcionalismo (o salário de ministro do STF)" : ""}.`
          : p.pos === p.n ? `É o menor salário de governador do país. A mediana dos 27 estados é ${reais(med)}.`
            : `É o ${p.pos}º maior salário de governador entre os 27 estados. A mediana é ${reais(med)}; o maior é o ${deUF(maior.uf)} (${reais(maior.v[0])}) e o menor, o ${deUF(menor.uf)} (${reais(menor.v[0])}).`),
        h("div", { class: "fonte-gov" },
          h("p", { style: "margin:0" }, h("strong", null, "De onde vem o valor: "), seloConf(e.v[2]), " ", CONF[e.v[2]][1]),
          h("p", { class: "nota", style: "margin:0" }, e.v[3], ". ", h("a", { href: e.v[4], target: "_blank", rel: "noopener" }, "Ver a fonte\u00a0↗"))),
        blocoMensalGov(e),
        h("h2", { class: "h3" }, "Quem governou desde 2023"),
        rolagem("Quem governou desde 2023", h("table", { class: "tabela-gov" },
          h("thead", null, h("tr", null, ["Quem", "Cargo", "De", "Até"].map((c) => h("th", null, c)))),
          h("tbody", null, e.oc.map((o) => h("tr", null,
            h("td", { style: "min-width:11rem" }, h("strong", null, o.n), o.pt ? ` (${o.pt})` : "", o.obs ? h("small", { class: "tabela-gov__obs" }, o.obs) : null),
            h("td", null, cargoTxt(o.c, o.fem)), h("td", null, fmtData(o.de)), h("td", null, o.ate ? fmtData(o.ate) : "hoje")))))),
        h("h2", { class: "h3" }, "O salário ao longo do tempo"),
        rolagem("O salário ao longo do tempo", h("table", { class: "tabela-gov" },
          h("thead", null, h("tr", null, ["Desde", "Cargo", "Valor por mês", "Origem", "Lei ou fonte"].map((c, i) => h("th", { class: i === 2 ? "num" : null }, c)))),
          h("tbody", null, hist.map(linhaHist)))),
        sec.length ? h("details", { class: "tabela" }, h("summary", null, "Secretários de Estado"), rolagem("Secretários de Estado", h("table", { class: "tabela-gov" }, h("tbody", null, sec.map(linhaHist))))) : null,
        h("p", { class: "nota" }, "\"Desde\" é o mês em que o valor passou a valer. Quando a fonte é só a imprensa, é o mês a que o valor se refere."),
        h("h2", { class: "h3" }, "Dá para conferir na folha de pagamento?"),
        h("p", { style: "margin:0" }, e.m ? "Sim. O Estado publica a folha com o nome de cada servidor, e o robô lê toda semana: veja o mês a mês acima." : FOLHA_GOV[e.folha.s]),
        e.folha.c && !e.m ? h("p", { class: "nota", style: "margin:0" }, `Na folha de ${mesTxt(e.folha.c.mes)}, ${tituloCase(e.folha.c.nome)} aparece com ${reaisC(e.folha.c.bruto)} brutos${Math.abs(e.folha.c.bruto - e.v[0]) > 1 ? " (o valor do mês pode incluir 13º, férias, acertos ou descontos; veja as notas)" : ", o mesmo valor do subsídio"}.`) : null,
        e.folha.u ? h("p", { class: "nota", style: "margin:0" }, h("a", { href: e.folha.u, target: "_blank", rel: "noopener" }, `Folha de pagamento ${deUF(e.uf)}\u00a0↗`)) : null,
        h("p", { class: "nota", style: "margin:0" }, h("a", { href: `/indice#indice-${e.uf.toLowerCase()}`, onclick: () => { S.origem = "governador"; } }, `Ver as notas ${deUF(e.uf)} no Índice de Transparência`)),
        e.notas.length ? h("h2", { class: "h3" }, "O que mais saber") : null,
        e.notas.map((n) => h("p", { class: "nota", style: "margin:0" }, n)),
        h("ul", { class: "lista nota" },
          h("li", null, "Subsídio é o salário do cargo, em parcela única, bruto (antes do imposto de renda e da previdência). Muitos estados pagam também 13º e terço de férias ao governador (o STF considera isso compatível com o subsídio). A residência oficial, o carro, a segurança e as viagens do governador são pagos pelo Estado e não aparecem por pessoa."),
          h("li", null, `O subsídio do governador é também o teto salarial dos servidores do Poder Executivo ${deUF(e.uf)} (Constituição, art. 37, XI), a não ser que o Estado adote um teto único, o dos desembargadores. Por isso, um aumento do governador costuma abrir espaço para aumentar outros salários.`),
          h("li", null, "Nenhum governador pode ganhar mais que um ministro do STF (R$ 46.366,19 em 2025 e 2026).")),
        foto));
  }
  function secTipicos() {
    const bloco = (casa, titulo) => {
      const C = colegas(casa, "2025"), sm25 = meta().salario_minimo["2025"];
      const comJetons = C.lista.filter((x) => x.r.cats.jetons).length;
      return h("article", { class: "cartao" },
        h("div", { class: "cartao__cabeca" }, h("h3", null, titulo), h("span", { class: "rotulo" }, "Mediana de 2025")),
        h("div", { class: "estatisticas estatisticas--2" },
          estatistica("Custo por mês", compacto(C.tm), `${sm(C.tm / sm25)} salários mínimos`),
          estatistica("Vai para o bolso", compacto(C.gm), `${sm(C.gm / sm25)} salários mínimos`)),
        casa === "e" ? h("div", { class: "estatisticas estatisticas--2" },
          estatistica("Gastos do cargo", compacto(C.cm), "viagens oficiais, por mês"),
          estatistica("Recebem jetons", String(comJetons), `de ${C.n} ministros em 2025, segundo o Portal`)) : h("div", { class: "estatisticas estatisticas--2" },
          estatistica("Equipe do gabinete", compacto(C.em), "por mês"),
          estatistica("Pessoas na equipe", num(C.pessoas || 0, 0), `${reais(C.porPessoa || 0)} por pessoa`)),
        casa === "s" ? h("p", { class: "nota" }, h("span", { class: "etiqueta etiqueta--estimativa" }, "estimativa"), " A equipe do Senado é estimada a partir da folha de pagamento.") : null);
    };
    return h("section", { class: "bloco", id: "tipico" },
      h("p", { class: "rotulo" }, "Para começar"),
      h("h2", null, "Um parlamentar e um ministro típicos"),
      h("div", { class: "grade-cartoes grade-cartoes--3" }, bloco("d", "Deputado federal"), bloco("s", "Senador"), bloco("e", "Ministro de Estado")),
      h("p", { class: "nota" }, "Custo total: o que vai para o bolso (salário, 13º e auxílios, em valor bruto) mais os gastos do mandato pagos com dinheiro público (cota parlamentar, diárias e outros gastos). A equipe do gabinete fica à parte, porque é dinheiro que paga outras pessoas. Para os ministros, o bolso inclui os jetons de conselhos e os gastos do cargo são as viagens oficiais."),
      h("div", { class: "acoes" }, h("button", { type: "button", class: "botao", onclick: abrirGuia }, "Descobrir os meus representantes")));
  }
  const METRICAS = {
    custo: { nome: "Custo por mês", nomeP: "Quanto recebe por mês", v: (r) => r.tm, cls: "barra__fill--neutra", fmt: reais },
    ganha: { nome: "Vai para o bolso por mês", v: (r) => r.gm, cls: "barra__fill--ganha", fmt: reais },
    despesas: { nome: "Gastos do mandato por mês", nomeE: "Gastos do cargo (viagens) por mês", nomeV: "Verba do gabinete usada por mês", v: (r) => r.cm, cls: "", fmt: reais, casas: ["d", "s", "e", "j", "v"] },
    jetons: { nome: "Jetons por mês", v: (r) => porMes(r, "jetons"), cls: "barra__fill--ganha", fmt: reais, casas: ["e"] },
    cota: { nome: "Cota parlamentar por mês", v: (r) => porMes(r, "cota_parlamentar"), cls: "", fmt: reais, casas: ["d", "s"] },
    equipe: { nome: "Equipe do gabinete por mês", v: (r) => r.em, cls: "barra__fill--equipe", fmt: reais, casas: ["d", "s", "v+"] },
    pessoas: { nome: "Pessoas na equipe", v: (r) => r.pessoas, cls: "barra__fill--equipe", fmt: (v) => num(v, 0), casas: ["d", "s", "v+"] },
    porPessoa: { nome: "Custo por pessoa da equipe", v: (r) => r.porPessoa, cls: "barra__fill--equipe", fmt: reais, casas: ["d", "s", "v+"] },
  };
  // g: grupo ("d", "v3550308"...). "v+": só nas câmaras que publicam o custo da equipe de cada gabinete
  const metricaVale = (m, g) => {
    const cs = METRICAS[m].casas;
    if (!cs) return true;
    if (cs.includes(tipoG(g))) return true;
    return cs.includes("v+") && tipoG(g) === "v" && !!(infoG(g) || {}).equipe_custo;
  };
  const nomeMetrica = (m, g) => { const casa = tipoG(g); return (casa === "e" && METRICAS[m].nomeE) || (casa === "v" && METRICAS[m].nomeV) || (casa === "p" && METRICAS[m].nomeP) || METRICAS[m].nome; };
  const nomeGrupo = (g) => ({ d: "deputados", s: "senadores", e: "governo" })[g] || (tipoG(g) === "v" ? `vereadores_${cidG(g)}` : `prefeitura_${cidG(g)}`);
  // Colegas e ranking numa seção só: filtros, posição, gráfico de pontos e os maiores/menores.
  function secRanking(p, k, comoCargo) {
    const R = S.rank;
    if (!R.casa) { R.casa = p ? p.k : "d"; if (p && (p.k === "v" || p.k === "p")) R.cid = p.cid; }
    if (!R.periodo) R.periodo = (p && k) || "2025";
    // vereadores e prefeituras: uma cidade de cada vez
    const cidadesDo = (casa) => (casa === "v" ? cidadesCamara() : casa === "p" ? cidadesPrefeitura() : []);
    if ((R.casa === "v" || R.casa === "p") && !cidadesDo(R.casa).length) R.casa = "d";
    if ((R.casa === "v" || R.casa === "p") && !cidadesDo(R.casa).some((c) => c.cod === R.cid)) R.cid = cidadesDo(R.casa)[0].cod;
    const G = () => (R.casa === "v" || R.casa === "p" ? `${R.casa}${R.cid}` : R.casa);
    if (!METRICAS[R.metrica] || !metricaVale(R.metrica, G())) R.metrica = "custo";
    const periodosOk = () => { if (![...anosGrupo(G()), "leg"].includes(R.periodo)) R.periodo = anosGrupo(G()).includes("2025") ? "2025" : anosGrupo(G())[0]; };
    periodosOk();
    const semUF = () => R.casa === "e" || R.casa === "v" || R.casa === "p";
    const sec = h("section", { class: "bloco", id: "ranking" });
    const corpo = h("div", { style: "display:grid;gap:12px" });
    const desenhar = () => {
      corpo.textContent = "";
      const M = METRICAS[R.metrica];
      const minimo = R.periodo === "leg" ? 6 : 3;
      const lista = S.D.p.filter((q) => grupo(q) === G() && !q.ced && (!R.uf || semUF() || q.uf === R.uf) && (!R.noCargo || q.x || (p && q.id === p.id)))
        .map((q) => { const r = resumo(q, R.periodo); return r && r.m >= minimo ? { p: q, v: M.v(r) } : null; })
        .filter((x) => x && x.v > 0).sort((a, b) => b.v - a.v);
      const max = Math.max(1, ...lista.map((x) => x.v));
      const sub = (q) => (q.k === "e" ? pastaCurta(q.g) : q.k === "v" ? q.pt || "sem partido" : q.k === "p" ? pastaCurtaP(q) : partidoUF(q));
      const linha = (x, pos) => h("a", { class: `rank${p && x.p.id === p.id ? " rank--eu" : ""}`, href: urlPessoa(x.p, R.periodo), onclick: () => { S.origem = "ranking"; } },
        h("span", { class: "rank__pos" }, `${pos}º`),
        h("span", { class: "rank__nome" }, x.p.n, " ", h("small", null, sub(x.p))),
        h("span", { class: "rank__valor" }, M.fmt(x.v)),
        h("span", { class: "barra__trilho" }, h("span", { class: `barra__fill ${M.cls}`, style: `width:${Math.max(0.5, (x.v / max) * 100)}%` })));
      // na página de um político, os 10 maiores e os 10 menores; na página inicial e na da cidade, 5 e 5
      const n = Math.min(p ? 10 : 5, Math.ceil(lista.length / 2));
      const topo = lista.slice(0, n), fim = lista.slice(-n).reverse();
      const eu = p ? lista.findIndex((x) => x.p.id === p.id) : -1;
      const med = mediana(lista.map((x) => x.v));
      const grupoTxt = R.casa === "e" ? "no governo federal" : plural(G());
      const ptxt = R.casa === "e" ? "integrantes do governo" : grupoTxt;
      const caixa = h("div", { class: "grafico" });
      add(corpo,
        eu >= 0 ? h("div", { class: "estatisticas" },
          estatistica(nomeMetrica(R.metrica, G()), M.fmt(lista[eu].v), med !== null ? `Mediana: ${M.fmt(med)}` : null),
          estatistica("Posição", `${eu + 1}º`, `de ${lista.length} ${grupoTxt}`)) : null,
        p && eu < 0 ? h("p", { class: "discreto pequeno" }, `${p.n} não entra nesta lista (menos de ${minimo} meses ${R.casa === "e" || R.casa === "p" ? "no cargo" : "de mandato"} no período, valor zero ou outro grupo).`) : null,
        lista.length ? h("div", null,
          h("p", { class: "discreto pequeno", style: "margin:0 0 4px" }, `Cada ponto é um dos ${lista.length} ${ptxt} · ${nomeMetrica(R.metrica, G()).toLowerCase()} · ${nomePeriodo(R.periodo, false, G())}${R.uf && !semUF() ? ` · ${ESTADOS[R.uf]}` : ""}. Passe o mouse ou toque num ponto para ver quem é.`),
          caixa) : h("p", { class: "discreto" }, "Ninguém com dados neste filtro."),
        lista.length ? h("div", { class: "duas-colunas" },
          h("article", { class: "cartao" }, h("h3", null, "Os maiores"), h("div", { class: "rank-lista" }, topo.map((x, i) => linha(x, i + 1)))),
          h("article", { class: "cartao" }, h("h3", null, "Os menores"), h("div", { class: "rank-lista" }, fim.map((x, i) => linha(x, lista.length - i))))) : null,
        R.completo
          ? h("article", { class: "cartao" }, h("h3", null, "Lista completa"), h("div", { class: "rank-lista" }, lista.map((x, i) => linha(x, i + 1))))
          : lista.length > 2 * n ? h("div", null, h("button", { type: "button", class: "botao botao--leve", onclick: () => { R.completo = true; evento("ranking_completo", { casa: nomeGrupo(G()), metrica: R.metrica }); desenhar(); } }, `Ver a lista completa (${lista.length})`)) : null,
        h("ul", { class: "lista nota" },
          R.metrica === "cota" && R.casa === "d" ? h("li", null, "O limite da cota muda por estado, de R$ 41,6 mil (DF) a R$ 58,5 mil (RR) por mês, por causa do preço das passagens.") : null,
          R.casa === "s" && ["equipe", "pessoas", "porPessoa"].includes(R.metrica) ? h("li", null, "A equipe do Senado é uma estimativa feita a partir da folha de pagamento.") : null,
          R.casa === "d" && ["custo", "ganha"].includes(R.metrica) ? h("li", null, "Para deputados, ainda faltam o 13º, a ajuda de custo e as diárias.") : null,
          R.casa === "e" ? h("li", null, "Governo federal: presidente, vice e ministros. Viagens em aviões da FAB e no avião presidencial não têm custo publicado.") : null,
          R.casa === "p" ? h("li", null, `Prefeitura ${deCid(R.cid)}: prefeito, vice, secretários municipais${R.cid === SP ? " e subprefeitos" : ""}. Só o que recebem: a Prefeitura não publica os gastos por pessoa. Servidores cedidos por outro órgão ficam de fora.`) : null,
          R.casa === "v" ? h("li", null, `Vereadores ${deCid(R.cid)}: ${(infoG(G()) || {}).subsidio_folha ? "o salário vem da folha de pagamento da Câmara" : "o salário é o mesmo para todos; o que muda é quanto cada um usa da verba do gabinete"}. Suplentes entram pelos meses em que ocuparam o gabinete. Vereadores de cidades diferentes não se comparam aqui: cada Câmara tem as suas regras.`) : null,
          R.periodo === anoAtual() ? h("li", null, R.casa === "e" ? "Período ainda aberto: o Portal publica os salários com uns 2 meses de atraso." : "Período ainda aberto: os últimos meses ainda podem receber notas.") : null,
          h("li", null, `Só entra quem teve pelo menos ${minimo} meses ${R.casa === "e" || R.casa === "p" ? "no cargo" : "de mandato"} no período.`)));
      if (lista.length) requestAnimationFrame(() => graficoPontos(caixa, p ? p.id : null, lista.map((x) => ({ id: x.p.id, n: x.p.n, sub: sub(x.p), v: x.v })), M.fmt));
    };
    const medir = () => evento("ranking", { casa: nomeGrupo(G()), metrica: R.metrica, periodo: R.periodo === "leg" ? "mandato" : R.periodo, uf: R.uf || "todos" });
    const trocouGrupo = () => { R.completo = false; if (!metricaVale(R.metrica, G())) R.metrica = "custo"; periodosOk(); medir(); render(); irPara("ranking"); };
    const filtros = h("div", { class: "filtros" },
      h("div", { class: "campo campo--quem" }, h("span", { class: "rotulo" }, "Quem"),
        pilulas([["d", "Deputados"], ["s", "Senadores"], ["e", "Governo"], ...(cidadesCamara().length ? [["v", "Vereadores"]] : []), ...(cidadesPrefeitura().length ? [["p", "Prefeituras"]] : [])], R.casa, (v) => {
          R.casa = v;
          if ((v === "v" || v === "p") && !cidadesDo(v).some((c) => c.cod === R.cid)) R.cid = cidadesDo(v)[0].cod;
          trocouGrupo();
        }, "Quem", "grupo-pilulas")),
      semUF() && R.casa !== "e" ? h("div", { class: "campo" }, h("label", { for: "cidade-rank" }, "Cidade"),
        h("select", { id: "cidade-rank", onchange: (e) => { R.cid = +e.target.value; trocouGrupo(); } },
          cidadesDo(R.casa).map((c) => h("option", { value: c.cod, selected: c.cod === R.cid }, `${c.n} (${c.uf})`)))) : null,
      h("div", { class: "campo" }, h("label", { for: "metrica" }, "Comparar por"),
        h("select", { id: "metrica", onchange: (e) => { R.metrica = e.target.value; medir(); desenhar(); } },
          Object.keys(METRICAS).filter((v) => metricaVale(v, G())).map((v) => h("option", { value: v, selected: v === R.metrica }, nomeMetrica(v, G()))))),
      h("div", { class: "campo" }, h("label", { for: "periodo-rank" }, "Período"),
        h("select", { id: "periodo-rank", onchange: (e) => { R.periodo = e.target.value; medir(); desenhar(); } },
          [...anosGrupo(G()), "leg"].map((v) => h("option", { value: v, selected: v === R.periodo }, nomePeriodo(v, true, G()))))),
      semUF() ? null : h("div", { class: "campo" }, h("label", { for: "uf-rank" }, "Estado"), seletorUF("uf-rank", R.uf, (v) => { R.uf = v; medir(); desenhar(); })));
    add(sec, h("p", { class: "rotulo" }, p ? "Colegas e ranking" : "Ranking"),
      h("h2", null, p ? `${p.n} comparado com os colegas${comoCargo ? `, como ${p.g.charAt(0).toLowerCase()}${p.g.slice(1)}` : ""}` : "Quem custa mais e quem custa menos"), filtros,
      h("label", { class: "pequeno discreto", style: "display:inline-flex;gap:8px;align-items:center" },
        h("input", { type: "checkbox", id: "no-cargo-rank", checked: R.noCargo, onchange: (e) => { R.noCargo = e.target.checked; desenhar(); } }), "Só quem está no cargo hoje"),
      corpo);
    desenhar();
    return sec;
  }
  function secResumoGeral() {
    const Cd = colegas("d", "2025"), Cs = colegas("s", "2025");
    const texto = `*Contas do Poder*\nUm deputado federal típico custa ${reais(Cd.tm)} por mês (salário, auxílios e despesas), sem contar a equipe de ${num(Cd.pessoas || 0, 0)} pessoas no gabinete (${reais(Cd.em)} por mês). Mediana de 2025.\nUm senador típico: ${reais(Cs.tm)} por mês.\n\nQuanto custa quem te representa? ${endereco() || "Contas do Poder"}`;
    return h("section", { class: "bloco", id: "resumo" },
      h("div", { class: "resumo" },
        h("p", { class: "rotulo" }, "Resumo para compartilhar"),
        h("h2", null, "Quanto custa um parlamentar em 2025"),
        h("div", { class: "resumo__grade" },
          h("div", { class: "resumo__item" }, h("span", { class: "rotulo" }, "Deputado federal"), h("span", { class: "estatistica__valor" }, compacto(Cd.tm)), h("span", null, `por mês, sem a equipe de ${num(Cd.pessoas || 0, 0)} pessoas`)),
          h("div", { class: "resumo__item" }, h("span", { class: "rotulo" }, "Senador"), h("span", { class: "estatistica__valor" }, compacto(Cs.tm)), h("span", null, "por mês, sem a equipe"))),
        h("p", { class: "resumo__cta" }, `Quanto custa quem te representa? ${dominio()}`),
        h("p", { class: "resumo__fonte" }, "Dados oficiais: Câmara dos Deputados e Senado Federal. Mediana de 2025.")),
      h("div", { class: "compartilhar", style: "padding-inline:0" }, h("div", { class: "acoes" },
        h("a", { class: "botao botao--zap", href: `https://wa.me/?text=${encodeURIComponent(texto)}`, target: "_blank", rel: "noopener", onclick: () => evento("compartilhar", { metodo: "whatsapp", conteudo: "geral" }) }, "Mandar no WhatsApp"))));
  }

  // ================================================================== cabeçalho da página
  // Busca no cabeçalho fixo: a lupa abre um campo logo abaixo do logo, em qualquer página e em qualquer ponto da rolagem.
  let fecharBuscaTopo = () => {};
  function ligarBuscaTopo() {
    const botao = $("#abrir-busca"), painel = $("#busca-topo-caixa"), campo = $("#busca-topo"), sug = $("#sugestoes-topo");
    if (!botao || !painel || !campo || !sug) return;
    const rotulo = $(".cabecalho__buscar-texto", botao);
    const marcar = (aberto) => { painel.hidden = !aberto; botao.setAttribute("aria-expanded", String(aberto)); if (rotulo) rotulo.textContent = aberto ? "Fechar" : "Buscar"; };
    fecharBuscaTopo = () => { if (!painel.hidden) { marcar(false); campo.value = ""; sug.hidden = true; const est = $("#estados-topo"); if (est) est.hidden = false; } };
    botao.addEventListener("click", () => {
      if (!painel.hidden) { fecharBuscaTopo(); return; }
      marcar(true); campo.focus();
      evento("abrir_busca", { pagina: S.sel ? "politico" : S.gov ? "governador" : S.cidade ? "cidade" : S.extra || "inicio" });
    });
    // Esc com a lista de sugestões fechada fecha o campo (com a lista aberta, o primeiro Esc fecha só a lista)
    campo.addEventListener("keydown", (e) => { if (e.key === "Escape" && sug.hidden) { fecharBuscaTopo(); botao.focus(); } });
    // embaixo do campo: escolher o estado abre o guia já com o governador, os senadores e os deputados dele
    const estados = $("#estados-topo"), ufs = $("#ufs-topo");
    if (estados && ufs) {
      UFS.forEach((u) => ufs.append(h("button", { type: "button", title: ESTADOS[u], "aria-label": ESTADOS[u], onclick: () => { fecharBuscaTopo(); abrirGuia(u, "busca_topo"); } }, u)));
      const gov = $("#governo-topo");
      if (gov) gov.addEventListener("click", () => { fecharBuscaTopo(); abrirGuia("governo", "busca_topo"); });
      campo.addEventListener("input", () => { estados.hidden = !!campo.value.trim(); });
    }
    ligarBusca(campo, sug, (p) => { S.origem = "busca_topo"; escolher(p.id); }, null, true, "busca_topo");
  }
  function montarCabecalho() {
    const D = S.D, noCargo = D.p.filter((p) => p.x).length;
    // os números da abertura, em blocos sobre a faixa escura
    const chips = $("#chips-info");
    chips.textContent = "";
    const numero = (n, texto) => h("p", { class: "numero" }, h("strong", null, String(n)), h("span", null, texto));
    const nVer = D.p.filter((p) => p.x && p.k === "v").length, nPref = D.p.filter((p) => p.x && p.k === "p").length;
    add(chips,
      numero(D.p.filter((p) => p.x && (p.k === "d" || p.k === "s")).length, "deputados e senadores no cargo"),
      numero(D.p.filter((p) => p.x && p.k === "e").length, "no governo federal"),
      GOV.e.length ? numero(GOV.e.length, "governadores") : null,
      cidadesCamara().length ? numero(nVer, cidadesCamara().length === 1 ? `vereadores ${deCid(cidadesCamara()[0].cod)}` : `vereadores em ${cidadesCamara().length} capitais`) : null,
      cidadesPrefeitura().length ? numero(nPref, cidadesPrefeitura().length === 1 ? "na Prefeitura" : `nas prefeituras de ${cidadesPrefeitura().length} capitais`) : null,
      h("p", { class: "numeros__data" }, `Dados até ${MESES[mesAtual() - 1]}/${anoAtual()} · atualizado em ${D.meta.atualizado}`));
    const sel = $("#estado");
    sel.replaceWith(seletorUF("estado", S.ufLista, (v) => { S.ufLista = v; if (v) evento("ver_estado", { uf: v }); listaEstado(); }, "Ver por estado"));
    ligarBusca($("#busca"), $("#sugestoes"), (p) => { S.origem = "busca"; escolher(p.id); }, null, true);
    ligarBuscaTopo();
    $("#abrir-guia").addEventListener("click", abrirGuia);
    document.querySelectorAll("[data-ir]").forEach((b) => b.addEventListener("click", () => irPara(b.dataset.ir)));
    const pend = $("#pendencias");
    D.meta.pendencias.forEach((t) => pend.append(h("li", null, t)));
    // cliques em links para fora (fontes oficiais, GitHub, e-mail de contato) e temas do "Entenda" abertos
    document.addEventListener("click", (ev) => {
      const a = ev.target.closest && ev.target.closest("a[href]");
      if (!a) return;
      const href = a.getAttribute("href"), onde = a.closest("footer") ? "rodape" : (a.closest("[id]") || {}).id || "";
      if (href.startsWith("mailto:")) { evento(a.dataset.evento || "contato", { onde }); return; }
      if (!/^https?:/.test(href) || a.href.startsWith(location.origin)) return;
      let dominio = ""; try { dominio = new URL(a.href).hostname.replace(/^www\./, ""); } catch (e) { /* link estranho */ }
      if (dominio === "wa.me") return; // já medido como "compartilhar"
      evento(dominio === "github.com" ? "abrir_github" : "abrir_fonte", { dominio, onde });
    });
    const ent = $("#entenda");
    if (ent) ent.addEventListener("toggle", (ev) => {
      const s = ev.target.open && ev.target.querySelector("summary");
      if (s) evento("abrir_entenda", { tema: s.textContent.trim().slice(0, 60) });
    }, true);
    const rn = $("#renda-numeros"), R = D.meta.renda;
    if (rn && R) {
      const tri = (t) => t.replace("/", " trimestre de ");
      add(rn, `São cerca de ${num(R.pessoas / 1e6, 0)} milhões de pessoas (do ${tri(R.trimestres[R.trimestres.length - 1])} ao ${tri(R.trimestres[0])}). `,
        `Metade ganha até ${num(R.mediana_sm, 1)} salário mínimo por mês, e só 1% ganha mais que ${num(R.p99_sm, 1)} salários mínimos. `,
        h("a", { href: R.url, target: "_blank", rel: "noopener" }, "Fonte: IBGE\u00a0↗"));
    }
    $("#gerado-em").textContent = `Gerado em ${D.meta.atualizado}.`;
  }
  function listaEstado() {
    const caixa = $("#lista-estado");
    caixa.textContent = "";
    if (!S.ufLista) return;
    const doEstado = S.D.p.filter((p) => p.uf === S.ufLista && p.x).sort((a, b) => a.n.localeCompare(b.n, "pt-BR"));
    const chip = (p) => h("button", { type: "button", class: "pessoa-chip", onclick: () => { S.origem = "estado"; escolher(p.id); } }, avatar(p, "p"), p.n, h("small", null, p.pt));
    const sen = doEstado.filter((p) => p.k === "s"), dep = doEstado.filter((p) => p.k === "d");
    const g = GOV.porUF[S.ufLista];
    add(caixa, h("div", { class: "lista-estado" },
      g ? h("div", { class: "lista-estado__grupo" }, h("a", { class: "pessoa-chip", href: urlGov(g.uf), onclick: () => { S.origem = "estado"; } },
        avatar({ n: g.gov.n, f: g.gov.f }, "p"), g.gov.n, h("small", null, `${tituloGov(g)} · ${reais(g.v[0])} por mês`))) : null,
      h("p", { class: "rotulo" }, `${ESTADOS[S.ufLista]}: ${sen.length} senadores e ${dep.length} deputados federais no cargo`),
      h("div", { class: "lista-estado__grupo" }, sen.map(chip)),
      h("div", { class: "lista-estado__grupo" }, dep.map(chip))));
  }
  function navSecoes(ids) {
    const nomes = { indice: "Índice", "indice-como": "Como funciona", correcoes: "Correções", prefeitura: "A Prefeitura", contracheque: "Contracheque", "mes-a-mes": "Mês a mês", equipe: "Equipe do gabinete", cota: "Detalhe dos gastos", comparar: "Comparar", tipico: "Parlamentar típico", governo: "Governo federal", governadores: "Governadores", governador: "O governador", cidade: "A Câmara", cidades: "Câmaras municipais", ranking: "Colegas e ranking", resumo: "Compartilhar", entenda: "Entenda", fontes: "Fontes" };
    const nav = $("#secoes");
    nav.textContent = "";
    ids.filter((id) => document.getElementById(id)).forEach((id) => nav.append(h("button", { type: "button", onclick: () => irPara(id) }, nomes[id])));
  }

  // ================================================================== guia passo a passo
  // inicio: a sigla de um estado (abre direto na lista dele) ou "governo"; origem: de onde a pessoa abriu
  function abrirGuia(inicio, origem) {
    if (typeof inicio !== "string") inicio = null; // chamado direto pelo clique de um botão
    const dlg = $("#guia"), corpo = $("#guia-corpo");
    const topo = (passo, titulo) => h("div", { class: "guia__topo" },
      h("p", { class: "rotulo" }, `Passo ${passo} de 2`, h("span", { class: "progresso" }, h("span", { class: "feito" }), h("span", { class: passo === 2 ? "feito" : "" }))),
      h("button", { type: "button", class: "fechar", "aria-label": "Fechar", onclick: () => fechar() }, "×"));
    const fechar = () => { if (dlg.close) dlg.close(); else dlg.removeAttribute("open"); };
    const passo1 = () => {
      corpo.textContent = "";
      add(corpo, topo(1),
        h("h2", { id: "guia-titulo" }, "Quem te representa em Brasília?"),
        h("p", { class: "discreto" }, "Cada estado elege um governador, 3 senadores e de 8 a 70 deputados federais. Escolha o seu estado para ver quem são e quanto cada um ganha e custa."),
        h("p", null, h("strong", null, "Em qual estado você vota?")),
        h("div", { class: "ufs" }, UFS.map((u) => h("button", { type: "button", title: ESTADOS[u], onclick: () => passo2(u) }, u))),
        h("div", { class: "guia__outros" },
          h("p", null, h("strong", null, "Ou veja quem não depende do estado")),
          h("button", { type: "button", class: "guia__opcao", onclick: passoGoverno },
            h("span", null, h("strong", null, "Governo federal"), h("small", null, "Presidente, vice e ministros")), h("span", { "aria-hidden": "true" }, "→")),
          h("button", { type: "button", class: "guia__opcao", onclick: () => { evento("guia", { etapa: "cidades" }); fechar(); if (location.pathname === "/") irPara("cidades"); else navegar("/#cidades"); } },
            h("span", null, h("strong", null, "Câmara da sua cidade"), h("small", null, "Vereadores e quanto custa a Câmara")), h("span", { "aria-hidden": "true" }, "→"))),
        h("div", { class: "guia__rodape" }, h("button", { type: "button", class: "link-botao", onclick: () => { evento("guia", { etapa: "pulou" }); fechar(); } }, "Pular e ver o painel")));
    };
    // quem não é eleito por estado: presidente, vice e ministros (depois, outros grupos)
    const passoGoverno = () => {
      evento("guia", { etapa: "governo" });
      corpo.textContent = "";
      const ordem = { pr: 0, vp: 1, mi: 2 };
      const pessoas = S.D.p.filter((p) => p.k === "e" && p.x).sort((a, b) => ordem[a.tp] - ordem[b.tp] || a.n.localeCompare(b.n, "pt-BR"));
      const lista = h("div", { class: "guia__lista" });
      const pintar = (q) => {
        lista.textContent = "";
        const itens = pessoas.filter((p) => !q || buscaTexto(p).includes(semAcento(q)));
        for (const [grupo, titulo] of [[["pr", "vp"], "Presidente e vice"], [["mi"], "Ministros"]]) {
          const g = itens.filter((p) => grupo.includes(p.tp));
          if (!g.length) continue;
          lista.append(h("p", { class: "rotulo", style: "margin-top:8px" }, `${titulo} (${g.length})`));
          g.forEach((p) => lista.append(h("button", { type: "button", class: "sugestao", onclick: () => { fechar(); S.origem = "guia"; escolher(p.id); } },
            avatar(p, "p"), h("span", null, p.n, h("small", null, p.g)))));
        }
        if (!lista.children.length) lista.append(h("p", { class: "discreto pequeno" }, "Ninguém encontrado."));
      };
      add(corpo, topo(2),
        h("h2", { id: "guia-titulo" }, "Governo federal"),
        h("p", { class: "discreto" }, "Presidente, vice e ministros no cargo hoje. Toque num nome para ver quanto ganha e quanto custa."),
        h("input", { type: "search", id: "guia-filtro", placeholder: "Filtrar por nome ou ministério", autocomplete: "off", oninput: (e) => pintar(e.target.value) }),
        lista,
        h("div", { class: "guia__rodape" },
          h("button", { type: "button", class: "link-botao", onclick: passo1 }, "← Voltar"),
          h("button", { type: "button", class: "link-botao", onclick: () => { fechar(); irPara("governo"); } }, "Ver todos na página")));
      pintar("");
    };
    const passo2 = (uf) => {
      evento("guia", { etapa: "estado", uf });
      corpo.textContent = "";
      const doEstado = S.D.p.filter((p) => p.uf === uf && p.x).sort((a, b) => a.k.localeCompare(b.k) * -1 || a.n.localeCompare(b.n, "pt-BR"));
      const lista = h("div", { class: "guia__lista" });
      const pintar = (q) => {
        lista.textContent = "";
        const itens = doEstado.filter((p) => !q || buscaTexto(p).includes(semAcento(q)));
        for (const [casa, titulo] of [["s", "Senadores"], ["d", "Deputados federais"]]) {
          const grupo = itens.filter((p) => p.k === casa);
          if (!grupo.length) continue;
          lista.append(h("p", { class: "rotulo", style: "margin-top:8px" }, `${titulo} (${grupo.length})`));
          grupo.forEach((p) => lista.append(h("button", { type: "button", class: "sugestao", onclick: () => { fechar(); S.ufLista = uf; S.origem = "guia"; escolher(p.id); } },
            avatar(p, "p"), h("span", null, p.n, h("small", null, `${p.g} · ${partidoUF(p)}`)))));
        }
      };
      add(corpo, topo(2),
        h("h2", { id: "guia-titulo" }, `Seus representantes: ${ESTADOS[uf]}`),
        h("p", { class: "discreto" }, "Toque num nome para ver o contracheque do mandato."),
        GOV.porUF[uf] ? (() => { const g = GOV.porUF[uf]; return h("button", { type: "button", class: "guia__opcao", onclick: () => { evento("guia", { etapa: `governador_${uf}` }); fechar(); S.origem = "guia"; navegar(urlGov(uf)); } },
          h("span", null, h("strong", null, `${tituloGov(g)}: ${g.gov.n}`), h("small", null, `Salário de ${reais(g.v[0])} por mês. Veja a lei e quem governou desde 2023`)), h("span", { "aria-hidden": "true" }, "→")); })() : null,
        [...new Set([...cidadesCamara(), ...cidadesPrefeitura()].filter((c) => c.uf === uf).map((c) => c.cod))].map((cod) => {
          const c = { ...(camaraDe(cod) || prefeituraDe(cod)), cod };
          const partes = [camaraDe(cod) ? `os ${S.D.p.filter((q) => q.k === "v" && q.x && q.cid === cod).length} vereadores` : null, prefeituraDe(cod) ? "a Prefeitura" : null].filter(Boolean);
          return h("button", { type: "button", class: "guia__opcao", onclick: () => { evento("guia", { etapa: `capital_${cod}` }); fechar(); S.origem = "guia"; navegar(urlDe(`cid-${cod}`)); } },
            h("span", null, h("strong", null, `Mora ${COM_ARTIGO.has(cod) ? "no" : "em"} ${c.n}?`), h("small", null, `Veja também ${listaE(partes)} da capital, um a um`)), h("span", { "aria-hidden": "true" }, "→"));
        }),
        h("input", { type: "search", id: "guia-filtro", placeholder: "Filtrar por nome ou partido", autocomplete: "off", oninput: (e) => pintar(e.target.value) }),
        lista,
        h("div", { class: "guia__rodape" },
          h("button", { type: "button", class: "link-botao", onclick: passo1 }, "← Outro estado"),
          h("button", { type: "button", class: "link-botao", onclick: () => { fechar(); S.ufLista = uf; const e = $("#estado"); if (e) e.value = uf; listaEstado(); irPara("rotulo-escolha"); } }, "Ver todos na página")));
      pintar("");
    };
    if (inicio === "governo") passoGoverno(); else if (inicio && ESTADOS[inicio]) passo2(inicio); else passo1();
    evento("guia", { etapa: "abrir", origem: typeof origem === "string" ? origem : "botao" });
    if (dlg.showModal) dlg.showModal(); else dlg.setAttribute("open", "");
  }

  // ================================================================== página
  // ------------------------------------------------------------------ endereços e navegação
  // Cada página tem o seu endereço (/guilherme-boulos, /cidade/sao-paulo-sp, /governador/sp); o "#" fica só para as
  // seções da página (#ranking). Os links internos trocam de página sem recarregar (history.pushState), e os links
  // antigos (/#dep-220639~2025, /#cid-3550308, /#gov-SP) levam para o endereço novo.
  let ultimoLocal = null; // caminho + período da página desenhada (para saber quando só o # mudou)
  function trocarEndereco(url) { history.replaceState(null, "", url); ultimoLocal = location.pathname + location.search; }
  function navegar(url) {
    fecharBuscaTopo();
    if (url === location.pathname + location.search + location.hash) { aplicarEndereco("mesma"); return; }
    history.pushState(null, "", url);
    aplicarEndereco("nova");
  }
  function escolher(id) { navegar(urlDe(id)); }
  // endereço antigo, com # (/#dep-220639~2025): troca pelo novo, sem criar uma entrada a mais no histórico
  function converterAntigo() {
    const bruto = decodeURIComponent(location.hash.slice(1));
    if (!bruto) return false;
    const [base, per] = bruto.split("~");
    let url = null;
    if (/^gov-[a-z]{2}$/i.test(base) && GOV.porUF[base.slice(4).toUpperCase()]) url = urlGov(base.slice(4));
    else if (/^cid-\d+$/.test(base)) url = urlDe(base);
    else if (S.porId.has(base)) url = urlPessoa(S.porId.get(base), per || null);
    if (!url) return false;
    history.replaceState(null, "", url);
    return true;
  }
  // modo: "inicio" (abriu o site), "nova" (clicou num link), "mesma" (clicou no link da página em que já está),
  // "voltar" (botão voltar/avançar do navegador: quem devolve a rolagem é o navegador)
  function aplicarEndereco(modo) {
    if (converterAntigo() && modo === "voltar") modo = "nova";
    const secao = decodeURIComponent(location.hash.slice(1)) || null;
    if (modo === "voltar" && location.pathname + location.search === ultimoLocal) { if (secao) irPara(secao); return; } // só o # mudou
    lerEndereco();
    ultimoLocal = location.pathname + location.search;
    // a seção do # (/nikolas-ferreira#ranking) pode só existir depois que os dados da página chegam: render() rola
    // até ela quando ela aparecer (rolarPendente)
    S.rolarPara = secao ? { id: secao, animar: modo === "mesma" } : null;
    // página nova: começa do topo (sem a abertura da página inicial, o contracheque já está lá em cima). Na primeira
    // visita, o navegador já abre no topo (ou devolve a rolagem de antes, num recarregar).
    if (!secao && (modo === "nova" || modo === "mesma")) irParaTopo();
    render();
    atualizarCanonico();
  }
  function rolarPendente() {
    const alvo = S.rolarPara;
    if (!alvo || !document.getElementById(alvo.id)) return;
    S.rolarPara = null;
    irPara(alvo.id, !alvo.animar); // numa página nova, sem animação (ver irPara)
  }
  function irParaTopo() {
    const raiz = document.documentElement, antes = raiz.style.scrollBehavior;
    raiz.style.scrollBehavior = "auto";
    window.scrollTo(0, 0);
    raiz.style.scrollBehavior = antes;
  }
  // a cidade escolhida: o ranking embaixo começa pelos vereadores dela (ou pela Prefeitura)
  function entrarNaCidade(c) {
    if (S.cidadeVista === c.id) return;
    S.cidadeVista = c.id;
    evento("ver_cidade", { cidade: c.id, origem: S.origemCidade || (S.carregado ? "navegacao" : "link") });
    if (camaraDe(c.cod)) Object.assign(S.rank, { casa: "v", cid: c.cod, periodo: "2025", uf: "", metrica: "custo", completo: false });
    else if (prefeituraDe(c.cod)) Object.assign(S.rank, { casa: "p", cid: c.cod, periodo: "2025", uf: "", metrica: "custo", completo: false });
  }
  // lê o endereço e diz qual página mostrar (S.sel, S.cidade ou S.gov; nenhum = página inicial)
  function lerEndereco() {
    const caminho = decodeURIComponent(location.pathname).replace(/^\/+|\/+$/g, "").replace(/\.html$/, "").toLowerCase();
    const q = new URLSearchParams(location.search).get("periodo");
    const per = q === "mandato" ? "leg" : q;
    S.naoAchada = false;
    const extraAntes = S.extra;
    S.extra = null;
    // cidade: /cidade/sao-paulo-sp (ou /cid-3550308, quando a lista de cidades ainda não tinha chegado)
    const mc = caminho.match(/^cidade\/(.+)$/) || caminho.match(/^(cid-\d+)$/);
    if (mc) {
      S.origemCidade = S.origem || (S.carregado ? "navegacao" : "link");
      S.origem = null; S.sel = null; S.gov = null; S.cidade = mc[1];
      return;
    }
    S.cidadeVista = null;
    // páginas do site que não são de um político: /correcoes e /indice
    if (caminho === "correcoes" || caminho === "indice") {
      if (extraAntes !== caminho) evento(`ver_${caminho}`, { origem: S.origem || (S.carregado ? "navegacao" : "link") });
      S.origem = null; S.sel = null; S.cidade = null; S.gov = null; S.extra = caminho;
      return;
    }
    const mg = caminho.match(/^governador\/([a-z]{2})$/);
    if (mg && GOV.porUF[mg[1].toUpperCase()]) {
      const uf = mg[1].toUpperCase();
      if (S.gov !== uf) evento("ver_governador", { uf, origem: S.origem || (S.carregado ? "navegacao" : "link") });
      S.origem = null; S.sel = null; S.cidade = null; S.gov = uf;
      return;
    }
    S.gov = null; S.cidade = null;
    let id = caminho ? END.porCaminho.get(caminho) || (S.porId.has(caminho) ? caminho : null) : null;
    if (!id && caminho && END.antigos[caminho] && S.porId.has(END.antigos[caminho])) {
      id = END.antigos[caminho]; // endereço que mudou: vai para o atual
      trocarEndereco(urlPessoa(S.porId.get(id), per) + location.hash);
    }
    if (id) {
      const p = S.porId.get(id);
      if (S.sel !== id) {
        S.outro = null; S.rank.completo = false;
        Object.assign(S.rank, { casa: null, periodo: null, uf: "", metrica: "custo" });
        evento("ver_parlamentar", { parlamentar: p.n, casa: casaTxt(p), uf: p.uf, partido: p.pt || "", origem: S.origem || (S.carregado ? "navegacao" : "link") });
      }
      S.origem = null;
      S.sel = id;
      S.periodo = per && periodos(p).includes(per) ? per : periodoPadrao(p);
      return;
    }
    // página inicial (ou endereço que não existe: mostra a inicial com um aviso)
    S.sel = null;
    S.naoAchada = !!caminho;
  }
  // o endereço "oficial" da página, para o Google (as versões com ?periodo= apontam para a principal)
  function atualizarCanonico() {
    const l = $('link[rel="canonical"]');
    if (l && endereco()) l.href = `${origem()}${S.naoAchada ? "/" : location.pathname}`;
  }
  // ------------------------------------------------------------------ "Encontrou um erro?" e a lista de correções
  // No fim de cada página: primeiro, os links para conferir na fonte oficial; só se a fonte mostrar outro valor, o
  // e-mail (já com o endereço da página). O que for corrigido entra em dados/correcoes.json (editado à mão) e aparece
  // em /correcoes.
  const CONTATO = "contato@contasdopoder.com";
  const SICONFI = "https://siconfi.tesouro.gov.br/siconfi/pages/public/declaracao/declaracao_list.jsf";
  // [texto, link] das fontes oficiais de cada página
  function fontesPessoa(p) {
    const nome = { d: "Página do deputado no site da Câmara", s: "Página do senador no site do Senado", e: "Página no Portal da Transparência",
      j: "Página no Portal da Transparência", v: "Página do vereador no site da Câmara Municipal", p: "Folha de pagamento da Prefeitura" }[p.k] || "Página oficial";
    const f = [[nome, p.o]];
    const par = p.k === "j" && p.j ? S.porId.get(p.j) : null; // tudo junto: a página do Congresso também
    if (par && par.o) f.push([par.k === "s" ? "Página do senador no site do Senado" : "Página do deputado no site da Câmara", par.o]);
    return f;
  }
  function fontesGov(e) {
    return [e.v && e.v[4] ? [`Lei ou fonte do salário ${deUF(e.uf)}`, e.v[4]] : null, e.folha && e.folha.u ? [`Folha de pagamento ${deUF(e.uf)}`, e.folha.u] : null];
  }
  function fontesCidade(c) {
    return [["Declarações das prefeituras ao Tesouro Nacional (Siconfi)", SICONFI]];
  }
  function blocoErro(nome, fontes) {
    const url = `${origem() || location.origin}${location.pathname}${location.search}`;
    const corpo = `Página: ${url}\n\nQual número está diferente (e de qual mês):\n\n\nO que a fonte oficial mostra (com o link):\n\n`;
    const mailto = `mailto:${CONTATO}?subject=${encodeURIComponent(`Erro no Contas do Poder: ${nome}`)}&body=${encodeURIComponent(corpo)}`;
    const links = (fontes || []).filter((f) => f && f[1]);
    return h("section", { class: "bloco", id: "erro", "aria-labelledby": "t-erro" },
      h("div", { class: "cartao erro-aviso" },
        h("h2", { id: "t-erro" }, "Encontrou um erro nesta página?"),
        h("p", null, h("strong", null, "Primeiro, confira na fonte. "),
          "Os números desta página vêm de fontes oficiais, com o link ao lado de cada bloco", links.length ? ". As principais:" : "."),
        links.length ? h("ul", { class: "erro-aviso__fontes" }, links.map(([t, u]) => h("li", null, h("a", { href: u, target: "_blank", rel: "noopener" }, `${t}\u00a0↗`)))) : null,
        h("p", { class: "discreto" }, h("strong", null, "A fonte mostra o mesmo valor? "),
          "Então é o que o órgão publicou, e quem pode corrigir é ele: fale com a ouvidoria do órgão ou faça um pedido pela Lei de Acesso à Informação."),
        h("details", { class: "erro-aviso__email", ontoggle: (ev) => { if (ev.target.open) evento("abrir_reportar_erro", { pagina: nome }); } },
          h("summary", null, "A fonte mostra outro valor?"),
          h("p", null, "Então o erro é nosso. Escreva para ", h("a", { href: mailto, "data-evento": "reportar_erro" }, CONTATO),
            " com o link desta página, o número que está diferente e o link da fonte. Conferimos, corrigimos e registramos o que mudou na ",
            h("a", { href: "/correcoes" }, "lista de correções"), "."))));
  }
  let correcoes = null;
  function carregarCorrecoes() {
    if (!correcoes) {
      correcoes = fetch("/dados/correcoes.json").then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); });
      correcoes.catch(() => { correcoes = null; }); // se falhar, tenta de novo na próxima vez
    }
    return correcoes;
  }
  // cada página corrigida: o id de um político ("dep-204558") ou um endereço ("governador/al")
  function linkCorrigido(ref) {
    const g = /^governador\/([a-z]{2})$/.exec(ref);
    if (g) return GOV.porUF[g[1].toUpperCase()] ? h("a", { href: urlGov(g[1]) }, `Governo ${deUF(g[1].toUpperCase())}`) : null;
    const p = S.porId.get(ref);
    return p ? h("a", { href: urlDe(ref) }, p.n) : null;
  }
  function secCorrecoes(C) {
    const itens = (C.c || []).map((c, i) => ({ ...c, i })).sort((a, b) => b.data.localeCompare(a.data) || a.i - b.i);
    const dataBR = (d) => d.split("-").reverse().join("/");
    return h("section", { class: "bloco", id: "correcoes", "aria-labelledby": "t-correcoes" },
      h("p", { class: "rotulo" }, "Transparência do site"),
      h("h1", { id: "t-correcoes", class: "titulo-pagina" }, "Correções"),
      h("p", { class: "discreto" }, C.intro || ""),
      itens.length ? h("ol", { class: "correcoes" }, itens.map((c) => {
        const links = (c.paginas || []).map(linkCorrigido).filter(Boolean);
        return h("li", { class: "cartao correcao" },
          h("p", { class: "rotulo" }, h("time", { datetime: c.data }, dataBR(c.data)), c.aviso ? ` · avisado por ${c.aviso}` : ""),
          h("h2", { class: "h3" }, c.titulo),
          (c.texto || []).map((t) => h("p", null, t)),
          links.length ? h("p", { class: "correcao__paginas pequeno" }, `${links.length === 1 ? "Página corrigida" : `Páginas corrigidas (${links.length})`}: `,
            links.map((a, i) => [i ? ", " : "", a])) : null);
      })) : h("p", null, "Nenhuma correção até agora."),
      h("p", { class: "discreto pequeno" }, "Viu outro erro? Use o \"Encontrou um erro?\" no fim da página do político ou escreva para ",
        h("a", { href: `mailto:${CONTATO}?subject=${encodeURIComponent("Erro no Contas do Poder")}`, "data-evento": "reportar_erro" }, CONTATO), "."));
  }

  // ------------------------------------------------------------------ Índice de Transparência dos estados
  // /indice: para cada estado, se dá para saber, pela fonte oficial, quanto ganham e quanto custam os seus políticos.
  // Um bloco para cada fonte (o governo e a Assembleia Legislativa), cada um com completude (o que a fonte mostra) e
  // facilidade (como dá para obter). Os números vêm de dados/indice_transparencia.json (feito pelo robô e conferido à
  // mão, "coletar.py indice"); os nomes dos blocos e dos critérios e o "como pontua" vêm de meta.blocos, não daqui.
  // Cada nota tem a prova e, às vezes, o link. O índice e as dimensões vão de 0 a 1, com duas casas, como no método.
  let indice = null;
  function carregarIndice() {
    if (!indice) {
      indice = fetch("/dados/indice_transparencia.json").then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); });
      indice.catch(() => { indice = null; }); // se falhar, tenta de novo na próxima vez
    }
    return indice;
  }
  const semNotaIdx = (v) => v === null || v === undefined;
  const notaIdx = (v) => (semNotaIdx(v) ? "a conferir" : num(v, 2));
  const notaCrit = (v) => (semNotaIdx(v) ? "a conferir" : v.toLocaleString("pt-BR", { maximumFractionDigits: 2 }));
  const dataBR = (d) => String(d || "").split("-").reverse().join("/");
  function secIndice(I) {
    const M = I.meta || {}, BL = M.blocos || [];
    const curto = (b) => String(b.titulo || b.id).split(" ")[0]; // "Governo do Estado" → "Governo"
    const comNota = I.estados.filter((e) => !semNotaIdx(e.indice) && !(e.a_conferir || []).length);
    const semNota = I.estados.filter((e) => !comNota.includes(e));
    // a posição usa o índice com as duas casas que a página mostra: dois estados com o mesmo número dividem a posição
    // e aparecem em ordem alfabética (0,905 e 0,914 aparecem os dois como 0,91)
    const r2 = (v) => Number(v.toFixed(2));
    const ordem = [...comNota.sort((a, b) => r2(b.indice) - r2(a.indice) || a.nome.localeCompare(b.nome, "pt-BR")), ...semNota.sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR"))];
    const posDe = (e) => 1 + comNota.filter((x) => r2(x.indice) > r2(e.indice)).length; // empate: a mesma posição
    const vals = comNota.map((e) => r2(e.indice)), med = mediana(vals);
    const maior = Math.max(...vals), menor = Math.min(...vals);
    const nomes = (v) => listaE(comNota.filter((e) => r2(e.indice) === v).map((e) => e.nome));
    const aberto = decodeURIComponent(location.hash.slice(1));
    const trilho = (v, tipo) => h("span", { class: `indice__trilho indice__trilho--${tipo}` }, semNotaIdx(v) ? null : h("span", { style: `width:${Math.max(1, v * 100).toFixed(1)}%` }));
    // na linha do estado, um bloco por linha: o nome curto, as duas dimensões em barras finas e o índice do bloco
    const blocoLinha = (e, b) => {
      const x = (e.blocos || {})[b.id] || {};
      return h("span", { class: `indice-bl${semNotaIdx(x.indice) ? " indice-bl--conferir" : ""}` },
        h("span", { class: "indice-bl__nome", "aria-hidden": "true" }, curto(b)),
        h("span", { class: "indice-bl__barras", "aria-hidden": "true" }, trilho(x.completude, "completude"), trilho(x.facilidade, "facilidade")),
        h("span", { class: "indice-bl__num", "aria-hidden": "true" }, notaIdx(x.indice)),
        h("span", { class: "visualmente-oculto" }, `. ${b.titulo}: ${semNotaIdx(x.indice) ? "a conferir" : `índice ${notaIdx(x.indice)}`} (completude ${notaIdx(x.completude)}; facilidade ${notaIdx(x.facilidade)})`));
    };
    const dimensao = (x, crit, d, titulo, sub) => h("div", { class: "indice-dimensao" },
      h("p", { class: "indice-dimensao__titulo" }, h("span", null, titulo), h("span", { class: "indice-dimensao__nota" }, notaIdx(x[d]))),
      h("p", { class: "pequeno discreto" }, sub),
      h("ul", { class: "criterios" }, crit.filter((c) => c.dimensao === d).map((c) => {
        const y = (x.criterios || {})[c.id] || {}, v = y.v;
        const falta = semNotaIdx(v);
        return h("li", { class: `criterio${falta ? " criterio--conferir" : ""}` },
          h("span", { class: "criterio__nome" }, c.nome),
          h("span", { class: "criterio__nota" }, falta ? null : h("span", { class: "criterio__medidor", "aria-hidden": "true" }, h("span", { style: `width:${(v * 100).toFixed(0)}%` })), notaCrit(v)),
          y.prova ? h("span", { class: "criterio__prova" }, y.prova, y.link ? [" ", h("a", { href: y.link, target: "_blank", rel: "noopener" }, "ver ↗")] : null) : null,
          h("span", { class: "criterio__como" }, c.como_pontua));
      })));
    // ao abrir o estado: cada bloco com os critérios, a fonte oficial e a página do site que mostra os números
    const blocoDetalhe = (e, b) => {
      const x = (e.blocos || {})[b.id] || {}, crit = b.criterios || [];
      const nConf = (x.a_conferir || []).length;
      return h("div", { class: `indice-bloco indice-bloco--${b.id}` },
        h("div", { class: "indice-bloco__topo" },
          h("p", { class: "indice-bloco__titulo" }, b.titulo),
          h("p", { class: `indice-bloco__nota${semNotaIdx(x.indice) ? " indice-bloco__nota--conferir" : ""}` }, semNotaIdx(x.indice) ? "a conferir" : notaIdx(x.indice))),
        b.pergunta ? h("p", { class: "pequeno discreto" }, b.pergunta) : null,
        semNotaIdx(x.indice) && nConf ? h("p", { class: "pequeno" }, h("strong", null, `${nConf} dos ${crit.length} critérios ainda estão a conferir`), "; o índice do bloco sai quando todos tiverem nota.") : null,
        h("div", { class: "indice-dimensoes" },
          dimensao(x, crit, "completude", "Completude", "O que a fonte mostra."),
          dimensao(x, crit, "facilidade", "Facilidade", "Como dá para obter os dados.")),
        h("p", { class: "indice-links" },
          x.fonte ? h("a", { href: x.fonte, target: "_blank", rel: "noopener" }, "Fonte oficial", h("span", { class: "visualmente-oculto" }, ` (${b.titulo}, ${e.nome})`), " ↗") : null,
          b.id === "governo" && GOV.porUF[e.uf] ? h("a", { href: urlGov(e.uf), onclick: () => { S.origem = "indice"; } }, `Salário do governador ${deUF(e.uf)} →`) : null));
    };
    const linha = (e) => {
      const falta = !comNota.includes(e), uf = e.uf.toLowerCase();
      const blocosConf = BL.filter((b) => (e.a_conferir || []).includes(b.id));
      return h("li", null, h("details", { class: `indice-estado${falta ? " indice-estado--conferir" : ""}`, id: `indice-${uf}`, open: aberto === `indice-${uf}`,
        ontoggle: (ev) => { if (ev.target.open) evento("abrir_indice", { uf: e.uf }); } },
        h("summary", null,
          h("span", { class: "indice__pos" }, falta ? "–" : `${posDe(e)}º`),
          h("span", { class: "indice__nome" }, e.nome),
          h("span", { class: "indice__valor" }, falta ? "a conferir" : notaIdx(e.indice)),
          h("span", { class: "indice__blocos" }, BL.map((b) => blocoLinha(e, b)))),
        h("div", { class: "indice-corpo" },
          falta ? h("p", { class: "aviso" }, blocosConf.length
            ? `Sem índice geral por enquanto: ${blocosConf.length === 1 ? "o bloco" : "os blocos"} ${listaE(blocosConf.map((b) => b.titulo))} ainda ${blocosConf.length === 1 ? "está" : "estão"} a conferir. As notas que já existem estão abaixo.`
            : "Sem índice geral por enquanto. As notas que já existem estão abaixo.") : null,
          BL.map((b) => blocoDetalhe(e, b)))));
    };
    const como = M.como || [];
    return [
      h("section", { class: "bloco", id: "indice", "aria-labelledby": "t-indice" },
        h("div", { class: "indice-topo" },
          h("p", { class: "rotulo" }, "Estados"),
          h("h1", { id: "t-indice", class: "titulo-pagina" }, M.titulo || "Índice de Transparência dos estados"),
          M.pergunta ? h("p", { class: "lide" }, M.pergunta) : null,
          h("p", { class: "pequeno" }, `Conferido em ${dataBR(M.conferido_em)}. ${comNota.length} estados com índice geral${semNota.length ? `; ${listaE(semNota.map((e) => e.nome))} a conferir` : ""}.`),
          como[0] ? h("p", { class: "caixa-nota" }, como[0]) : null),
        comNota.length ? h("div", { class: "estatisticas" },
          estatistica("Maior índice", notaIdx(maior), nomes(maior)),
          estatistica("Mediana dos estados", notaIdx(med), "metade tem índice maior, metade menor"),
          estatistica("Menor índice", notaIdx(menor), nomes(menor))) : null,
        h("div", { class: "legenda" },
          h("span", null, h("span", { class: "chave chave--ganha" }), "Completude: o que a fonte mostra"),
          h("span", null, h("span", { class: "chave chave--custa" }), "Facilidade: como dá para obter")),
        h("article", { class: "cartao indice-cartao" },
          h("p", { class: "pequeno discreto" }, `Do maior índice geral para o menor. Em cada estado, o índice de cada bloco (${listaE(BL.map(curto))}), com as duas dimensões em barras. Toque num estado para ver cada critério, a nota e a prova.`),
          h("ol", { class: "indice-lista" }, ordem.map(linha)))),
      h("section", { class: "bloco", id: "indice-como", "aria-labelledby": "t-indice-como" },
        h("h2", { id: "t-indice-como" }, "Como funciona"),
        h("div", { class: "cartao" },
          como.slice(1).map((c) => h("p", null, c)),
          BL.map((b) => h("div", { class: "indice-como-bloco" },
            h("h3", null, b.titulo),
            b.pergunta ? h("p", { class: "discreto" }, b.pergunta) : null,
            h("div", { class: "indice-dimensoes" },
              [["completude", "Completude: o que a fonte mostra"], ["facilidade", "Facilidade: como dá para obter"]].map(([d, titulo]) => h("div", null,
                h("h4", null, titulo),
                h("dl", { class: "indice-criterios" }, (b.criterios || []).filter((c) => c.dimensao === d).map((c) => [h("dt", null, c.nome), h("dd", null, c.como_pontua)]))))))),
          h("p", { class: "nota" }, "Os dados do índice, com todas as notas e provas: ", h("a", { href: "/dados/indice_transparencia.json" }, "indice_transparencia.json"), ". O robô confere as fontes toda semana."))),
    ];
  }

  // ------------------------------------------------------------------ série mês a mês e detalhe dos gastos de cada pessoa
  // No site publicado, a lista de todos (dados/indice/) vem sem a série mês a mês (p.t) e sem o detalhe dos gastos (p.dt):
  // cada pessoa tem o seu arquivo (dados/pessoa/<id>.json, feito pelo publicacao/gerar.mjs), baixado só ao abrir a
  // página dela. Direto de site/ (sem o gerar.mjs), o app lê os arquivos inteiros e p.t já está lá.
  const detalhes = new Map();
  function carregarDetalhe(p) {
    if (p.t) return Promise.resolve(p);
    if (!detalhes.has(p.id)) {
      const pr = fetch(`/dados/pessoa/${encodeURIComponent(p.id)}.json`).then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
        .then((d) => { p.t = d.t || []; p.dt = d.dt || {}; return p; });
      pr.catch(() => detalhes.delete(p.id)); // se falhar, tenta de novo na próxima vez
      detalhes.set(p.id, pr);
    }
    return detalhes.get(p.id);
  }
  // enquanto o detalhe não chega: o topo do contracheque (nome, período, custo por mês e posição), que só usa a lista
  function previaPessoa(p) {
    const k = S.periodo || periodoPadrao(p), r = resumo(p, k), C = colegasDe(p, k);
    return h("article", { class: "cartao conta", id: "previa" },
      h("div", { class: "conta__topo" }, avatar(p, "g"),
        h("div", null, h("p", { class: "rotulo" }, "Contracheque"), h("h1", { class: "conta__nome" }, p.n),
          h("div", { class: "conta__sub" }, h("span", null, `${p.g} · ${partidoUF(p)}`), etiquetaCargo(p)))),
      resumoTopo(p, k, r, C, posicao(p, k), () => {}),
      h("p", { class: "carregando", role: "status" }, "Carregando o mês a mês e o detalhe dos gastos…"));
  }
  // página inicial ou página "interna" (político, estado, cidade, correções): nas internas, a abertura da página
  // inicial some e o título (h1) é o nome da pessoa, do estado ou da cidade (estilo.css: body.interna)
  // No "Entenda", as páginas internas mostram só os temas daquele tipo de página (index.html: data-para); os temas sem
  // data-para (como calculamos, "ganha mais que X%", o que ainda falta) aparecem sempre.
  function marcarPagina(interna, tipo) {
    document.body.classList.toggle("interna", interna);
    const t = document.getElementById("titulo-abertura");
    if (t && !interna && t.tagName !== "H1") { const n = h("h1", { id: "titulo-abertura" }); n.append(...t.childNodes); t.replaceWith(n); }
    const li = document.getElementById("link-indice");
    if (li) { if (tipo === "indice") li.setAttribute("aria-current", "page"); else li.removeAttribute("aria-current"); }
    document.querySelectorAll("#entenda details[data-para]").forEach((d) => { d.hidden = !!tipo && !d.dataset.para.split(" ").includes(tipo); });
  }

  function render() {
    observadores.forEach((o) => o.disconnect()); observadores = [];
    botaoFlutuante(null);
    const app = $("#app");
    const p = S.sel ? S.porId.get(S.sel) : null;
    marcarPagina(!!(p || S.gov || S.cidade || S.extra), p ? p.k : S.gov ? "gov" : S.cidade ? "cidade" : S.extra === "indice" ? "indice" : null);
    if (p && !p.t) {
      document.title = `${p.n} · Contas do Poder`;
      // primeira visita: o resumo pronto do HTML (gerar.mjs, no período padrão) fica na tela; trocando de página ou com
      // outro período no endereço, a prévia feita aqui
      const k = S.periodo || periodoPadrao(p), pv = $("#previa", app);
      if (!pv || pv.dataset.id !== p.id || pv.dataset.k !== k) {
        app.textContent = "";
        app.append(add(previaPessoa(p), null));
        Object.assign($("#previa", app).dataset, { id: p.id, k });
      }
      navSecoes(["entenda", "fontes"]);
      carregarDetalhe(p).then(() => { if (S.sel === p.id) render(); }, () => {
        if (S.sel !== p.id) return;
        const st = $("#previa .carregando", app);
        if (st) { st.textContent = "Não foi possível carregar o mês a mês. "; st.append(h("button", { type: "button", class: "link-botao", onclick: () => render() }, "Tentar de novo")); }
      });
      return;
    }
    app.textContent = "";
    if (S.extra === "correcoes") {
      document.title = "Correções · Contas do Poder";
      const espera = h("p", { class: "discreto" }, "Carregando as correções…");
      app.append(espera);
      navSecoes(["entenda", "fontes"]);
      carregarCorrecoes().then((C) => {
        if (!espera.isConnected) return; // já foi para outra página
        espera.replaceWith(secCorrecoes(C));
        navSecoes(["correcoes", "entenda", "fontes"]);
        rolarPendente();
      }, () => { espera.textContent = "Não foi possível carregar as correções."; });
      return;
    }
    if (S.extra === "indice") {
      document.title = "Índice de Transparência dos estados · Contas do Poder";
      const espera = h("p", { class: "discreto" }, "Carregando o índice…");
      app.append(espera);
      navSecoes(["entenda", "fontes"]);
      carregarIndice().then((I) => {
        if (!espera.isConnected) return; // já foi para outra página
        espera.replaceWith(...secIndice(I));
        navSecoes(["indice", "indice-como", "entenda", "fontes"]);
        rolarPendente();
      }, () => { espera.textContent = "Não foi possível carregar o índice."; });
      return;
    }
    if (S.gov) {
      const e = GOV.porUF[S.gov];
      document.title = `${tituloGov(e)} ${deUF(e.uf)} · Contas do Poder`;
      app.append(...[secGovernador(e), secCompartilhar(specGov(e), `A imagem e o texto mostram o salário do cargo ${deUF(e.uf)} e de onde vem o valor.`),
        secGovernadores(e), blocoErro(`${tituloGov(e)} ${deUF(e.uf)}`, fontesGov(e))].filter(Boolean));
      navSecoes(["governador", "resumo", "governadores", "entenda", "fontes"]);
      botaoFlutuante(specGov(e), "#governador .estatisticas");
      rolarPendente();
      return;
    }
    if (S.cidade) {
      document.title = "Câmara Municipal · Contas do Poder";
      const espera = h("p", { class: "discreto" }, "Carregando a câmara…");
      app.append(espera);
      carregarCidades().then(() => {
        if (!espera.isConnected) return; // já foi para outra página
        const c = /^cid-\d+$/.test(S.cidade) ? CID.porId.get(S.cidade) : CID.porSlug.get(S.cidade);
        if (!c) { espera.textContent = "Cidade não encontrada."; return; }
        if (location.pathname !== urlCidade(c)) { trocarEndereco(urlCidade(c) + location.hash); atualizarCanonico(); }
        entrarNaCidade(c);
        document.title = `Câmara ${deCidade(c)} · Contas do Poder`;
        espera.replaceWith(...[secCidade(c), secPrefeitura(c), camaraDe(c.cod) || prefeituraDe(c.cod) ? secRanking(null, null) : null,
          secCompartilhar(specCidade(c), `A imagem e o texto mostram o custo da Câmara em ${c.ano}, pelas contas que a prefeitura entregou ao Tesouro Nacional (Siconfi).`),
          secCamaras(c), blocoErro(`${c.n} (${c.uf})`, fontesCidade(c))].filter(Boolean));
        navSecoes(["cidade", "prefeitura", "ranking", "resumo", "cidades", "entenda", "fontes"]);
        botaoFlutuante(specCidade(c), "#cidade .estatisticas");
        rolarPendente();
      }, () => { espera.textContent = "Não foi possível carregar as câmaras."; });
      return;
    }
    if (p) {
      const k = S.periodo || periodoPadrao(p);
      document.title = `${p.n} · Contas do Poder`;
      const papel = p.k === "j" ? S.porId.get((p.cg.find((c) => c.x) || p.cg[0]).id) || p : p;
      app.append(...[secContracheque(p, k), blocoCompartilhar(specPessoa(p, k), "depois_contracheque", "Compartilhe este contracheque"), secMensal(p, k), p.k === "v" ? secEquipe(p, k) || secEquipeVereador(p) : secEquipe(p, k), secCota(p, k), secRanking(papel, k, p.k === "j"), secComparar(p, k), secResumo(p, k), blocoErro(p.n, fontesPessoa(p))].filter(Boolean));
      navSecoes(["contracheque", "mes-a-mes", "equipe", "cota", "ranking", "comparar", "resumo", "entenda", "fontes"]);
      botaoFlutuante(specPessoa(p, k), "#contracheque .conta__resumo");
    } else {
      document.title = "Contas do Poder";
      if (S.naoAchada) app.append(h("p", { class: "aviso" }, "Não achamos esta página. Procure pelo nome acima ou veja os destaques abaixo."));
      app.append(...[secTipicos(), secGoverno(), secGovernadores(null), secCamaras(null), secRanking(null, null), secResumoGeral()].filter(Boolean));
      navSecoes(["tipico", "governo", "governadores", "cidades", "ranking", "resumo", "entenda", "fontes"]);
    }
    rolarPendente();
  }
  // voltar/avançar do navegador e # digitado na barra de endereço (inclusive os links antigos, /#dep-220639)
  window.addEventListener("popstate", () => aplicarEndereco("voltar"));
  window.addEventListener("hashchange", () => aplicarEndereco("voltar"));
  // links internos (href="/..."): troca de página sem recarregar. Ctrl/Cmd+clique e botão do meio abrem em outra aba.
  function ligarLinksInternos() {
    document.addEventListener("click", (ev) => {
      if (ev.defaultPrevented || ev.button !== 0 || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return;
      const a = ev.target.closest && ev.target.closest("a[href]");
      if (!a || (a.target && a.target !== "_self") || a.hasAttribute("download")) return;
      const href = a.getAttribute("href");
      if (!href.startsWith("/") || href.startsWith("//")) return;
      ev.preventDefault();
      navegar(href);
    });
  }

  // dados.json (Congresso e governo), camaras.json (vereador por vereador), prefeituras.json e governadores.json;
  // se um dos três últimos falhar, o site segue sem ele. No site publicado, dados.json e camaras.json vêm da versão leve
  // (dados/indice/, sem a série mês a mês e o detalhe dos gastos de cada um: ver carregarDetalhe); direto de site/, os
  // arquivos inteiros. (O Cloudflare Pages e o servir.mjs devolvem a página inicial, e não um erro, para arquivo que
  // não existe: o r.json() falha e vale o arquivo inteiro.)
  const lerJSON = (u) => fetch(u).then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); });
  const leve = (arq) => lerJSON(`/dados/indice/${arq}`).catch(() => lerJSON(`/dados/${arq}`));
  Promise.all([
    leve("dados.json"),
    leve("camaras.json").catch(() => null),
    lerJSON("/dados/prefeituras.json").catch(() => null),
    lerJSON("/dados/governadores.json").catch(() => null),
    lerJSON("/dados/enderecos.json").catch(() => null),
  ])
    .then(([D, camaras, prefeituras, governadores, enderecos]) => {
      if (enderecos) {
        for (const [id, cam] of Object.entries(enderecos.p || {})) { END.porId.set(id, cam); END.porCaminho.set(cam, id); }
        END.antigos = enderecos.antigos || {};
      }
      if (governadores) { GOV.meta = governadores.meta; GOV.e = governadores.e; GOV.e.forEach((e) => { GOV.porUF[e.uf] = e; }); }
      juntarMunicipal(D, camaras, "cidades");
      juntarMunicipal(D, prefeituras, "prefeituras");
      S.D = D;
      D.p.forEach((p) => S.porId.set(p.id, p));
      // vereador que está (ou esteve) na Prefeitura: a ligação vem do lado da Prefeitura; faz a volta
      D.p.forEach((p) => { const q = p.k === "p" && p.rel && S.porId.get(p.rel); if (q && !q.rel) q.rel = p.id; });
      montarCabecalho();
      ligarLinksInternos();
      aplicarEndereco("inicio");
      S.carregado = true;
      carregarCidades().catch(() => {});
    })
    .catch((e) => {
      const app = $("#app");
      app.textContent = "";
      app.append(h("p", { class: "aviso" }, `Não foi possível carregar os dados (${e.message}). Se você abriu o arquivo direto do computador, rode "node publicacao/gerar.mjs && node publicacao/servir.mjs" e acesse http://localhost:8000.`));
      console.error(e);
    });
})();
