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
  const ESTADOS = { AC: "Acre", AL: "Alagoas", AM: "Amazonas", AP: "Amapá", BA: "Bahia", CE: "Ceará", DF: "Distrito Federal", ES: "Espírito Santo", GO: "Goiás", MA: "Maranhão", MG: "Minas Gerais", MS: "Mato Grosso do Sul", MT: "Mato Grosso", PA: "Pará", PB: "Paraíba", PE: "Pernambuco", PI: "Piauí", PR: "Paraná", RJ: "Rio de Janeiro", RN: "Rio Grande do Norte", RO: "Rondônia", RR: "Roraima", RS: "Rio Grande do Sul", SC: "Santa Catarina", SE: "Sergipe", SP: "São Paulo", TO: "Tocantins" };
  const UFS = Object.keys(ESTADOS);
  const ORDEM_GANHA = ["salario", "decimo_terceiro", "jetons", "auxilio_moradia", "auxilios", "ajuda_de_custo", "outros_rendimentos"];
  const ORDEM_CUSTA = ["cota_parlamentar", "diarias", "outros_gastos_mandato", "viagens_oficiais"];
  const ORDEM_EQUIPE = ["assessores_gabinete"];
  function iniciais(nome) {
    const p = nome.replace(/^(Dr|Dra|Delegad[oa]|Coronel|Capitão|Pastor[a]?|Sargento|Professor[a]?|Missionário|General|Cabo|Major|Tenente)\.?\s+/i, "").split(/\s+/);
    return ((p[0] || "")[0] + (p.length > 1 ? p[p.length - 1][0] : "")).toUpperCase();
  }
  function hashNum(t) { let x = 0; for (const c of t) x = (x * 31 + c.charCodeAt(0)) >>> 0; return x; }

  // ================================================================== estado
  const S = {
    D: null, porId: new Map(), sel: null, periodo: null, outro: null, ufLista: "", origem: null, carregado: false,
    rank: { casa: null, metrica: "custo", periodo: null, uf: "", noCargo: true, completo: false },
  };
  let observadores = [];

  // ================================================================== Google Analytics (só se o gtag estiver carregado)
  const evento = (nome, params = {}) => { try { if (typeof gtag === "function") gtag("event", nome, params); } catch (e) { /* segue sem medir */ } };
  const casaTxt = (p) => (p.k === "d" ? "deputado" : "senador");

  // ================================================================== contas
  const meta = () => S.D.meta;
  const anoAtual = () => String(Math.floor(meta().ultimo_mes / 100));
  const mesAtual = () => meta().ultimo_mes % 100;
  function nomePeriodo(k, curto) {
    if (k === "leg") return curto ? "Mandato todo" : `de fev/2023 a ${MESES[mesAtual() - 1]}/${anoAtual()}`;
    if (k === anoAtual()) return curto ? `${k} (até ${MESES[mesAtual() - 1]})` : `em ${k} (até ${MESES[mesAtual() - 1]})`;
    if (k === "2023") return curto ? "2023" : "em 2023 (desde fevereiro)";
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
  const plural = (casa) => ({ d: "deputados", s: "senadores", e: "ministros" })[casa];
  // governo federal: "cargo" em vez de "mandato", viagens em vez de cota
  const gastosNome = (p) => (p.k === "e" ? "Gastos do cargo" : "Gastos do mandato");
  const gastosDetalhe = (p) => (p.k === "e" ? "viagens oficiais" : "cota parlamentar e outros");
  const fonteDados = (p) => (p.k === "e" ? "do Portal da Transparência" : "da Câmara e do Senado");
  const nomeRel = (id) => { const q = S.porId.get(id); return q ? q.g.toLowerCase() : ""; };
  function mediana(xs) {
    const a = xs.filter((x) => x !== null && !isNaN(x)).sort((x, y) => x - y);
    if (!a.length) return null;
    const m = Math.floor(a.length / 2);
    return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2;
  }
  const cacheMed = new Map();
  function colegas(casa, k) {
    const chave = casa + k;
    if (cacheMed.has(chave)) return cacheMed.get(chave);
    const lista = S.D.p.filter((p) => p.k === casa && (casa !== "e" || p.tp === "mi")).map((p) => ({ p, r: resumo(p, k) })).filter((x) => x.r && x.r.m >= 3);
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
  function posicao(p, k) {
    const C = colegas(p.k, k);
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
  const partidoUF = (p) => (p.k === "e" ? (p.pt ? `${p.pt} · governo federal` : "Governo federal") : `${p.pt || "sem partido"}-${p.uf}`);
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
    const achados = S.D.p.filter((p) => (!filtro || filtro(p)) && termos.every((t) => buscaTexto(p).includes(t)));
    const ids = new Set(achados.map((p) => p.id));
    // mesma pessoa em dois cargos (ex.: deputado licenciado que é ministro): mostra só uma vez, o cargo atual
    return achados.filter((p) => {
      const o = p.rel && ids.has(p.rel) ? S.porId.get(p.rel) : null;
      return !o || (p.x && !o.x) || (!!p.x === !!o.x && p.k === "e");
    }).sort((a, b) => b.x - a.x || a.n.localeCompare(b.n, "pt-BR"));
  }
  // campo de busca com lista de sugestões (teclado: setas, Enter, Esc)
  function ligarBusca(input, caixa, aoEscolher, filtro) {
    let itens = [], ativo = -1;
    const fechar = () => { caixa.hidden = true; ativo = -1; };
    const marcar = () => [...caixa.children].forEach((b, i) => b.setAttribute("aria-selected", String(i === ativo)));
    input.addEventListener("input", () => {
      itens = encontrar(input.value, filtro).slice(0, 8);
      caixa.textContent = "";
      itens.forEach((p) => caixa.append(h("button", { type: "button", class: "sugestao", role: "option", onclick: () => { fechar(); input.value = ""; aoEscolher(p); } },
        avatar(p, "p"), h("span", null, p.n, h("small", null, `${p.g} · ${partidoUF(p)}${p.x ? "" : " · fora do cargo"}${p.rel && S.porId.get(p.rel) ? ` · também ${nomeRel(p.rel)}` : ""}`)))));
      if (input.value.trim().length >= 2 && !itens.length) caixa.append(h("p", { class: "pequeno discreto", style: "padding:8px" }, "Ninguém encontrado. Confira a grafia."));
      caixa.hidden = !caixa.children.length;
      ativo = -1;
    });
    input.addEventListener("keydown", (e) => {
      if (caixa.hidden) return;
      if (e.key === "ArrowDown") { ativo = Math.min(itens.length - 1, ativo + 1); marcar(); e.preventDefault(); }
      else if (e.key === "ArrowUp") { ativo = Math.max(0, ativo - 1); marcar(); e.preventDefault(); }
      else if (e.key === "Enter" && itens.length) { const p = itens[Math.max(0, ativo)]; fechar(); input.value = ""; aoEscolher(p); e.preventDefault(); }
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
  function graficoColunas(caixa, pontos, series, linhasDica) {
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
  function textoCompartilhar(p, k) {
    const r = resumo(p, k), pos = posicao(p, k);
    const link = linkDe(p, k);
    return [
      `*${p.n}* (${p.g}, ${partidoUF(p)}) ${nomePeriodo(k, false)}:`,
      `Custo dele: *${reais(r.tm)} por mês*`,
      `• Vai para o bolso: ${reais(r.gm)} por mês (${sm(emSalariosMinimos(p, k, "g"))} salários mínimos)`,
      r.cats.jetons ? `  (inclui ${reais(porMes(r, "jetons"))} por mês de jetons de conselhos)` : null,
      `• ${gastosNome(p)}: ${reais(r.cm)} por mês (${gastosDetalhe(p)})`,
      r.em ? `À parte, a equipe do gabinete: ${pessoasTxt(r.pessoas)}, ${reais(r.em)} por mês` : null,
      pos ? `O custo dele fica acima de ${pos.pct}% dos ${plural(p.k)}` : null,
      "",
      `Tudo com dados abertos oficiais ${fonteDados(p)}.`,
      `Veja também o seu deputado, os senadores e os ministros: ${link || "Contas do Poder"}`,
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
    g.fillStyle = C.ink2; g.font = `600 24px ${BODY}`; g.fillText(p.k === "e" ? "CONTRACHEQUE DO CARGO" : "CONTRACHEQUE DO MANDATO", tx, fy + 28);
    g.fillStyle = "#ffffff"; g.font = `800 ${grande ? 58 : 50}px ${DISP}`;
    let y = quebra(p.n, tx, fy + 88, tmax, grande ? 62 : 54, 3);
    g.fillStyle = C.ink2; g.font = `500 30px ${BODY}`; y = quebra(`${p.g} · ${partidoUF(p)}`, tx, y + 2, tmax, 38, p.k === "e" ? 3 : 2);
    // custo dele
    y = Math.max(y + 30, fy + fh + 62);
    g.fillStyle = C.ink2; g.font = `600 28px ${BODY}`; g.fillText(`CUSTO DELE POR MÊS · ${nomePeriodo(k, true).toUpperCase()}`, M, y);
    comMes(reais(r.tm), M - 6, y + 118, `500 112px ${MONO}`, 36, "#ffffff");
    y += 140;
    if (pos) {
      const selo = pos.pct >= 50 ? `Custa mais que ${pos.pct}% dos ${plural(p.k)}` : `Custa menos que ${100 - pos.pct}% dos ${plural(p.k)}`;
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
      comMes(valor, x + 24, y + 106, `500 54px ${MONO}`, 25, "#ffffff");
      g.fillStyle = C.ink2; g.font = `400 24px ${BODY}`; g.fillText(detalhe, x + 24, y + 142);
    };
    bloco(M, C.ganha, "VAI PARA O BOLSO", reais(r.gm), `${sm(emSalariosMinimos(p, k, "g"))} salários mínimos`);
    bloco(M + tw + 24, C.custa, gastosNome(p).toUpperCase(), reais(r.cm), gastosDetalhe(p));
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
      g.fillText(`${r.pessoas ? pessoasTxt(r.pessoas) : "Assessores"}${r.porPessoa ? ` · ${reais(r.porPessoa)} por pessoa` : ""}${p.k === "s" ? " (estimativa)" : ""}`, M + 24, y + 88);
      g.font = `500 24px ${BODY}`; const wMes = g.measureText("/mês").width + 6;
      g.font = `500 48px ${MONO}`; const wValor = g.measureText(reais(r.em)).width;
      comMes(reais(r.em), W - M - 24 - wMes - wValor, y + 66, `500 48px ${MONO}`, 24, "#ffffff");
      y += eh;
    }
    const aviso = p.k === "d" ? "Para deputados, ainda faltam o 13º, a ajuda de custo e as diárias."
      : p.tp === "pr" ? "O avião presidencial e a estrutura da Presidência não entram na conta."
      : p.k === "e" ? `${r.cats.jetons ? `O bolso inclui ${reais(porMes(r, "jetons"))} por mês de jetons. ` : ""}Voos da FAB não têm custo publicado.` : null;
    if (aviso) { g.fillStyle = C.ink2; g.font = `400 22px ${BODY}`; g.fillText(aviso, M, Math.min(y + 34, H - 196)); }
    if (p.fc && foto) {
      g.fillStyle = "rgba(196,191,224,.7)"; g.font = `400 16px ${BODY}`;
      direita(`Foto: ${(p.fc.a || "Wikimedia Commons").replace(/ from .*$/, "").slice(0, 40)} (${p.fc.l}), Wikimedia Commons`, W - M, H - 190);
    }
    // rodapé: onde ver mais e de onde vêm os dados
    const ry = H - 176;
    g.fillStyle = C.marca; g.fillRect(0, ry, W, H - ry);
    g.fillStyle = "rgba(255,255,255,.85)"; g.font = `700 24px ${BODY}`; g.fillText("VEJA TAMBÉM O SEU DEPUTADO, OS SENADORES E OS MINISTROS EM", M, ry + 46);
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
  function secContracheque(p, k) {
    const r = resumo(p, k), C = colegas(p.k, k), pos = posicao(p, k);
    const trocar = (novo) => { evento("trocar_periodo", { periodo: novo === "leg" ? "mandato" : novo, casa: casaTxt(p) }); S.periodo = novo; S.rank.periodo = novo; history.replaceState(null, "", `#${p.id}${novo !== periodoPadrao(p) ? "~" + novo : ""}`); render(false); };
    const card = h("article", { class: "cartao conta", id: "contracheque" });
    add(card, h("div", { class: "conta__topo" },
      avatar(p, "g"),
      h("div", null,
        h("p", { class: "rotulo" }, p.k === "e" ? "Contracheque do cargo" : "Contracheque do mandato"),
        h("h2", null, p.n),
        h("div", { class: "conta__sub" }, h("span", null, `${p.g} · ${partidoUF(p)}`), etiquetaCargo(p))),
      h("a", { href: p.o, target: "_blank", rel: "noopener", class: "pequeno" }, "Página oficial ↗")));
    const lado = h("div", { class: "conta__lado" },
      h("p", { class: "passo" }, "1. Escolha o período"),
      pilulas(periodos(p).map((x) => [x, nomePeriodo(x, true)]), k, trocar, "Período"));
    if (r) {
      add(lado, h("div", { class: "estatisticas" },
        estatistica(p.k === "e" ? "Meses no cargo" : "Meses de mandato", String(r.m), nomePeriodo(k, false)),
        estatistica("Vai para o bolso", sm(emSalariosMinimos(p, k, "g")), "salários mínimos por mês")));
      if (p.im) {
        const anos = k === "leg" ? Object.keys(p.im) : [k];
        const frases = anos.filter((a) => p.im[a]).map((a) => p.k === "d" ? `${a}: apartamento funcional por ${p.im[a]} dias` : `${a}: ${p.im[a] === "Utilizou" ? "usou" : "não usou"} imóvel funcional`);
        if (frases.length) add(lado, h("div", { class: "estatistica" }, h("span", { class: "rotulo" }, "Moradia em Brasília"), frases.map((f) => h("span", { class: "pequeno" }, f))));
      }
      if (r.mg < r.m && p.k !== "e") add(lado, h("p", { class: "nota" }, `Em ${r.m - r.mg} ${r.m - r.mg === 1 ? "mês" : "meses"} não houve salário (licença, por exemplo), mas o gabinete continuou funcionando. Cada média usa os seus próprios meses.`));
      if (p.k === "d") add(lado, h("p", { class: "aviso" }, "Ainda faltam o 13º, a ajuda de custo e as diárias dos deputados. O valor real que recebem é um pouco maior."));
      if (p.k === "e") {
        const ate = meta().ultimo_mes_executivo;
        add(lado, h("p", { class: "aviso" }, p.tp === "pr"
          ? "O presidente viaja no avião presidencial, e a estrutura da Presidência é paga à parte. Esses custos não aparecem no nome dele: aqui entra o que ele recebe."
          : "Ministros não têm cota parlamentar nem verba de gabinete. Entram o salário, os jetons de conselhos e as viagens oficiais (diárias e passagens). Voos da FAB não têm custo publicado."),
          h("p", { class: "nota" }, `O Portal da Transparência publica os salários com uns 2 meses de atraso: dados até ${MESES[(ate % 100) - 1]}/${Math.floor(ate / 100)}.`));
      }
      if (p.fc) add(lado, h("p", { class: "nota credito" }, "Foto: ", h("a", { href: p.fc.u, target: "_blank", rel: "noopener" }, `${(p.fc.a || "autor no Wikimedia Commons").replace(/ from .*$/, "")} (${p.fc.l})`), ", via Wikimedia Commons."));
      if (p.q) add(lado, h("p", { class: "nota" }, `Depois de deixar o cargo, recebeu mais ${reais(p.q[1])} em ${p.q[0]} ${p.q[0] === 1 ? "mês" : "meses"} (acertos da saída e quarentena). Esse valor não entra nas médias.`));
      if (p.rel && S.porId.get(p.rel)) add(lado, h("p", { class: "nota" },
        p.k === "e" ? `Também é ${nomeRel(p.rel)}. Nos meses como ministro, o salário pode ter sido pago pelo Congresso: aparece aqui. ` : "Também foi do governo federal. ",
        h("a", { href: `#${p.rel}` }, p.k === "e" ? "Ver o contracheque no Congresso" : `Ver o contracheque como ${nomeRel(p.rel)}`)));
    }
    const valores = h("div", { class: "conta__valores" }, h("p", { class: "passo", style: "padding:20px 22px 0" }, "2. Quanto isso dá por mês"));
    if (!r) add(valores, h("p", { class: "discreto", style: "padding:16px 22px" }, "Sem pagamentos registrados neste período."));
    else {
      const txtMed = `mediana dos ${plural(p.k)}`;
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
        titulo(`${gastosNome(p)}, pagos com dinheiro público`, "custa"), linhas(ORDEM_CUSTA),
        rateados.length ? h("p", { class: "nota", style: "padding:10px 22px 0" },
          `≈ ${rateados.map((c) => meta().rateio[c]).join(" ")} Dividimos o total do ano pelos meses com salário: é uma aproximação.`) : null,
        h("div", { class: "total" },
          h("strong", null, "Custo dele por mês"),
          h("span", { class: "total__valor" }, reais(r.tm)),
          h("span", { class: "item__detalhe" }, `${reais(r.gm)} para o bolso + ${reais(r.cm)} em ${gastosNome(p).toLowerCase()} · ${sm(emSalariosMinimos(p, k, "t"))} salários mínimos`),
          seloComp(r.tm, C.tm, `vs. ${txtMed}`)),
        pos ? h("p", { class: "destaque" }, `O custo dele fica acima de ${pos.pct}% dos ${plural(p.k)} ${nomePeriodo(k, false)} (${pos.pos}º de ${pos.n}).`) : null,
        r.em ? h("div", { class: "equipe-resumo" },
          titulo("À parte: equipe do gabinete (vai para outras pessoas)", "equipe"),
          h("div", { class: "estatisticas", style: "padding:6px 22px 0" },
            estatistica("Custo da equipe", reais(r.em), "por mês"),
            estatistica("Pessoas", num(r.pessoas, r.pessoas < 10 ? 1 : 0), r.pessoasHoje ? `em média; ${r.pessoasHoje} no último mês` : "em média"),
            estatistica("Por pessoa", r.porPessoa ? reais(r.porPessoa) : "—", "por mês, em média")),
          h("p", { class: "nota", style: "padding:8px 22px 0" }, p.k === "d"
            ? "Secretários parlamentares pagos pela verba de gabinete. Não inclui cargos de natureza especial, pagos pela Câmara quando o deputado tem cargo de liderança."
            : "Assessores comissionados do gabinete e dos escritórios nos estados. Estimativa feita a partir da folha de pagamento do Senado."),
          h("button", { type: "button", class: "link-botao pequeno", style: "margin:6px 22px 0", onclick: () => irPara("equipe") }, "Ver a equipe mês a mês")) : null,
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
  function secMensal(p, k) {
    const pontos = pontosDoPeriodo(p, k).filter((q) => q.g || q.c);
    if (!pontos.length) return null;
    const caixa = h("div", { class: "grafico" });
    const card = h("article", { class: "cartao", id: "mes-a-mes" },
      h("div", { class: "cartao__cabeca" }, h("div", null, h("h3", null, "Custo dele mês a mês"),
        h("p", { class: "pequeno discreto" }, `O que foi para o bolso e os ${gastosNome(p).toLowerCase()} em cada mês, ${nomePeriodo(k, false).replace(/^em /, "")}. A equipe do gabinete aparece à parte.`))),
      h("div", { class: "legenda" }, h("span", null, h("span", { class: "chave chave--ganha" }), "Vai para o bolso"), h("span", null, h("span", { class: "chave chave--custa" }), gastosNome(p))),
      caixa,
      tabela(["Mês", "Bolso", gastosNome(p), "Custo dele"], pontos.map((q) => [nomeMes(q), reais(q.g), reais(q.c), `${q.ra ? "≈ " : ""}${reais(q.g + q.c)}`])),
      h("ul", { class: "lista nota" },
        pontos.some((q) => q.ra) ? h("li", null, p.k === "d"
          ? "≈ O auxílio-moradia é informado por ano. Dividimos o total pelos meses com salário, então o valor de cada mês é aproximado."
          : "≈ Passagens, correios e outros gastos do Senado são informados por ano. Dividimos o total pelos meses com salário, então o valor de cada mês é aproximado.") : null,
        p.k !== "d" ? h("li", null, "Os meses mais altos costumam ter o 13º salário, pago de uma vez.") : null,
        p.k === "e" ? h("li", null, "As viagens entram no mês em que começaram. Os salários saem no Portal com uns 2 meses de atraso.")
          : h("li", null, "Os 3 últimos meses ainda podem receber notas da cota.")));
    requestAnimationFrame(() => graficoColunas(caixa, pontos,
      [{ k: "g", cls: "seg-ganha" }, { k: "c", cls: "seg-custa" }],
      (q) => [linhaDica("ganha", reais(q.g), "para o bolso"), linhaDica("custa", reais(q.c), `em ${gastosNome(p).toLowerCase()}`), h("div", null, "Custo dele ", h("strong", null, reais(q.g + q.c))),
        q.ra ? h("div", { class: "pequeno" }, `≈ inclui ${reais(q.ra)} de valores informados por ano, divididos por mês`) : null]));
    return card;
  }
  function secEquipe(p, k) {
    const r = resumo(p, k);
    const pontos = pontosDoPeriodo(p, k).filter((q) => q.e);
    if (!r || !r.em || !pontos.length) return null;
    const C = colegas(p.k, k);
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
      h("p", { class: "nota" }, p.k === "d"
        ? "Na Câmara, cada deputado tem até R$ 165.806,07 por mês para pagar até 25 secretários parlamentares. Contamos quem trabalhou no gabinete em cada mês, mesmo que só parte dele."
        : "No Senado, os assessores são pagos direto pela folha. Ligamos a folha à lotação de cada comissionado: é uma estimativa, mais precisa nos meses recentes."));
    requestAnimationFrame(() => graficoColunas(caixa, pontos, [{ k: "e", cls: "seg-equipe" }],
      (q) => [linhaDica("equipe", reais(q.e), "com a equipe"), q.pes ? h("div", null, `${q.pes} pessoas · `, h("strong", null, reais(q.e / q.pes)), " por pessoa") : null]));
    return card;
  }
  // ---------------------------------------------------------------- detalhe dos gastos por tipo
  const divisorCat = (r, cat) => (ORDEM_GANHA.includes(cat) ? r.mg : ORDEM_EQUIPE.includes(cat) ? r.me : r.mc);
  // [[nome do tipo, total no período], ...] de uma categoria, com "Outros tipos" para o que sobra
  function detalheCat(p, k, cat) {
    const r = resumo(p, k);
    const d = (p.dt && p.dt[k] && p.dt[k][cat]) || [];
    if (!r || !d.length) return null;
    const total = r.cats[cat] || 0;
    const linhas = d.map(([i, v]) => [meta().tipos[i], v]);
    const resto = total - linhas.reduce((a, [, v]) => a + v, 0);
    if (total && resto > 0 && resto / total >= 0.005) linhas.push(["Outros tipos", resto]);
    return { total, linhas, div: divisorCat(r, cat) || 1 };
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
    const grupos = (p.k === "e"
      ? [["viagens_oficiais", "Viagens oficiais", ""], ["jetons", "Jetons, por conselho", "barra__fill--ganha"]]
      : [["cota_parlamentar", "Cota parlamentar", ""], ["outros_gastos_mandato", "Outros gastos do mandato", ""]])
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
    }
    const titulo = p.k === "e" ? "Viagens e jetons, por mês" : grupos.length > 1 ? "Para onde vão os gastos do mandato, por mês" : "Para onde vai a cota parlamentar, por mês";
    const sub = p.k === "e" ? `Quanto vai para cada tipo por mês, em média, ${nomePeriodo(k, false)}.`
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
        h("p", { class: "pequeno discreto" }, "Da Câmara ou do Senado. No mesmo período, quanto o outro custa a mais ou a menos por mês."))));
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
          ["Cota parlamentar", (r) => porMes(r, "cota_parlamentar"), reais],
          ["Equipe do gabinete", (r) => r.em, reais], ["Pessoas na equipe", (r) => r.pessoas, (v) => num(v, 0)], ["Por pessoa da equipe", (r) => r.porPessoa, reais]];
        add(card, h("div", { class: "rolagem" }, h("table", { class: "comp-tabela" },
          h("thead", null, h("tr", null, h("th", null, nomePeriodo(k, true)), h("th", null, p.n), h("th", null, o.n), h("th", null, "Diferença"))),
          h("tbody", null, linhas.map(([nome, f, fmt]) => {
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
    custo: { nome: "Custo dele por mês", v: (r) => r.tm, cls: "barra__fill--neutra", fmt: reais },
    ganha: { nome: "Vai para o bolso por mês", v: (r) => r.gm, cls: "barra__fill--ganha", fmt: reais },
    despesas: { nome: "Gastos do mandato por mês", nomeE: "Gastos do cargo (viagens) por mês", v: (r) => r.cm, cls: "", fmt: reais },
    jetons: { nome: "Jetons por mês", v: (r) => porMes(r, "jetons"), cls: "barra__fill--ganha", fmt: reais, casas: ["e"] },
    cota: { nome: "Cota parlamentar por mês", v: (r) => porMes(r, "cota_parlamentar"), cls: "", fmt: reais, casas: ["d", "s"] },
    equipe: { nome: "Equipe do gabinete por mês", v: (r) => r.em, cls: "barra__fill--equipe", fmt: reais, casas: ["d", "s"] },
    pessoas: { nome: "Pessoas na equipe", v: (r) => r.pessoas, cls: "barra__fill--equipe", fmt: (v) => num(v, 0), casas: ["d", "s"] },
    porPessoa: { nome: "Custo por pessoa da equipe", v: (r) => r.porPessoa, cls: "barra__fill--equipe", fmt: reais, casas: ["d", "s"] },
  };
  const metricaVale = (m, casa) => !METRICAS[m].casas || METRICAS[m].casas.includes(casa);
  const nomeMetrica = (m, casa) => (casa === "e" && METRICAS[m].nomeE) || METRICAS[m].nome;
  const nomeGrupo = (casa) => ({ d: "deputados", s: "senadores", e: "governo" })[casa];
  // Colegas e ranking numa seção só: filtros, posição, gráfico de pontos e os maiores/menores.
  function secRanking(p, k) {
    const R = S.rank;
    if (!R.casa) R.casa = p ? p.k : "d";
    if (!R.periodo) R.periodo = (p && k) || "2025";
    if (!METRICAS[R.metrica] || !metricaVale(R.metrica, R.casa)) R.metrica = "custo";
    const sec = h("section", { class: "bloco", id: "ranking" });
    const corpo = h("div", { style: "display:grid;gap:12px" });
    const desenhar = () => {
      corpo.textContent = "";
      const M = METRICAS[R.metrica];
      const minimo = R.periodo === "leg" ? 6 : 3;
      const lista = S.D.p.filter((q) => q.k === R.casa && (!R.uf || R.casa === "e" || q.uf === R.uf) && (!R.noCargo || q.x || (p && q.id === p.id)))
        .map((q) => { const r = resumo(q, R.periodo); return r && r.m >= minimo ? { p: q, v: M.v(r) } : null; })
        .filter((x) => x && x.v > 0).sort((a, b) => b.v - a.v);
      const max = Math.max(1, ...lista.map((x) => x.v));
      const sub = (q) => (q.k === "e" ? pastaCurta(q.g) : partidoUF(q));
      const linha = (x, pos) => h("a", { class: `rank${p && x.p.id === p.id ? " rank--eu" : ""}`, href: `#${x.p.id}${R.periodo !== periodoPadrao(x.p) ? "~" + R.periodo : ""}`, onclick: () => { S.origem = "ranking"; } },
        h("span", { class: "rank__pos" }, `${pos}º`),
        h("span", { class: "rank__nome" }, x.p.n, " ", h("small", null, sub(x.p))),
        h("span", { class: "rank__valor" }, M.fmt(x.v)),
        h("span", { class: "barra__trilho" }, h("span", { class: `barra__fill ${M.cls}`, style: `width:${Math.max(0.5, (x.v / max) * 100)}%` })));
      const n = Math.min(10, Math.ceil(lista.length / 2));
      const topo = lista.slice(0, n), fim = lista.slice(-n).reverse();
      const eu = p ? lista.findIndex((x) => x.p.id === p.id) : -1;
      const med = mediana(lista.map((x) => x.v));
      const grupo = R.casa === "e" ? "no governo federal" : plural(R.casa);
      const caixa = h("div", { class: "grafico" });
      add(corpo,
        eu >= 0 ? h("div", { class: "estatisticas" },
          estatistica(nomeMetrica(R.metrica, R.casa), M.fmt(lista[eu].v), med !== null ? `Mediana: ${M.fmt(med)}` : null),
          estatistica("Posição", `${eu + 1}º`, `de ${lista.length} ${grupo}`)) : null,
        p && eu < 0 ? h("p", { class: "discreto pequeno" }, `${p.n} não entra nesta lista (menos de ${minimo} meses ${R.casa === "e" ? "no cargo" : "de mandato"} no período, valor zero ou outro grupo).`) : null,
        lista.length ? h("div", null,
          h("p", { class: "discreto pequeno", style: "margin:0 0 4px" }, `Cada ponto é um dos ${lista.length} ${grupo === plural(R.casa) ? grupo : "integrantes do governo"} · ${nomeMetrica(R.metrica, R.casa).toLowerCase()} · ${nomePeriodo(R.periodo, false)}${R.uf && R.casa !== "e" ? ` · ${ESTADOS[R.uf]}` : ""}. Passe o mouse ou toque num ponto para ver quem é.`),
          caixa) : h("p", { class: "discreto" }, "Ninguém com dados neste filtro."),
        lista.length ? h("div", { class: "duas-colunas" },
          h("article", { class: "cartao" }, h("h3", null, "Os maiores"), h("div", { class: "rank-lista" }, topo.map((x, i) => linha(x, i + 1)))),
          h("article", { class: "cartao" }, h("h3", null, "Os menores"), h("div", { class: "rank-lista" }, fim.map((x, i) => linha(x, lista.length - i))))) : null,
        R.completo
          ? h("article", { class: "cartao" }, h("h3", null, "Lista completa"), h("div", { class: "rank-lista" }, lista.map((x, i) => linha(x, i + 1))))
          : lista.length > 2 * n ? h("div", null, h("button", { type: "button", class: "botao botao--leve", onclick: () => { R.completo = true; evento("ranking_completo", { casa: nomeGrupo(R.casa), metrica: R.metrica }); desenhar(); } }, `Ver a lista completa (${lista.length})`)) : null,
        h("ul", { class: "lista nota" },
          R.metrica === "cota" && R.casa === "d" ? h("li", null, "O limite da cota muda por estado, de R$ 41,6 mil (DF) a R$ 58,5 mil (RR) por mês, por causa do preço das passagens.") : null,
          R.casa === "s" && ["equipe", "pessoas", "porPessoa"].includes(R.metrica) ? h("li", null, "A equipe do Senado é uma estimativa feita a partir da folha de pagamento.") : null,
          R.casa === "d" && ["custo", "ganha"].includes(R.metrica) ? h("li", null, "Para deputados, ainda faltam o 13º, a ajuda de custo e as diárias.") : null,
          R.casa === "e" ? h("li", null, "Governo federal: presidente, vice e ministros. Viagens em aviões da FAB e no avião presidencial não têm custo publicado.") : null,
          R.periodo === anoAtual() ? h("li", null, R.casa === "e" ? "Período ainda aberto: o Portal publica os salários com uns 2 meses de atraso." : "Período ainda aberto: os últimos meses podem receber notas da cota.") : null,
          h("li", null, `Só entra quem teve pelo menos ${minimo} meses ${R.casa === "e" ? "no cargo" : "de mandato"} no período.`)));
      if (lista.length) requestAnimationFrame(() => graficoPontos(caixa, p ? p.id : null, lista.map((x) => ({ id: x.p.id, n: x.p.n, sub: sub(x.p), v: x.v })), M.fmt));
    };
    const medir = () => evento("ranking", { casa: nomeGrupo(R.casa), metrica: R.metrica, periodo: R.periodo === "leg" ? "mandato" : R.periodo, uf: R.uf || "todos" });
    const filtros = h("div", { class: "filtros" },
      h("div", { class: "campo" }, h("span", { class: "rotulo" }, "Quem"),
        pilulas([["d", "Deputados"], ["s", "Senadores"], ["e", "Governo"]], R.casa, (v) => { R.casa = v; R.completo = false; if (!metricaVale(R.metrica, v)) R.metrica = "custo"; medir(); render(false); irPara("ranking"); }, "Quem", "grupo-pilulas")),
      h("div", { class: "campo" }, h("label", { for: "metrica" }, "Comparar por"),
        h("select", { id: "metrica", onchange: (e) => { R.metrica = e.target.value; medir(); desenhar(); } },
          Object.keys(METRICAS).filter((v) => metricaVale(v, R.casa)).map((v) => h("option", { value: v, selected: v === R.metrica }, nomeMetrica(v, R.casa))))),
      h("div", { class: "campo" }, h("label", { for: "periodo-rank" }, "Período"),
        h("select", { id: "periodo-rank", onchange: (e) => { R.periodo = e.target.value; medir(); desenhar(); } },
          [...meta().anos, "leg"].map((v) => h("option", { value: v, selected: v === R.periodo }, nomePeriodo(v, true))))),
      R.casa === "e" ? null : h("div", { class: "campo" }, h("label", { for: "uf-rank" }, "Estado"), seletorUF("uf-rank", R.uf, (v) => { R.uf = v; medir(); desenhar(); })));
    add(sec, h("p", { class: "rotulo" }, p ? "Colegas e ranking" : "Ranking"),
      h("h2", null, p ? `${p.n} comparado com os colegas` : "Quem custa mais e quem custa menos"), filtros,
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
    chips.append(
      h("span", { class: "chip" }, "Dados até ", h("strong", null, `${MESES[mesAtual() - 1]}/${anoAtual()}`)),
      h("span", { class: "chip" }, h("strong", null, D.p.filter((p) => p.x && p.k !== "e").length), " parlamentares e ", h("strong", null, D.p.filter((p) => p.x && p.k === "e").length), " no governo federal, no cargo"),
      h("span", { class: "chip" }, "Salário bruto: ", h("strong", null, "R$ 46.366,19")),
      h("span", { class: "chip" }, "Atualizado em ", h("strong", null, D.meta.atualizado)));
    const sel = $("#estado");
    sel.replaceWith(seletorUF("estado", S.ufLista, (v) => { S.ufLista = v; if (v) evento("ver_estado", { uf: v }); listaEstado(); }, "Ver por estado"));
    ligarBusca($("#busca"), $("#sugestoes"), (p) => { S.origem = "busca"; escolher(p.id); });
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
    add(caixa, h("div", { class: "lista-estado" },
      h("p", { class: "rotulo" }, `${ESTADOS[S.ufLista]}: ${sen.length} senadores e ${dep.length} deputados federais no cargo`),
      h("div", { class: "lista-estado__grupo" }, sen.map(chip)),
      h("div", { class: "lista-estado__grupo" }, dep.map(chip))));
  }
  function navSecoes(ids) {
    const nomes = { contracheque: "Contracheque", "mes-a-mes": "Mês a mês", equipe: "Equipe do gabinete", cota: "Detalhe dos gastos", comparar: "Comparar", tipico: "Parlamentar típico", governo: "Governo federal", ranking: "Colegas e ranking", resumo: "Compartilhar", entenda: "Entenda", fontes: "Fontes" };
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
        h("p", { class: "discreto" }, "Cada estado elege 3 senadores e de 8 a 70 deputados federais. Escolha o seu estado para ver quem são e quanto cada um ganha e custa."),
        h("p", null, h("strong", null, "Em qual estado você vota?")),
        h("div", { class: "ufs" }, UFS.map((u) => h("button", { type: "button", title: ESTADOS[u], onclick: () => passo2(u) }, u))),
        h("div", { class: "guia__outros" },
          h("p", null, h("strong", null, "Ou veja quem não depende do estado")),
          h("button", { type: "button", class: "guia__opcao", onclick: passoGoverno },
            h("span", null, h("strong", null, "Governo federal"), h("small", null, "Presidente, vice e ministros")), h("span", { "aria-hidden": "true" }, "→"))),
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
    if (base && S.porId.has(base)) {
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
    return base || null; // pode ser o nome de uma seção
  }
  function render(rolar) {
    observadores.forEach((o) => o.disconnect()); observadores = [];
    const app = $("#app");
    app.textContent = "";
    const p = S.sel ? S.porId.get(S.sel) : null;
    if (p) {
      const k = S.periodo || periodoPadrao(p);
      document.title = `${p.n} · Contas do Poder`;
      app.append(...[secContracheque(p, k), secMensal(p, k), secEquipe(p, k), secCota(p, k), secRanking(p, k), secComparar(p, k), secResumo(p, k)].filter(Boolean));
      navSecoes(["contracheque", "mes-a-mes", "equipe", "cota", "ranking", "comparar", "resumo", "entenda", "fontes"]);
      if (rolar) irPara("contracheque");
    } else {
      document.title = "Contas do Poder";
      app.append(...[secTipicos(), secGoverno(), secRanking(null, null), secResumoGeral()].filter(Boolean));
      navSecoes(["tipico", "governo", "ranking", "resumo", "entenda", "fontes"]);
    }
  }
  window.addEventListener("hashchange", () => { const secao = lerEndereco(); render(!secao); if (secao) irPara(secao); });

  fetch("dados/dados.json")
    .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
    .then((D) => {
      S.D = D;
      D.p.forEach((p) => S.porId.set(p.id, p));
      montarCabecalho();
      const secao = lerEndereco();
      S.carregado = true;
      render(!!S.sel);
      if (secao) irPara(secao);
    })
    .catch((e) => {
      const app = $("#app");
      app.textContent = "";
      app.append(h("p", { class: "aviso" }, `Não foi possível carregar os dados (${e.message}). Se você abriu o arquivo direto do computador, rode "python3 -m http.server -d site" e acesse http://localhost:8000.`));
      console.error(e);
    });
})();
