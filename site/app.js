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
  const ORDEM_GANHA = ["salario", "decimo_terceiro", "auxilio_moradia", "auxilios", "ajuda_de_custo", "outros_rendimentos"];
  const ORDEM_CUSTA = ["cota_parlamentar", "diarias", "outros_gastos_mandato"];
  const ORDEM_EQUIPE = ["assessores_gabinete"];
  function iniciais(nome) {
    const p = nome.replace(/^(Dr|Dra|Delegad[oa]|Coronel|Capitão|Pastor[a]?|Sargento|Professor[a]?|Missionário|General|Cabo|Major|Tenente)\.?\s+/i, "").split(/\s+/);
    return ((p[0] || "")[0] + (p.length > 1 ? p[p.length - 1][0] : "")).toUpperCase();
  }
  function hashNum(t) { let x = 0; for (const c of t) x = (x * 31 + c.charCodeAt(0)) >>> 0; return x; }

  // ================================================================== estado
  const S = {
    D: null, porId: new Map(), sel: null, periodo: null, outro: null, ufLista: "",
    rank: { casa: null, metrica: "custo", periodo: null, uf: "", noCargo: true, completo: false },
  };
  let observadores = [];

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
  // Resumo de um período. "Custo dele" = o que vai para o bolso (ganha) + as despesas dele (custa).
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
  const plural = (casa) => (casa === "d" ? "deputados" : "senadores");
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
    const lista = S.D.p.filter((p) => p.k === casa).map((p) => ({ p, r: resumo(p, k) })).filter((x) => x.r && x.r.m >= 3);
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
  const partidoUF = (p) => `${p.pt || "sem partido"}-${p.uf}`;
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
    return S.D.p.filter((p) => (!filtro || filtro(p)) && termos.every((t) => buscaTexto(p).includes(t)))
      .sort((a, b) => b.x - a.x || a.n.localeCompare(b.n, "pt-BR"));
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
        avatar(p, "p"), h("span", null, p.n, h("small", null, `${p.g} · ${partidoUF(p)}${p.x ? "" : " · fora do cargo"}`)))));
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
          d.append(h("div", null, `${MESES[mes - 1]}/${ano}`), linhasDica(p));
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
  function graficoColegas(caixa, eu, pares) {
    const desenhar = () => {
      caixa.querySelectorAll("svg").forEach((x) => x.remove());
      const W = Math.max(260, caixa.clientWidth), H = 150;
      const m = { t: 30, r: 14, b: 26, l: 14 };
      const iw = W - m.l - m.r, ih = H - m.t - m.b;
      const { ticks, topo } = escala(Math.max(...pares.map((p) => p.v)), 4);
      const x = (v) => m.l + (v / topo) * iw;
      const svg = s("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Onde fica entre os colegas" });
      for (const t of ticks) {
        svg.append(s("line", { class: "grade", x1: x(t), x2: x(t), y1: m.t - 6, y2: H - m.b }));
        const tx = s("text", { x: x(t), y: H - 8, "text-anchor": t === 0 ? "start" : t === topo ? "end" : "middle" });
        tx.textContent = t === 0 ? "R$ 0" : compacto(t); svg.append(tx);
      }
      const pos = pares.map((p) => ({ ...p, cx: x(p.v), cy: m.t + 6 + ((hashNum(p.id) % 1000) / 1000) * (ih - 12) }));
      for (const p of pos) if (p.id !== eu.id) svg.append(s("circle", { class: "ponto", cx: p.cx, cy: p.cy, r: 3.5 }));
      const meu = pos.find((p) => p.id === eu.id);
      if (meu) {
        svg.append(s("line", { class: "guia-linha", x1: meu.cx, x2: meu.cx, y1: 16, y2: meu.cy - 6 }));
        svg.append(s("circle", { class: "ponto--eu", cx: meu.cx, cy: meu.cy, r: 6.5 }));
        const tx = s("text", { class: "forte", x: meu.cx, y: 12, "text-anchor": meu.cx < W * 0.2 ? "start" : meu.cx > W * 0.8 ? "end" : "middle" });
        tx.textContent = `${eu.n}: ${compacto(meu.v)}`; svg.append(tx);
      }
      const destaque = s("circle", { class: "ponto--ativo", r: 5, cx: 0, cy: 0, visibility: "hidden" });
      svg.append(destaque);
      const d = dica(caixa);
      svg.addEventListener("pointermove", (ev) => {
        const r = svg.getBoundingClientRect();
        const px = (ev.clientX - r.left) * (W / r.width), py = (ev.clientY - r.top) * (H / r.height);
        let melhor = null, dist = Infinity;
        for (const p of pos) { const dd = (p.cx - px) ** 2 + (p.cy - py) ** 2; if (dd < dist) { dist = dd; melhor = p; } }
        if (!melhor || dist > 900) { d.hidden = true; destaque.setAttribute("visibility", "hidden"); return; }
        destaque.setAttribute("cx", melhor.cx); destaque.setAttribute("cy", melhor.cy); destaque.setAttribute("visibility", "visible");
        d.hidden = false; d.textContent = "";
        d.append(h("div", null, h("strong", null, reais(melhor.v)), " por mês"), h("div", null, `${melhor.n} (${melhor.pt}-${melhor.uf})`));
        posicionarDica(caixa, d, melhor.cx + 12, melhor.cy + 14);
      });
      svg.addEventListener("pointerleave", () => { d.hidden = true; destaque.setAttribute("visibility", "hidden"); });
      caixa.prepend(svg);
    };
    aoRedimensionar(caixa, desenhar); desenhar();
  }

  // ================================================================== compartilhar
  const endereco = () => (($('meta[name="endereco-do-site"]') || {}).content || "").replace(/#.*$/, "");
  const dominio = () => endereco().replace(/^https?:\/\//, "").replace(/\/$/, "") || "contasdopoder.com";
  const pessoasTxt = (n) => `${num(n, n < 10 && n % 1 ? 1 : 0)} ${Math.round(n) === 1 ? "pessoa" : "pessoas"}`;
  function textoCompartilhar(p, k) {
    const r = resumo(p, k), pos = posicao(p, k);
    const link = endereco() ? `${endereco()}#${p.id}${k !== periodoPadrao(p) ? "~" + k : ""}` : "";
    return [
      `*${p.n}* (${p.g}, ${partidoUF(p)}) ${nomePeriodo(k, false)}:`,
      `Custo dele: *${reais(r.tm)} por mês* (salário, auxílios e despesas pagas com dinheiro público)`,
      `Só o que vai para o bolso: ${reais(r.gm)} por mês (${sm(emSalariosMinimos(p, k, "g"))} salários mínimos)`,
      r.em ? `Equipe do gabinete: ${pessoasTxt(r.pessoas)}, ${reais(r.em)} por mês` : null,
      pos ? `O custo dele fica acima de ${pos.pct}% dos ${plural(p.k)}` : null,
      "",
      `Quanto custa quem te representa? ${link || "Contas do Poder"}`,
    ].filter((x) => x !== null).join("\n");
  }
  function botoesCompartilhar(p, k) {
    const texto = textoCompartilhar(p, k);
    const painel = h("div", { hidden: true, class: "cartao", style: "padding:14px" });
    const retorno = h("p", { class: "pequeno discreto", role: "status" });
    const copiar = async (conteudo, msg) => {
      try { await navigator.clipboard.writeText(conteudo); retorno.textContent = msg; }
      catch (e) {
        retorno.textContent = "";
        const campo = h("input", { type: "text", readonly: true, value: conteudo, "aria-label": "Texto para copiar" });
        retorno.append("Selecione e copie:", campo); campo.select();
      }
    };
    const link = endereco() ? `${endereco()}#${p.id}` : "";
    add(painel, h("div", { class: "acoes" },
      h("button", { type: "button", class: "botao botao--leve", onclick: () => copiar(texto, "Texto copiado. É só colar.") }, "Copiar o texto"),
      link ? h("button", { type: "button", class: "botao botao--leve", onclick: () => copiar(link, "Link copiado.") }, "Copiar o link") : null), retorno);
    return h("div", { class: "compartilhar" },
      h("div", { class: "acoes" },
        h("a", { class: "botao botao--zap", href: `https://wa.me/?text=${encodeURIComponent(texto)}`, target: "_blank", rel: "noopener" }, "Mandar no WhatsApp"),
        h("button", { type: "button", class: "link-botao", onclick: () => { painel.hidden = !painel.hidden; } }, "Outras formas de compartilhar")),
      painel);
  }

  // ================================================================== seções com parlamentar escolhido
  function secContracheque(p, k) {
    const r = resumo(p, k), C = colegas(p.k, k), pos = posicao(p, k);
    const trocar = (novo) => { S.periodo = novo; history.replaceState(null, "", `#${p.id}${novo !== periodoPadrao(p) ? "~" + novo : ""}`); render(false); };
    const card = h("article", { class: "cartao conta", id: "contracheque" });
    add(card, h("div", { class: "conta__topo" },
      avatar(p, "g"),
      h("div", null,
        h("p", { class: "rotulo" }, "Contracheque do mandato"),
        h("h2", null, p.n),
        h("div", { class: "conta__sub" }, h("span", null, `${p.g} · ${partidoUF(p)}`), etiquetaCargo(p))),
      h("a", { href: p.o, target: "_blank", rel: "noopener", class: "pequeno" }, "Página oficial ↗")));
    const lado = h("div", { class: "conta__lado" },
      h("p", { class: "passo" }, "1. Escolha o período"),
      pilulas(periodos(p).map((x) => [x, nomePeriodo(x, true)]), k, trocar, "Período"));
    if (r) {
      add(lado, h("div", { class: "estatisticas" },
        estatistica("Meses de mandato", String(r.m), nomePeriodo(k, false)),
        estatistica("Vai para o bolso", sm(emSalariosMinimos(p, k, "g")), "salários mínimos por mês")));
      if (p.im) {
        const anos = k === "leg" ? Object.keys(p.im) : [k];
        const frases = anos.filter((a) => p.im[a]).map((a) => p.k === "d" ? `${a}: apartamento funcional por ${p.im[a]} dias` : `${a}: ${p.im[a] === "Utilizou" ? "usou" : "não usou"} imóvel funcional`);
        if (frases.length) add(lado, h("div", { class: "estatistica" }, h("span", { class: "rotulo" }, "Moradia em Brasília"), frases.map((f) => h("span", { class: "pequeno" }, f))));
      }
      if (r.mg < r.m) add(lado, h("p", { class: "nota" }, `Em ${r.m - r.mg} ${r.m - r.mg === 1 ? "mês" : "meses"} não houve salário (licença, por exemplo), mas o gabinete continuou funcionando. Cada média usa os seus próprios meses.`));
      if (p.k === "d") add(lado, h("p", { class: "aviso" }, "Ainda faltam o 13º, a ajuda de custo e as diárias dos deputados. O valor real que recebem é um pouco maior."));
    }
    const valores = h("div", { class: "conta__valores" }, h("p", { class: "passo", style: "padding:20px 22px 0" }, "2. Quanto isso dá por mês"));
    if (!r) add(valores, h("p", { class: "discreto", style: "padding:16px 22px" }, "Sem pagamentos registrados neste período."));
    else {
      const txtMed = `mediana dos ${plural(p.k)}`;
      const linhas = (ordem) => ordem.filter((c) => r.cats[c]).map((c) => h("div", { class: "item" },
        h("span", { class: "item__nome" }, nomeCat(c)),
        h("span", { class: "item__valor" }, reais(porMes(r, c))),
        seloComp(porMes(r, c), C.cat[c], `vs. ${txtMed}`)));
      const titulo = (texto, tipo) => h("div", { class: "grupo-titulo" }, h("span", { class: `chave chave--${tipo}` }), h("span", { class: "rotulo" }, texto));
      add(valores,
        titulo("Vai para o bolso", "ganha"), linhas(ORDEM_GANHA),
        titulo("Despesas dele pagas com dinheiro público", "custa"), linhas(ORDEM_CUSTA),
        h("div", { class: "total" },
          h("strong", null, "Custo dele por mês"),
          h("span", { class: "total__valor" }, reais(r.tm)),
          h("span", { class: "item__detalhe" }, `${reais(r.gm)} para o bolso + ${reais(r.cm)} em despesas · ${sm(emSalariosMinimos(p, k, "t"))} salários mínimos`),
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
    return p.t.filter((t) => ano === null || Math.floor(t[0] / 100) === ano).map((t) => ({ aaaamm: t[0], g: t[1], c: t[2], e: t[3], pes: t[4] }));
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
        h("p", { class: "pequeno discreto" }, `O que foi para o bolso e as despesas dele em cada mês, ${nomePeriodo(k, false).replace(/^em /, "")}. A equipe do gabinete aparece à parte.`))),
      h("div", { class: "legenda" }, h("span", null, h("span", { class: "chave chave--ganha" }), "Vai para o bolso"), h("span", null, h("span", { class: "chave chave--custa" }), "Despesas dele")),
      caixa,
      tabela(["Mês", "Bolso", "Despesas", "Custo dele"], pontos.map((q) => [nomeMes(q), reais(q.g), reais(q.c), reais(q.g + q.c)])),
      h("p", { class: "nota" }, p.k === "d"
        ? "O auxílio-moradia da Câmara é informado por ano: entra nas médias, mas não no gráfico. Os 3 últimos meses ainda podem receber notas da cota."
        : "Passagens, correios e outros gastos do Senado são informados por ano: entram nas médias, mas não no gráfico."));
    requestAnimationFrame(() => graficoColunas(caixa, pontos,
      [{ k: "g", cls: "seg-ganha" }, { k: "c", cls: "seg-custa" }],
      (q) => [linhaDica("ganha", reais(q.g), "para o bolso"), linhaDica("custa", reais(q.c), "em despesas"), h("div", null, "Custo dele ", h("strong", null, reais(q.g + q.c)))]));
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
  function secColegas(p, k) {
    const C = colegas(p.k, k), pos = posicao(p, k), r = resumo(p, k);
    if (!pos || C.n < 6) return null;
    const caixa = h("div", { class: "grafico" });
    const card = h("article", { class: "cartao", id: "colegas" },
      h("div", { class: "cartao__cabeca" }, h("div", null, h("h3", null, "Comparado com os colegas"),
        h("p", { class: "pequeno discreto" }, `Custo dele por mês (bolso + despesas), sem a equipe. Cada ponto é um dos ${C.n} ${plural(p.k)} com pelo menos 3 meses de mandato ${nomePeriodo(k, false)}.`))),
      h("div", { class: "estatisticas" },
        estatistica("Custo dele por mês", reais(r.tm), `Mediana: ${reais(C.tm)}`),
        estatistica("Vai para o bolso", reais(r.gm), `Mediana: ${reais(C.gm)}`),
        estatistica("Posição", `${pos.pos}º`, `de ${pos.n} ${plural(p.k)}`)),
      caixa);
    const pares = C.lista.map((x) => ({ id: x.p.id, n: x.p.n, pt: x.p.pt, uf: x.p.uf, v: x.r.tm }));
    requestAnimationFrame(() => graficoColegas(caixa, p, pares));
    return card;
  }
  function secCota(p, k) {
    const ct = p.ct[k] || [];
    if (!ct.length) return null;
    const r = resumo(p, k), max = ct[0][1];
    const notas = [];
    if (ct.some(([i]) => meta().tipos_cota[i].endsWith("*"))) notas.push("* Desde agosto de 2025, a Câmara deixou de publicar nos dados abertos as passagens compradas pelo próprio sistema. Usamos o total do site oficial, que não tem o detalhe por tipo.");
    if (p.k === "d" && k === anoAtual() && meta().limites_cota_camara[p.uf] && r && r.mc) {
      const usado = (r.cats.cota_parlamentar || 0) / (meta().limites_cota_camara[p.uf] * r.mc);
      notas.push(`Usou ${num(usado * 100, 0)}% do limite da cota em ${k} (limite de ${reais(meta().limites_cota_camara[p.uf])} por mês para ${ESTADOS[p.uf]}).`);
    }
    return h("article", { class: "cartao", id: "cota" },
      h("div", { class: "cartao__cabeca" }, h("div", null, h("h3", null, "Para onde vai a cota parlamentar"),
        h("p", { class: "pequeno discreto" }, `Passagens, combustível, alimentação, escritório e outras despesas reembolsadas, somadas ${nomePeriodo(k, false)}.`))),
      h("div", { class: "barras" }, ct.map(([i, v]) => barra(meta().tipos_cota[i], reais(v), v / max))),
      notas.map((n) => h("p", { class: "nota" }, n)));
  }
  function secComparar(p, k) {
    const card = h("article", { class: "cartao", id: "comparar" },
      h("div", { class: "cartao__cabeca" }, h("div", null, h("h3", null, "Comparar com outro parlamentar"),
        h("p", { class: "pequeno discreto" }, "Da Câmara ou do Senado. No mesmo período, quanto o outro custa a mais ou a menos por mês."))));
    const input = h("input", { type: "search", id: "busca-comparar", placeholder: "Nome, partido ou estado", autocomplete: "off" });
    const sug = h("div", { class: "sugestoes", hidden: true });
    add(card, h("div", { class: "busca-caixa", style: "max-width:520px" }, h("label", { class: "visualmente-oculto", for: "busca-comparar" }, "Comparar com"), input, sug));
    ligarBusca(input, sug, (q) => { S.outro = q.id; render(false); irPara("comparar"); }, (q) => q.id !== p.id);
    const o = S.outro && S.porId.get(S.outro);
    if (o) {
      const r1 = resumo(p, k), r2 = resumo(o, k);
      if (!r2) add(card, h("p", { class: "discreto" }, `${o.n} não tem mandato ${nomePeriodo(k, false)}. Escolha outro período acima.`));
      else if (r1) {
        const linhas = [
          ["Vai para o bolso", (r) => r.gm, reais], ["Despesas dele", (r) => r.cm, reais], ["Custo dele por mês", (r) => r.tm, reais],
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
            h("a", { href: `#${o.id}`, class: "pequeno" }, `Ver o contracheque de ${o.n}`),
            h("button", { type: "button", class: "link-botao pequeno", onclick: () => { S.outro = null; render(false); irPara("comparar"); } }, "Tirar da comparação")),
          (p.k === "s" || o.k === "s") ? h("p", { class: "nota" }, "A equipe do Senado é uma estimativa. Para deputados, ainda faltam o 13º, a ajuda de custo e as diárias.") : null);
      }
    }
    return card;
  }
  function secResumo(p, k) {
    const r = resumo(p, k);
    if (!r) return null;
    const pos = posicao(p, k);
    return h("section", { class: "bloco", id: "resumo" },
      h("div", { class: "resumo" },
        h("p", { class: "rotulo" }, "Resumo para compartilhar"),
        h("h2", null, `${p.n}, ${nomePeriodo(k, false).replace(/^em /, "")}`),
        h("p", { style: "color:var(--escuro-ink-2)" }, `${p.g} · ${partidoUF(p)}`),
        h("div", { class: "resumo__grade" },
          h("div", { class: "resumo__item" }, h("span", { class: "rotulo" }, "Custo dele por mês"), h("span", { class: "estatistica__valor" }, reais(r.tm)), h("span", null, "salário, auxílios e despesas")),
          h("div", { class: "resumo__item" }, h("span", { class: "rotulo" }, "Vai para o bolso"), h("span", { class: "estatistica__valor" }, reais(r.gm)), h("span", null, `${sm(emSalariosMinimos(p, k, "g"))} salários mínimos por mês`)),
          r.em ? h("div", { class: "resumo__item" }, h("span", { class: "rotulo" }, "Equipe do gabinete"), h("span", { class: "estatistica__valor" }, compacto(r.em)), h("span", null, `por mês, ${pessoasTxt(r.pessoas)}`)) : null,
          pos ? h("div", { class: "resumo__item" }, h("span", { class: "rotulo" }, "Entre os colegas"), h("span", { class: "estatistica__valor" }, `${pos.pos}º de ${pos.n}`), h("span", null, `custo acima de ${pos.pct}% dos ${plural(p.k)}`)) : null),
        h("p", { class: "resumo__cta" }, `Quanto custa quem te representa? ${dominio()}`),
        h("p", { class: "resumo__fonte" }, "Dados oficiais: Câmara dos Deputados e Senado Federal. Valores brutos, média por mês de mandato.")),
      botoesCompartilhar(p, k));
  }

  // ================================================================== seções gerais
  function secTipicos() {
    const bloco = (casa, titulo) => {
      const C = colegas(casa, "2025"), sm25 = meta().salario_minimo["2025"];
      return h("article", { class: "cartao" },
        h("div", { class: "cartao__cabeca" }, h("h3", null, titulo), h("span", { class: "rotulo" }, "Mediana de 2025")),
        h("div", { class: "estatisticas" },
          estatistica("Custo dele por mês", compacto(C.tm), `${sm(C.tm / sm25)} salários mínimos`),
          estatistica("Vai para o bolso", compacto(C.gm), `${sm(C.gm / sm25)} salários mínimos`)),
        h("div", { class: "estatisticas" },
          estatistica("Equipe do gabinete", compacto(C.em), "por mês"),
          estatistica("Pessoas na equipe", num(C.pessoas || 0, 0), `${reais(C.porPessoa || 0)} por pessoa`)),
        casa === "s" ? h("p", { class: "nota" }, h("span", { class: "etiqueta etiqueta--estimativa" }, "estimativa"), " A equipe do Senado é estimada a partir da folha de pagamento.") : null);
    };
    return h("section", { class: "bloco", id: "tipico" },
      h("p", { class: "rotulo" }, "Para começar"),
      h("h2", null, "Um parlamentar típico"),
      h("div", { class: "grade-cartoes grade-cartoes--2" }, bloco("d", "Deputado federal"), bloco("s", "Senador")),
      h("p", { class: "nota" }, "Custo dele: o que vai para o bolso (salário, 13º e auxílios, em valor bruto) mais as despesas dele pagas com dinheiro público (cota parlamentar, diárias e outros gastos). A equipe do gabinete fica à parte, porque é dinheiro que paga outras pessoas."),
      h("div", { class: "acoes" }, h("button", { type: "button", class: "botao", onclick: abrirGuia }, "Descobrir os meus representantes")));
  }
  const METRICAS = {
    custo: { nome: "Custo dele por mês", v: (r) => r.tm, cls: "barra__fill--neutra", fmt: reais },
    ganha: { nome: "Vai para o bolso por mês", v: (r) => r.gm, cls: "barra__fill--ganha", fmt: reais },
    despesas: { nome: "Despesas dele por mês", v: (r) => r.cm, cls: "", fmt: reais },
    cota: { nome: "Cota parlamentar por mês", v: (r) => porMes(r, "cota_parlamentar"), cls: "", fmt: reais },
    equipe: { nome: "Equipe do gabinete por mês", v: (r) => r.em, cls: "barra__fill--equipe", fmt: reais },
    pessoas: { nome: "Pessoas na equipe", v: (r) => r.pessoas, cls: "barra__fill--equipe", fmt: (v) => num(v, 0) },
    porPessoa: { nome: "Custo por pessoa da equipe", v: (r) => r.porPessoa, cls: "barra__fill--equipe", fmt: reais },
  };
  function secRanking(p) {
    const R = S.rank;
    if (!R.casa) R.casa = p ? p.k : "d";
    if (!R.periodo) R.periodo = "2025";
    if (!METRICAS[R.metrica]) R.metrica = "custo";
    const sec = h("section", { class: "bloco", id: "ranking" });
    const corpo = h("div", { style: "display:grid;gap:12px" });
    const desenhar = () => {
      corpo.textContent = "";
      const M = METRICAS[R.metrica];
      const minimo = R.periodo === "leg" ? 6 : 3;
      const lista = S.D.p.filter((q) => q.k === R.casa && (!R.uf || q.uf === R.uf) && (!R.noCargo || q.x))
        .map((q) => { const r = resumo(q, R.periodo); return r && r.m >= minimo ? { p: q, v: M.v(r) } : null; })
        .filter((x) => x && x.v > 0).sort((a, b) => b.v - a.v);
      const max = Math.max(1, ...lista.map((x) => x.v));
      const linha = (x, pos) => h("a", { class: `rank${p && x.p.id === p.id ? " rank--eu" : ""}`, href: `#${x.p.id}${R.periodo !== periodoPadrao(x.p) ? "~" + R.periodo : ""}` },
        h("span", { class: "rank__pos" }, `${pos}º`),
        h("span", { class: "rank__nome" }, x.p.n, " ", h("small", null, partidoUF(x.p))),
        h("span", { class: "rank__valor" }, M.fmt(x.v)),
        h("span", { class: "barra__trilho" }, h("span", { class: `barra__fill ${M.cls}`, style: `width:${Math.max(0.5, (x.v / max) * 100)}%` })));
      const n = Math.min(10, Math.ceil(lista.length / 2));
      const topo = lista.slice(0, n), fim = lista.slice(-n).reverse();
      const eu = p ? lista.findIndex((x) => x.p.id === p.id) : -1;
      add(corpo,
        h("p", { class: "discreto pequeno" }, `${lista.length} ${plural(R.casa)} · ${M.nome.toLowerCase()} · ${nomePeriodo(R.periodo, false)}${R.uf ? ` · ${ESTADOS[R.uf]}` : ""}`),
        eu >= 0 ? h("p", { class: "destaque", style: "margin:0" }, `${p.n} está em ${eu + 1}º lugar de ${lista.length}.`) : null,
        h("div", { class: "duas-colunas" },
          h("article", { class: "cartao" }, h("h3", null, "Os maiores"), h("div", { class: "rank-lista" }, topo.map((x, i) => linha(x, i + 1)))),
          h("article", { class: "cartao" }, h("h3", null, "Os menores"), h("div", { class: "rank-lista" }, fim.map((x, i) => linha(x, lista.length - i))))),
        R.completo
          ? h("article", { class: "cartao" }, h("h3", null, "Lista completa"), h("div", { class: "rank-lista" }, lista.map((x, i) => linha(x, i + 1))))
          : h("div", null, h("button", { type: "button", class: "botao botao--leve", onclick: () => { R.completo = true; desenhar(); } }, `Ver a lista completa (${lista.length})`)),
        h("ul", { class: "lista nota" },
          R.metrica === "cota" && R.casa === "d" ? h("li", null, "O limite da cota muda por estado, de R$ 41,6 mil (DF) a R$ 58,5 mil (RR) por mês, por causa do preço das passagens.") : null,
          R.casa === "s" && ["equipe", "pessoas", "porPessoa"].includes(R.metrica) ? h("li", null, "A equipe do Senado é uma estimativa feita a partir da folha de pagamento.") : null,
          R.casa === "d" && ["custo", "ganha"].includes(R.metrica) ? h("li", null, "Para deputados, ainda faltam o 13º, a ajuda de custo e as diárias.") : null,
          R.periodo === anoAtual() ? h("li", null, "Período ainda aberto: os últimos meses podem receber notas da cota.") : null,
          h("li", null, `Só entra quem teve pelo menos ${minimo} meses de mandato no período.`)));
    };
    const filtros = h("div", { class: "filtros" },
      h("div", { class: "campo" }, h("span", { class: "rotulo" }, "Casa"),
        pilulas([["d", "Deputados"], ["s", "Senadores"]], R.casa, (v) => { R.casa = v; R.completo = false; render(false); irPara("ranking"); }, "Casa", "grupo-pilulas")),
      h("div", { class: "campo" }, h("label", { for: "metrica" }, "Ordenar por"),
        h("select", { id: "metrica", onchange: (e) => { R.metrica = e.target.value; desenhar(); } },
          Object.entries(METRICAS).map(([v, m]) => h("option", { value: v, selected: v === R.metrica }, m.nome)))),
      h("div", { class: "campo" }, h("label", { for: "periodo-rank" }, "Período"),
        h("select", { id: "periodo-rank", onchange: (e) => { R.periodo = e.target.value; desenhar(); } },
          [...meta().anos, "leg"].map((v) => h("option", { value: v, selected: v === R.periodo }, nomePeriodo(v, true))))),
      h("div", { class: "campo" }, h("label", { for: "uf-rank" }, "Estado"), seletorUF("uf-rank", R.uf, (v) => { R.uf = v; desenhar(); })));
    add(sec, h("p", { class: "rotulo" }, "Ranking"), h("h2", null, "Quem custa mais e quem custa menos"), filtros,
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
        h("a", { class: "botao botao--zap", href: `https://wa.me/?text=${encodeURIComponent(texto)}`, target: "_blank", rel: "noopener" }, "Mandar no WhatsApp"))));
  }

  // ================================================================== cabeçalho da página
  function montarCabecalho() {
    const D = S.D, noCargo = D.p.filter((p) => p.x).length;
    const chips = $("#chips-info");
    chips.textContent = "";
    chips.append(
      h("span", { class: "chip" }, "Dados até ", h("strong", null, `${MESES[mesAtual() - 1]}/${anoAtual()}`)),
      h("span", { class: "chip" }, h("strong", null, noCargo), " parlamentares no cargo · ", h("strong", null, D.p.length), " desde 2023"),
      h("span", { class: "chip" }, "Salário bruto: ", h("strong", null, "R$ 46.366,19")),
      h("span", { class: "chip" }, "Atualizado em ", h("strong", null, D.meta.atualizado)));
    const sel = $("#estado");
    sel.replaceWith(seletorUF("estado", S.ufLista, (v) => { S.ufLista = v; listaEstado(); }, "Ver por estado"));
    ligarBusca($("#busca"), $("#sugestoes"), (p) => escolher(p.id));
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
    const chip = (p) => h("button", { type: "button", class: "pessoa-chip", onclick: () => escolher(p.id) }, avatar(p, "p"), p.n, h("small", null, p.pt));
    const sen = doEstado.filter((p) => p.k === "s"), dep = doEstado.filter((p) => p.k === "d");
    add(caixa, h("div", { class: "lista-estado" },
      h("p", { class: "rotulo" }, `${ESTADOS[S.ufLista]}: ${sen.length} senadores e ${dep.length} deputados federais no cargo`),
      h("div", { class: "lista-estado__grupo" }, sen.map(chip)),
      h("div", { class: "lista-estado__grupo" }, dep.map(chip))));
  }
  function navSecoes(ids) {
    const nomes = { contracheque: "Contracheque", "mes-a-mes": "Mês a mês", equipe: "Equipe do gabinete", colegas: "Comparado com os colegas", cota: "Para onde vai a cota", comparar: "Comparar", tipico: "Parlamentar típico", ranking: "Ranking", resumo: "Resumo para compartilhar", entenda: "Entenda", fontes: "Fontes" };
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
        h("div", { class: "guia__rodape" }, h("button", { type: "button", class: "link-botao", onclick: fechar }, "Pular e ver o painel")));
    };
    const passo2 = (uf) => {
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
          grupo.forEach((p) => lista.append(h("button", { type: "button", class: "sugestao", onclick: () => { fechar(); S.ufLista = uf; escolher(p.id); } },
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
      if (S.sel !== base) { S.outro = null; S.rank.completo = false; }
      S.sel = base;
      const p = S.porId.get(base);
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
      app.append(...[secContracheque(p, k), secMensal(p, k), secEquipe(p, k), secColegas(p, k), secCota(p, k), secComparar(p, k), secRanking(p), secResumo(p, k)].filter(Boolean));
      navSecoes(["contracheque", "mes-a-mes", "equipe", "colegas", "cota", "comparar", "ranking", "resumo", "entenda", "fontes"]);
      if (rolar) irPara("contracheque");
    } else {
      document.title = "Contas do Poder";
      app.append(secTipicos(), secRanking(null), secResumoGeral());
      navSecoes(["tipico", "ranking", "resumo", "entenda", "fontes"]);
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
