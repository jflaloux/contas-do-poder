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
    D: null, porId: new Map(), sel: null, cidade: null, gov: null, periodo: null, outro: null, ufLista: "", origem: null, carregado: false,
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
  // Resumo de um período. "Custo dele" = o que vai para o bolso (ganha) + os gastos do mandato (custa).
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
  // "O custo dele fica acima de 57% dos ..."; no topo e no fim, "o maior" / "o menor"
  const fraseposicao = (p, pos) => (p.k === "p"
    ? (pos.pos === 1 ? `É quem mais recebe entre os ${plural(grupo(p))}` : pos.pos === pos.n ? `É quem menos recebe entre os ${plural(grupo(p))}` : `Recebe mais que ${pos.pct}% dos ${plural(grupo(p))}`)
    : pos.pos === 1 ? `É o maior custo entre os ${plural(grupo(p))}` : pos.pos === pos.n ? `É o menor custo entre os ${plural(grupo(p))}`
    : `O custo dele fica acima de ${pos.pct}% dos ${plural(grupo(p))}`);
  function posicao(p, k) {
    const C = colegas(grupo(p), k);
    const eu = C.lista.find((x) => x.p.id === p.id);
    if (!eu) return null;
    const acima = C.lista.filter((x) => x.r.tm > eu.r.tm).length;
    const abaixo = C.lista.filter((x) => x.r.tm < eu.r.tm).length;
    return { pos: acima + 1, n: C.n, pct: Math.round((abaixo / Math.max(1, C.n - 1)) * 100) };
  }

  // ================================================================== peças
  function avatar(p, tam) {
    const d = h("span", { class: "avatar" + (tam ? ` avatar--${tam}` : ""), "aria-hidden": "true" }, iniciais(p.n));
    if (p.f) {
      const img = h("img", { src: p.f, alt: "", loading: "lazy", referrerpolicy: "no-referrer" });
      img.addEventListener("error", () => img.remove());
      d.append(img);
    }
    return d;
  }
  const partidoUF = (p) => (p.k === "e" ? (p.pt ? `${p.pt} · governo federal` : "Governo federal")
    : p.k === "v" ? `${p.pt || "sem partido"} · ${(cidadeDe(p) || {}).n || "vereador"}` : p.k === "p" ? p.pt || `Prefeitura ${deCid(p.cid)}` : `${p.pt || "sem partido"}-${p.uf}`);
  const etiquetaCargo = (p) => (p.x ? h("span", { class: "etiqueta" }, "No cargo") : h("span", { class: "etiqueta etiqueta--fora" }, "Fora do cargo hoje"));
  function pilulas(opcoes, atual, aoEscolher, rotulo, classe) {
    return h("div", { class: classe || "pilulas", role: "group", "aria-label": rotulo },
      opcoes.map(([v, t]) => h("button", { type: "button", class: "pilula", "aria-pressed": String(v === atual), onclick: () => aoEscolher(v) }, t)));
  }
  function seloComp(v, med, texto) {
    if (!med || !v) return null;
    const dif = (v - med) / med;
    const pct = Math.round(dif * 100);
    const cls = pct > 2 ? "acima" : pct < -2 ? "abaixo" : "igual";
    return h("span", { class: "item__detalhe" }, h("span", { class: `selo-comp selo-comp--${cls}` }, `${pct > 0 ? "+" : ""}${pct}%`), `${texto} ${reais(med)}`);
  }
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
  const irPara = (id) => { const e = document.getElementById(id); if (e) e.scrollIntoView({ block: "start" }); };
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
  function ligarBusca(input, caixa, aoEscolher, filtro, comCidades) {
    let itens = [], ativo = -1;
    const fechar = () => { caixa.hidden = true; ativo = -1; };
    const marcar = () => [...caixa.children].forEach((b, i) => b.setAttribute("aria-selected", String(i === ativo)));
    input.addEventListener("input", () => {
      const pol = encontrar(input.value, filtro).slice(0, comCidades ? 6 : 8);
      const cid = comCidades ? encontrarCidades(input.value) : [];
      const govs = comCidades ? encontrarGov(input.value) : [];
      itens = [...govs, ...pol, ...cid];
      caixa.textContent = "";
      govs.forEach((e) => caixa.append(h("button", { type: "button", class: "sugestao", role: "option", onclick: () => { fechar(); input.value = ""; S.origem = "busca"; location.hash = `gov-${e.uf}`; } },
        avatar({ n: e.gov.n, f: e.gov.f }, "p"), h("span", null, e.gov.n, h("small", null, `${tituloGov(e)} ${deUF(e.uf)}${partidoTxt(e.gov).replace(/[()]/g, "").replace(/^ /, " · ")}`)))));
      cid.forEach((c) => caixa.append(h("button", { type: "button", class: "sugestao sugestao--cidade", role: "option", onclick: () => { fechar(); input.value = ""; irParaCidade(c, "busca"); } },
        iconeCidade(avatarCidade("p")), h("span", null, `Câmara Municipal de ${c.n} (${c.uf})`, h("small", null, `${c.nv} vereadores · ${num(c.pop, 0)} habitantes`)))));
      pol.forEach((p) => caixa.append(h("button", { type: "button", class: "sugestao", role: "option", onclick: () => { fechar(); input.value = ""; aoEscolher(p); } },
        avatar(p, "p"), h("span", null, p.n, h("small", null, `${p.g} · ${partidoUF(p)}${p.x ? "" : " · fora do cargo"}${p.rel && S.porId.get(p.rel) ? ` · também ${nomeRel(p.rel)}` : ""}`)))));
      if (input.value.trim().length >= 2 && !itens.length) caixa.append(h("p", { class: "pequeno discreto", style: "padding:8px" }, "Ninguém encontrado. Confira a grafia."));
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
      const W = Math.max(260, caixa.clientWidth), H = 240;
      const m = { t: 10, r: 4, b: 28, l: 62 };
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
        if (fx) svg.append(s("rect", { class: `faixa-cargo faixa-cargo--${fx}`, x: m.l + banda * i, y: m.t + ih + 3, width: banda + 0.5, height: 5 }));
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
      const W = Math.max(260, caixa.clientWidth), H = 150;
      const m = { t: 30, r: 14, b: 26, l: 14 };
      const iw = W - m.l - m.r, ih = H - m.t - m.b;
      const { ticks, topo } = escala(Math.max(...pares.map((p) => p.v)), 4);
      const x = (v) => m.l + (v / topo) * iw;
      const svg = s("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Onde cada um fica" });
      for (const t of ticks) {
        svg.append(s("line", { class: "grade", x1: x(t), x2: x(t), y1: m.t - 6, y2: H - m.b }));
        const tx = s("text", { x: x(t), y: H - 8, "text-anchor": t === 0 ? "start" : t === topo ? "end" : "middle" });
        tx.textContent = t === 0 ? "0" : fmt === reais ? compacto(t) : num(t, 0); svg.append(tx);
      }
      const pos = pares.map((p) => ({ ...p, cx: x(p.v), cy: m.t + 6 + ((hashNum(p.id) % 1000) / 1000) * (ih - 12) }));
      for (const p of pos) if (p.id !== euId) svg.append(s("circle", { class: "ponto", cx: p.cx, cy: p.cy, r: 3.5 }));
      const meu = pos.find((p) => p.id === euId);
      if (meu) {
        svg.append(s("line", { class: "guia-linha", x1: meu.cx, x2: meu.cx, y1: 16, y2: meu.cy - 6 }));
        svg.append(s("circle", { class: "ponto--eu", cx: meu.cx, cy: meu.cy, r: 6.5 }));
        const tx = s("text", { class: "forte", x: meu.cx, y: 12, "text-anchor": meu.cx < W * 0.2 ? "start" : meu.cx > W * 0.8 ? "end" : "middle" });
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
      svg.addEventListener("click", (ev) => { const p = achar(ev); if (p && p.id !== euId) { S.origem = "grafico"; location.hash = p.id; } });
      svg.addEventListener("pointerleave", () => { d.hidden = true; destaque.setAttribute("visibility", "hidden"); });
      caixa.prepend(svg);
    };
    aoRedimensionar(caixa, desenhar); desenhar();
  }
  // ================================================================== compartilhar
  const endereco = () => (($('meta[name="endereco-do-site"]') || {}).content || "").replace(/#.*$/, "");
  const dominio = () => endereco().replace(/^https?:\/\//, "").replace(/\/$/, "") || "contasdopoder.com";
  const pessoasTxt = (n) => `${num(n, n < 10 && n % 1 ? 1 : 0)} ${Math.round(n) === 1 ? "pessoa" : "pessoas"}`;
  const linkDe = (p, k) => (endereco() ? `${endereco()}#${p.id}${k !== periodoPadrao(p) ? "~" + k : ""}` : "");
  // o aviso curto da imagem, conforme o que a Câmara de cada cidade publica
  function avisoVereador(p) {
    const c = cidadeDe(p) || {};
    return [c.subsidio_folha ? "Salário pela folha de pagamento da Câmara." : "Salário igual para todos.",
      c.equipe_custo ? null : p.eq ? "O custo da equipe do gabinete não é publicado." : "A equipe de cada gabinete não é publicada."].filter(Boolean).join(" ");
  }
  function textoCompartilhar(p, k) {
    const r = resumo(p, k), pos = posicao(p, k);
    const link = linkDe(p, k);
    return [
      `*${p.n}* (${p.g}, ${partidoUF(p)}) ${nomePeriodo(k, false)}:`,
      `${p.k === "p" ? "Recebe" : "Custo dele"}: *${reais(r.tm)} por mês*`,
      `• Vai para o bolso: ${reais(r.gm)} por mês (${sm(emSalariosMinimos(p, k, "g"))} salários mínimos)`,
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
  function carregarImagem(src) {
    return new Promise((ok) => { const img = new Image(); img.onload = () => ok(img); img.onerror = () => ok(null); img.src = src; });
  }
  async function imagemCompartilhar(p, k) {
    const r = resumo(p, k), pos = posicao(p, k);
    if (!r) return null;
    try { await Promise.all(['800 64px "Bricolage Grotesque"', '600 30px "Public Sans"', '500 60px "IBM Plex Mono"'].map((f) => document.fonts.load(f))); } catch (e) { /* usa a fonte do sistema */ }
    const W = 1080, H = 1350, M = 72, cv = document.createElement("canvas");
    cv.width = W; cv.height = H;
    const g = cv.getContext("2d");
    const DISP = '"Bricolage Grotesque", "Public Sans", sans-serif', BODY = '"Public Sans", system-ui, sans-serif', MONO = '"IBM Plex Mono", monospace';
    const C = { fundo: "#17142e", cartao: "#221d42", ink: "#f2f0fb", ink2: "#c4bfe0", linha: "rgba(242,240,251,.28)", marca: "#4430c2", hi: "#ff6f9f", ganha: "#3987e5", custa: "#eb6834", equipe: "#1baf7a" };
    const caixa = (x, y, w, alt, raio) => { g.beginPath(); if (g.roundRect) g.roundRect(x, y, w, alt, raio); else g.rect(x, y, w, alt); };
    const quebra = (texto, x, y, max, lh, maxLinhas) => {
      let linha = "", n = 0;
      for (const w of texto.split(" ")) {
        const t = linha ? `${linha} ${w}` : w;
        if (g.measureText(t).width > max && linha && n < maxLinhas - 1) { g.fillText(linha, x, y); y += lh; n++; linha = w; } else linha = t;
      }
      g.fillText(linha, x, y); return y + lh;
    };
    const direita = (t, x, y) => g.fillText(t, x - g.measureText(t).width, y);
    // escreve um valor seguido de "/mês" menor, na mesma linha de base
    const comMes = (valor, x, y, fonte, tamanho, cor) => {
      g.fillStyle = cor; g.font = fonte; g.fillText(valor, x, y);
      const w = g.measureText(valor).width;
      g.fillStyle = C.ink2; g.font = `500 ${tamanho}px ${BODY}`; g.fillText("/mês", x + w + 6, y);
      return w + 6 + g.measureText("/mês").width;
    };
    const bolinha = (cor, x, y) => { g.fillStyle = cor; g.beginPath(); g.arc(x, y, 11, 0, 7); g.fill(); };
    g.fillStyle = C.fundo; g.fillRect(0, 0, W, H);
    g.fillStyle = C.marca; g.fillRect(0, 0, W * 0.72, 12); g.fillStyle = C.hi; g.fillRect(W * 0.72, 0, W * 0.28, 12);
    // marca
    g.fillStyle = C.marca; caixa(M, 52, 64, 64, 14); g.fill();
    const svg = $(".logo__icone svg");
    if (svg) {
      const logo = await carregarImagem("data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg.outerHTML.replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" fill="#ffffff" ')));
      if (logo) g.drawImage(logo, M + 11, 63, 42, 42);
    }
    g.textBaseline = "middle"; g.fillStyle = C.ink; g.font = `700 36px ${DISP}`; g.fillText("Contas do Poder", M + 82, 85);
    g.textBaseline = "alphabetic";
    // foto e nome
    const fy = 148, fw = 150, fh = 200;
    const foto = p.f && p.f.startsWith("fotos/") ? await carregarImagem(p.f) : null;
    g.save(); caixa(M, fy, fw, fh, 20); g.clip();
    if (foto) g.drawImage(foto, M, fy, fw, fh);
    else { g.fillStyle = C.cartao; g.fillRect(M, fy, fw, fh); g.fillStyle = C.ink2; g.font = `700 64px ${DISP}`; g.textAlign = "center"; g.fillText(iniciais(p.n), M + fw / 2, fy + fh / 2 + 22); g.textAlign = "left"; }
    g.restore();
    const tx = M + fw + 32, tmax = W - M - tx, grande = p.n.length <= 22;
    g.fillStyle = C.ink2; g.font = `600 24px ${BODY}`; g.fillText({ e: "CONTRACHEQUE DO CARGO", j: "DOIS CARGOS, SOMADOS", p: "CONTRACHEQUE DO CARGO" }[p.k] || "CONTRACHEQUE DO MANDATO", tx, fy + 28);
    g.fillStyle = "#ffffff"; g.font = `800 ${grande ? 58 : 50}px ${DISP}`;
    let y = quebra(p.n, tx, fy + 88, tmax, grande ? 62 : 54, 3);
    g.fillStyle = C.ink2; g.font = `500 30px ${BODY}`; y = quebra(`${p.g} · ${partidoUF(p)}`, tx, y + 2, tmax, 38, p.k === "e" || p.k === "j" || p.k === "p" ? 3 : 2);
    // custo dele
    y = Math.max(y + 30, fy + fh + 62);
    g.fillStyle = C.ink2; g.font = `600 28px ${BODY}`; g.fillText(`${p.k === "p" ? "QUANTO RECEBE POR MÊS" : "CUSTO DELE POR MÊS"} · ${nomePeriodo(k, true).toUpperCase()}`, M, y);
    comMes(reais(r.tm), M - 6, y + 118, `500 112px ${MONO}`, 36, "#ffffff");
    y += 140;
    if (pos) {
      const selo = p.k === "p" ? (pos.pos === 1 ? `Quem mais recebe na Prefeitura` : pos.pct >= 50 ? `Recebe mais que ${pos.pct}% da Prefeitura` : `Recebe menos que ${100 - pos.pct}% da Prefeitura`)
        : pos.pos === 1 ? `O maior custo entre os ${plural(p.k)}` : pos.pos === pos.n ? `O menor custo entre os ${plural(p.k)}`
        : pos.pct >= 50 ? `Custa mais que ${pos.pct}% dos ${plural(p.k)}` : `Custa menos que ${100 - pos.pct}% dos ${plural(p.k)}`;
      g.font = `700 32px ${BODY}`; const larg = g.measureText(selo).width;
      g.fillStyle = C.hi; caixa(M, y, larg + 48, 58, 29); g.fill();
      g.fillStyle = "#2a0714"; g.fillText(selo, M + 24, y + 40);
      y += 78;
    } else y += 4;
    // as duas partes do custo dele
    const tw = (W - 2 * M - 24) / 2, th = 160;
    const bloco = (x, cor, rotulo, valor, detalhe) => {
      g.fillStyle = C.cartao; caixa(x, y, tw, th, 20); g.fill();
      bolinha(cor, x + 34, y + 38);
      g.fillStyle = C.ink2; g.font = `700 24px ${BODY}`; g.fillText(rotulo, x + 56, y + 47);
      if (valor === null) { g.fillStyle = "#ffffff"; g.font = `600 36px ${BODY}`; g.fillText("não publicados", x + 24, y + 104); }
      else comMes(valor, x + 24, y + 106, `500 54px ${MONO}`, 25, "#ffffff");
      g.fillStyle = C.ink2; g.font = `400 24px ${BODY}`; g.fillText(detalhe, x + 24, y + 142);
    };
    bloco(M, C.ganha, "VAI PARA O BOLSO", reais(r.gm), `${sm(emSalariosMinimos(p, k, "g"))} salários mínimos`);
    bloco(M + tw + 24, C.custa, gastosNome(p).toUpperCase(), p.k === "p" ? null : reais(r.cm), p.k === "p" ? "carro oficial, viagens, equipe" : gastosDetalhe(p));
    y += th + 18;
    // onde mais gasta: os 3 maiores tipos de gasto, por mês
    const maiores = maioresGastos(p, k, 3);
    if (maiores.length) {
      g.fillStyle = C.ink2; g.font = `700 22px ${BODY}`; g.fillText(`${gastosNome(p).toUpperCase()}: ONDE MAIS GASTA`, M, y + 26);
      y += 26;
      for (const [t, v] of maiores) {
        y += 40;
        bolinha(C.custa, M + 8, y - 8);
        g.fillStyle = "#e4e1f3"; g.font = `500 26px ${BODY}`;
        let nome = t.replace(/\*$/, "");
        while (g.measureText(nome).width > W - 2 * M - 260 && nome.length > 10) nome = nome.slice(0, -2);
        g.fillText(nome === t.replace(/\*$/, "") ? nome : `${nome.trim()}…`, M + 28, y);
        g.font = `500 26px ${BODY}`; const wMes = g.measureText("/mês").width + 6;
        g.font = `500 30px ${MONO}`; const wV = g.measureText(reais(v)).width;
        comMes(reais(v), W - M - wMes - wV, y, `500 30px ${MONO}`, 22, "#ffffff");
      }
      y += 26;
    }
    // equipe: à parte (borda tracejada, fora da soma)
    if (r.em) {
      const eh = 110;
      g.strokeStyle = C.linha; g.lineWidth = 2; g.setLineDash([10, 8]); caixa(M + 1, y + 1, W - 2 * M - 2, eh - 2, 20); g.stroke(); g.setLineDash([]);
      bolinha(C.equipe, M + 34, y + 40);
      g.fillStyle = C.ink2; g.font = `700 24px ${BODY}`; g.fillText("À PARTE: EQUIPE DO GABINETE", M + 56, y + 49);
      g.fillStyle = C.ink2; g.font = `400 24px ${BODY}`;
      g.fillText(`${r.pessoas ? pessoasTxt(r.pessoas) : "Assessores"}${r.porPessoa ? ` · ${reais(r.porPessoa)} por pessoa` : ""}${casaBase(p) === "s" ? " (estimativa)" : ""}`, M + 24, y + 88);
      g.font = `500 24px ${BODY}`; const wMes = g.measureText("/mês").width + 6;
      g.font = `500 48px ${MONO}`; const wValor = g.measureText(reais(r.em)).width;
      comMes(reais(r.em), W - M - 24 - wMes - wValor, y + 66, `500 48px ${MONO}`, 24, "#ffffff");
      y += eh;
    } else if (p.k === "v" && p.eq) {
      const eh = 92;
      g.strokeStyle = C.linha; g.lineWidth = 2; g.setLineDash([10, 8]); caixa(M + 1, y + 1, W - 2 * M - 2, eh - 2, 20); g.stroke(); g.setLineDash([]);
      bolinha(C.equipe, M + 34, y + 46);
      g.fillStyle = C.ink2; g.font = `700 24px ${BODY}`; g.fillText("À PARTE: EQUIPE DO GABINETE", M + 56, y + 55);
      g.fillStyle = "#ffffff"; g.font = `500 30px ${MONO}`; direita(pessoasTxt(p.eq.n), W - M - 24, y + 57);
      y += eh;
    }
    const aviso = p.k === "v" ? avisoVereador(p)
      : p.k === "p" ? "A Prefeitura publica só o que cada um recebe, não os gastos por pessoa."
      : p.k === "j" ? "Soma dos dois cargos, sem contar o salário duas vezes."
      : p.k === "d" ? "Para deputados, ainda faltam o 13º, a ajuda de custo e as diárias."
      : p.tp === "pr" ? "O avião presidencial e a estrutura da Presidência não entram na conta."
      : p.k === "e" ? `${r.cats.jetons ? `O bolso inclui ${reais(porMes(r, "jetons"))} por mês de jetons. ` : ""}Voos da FAB não têm custo publicado.` : null;
    if (aviso) { g.fillStyle = C.ink2; g.font = `400 22px ${BODY}`; g.fillText(aviso, M, Math.min(y + 34, H - 196)); }
    if (p.fc && foto) {
      g.fillStyle = "rgba(196,191,224,.7)"; g.font = `400 16px ${BODY}`;
      direita(p.fc.l ? `Foto: ${(p.fc.a || "Wikimedia Commons").replace(/ from .*$/, "").slice(0, 40)} (${p.fc.l}), Wikimedia Commons` : `Foto: ${p.fc.a}`, W - M, H - 190);
    }
    // rodapé: onde ver mais e de onde vêm os dados
    const ry = H - 176;
    g.fillStyle = C.marca; g.fillRect(0, ry, W, H - ry);
    g.fillStyle = "rgba(255,255,255,.85)"; g.font = `700 24px ${BODY}`; g.fillText(p.k === "v" ? "VEJA TAMBÉM OS OUTROS VEREADORES, DEPUTADOS E SENADORES EM" : p.k === "p" ? "VEJA TAMBÉM OS VEREADORES, OS DEPUTADOS E OS SENADORES EM" : "VEJA TAMBÉM O SEU DEPUTADO, OS SENADORES E OS MINISTROS EM", M, ry + 46);
    g.fillStyle = "#ffc2d6"; g.font = `800 58px ${DISP}`; g.fillText(dominio(), M, ry + 106);
    g.fillStyle = "rgba(255,255,255,.85)"; g.font = `500 26px ${BODY}`; g.fillText(`Tudo com dados abertos oficiais ${fonteDados(p)}`, M, ry + 150);
    return await new Promise((ok) => cv.toBlob(ok, "image/png"));
  }
  const arquivoNome = (p) => `contas-do-poder-${semAcento(p.n).replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")}.png`;
  // guarda a última imagem gerada (troca quando muda o parlamentar ou o período)
  let imagemAtual = { chave: null, blob: null, url: null };
  async function obterImagem(p, k) {
    const chave = `${p.id}~${k}`;
    if (imagemAtual.chave === chave && imagemAtual.blob) return imagemAtual;
    const blob = await imagemCompartilhar(p, k);
    if (imagemAtual.url) URL.revokeObjectURL(imagemAtual.url);
    imagemAtual = { chave, blob, url: blob ? URL.createObjectURL(blob) : null };
    return imagemAtual;
  }
  const podeCopiarImagem = () => !!(navigator.clipboard && navigator.clipboard.write && window.ClipboardItem);
  const podeEnviarArquivo = () => { try { return !!(navigator.canShare && navigator.canShare({ files: [new File([""], "x.png", { type: "image/png" })] })); } catch (e) { return false; } };
  const noCelular = () => matchMedia("(pointer: coarse)").matches;
  async function copiarTexto(conteudo, retorno, msg) {
    try { await navigator.clipboard.writeText(conteudo); retorno.textContent = msg; }
    catch (e) {
      retorno.textContent = "";
      const campo = h("textarea", { readonly: true, rows: 4, "aria-label": "Texto para copiar" }, conteudo);
      retorno.append("Selecione e copie:", campo); campo.select();
    }
  }
  // botões no fim do contracheque: texto no WhatsApp ou ir para a imagem
  function botoesCompartilhar(p, k) {
    const medir = (metodo) => evento("compartilhar", { metodo, conteudo: "parlamentar", parlamentar: p.n, casa: casaTxt(p) });
    return h("div", { class: "compartilhar" },
      h("div", { class: "acoes" },
        h("a", { class: "botao botao--zap", href: `https://wa.me/?text=${encodeURIComponent(textoCompartilhar(p, k))}`, target: "_blank", rel: "noopener", onclick: () => medir("whatsapp") }, "Mandar no WhatsApp"),
        h("button", { type: "button", class: "botao botao--leve", onclick: () => { evento("abrir_compartilhar", { parlamentar: p.n, casa: casaTxt(p) }); irPara("resumo"); } }, "Compartilhar como imagem")));
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
    const opcoes = [[j.id, "Tudo junto", "os dois cargos, sem contar nada duas vezes"], [exe.id, exe.g, sub(exe)], [par.id, par.g, sub(par)]];
    const alvo = (id) => { const q = S.porId.get(id); return `#${id}${q && k !== periodoPadrao(q) && periodos(q).includes(k) ? "~" + k : ""}`; };
    return h("nav", { class: "cargos", "aria-label": "Cargos desta pessoa" },
      h("p", { class: "rotulo" }, `${j.n} tem dois cargos. Veja juntos ou separados (custo dele ${nomePeriodo(k, false)}):`),
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
    const cols = [[exe, j.cg[0].g], [par, j.cg[1].g], [j, "Tudo junto"]].map(([q, nome]) => ({ nome, r: q ? resumo(q, k) : null }));
    if (!cols[2].r) return null;
    const cats = [...ORDEM_GANHA, ...ORDEM_CUSTA].filter((c) => cols.some((x) => x.r && x.r.cats[c]));
    const total = (x, f) => (x.r && Math.abs(f(x.r)) >= 0.5 ? reais(f(x.r)) : "R$ 0");
    const linhas = [
      ...cats.map((c) => [nomeCat(c).replace(/ \(.*\)$/, ""), (r) => r.cats[c] || 0]),
      ["Custo dele no período", (r) => r.g + r.c, "total"],
      ["Meses no cargo", null, "meses"],
      ["Custo dele por mês (média)", (r) => r.tm, "media"],
      ...(cols.some((x) => x.r && x.r.e) ? [["À parte: equipe do gabinete", (r) => r.e]] : []),
    ];
    const n = mesesPorCargo(j, k);
    const cargoPar = j.cg[1].g.toLowerCase(), casaPar = S.porId.get(j.cg[1].id) && S.porId.get(j.cg[1].id).k === "s" ? "o Senado" : "a Câmara";
    const quando = maiuscula(nomePeriodo(k, false));
    const expl = [];
    if (n.par === 0) expl.push(`${quando}, ${j.n} passou os ${n.e} meses no ministério, licenciado do mandato de ${cargoPar}. O salário desses meses foi pago por ${casaPar}, mas é o salário de ministro: aparece só na coluna do ministério. Como ${cargoPar}, sem exercer o mandato, não recebeu nada a mais.`);
    else if (n.e === 0) expl.push(`${quando}, ${j.n} passou os ${n.par} meses exercendo o mandato de ${cargoPar}, fora do ministério.`);
    else expl.push(`${quando}, foram ${n.e} ${n.e === 1 ? "mês" : "meses"} no ministério e ${n.par} ${n.par === 1 ? "mês" : "meses"} exercendo o mandato de ${cargoPar}. Cada coluna tem só os meses daquele cargo: o salário entra uma vez por mês, no cargo em que ele estava; cota e equipe do gabinete, nos meses do mandato; jetons e viagens, nos meses do ministério.`);
    if (n.par === 0 && cols[1].r && cols[1].r.e) expl.push(`${casaPar === "a Câmara" ? "A Câmara" : "O Senado"} ainda registrou ${reais(cols[1].r.e)} com a equipe do gabinete dele no período, mesmo licenciado; como toda equipe, fica à parte.`);
    expl.push("Somando as duas primeiras colunas, dá o “tudo junto”. A média por mês de cada coluna usa só os meses daquele cargo.");
    const celula = (x, f, tipo) => {
      const meses = x === cols[0] ? n.e : x === cols[1] ? n.par : n.e + n.par;
      if (tipo === "meses") return String(meses);
      if (tipo === "media") return x.r && meses ? reais(f(x.r)) : "—";
      return total(x, f);
    };
    return h("details", { class: "conta-cargos", open: aberto || null, ontoggle: (e) => { if (e.target.open) evento("abrir_detalhe", { categoria: "dois_cargos", casa: "dois cargos" }); } },
      h("summary", null, "Como a conta fecha: cada cargo e a soma"),
      h("div", { class: "rolagem" }, h("table", { class: "comp-tabela conta-cargos__tabela" },
        h("thead", null, h("tr", null, h("th", null, `Total ${nomePeriodo(k, false).replace(/^em /, "em ")}`), cols.map((x) => h("th", null, x.nome)))),
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
      h("p", { class: "rotulo" }, `${p.n} teve dois cargos desde 2025, em momentos diferentes (custo dele ${nomePeriodo(k, false)}):`),
      h("div", { class: "cargos__lista" }, [ver, pre].map((x) => h("a", {
        class: "cargo-opcao", href: `#${x.id}`, "aria-current": x.id === p.id ? "page" : null,
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
  function secContracheque(p, k) {
    const r = resumo(p, k), C = p.ced ? { cat: {}, tm: null } : colegas(grupo(p), k), pos = posicao(p, k);
    const jj = (p.k === "d" || p.k === "s") && p.j ? S.porId.get(p.j) : null; // deputado/senador que também foi ministro
    const trocar = (novo) => { evento("trocar_periodo", { periodo: novo === "leg" ? "mandato" : novo, casa: casaTxt(p) }); S.periodo = novo; S.rank.periodo = novo; history.replaceState(null, "", `#${p.id}${novo !== periodoPadrao(p) ? "~" + novo : ""}`); render(false); };
    const card = h("article", { class: "cartao conta", id: "contracheque" });
    add(card, h("div", { class: "conta__topo" },
      avatar(p, "g"),
      h("div", null,
        h("p", { class: "rotulo" }, { e: "Contracheque do cargo", j: "Contracheque dos dois cargos, somados", p: "Contracheque do cargo" }[p.k] || "Contracheque do mandato"),
        h("h2", null, p.n),
        h("div", { class: "conta__sub" }, h("span", null, `${p.g} · ${partidoUF(p)}`), etiquetaCargo(p))),
      h("a", { href: p.o, target: "_blank", rel: "noopener", class: "pequeno" }, "Página oficial ↗")));
    const lado = h("div", { class: "conta__lado" },
      h("p", { class: "passo" }, "1. Escolha o período"),
      pilulas(periodos(p).map((x) => [x, nomePeriodo(x, true)]), k, trocar, "Período"));
    if (r) {
      // deputado/senador que também foi ministro: conta só os meses exercendo o mandato
      add(lado, h("div", { class: "estatisticas" },
        jj ? estatistica("Meses exercendo o mandato", String(mesesPorCargo(jj, k).par), nomePeriodo(k, false))
          : estatistica({ e: "Meses no cargo", j: "Meses nos dois cargos", p: "Meses no cargo" }[p.k] || "Meses de mandato", String(r.m), nomePeriodo(k, false)),
        estatistica("Vai para o bolso", sm(emSalariosMinimos(p, k, "g")), "salários mínimos por mês")));
      if (p.im) {
        const anos = k === "leg" ? Object.keys(p.im) : [k];
        const frases = anos.filter((a) => p.im[a]).map((a) => p.k === "d" ? `${a}: apartamento funcional por ${p.im[a]} dias` : `${a}: ${p.im[a] === "Utilizou" ? "usou" : "não usou"} imóvel funcional`);
        if (frases.length) add(lado, h("div", { class: "estatistica" }, h("span", { class: "rotulo" }, "Moradia em Brasília"), frases.map((f) => h("span", { class: "pequeno" }, f))));
      }
      if (r.mg < r.m && p.k !== "e" && p.k !== "j" && p.k !== "p" && !p.j) add(lado, h("p", { class: "nota" }, `Em ${r.m - r.mg} ${r.m - r.mg === 1 ? "mês" : "meses"} não houve salário (licença, por exemplo), mas o gabinete continuou funcionando. Cada média usa os seus próprios meses.`));
      if (p.k === "j") add(lado, h("p", { class: "aviso" }, "Somamos os dois cargos sem contar nada duas vezes: o salário entra uma vez (nos meses como ministro, quem paga é o Congresso); a cota e a equipe do gabinete só nos meses exercendo o mandato; viagens e jetons só nos meses como ministro."));
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
          igual || c.salario_nota ? h("p", { class: "aviso" }, `${igual}${c.salario_nota || ""}`) : null,
          (c.notas || []).map((n) => h("p", { class: "nota" }, n)),
          h("p", { class: "nota" }, `Dados da ${c.casa} até ${fmtMes(c.ultimo_mes)}.`));
      }
      if (p.fc) add(lado, h("p", { class: "nota credito" }, "Foto: ", h("a", { href: p.fc.u, target: "_blank", rel: "noopener" }, p.fc.l ? `${(p.fc.a || "autor no Wikimedia Commons").replace(/ from .*$/, "")} (${p.fc.l})` : p.fc.a), p.fc.l ? ", via Wikimedia Commons." : "."));
      if (p.q) add(lado, h("p", { class: "nota" }, p.k === "p"
        ? `No mês da saída, recebeu mais ${reais(p.q[1])} de acertos (férias, 13º proporcional e outros). Esse valor não entra nas médias.`
        : `Depois de deixar o cargo, recebeu mais ${reais(p.q[1])} em ${p.q[0]} ${p.q[0] === 1 ? "mês" : "meses"} (acertos da saída e quarentena). Esse valor não entra nas médias.`));
      if (p.k === "p" && p.rel && !S.porId.get(p.rel)) add(lado, h("p", { class: "nota" }, `${p.n} é vereador ${deCid(p.cid)} e está licenciado da Câmara para ficar na Prefeitura: um suplente ocupa a cadeira dele.`));
      if (p.rel && !p.j && S.porId.get(p.rel) && p.k !== "p" && p.k !== "v") add(lado, h("p", { class: "nota" },
        p.k === "e" ? `Também é ${nomeRel(p.rel)}. Nos meses como ministro, o salário pode ter sido pago pelo Congresso: aparece aqui. ` : "Também foi do governo federal. ",
        h("a", { href: `#${p.rel}` }, p.k === "e" ? "Ver o contracheque no Congresso" : `Ver o contracheque como ${nomeRel(p.rel)}`)));
    }
    const cargos = barraCargos(p, k) || barraRel(p, k);
    if (cargos) card.append(cargos);
    const valores = h("div", { class: "conta__valores" }, h("p", { class: "passo", style: "padding:20px 22px 0" }, "2. Quanto isso dá por mês"));
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
          h("span", { class: "item__detalhe" }, "Nos meses no ministério, o salário está na página de ministro. ", h("a", { href: `#${jj.cg[0].id}` }, "Ver"))) : null,
        titulo(`${gastosNome(p)}, pagos com dinheiro público`, "custa"),
        p.k === "p" ? h("div", { class: "item" }, h("span", { class: "item__nome" }, "Carro oficial, viagens e equipe"), h("span", { class: "item__valor" }, "não publicados"),
          h("span", { class: "item__detalhe" }, "A Prefeitura não informa esses gastos por pessoa.")) : linhas(ORDEM_CUSTA),
        rateados.length ? h("p", { class: "nota", style: "padding:10px 22px 0" },
          `≈ ${rateados.map((c) => meta().rateio[c]).join(" ")} Dividimos o total do ano pelos meses com salário: é uma aproximação.`) : null,
        h("div", { class: "total" },
          h("strong", null, "Custo dele por mês"),
          h("span", { class: "total__valor" }, reais(r.tm)),
          h("span", { class: "item__detalhe" }, p.k === "p" ? `tudo para o bolso · ${sm(emSalariosMinimos(p, k, "t"))} salários mínimos` : `${reais(r.gm)} para o bolso + ${reais(r.cm)} em ${gastosNome(p).toLowerCase()} · ${sm(emSalariosMinimos(p, k, "t"))} salários mínimos`),
          seloComp(r.tm, C.tm, `vs. ${txtMed}`)),
        pos ? h("p", { class: "destaque" }, `${fraseposicao(p, pos)} ${nomePeriodo(k, false)} (${pos.pos}º de ${pos.n}).`) : null,
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
          h("button", { type: "button", class: "link-botao pequeno", style: "margin:6px 22px 0", onclick: () => irPara("equipe") }, "Ver os cargos da equipe")) : null,
        botoesCompartilhar(p, k));
    }
    add(card, h("div", { class: "conta__corpo" }, lado, valores));
    return card;
  }
  function pontosDoPeriodo(p, k) {
    const ano = k === "leg" ? null : Number(k);
    return p.t.filter((t) => ano === null || Math.floor(t[0] / 100) === ano).map((t) => ({ aaaamm: t[0], g: t[1], c: t[2], e: t[3], pes: t[4], ra: t[5] || 0 }));
  }
  const nomeMes = (q) => `${MESES[(q.aaaamm % 100) - 1]}/${Math.floor(q.aaaamm / 100)}`;
  function tabela(cabecalho, linhas) {
    return h("details", { class: "tabela" }, h("summary", null, "Ver os valores em tabela"),
      h("div", { class: "rolagem" }, h("table", null,
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
      h("div", { class: "cartao__cabeca" }, h("div", null, h("h3", null, "Custo dele mês a mês"),
        h("p", { class: "pequeno discreto" }, `O que foi para o bolso e os ${gastosNome(p).toLowerCase()} em cada mês, ${nomePeriodo(k, false).replace(/^em /, "")}. A equipe do gabinete aparece à parte.`))),
      h("div", { class: "legenda" }, h("span", null, h("span", { class: "chave chave--ganha" }), "Vai para o bolso"), h("span", null, h("span", { class: "chave chave--custa" }), gastosNome(p)),
        p.k === "j" ? p.cg.map((c) => h("span", null, h("span", { class: `chave chave--faixa faixa-cargo--${S.porId.get(c.id) ? S.porId.get(c.id).k : "e"}` }), `Mês como ${c.g.split(/[ -]/)[0].toLowerCase()}`)) : null),
      caixa,
      tabela(["Mês", "Bolso", gastosNome(p), "Custo dele"], pontos.map((q) => [nomeMes(q), reais(q.g), reais(q.c), `${q.ra ? "≈ " : ""}${reais(q.g + q.c)}`])),
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
      (q) => [linhaDica("ganha", reais(q.g), "para o bolso"), linhaDica("custa", reais(q.c), `em ${gastosNome(p).toLowerCase()}`), h("div", null, "Custo dele ", h("strong", null, reais(q.g + q.c))),
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
      h("div", { class: "cartao__cabeca" }, h("div", null, h("h3", null, "Equipe do gabinete"),
        h("p", { class: "pequeno discreto" }, `Dinheiro público que paga as pessoas que trabalham para ${p.n}. Não vai para o bolso dele.`))),
      h("div", { class: "estatisticas" },
        estatistica("Custo da equipe por mês", reais(r.em), C.em ? `Mediana: ${reais(C.em)}` : null),
        estatistica("Pessoas", num(r.pessoas, r.pessoas < 10 ? 1 : 0), C.pessoas ? `Mediana: ${num(C.pessoas, 0)}` : null),
        estatistica("Média por pessoa", r.porPessoa ? reais(r.porPessoa) : "—", C.porPessoa ? `Mediana: ${reais(C.porPessoa)}` : null)),
      caixa,
      tabela(["Mês", "Custo da equipe", "Pessoas", "Por pessoa"], pontos.map((q) => [nomeMes(q), reais(q.e), q.pes ? String(q.pes) : "—", q.pes ? reais(q.e / q.pes) : "—"])),
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
      h("div", { class: "cartao__cabeca" }, h("div", null, h("h3", null, "Equipe do gabinete"),
        h("p", { class: "pequeno discreto" }, `Quem trabalha para ${p.n}, em ${fmtMes(mesEquipe(c))}. É pago com dinheiro público, mas não vai para o bolso dele.`))),
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
    const linhas = d.map(([i, v]) => [meta().tipos[i], v]);
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
      h("div", { class: "cartao__cabeca" }, h("div", null, h("h3", null, titulo), h("p", { class: "pequeno discreto" }, sub))),
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
      h("div", { class: "cartao__cabeca" }, h("div", null, h("h3", null, "Comparar com outro parlamentar"),
        h("p", { class: "pequeno discreto" }, `${Object.keys(CAM.cidades).length ? "Deputado, senador, ministro ou vereador das capitais com dados" : "Da Câmara, do Senado ou do governo federal"}. No mesmo período, quanto o outro custa a mais ou a menos por mês.`))));
    const input = h("input", { type: "search", id: "busca-comparar", placeholder: "Quem? Ex.: Haddad, PT ou Bahia", autocomplete: "off" });
    const sug = h("div", { class: "sugestoes", hidden: true });
    add(card, h("div", { class: "busca-caixa", style: "max-width:520px" }, h("label", { class: "visualmente-oculto", for: "busca-comparar" }, "Comparar com"), input, sug));
    ligarBusca(input, sug, (q) => { evento("comparar", { parlamentar: p.n, outro: q.n }); S.outro = q.id; render(false); irPara("comparar"); }, (q) => q.id !== p.id);
    const o = S.outro && S.porId.get(S.outro);
    if (o) {
      const r1 = resumo(p, k), r2 = resumo(o, k);
      if (!r2) add(card, h("p", { class: "discreto" }, `${o.n} não tem mandato ${nomePeriodo(k, false)}. Escolha outro período acima.`));
      else if (r1) {
        const linhas = [
          ["Vai para o bolso", (r) => r.gm, reais], ["Gastos do mandato ou do cargo", (r) => r.cm, reais], ["Jetons", (r) => porMes(r, "jetons"), reais], ["Custo dele por mês", (r) => r.tm, reais],
          ["Cota parlamentar", (r) => porMes(r, "cota_parlamentar"), reais], ["Verba do gabinete (vereador)", (r) => porMes(r, "verba_gabinete"), reais],
          ["Equipe do gabinete", (r) => r.em, reais], ["Pessoas na equipe", (r) => r.pessoas, (v) => num(v, 0)], ["Por pessoa da equipe", (r) => r.porPessoa, reais]];
        add(card, h("div", { class: "rolagem" }, h("table", { class: "comp-tabela" },
          h("thead", null, h("tr", null, h("th", null, nomePeriodo(k, true)), h("th", null, p.n), h("th", null, o.n), h("th", null, "Diferença"))),
          h("tbody", null, linhas.filter(([, f]) => f(r1) || f(r2)).map(([nome, f, fmt]) => {
            const a = f(r1), b = f(r2), dif = b - a, pct = a ? Math.round((dif / a) * 100) : null;
            const igual = fmt === reais ? Math.abs(dif) < 1 : Math.abs(dif) < 0.5;
            return h("tr", null, h("td", null, nome), h("td", { class: "num" }, fmt(a)), h("td", { class: "num" }, fmt(b)),
              h("td", { class: igual ? "" : dif > 0 ? "dif-mais" : "dif-menos" }, igual ? "igual" : `${dif > 0 ? "+" : "−"}${fmt(Math.abs(dif))}${pct !== null ? ` (${pct > 0 ? "+" : ""}${pct}%)` : ""}`));
          })))),
          h("div", { class: "acoes" },
            h("a", { href: `#${o.id}`, class: "pequeno", onclick: () => { S.origem = "comparar"; } }, `Ver o contracheque de ${o.n}`),
            h("button", { type: "button", class: "link-botao pequeno", onclick: () => { S.outro = null; render(false); irPara("comparar"); } }, "Tirar da comparação")),
          (p.k === "s" || o.k === "s") ? h("p", { class: "nota" }, "A equipe do Senado é uma estimativa. Para deputados, ainda faltam o 13º, a ajuda de custo e as diárias.") : null);
      }
    }
    return card;
  }
  // Resumo para compartilhar: a própria imagem, com copiar / enviar / baixar, e o texto à parte
  function secResumo(p, k) {
    const r = resumo(p, k);
    if (!r) return null;
    const medir = (metodo) => evento("compartilhar", { metodo, conteudo: "parlamentar", parlamentar: p.n, casa: casaTxt(p) });
    const texto = textoCompartilhar(p, k), link = linkDe(p, k);
    let atual = null;
    const retornoImg = h("p", { class: "compartilhar-img__retorno", role: "status" });
    const retornoTxt = h("p", { class: "compartilhar-img__retorno", role: "status" });
    const img = h("img", { class: "compartilhar-img__previa", width: 1080, height: 1350, alt: `Resumo de ${p.n}: custo dele de ${reais(r.tm)} por mês ${nomePeriodo(k, false)}` });
    const quadro = h("div", { class: "compartilhar-img__quadro carregando" }, img);
    const botao = (rotulo, cls, fn) => h("button", { type: "button", class: `botao ${cls}`, disabled: true, onclick: fn }, rotulo);
    const botoes = [];
    if (podeCopiarImagem()) botoes.push(botao("Copiar imagem", "", () => {
      // sem await antes do write: o Safari só deixa copiar dentro do clique
      navigator.clipboard.write([new ClipboardItem({ "image/png": atual.blob })]).then(() => {
        medir("copiar_imagem");
        retornoImg.textContent = noCelular() ? "Imagem copiada. Abra a conversa e cole." : "Imagem copiada. Abra a conversa e cole (Ctrl+V ou ⌘+V).";
      }, () => {
        retornoImg.textContent = noCelular() ? "Não deu para copiar. Toque e segure a imagem para copiar ou salvar." : "O navegador não deixou copiar a imagem. Use “Baixar imagem”.";
      });
    }));
    if (podeEnviarArquivo()) botoes.push(botao("Enviar imagem…", botoes.length ? "botao--leve" : "", async () => {
      const arquivo = new File([atual.blob], arquivoNome(p), { type: "image/png" });
      try { await navigator.share({ files: [arquivo], text: link ? `Mais detalhes: ${link}` : undefined }); medir("enviar_imagem"); }
      catch (e) { if (e.name !== "AbortError") retornoImg.textContent = "Não deu para abrir o menu de compartilhar. Copie ou baixe a imagem."; }
    }));
    botoes.push(botao("Baixar imagem", botoes.length ? "botao--leve" : "", () => {
      const a = h("a", { href: atual.url, download: arquivoNome(p) });
      document.body.append(a); a.click(); a.remove();
      medir("baixar_imagem");
      retornoImg.textContent = "Imagem salva. Agora é só anexar na conversa.";
    }));
    obterImagem(p, k).then((a) => {
      if (!a.blob) { retornoImg.textContent = "Não deu para gerar a imagem neste navegador."; return; }
      atual = a; img.src = a.url; quadro.classList.remove("carregando");
      botoes.forEach((b) => { b.disabled = false; });
    }, () => { retornoImg.textContent = "Não deu para gerar a imagem neste navegador."; });
    return h("section", { class: "bloco", id: "resumo" },
      h("p", { class: "rotulo" }, "Resumo para compartilhar"),
      h("h2", null, "Mande para quem você quiser"),
      h("div", { class: "compartilhar-img" },
        quadro,
        h("div", { class: "compartilhar-img__lado" },
          h("div", { class: "cartao compartilhar-img__opcao" },
            h("h3", null, "Imagem"),
            h("p", { class: "pequeno discreto" },
              `${noCelular() ? "Copie e cole numa conversa do WhatsApp, do Telegram ou onde quiser." : "Copie e cole numa conversa do WhatsApp Web, do Telegram ou num e-mail."}${podeEnviarArquivo() ? " Ou toque em “Enviar imagem” para escolher o aplicativo." : " Ou baixe para anexar."}`),
            h("div", { class: "acoes" }, botoes), retornoImg),
          h("div", { class: "cartao compartilhar-img__opcao" },
            h("h3", null, "Texto"),
            h("p", { class: "pequeno discreto" }, "O mesmo resumo em texto, com o link para ver mais detalhes."),
            h("div", { class: "acoes" },
              h("a", { class: "botao botao--zap", href: `https://wa.me/?text=${encodeURIComponent(texto)}`, target: "_blank", rel: "noopener", onclick: () => medir("whatsapp") }, "Mandar no WhatsApp"),
              h("button", { type: "button", class: "botao botao--leve", onclick: () => { medir("copiar_texto"); copiarTexto(texto, retornoTxt, "Texto copiado. É só colar."); } }, "Copiar texto"),
              link ? h("button", { type: "button", class: "botao botao--leve", onclick: () => { medir("copiar_link"); copiarTexto(link, retornoTxt, "Link copiado."); } }, "Copiar link") : null),
            retornoTxt),
          h("p", { class: "nota" }, `A imagem e o texto mostram o período escolhido no contracheque (${nomePeriodo(k, true)}). Dados abertos oficiais ${fonteDados(p)}.`))));
  }

  // ================================================================== câmaras municipais (vereadores)
  // Carregado à parte (dados/municipios.json), para não pesar a primeira visita.
  const CID = { m: null, meta: null, porId: new Map(), ver: {}, carregando: null };
  function carregarCidades() {
    if (!CID.carregando) {
      CID.carregando = fetch("dados/municipios.json").then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); }).then((d) => {
        CID.meta = d.meta;
        CID.m = d.m.map(([cod, n, uf, pop, cap, nv, custo, ano]) => ({ cod, id: `cid-${cod}`, n, uf, pop, cap, nv, custo, ano }));
        CID.m.forEach((c) => CID.porId.set(c.id, c));
        // mediana do custo por habitante em cada faixa de população; valor muito abaixo dela é suspeito
        // (parte do gasto da Câmara deve ter sido informada em outra função nas contas da prefeitura)
        CID.med = CID.meta.faixas_teto.map((_, i) => mediana(CID.m.filter((c) => c.custo > 0 && c.pop > 0 && faixaDe(c.pop) === i).map(porHabMes)));
        CID.m.forEach((c) => { c.suspeito = c.custo > 0 && c.pop > 0 && porHabMes(c) < 0.3 * CID.med[faixaDe(c.pop)]; });
        return CID;
      });
    }
    return CID.carregando;
  }
  const carregarVereadores = (uf) => (CID.ver[uf] = CID.ver[uf] || fetch(`dados/vereadores/${uf}.json`).then((r) => r.json()));
  const reaisC = (v) => v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" }).replace(/ /g, " ");
  const temCusto = (c) => c.custo > 0 && c.pop > 0 && !c.suspeito;
  const porHabMes = (c) => c.custo / c.pop / 12;
  const faixaDe = (pop) => CID.meta.faixas_teto.findIndex(([lim]) => lim === null || pop <= lim);
  const tetoVereador = (pop) => CID.meta.faixas_teto[faixaDe(pop)][1] * CID.meta.teto_deputado_estadual;
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
  const irParaCidade = (c, origem) => { S.origem = origem; location.hash = c.id; };
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
      h("h3", null, `Mora em ${c.n}? Ajude a corrigir`),
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
    const link = endereco() ? `${endereco()}#${c.id}` : "";
    return [
      `*Câmara Municipal de ${c.n} (${c.uf})*`,
      temCusto(c) ? `Custa *${compacto(c.custo / 12)} por mês* (${reaisC(porHabMes(c))} por habitante, por mês), com ${c.nv} vereadores.` : `${c.nv} vereadores.`,
      `Um vereador daqui pode ganhar até ${reais(tetoVereador(c.pop))} por mês.`,
      "",
      "Dados abertos oficiais do Tesouro Nacional e do TSE.",
      `Veja a da sua cidade: ${link || "Contas do Poder"}`,
    ].join("\n");
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
    const chip = (q) => h("a", { class: "pessoa-chip", href: `#${q.id}`, onclick: () => { S.origem = "cidade"; } },
      avatar(q, "p"), q.n, h("small", null, `${q.pt || "sem partido"}${q.sup ? " · suplente" : ""}`));
    const partidos = {};
    agora.forEach((q) => { partidos[q.pt] = (partidos[q.pt] || 0) + 1; });
    const mulheres = agora.filter((q) => q.g === "Vereadora").length;
    return [
      h("div", { class: "estatisticas" },
        sub && !cam.subsidio_folha ? estatistica("Salário de cada vereador", reaisC(sub[1]), `por mês desde ${fmtMes(sub[0])}${noTeto ? ", o máximo que a Constituição permite" : ""}`)
          : C.n ? estatistica("Vai para o bolso de um vereador", reais(C.gm), "por mês em 2025, pela folha de pagamento da Câmara (mediana)") : null,
        C.n ? estatistica("Custo típico de um vereador", reais(C.tm), "por mês em 2025: salário + verba do gabinete (mediana)") : null,
        C.n && C.cm ? estatistica("Verba do gabinete usada", reais(C.cm), `por mês em 2025 (mediana)${(cam.verba_mes || {})["2025"] ? `, de até ${reais(cam.verba_mes["2025"])}` : ""}`) : null,
        C.n && C.em ? estatistica("Equipe de um gabinete", reais(C.em), `por mês em 2025 (mediana), à parte: vai para os assessores`) : null),
      (cam.notas || []).map((n) => h("p", { class: "nota" }, n)),
      h("h3", null, `Os ${agora.length} vereadores no cargo, um a um`),
      h("p", { class: "discreto pequeno" }, `${Object.entries(partidos).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([pt, n]) => `${pt} ${n}`).join(" · ")} — ${mulheres} ${mulheres === 1 ? "mulher" : "mulheres"} de ${agora.length}. Toque num nome para ver o salário, a verba do gabinete mês a mês${temEquipe ? " e a equipe" : ""}.`),
      h("div", { class: "lista-estado__grupo" }, agora.map(chip)),
      sairam.length ? h("details", { class: "problemas" }, h("summary", null, `Quem ocupou um gabinete e saiu (${sairam.length})`), h("div", { class: "lista-estado__grupo" }, sairam.map(chip))) : null,
    ];
  }
  function secCidade(c) {
    const tem = temCusto(c) || c.suspeito;
    const detalhe = vereadoresDaCidade(c);
    const prob = problemaCidade(c);
    if (prob) evento("ver_problema_cidade", { cidade: c.n, uf: c.uf, problema: prob.tipo });
    const faixa = faixaDe(c.pop);
    const mesmos = CID.m.filter((x) => temCusto(x) && faixaDe(x.pop) === faixa);
    const med = mediana(mesmos.map(porHabMes));
    const pct = temCusto(c) && mesmos.length > 1 ? Math.round((mesmos.filter((x) => porHabMes(x) < porHabMes(c)).length / (mesmos.length - 1)) * 100) : null;
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
    const texto = textoCidade(c);
    const retorno = h("p", { class: "compartilhar-img__retorno", role: "status" });
    return h("article", { class: "cartao conta", id: "cidade" },
      h("div", { class: "conta__topo" }, iconeCidade(avatarCidade("g")),
        h("div", null,
          h("p", { class: "rotulo" }, "Câmara Municipal"),
          h("h2", null, `${c.n} (${c.uf})`),
          h("div", { class: "conta__sub" }, h("span", null, `${num(c.pop, 0)} habitantes · ${c.nv} vereadores${c.cap ? " · capital" : ""}`))),
        null),
      h("div", { class: "cidade__corpo" },
        tem ? h("div", { class: "estatisticas" },
          estatistica("Custo da Câmara por mês", compacto(c.custo / 12), `${compacto(c.custo)} em ${c.ano}`),
          estatistica("Por habitante", reaisC(porHabMes(c)), `por mês (${reais(c.custo / c.pop)} por ano)`),
          estatistica("Dividido pelos vereadores", compacto(c.custo / 12 / Math.max(1, c.nv)), "por vereador, por mês")) :
          h("p", { class: "aviso aviso--forte" }, h("strong", null, "A Prefeitura não informou corretamente o gasto da Câmara. "), `Nas contas que ${c.n} enviou ao Tesouro Nacional, o gasto da Câmara Municipal não aparece (está vazio ou zerado, ou a declaração não foi entregue). Por isso não dá para mostrar quanto a Câmara custa.`),
        c.suspeito ? h("p", { class: "aviso aviso--forte" }, h("strong", null, "Este valor parece errado. "), `É muito menor que o das cidades do mesmo tamanho (mediana de ${reaisC(med)} por habitante, por mês). Provavelmente a Prefeitura informou parte do gasto da Câmara em outra função nas contas enviadas ao Tesouro Nacional. Por isso esta cidade fica fora das comparações.`) : null,
        prob && prob.tipo === "antigo" ? h("p", { class: "aviso" }, h("strong", null, `A Prefeitura ainda não entregou as contas de ${anoRecente()}. `), `Mostramos o gasto de ${c.ano}, o último informado ao Tesouro Nacional.`) : null,
        prob ? cobrarCidade(c, prob, med) : null,
        tem && pct !== null ? h("p", { class: "destaque" }, `Por habitante, a Câmara de ${c.n} custa mais que ${pct}% das ${mesmos.length} cidades do mesmo tamanho (${nomeFaixa(faixa)}). A mediana delas é ${reaisC(med)} por habitante, por mês.`) : null,
        tem && posUF >= 0 ? h("p", { class: "discreto" }, `${posUF + 1}ª mais cara por habitante entre as ${doEstado.length} cidades de ${ESTADOS[c.uf]} com dados.`) : null,
        tem && mesmos.length > 5 ? h("div", null, h("p", { class: "discreto pequeno", style: "margin:0 0 4px" }, `Cada ponto é uma cidade com ${nomeFaixa(faixa)}: custo da Câmara por habitante, por mês. Toque num ponto para ver qual é.`), caixa) : null,
        detalhe || [h("div", { class: "estatisticas" },
          estatistica("Salário máximo de um vereador aqui", `até ${reais(teto)}`, "por mês, pela Constituição")),
        h("p", { class: "nota" }, `A Constituição (art. 29) deixa uma cidade com ${nomeFaixa(faixa)} pagar ao vereador até ${num(CID.meta.faixas_teto[faixa][1] * 100, 0)}% do salário do deputado estadual, que é no máximo ${reais(CID.meta.teto_deputado_estadual)}. O salário de verdade é definido pela própria Câmara e ainda não tem uma fonte nacional: por enquanto mostramos o teto.`),
        h("h3", null, `Os ${c.nv} vereadores eleitos em 2024`), lista],
        h("div", { class: "acoes" },
          h("a", { class: "botao botao--zap", href: `https://wa.me/?text=${encodeURIComponent(texto)}`, target: "_blank", rel: "noopener", onclick: () => evento("compartilhar", { metodo: "whatsapp", conteudo: "cidade", cidade: c.n }) }, "Mandar no WhatsApp"),
          h("button", { type: "button", class: "botao botao--leve", onclick: () => { evento("compartilhar", { metodo: "copiar_texto", conteudo: "cidade" }); copiarTexto(texto, retorno, "Texto copiado. É só colar."); } }, "Copiar texto")),
        retorno,
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
    const chip = (q) => h("a", { class: "pessoa-chip", href: `#${q.id}`, onclick: () => { S.origem = "cidade"; } },
      avatar(q, "p"), q.n, h("small", null, pastaCurtaP(q)));
    const ultimoValor = (tp) => { const q = agora.find((x) => x.tp === tp && !x.ced); return q ? (q.t.find((t) => t[0] === pref.ultimo_mes) || [])[1] : null; };
    const tipico = (tp) => mediana(agora.filter((x) => x.tp === tp && !x.ced).map((x) => (x.t.find((t) => t[0] === pref.ultimo_mes) || [])[1]).filter(Boolean));
    const grupo = (titulo, tps) => { const g = agora.filter((q) => tps.includes(q.tp)); return g.length ? [h("p", { class: "rotulo", style: "margin:6px 0 0" }, `${titulo} (${g.length})`), h("div", { class: "lista-estado__grupo" }, g.map(chip))] : null; };
    return h("section", { class: "bloco", id: "prefeitura" },
      h("p", { class: "rotulo" }, "Prefeitura"),
      h("h2", null, `Quanto recebem o prefeito, os secretários${agora.some((q) => q.tp === "sb") ? " e os subprefeitos" : ""} ${deCid(c.cod)}`),
      h("p", { class: "discreto" }, `Pela folha de pagamento que a Prefeitura publica todo mês, com o nome de cada um. Valores brutos de ${fmtMes(pref.ultimo_mes)}.`),
      h("article", { class: "cartao" },
        h("div", { class: "estatisticas" },
          ultimoValor("pr") ? estatistica(agora.find((x) => x.tp === "pr").g.startsWith("Prefeita") ? "Prefeita" : "Prefeito", reais(ultimoValor("pr")), `em ${fmtMes(pref.ultimo_mes)}`) : null,
          tipico("se") ? estatistica("Secretário municipal", reais(tipico("se")), "típico (mediana)") : null,
          tipico("sb") ? estatistica("Subprefeito", reais(tipico("sb")), "típico (mediana)") : null),
        grupo("Prefeito e vice", ["pr", "vp"]), grupo("Secretários", ["se"]), grupo("Subprefeitos", ["sb"]),
        sairam.length ? h("details", { class: "problemas" }, h("summary", null, `Quem passou pela Prefeitura desde 2025 e saiu (${sairam.length})`), h("div", { class: "lista-estado__grupo" }, sairam.map(chip))) : null,
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
      h("div", { class: "lista-estado__grupo" }, cs.map((c) => h("a", { class: "pessoa-chip", href: `#cid-${c.cod}`, onclick: () => { S.origem = "destaque_capitais"; } },
        c.n, h("small", null, [c.uf, camaraDe(c.cod) ? `${S.D.p.filter((q) => q.k === "v" && q.x && q.cid === c.cod).length} vereadores` : null, prefeituraDe(c.cod) ? "Prefeitura" : null].filter(Boolean).join(" · "))))));
  }
  // Seção da página inicial (e embaixo da página de uma cidade): procurar a cidade e as mais caras do estado
  function secCamaras(atual) {
    const sec = h("section", { class: "bloco", id: "cidades" });
    const corpo = h("div", { style: "display:grid;gap:12px" }, h("p", { class: "discreto" }, "Carregando as câmaras…"));
    let uf = atual ? atual.uf : S.ufLista || "SP";
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
      const linha = (c, pos) => h("a", { class: `rank${atual && c.cod === atual.cod ? " rank--eu" : ""}`, href: `#${c.id}`, onclick: () => { S.origem = "ranking_cidades"; } },
        h("span", { class: "rank__pos" }, `${pos}º`),
        h("span", { class: "rank__nome" }, c.n, " ", h("small", null, `${num(c.pop, 0)} hab.`)),
        h("span", { class: "rank__valor" }, reaisC(porHabMes(c))),
        h("span", { class: "barra__trilho" }, h("span", { class: "barra__fill", style: `width:${Math.max(0.5, (porHabMes(c) / max) * 100)}%` })));
      const n = Math.min(10, Math.ceil(doEstado.length / 2));
      add(corpo,
        h("div", { class: "estatisticas" },
          estatistica("Todas as câmaras do Brasil", `${compacto(total / 12)} por mês`, `${num(todas.length, 0)} cidades com dados`),
          estatistica("Por habitante", reaisC(total / pop / 12), "por mês, em média no Brasil"),
          estatistica("Vereadores", num(CID.m.reduce((a, c) => a + c.nv, 0), 0), "eleitos em 2024")),
        h("div", { class: "filtros" }, h("div", { class: "campo" }, h("label", { for: "uf-cidades" }, "Estado"), seletorUF("uf-cidades", uf, (v) => { uf = v || "SP"; evento("ver_estado_cidades", { uf }); desenhar(); }, "Escolha o estado"))),
        doEstado.length ? h("div", { class: "duas-colunas" },
          h("article", { class: "cartao" }, h("h3", null, `Mais caras por habitante em ${ESTADOS[uf]}`), h("div", { class: "rank-lista" }, doEstado.slice(0, n).map((c, i) => linha(c, i + 1)))),
          h("article", { class: "cartao" }, h("h3", null, "Mais baratas por habitante"), h("div", { class: "rank-lista" }, doEstado.slice(-n).reverse().map((c, i) => linha(c, doEstado.length - i))))) : null,
        h("p", { class: "nota" }, "Custo da Câmara por habitante, por mês. Cidades pequenas costumam custar mais por habitante, porque toda câmara tem pelo menos 9 vereadores e uma estrutura mínima."),
        (() => {
          const comProblema = CID.m.filter((c) => c.uf === uf && problemaCidade(c)).sort((a, b) => a.n.localeCompare(b.n, "pt-BR"));
          const noBrasil = CID.m.filter((c) => problemaCidade(c)).length;
          if (!comProblema.length) return h("p", { class: "nota" }, `Todas as cidades de ${ESTADOS[uf]} informaram o gasto da Câmara. No Brasil, ${num(noBrasil, 0)} cidades têm dados faltando ou estranhos.`);
          return h("details", { class: "cartao problemas" },
            h("summary", null, h("strong", null, `${comProblema.length} ${comProblema.length === 1 ? "cidade" : "cidades"} de ${ESTADOS[uf]} com dados faltando ou estranhos`),
              h("span", { class: "pequeno discreto" }, ` · ${num(noBrasil, 0)} no Brasil. A sua está aqui? Veja como pedir a correção.`)),
            h("div", { class: "lista-estado__grupo" }, comProblema.map((c) => h("a", { class: "pessoa-chip", href: `#${c.id}`, onclick: () => { S.origem = "lista_problemas"; } }, c.n, h("small", null, problemaCidade(c).curto)))));
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
    const chip = (p) => h("button", { type: "button", class: "pessoa-chip", onclick: () => { S.origem = "governo"; escolher(p.id); } },
      avatar(p, "p"), p.n, h("small", null, pastaCurta(p.g)));
    return h("section", { class: "bloco", id: "governo" },
      h("p", { class: "rotulo" }, "Governo federal"),
      h("h2", null, "Presidente, vice e ministros"),
      h("p", { class: "discreto" }, `Toque num nome para ver quanto ganha e quanto custa por mês. Dados do Portal da Transparência até ${MESES[(ate % 100) - 1]}/${Math.floor(ate / 100)}.`),
      h("div", { class: "lista-estado" }, h("div", { class: "lista-estado__grupo" }, atuais.map(chip))));
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
    const p = posGov(e), link = endereco() ? `${endereco()}#gov-${e.uf}` : "";
    return [
      `*${tituloGov(e)} ${deUF(e.uf)}: ${e.gov.n}*`,
      `Salário (subsídio) do cargo: *${reaisC(e.v[0])} por mês*, bruto. É o ${p.pos}º maior entre os 27 estados.`,
      e.recebe ? e.recebe.texto + (e.recebe.bruto ? ` (${reaisC(e.recebe.bruto)} brutos em ${mesTxt(e.recebe.mes)}).` : ".") : null,
      "",
      `Fonte: ${e.v[3].split(";")[0]}.`,
      `Veja o do seu estado: ${link || "Contas do Poder"}`,
    ].filter((x) => x !== null).join("\n");
  }
  // lista dos 27, do maior salário para o menor (na página inicial e embaixo da página de um estado)
  function secGovernadores(atual) {
    if (!GOV.e.length) return null;
    let campo = "v";
    const corpo = h("div", { style: "display:grid;gap:12px" });
    const desenhar = () => {
      corpo.textContent = "";
      const r = rankingGov(campo), max = r[0][campo][0];
      const valores = r.map((e) => e[campo][0]), med = mediana(valores);
      const linha = (e, i) => h("a", { class: `rank${atual && e.uf === atual.uf ? " rank--eu" : ""}`, href: `#gov-${e.uf}`, onclick: () => { S.origem = "ranking_governadores"; } },
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
        h("article", { class: "cartao" }, h("div", { class: "rank-lista" }, r.map(linha))),
        h("p", { class: "nota" }, "Salário bruto do cargo por mês (o subsídio em vigor hoje), antes do imposto e da previdência. É o valor fixado para o cargo, não necessariamente o que a pessoa recebe: quem é servidor de carreira pode optar pelo salário do cargo de origem (como a governadora de Pernambuco, procuradora do Estado), e o governador em exercício do Rio, desembargador, provavelmente continua recebendo pelo Tribunal de Justiça."),
        h("p", { class: "nota" }, "De onde vem cada valor: ", ...Object.keys(CONF).map((c) => h("span", { style: "display:inline-block;margin:2px 8px 2px 0" }, seloConf(c), " ", CONF[c][1].split(";")[0].replace(/\.$/, ""), ". "))),
        campo === "vv" ? h("p", { class: "nota" }, `Estados sem vice hoje (o vice virou governador ou o cargo ficou vago) aparecem com o valor do cargo, se a lei o fixa. Em ${listaE(GOV.e.filter((e) => !e.vv).map((e) => ESTADOS[e.uf]))}, não achamos o valor do vice.`) : null);
    };
    desenhar();
    return h("section", { class: "bloco", id: "governadores" },
      h("p", { class: "rotulo" }, "Governadores"),
      h("h2", null, atual ? "Os 27 governadores" : "Quanto ganha cada governador"),
      h("p", { class: "discreto" }, "O salário (subsídio) do governador e do vice é fixado por lei em cada estado, pela Assembleia Legislativa, e não há uma fonte nacional com todos. Juntamos, estado por estado, a lei, a tabela oficial ou a folha de pagamento do Estado e, só quando não há outra, a imprensa, e mostramos de onde veio cada valor. Toque num estado para ver quem governa, a lei, a história do valor e se dá para conferir na folha."),
      GOV.e.some((e) => e.m) ? h("p", { class: "discreto" }, `Em ${GOV.e.filter((e) => e.m).length} estados (${listaE(GOV.e.filter((e) => e.m).map((e) => ESTADOS[e.uf]))}), a folha de pagamento abre para o nosso robô, e a página mostra também quanto o governador e o vice receberam de fato em cada mês, com 13º, férias e acertos de saída (marcados com "mês a mês").`) : null,
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
      const dinheiro = (v) => (v == null ? "—" : reaisC(v));
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
          h("div", { class: "rolagem" }, h("table", { class: "tabela-gov" },
            h("thead", null, h("tr", null, ["Mês", "Quem", "Recebeu", ...colunas.map((k) => (k === 9 ? "Abate-teto" : PARTES_GOV.find(([c]) => c === k)[1]))].map((c) => h("th", null, c)))),
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
    return [h("h3", null, "Quanto recebeu, mês a mês"),
      h("p", { class: "discreto pequeno", style: "margin:0" }, `Pela folha de pagamento ${deUF(e.uf)}, com o nome de cada servidor: o que ${govFem(e) ? "a governadora" : "o governador"} e o vice receberam de fato em cada mês, com 13º, férias e acertos.`),
      corpo];
  }
  // página de um estado: #gov-SP
  function secGovernador(e) {
    const p = posGov(e), med = mediana(GOV.e.map((x) => x.v[0]));
    const sm = meta().salario_minimo["2026"] || meta().salario_minimo[anoAtual()];
    const fem = govFem(e), R = rankingGov("v"), maior = R[0], menor = R[R.length - 1];
    const texto = textoGov(e);
    const retorno = h("p", { class: "compartilhar-img__retorno", role: "status" });
    const cargoTxt = (c, f) => ({ gov: f ? "Governadora" : "Governador", vice: f ? "Vice-governadora" : "Vice-governador", exercicio: f ? "Governadora em exercício" : "Governador em exercício", sec: "Secretário de Estado" })[c];
    const lado = (o) => o ? h("span", null, `${o.n}${partidoTxt(o)}`) : null;
    const hist = e.h.filter((x) => x[0] !== "sec");
    const sec = e.h.filter((x) => x[0] === "sec");
    const linhaHist = (x) => h("tr", null,
      h("td", null, fmtMes(x[1])), h("td", null, cargoTxt(x[0])), h("td", { class: "num" }, reaisC(x[2])), h("td", null, seloConf(x[3])),
      h("td", { style: "white-space:normal;min-width:16rem" }, x[4], " ", h("a", { href: x[5], target: "_blank", rel: "noopener" }, "fonte ↗")));
    const foto = e.gov.fc ? h("p", { class: "nota credito" }, "Foto: ", h("a", { href: e.gov.fc.u, target: "_blank", rel: "noopener" }, e.gov.fc.l ? `${(e.gov.fc.a || "autor no Wikimedia Commons").replace(/ from .*$/, "")} (${e.gov.fc.l})` : e.gov.fc.a), e.gov.fc.l ? ", via Wikimedia Commons." : ".") : null;
    return h("article", { class: "cartao conta", id: "governador" },
      h("div", { class: "conta__topo" }, avatar({ n: e.gov.n, f: e.gov.f }, "g"),
        h("div", null,
          h("p", { class: "rotulo" }, `Governo ${deUF(e.uf)}`),
          h("h2", null, e.gov.n),
          h("div", { class: "conta__sub" }, h("span", null, `${tituloGov(e)} ${deUF(e.uf)}${partidoTxt(e.gov).replace(/[()]/g, "").replace(/^ /, " · ")} · desde ${fmtData(e.gov.de)}`))),
        null),
      h("div", { class: "cidade__corpo" },
        h("div", { class: "estatisticas" },
          estatistica(`Salário ${fem ? "da governadora" : "do governador"}`, reaisC(e.v[0]), `por mês, bruto, ${e.v[2] === "imprensa" ? `valor de ${fmtMes(e.v[1])}` : `desde ${fmtMes(e.v[1])}`}`),
          estatistica(e.vice && e.vice.fem ? "Vice-governadora" : "Vice-governador", e.vv ? reaisC(e.vv[0]) : "—", e.vice ? `${e.vice.n}${partidoTxt(e.vice)}` : `cargo vago hoje${e.vv ? " (valor do cargo)" : ""}`),
          estatistica("Em salários mínimos", `${num(e.v[0] / sm, 1)}`, `salários mínimos de ${reais(sm)}`),
          e.vs ? estatistica("Secretário de Estado", reaisC(e.vs[0]), `por mês, desde ${fmtMes(e.vs[1])}`) : null),
        e.recebe ? h("p", { class: "aviso aviso--forte" }, h("strong", null, `${e.recebe.texto}${e.recebe.bruto ? `: ${reaisC(e.recebe.bruto)} brutos em ${mesTxt(e.recebe.mes)}` : ""}. `),
          e.recebe.bruto ? "Quem é servidor de carreira pode escolher entre o salário do cargo de origem e o subsídio do cargo político. O valor da folha já tem o desconto do teto." : "") : null,
        h("p", { class: "destaque", style: "margin:0" }, p.pos === 1 ? `É o maior salário de governador do país${e.v[0] >= 46366 ? ", igual ao teto do funcionalismo (o salário de ministro do STF)" : ""}.`
          : p.pos === p.n ? `É o menor salário de governador do país. A mediana dos 27 estados é ${reais(med)}.`
            : `É o ${p.pos}º maior salário de governador entre os 27 estados. A mediana é ${reais(med)}; o maior é o ${deUF(maior.uf)} (${reais(maior.v[0])}) e o menor, o ${deUF(menor.uf)} (${reais(menor.v[0])}).`),
        h("div", { class: "fonte-gov" },
          h("p", { style: "margin:0" }, h("strong", null, "De onde vem o valor: "), seloConf(e.v[2]), " ", CONF[e.v[2]][1]),
          h("p", { class: "nota", style: "margin:0" }, e.v[3], ". ", h("a", { href: e.v[4], target: "_blank", rel: "noopener" }, "Ver a fonte ↗"))),
        blocoMensalGov(e),
        h("h3", null, "Quem governou desde 2023"),
        h("div", { class: "rolagem" }, h("table", { class: "tabela-gov" },
          h("thead", null, h("tr", null, ["Quem", "Cargo", "De", "Até"].map((c) => h("th", null, c)))),
          h("tbody", null, e.oc.map((o) => h("tr", null,
            h("td", { style: "min-width:11rem" }, h("strong", null, o.n), o.pt ? ` (${o.pt})` : "", o.obs ? h("small", { class: "tabela-gov__obs" }, o.obs) : null),
            h("td", null, cargoTxt(o.c, o.fem)), h("td", null, fmtData(o.de)), h("td", null, o.ate ? fmtData(o.ate) : "hoje")))))),
        h("h3", null, "O salário ao longo do tempo"),
        h("div", { class: "rolagem" }, h("table", { class: "tabela-gov" },
          h("thead", null, h("tr", null, ["Desde", "Cargo", "Valor por mês", "Origem", "Lei ou fonte"].map((c) => h("th", null, c)))),
          h("tbody", null, hist.map(linhaHist)))),
        sec.length ? h("details", { class: "tabela" }, h("summary", null, "Secretários de Estado"), h("div", { class: "rolagem" }, h("table", { class: "tabela-gov" }, h("tbody", null, sec.map(linhaHist))))) : null,
        h("p", { class: "nota" }, "\"Desde\" é o mês em que o valor passou a valer. Quando a fonte é só a imprensa, é o mês a que o valor se refere."),
        h("h3", null, "Dá para conferir na folha de pagamento?"),
        h("p", { style: "margin:0" }, e.m ? "Sim. O Estado publica a folha com o nome de cada servidor, e o robô lê toda semana: veja o mês a mês acima." : FOLHA_GOV[e.folha.s]),
        e.folha.c && !e.m ? h("p", { class: "nota", style: "margin:0" }, `Na folha de ${mesTxt(e.folha.c.mes)}, ${tituloCase(e.folha.c.nome)} aparece com ${reaisC(e.folha.c.bruto)} brutos${Math.abs(e.folha.c.bruto - e.v[0]) > 1 ? " (o valor do mês pode incluir 13º, férias, acertos ou descontos; veja as notas)" : ", o mesmo valor do subsídio"}.`) : null,
        e.folha.u ? h("p", { class: "nota", style: "margin:0" }, h("a", { href: e.folha.u, target: "_blank", rel: "noopener" }, `Folha de pagamento ${deUF(e.uf)} ↗`)) : null,
        e.notas.length ? h("h3", null, "O que mais saber") : null,
        e.notas.map((n) => h("p", { class: "nota", style: "margin:0" }, n)),
        h("div", { class: "acoes" },
          h("a", { class: "botao botao--zap", href: `https://wa.me/?text=${encodeURIComponent(texto)}`, target: "_blank", rel: "noopener", onclick: () => evento("compartilhar", { metodo: "whatsapp", conteudo: "governador", uf: e.uf }) }, "Mandar no WhatsApp"),
          h("button", { type: "button", class: "botao botao--leve", onclick: () => { evento("compartilhar", { metodo: "copiar_texto", conteudo: "governador" }); copiarTexto(texto, retorno, "Texto copiado. É só colar."); } }, "Copiar texto")),
        retorno,
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
        h("div", { class: "estatisticas" },
          estatistica("Custo dele por mês", compacto(C.tm), `${sm(C.tm / sm25)} salários mínimos`),
          estatistica("Vai para o bolso", compacto(C.gm), `${sm(C.gm / sm25)} salários mínimos`)),
        casa === "e" ? h("div", { class: "estatisticas" },
          estatistica("Gastos do cargo", compacto(C.cm), "viagens oficiais, por mês"),
          estatistica("Recebem jetons", String(comJetons), `de ${C.n} ministros em 2025, segundo o Portal`)) : h("div", { class: "estatisticas" },
          estatistica("Equipe do gabinete", compacto(C.em), "por mês"),
          estatistica("Pessoas na equipe", num(C.pessoas || 0, 0), `${reais(C.porPessoa || 0)} por pessoa`)),
        casa === "s" ? h("p", { class: "nota" }, h("span", { class: "etiqueta etiqueta--estimativa" }, "estimativa"), " A equipe do Senado é estimada a partir da folha de pagamento.") : null);
    };
    return h("section", { class: "bloco", id: "tipico" },
      h("p", { class: "rotulo" }, "Para começar"),
      h("h2", null, "Um parlamentar e um ministro típicos"),
      h("div", { class: "grade-cartoes grade-cartoes--3" }, bloco("d", "Deputado federal"), bloco("s", "Senador"), bloco("e", "Ministro de Estado")),
      h("p", { class: "nota" }, "Custo dele: o que vai para o bolso (salário, 13º e auxílios, em valor bruto) mais os gastos do mandato pagos com dinheiro público (cota parlamentar, diárias e outros gastos). A equipe do gabinete fica à parte, porque é dinheiro que paga outras pessoas. Para os ministros, o bolso inclui os jetons de conselhos e os gastos do cargo são as viagens oficiais."),
      h("div", { class: "acoes" }, h("button", { type: "button", class: "botao", onclick: abrirGuia }, "Descobrir os meus representantes")));
  }
  const METRICAS = {
    custo: { nome: "Custo dele por mês", nomeP: "Quanto recebe por mês", v: (r) => r.tm, cls: "barra__fill--neutra", fmt: reais },
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
      const linha = (x, pos) => h("a", { class: `rank${p && x.p.id === p.id ? " rank--eu" : ""}`, href: `#${x.p.id}${R.periodo !== periodoPadrao(x.p) ? "~" + R.periodo : ""}`, onclick: () => { S.origem = "ranking"; } },
        h("span", { class: "rank__pos" }, `${pos}º`),
        h("span", { class: "rank__nome" }, x.p.n, " ", h("small", null, sub(x.p))),
        h("span", { class: "rank__valor" }, M.fmt(x.v)),
        h("span", { class: "barra__trilho" }, h("span", { class: `barra__fill ${M.cls}`, style: `width:${Math.max(0.5, (x.v / max) * 100)}%` })));
      const n = Math.min(10, Math.ceil(lista.length / 2));
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
    const trocouGrupo = () => { R.completo = false; if (!metricaVale(R.metrica, G())) R.metrica = "custo"; periodosOk(); medir(); render(false); irPara("ranking"); };
    const filtros = h("div", { class: "filtros" },
      h("div", { class: "campo" }, h("span", { class: "rotulo" }, "Quem"),
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
  function montarCabecalho() {
    const D = S.D, noCargo = D.p.filter((p) => p.x).length;
    const chips = $("#chips-info");
    chips.textContent = "";
    add(chips,
      h("span", { class: "chip" }, "Dados até ", h("strong", null, `${MESES[mesAtual() - 1]}/${anoAtual()}`)),
      h("span", { class: "chip" }, h("strong", null, D.p.filter((p) => p.x && (p.k === "d" || p.k === "s")).length), " parlamentares e ", h("strong", null, D.p.filter((p) => p.x && p.k === "e").length), " no governo federal, no cargo"),
      cidadesCamara().length ? h("span", { class: "chip" }, h("strong", null, D.p.filter((p) => p.x && p.k === "v").length),
        cidadesCamara().length === 1 ? ` vereadores ${deCid(cidadesCamara()[0].cod)}` : [" vereadores em ", h("strong", null, cidadesCamara().length), " capitais"],
        cidadesPrefeitura().length ? [" e ", h("strong", null, D.p.filter((p) => p.x && p.k === "p").length), cidadesPrefeitura().length === 1 ? " na Prefeitura" : " nas prefeituras"] : null) : null,
      GOV.e.length ? h("span", { class: "chip" }, h("strong", null, GOV.e.length), " governadores") : null,
      h("span", { class: "chip" }, "Salário bruto: ", h("strong", null, "R$ 46.366,19")),
      h("span", { class: "chip" }, "Atualizado em ", h("strong", null, D.meta.atualizado)));
    const sel = $("#estado");
    sel.replaceWith(seletorUF("estado", S.ufLista, (v) => { S.ufLista = v; if (v) evento("ver_estado", { uf: v }); listaEstado(); }, "Ver por estado"));
    ligarBusca($("#busca"), $("#sugestoes"), (p) => { S.origem = "busca"; escolher(p.id); }, null, true);
    $("#abrir-guia").addEventListener("click", abrirGuia);
    document.querySelectorAll("[data-ir]").forEach((b) => b.addEventListener("click", () => irPara(b.dataset.ir)));
    const pend = $("#pendencias");
    D.meta.pendencias.forEach((t) => pend.append(h("li", null, t)));
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
      g ? h("div", { class: "lista-estado__grupo" }, h("a", { class: "pessoa-chip", href: `#gov-${g.uf}`, onclick: () => { S.origem = "estado"; } },
        avatar({ n: g.gov.n, f: g.gov.f }, "p"), g.gov.n, h("small", null, `${tituloGov(g)} · ${reais(g.v[0])} por mês`))) : null,
      h("p", { class: "rotulo" }, `${ESTADOS[S.ufLista]}: ${sen.length} senadores e ${dep.length} deputados federais no cargo`),
      h("div", { class: "lista-estado__grupo" }, sen.map(chip)),
      h("div", { class: "lista-estado__grupo" }, dep.map(chip))));
  }
  function navSecoes(ids) {
    const nomes = { prefeitura: "A Prefeitura", contracheque: "Contracheque", "mes-a-mes": "Mês a mês", equipe: "Equipe do gabinete", cota: "Detalhe dos gastos", comparar: "Comparar", tipico: "Parlamentar típico", governo: "Governo federal", governadores: "Governadores", governador: "O governador", cidade: "A Câmara", cidades: "Câmaras municipais", ranking: "Colegas e ranking", resumo: "Compartilhar", entenda: "Entenda", fontes: "Fontes" };
    const nav = $("#secoes");
    nav.textContent = "";
    ids.filter((id) => document.getElementById(id)).forEach((id) => nav.append(h("button", { type: "button", onclick: () => irPara(id) }, nomes[id])));
  }

  // ================================================================== guia passo a passo
  function abrirGuia() {
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
          h("button", { type: "button", class: "guia__opcao", onclick: () => { evento("guia", { etapa: "cidades" }); fechar(); if (location.hash === "#cidades") irPara("cidades"); else location.hash = "cidades"; } },
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
        GOV.porUF[uf] ? (() => { const g = GOV.porUF[uf]; return h("button", { type: "button", class: "guia__opcao", onclick: () => { evento("guia", { etapa: `governador_${uf}` }); fechar(); S.origem = "guia"; location.hash = `gov-${uf}`; } },
          h("span", null, h("strong", null, `${tituloGov(g)}: ${g.gov.n}`), h("small", null, `Salário de ${reais(g.v[0])} por mês. Veja a lei e quem governou desde 2023`)), h("span", { "aria-hidden": "true" }, "→")); })() : null,
        [...new Set([...cidadesCamara(), ...cidadesPrefeitura()].filter((c) => c.uf === uf).map((c) => c.cod))].map((cod) => {
          const c = { ...(camaraDe(cod) || prefeituraDe(cod)), cod };
          const partes = [camaraDe(cod) ? `os ${S.D.p.filter((q) => q.k === "v" && q.x && q.cid === cod).length} vereadores` : null, prefeituraDe(cod) ? "a Prefeitura" : null].filter(Boolean);
          return h("button", { type: "button", class: "guia__opcao", onclick: () => { evento("guia", { etapa: `capital_${cod}` }); fechar(); S.origem = "guia"; location.hash = `cid-${cod}`; } },
            h("span", null, h("strong", null, `Mora ${COM_ARTIGO.has(cod) ? "no" : "em"} ${c.n}?`), h("small", null, `Veja também ${listaE(partes)} da capital, um a um`)), h("span", { "aria-hidden": "true" }, "→"));
        }),
        h("input", { type: "search", id: "guia-filtro", placeholder: "Filtrar por nome ou partido", autocomplete: "off", oninput: (e) => pintar(e.target.value) }),
        lista,
        h("div", { class: "guia__rodape" },
          h("button", { type: "button", class: "link-botao", onclick: passo1 }, "← Outro estado"),
          h("button", { type: "button", class: "link-botao", onclick: () => { fechar(); S.ufLista = uf; const e = $("#estado"); if (e) e.value = uf; listaEstado(); irPara("rotulo-escolha"); } }, "Ver todos na página")));
      pintar("");
    };
    passo1();
    evento("guia", { etapa: "abrir" });
    if (dlg.showModal) dlg.showModal(); else dlg.setAttribute("open", "");
  }

  // ================================================================== página
  function escolher(id) {
    if (location.hash.slice(1) === id) { render(true); return; }
    location.hash = id;
  }
  function lerEndereco() {
    const bruto = decodeURIComponent(location.hash.slice(1));
    const [base, per] = bruto.split("~");
    if (base && base.startsWith("cid-")) {
      if (S.cidade !== base) {
        evento("ver_cidade", { cidade: base, origem: S.origem || (S.carregado ? "navegacao" : "link") });
        // cidade com vereador por vereador: o ranking embaixo começa pelos vereadores dela
        if (camaraDe(base.slice(4))) Object.assign(S.rank, { casa: "v", cid: +base.slice(4), periodo: "2025", uf: "", metrica: "custo", completo: false });
        else if (prefeituraDe(base.slice(4))) Object.assign(S.rank, { casa: "p", cid: +base.slice(4), periodo: "2025", uf: "", metrica: "custo", completo: false });
      }
      S.origem = null; S.sel = null; S.gov = null; S.cidade = base;
      return null;
    }
    if (base && base.startsWith("gov-") && GOV.porUF[base.slice(4).toUpperCase()]) {
      const uf = base.slice(4).toUpperCase();
      if (S.gov !== uf) evento("ver_governador", { uf, origem: S.origem || (S.carregado ? "navegacao" : "link") });
      S.origem = null; S.sel = null; S.cidade = null; S.gov = uf;
      return null;
    }
    S.gov = null;
    if (base && S.porId.has(base)) {
      S.cidade = null;
      const p = S.porId.get(base);
      if (S.sel !== base) {
        S.outro = null; S.rank.completo = false;
        Object.assign(S.rank, { casa: null, periodo: null, uf: "", metrica: "custo" });
        evento("ver_parlamentar", { parlamentar: p.n, casa: casaTxt(p), uf: p.uf, partido: p.pt || "", origem: S.origem || (S.carregado ? "navegacao" : "link") });
      }
      S.origem = null;
      S.sel = base;
      S.periodo = periodos(p).includes(per) ? per : periodoPadrao(p);
      return null;
    }
    // "#" (logo) ou uma seção que só existe na página inicial: volta para a página inicial
    if (!base || ["tipico", "governo", "governadores", "cidades"].includes(base)) { S.sel = null; S.cidade = null; }
    return base || null; // pode ser o nome de uma seção
  }
  function render(rolar) {
    observadores.forEach((o) => o.disconnect()); observadores = [];
    const app = $("#app");
    app.textContent = "";
    const p = S.sel ? S.porId.get(S.sel) : null;
    if (S.gov) {
      const e = GOV.porUF[S.gov];
      document.title = `${tituloGov(e)} ${deUF(e.uf)} · Contas do Poder`;
      app.append(secGovernador(e), secGovernadores(e));
      navSecoes(["governador", "governadores", "entenda", "fontes"]);
      if (rolar) irPara("governador");
      return;
    }
    if (S.cidade) {
      document.title = "Câmara Municipal · Contas do Poder";
      const espera = h("p", { class: "discreto" }, "Carregando a câmara…");
      app.append(espera);
      carregarCidades().then(() => {
        const c = CID.porId.get(S.cidade);
        if (!c) { espera.textContent = "Cidade não encontrada."; return; }
        document.title = `Câmara de ${c.n} · Contas do Poder`;
        espera.replaceWith(...[secCidade(c), secPrefeitura(c), camaraDe(c.cod) || prefeituraDe(c.cod) ? secRanking(null, null) : null, secCamaras(c)].filter(Boolean));
        navSecoes(["cidade", "prefeitura", "ranking", "cidades", "entenda", "fontes"]);
        if (rolar) irPara("cidade");
      }, () => { espera.textContent = "Não foi possível carregar as câmaras."; });
      return;
    }
    if (p) {
      const k = S.periodo || periodoPadrao(p);
      document.title = `${p.n} · Contas do Poder`;
      const papel = p.k === "j" ? S.porId.get((p.cg.find((c) => c.x) || p.cg[0]).id) || p : p;
      app.append(...[secContracheque(p, k), secMensal(p, k), p.k === "v" ? secEquipe(p, k) || secEquipeVereador(p) : secEquipe(p, k), secCota(p, k), secRanking(papel, k, p.k === "j"), secComparar(p, k), secResumo(p, k)].filter(Boolean));
      navSecoes(["contracheque", "mes-a-mes", "equipe", "cota", "ranking", "comparar", "resumo", "entenda", "fontes"]);
      if (rolar) irPara("contracheque");
    } else {
      document.title = "Contas do Poder";
      app.append(...[secTipicos(), secGoverno(), secGovernadores(null), secCamaras(null), secRanking(null, null), secResumoGeral()].filter(Boolean));
      navSecoes(["tipico", "governo", "governadores", "cidades", "ranking", "resumo", "entenda", "fontes"]);
    }
  }
  window.addEventListener("hashchange", () => { const secao = lerEndereco(); render(!secao); if (secao) irPara(secao); });

  // dados.json (Congresso e governo), camaras.json (vereador por vereador), prefeituras.json e governadores.json;
  // se um dos três últimos falhar, o site segue sem ele
  Promise.all([
    fetch("dados/dados.json").then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); }),
    fetch("dados/camaras.json").then((r) => (r.ok ? r.json() : null)).catch(() => null),
    fetch("dados/prefeituras.json").then((r) => (r.ok ? r.json() : null)).catch(() => null),
    fetch("dados/governadores.json").then((r) => (r.ok ? r.json() : null)).catch(() => null),
  ])
    .then(([D, camaras, prefeituras, governadores]) => {
      if (governadores) { GOV.meta = governadores.meta; GOV.e = governadores.e; GOV.e.forEach((e) => { GOV.porUF[e.uf] = e; }); }
      juntarMunicipal(D, camaras, "cidades");
      juntarMunicipal(D, prefeituras, "prefeituras");
      S.D = D;
      D.p.forEach((p) => S.porId.set(p.id, p));
      // vereador que está (ou esteve) na Prefeitura: a ligação vem do lado da Prefeitura; faz a volta
      D.p.forEach((p) => { const q = p.k === "p" && p.rel && S.porId.get(p.rel); if (q && !q.rel) q.rel = p.id; });
      montarCabecalho();
      const secao = lerEndereco();
      S.carregado = true;
      render(!!S.sel || !!S.cidade);
      carregarCidades().catch(() => {});
      if (secao) irPara(secao);
    })
    .catch((e) => {
      const app = $("#app");
      app.textContent = "";
      app.append(h("p", { class: "aviso" }, `Não foi possível carregar os dados (${e.message}). Se você abriu o arquivo direto do computador, rode "python3 -m http.server -d site" e acesse http://localhost:8000.`));
      console.error(e);
    });
})();
