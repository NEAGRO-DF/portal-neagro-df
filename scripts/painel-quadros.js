/* Quadros do Painel NEAGRO-DF que o portal reproduz (o painel continua sem link público).
   O painel guarda no próprio código (index.html) os quadros que a equipe atualiza à mão: GTA de suínos,
   rebanhos e produção por UF (IBGE/PPM e Peixe BR), comércio exterior de ovinos e caprinos e de pescado
   (MDIC/Comex Stat) e os números da EMATER-DF. Este módulo lê esses quadros a cada execução do robô e grava
   data/painel_quadros.json; o portal desenha a seção "Produção e mercado" a partir desse arquivo.
   Séries mensais param no último mês aprovado (MES_APROVADO de src/painel-calc.js). */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const RAIZ = path.resolve(__dirname, "..");
const SAIDA = path.join(RAIZ, "data", "painel_quadros.json");
const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const ordem = m => { const p = String(m).split("/"); return (+p[1]) * 100 + MESES.indexOf(p[0]); };

/* Ordem importa: PEIXE_BR usa PBR_UF. */
const NOMES = ["GTA_SUINO_MESES", "GTA_SUINO", "GTA_SUINO_UF_SAIDA_MES", "GTA_SUINO_UF_ENTRADA_MES",
  "REBANHO_BOV", "VACAS_ORD", "PROD_LEITE", "SUI_REB", "SUI_MAT", "AVI_GAL", "AVI_GLN", "PBR_UF", "PEIXE_BR",
  "XC_SEED", "IM_SEED", "PESCA_SEED", "DF_EMATER", "PAINEL_VERSAO"];

/* Texto do literal que segue "const NOME = " (objeto, lista, texto ou expressão simples até o ";"). */
function literal(html, nome) {
  const m = new RegExp(`const ${nome}\\s*=\\s*`).exec(html);
  if (!m) return null;
  let i = m.index + m[0].length;
  if (html[i] !== "{" && html[i] !== "[") { const f = html.indexOf(";", i); return f < 0 ? null : html.slice(i, f); }
  let prof = 0, aspas = null;
  for (let k = i; k < html.length; k++) {
    const c = html[k];
    if (aspas) { if (c === "\\") { k++; continue; } if (c === aspas) aspas = null; continue; }
    if (c === "/" && html[k + 1] === "/") { k = html.indexOf("\n", k); if (k < 0) return null; continue; }
    if (c === "/" && html[k + 1] === "*") { k = html.indexOf("*/", k + 2) + 1; if (k <= 0) return null; continue; }
    if (c === '"' || c === "'" || c === "`") { aspas = c; continue; }
    if (c === "{" || c === "[") prof++;
    else if ((c === "}" || c === "]") && --prof === 0) return html.slice(i, k + 1);
  }
  return null;
}

function ler(html) {
  const ctx = vm.createContext({});
  const q = {}, faltam = [];
  for (const nome of NOMES) {
    const t = literal(html, nome);
    if (!t) { faltam.push(nome); continue; }
    try { vm.runInContext(`var ${nome} = (${t});`, ctx, { timeout: 2000 }); q[nome] = ctx[nome]; }
    catch (e) { faltam.push(`${nome} (${e.message})`); }
  }
  return { q: JSON.parse(JSON.stringify(q)), faltam };
}

function mesAprovado() {
  const t = fs.readFileSync(path.join(RAIZ, "src", "painel-calc.js"), "utf8");
  const m = /MES_APROVADO\s*=\s*"([a-z]{3}\/\d{2})"/.exec(t);
  return m ? m[1] : null;
}

const UF_NOME = { AC: "Acre", AL: "Alagoas", AP: "Amapá", AM: "Amazonas", BA: "Bahia", CE: "Ceará", DF: "Distrito Federal",
  ES: "Espírito Santo", GO: "Goiás", MA: "Maranhão", MT: "Mato Grosso", MS: "Mato Grosso do Sul", MG: "Minas Gerais",
  PA: "Pará", PB: "Paraíba", PR: "Paraná", PE: "Pernambuco", PI: "Piauí", RJ: "Rio de Janeiro", RN: "Rio Grande do Norte",
  RS: "Rio Grande do Sul", RO: "Rondônia", RR: "Roraima", SC: "Santa Catarina", SP: "São Paulo", SE: "Sergipe", TO: "Tocantins" };

function producao(q) {
  const itens = [
    ["REBANHO_BOV", "Rebanho bovino", "cabeças", "IBGE, PPM, Tabela 3939", "https://sidra.ibge.gov.br/tabela/3939"],
    ["VACAS_ORD", "Vacas ordenhadas", "cabeças", "IBGE, PPM, Tabela 94", "https://sidra.ibge.gov.br/tabela/94"],
    ["PROD_LEITE", "Produção de leite", "mil litros", "IBGE, PPM, Tabela 74", "https://sidra.ibge.gov.br/tabela/74"],
    ["SUI_REB", "Rebanho suíno", "cabeças", "IBGE, PPM, Tabela 3939", "https://sidra.ibge.gov.br/tabela/3939"],
    ["SUI_MAT", "Matrizes de suínos", "cabeças", "IBGE, PPM, Tabela 3939", "https://sidra.ibge.gov.br/tabela/3939"],
    ["AVI_GAL", "Galináceos", "cabeças", "IBGE, PPM, Tabela 3939", "https://sidra.ibge.gov.br/tabela/3939"],
    ["AVI_GLN", "Galinhas (postura)", "cabeças", "IBGE, PPM, Tabela 3939", "https://sidra.ibge.gov.br/tabela/3939"],
    ["PEIXE_BR", "Peixes de cultivo", "toneladas", "Associação Brasileira da Piscicultura, Anuário Peixe BR", "https://www.peixebr.com.br/anuario/"]
  ];
  return itens.filter(([k]) => q[k] && q[k].uf).map(([k, nome, un, fonte, link]) => {
    const o = q[k], ufs = Object.entries(o.uf).filter(([, v]) => typeof v === "number" && v > 0).sort((a, b) => b[1] - a[1]);
    const brasil = o.brasil || ufs.reduce((s, [, v]) => s + v, 0);
    const pos = ufs.findIndex(([u]) => u === "DF");
    return { id: k, nome, ano: String(o.ano || ""), unidade: un, brasil,
      df: o.uf.DF || null, df_pct: o.uf.DF && brasil ? +(o.uf.DF / brasil * 100).toFixed(2) : null, df_posicao: pos >= 0 ? pos + 1 : null, ufs_com_dado: ufs.length,
      maiores: ufs.slice(0, 5).map(([u, v]) => ({ uf: u, nome: UF_NOME[u] || u, valor: v, pct: brasil ? +(v / brasil * 100).toFixed(1) : null })),
      fonte, link };
  });
}

function gtaSuinos(q, corte) {
  const M = q.GTA_SUINO_MESES, G = q.GTA_SUINO;
  if (!M || !G) return null;
  const n = M.filter(m => !corte || ordem(m) <= ordem(corte)).length;
  const serie = (o, k) => (o && o[k] ? o[k].slice(0, n) : []);
  const ufs = (o) => Object.entries(o || {}).map(([uf, v]) => {
    const ult = v.slice(0, n).slice(-12);
    return { uf, nome: UF_NOME[uf] || uf, ultimos12: ult.reduce((s, x) => s + (x || 0), 0) };
  }).filter(x => x.ultimos12 > 0).sort((a, b) => b.ultimos12 - a.ultimos12);
  return {
    meses: M.slice(0, n),
    entrada: { total: serie(G.entrada, "total"), abate: serie(G.entrada, "abate"), engorda: serie(G.entrada, "engorda") },
    saida: { total: serie(G.saida, "total"), abate: serie(G.saida, "abate"), engorda: serie(G.saida, "engorda") },
    interno: { total: serie(G.interno, "total"), abate: serie(G.interno, "abate"), engorda: serie(G.interno, "engorda") },
    destinos: ufs(q.GTA_SUINO_UF_SAIDA_MES), origens: ufs(q.GTA_SUINO_UF_ENTRADA_MES),
    fonte: "SEAGRI-DF, Guias de Trânsito Animal (GTA) de suínos emitidas e recebidas no DF, compiladas pelo NEAGRO-DF",
    link: ""
  };
}

/* Comex: soma dos últimos 12 meses aprovados e principais países. Pares [kg, US$]. */
function comexOvinos(lista, corte) {
  if (!Array.isArray(lista)) return null;
  const ok = lista.filter(e => e && e.mes && (!corte || ordem(e.mes) <= ordem(corte))).sort((a, b) => ordem(a.mes) - ordem(b.mes));
  const ult = ok.slice(-12);
  if (!ult.length) return null;
  const paises = {};
  let kg = 0, usd = 0;
  ult.forEach(e => Object.entries(e.c || {}).forEach(([p, v]) => {
    const [k, u] = v || [0, 0]; kg += k || 0; usd += u || 0;
    paises[p] = paises[p] || [0, 0]; paises[p][0] += k || 0; paises[p][1] += u || 0;
  }));
  return { de: ult[0].mes, ate: ult[ult.length - 1].mes, kg, usd,
    meses: ok.map(e => ({ mes: e.mes, kg: Object.values(e.c || {}).reduce((s, v) => s + ((v || [])[0] || 0), 0),
      usd: Object.values(e.c || {}).reduce((s, v) => s + ((v || [])[1] || 0), 0) })),
    paises: Object.entries(paises).sort((a, b) => b[1][0] - a[1][0]).slice(0, 6).map(([p, v]) => ({ pais: p, kg: v[0], usd: v[1] })) };
}

function comexPescado(P, corte) {
  if (!P) return null;
  const meses = Object.keys(P).filter(m => !corte || ordem(m) <= ordem(corte)).sort((a, b) => ordem(a) - ordem(b));
  const ult = meses.slice(-12);
  if (!ult.length) return null;
  const lado = k => {
    const paises = {}; let kg = 0, usd = 0;
    ult.forEach(m => (P[m][k] || []).forEach(([p, a, b]) => {
      kg += a || 0; usd += b || 0;
      if (!/^Demais/.test(p)) { paises[p] = paises[p] || [0, 0]; paises[p][0] += a || 0; paises[p][1] += b || 0; }
    }));
    return { kg, usd, paises: Object.entries(paises).sort((a, b) => b[1][1] - a[1][1]).slice(0, 6).map(([p, v]) => ({ pais: p, kg: v[0], usd: v[1] })) };
  };
  return { de: ult[0], ate: ult[ult.length - 1], exportacao: lado("ex"), importacao: lado("im") };
}

function montar(html, hoje) {
  const { q, faltam } = ler(html);
  const corte = mesAprovado();
  return {
    versao_painel: q.PAINEL_VERSAO || null,
    mes_aprovado: corte,
    extraido_em: hoje,
    producao: producao(q),
    gta_suinos: gtaSuinos(q, corte),
    comex: {
      ovinos_caprinos: {
        titulo: "Carne de ovinos e caprinos (NCM/SH4 0204)",
        exportacao: comexOvinos(q.XC_SEED, corte),
        importacao: comexOvinos(q.IM_SEED, corte),
        fonte: "MDIC/Secex, Comex Stat", link: "https://comexstat.mdic.gov.br/pt/geral"
      },
      pescado: Object.assign({ titulo: "Pescado (capítulo 03 da NCM)", fonte: "MDIC/Secex, Comex Stat", link: "https://comexstat.mdic.gov.br/pt/geral" },
        comexPescado(q.PESCA_SEED, corte) || {})
    },
    emater_df: q.DF_EMATER || null,
    faltam
  };
}

/* Lê o HTML do painel, grava data/painel_quadros.json e devolve os nomes de quadros que não foram lidos. */
function gravar(html, hoje) {
  const novo = montar(html, hoje);
  if (!novo.producao.length && !novo.gta_suinos) throw new Error("nenhum quadro do painel foi lido");
  fs.writeFileSync(SAIDA, JSON.stringify(novo, null, 1));
  return novo.faltam;
}

module.exports = { gravar, montar, literal };
