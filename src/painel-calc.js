/* Cálculo do semáforo de relações de troca a partir da base do Painel NEAGRO-DF.
   Usado em dois lugares, com o mesmo código:
   1) pela página do portal, que lê a base do painel ao vivo;
   2) pelo robô (scripts/painel.js), que grava o retrato data/painel.json.
   Regras da aba Metodologia do painel:
   IRT = preço do insumo ÷ preço do produto, no mês;
   sinal comparado à média simples de todos os meses registrados (inclusive o atual):
   favorável se o IRT estiver mais de 5% abaixo da média, desfavorável se mais de 5% acima, normal no intervalo. */
(function (raiz) {
  "use strict";
  var MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
  function ordem(m) { var p = String(m).split("/"); return (+p[1]) * 100 + MESES.indexOf(p[0]); }
  function valor(x) {
    if (!x) return null;
    if ("doubleValue" in x) return x.doubleValue;
    if ("integerValue" in x) return +x.integerValue;
    if ("stringValue" in x) return x.stringValue;
    return null;
  }
  function plano(f) { var o = {}; for (var k in (f || {})) { var v = valor(f[k]); if (v !== null) o[k] = v; } return o; }

  /* Junta o registro mensal (coleção "meses") com os lançamentos por aba (coleção "lancamentos"),
     que o painel aplica por cima do registro do mês. */
  function mesclar(docsMeses, docsLanc) {
    var por = {};
    (docsMeses || []).forEach(function (d) { var f = plano(d.fields); if (f.mes) por[f.mes] = f; });
    (docsLanc || []).slice().sort(function (a, b) {
      return String(valor((a.fields || {}).atualizado) || "").localeCompare(String(valor((b.fields || {}).atualizado) || ""));
    }).forEach(function (d) {
      var f = d.fields || {}, mes = valor(f.mes);
      var c = f.campos && f.campos.mapValue ? plano(f.campos.mapValue.fields) : {};
      if (!mes) return;
      por[mes] = Object.assign(por[mes] || { mes: mes }, c);
    });
    return Object.keys(por).map(function (k) { return por[k]; }).sort(function (a, b) { return ordem(a.mes) - ordem(b.mes); });
  }

  var UFS_BOI_MILHO = ["GO", "MG", "MS", "MT", "PR", "SC", "SP"], UFS_BOI_FARELO = ["GO", "MT", "SC", "SP"];
  function milho(uf) { return uf === "GO" ? "milho" : "milho_" + uf.toLowerCase(); }
  function farelo(uf) { return uf === "GO" ? "farelo" : "farelo_" + uf.toLowerCase(); }
  var RELACOES = [
    { cadeia: "Suinocultura", relacao: "Milho × suíno vivo (DF)", a: "milho_df", b: "sdf", ler: "kg de suíno por saca de milho", casas: 1 },
    { cadeia: "Suinocultura", relacao: "Farelo de soja × suíno vivo (DF)", a: "farelo", b: "sdf", ler: "kg de suíno por tonelada de farelo", casas: 1 }
  ]
    .concat(UFS_BOI_MILHO.map(function (uf) { return { cadeia: "Bovinocultura de corte", relacao: "Milho × boi gordo (" + uf + ")", a: milho(uf), b: "ub_" + uf.toLowerCase(), ler: "@ de boi por saca de milho", casas: 2 }; }))
    .concat(UFS_BOI_FARELO.map(function (uf) { return { cadeia: "Bovinocultura de corte", relacao: "Farelo de soja × boi gordo (" + uf + ")", a: farelo(uf), b: "ub_" + uf.toLowerCase(), ler: "@ de boi por tonelada de farelo", casas: 2 }; }))
    .concat([
      { cadeia: "Avicultura de corte", relacao: "Milho × frango vivo (GO)", a: "milho", b: "frgo", ler: "kg de frango por saca de milho", casas: 1 },
      { cadeia: "Avicultura de corte", relacao: "Farelo de soja × frango vivo (GO)", a: "farelo", b: "frgo", ler: "kg de frango por tonelada de farelo", casas: 1 },
      { cadeia: "Avicultura de postura", relacao: "Milho × ovo (GO)", a: "milho", b: "ovgo", ler: "dúzias de ovos por saca de milho", casas: 2 },
      { cadeia: "Avicultura de postura", relacao: "Farelo de soja × ovo (GO)", a: "farelo", b: "ovgo", ler: "dúzias de ovos por tonelada de farelo", casas: 1 },
      { cadeia: "Bovinocultura de leite", relacao: "Milho × leite (GO)", a: "milho", b: "lego", ler: "litros de leite por saca de milho", casas: 2 },
      { cadeia: "Bovinocultura de leite", relacao: "Farelo de soja × leite (GO)", a: "farelo", b: "lego", ler: "litros de leite por tonelada de farelo", casas: 1 }
    ]);

  var RESUMO = [
    ["Milho (GO)", "milho"], ["Farelo de soja (GO)", "farelo"], ["Suíno vivo (DF)", "sdf"],
    ["Boi gordo (SP, Barretos, Scot)", "scb_spbar"], ["Frango vivo (GO)", "frgo"], ["Ovo (GO)", "ovgo"], ["Leite (GO)", "lego"]
  ];
  var PRECOS_DF = [
    ["suino", "Suíno vivo DF", "sdf", "R$/kg", 2], ["milho", "Milho DF", "milho_df", "R$/sc 60 kg", 2],
    ["soja", "Soja DF", "soja_df", "R$/sc 60 kg", 2], ["ovo", "Ovo DF", "ovdf", "R$/dúzia", 2],
    ["leite", "Leite DF", "ledf", "R$/litro", 2], ["frango", "Frango vivo GO", "frgo", "R$/kg", 2],
    ["tilapia", "Tilápia (Grandes Lagos)", "tilgl", "R$/kg", 2], ["farelo", "Farelo de soja GO", "farelo", "R$/t", 2]
  ];
  var DESTAQUES = ["Milho × suíno vivo (DF)", "Milho × boi gordo (SP)", "Milho × frango vivo (GO)", "Milho × leite (GO)", "Milho × ovo (GO)"];
  function pos(x) { return typeof x === "number" && isFinite(x) && x > 0; }

  /* Conferência automática da base do painel.
     1) Estrutura: campos que o portal usa e que sumiram da base (o painel pode ter renomeado campos ou praças).
     2) Valores atípicos: preço de uma praça muito distante das demais praças do mesmo produto no mesmo mês
        (menos da metade ou mais de 1,5 vez a mediana das outras), ou variação de mais de 40% sobre o mês anterior. */
  var PRACAS = {
    "Frango vivo": { frgo: "GO", frpr: "PR", frsc: "SC", frsp: "SP", fres: "ES" },
    "Milho": { milho: "GO", milho_df: "DF", milho_mg: "MG", milho_ms: "MS", milho_mt: "MT", milho_pr: "PR", milho_sc: "SC", milho_sp: "SP" },
    "Farelo de soja": { farelo: "GO", farelo_mt: "MT", farelo_sc: "SC", farelo_sp: "SP" },
    "Boi gordo": { ub_go: "GO", ub_mg: "MG", ub_ms: "MS", ub_mt: "MT", ub_pr: "PR", ub_sc: "SC", ub_sp: "SP" }
  };
  function mediana(v) { v = v.slice().sort(function (a, b) { return a - b; }); var n = v.length; return n % 2 ? v[(n - 1) / 2] : (v[n / 2 - 1] + v[n / 2]) / 2; }
  function camposUsados() {
    var s = {};
    RELACOES.forEach(function (r) { s[r.a] = 1; s[r.b] = 1; });
    RESUMO.forEach(function (x) { s[x[1]] = 1; });
    PRECOS_DF.forEach(function (p) { s[p[2]] = 1; });
    return Object.keys(s);
  }
  function verificar(meses, atual, anterior) {
    var alertas = [], i = meses.indexOf(atual), recentes = meses.slice(Math.max(0, i - 3), i);
    camposUsados().forEach(function (k) {
      var nunca = !meses.some(function (m) { return k in m; });
      var sumiu = !nunca && !(k in atual) && recentes.length && recentes.every(function (m) { return k in m; });
      if (nunca) alertas.push({ tipo: "estrutura", campo: k, mes: atual.mes, texto: "Campo " + k + " não existe na base do painel. O painel pode ter mudado o nome do campo; ajuste src/painel-calc.js." });
      else if (sumiu) alertas.push({ tipo: "estrutura", campo: k, mes: atual.mes, texto: "Campo " + k + " lançado nos meses anteriores e ausente em " + atual.mes + " (lançamento pendente ou campo renomeado)." });
    });
    Object.keys(PRACAS).forEach(function (prod) {
      var ks = Object.keys(PRACAS[prod]).filter(function (k) { return pos(atual[k]); });
      ks.forEach(function (k) {
        var outros = ks.filter(function (j) { return j !== k; }).map(function (j) { return atual[j]; });
        if (outros.length < 2) return;
        var md = mediana(outros), r = atual[k] / md;
        if (r < 0.5 || r > 1.5) alertas.push({ tipo: "valor", campo: k, mes: atual.mes,
          texto: prod + " " + PRACAS[prod][k] + " em " + atual.mes + ": " + atual[k] + ", contra mediana de " + (+md.toFixed(2)) + " nas demais praças. Conferir unidade e série da fonte." });
      });
    });
    if (anterior) camposUsados().forEach(function (k) {
      if (pos(atual[k]) && pos(anterior[k]) && Math.abs(atual[k] / anterior[k] - 1) > 0.4 && !alertas.some(function (a) { return a.campo === k; }))
        alertas.push({ tipo: "valor", campo: k, mes: atual.mes, texto: "Campo " + k + " variou " + Math.round((atual[k] / anterior[k] - 1) * 100) + "% de " + anterior.mes + " para " + atual.mes + ". Conferir." });
    });
    return alertas;
  }

  function calcular(docsMeses, docsLanc, docsIndices) {
    // Último mês aprovado para publicação pelo NEAGRO-DF
    var MES_APROVADO = "set/26";

    var meses = mesclar(docsMeses, docsLanc).filter(function (m) {
      return ordem(m.mes) <= ordem(MES_APROVADO);
    });

    var comDados = meses.filter(function (m) {
      return pos(m.milho) && pos(m.farelo);
    });

    if (!comDados.length) return null;

    var atual = comDados[comDados.length - 1];
    var anterior = comDados.length > 1 ? comDados[comDados.length - 2] : null;

    var ate = meses.filter(function (m) {
      return ordem(m.mes) <= ordem(atual.mes);
    });

    var semaforo = [], alertas = verificar(meses, atual, anterior);



    var suspeito = {}; alertas.forEach(function (a) { if (a.tipo === "valor") suspeito[a.campo] = 1; });
    RELACOES.forEach(function (r) {
      var serie = ate.filter(function (m) { return pos(m[r.a]) && pos(m[r.b]); }).map(function (m) { return m[r.a] / m[r.b]; });
      if (!(pos(atual[r.a]) && pos(atual[r.b])) || !serie.length) return;
      var irt = atual[r.a] / atual[r.b];
      var media = serie.reduce(function (s, v) { return s + v; }, 0) / serie.length;
      var desvio = irt / media - 1;
      semaforo.push({ cadeia: r.cadeia, relacao: r.relacao, irt: +irt.toFixed(4), casas: r.casas, ler: r.ler,
        media: +media.toFixed(4), meses: serie.length, sinal: desvio < -0.05 ? "favoravel" : desvio > 0.05 ? "desfavoravel" : "normal", conferir: !!(suspeito[r.a] || suspeito[r.b]) });
    });
    var resumo = RESUMO.map(function (x) {
      var a = atual[x[1]], b = anterior ? anterior[x[1]] : null;
      return pos(a) && pos(b) ? { item: x[0], variacao: +((a / b - 1) * 100).toFixed(2) } : null;
    }).filter(Boolean);
    var precos = {};
    PRECOS_DF.forEach(function (p) {
      var a = atual[p[2]], b = anterior ? anterior[p[2]] : null;
      if (pos(a)) precos[p[0]] = { nome: p[1], valor: +a.toFixed(4), unidade: p[3], casas: p[4], variacao: pos(b) ? +((a / b - 1) * 100).toFixed(2) : null };
    });
    /* Séries para os gráficos do portal: últimos 13 meses até o mês em análise. */
    var janela = ate.slice(-13), series = { meses: janela.map(function (m) { return m.mes; }), irt: {}, precos: {} };
    RELACOES.forEach(function (r) {
      if (DESTAQUES.indexOf(r.relacao) < 0) return;
      series.irt[r.relacao] = janela.map(function (m) { return pos(m[r.a]) && pos(m[r.b]) ? +(m[r.a] / m[r.b]).toFixed(4) : null; });
    });
    ["sdf", "milho_df", "ovdf", "ledf"].forEach(function (k) {
      series.precos[k] = janela.map(function (m) { return pos(m[k]) ? +m[k].toFixed(4) : null; });
    });
    var idx = (docsIndices || []).map(function (d) { return plano(d.fields); }).filter(function (i) { return i.mes === atual.mes; })[0] || {};
    return {
      mes: atual.mes, mes_anterior: anterior ? anterior.mes : null, base: "mai/26",
      indices: { ipca: typeof idx.var_ipca === "number" ? idx.var_ipca : null, igpdi: typeof idx.var_igpdi === "number" ? idx.var_igpdi : null },
      resumo: resumo, semaforo: semaforo, precos: precos, series: series, destaques: DESTAQUES,
      gta_suinos: pos(atual.gta_ent_tot) || pos(atual.gta_sai_tot) ? { entrada: atual.gta_ent_tot || 0, saida: atual.gta_sai_tot || 0 } : null,
      meses_registrados: comDados.length,
      relacoes_esperadas: RELACOES.length,
      alertas: alertas
    };
  }

  /* Movimentação de animais (GTA) no DF, a partir do quadro GTA_DF publicado no código do painel. */
  var ESPECIES = [["bov", "Bovinos"], ["ave", "Aves vivas"], ["cap", "Caprinos"], ["ovi", "Ovinos"]];
  function gta(G, suinos, mesSuinos) {
    if (!G || !G.meses) return null;
    var i = G.meses.length - 1;
    if (G.parcial && G.meses[i] === G.parcial) i -= 1;
    if (i < 0) return null;
    var linhas = ESPECIES.map(function (e) {
      var s = G[e[0]]; if (!s || !s.entrada || !s.saida) return null;
      return { especie: e[1], entrada: s.entrada.total[i] || 0, saida: s.saida.total[i] || 0, interno: s.interno ? (s.interno.total[i] || 0) : null };
    }).filter(Boolean);
    if (suinos && mesSuinos === G.meses[i]) linhas.unshift({ especie: "Suínos", entrada: suinos.entrada, saida: suinos.saida, interno: null });
    return { mes: G.meses[i], parcial: G.parcial || null, ate: G.fim || null, linhas: linhas };
  }

  var api = { calcular: calcular, gta: gta, mesclar: mesclar, ordem: ordem, camposUsados: camposUsados };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else raiz.PainelNEAGRO = api;
})(typeof window !== "undefined" ? window : this);
