/* Robô de integração com o Painel NEAGRO-DF.
   Lê a base pública do painel (Firestore: coleções meses, lancamentos e indices) e o quadro de
   movimentação de animais (GTA_DF) publicado no código do painel, calcula o semáforo de relações
   de troca com a mesma rotina usada pela página (src/painel-calc.js) e grava data/painel.json.
   Se alguma leitura falhar, o retrato anterior é mantido.
   Uso: node scripts/painel.js   (Node 18 ou mais recente, sem dependências) */
"use strict";
const fs = require("fs");
const path = require("path");
const calc = require("../src/painel-calc.js");
const quadros = require("./painel-quadros.js");

const RAIZ = path.resolve(__dirname, "..");
const SAIDA = path.join(RAIZ, "data", "painel.json");
const PROJETO = "neagro---df";
const BASE = `https://firestore.googleapis.com/v1/projects/${PROJETO}/databases/(default)/documents/`;
const PAINEL = process.env.PAINEL_URL || ""; /* endereço do painel guardado no secret PAINEL_URL do repositório */
const log = m => console.error(`[painel] ${m}`);
const NO_ACTIONS = !!process.env.GITHUB_ACTIONS;
/* Avisos aparecem no resumo da execução do GitHub Actions; erros de estrutura fazem a etapa de conferência falhar,
   e o GitHub avisa por e-mail quem mantém o repositório. */
function anunciar(a) {
  const nivel = a.tipo === "estrutura" ? "error" : "warning";
  if (NO_ACTIONS) console.log(`::${nivel} title=Painel NEAGRO-DF (${a.tipo})::${a.texto}`);
  else log(`${nivel === "error" ? "ERRO" : "aviso"}: ${a.texto}`);
}

/* node scripts/painel.js --verificar : confere o retrato gravado e sai com código 1 se houver erro de estrutura. */
if (process.argv.includes("--verificar")) {
  const p = fs.existsSync(SAIDA) ? JSON.parse(fs.readFileSync(SAIDA, "utf8")) : null;
  const al = (p && p.alertas) || [];
  al.forEach(anunciar);
  const graves = al.filter(a => a.tipo === "estrutura");
  log(graves.length ? `${graves.length} problema(s) de estrutura na integração com o painel` : `integração conferida (${al.length} aviso(s) de valor)`);
  process.exit(graves.length ? 1 : 0);
}

async function colecao(nome) {
  const docs = [];
  let token = "";
  do {
    const url = `${BASE}${nome}?pageSize=300${token ? "&pageToken=" + encodeURIComponent(token) : ""}`;
    const r = await fetch(url, { headers: { "User-Agent": "NEAGRO-DF portal" } });
    if (!r.ok) throw new Error(`${nome}: HTTP ${r.status}`);
    const j = await r.json();
    (j.documents || []).forEach(d => docs.push(d));
    token = j.nextPageToken || "";
  } while (token);
  return docs;
}

let HTML_PAINEL = null;
async function htmlPainel() {
  if (HTML_PAINEL) return HTML_PAINEL;
  if (!PAINEL) throw new Error("endereço do painel não configurado (secret PAINEL_URL)");
  const r = await fetch(PAINEL, { headers: { "User-Agent": "NEAGRO-DF portal" } });
  if (!r.ok) throw new Error(`painel: HTTP ${r.status}`);
  HTML_PAINEL = await r.text();
  return HTML_PAINEL;
}

async function quadroGTA() {
  const html = await htmlPainel();
  const i = html.indexOf("const GTA_DF = ");
  if (i < 0) throw new Error("quadro GTA_DF não encontrado no painel");
  const fim = html.indexOf(";\n", i);
  return JSON.parse(html.slice(i + 15, fim));
}

async function main() {
  const anterior = fs.existsSync(SAIDA) ? JSON.parse(fs.readFileSync(SAIDA, "utf8")) : null;
  const hoje = new Date(Date.now() - 3 * 3600e3).toISOString().slice(0, 10);
  let resultado;
  try {
    const [meses, lanc, indices] = await Promise.all([colecao("meses"), colecao("lancamentos"), colecao("indices")]);
    resultado = calc.calcular(meses, lanc, indices);
    if (!resultado) throw new Error("nenhum mês com dados comuns (milho e farelo)");
    log(`semáforo de ${resultado.mes}: ${resultado.semaforo.length} relações, ${resultado.meses_registrados} meses registrados`);
    if (resultado.semaforo.length < resultado.relacoes_esperadas)
      resultado.alertas.push({ tipo: "estrutura", campo: null, mes: resultado.mes,
        texto: `Semáforo de ${resultado.mes} com ${resultado.semaforo.length} de ${resultado.relacoes_esperadas} relações. Conferir campos ausentes ou renomeados no painel.` });
  } catch (e) {
    log(`falha ao ler a base do painel (${e.message}); mantido o retrato anterior`);
    return;
  }
  try {
    resultado.gta = calc.gta(await quadroGTA(), resultado.gta_suinos, resultado.mes);
    if (resultado.gta) log(`GTA do DF: ${resultado.gta.mes}`);
  } catch (e) {
    log(`GTA não atualizado (${e.message})`);
    resultado.alertas.push({ tipo: "estrutura", campo: "GTA_DF", mes: resultado.mes, texto: `Quadro GTA_DF não lido no código do painel (${e.message}).` });
    resultado.gta = anterior ? anterior.gta : null;
  }
  /* Demais quadros do painel (GTA de suínos, rebanhos por UF, comércio exterior, EMATER-DF): data/painel_quadros.json. */
  try {
    const faltam = quadros.gravar(await htmlPainel(), hoje);
    log(`data/painel_quadros.json gravado${faltam.length ? ` (não lidos: ${faltam.join(", ")})` : ""}`);
    faltam.forEach(f => resultado.alertas.push({ tipo: "valor", campo: f, mes: resultado.mes,
      texto: `Quadro ${f} não encontrado no código do painel; o portal manteve o anterior ou omitiu o bloco.` }));
  } catch (e) {
    log(`quadros do painel não atualizados (${e.message}); mantido o arquivo anterior`);
  }
  /* O painel não é público: o retrato não traz o endereço do painel nem o da base. */
  resultado.fonte = {
    nome: "NEAGRO-DF (FAV/UnB), levantamento mensal de preços e relações de troca",
    link: "",
    endpoint: "base de dados interna do NEAGRO-DF",
    gta_fonte: "SEAGRI-DF, GTAs emitidas e recebidas no DF, compiladas pelo NEAGRO-DF",
    extraido_em: hoje
  };
  resultado.alertas.forEach(anunciar);
  fs.writeFileSync(SAIDA, JSON.stringify(resultado, null, 2));
  log("data/painel.json gravado");
}

main().catch(e => { log(`erro inesperado: ${e.message}`); process.exitCode = 0; });
