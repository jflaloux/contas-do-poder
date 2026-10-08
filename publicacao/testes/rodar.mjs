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
//   node publicacao/testes/rodar.mjs --rapido          modo rápido, para o meio do trabalho: uma página de cada tipo, 2 perfis (uns 3 min)
//   node publicacao/testes/rodar.mjs --mudou           o rápido mais as páginas dos assuntos que o seu git diff toca (ver GRUPOS). A suíte
//                                                      completa (--completo, sem --rapido) continua sendo a que vale antes do commit
//   node publicacao/testes/regras.mjs                  as regras de cálculo com casos inventados e a concordância entre o HTML pronto e a página
//   node publicacao/testes/rodar.mjs --analytics       com --paginas, roda também a conferência do Google Analytics (sem --paginas ela já roda; --sem-analytics a corta)
//   node publicacao/testes/rodar.mjs --url=http://localhost:8000      usa um servidor que já está rodando (a conferência do Analytics só roda em localhost)
//   node publicacao/testes/rodar.mjs --capturas=/tmp/capturas         guarda uma imagem de cada página
//   node publicacao/testes/rodar.mjs --baixar-axe      baixa o axe-core (uma vez) para o cache e roda
// Precisa só do Node (22 ou mais novo) e do Chrome. Nenhum pacote do npm; nada disso entra no build do Cloudflare Pages.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import crypto from "node:crypto";
import { spawn, spawnSync } from "node:child_process";
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
// o primeiro (por id) que recebeu 13º em 2025 (dados.json): a linha do 13º só existe para quem recebeu
const primeiroCom13 = (prefixo) => {
  try {
    const D = lerDados("dados.json");
    const id = D.p.filter((p) => p.id.startsWith(prefixo) && p.per && p.per["2025"] && (p.per["2025"].cats || {}).decimo_terceiro > 0).map((p) => p.id).sort()[0];
    return id && ENDERECOS[id] ? `/${ENDERECOS[id]}` : null;
  } catch { return null; }
};
// Reserva pelo Tribunal de Contas (situacao.json, "reservas"): hoje nenhuma está ligada, então o teste liga à mão, só na página
// que está sendo testada (o pedido do arquivo é respondido aqui, sem mexer em site/dados/). O de Recife ganha um vereador de
// mentira (o arquivo de PE não tem a Câmara do Recife).
const simularReservas = (chaves, comRecife) => (caminho) => {
  if (caminho === "/dados/situacao.json") {
    const s = lerDados("situacao.json");
    for (const k of chaves) { s.reservas[k].ativa = true; s.reservas[k].motivo = "a coleta da fonte própria falhou"; }
    return JSON.stringify(s);
  }
  if (comRecife && caminho === "/dados/interior-cargo/pe.json") {
    const d = lerDados("interior-cargo/pe.json");
    d.m["2611606"] = { ...d.m["2611606"], cad: 37, c: d.m["2600054"].c, zc: undefined };
    return JSON.stringify(d);
  }
  return null;
};
// "O que mudou nesta rodada" (situacao.json, chave "rodada"): o arquivo real tem rodada desde 07/10/2026; os testes de rodada
// põem uma de mentira na resposta do arquivo, para o texto não depender do que a rodada real trouxe, com fontes de verdade (os nomes saem do próprio arquivo)
const FONTES_SIT = (lerDados("situacao.json") || { fontes: [] }).fontes || [];
const reEsc = (t) => String(t).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const simularRodada = (rodada) => (caminho) => { if (caminho !== "/dados/situacao.json") return null; const s = lerDados("situacao.json"); s.rodada = rodada; return JSON.stringify(s); };
// Limite da verba do gabinete por vigência (camaras.json, meta.cidades[cod].verba_vigencia = [[desde AAAAMM, valor], ...]): só quando o limite muda no meio de
// um ano o texto diz cada valor com o período; sem o campo, ou com mudança só na virada do ano, fica o texto por ano de sempre. Os dados são simulados (São Paulo)
const simularVerba = (verbaMes, vigencia) => (caminho) => {
  if (caminho !== "/dados/indice/camaras.json" && caminho !== "/dados/camaras.json") return null;
  const d = lerDados("camaras.json"), c = d.meta.cidades["3550308"];
  c.verba_mes = verbaMes; if (vigencia) c.verba_vigencia = vigencia; else delete c.verba_vigencia;
  return JSON.stringify(d);
};
const VER_SP = Object.keys(ENDERECOS).filter((k) => k.startsWith("ver-3550308-")).sort()[0];
const VERBA_ANOS = { 2025: 34706.25, 2026: 36018.75 };
const VERBA_TEXTO_ANOS = [/Cada vereador pode gastar até R\$\s34\.706 em 2025 e R\$\s36\.019 em 2026 por mês\./];
// Valor de governador, vice ou secretário cuja origem é "imprensa" (governadores.json): a fonte aparece como notícia, com o nome do veículo e a norma
// que ela cita ("não foi localizada"); se o link é de órgão público (.gov.br), não é notícia e o texto da fonte fica como está. O teste simula os dados
// para não depender de o `dados` ainda ter ou não um caso assim.
const simularImprensa = (muda) => (caminho) => { if (caminho !== "/dados/governadores.json") return null; const d = lerDados("governadores.json"); muda(d.e); return JSON.stringify(d); };
const JORNAL_AP = "https://www.diariodoamapa.com.br/cadernos/politica/publicadas-leis-que-fixam-subsidios-de-deputados-estaduais-e-de-gestores-do-poder-executivo-a-partir-de-janeiro/";
const IMPRENSA_AP = (es) => { const e = es.find((x) => x.uf === "AP"); e.vs = [18000, 202301, "imprensa", "Lei nº 2.799, de 30/12/2022", JORNAL_AP];
  e.h = e.h.filter((x) => x[0] !== "sec").concat([["sec", 202301, 18000, "imprensa", "Lei nº 2.799, de 30/12/2022", JORNAL_AP]]);
  e.vv = [29700, 202301, "imprensa", "valor informado pelo jornal", "https://jornal.exemplo.com.br/noticia"]; };
// Bens declarados ao TSE (bens.json e bens-interior/<uf>.json): os arquivos só existem a partir de 26/10/2026, então o teste simula os dois (a
// <meta name="dados-bens"> entra na página e o arquivo, na resposta do pedido), com pessoas e nomes de verdade dos arquivos do site. Os valores são de
// mentira. O código da eleição e a região são do formato do DivulgaCandContas (conferido em 03/10/2026).
const REGIAO_UF = Object.fromEntries(Object.entries({ NORTE: "AC AP AM PA RO RR TO", NORDESTE: "AL BA CE MA PB PE PI RN SE", CENTROOESTE: "DF GO MT MS", SUDESTE: "ES MG RJ SP", SUL: "PR RS SC" })
  .flatMap(([r, ufs]) => ufs.split(" ").map((u) => [u, r])));
const META_BENS = { credito: "Fonte: Tribunal Superior Eleitoral (dados abertos das candidaturas), licença CC BY 4.0", licenca: "CC BY 4.0", fontes: {}, regiao: REGIAO_UF,
  grupos: ["Imóveis", "Veículos", "Aplicações e depósitos", "Participações em empresas", "Outros"], eleicao: { 2018: "2022802018", 2022: "2040602022", 2024: "2045202024" },
  link: "https://divulgacandcontas.tse.jus.br/divulga/#/candidato/{regiao}/{uf}/{eleicao}/{sq}/{ano}/{ue}" };
const idDe = (prefixo, i = 0) => Object.keys(ENDERECOS).filter((k) => k.startsWith(prefixo)).sort()[i];
const BENS_FALSOS = { dep: idDe("dep-"), depSem: idDe("dep-", 1), sen: idDe("sen-"), ver: idDe("ver-"), pre: idDe("pre-"), est: idDe("est-") };
const simularBens = (interior = {}) => (caminho) => {
  if (caminho === "/dados/bens.json") {
    return JSON.stringify({ meta: META_BENS, p: {
      [BENS_FALSOS.dep]: [2022, 366907.22, 5, 230590, 84000, 52317.22, 0, 0, "XX", "270001234567"], [BENS_FALSOS.depSem]: [2022, 0, 0, 0, 0, 0, 0, 0, "XX", "270007654321"],
      [BENS_FALSOS.sen]: [2018, 1250000, 1, 0, 0, 1250000, 0, 0, "XX", "260000000001"], [BENS_FALSOS.ver]: [2024, 98500.5, 3, 80000, 18500.5, 0, 0, 0, "3550308", "250002345678"],
      [BENS_FALSOS.pre]: [2024, 640000, 2, 640000, 0, 0, 0, 0, "2304400", "60001234567"], [BENS_FALSOS.est]: [2022, 15000, 1, 0, 15000, 0, 0, 0, "XX", "180001112223"] } });
  }
  const m = /^\/dados\/bens-interior\/([a-z]{2})\.json$/.exec(caminho);
  return m && interior[m[1]] ? JSON.stringify({ meta: META_BENS, m: interior[m[1]] }) : null;
};
// os nomes de uma cidade do interior, como os arquivos do site trazem (a chave é o nome civil, ou o de urna se não houver)
const nomesInterior = (arq, cod, blocos) => { const d = lerDados(arq).m[String(cod)]; return blocos.flatMap((b) => { const x = d[b]; const l = Array.isArray(x) ? x.filter((q) => q.x === 1) : (x && x.ps) || []; return l.map((q) => q.nc || q.n); }); };
const BENS_CE = (() => { const [pf, vp, ...v] = [...nomesInterior("interior/ce.json", 2300101, ["pf"]), ...nomesInterior("interior/ce.json", 2300101, ["vp"]), ...nomesInterior("interior/ce.json", 2300101, ["v"])];
  return { 2300101: { [pf]: [2024, 175500, 4, 145000, 24000, 0, 6500, 0, "13013", "60002313505"], [vp]: [2024, 0, 0, 0, 0, 0, 0, 0, "13013", "60002313506"], [v[0]]: [2024, 52000, 2, 0, 52000, 0, 0, 0, "13013", "60002313507"] } }; })();
const BENS_ES = (() => { const nomes = nomesInterior("interior-cargo/es.json", 3200102, ["c"]); return { 3200102: { [nomes[2]]: [2024, 310000, 1, 310000, 0, 0, 0, 0, "56170", "80000123456"], [nomes[0]]: [2024, 0, 0, 0, 0, 0, 0, 0, "56170", "80000123457"] } }; })();
// nada de juízo, ranking, média, comparação ou evolução dentro do bloco (testado só no texto de #bens)
const SEM_JULGAMENTO_BENS = [/mais rico/i, /\brico\b/i, /patrimônio (cresceu|aumentou|dobrou)/i, /evolução/i, /maior patrimônio/i, /ranking/i, /enriquec/i, /média/i, /mediana/i, /\bcompar/i, /acima d[eoa]/i, /abaixo d[eoa]/i];
const PAGINAS = [
  { nome: "inicio", url: "/", ter: [["#chips-info", 1]] },
  // o "Descobrir", passo 2 (SP) aberto: nada rola para o lado, a única rolagem é a do popup, os rótulos existem e "Ver todos" abre o grupo
  { nome: "descobrir-passo-2", url: "/", depois: `(async () => {
      const f = [], esp = (ms) => new Promise((r) => setTimeout(r, ms));
      document.querySelector("#abrir-guia").click(); await esp(300);
      [...document.querySelectorAll("#guia .ufs button")].find((b) => b.textContent === "SP").click(); await esp(400);
      const d = document.querySelector("#guia");
      if (!d.open) f.push("o popup não abriu");
      if (!d.getAttribute("aria-labelledby") || !document.getElementById(d.getAttribute("aria-labelledby"))) f.push("o popup não tem título ligado (aria-labelledby)");
      if (!/passo 2 de 3/i.test(d.innerText)) f.push("não está no passo 2");
      const todos = [d, ...d.querySelectorAll("*")];
      const lado = todos.filter((e) => e.clientWidth > 0 && e.scrollWidth > e.clientWidth + 1).map((e) => e.tagName + "." + e.className);
      if (lado.length) f.push("rola para o lado dentro do popup: " + lado.slice(0, 3).join(", "));
      const aninhadas = [...d.querySelectorAll("*")].filter((e) => { const o = getComputedStyle(e).overflowY; return (o === "auto" || o === "scroll") && e.scrollHeight > e.clientHeight + 1; }).map((e) => e.className);
      if (aninhadas.length) f.push("rolagem dentro da rolagem do popup: " + aninhadas.join(", "));
      const sem = [...d.querySelectorAll("input, button")].filter((e) => !(e.getAttribute("aria-label") || e.innerText.trim() || e.getAttribute("title") || e.placeholder)).length;
      if (sem) f.push(sem + " campos ou botões sem nome acessível");
      const antes = d.querySelectorAll(".sugestao").length, mais = d.querySelector(".guia__mais");
      if (!mais) f.push('não achei o "Ver todos os N" do grupo de deputados');
      else {
        mais.click(); await esp(200);
        if (d.querySelectorAll(".sugestao").length <= antes) f.push('"Ver todos" não mostrou mais nomes');
        if (!d.contains(document.activeElement) || document.activeElement.tagName !== "BUTTON") f.push("o foco saiu do popup ao abrir o grupo");
      }
      const filtro = d.querySelector("#guia-filtro");
      if (!filtro || !filtro.getAttribute("aria-label")) f.push("o campo de filtro não tem rótulo");
      return f;
    })()` },
  // sem os arquivos de bens (hoje não existem; só a partir de 26/10/2026): nada aparece, nem título, e o app nem pede o arquivo
  { nome: "deputado-federal", url: primeiro("dep-"), semPagina: [/bens declarados/i, /Justiça Eleitoral/] },
  // arquivo que FALTA (404) ou vem quebrado: a seção diz que não deu para carregar (atividade) ou some (bens, que é opcional), e para de pedir
  // (antes, a seção se recriava e pedia o arquivo de novo, em ciclo, e a página podia travar). O limite de pedidos pega o ciclo.
  { nome: "atividade-arquivo-ausente", url: ENDERECOS["dep-74856"] ? `/${ENDERECOS["dep-74856"]}` : null, falhasEsperadas: ["/dados/atividade.json"], maxPedidos: { "/dados/atividade.json": 4 },
    simular: (c) => (c === "/dados/atividade.json" ? { status: 404, corpo: "não achei" } : null),
    atividade: [/Não foi possível carregar a presença e os projetos agora\./, /Tentar de novo/], semAtividade: [/Carregando a presença e os projetos/, /dias com sessão deliberativa/],
    depois: `(async () => { const f = []; const b = document.querySelector("#atividade button"); if (!b) return ["sem o botão Tentar de novo"]; const n0 = performance.getEntriesByName(location.origin + "/dados/atividade.json").length;
      b.click(); await new Promise((r) => setTimeout(r, 1200)); if (!document.querySelector("#atividade")) f.push("a seção de atividade sumiu depois de Tentar de novo");
      if (/Carregando a presença/.test(document.querySelector("#atividade").innerText)) f.push("depois de Tentar de novo a seção ficou carregando sem fim"); return f; })()` },
  { nome: "atividade-arquivo-quebrado", url: ENDERECOS["dep-74856"] ? `/${ENDERECOS["dep-74856"]}` : null, maxPedidos: { "/dados/atividade.json": 4 },
    simular: (c) => (c === "/dados/atividade.json" ? JSON.stringify({ meta: {} }) : null), atividade: [/Não foi possível carregar a presença e os projetos agora\./], semAtividade: [/Carregando a presença e os projetos/] },
  { nome: "senador-atividade-arquivo-ausente", url: ENDERECOS["sen-5672"] ? `/${ENDERECOS["sen-5672"]}` : null, falhasEsperadas: ["/dados/atividade.json"], maxPedidos: { "/dados/atividade.json": 4 },
    simular: (c) => (c === "/dados/atividade.json" ? { status: 404, corpo: "" } : null), atividade: [/Não foi possível carregar a presença e os projetos agora\./] },
  { nome: "bens-arquivo-ausente", url: `/${ENDERECOS[BENS_FALSOS.dep]}`, metas: { "dados-bens": "br" }, falhasEsperadas: ["/dados/bens.json"], maxPedidos: { "/dados/bens.json": 4 },
    simular: (c) => (c === "/dados/bens.json" ? { status: 404, corpo: "" } : null), semPagina: [/Bens declarados/i, /Justiça Eleitoral/, /Carregando/] },
  { nome: "bens-arquivo-quebrado", url: `/${ENDERECOS[BENS_FALSOS.dep]}`, metas: { "dados-bens": "br" }, maxPedidos: { "/dados/bens.json": 4 },
    simular: (c) => (c === "/dados/bens.json" ? "isto não é JSON" : null), semPagina: [/Bens declarados/i] },
  { nome: "bens-cidade-arquivo-ausente", url: "/cidade/abaiara-ce", metas: { "dados-bens": "ce" }, falhasEsperadas: ["/dados/bens-interior/ce.json"], maxPedidos: { "/dados/bens-interior/ce.json": 4 },
    simular: (c) => (c === "/dados/bens-interior/ce.json" ? { status: 404, corpo: "" } : null), semPagina: [/Bens declarados/i] },
  // bens declarados ao TSE (arquivos simulados): texto neutro, aviso de que é autodeclarado e não é valor de mercado, link para o TSE, crédito, e nada de
  // ranking, comparação, evolução ou "mais rico"; só tipo e valor; o bloco fica à parte, depois da comparação e antes do "Compartilhar"
  { nome: "bens-deputado", recorte: "#bens", url: `/${ENDERECOS[BENS_FALSOS.dep]}`, metas: { "dados-bens": "br" }, simular: simularBens(),
    pagina: [/Bens declarados à Justiça Eleitoral/, /Na candidatura de 2022, declarou ao TSE bens que somam R\$\s366\.907,22, em 5 itens: imóveis R\$\s230\.590,00; veículos R\$\s84\.000,00; aplicações e depósitos R\$\s52\.317,22\./,
      /Declaração feita pela própria pessoa ao se candidatar\. Os valores são os informados por ela, em geral o valor de compra, e não o valor de mercado de hoje; a Justiça Eleitoral não confere esses valores\./,
      /Ver a declaração no TSE/, /Fonte: Tribunal Superior Eleitoral/],
    semBens: SEM_JULGAMENTO_BENS,
    depois: `(() => { const f = [], b = document.querySelector("#bens"); if (!b) return ["não achei o bloco #bens"];
      const a = b.querySelector("a[href*='divulgacandcontas']"); if (!a) f.push("sem o link da declaração no TSE");
      else if (!/^https:\\/\\/divulgacandcontas\\.tse\\.jus\\.br\\/divulga\\/#\\/candidato\\/(NORTE|NORDESTE|CENTROOESTE|SUDESTE|SUL)\\/[A-Z]{2}\\/2040602022\\/270001234567\\/2022\\/XX$/.test(a.href)) f.push("o link do TSE não segue o modelo: " + a.href);
      if (a && a.target !== "_blank") f.push("o link do TSE devia abrir em outra aba");
      const ant = document.querySelector("#comparar"), dep = document.querySelector("#resumo");
      if (ant && !(ant.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING)) f.push("o bloco de bens devia vir depois da comparação");
      if (dep && !(b.compareDocumentPosition(dep) & Node.DOCUMENT_POSITION_FOLLOWING)) f.push('o bloco de bens devia vir antes do "Compartilhar"');
      if (document.querySelector("#contracheque #bens, .conta__resumo #bens")) f.push("os bens não podem entrar no contracheque");
      if (/\\bbens\\b/i.test((document.querySelector("#contracheque") || {}).innerText || "")) f.push("o contracheque não pode falar de bens");
      return f; })()` },
  { nome: "bens-sem-bens", recorte: "#bens", url: `/${ENDERECOS[BENS_FALSOS.depSem]}`, metas: { "dados-bens": "br" }, simular: simularBens(),
    pagina: [/Na candidatura de 2022, não declarou bens à Justiça Eleitoral\./, /Ver a declaração no TSE/, /Fonte: Tribunal Superior Eleitoral/], semPagina: [/bens que somam/, /em 0 itens/] },
  { nome: "bens-senador", url: `/${ENDERECOS[BENS_FALSOS.sen]}`, metas: { "dados-bens": "br" }, simular: simularBens(),
    pagina: [/Na candidatura de 2018, declarou ao TSE bens que somam R\$\s1\.250\.000,00, em 1 item: aplicações e depósitos R\$\s1\.250\.000,00\./] },
  { nome: "bens-vereador-capital", url: `/${ENDERECOS[BENS_FALSOS.ver]}`, metas: { "dados-bens": "br" }, simular: simularBens(),
    pagina: [/Na candidatura de 2024, declarou ao TSE bens que somam R\$\s98\.500,50, em 3 itens: imóveis R\$\s80\.000,00; veículos R\$\s18\.500,50\./] },
  { nome: "bens-prefeitura", url: `/${ENDERECOS[BENS_FALSOS.pre]}`, metas: { "dados-bens": "br" }, simular: simularBens(), pagina: [/Bens declarados à Justiça Eleitoral/, /imóveis R\$\s640\.000,00/] },
  { nome: "bens-estadual", url: `/${ENDERECOS[BENS_FALSOS.est]}`, metas: { "dados-bens": "br" }, simular: simularBens(), pagina: [/Bens declarados à Justiça Eleitoral/, /veículos R\$\s15\.000,00/] },
  // quem não tem registro no arquivo (a maioria dos ministros, por exemplo): sem o bloco, mesmo com o arquivo e a <meta>
  { nome: "bens-pessoa-sem-registro", url: primeiro("exe-"), metas: { "dados-bens": "br" }, simular: simularBens(), semPagina: [/Bens declarados/i] },
  // cidade do interior (CE): quem está no cargo e tem declaração, prefeito e vice primeiro e os vereadores em ordem alfabética, sem valor nem ordem de ricos
  { nome: "bens-cidade-ce", recorte: "#bens", url: "/cidade/abaiara-ce", metas: { "dados-bens": "ce" }, simular: simularBens({ ce: BENS_CE }),
    pagina: [/Bens declarados à Justiça Eleitoral/, /São 3 pessoas no cargo de Abaiara, em ordem alfabética/, /Na candidatura de 2024, declarou ao TSE bens que somam R\$\s175\.500,00, em 4 itens: imóveis R\$\s145\.000,00; veículos R\$\s24\.000,00; participações em empresas R\$\s6\.500,00\./,
      /Na candidatura de 2024, não declarou bens à Justiça Eleitoral\./, /Ver a declaração no TSE/, /Fonte: Tribunal Superior Eleitoral/], semBens: SEM_JULGAMENTO_BENS,
    depois: `(() => { const f = [], l = [...document.querySelectorAll("#bens .bens-lista li")]; if (l.length !== 3) return ["esperava 3 pessoas na lista de bens e achei " + l.length];
      const cargos = l.map((e) => e.querySelector(".bens__nome small").textContent); if (!/^Prefeito/.test(cargos[0]) || !/^Vice-prefeito/.test(cargos[1]) || !/^Vereador/.test(cargos[2])) f.push("a ordem tem de ser prefeito, vice e vereadores: " + cargos.join(" | "));
      const a = l[0].querySelector("a[href*='divulgacandcontas']"); if (!a || !/\\/NORDESTE\\/CE\\/2045202024\\/60002313505\\/2024\\/13013$/.test(a.href)) f.push("o link da declaração do prefeito não segue o modelo: " + (a && a.href));
      return f; })()` },
  { nome: "bens-cidade-es", url: "/cidade/afonso-claudio-es", metas: { "dados-bens": "es" }, simular: simularBens({ es: BENS_ES }),
    pagina: [/Bens declarados à Justiça Eleitoral/, /São 2 pessoas no cargo de Afonso Cláudio, em ordem alfabética/, /imóveis R\$\s310\.000,00/, /não declarou bens/] },
  { nome: "bens-cidade-sem-registro", url: "/cidade/acrelandia-ac", metas: { "dados-bens": "ce" }, simular: simularBens({ ce: BENS_CE }), semPagina: [/Bens declarados/i] },
  { nome: "cidade-interior-sem-bens", url: "/cidade/abaiara-ce", semPagina: [/Bens declarados/i, /Justiça Eleitoral/] },
  // ajuda de custo (paga de uma vez) fora do "por mês" e da comparação: quem tem poucos meses e a ajuda da posse não sobe no ranking só por ela.
  // Tiago Dimas (5 meses em 2025, ajuda de R$ 46.366 em set/2025) já foi o 9º de 554; André Abdon, o 1º. A largura de 900 px é a em que o
  // menu das seções do deputado não cabe: tem de ficar numa linha só, rolando para o lado, com o aviso de que há mais.
  { nome: "deputado-ajuda-de-custo-tiago-dimas", url: ENDERECOS["dep-143084"] ? `/${ENDERECOS["dep-143084"]}` : null, largura: 900,
    contem: [/Fora desta média: ajuda de custo de R\$ 46\.366, paga de uma vez em set\/2025\. Contando com ela, seriam R\$ [\d.]+ por mês/, /Pago de uma vez, fora da média por mês/i,
      /somaria R\$ 9\.273 por mês, bem mais do que pesaria em quem teve os 12 meses do ano/, /(?<![0-9])(?!(?:[1-9]|10)º de )[0-9]+º de [0-9]+ · /],
    semContem: [/(?<![0-9])9º de [0-9]+ · /],
    depois: `(() => {
      const f = [], proibidos = ["André Abdon", "Professora Marcivania", "Rafael Fera", "Fatima Pelaes", "Fabiano Cazeca", "Elmano Férrer", "Tiago Dimas"];
      const topo = document.querySelector("#ranking .rank-lista");
      if (!topo) return ["não achei a lista dos maiores no ranking"];
      const nomes = [...topo.querySelectorAll(".rank__nome")].map((e) => e.firstChild.textContent.trim());
      const subiu = nomes.filter((n) => proibidos.includes(n));
      if (subiu.length) f.push("entre os maiores custos por mês só por causa da ajuda de custo da posse: " + subiu.join(", "));
      return f;
    })()` },
  // topo escuro no computador de 1080 px: duas colunas (número e divisão à esquerda, contexto à direita) e a nota da ajuda de custo no pé; sem a posição (2 meses), o contexto só tem os salários mínimos
  { nome: "deputado-topo-1080", url: ENDERECOS["dep-143084"] ? `/${ENDERECOS["dep-143084"]}` : null, largura: 1080,
    contem: [/Equivale a \d+ salários mínimos por mês\s+\S*\d+%\s+vs\. mediana R\$ [0-9.]+/, /Comparado com os colegas/i, /Fora desta média: ajuda de custo de R\$ 46\.366/] },
  // larguras-limite do topo escuro (980 px é onde viram duas colunas; 1080 px é a do menu das seções): cada tipo de pessoa
  ...[["senador", "sen-", 980], ["ministro", "exe-", 980], ["governador", "gov-", 980], ["judiciario-pessoa", "jud-", 980], ["vereador-capital", "ver-", 1080], ["prefeitura", "pre-", 1080], ["deputado-estadual", "est-", 1080]]
    .map(([nome, prefixo, largura]) => ({ nome: `${nome}-topo-${largura}`, url: primeiro(prefixo), largura })),
  { nome: "deputado-topo-980", url: ENDERECOS["dep-143084"] ? `/${ENDERECOS["dep-143084"]}` : null, largura: 980, contem: [/Equivale a \d+ salários mínimos por mês/, /\d+º de \d+ · /] },
  // o MÊS da ajuda de custo vem do campo "aj" de dados.json (o mês de cada pagamento, como a folha registra); o site não estima mais (a estimativa
  // pelo mês a mês errava: Lafayette de Andrada recebeu em fev/2023 e a página dizia dezembro; Luiz Carlos Hauly, em jul/2023, e aparecia dezembro).
  // Sem "aj" na pessoa ou no período: "no período", sem mês. Vários pagamentos: os meses (ou "N pagamentos").
  { nome: "deputado-ajuda-mes-lafayette-fev-2023", url: ENDERECOS["dep-98057"] ? `/${ENDERECOS["dep-98057"]}?periodo=2023` : null,
    contem: [/Fora desta média: ajuda de custo de R\$ 39\.293, paga de uma vez em fev\/2023\./, /Paga de uma vez em fev\/2023: é o total do período/], semContem: [/dez\/2023/, /no período\./] },
  { nome: "deputado-ajuda-mes-hauly-jul-2023", url: ENDERECOS["dep-73778"] ? `/${ENDERECOS["dep-73778"]}?periodo=mandato` : null,
    contem: [/Fora desta média: ajuda de custo de R\$ 41\.651, paga de uma vez em jul\/2023\./], semContem: [/dez\/2023/, /no período\./] },
  { nome: "deputado-ajuda-mes-hauly-ano", url: ENDERECOS["dep-73778"] ? `/${ENDERECOS["dep-73778"]}?periodo=2023` : null,
    contem: [/Fora desta média: ajuda de custo de R\$ 41\.651, paga de uma vez em jul\/2023\./], semContem: [/dez\/2023/] },
  // dados simulados: sem "aj" (não diz o mês, nunca estima), dois pagamentos (lista os meses) e muitos pagamentos ("N pagamentos")
  ...[["sem-aj", (p) => { delete p.aj; }, [/paga de uma vez no período\./], [/paga de uma vez em [a-z]{3}\/20/i, /paga em [a-z]{3}\/20/i]],
    ["dois-pagamentos", (p) => { p.aj = { 2023: [[202302, 20000], [202307, 19293]], leg: [[202302, 20000], [202307, 19293]] }; }, [/paga em fev\/2023 e jul\/2023\./], [/no período\./]],
    ["cinco-pagamentos", (p) => { p.aj = { 2023: [202301, 202302, 202303, 202304, 202305].map((m) => [m, 7000]), leg: [] }; }, [/paga em 5 pagamentos\./], [/no período\./]]]
    .map(([nome, muda, contem, semContem]) => ({ nome: `deputado-ajuda-mes-simulado-${nome}`, url: ENDERECOS["dep-98057"] ? `/${ENDERECOS["dep-98057"]}?periodo=2023` : null,
      simular: (c) => { if (c !== "/dados/indice/dados.json" && c !== "/dados/dados.json") return null; const d = lerDados("dados.json"); muda(d.p.find((x) => x.id === "dep-98057")); return JSON.stringify(d); },
      contem: [/Fora desta média: ajuda de custo de R\$ 39\.293, /, ...contem], semContem })),
  { nome: "deputado-ajuda-de-custo-andre-abdon", url: ENDERECOS["dep-178831"] ? `/${ENDERECOS["dep-178831"]}` : null,
    contem: [/Fora desta média: ajuda de custo de R\$ 46\.366/, /Pago de uma vez, fora da média por mês/i], semContem: [/É o maior custo entre os deputados/, /(?<![0-9])1º de [0-9]+ · /] },
  // 2 meses de mandato: fora do ranking (mínimo de 3 meses), com a ajuda de custo à parte e sem posição
  { nome: "deputado-ajuda-de-custo-elmano-ferrer", url: ENDERECOS["dep-234406"] ? `/${ENDERECOS["dep-234406"]}` : null,
    contem: [/Fora desta média: ajuda de custo de R\$ 46\.366/, /Pago de uma vez, fora da média por mês/i], semContem: [/É o maior custo entre os deputados/, /Custa mais que \d+% dos deputados/] },
  // o 13º no contracheque é "média por mês" e diz a conta (total do período ÷ meses): conferido num deputado que recebeu 13º
  // presença e projetos (atividade.json): "X de Y", sem porcentagem; Câmara por dia de sessão e Senado por votação nominal, nunca juntos
  // fontes congeladas (situacao.json): a página diz "Folha até mar/2026: a fonte parou de publicar" (PA e RJ: governador; Campo Grande: Prefeitura)
  { nome: "governador-pa-congelada", url: primeiro("gov-pa-"), pagina: [/folha até mar\/2026: a fonte parou de publicar/i] },
  { nome: "estado-pa-congelada", url: "/governador/pa", pagina: [/folha até mar\/2026: a fonte parou de publicar/i] },
  { nome: "estado-rj-congelada", url: "/governador/rj", pagina: [/folha até mar\/2026: a fonte parou de publicar/i] },
  { nome: "cidade-campo-grande-congelada", url: "/cidade/campo-grande-ms", pagina: [/folha até fev\/2026: a fonte parou de publicar/i] },
  { nome: "governador-sp-sem-congelada", url: primeiro("gov-sp-"), semPagina: [/a fonte parou de publicar/i] },
  // capital sem reserva ligada: a fonte própria, sem o aviso do tribunal
  { nome: "cidade-fortaleza-fonte-propria", url: "/cidade/fortaleza-ce", semPagina: [/dados do tce-ce/i] },
  // reserva ligada (simulada): o tribunal no lugar da fonte própria, com o aviso; sem misturar valor por pessoa e por cargo
  { nome: "reserva-fortaleza-pessoa", url: "/cidade/fortaleza-ce", simular: simularReservas(["vereadores/fortaleza", "prefeituras/fortaleza"]),
    pagina: [/dados do tce-ce\./i, /pessoa por pessoa/i, /valor típico de um vereador/i], semPagina: [/total pago ao cargo/i, /em média, por vereador/i] },
  { nome: "reserva-recife-cargo", url: "/cidade/recife-pe", simular: simularReservas(["vereadores/recife"], true),
    pagina: [/dados do tce-pe\./i, /não é o salário de cada pessoa/i, /em média, por vereador/i, /total pago ao cargo/i], semPagina: [/valor típico de um vereador/i], sem: [/ganha mais que/i, /passa do teto/i] },
  { nome: "reserva-vitoria-prefeitura-cargo", url: "/cidade/vitoria-es", simular: simularReservas(["prefeituras/vitoria"]),
    pagina: [/dados do tce-es\./i, /quanto a prefeitura paga ao prefeito e ao vice/i, /não é o salário de cada pessoa/i], semPagina: [/quanto recebem o prefeito, os secretários/i] },
  { nome: "deputado-atividade", url: ENDERECOS["dep-74856"] ? `/${ENDERECOS["dep-74856"]}` : null,
    atividade: [/teve presença em \d+ dos \d+ dias com sessão deliberativa no plenário em que estava no mandato/i, /ausências justificadas: \d+/i, /homenagens e datas/i, /viraram norma/i, /como contamos|homenagem ou data: projeto cuja ementa/i],
    semAtividade: [/%/, /votações nominais/i, /mais produtiv|menos produtiv/i] },
  { nome: "senador-atividade", url: ENDERECOS["sen-5672"] ? `/${ENDERECOS["sen-5672"]}` : null,
    atividade: [/das \d+ votações nominais no plenário em que estava no mandato: presente em \d+/i, /o senado não publica a presença por sessão/i, /na pec, o senado lista como autores todos os que assinaram/i],
    semAtividade: [/%/, /dias com sessão deliberativa/i, /mais produtiv|menos produtiv/i] },
  { nome: "deputado-13o", url: primeiroCom13("dep-"), contem: [/13º salário \(média por mês\)/i, /R\$ [\d.]+ de 13º pagos .*divididos pelos \d+ meses com pagamento/i, /para somar com o resto do mês/i] },
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
  // ES, PE e RJ: o Tribunal de Contas só publica o total pago ao cargo (e quantas pessoas): sempre "em média", nunca o salário
  // de alguém, sem "passa do teto" nem "ganha mais que X%"
  { nome: "cidade-es-vitoria", url: "/cidade/vitoria-es", ter: [["#cidade .pessoa-chip--fixo", 15]], texto: [/em média, por vereador/i, /total pago ao cargo/i], sem: [/passa do teto/i, /ganha mais que/i] },
  { nome: "cidade-es-cariacica", url: "/cidade/cariacica-es", ter: [["#cidade .pessoa-chip--fixo", 15], ["#prefeitura .folha-linha", 2]], texto: [/23 pessoas no cargo de vereador/i, /não representa um vereador/i], sem: [/em média, por vereador/i, /passa do teto/i, /ganha mais que/i] },
  { nome: "cidade-pe-abreu-e-lima", url: "/cidade/abreu-e-lima-pe", ter: [["#cidade .pessoa-chip--fixo", 10], ["#prefeitura .folha-linha", 2]], texto: [/em média, por vereador/i, /13 pessoas no cargo de vereador/i, /R\$ 26\.000/], sem: [/passa do teto/i, /ganha mais que/i] },
  { nome: "cidade-pe-aguas-belas", url: "/cidade/aguas-belas-pe", ter: [["#cidade .pessoa-chip--fixo", 10]], texto: [/presidente da Câmara/i, /13 pessoas/i], sem: [/passa do teto/i, /ganha mais que/i] },
  { nome: "cidade-rj-laje-do-muriae", url: "/cidade/laje-do-muriae-rj", ter: [["#cidade .pessoa-chip--fixo", 5]], texto: [/12 pessoas como agente político/i, /a fonte não tem os nomes/i], sem: [/em média, por/i, /passa do teto/i, /ganha mais que/i] },
  { nome: "governador-com-viagens", url: ENDERECOS["gov-mg-mateus-simoes"] ? `/${ENDERECOS["gov-mg-mateus-simoes"]}` : null, ter: [["#viagens h2", 1], ["#viagens .estatistica", 2], ["#viagens details table", 1]] },
  // governador em exercício pago pelo tribunal (RJ, e.ot em governadores.json): "recebe pelo Tribunal de Justiça, onde é desembargador", nunca "salário de
  // governador"; só os meses no governo, com a fonte de cada mês, o crédito do DadosJusBr (CC BY 4.0) e as diárias à parte (fora do recebido)
  { nome: "governador-rj-pelo-tribunal", url: ENDERECOS["gov-rj-ricardo-couto"] ? `/${ENDERECOS["gov-rj-ricardo-couto"]}` : null,
    pagina: [/Recebe pelo Tribunal de Justiça, onde é desembargador/, /Não recebe o subsídio de governador: recebe pelo Tribunal de Justiça/, /licença CC BY 4\.0/, /R\$\s[0-9.]+,[0-9]{2} brutos[^.]*antes dos descontos/, /Diárias, à parte/, /Dados do mês \(zip\)/],
    semPagina: [/Nenhum pagamento na folha/, /Sem pagamentos registrados/, /(recebe|ganha|salário d[eo] governador:?)\sR\$/i, /Folha até [a-z]{3}\/20[0-9]{2}: a fonte parou de publicar/],
    ter: [["#contracheque .tj-mes", 1]],
    depois: `(() => { const f = [], num = (t) => Number(t.replace(/[^0-9,]/g, "").replace(",", ".")); const cartoes = [...document.querySelectorAll(".tj-mes")];
      if (!cartoes.length) return ["não achei os cartões do mês"];
      for (const c of cartoes) { const rec = num(c.querySelector(".tj-mes__recebido strong").textContent), soma = [...c.querySelectorAll(".tj-mes__partes dd")].reduce((a, d) => a + num(d.textContent), 0);
        if (Math.abs(rec - soma) > 0.05) f.push(c.querySelector(".tj-mes__mes").textContent + ": o recebido (" + rec + ") não é a soma das partes (" + soma.toFixed(2) + "); as diárias ficam fora"); }
      return f; })()` },
  { nome: "estado-rj-pelo-tribunal", url: "/governador/rj", ter: [["#governador .tj-mes", 1]],
    pagina: [/Recebe pelo Tribunal de Justiça, onde é desembargador/, /o governador em exercício não recebe esse valor/, /licença CC BY 4\.0/, /Folha até mar\/2026: a fonte parou de publicar/], semPagina: [/Ganha mais que/] },
  { nome: "estado-sp-sem-tribunal", url: "/governador/sp", semPagina: [/Recebe pelo Tribunal de Justiça/, /não recebe esse valor/] },
  { nome: "governador-ap-fonte-imprensa", url: "/governador/ap", simular: simularImprensa(IMPRENSA_AP),
    pagina: [/Secretário de Estado: notícia \(Diário do Amapá\); a norma, Lei nº 2\.799\/2022, não foi localizada\./, /Vice-governador: notícia \(jornal\.exemplo\.com\.br\); a norma não foi localizada\./, /Ver\sa\snotícia/, /R\$\s18\.000,00/],
    semPagina: [/a norma, valor informado/, /a norma, Lei nº 2\.799, de 30\/12\/2022/],
    depois: `(() => { const f = [], t = [...document.querySelectorAll("details.tabela")].map((d) => d.textContent).join(" ");
      if (!/notícia \\(Diário do Amapá\\); a norma, Lei nº 2\\.799\\/2022, não foi localizada/.test(t)) f.push("a tabela dos secretários não traz a fonte como notícia");
      const a = [...document.querySelectorAll("a")].filter((x) => /diariodoamapa\\.com\\.br/.test(x.href));
      if (a.length < 2 || a.some((x) => x.target !== "_blank" || !/notícia/.test(x.textContent))) f.push("o link do jornal falta, não abre em outra aba ou não diz que é notícia");
      return f; })()` },
  // link de órgão público, mesmo marcado como imprensa: não vira "notícia"
  { nome: "governador-mt-imprensa-com-link-oficial", url: "/governador/mt",
    simular: simularImprensa((es) => { const e = es.find((x) => x.uf === "MT"); e.vv = [32353.46, 202501, "imprensa", "Lei nº 10.247/2014 fixa o MESMO subsídio para Governador e Vice (+ RGA)", "https://www.al.mt.gov.br/norma-juridica/lei-10247"]; }),
    semPagina: [/notícia \(/, /não foi localizada/],
    depois: `(() => (document.body.textContent.includes("notícia (") ? ["link do governo mostrado como notícia"] : []))()` },
  // o valor do próprio governador, só pela imprensa: o bloco "De onde vem o valor" diz o mesmo
  { nome: "governador-fonte-imprensa-do-governador", url: "/governador/sp",
    simular: simularImprensa((es) => { const e = es.find((x) => x.uf === "SP"); e.v = [e.v[0], e.v[1], "imprensa", "Lei nº 1.234, de 05/03/2020", "https://jornal.exemplo.com.br/lei"]; }),
    pagina: [/De onde vem o valor: Só pela imprensa/, /notícia \(jornal\.exemplo\.com\.br\); a norma, Lei nº 1\.234\/2020, não foi localizada\./, /Ver\sa\snotícia/] },
  // verba por vigência: sem o campo e com mudança só na virada do ano o texto não muda; com mudança em setembro, cada valor com o período
  { nome: "verba-sem-vigencia-vereador", url: VER_SP ? `/${ENDERECOS[VER_SP]}` : null, simular: simularVerba(VERBA_ANOS, null), pagina: VERBA_TEXTO_ANOS, semPagina: [/desde jan\/20/, /por mês de jan a/] },
  { nome: "verba-sem-vigencia-cidade", url: "/cidade/sao-paulo-sp", simular: simularVerba(VERBA_ANOS, null), pagina: [/por mês em 2025 \(mediana\), de até R\$\s34\.706(?! de| e)/], semPagina: [/desde jan\/20/] },
  { nome: "verba-vigencia-na-virada-do-ano", url: VER_SP ? `/${ENDERECOS[VER_SP]}` : null, simular: simularVerba(VERBA_ANOS, [[202501, 34706.25], [202601, 36018.75]]), pagina: VERBA_TEXTO_ANOS, semPagina: [/desde jan\/20/, /por mês de jan a/] },
  { nome: "verba-vigencia-na-virada-do-ano-cidade", url: "/cidade/sao-paulo-sp", simular: simularVerba(VERBA_ANOS, [[202501, 34706.25], [202601, 36018.75]]), pagina: [/por mês em 2025 \(mediana\), de até R\$\s34\.706(?! de| e)/], semPagina: [/desde jan\/20/] },
  { nome: "verba-vigencia-em-setembro", url: VER_SP ? `/${ENDERECOS[VER_SP]}` : null, simular: simularVerba({ 2025: 120, 2026: 120 }, [[202501, 100], [202509, 120]]),
    pagina: [/Cada vereador pode gastar até R\$\s100 por mês de jan a ago\/2025 e R\$\s120 desde set\/2025\./], semPagina: [/R\$\s120 em 2025/, /por mês\. por mês/] },
  { nome: "verba-vigencia-em-setembro-cidade", url: "/cidade/sao-paulo-sp", simular: simularVerba({ 2025: 120, 2026: 120 }, [[202501, 100], [202509, 120]]),
    pagina: [/por mês em 2025 \(mediana\), de até R\$\s100 de jan a ago\/2025 e R\$\s120 desde set\/2025/] },
  { nome: "verba-vigencia-tres-valores", url: VER_SP ? `/${ENDERECOS[VER_SP]}` : null, simular: simularVerba({ 2025: 120, 2026: 130 }, [[202501, 100], [202509, 120], [202601, 130]]),
    pagina: [/Cada vereador pode gastar até R\$\s100 por mês de jan a ago\/2025, R\$\s120 de set a dez\/2025 e R\$\s130 desde jan\/2026\./] },
  // mudança em 2026 (e não em 2025): o texto de 2025 na página da cidade não leva o período
  { nome: "verba-vigencia-so-em-2026-cidade", url: "/cidade/sao-paulo-sp", simular: simularVerba({ 2025: 100, 2026: 120 }, [[202501, 100], [202603, 120]]),
    pagina: [/por mês em 2025 \(mediana\), de até R\$\s100(?! de| e)/], semPagina: [/de jan a/] },
  { nome: "governador-sem-viagens", url: ENDERECOS["gov-sp-tarcisio-de-freitas"] ? `/${ENDERECOS["gov-sp-tarcisio-de-freitas"]}` : null, ter: [["#viagens h2", 1]] },
  { nome: "estado", url: "/governador/sp", ter: [["#governador", 1]] },
  { nome: "estado-assembleia", url: "/governador/go", ter: [["#governador", 1], ["#assembleia", 1]] },
  { nome: "judiciario", url: "/judiciario", ter: [["#judiciario", 1]] },
  { nome: "indice", url: "/indice", ter: [["#indice", 1]] },
  { nome: "dados-abertos", url: "/dados-abertos", ter: [[".copias li", 5], ["#dados-abertos tbody tr", 10]] },
  { nome: "correcoes", url: "/correcoes", ter: [["ol.correcoes > li", 1], ["ol.correcoes a[href='/cidade/sao-paulo-sp']", 1]] },
  // correções que apontam para uma página: o aviso "esta página já foi corrigida" no fim da página (cidade pelo código IBGE, pessoa pelo id) e nenhum aviso onde não há
  { nome: "cidade-com-correcao", url: "/cidade/sao-paulo-sp", pagina: [/Esta página já foi corrigida\./, /Vereadores de São Paulo: a verba do gabinete por mês em 2026/, /04\/10\/2026/], ter: [["#correcoes-desta-pagina:not([hidden]) li", 1]] },
  { nome: "senador-com-correcao", url: ENDERECOS["sen-4605"] ? `/${ENDERECOS["sen-4605"]}` : null, pagina: [/Esta página já foi corrigida\./, /Ajuda de custo: o mês do pagamento na página de senador de Flávio Dino/] },
  { nome: "cidade-sem-correcao", url: "/cidade/fortaleza-ce", semPagina: [/Esta página já foi corrigida/], ter: [["#erro", 1]] },
  { nome: "sobre", url: "/sobre", ter: [["#sobre h2", 5], ["#sobre a[href^='mailto:']", 1], ["#sobre a[href='/imprensa']", 1]] },
  // "Para a imprensa": curta e neutra; o método com os links das páginas de transparência, a licença e o modelo de citação, o contato; sem nome de pessoa
  // e sem link para o usuário do GitHub (o código é apontado por /dados-abertos)
  { nome: "imprensa", url: "/imprensa", ter: [["#imprensa h2", 5], ["#imprensa a[href='/sobre']", 1], ["#imprensa a[href='/atualizacao']", 1], ["#imprensa a[href='/correcoes']", 1], ["#imprensa a[href='/dados-abertos']", 1], ["#imprensa a[href^='mailto:contato@contasdopoder.com']", 1]],
    pagina: [/Para a imprensa/, /sem adjetivos, sem juízo e sem acusações/, /CC BY 4\.0/, /Contas do Poder \(contasdopoder\.com\), a partir de <fonte oficial>, consultado em <data>\./, /Erro nosso é corrigido e registrado/, /contato@contasdopoder\.com/],
    semPagina: [/Laloux|Jean-François|jflaloux|github\.com/i] },
  { nome: "atualizacao", url: "/atualizacao", ter: [["#atualizacao tbody tr", 50], ["#atualizacao .estatistica", 2]] }, // desde 07/10/2026 o arquivo real tem "rodada": o bloco "O que mudou nesta rodada" aparece, e os testes de rodada (simularRodada) cobrem o texto
  // com rodada anterior: o texto neutro, os nomes das fontes como links para a linha da lista, e nada de "problema" para quem só tem atraso da fonte
  { nome: "atualizacao-rodada", url: "/atualizacao", ter: [["#rodada li", 3], ["#rodada a[href^='#fonte-']", 3]],
    simular: FONTES_SIT.length > 4 ? simularRodada({ semana: "2026-10-06", anterior: "2026-09-29", quebrou: [FONTES_SIT[1].id, FONTES_SIT[2].id], voltou: [FONTES_SIT[3].id], continua: [] }) : null,
    pagina: FONTES_SIT.length > 4 ? [/Rodada de 06\/10\/2026, comparada com a de 29\/09\/2026:/, /2 fontes passaram a ter problema \(/, new RegExp(`${reEsc(FONTES_SIT[1].nome)} e ${reEsc(FONTES_SIT[2].nome)}`),
      /1 voltou \(/, /nenhuma continua com problema/, /O atraso da própria fonte e as fontes congeladas não contam/] : [],
    depois: `(async () => { const f = [], esp = (ms) => new Promise((r) => setTimeout(r, ms));
      const links = [...document.querySelectorAll("#rodada a[href^='#fonte-']")];
      for (const a of links) if (!document.getElementById(a.getAttribute("href").slice(1))) f.push("o link " + a.getAttribute("href") + " não leva a nenhuma linha da lista");
      const ids = [...document.querySelectorAll("[id^='fonte-']")].map((e) => e.id); if (new Set(ids).size !== ids.length) f.push("ids de fonte repetidos na página");
      if (links[0]) { links[0].click(); await esp(700); const alvo = document.getElementById(links[0].getAttribute("href").slice(1)), b = alvo && alvo.getBoundingClientRect();
        if (!alvo || b.bottom < 0 || b.top > innerHeight) f.push("o link da rodada não levou até a linha da fonte"); if (location.pathname !== "/atualizacao") f.push("o link da rodada saiu da página"); }
      return f; })()` },
  { nome: "atualizacao-rodada-sem-mudanca", url: "/atualizacao", simular: simularRodada({ semana: "2026-10-06", anterior: "2026-09-29", quebrou: [], voltou: [], continua: [] }),
    pagina: [/Rodada de 06\/10\/2026: nenhuma mudança desde a de 29\/09\/2026\./], semPagina: [/passaram a ter problema/] },
  // o servidor (como o Cloudflare Pages) responde 404 com o 404.html: a página avisa, sai do índice do Google (noindex) e mostra os destaques
  // ---- lote 2 (07/10/2026): carga sob demanda, tema, pular, baixar CSV, dados estruturados, guia (passo 3), cidades, cargos do estado, impressão
  // página de deputado: só o essencial de saída; Assembleias, Câmaras, Judiciário e governadores vêm ao buscar (ou ao chegar perto do ranking)
  { nome: "carga-sob-demanda", acao: true, url: primeiro("dep-"), semRolar: true, depois: `(async () => {
      const f = [], esp = (ms) => new Promise((r) => setTimeout(r, ms));
      const lidos = () => performance.getEntriesByType("resource").map((e) => new URL(e.name).pathname);
      const resto = ["/dados/indice/assembleias.json", "/dados/indice/camaras.json", "/dados/indice/judiciario.json", "/dados/indice/governadores-pessoas.json"];
      if (!document.querySelector('meta[name="dados-leve"]')) f.push("a página de deputado não tem <meta name=dados-leve>");
      const ja = resto.filter((a) => lidos().includes(a)); if (ja.length) f.push("baixou de saída o que devia vir sob demanda: " + ja.join(", "));
      const campo = document.querySelector("#busca-topo");
      document.querySelector("#abrir-busca").click(); await esp(200); campo.focus(); await esp(2500);
      const falta = resto.filter((a) => !lidos().includes(a)); if (falta.length) f.push("a busca não trouxe: " + falta.join(", "));
      campo.value = "Silva"; campo.dispatchEvent(new Event("input", { bubbles: true })); await esp(300);
      const sug = document.querySelector("#sugestoes-topo").innerText;
      if (!/Deputad[oa] estadual|Vereador|Governador|Ministro/.test(sug) && !/Deputad[oa] federal|Senador/.test(sug)) f.push("a busca não mostrou ninguém");
      document.querySelector("#abrir-busca").click();
      const quem = [...document.querySelectorAll("#ranking .grupo-pilulas button")].map((b) => b.textContent);
      if (!quem.some((t) => /estaduais/.test(t))) f.push("o ranking não ganhou o grupo dos deputados estaduais depois de carregar tudo: " + quem.join("|"));
      return f; })()` },
  { nome: "tema-e-pular", acao: true, url: "/", depois: `(async () => {
      const f = [], esp = (ms) => new Promise((r) => setTimeout(r, ms)), raiz = document.documentElement;
      const b = [...document.querySelectorAll("[data-tema-botao]")].pop(); if (!b) return ["sem botão de tema"];
      const antes = b.getAttribute("aria-label"); b.click(); await esp(100);
      const t1 = raiz.dataset.theme; if (t1 !== "light" && t1 !== "dark") f.push("o botão não pôs o tema");
      if (localStorage.getItem("tema") !== t1) f.push("o tema escolhido não ficou guardado");
      if (b.getAttribute("aria-label") === antes) f.push("o nome do botão não mudou");
      b.click(); await esp(100); if (raiz.dataset.theme === t1) f.push("o segundo clique não trocou de novo");
      localStorage.removeItem("tema"); raiz.removeAttribute("data-theme");
      const p = document.querySelector("#pular"); if (!p) f.push("sem link de pular"); else { p.click(); await esp(100); if (document.activeElement.id !== "app") f.push("o link de pular não levou o foco ao conteúdo"); }
      return f; })()` },
  // busca sem resultado: ao Analytics vai só o que tem cara de nome (termoMedivel, no app.js). Em localhost o gtag não existe: o teste põe um gravador no lugar.
  // Os termos têm "zzqx" para a busca não achar ninguém; cada termo espera os 1,5 s da pausa antes do envio.
  { nome: "busca-sem-resultado", acao: true, url: "/", depois: `(async () => {
      const f = [], esp = (ms) => new Promise((r) => setTimeout(r, ms)), enviados = [];
      window.gtag = (...a) => { if (a[0] === "event" && a[1] === "busca_sem_resultado") enviados.push(a[2].termo); };
      const campo = document.querySelector("#busca"), sug = document.querySelector("#sugestoes"); if (!campo || !sug) return ["sem o campo de busca da página inicial"];
      campo.focus(); await esp(2500);
      const digitar = async (v, vai) => {
        campo.value = v; campo.dispatchEvent(new Event("input", { bubbles: true })); await esp(1700);
        if (!/Ninguém encontrado/.test(sug.innerText)) f.push("a busca achou alguém com " + JSON.stringify(v) + ": o caso não vale");
        campo.value = ""; campo.dispatchEvent(new Event("input", { bubbles: true }));
      };
      await digitar("Zzqx Kwvy");                                   // vai: sem acento, minúsculas
      await digitar("ZZQX   kwvy");                                 // o mesmo termo de novo: uma vez só
      await digitar("Zzqx d'Ávila");                                // apóstrofo e acento
      await digitar("Dr. Zzqx João");                               // ponto
      await digitar("Zzqx 12 34 56 78 90 1");                       // dígitos em grupos de 1 ou 2 (o filtro antigo deixava passar)
      await digitar("12 34 56 78 90 1");
      await digitar("123.456.789-00");
      await digitar("https://zzqx.exemplo/a");                      // endereço de site
      await digitar("zzqx@exemplo.com");
      await digitar("zzqx 13");
      await digitar("zzqx rua das flores quinhentos e vinte tres apto trinta"); // texto longo colado: some, não é cortado
      const esperado = ["zzqx kwvy", "zzqx d'avila", "dr. zzqx joao"];
      if (JSON.stringify(enviados) !== JSON.stringify(esperado)) f.push("foram ao Analytics " + JSON.stringify(enviados) + " e deviam ir " + JSON.stringify(esperado));
      return f; })()` },
  { nome: "baixar-csv", acao: true, url: ENDERECOS["dep-74856"] ? `/${ENDERECOS["dep-74856"]}` : null, depois: `(async () => {
      const f = [], esp = (ms) => new Promise((r) => setTimeout(r, ms));
      const guardados = []; URL.createObjectURL = (bl) => { guardados.push(bl); return "blob:teste"; };
      HTMLAnchorElement.prototype.click = function () { if (this.hasAttribute("download")) this.dataset.baixou = "1"; };
      const bt = [...document.querySelectorAll("#baixar button")].find((x) => /Mês a mês/.test(x.textContent)); if (!bt) return ["sem o botão Mês a mês (CSV)"];
      bt.click(); await esp(200);
      if (!guardados.length) return ["o clique não gerou arquivo"];
      const t = await guardados[0].text(), ls = t.replace(/^\\ufeff/, "").split("\\r\\n").filter(Boolean);
      if (!/^pessoa,cargo,mes,vai_para_o_bolso_reais,gastos_do_mandato_reais,equipe_do_gabinete_reais,pessoas_na_equipe,parte_rateada_do_ano_reais,fonte$/.test(ls[0])) f.push("cabeçalho do CSV: " + ls[0]);
      if (ls.length < 13) f.push("o CSV tem poucas linhas: " + ls.length);
      if (!/,https?:\\/\\//.test(ls[1] || "")) f.push("a linha do CSV não traz o link da fonte: " + ls[1]);
      if (!/,\\d{4}-\\d{2},\\d+\\.\\d{2},/.test(ls[1] || "")) f.push("a linha do CSV não tem mês e valor com 2 casas: " + ls[1]);
      if (/\\d{3}\\.?\\d{3}\\.?\\d{3}-?\\d{2}/.test(t.replace(/\\d+\\.\\d{2}/g, ""))) f.push("o CSV parece ter CPF");
      const lk = document.querySelector('#baixar a[download]'); if (!lk || !/^\\/dados\\/pessoa\\/[a-z0-9-]+\\.json$/.test(lk.getAttribute("href"))) f.push("sem o link do arquivo completo (JSON)");
      const rk = [...document.querySelectorAll("#ranking button")].find((x) => /Baixar esta lista/.test(x.textContent)); if (!rk) f.push("sem o botão de baixar o ranking");
      else { rk.click(); await esp(200); const r = await guardados[guardados.length - 1].text(); if (!/^\\ufeff?posicao,nome,cargo,/.test(r)) f.push("cabeçalho do CSV do ranking: " + r.slice(0, 60)); }
      return f; })()` },
  // dados estruturados: JSON válido, neutro (sem valor em reais) e do tipo certo
  { nome: "json-ld", url: primeiro("dep-"), depois: `(() => { const f = [], ls = [...document.querySelectorAll('script[type="application/ld+json"]')].map((s) => { try { return JSON.parse(s.textContent); } catch (e) { f.push("JSON-LD inválido"); return {}; } });
      const w = ls.find((x) => x["@type"] === "WebPage"); if (!w) return ["sem WebPage"]; if (!w.about || w.about["@type"] !== "Person" || !w.about.name) f.push("o WebPage não diz de quem é");
      if (/R\\$|[0-9]/.test(JSON.stringify(w.about))) f.push("o about do JSON-LD tem valor ou número: tem de ser neutro");
      if (/aggregateRating|review|rating|award|salary|baseSalary|reviewRating/i.test(JSON.stringify(ls))) f.push("o JSON-LD tem avaliação ou salário: tem de ser neutro"); return f; })()` },
  { nome: "json-ld-dataset", url: "/dados-abertos", depois: `(() => { const f = [], ls = [...document.querySelectorAll('script[type="application/ld+json"]')].map((s) => JSON.parse(s.textContent));
      const d = ls.find((x) => x["@type"] === "Dataset"); if (!d) return ["sem Dataset"]; if (!/creativecommons.org\\/licenses\\/by\\/4.0/.test(d.license || "")) f.push("sem a licença CC BY 4.0");
      if (!(d.distribution || []).length || !d.distribution.every((x) => x.contentUrl && x.sha256)) f.push("a distribuição está incompleta"); return f; })()` },
  { nome: "guia-passo-3-cidade", acao: true, url: "/", depois: `(async () => {
      const f = [], esp = (ms) => new Promise((r) => setTimeout(r, ms));
      document.querySelector("#abrir-guia").click(); await esp(300);
      [...document.querySelectorAll("#guia .ufs button")].find((b) => b.textContent === "SP").click(); await esp(300);
      const c = document.querySelector("#guia-cidade"); if (!c) return ["sem o campo da cidade no passo 2"];
      c.focus(); await esp(1500); c.value = "campin"; c.dispatchEvent(new Event("input", { bubbles: true })); await esp(300);
      const o = [...document.querySelectorAll("#guia .guia__cidades button")]; if (!o.length || !/Campinas/.test(o[0].innerText)) return ["a lista de cidades não achou Campinas: " + o.map((x) => x.innerText).join("|")];
      o[0].click(); await esp(300); const d = document.querySelector("#guia").innerText;
      if (!/passo 3 de 3/i.test(d)) f.push("não está no passo 3"); if (!/Câmara Municipal de Campinas/.test(d)) f.push("sem a Câmara da cidade");
      if (!/Governador|Governo/.test(d)) f.push("sem o governador do estado");
      const lado = [...document.querySelectorAll("#guia *")].filter((e) => e.clientWidth > 0 && e.scrollWidth > e.clientWidth + 1).length; if (lado) f.push("rola para o lado no passo 3");
      return f; })()` },
  { nome: "cidades-ordenar-filtrar", acao: true, url: "/", depois: `(async () => {
      const f = [], esp = (ms) => new Promise((r) => setTimeout(r, ms)); await esp(800);
      const bt = [...document.querySelectorAll("#cidades button")].find((x) => /Ver as \\d+ cidades/.test(x.textContent)); if (!bt) return ["sem o botão Ver as N cidades"];
      bt.click(); await esp(300);
      const o = document.querySelector("#ordem-cidades"), fi = document.querySelector("#filtro-cidades"); if (!o || !fi) return ["sem os controles de ordem e filtro"];
      o.value = "pop"; o.dispatchEvent(new Event("change", { bubbles: true })); await esp(200);
      const nomes = () => [...document.querySelectorAll("#cidades .rank-lista .rank__nome")].map((e) => e.firstChild.textContent.trim());
      if (nomes()[0] !== "São Paulo") f.push("ordenada por habitantes, a primeira devia ser São Paulo: " + nomes()[0]);
      o.value = "nome"; o.dispatchEvent(new Event("change", { bubbles: true })); await esp(200);
      const n = nomes(); if (n.slice().sort((a, b) => a.localeCompare(b, "pt-BR")).join() !== n.join()) f.push("a ordem por nome não está em ordem alfabética");
      fi.value = "campinas"; fi.dispatchEvent(new Event("input", { bubbles: true })); await esp(200);
      if (!nomes().length || !nomes().every((x) => /campinas/i.test(x))) f.push("o filtro por nome não filtrou: " + nomes().slice(0, 3));
      if (document.activeElement !== fi && document.activeElement !== document.body) { /* o foco fica no campo ou sai sozinho */ }
      if (![...document.querySelectorAll("#cidades button")].some((x) => /Baixar esta lista/.test(x.textContent))) f.push("sem o botão de baixar a lista");
      return f; })()` },
  { nome: "estado-cargos", url: "/governador/sp", depois: `(() => { const f = [], t = document.querySelector("#cargos-estado table"); if (!t) return ["sem a tabela dos salários dos cargos"];
      const ls = [...t.querySelectorAll("tbody tr")]; if (ls.length < 3) f.push("poucas linhas: " + ls.length);
      const v = ls.map((r) => Number(r.children[1].innerText.replace(/[^0-9,]/g, "").replace(",", ".").slice(0, 12)));
      if (v.some((x, i) => i && x > v[i - 1])) f.push("não está do maior para o menor: " + v.join(" "));
      ls.forEach((r) => { if (!r.children[2].querySelector("a")) f.push("linha sem link de fonte: " + r.children[0].innerText); });
      if (/ruim|bom\\b|abusiv|absurd/i.test(t.innerText)) f.push("juízo de valor na tabela"); return f; })()` },
  { nome: "impressao-abre-os-blocos", acao: true, url: primeiro("dep-"), depois: `(async () => { const f = [], esp = (ms) => new Promise((r) => setTimeout(r, ms));
      const fechados = () => document.querySelectorAll("#app details:not([open])").length; document.querySelectorAll("#app details").forEach((d) => { d.open = false; });
      const n = fechados(); if (!n) return ["nenhum bloco recolhido para o teste"];
      window.dispatchEvent(new Event("beforeprint")); await esp(100); if (fechados()) f.push("a impressão não abriu todos os blocos");
      window.dispatchEvent(new Event("afterprint")); await esp(100); if (fechados() !== n) f.push("depois de imprimir, os blocos não voltaram ao que eram"); return f; })()` },
  // /como-calculamos: só existe quando o texto foi revisado ("publicar": true em site/como-calculamos.json); sem ela, o teste não roda
  { nome: "como-calculamos", url: fs.existsSync(path.join(PUBLICAR, "como-calculamos.html")) ? "/como-calculamos" : null,
    pagina: [/Em uma frase/, /Glossário/, /Abate-teto/, /Mediana/, /Em salários mínimos/], semPagina: [/\*\*/, /\]\(/], ter: [["#como-calculamos h2", 8], ["#como-calculamos strong", 10]],
    depois: `(() => { const f = [], t = document.title; if (!/^Como calculamos \\| Contas do Poder$/.test(t)) f.push("título: " + t);
      const ids = new Set([...document.querySelectorAll("[id]")].map((e) => e.id));
      document.querySelectorAll("#como-calculamos a[href^='/']").forEach((a) => { if (/^\\/#/.test(a.getAttribute("href"))) return; if (!["/indice", "/atualizacao", "/correcoes"].includes(a.getAttribute("href"))) f.push("link interno desconhecido: " + a.getAttribute("href")); });
      if (/R\\$ ?[0-9]+[.,][0-9]{3}[.,][0-9]{2}.*(maior|menor|melhor|pior)/i.test(document.querySelector("#como-calculamos").innerText)) f.push("juízo ao lado de valor");
      return f; })()` },
  { nome: "endereco-inexistente", url: "/pagina-que-nao-existe", falhasEsperadas: ["/pagina-que-nao-existe"], pagina: [/Não achamos esta página/],
    depois: `(async () => { const f = []; const m = document.querySelector('meta[name="robots"]');
      if (!m || !/noindex/.test(m.content)) f.push("a página de endereço inexistente não tem noindex");
      const r = await fetch("/pagina-que-nao-existe", { cache: "no-store" }); if (r.status !== 404) f.push("o servidor respondeu " + r.status + " a um endereço inexistente (esperado 404)");
      const h = await fetch("/", { cache: "no-store" }); if (h.status !== 200) f.push("a página inicial respondeu " + h.status);
      return f; })()` },
].filter((p) => p.url);

const TODOS_PERFIS = [
  { nome: "celular-claro", largura: 390, altura: 844, mobile: true, escala: 2, tema: "light" },
  { nome: "computador-escuro", largura: 1280, altura: 800, mobile: false, escala: 1, tema: "dark" },
  { nome: "celular-escuro", largura: 390, altura: 844, mobile: true, escala: 2, tema: "dark" },
  { nome: "computador-claro", largura: 1280, altura: 800, mobile: false, escala: 1, tema: "light" },
];
const PERFIS = arg("completo") ? TODOS_PERFIS : TODOS_PERFIS.slice(0, 2);
// Modo rápido: a suíte completa passou de 60 minutos (mais de 90 tipos de página em 4 perfis). No meio do trabalho, --rapido roda uma página de cada
// tipo e --mudou acrescenta as páginas dos assuntos que o git diff toca. GRUPOS: quando o diff (as linhas mudadas, ou o nome do arquivo) casa com
// "quando", entram as páginas de teste cujo nome casa com "paginas". Assunto novo no site = uma linha aqui.
const RAPIDO = ["inicio", "deputado-federal", "senador", "ministro", "governador", "estado", "cidade-capital", "cidade-interior", "atualizacao", "judiciario", "indice", "dados-abertos", "sobre", "correcoes", "deputado-topo-1080"];
const PESSOAS_TOPO = "topo|deputado|senador|ministro|governador|prefeitura|vereador|judiciario-pessoa";
const GRUPOS = [
  { nome: "topo do contracheque", quando: /conta__resumo|resumoTopo|faixaPosicao|posicao-faixa|resumo-valor|conta__topo/, paginas: new RegExp(PESSOAS_TOPO) },
  { nome: "ajuda de custo e comparações", quando: /unicosDe|UNICOS|mesesDoUnico|comoUnico|somaUnicos|textoUnico|function resumo\(|function colegas|function posicao|secRanking|secComparar/, paginas: /ajuda|topo|deputado-federal|senador|ministro/ },
  { nome: "menu das seções", quando: /navSecoes|secoes-caixa|\.secoes\b/, paginas: /topo|deputado-federal|senador|cidade|estado|inicio/ },
  { nome: "presença e projetos", quando: /secAtividade|carregarAtividade|\bATIV\b|atividade\.json/, paginas: /atividade/ },
  { nome: "bens declarados", quando: /secBens|BENS\b|bens\.json|bens-interior/, paginas: /bens/ },
  { nome: "atualização, rodada e congeladas", quando: /blocoRodada|secAtualizacao|situacao\.json|linhaCongelada|avisoReserva|RESERVA\b|congelad/, paginas: /atualizacao|congelada|reserva/ },
  { nome: "cidade e interior", quando: /secCidade|vereadoresInterior|secPrefeitura|vereadoresCargo|carregarInterior|carregarCargo|interior/, paginas: /^cidade|reserva|bens-cidade/ },
  { nome: "governador e estado", quando: /secGovernador|notasGov|blocoTJ|otDe|secViagensG|governadores\.json/, paginas: /governador|estado|rj-/ },
  { nome: "judiciário", quando: /secJudiciario|notasJud|judiciario\.json/, paginas: /judiciario/ },
  { nome: "busca sem resultado", quando: /termoMedivel|medirBuscaVazia|busca_sem_resultado/, paginas: /^busca-sem-resultado$/ },
  { nome: "índice de transparência", quando: /secIndice|indice_transparencia/, paginas: /indice/ },
  { nome: "sobre, imprensa e dados abertos", quando: /secSobre|sobre\.json|secImprensa|imprensa|secDadosAbertos|manifesto/, paginas: /sobre|imprensa|dados-abertos/ },
  { nome: "descobrir os representantes", quando: /abrirGuia|listaGuia|guia__/, paginas: /descobrir|inicio/ },
  { nome: "carregamento de arquivo que falta", quando: /\bfalhou\b|lerJSON|carregando/i, paginas: /arquivo-ausente|arquivo-quebrado/ },
];
function paginasDoRapido() {
  const nomes = new Set(RAPIDO), motivos = [];
  const git = (args) => spawnSync("git", args, { cwd: RAIZ, encoding: "utf8" }).stdout || "";
  // só o que é do site (o próprio teste não conta: ele cita todos os assuntos)
  const alvo = ["site", "publicacao", ":(exclude)publicacao/testes", ":(exclude)site/dados", ":(exclude)site/fotos", ":(exclude)Claude outputs"];
  const arquivos = [...git(["diff", "--name-only", "HEAD", "--", ...alvo]).split("\n"), ...git(["ls-files", "--others", "--exclude-standard", "--", ...alvo]).split("\n")].filter(Boolean);
  const diff = git(["diff", "HEAD", "-U0", "--", ...alvo]).split("\n").filter((l) => /^[+-][^+-]/.test(l)).join("\n") + "\n" + arquivos.join("\n");
  for (const g of GRUPOS) {
    if (!g.quando.test(diff)) continue;
    const achadas = PAGINAS.filter((p) => g.paginas.test(p.nome)).map((p) => p.nome);
    achadas.forEach((n) => nomes.add(n));
    motivos.push(`${g.nome} (${achadas.length})`);
  }
  // uma página nova ou mudada no próprio teste entra sempre
  const mudadaNoTeste = git(["diff", "HEAD", "-U0", "--", "publicacao/testes/rodar.mjs"]).split("\n").filter((l) => /^\+\s*\{ nome: "/.test(l)).map((l) => (/nome: "([^"]+)"/.exec(l) || [])[1]).filter((n) => n && PAGINAS.some((p) => p.nome === n));
  mudadaNoTeste.forEach((n) => nomes.add(n));
  if (mudadaNoTeste.length) motivos.push(`páginas novas no teste (${mudadaNoTeste.length})`);
  if (/publicacao\/gerar\.mjs|UNICOS|resumo\(/.test(diff)) motivos.push("rode também node publicacao/testes/regras.mjs (concordância entre o HTML pronto e a página)");
  return { nomes: [...nomes].filter((n) => PAGINAS.some((p) => p.nome === n)), motivos };
}
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
  const externos = new Set(), meus = new Set(), pedidosPorCaminho = new Map();
  const parar = eventos((metodo, p) => {
    if (metodo === "Runtime.exceptionThrown") {
      const d = p.exceptionDetails; falhas.push(`exceção: ${(d.exception && d.exception.description) || d.text}`.split("\n")[0].slice(0, 200));
    } else if (metodo === "Runtime.consoleAPICalled" && (p.type === "error" || p.type === "assert")) {
      const t = p.args.map((a) => a.value ?? a.description ?? "").join(" ");
      if (!/ERR_BLOCKED_BY_CLIENT/.test(t)) falhas.push(`console.error: ${t.slice(0, 200)}`);
    } else if (metodo === "Log.entryAdded" && p.entry.level === "error") {
      let host = ""; try { host = new URL(p.entry.url).host; } catch { /* sem endereço */ }
      if (host && host !== local) return; // arquivo de fora, que o teste bloqueia
      let caminhoLog = ""; try { caminhoLog = new URL(p.entry.url).pathname; } catch { /* sem endereço */ }
      if (caminhoLog && (pg.falhasEsperadas || []).includes(caminhoLog)) return; // o navegador registra o 404 do arquivo que o teste faz faltar
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
      if (h === local && r.status >= 400 && (pg.falhasEsperadas || []).includes(caminho)) { /* o teste simula este arquivo ausente */ }
      else if (h === local && r.status >= 400) falhas.push(`arquivo não carregou (${r.status}): ${caminho}`);
      // o servidor local (como o Cloudflare Pages) devolve a página inicial para o que não existe: um .json que veio como HTML é arquivo que falta
      else if (h === local && /\.(json|js|css|webp|png|svg)$/.test(caminho) && /text\/html/.test(r.mimeType || "")) falhas.push(`arquivo que não existe (veio uma página HTML): ${caminho}`);
    } else if (metodo === "Fetch.requestPaused") {
      const h = new URL(p.request.url).host;
      const caminhoP = h === local ? new URL(p.request.url).pathname : "";
      if (h === local) pedidosPorCaminho.set(caminhoP, (pedidosPorCaminho.get(caminhoP) || 0) + 1);
      const simulado = h === local && pg.simular ? pg.simular(caminhoP) : null;
      // simular() devolve o texto do arquivo (resposta 200) ou { status, corpo }, para simular o arquivo ausente (404) ou quebrado
      if (simulado) cmd("Fetch.fulfillRequest", { requestId: p.requestId, responseCode: typeof simulado === "object" ? simulado.status : 200, responseHeaders: [{ name: "Content-Type", value: "application/json" }], body: Buffer.from(typeof simulado === "object" ? simulado.corpo || "" : simulado).toString("base64") }).catch(() => {});
      else if (h === local || /^(data|blob):/.test(p.request.url)) cmd("Fetch.continueRequest", { requestId: p.requestId }).catch(() => {});
      else { externos.add(h); cmd("Fetch.failRequest", { requestId: p.requestId, errorReason: "BlockedByClient" }).catch(() => {}); }
    }
  });
  try {
    await Promise.all([cmd("Page.enable"), cmd("Runtime.enable"), cmd("Log.enable"), cmd("Network.enable")]);
    // nada de fora: o teste não pode contar visita no Google Analytics nem depender de internet
    await cmd("Fetch.enable", { patterns: [{ urlPattern: "*" }] });
    await cmd("Emulation.setDeviceMetricsOverride", { width: pg.largura && !perfil.mobile ? pg.largura : perfil.largura, height: perfil.altura, deviceScaleFactor: perfil.escala, mobile: perfil.mobile });
    await cmd("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: perfil.tema }] });
    await cmd("Page.addScriptToEvaluateOnNewDocument", { source: INICIO });
    if (pg.metas) { // a <meta> que o gerar.mjs poria se os arquivos existissem (entra assim que o <head> existe, antes do app)
      await cmd("Page.addScriptToEvaluateOnNewDocument", { source: `(() => { const metas = ${JSON.stringify(Object.entries(pg.metas))}; const poe = () => { if (!document.head) return false;
        for (const [n, c] of metas) { const m = document.createElement("meta"); m.name = n; m.content = c; document.head.append(m); } return true; };
        if (!poe()) { const o = new MutationObserver(() => { if (poe()) o.disconnect(); }); o.observe(document, { childList: true, subtree: true }); } })();` });
    }
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
    if (!pg.semRolar) { // (semRolar: a página que confere o que NÃO foi baixado antes de alguém chegar perto do ranking)
      await avaliar(`window.scrollTo(0, document.documentElement.scrollHeight)`); await espera(600);
      await avaliar(`window.scrollTo(0, 0)`); await espera(400);
    }

    // limite de pedidos por arquivo (pg.maxPedidos): arquivo que falta não pode ser pedido sem fim (já houve ciclo: a seção se recriava e pedia de novo)
    if (pg.maxPedidos) await espera(1500); // dá tempo de um ciclo se mostrar (só nas páginas que conferem o número de pedidos)
    for (const [arq, max] of Object.entries(pg.maxPedidos || {})) { const n = pedidosPorCaminho.get(arq) || 0; if (n > max) falhas.push(`${arq} foi pedido ${n} vezes (o limite é ${max}): ciclo de pedidos?`); }
    // blocos recolhidos no celular (details.recolher): abrem para o teste ler o texto; o pulo de layout de abrir não conta no CLS
    const cls0 = await avaliar(`window.__m.cls`);
    await avaliar(`document.querySelectorAll("details.recolher").forEach((d) => { d.open = true; })`); await espera(500);
    await avaliar(`window.__m.cls = ${Number(cls0) || 0}`);
    // pg.acao: o teste clica e digita (a pessoa teria dado um clique, o que não conta como pulo de layout); o CLS de antes fica
    const clsAntes = pg.acao ? Number(await avaliar(`window.__m.cls`)) || 0 : null;
    if (pg.depois) (await avaliar(pg.depois)).forEach((x) => falhas.push(x));
    if (pg.acao) { await espera(700); await avaliar(`window.__m.cls = ${clsAntes}`); }
    const m = await avaliar(`(() => {
      const visivel = (e) => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
      return { cls: window.__m.cls, lcp: window.__m.lcp, titulo: document.title, h1: [...document.querySelectorAll("h1")].filter(visivel).length,
        cookies: document.cookie, letras: [...document.fonts].filter((f) => f.status === "loaded").length, sobra: document.documentElement.scrollWidth - document.documentElement.clientWidth, carregando: !!document.querySelector(".carregando"),
        contagens: ${JSON.stringify((pg.ter || []).map(([s]) => s))}.map((s) => document.querySelectorAll(s).length),
        textoCidade: [...document.querySelectorAll("#cidade, #prefeitura")].map((e) => e.innerText).join("\\n"),
        textoPagina: (document.querySelector("#app") || {}).innerText || "", textoBens: (document.querySelector("#bens") || {}).innerText || "", textoContracheque: (document.querySelector("#contracheque") || {}).innerText || "", textoAtividade: (document.querySelector("#atividade") || {}).innerText || "",
        // o retângulo escuro do topo (proposta B, ver resumoTopo no app.js): o número e a divisão que o explica; o contexto (salários mínimos,
        // selo, posição); a nota no pé, ligada ao número por um asterisco; "Página oficial" na linha do cargo; sem canto vazio
        topo: (() => { const c = document.querySelector("#contracheque .conta__resumo"); if (!c || !c.querySelector(".resumo-valor")) return null;
          const R = (e) => e.getBoundingClientRect(), num = c.querySelector(".conta__resumo-numero"), ctx = c.querySelector(".conta__resumo-contexto"), origem = c.querySelector(".conta__resumo-origem"),
            valor = c.querySelector(".resumo-valor"), nota = c.querySelector(".conta__resumo-nota"), oficial = document.querySelector("#contracheque .conta__oficial");
          const duas = !!num && !!ctx && getComputedStyle(c).gridTemplateAreas !== "none";
          const ultimo = (e) => { const f = [...e.children].filter((x) => x.getBoundingClientRect().height); return f.length ? R(f[f.length - 1]).bottom : R(e).top; };
          return { numeroOk: !!num && num.contains(valor) && !!origem && num.contains(origem) && !!origem.querySelector(".resumo-divisao"),
            contextoOk: !!ctx && !!ctx.querySelector(".resumo-sm") && /salários mínimos por mês/.test(ctx.querySelector(".resumo-sm").textContent),
            origemSoDivisao: !!origem && !origem.querySelector(".resumo-sm, .selo-comp, .posicao-faixa, .conta__resumo-nota, .resumo-valor"),
            ordem: !!num && !!ctx && !!(num.compareDocumentPosition(ctx) & Node.DOCUMENT_POSITION_FOLLOWING) && (!nota || !!(ctx.compareDocumentPosition(nota) & Node.DOCUMENT_POSITION_FOLLOWING)),
            sinalOk: !nota || !!valor.querySelector(".resumo-sinal"), semNotaSemSinal: !!nota || !valor.querySelector(".resumo-sinal"),
            oficialNaLinha: !oficial || !!oficial.closest(".conta__sub"), duas,
            topoCtx: duas ? Math.round(R(ctx).top - R(num).top) : 0, sobraCtx: duas ? Math.round(ultimo(ctx) - ultimo(num)) : 0, sobrepoe: duas && R(valor).right > R(ctx).left + 1,
            fioEsq: duas ? R(ctx).left >= R(num).right : true, notaNoPe: !nota || !duas || R(nota).top >= Math.max(R(num).bottom, R(ctx).bottom) - 1,
            sobraH: [...c.querySelectorAll("*")].filter((e) => e.getBoundingClientRect().width && (R(e).right > R(c).right + 1 || R(e).left < R(c).left - 1)).length }; })(),
        // a lista das seções: uma linha só (os botões com o mesmo topo); se não cabe, rola e a caixa avisa onde há mais (data-mais)
        menu: (() => { const nav = document.querySelector("#secoes"), bs = nav ? [...nav.querySelectorAll("button")] : []; if (!bs.length) return null;
          const caixa = nav.parentElement; return { linhas: new Set(bs.map((b) => Math.round(b.getBoundingClientRect().top))).size, rola: nav.scrollWidth > nav.clientWidth + 1, mais: caixa.dataset.mais || "", esq: nav.scrollLeft > 4 }; })() };
    })()`);
    if (!/Contas do Poder/.test(m.titulo)) falhas.push(`título sem "Contas do Poder": "${m.titulo}"`);
    if (m.h1 !== 1) falhas.push(`${m.h1} títulos h1 visíveis (deve ser 1)`);
    if (m.carregando) falhas.push('o "Carregando…" continua na tela');
    if (m.cookies) falhas.push(`o site criou cookies (a página /sobre diz que não usa cookies próprios): ${m.cookies.slice(0, 80)}`);
    if (m.sobra > 1) falhas.push(`rolagem horizontal: a página é ${m.sobra} px mais larga que a tela`);
    (pg.ter || []).forEach(([sel, minimo], i) => { if (m.contagens[i] < minimo) falhas.push(`esperava ${minimo} de "${sel}" e achei ${m.contagens[i]}`); });
    (pg.texto || []).forEach((re) => { if (!re.test(m.textoCidade)) falhas.push(`o texto da cidade não tem ${re}`); });
    (pg.sem || []).forEach((re) => { if (re.test(m.textoCidade)) falhas.push(`o texto da cidade não podia ter ${re}`); });
    (pg.atividade || []).forEach((re) => { if (!re.test(m.textoAtividade)) falhas.push(`a seção de presença e projetos não tem ${re}`); });
    (pg.semAtividade || []).forEach((re) => { if (re.test(m.textoAtividade)) falhas.push(`a seção de presença e projetos não podia ter ${re}`); });
    (pg.pagina || []).forEach((re) => { if (!re.test(m.textoPagina)) falhas.push(`a página não tem ${re}`); });
    (pg.semPagina || []).forEach((re) => { if (re.test(m.textoPagina)) falhas.push(`a página não podia ter ${re}`); });
    (pg.semBens || []).forEach((re) => { if (re.test(m.textoBens)) falhas.push(`o bloco de bens não podia ter ${re}`); });
    (pg.contem || []).forEach((re) => { if (!re.test(m.textoContracheque)) falhas.push(`o contracheque não tem ${re}`); });
    (pg.semContem || []).forEach((re) => { if (re.test(m.textoContracheque)) falhas.push(`o contracheque não podia ter ${re}`); });
    if (m.topo) {
      if (!m.topo.numeroOk) falhas.push("no topo escuro, o número e a divisão bolso/gastos têm de estar juntos (conta__resumo-numero)");
      if (!m.topo.contextoOk) falhas.push('no topo escuro, o contexto tem de trazer "Equivale a N salários mínimos por mês" (conta__resumo-contexto)');
      if (!m.topo.origemSoDivisao) falhas.push("no topo escuro, a divisão bolso e gastos não pode levar o que é do contexto (salários mínimos, selo, posição, nota)");
      if (!m.topo.ordem) falhas.push("no topo escuro, a ordem tem de ser número, contexto e, por último, a nota");
      if (!m.topo.sinalOk) falhas.push("a nota do topo não está ligada ao número por um asterisco");
      if (!m.topo.semNotaSemSinal) falhas.push("há um asterisco no número do topo sem nota");
      if (!m.topo.oficialNaLinha) falhas.push('o link "Página oficial" tem de ficar na linha do cargo (conta__sub)');
      if (m.topo.duas && Math.abs(m.topo.topoCtx) > 2) falhas.push(`no computador, o contexto não começa na altura do número (${m.topo.topoCtx}px)`);
      if (m.topo.duas && !m.topo.fioEsq) falhas.push("no computador, o contexto tem de ficar à direita do número");
      if (m.topo.duas && m.topo.sobraCtx > 40) falhas.push(`no computador, o contexto passa ${m.topo.sobraCtx}px do fim do número: canto vazio embaixo do número`);
      if (m.topo.sobrepoe) falhas.push("o número grande passa por cima do contexto");
      if (!m.topo.notaNoPe) falhas.push("a nota do topo tem de ficar no pé, abaixo do número e do contexto");
      if (m.topo.sobraH) falhas.push(`${m.topo.sobraH} elementos do topo escuro passam da borda`);
    }
    if (m.menu) {
      if (m.menu.linhas > 1) falhas.push(`o menu das seções ficou em ${m.menu.linhas} linhas (tem de ser uma só, com rolagem para o lado)`);
      if (m.menu.rola && !/dir/.test(m.menu.mais) && !m.menu.esq) falhas.push("o menu das seções rola para o lado mas não avisa que há mais (data-mais)");
    }
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
      // pg.recorte: só o trecho da página (um seletor), em vez da página inteira
      const alvo = pg.recorte ? await avaliar(`(() => { const e = document.querySelector(${JSON.stringify(pg.recorte)}); if (!e) return null; const b = e.getBoundingClientRect(); return { x: Math.max(0, b.left - 8), y: b.top + scrollY - 8, width: Math.min(innerWidth, b.width + 16), height: b.height + 16, scale: 1 }; })()`) : null;
      const { data } = await cmd("Page.captureScreenshot", { format: "png", captureBeyondViewport: true, ...(alvo ? { clip: alvo } : {}) });
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
  let filtro = arg("paginas") && String(arg("paginas")).split(",");
  if (!filtro && (arg("rapido") || arg("mudou"))) {
    if (arg("mudou")) { const r = paginasDoRapido(); filtro = r.nomes; console.log(`Modo rápido (--mudou): ${filtro.length} páginas; assuntos tocados: ${r.motivos.join("; ") || "nenhum além do básico"}.`); }
    else { filtro = RAPIDO; console.log(`Modo rápido: ${filtro.length} páginas, uma de cada tipo.`); }
    console.log("A suíte completa (node publicacao/testes/rodar.mjs --completo) é a que vale antes do commit.\n");
  }
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
