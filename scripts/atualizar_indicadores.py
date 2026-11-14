"""Indicadores econômicos do portal NEAGRO-DF (seção "Indicadores do agro").

Lê fontes oficiais e grava em data/dados.json, na chave "cartoes", grupos de cartões que a
página desenha sem precisar de código novo. Cada cartão traz fonte, link, endpoint e data de
extração. Se uma fonte falhar, o cartão anterior é mantido e o erro vai para o log.

Fontes
  IBGE (SIDRA 5938): PIB dos Municípios e valor adicionado por setor, DF e RIDE-DF
  MDIC/Secex (API ComexStat): exportações da RIDE-DF, grãos e fertilizantes, produtos
      agropecuários (seções I a IV do SH) e comércio com a União Europeia
  USDA/FAS (PSD Online, arquivos CSV): oferta e demanda mundial de soja, milho e carnes
  Comissão Europeia (Agri-food Data Portal, API pública): preços de carnes e leite na UE

Uso:  python scripts/atualizar_indicadores.py   (só biblioteca padrão do Python 3.9+)
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
import unicodedata
import urllib.request
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DADOS = RAIZ / "data" / "dados.json"
BRT = timezone(timedelta(hours=-3))
HOJE = datetime.now(BRT).strftime("%Y-%m-%d")
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
UA = {"User-Agent": "NEAGRO-DF/1.0 (FAV/UnB; portal de dados do agronegocio)"}
COMEX = "https://api-comexstat.mdic.gov.br"
COMEX_LINK = "https://comexstat.mdic.gov.br/pt/geral"


def log(msg: str) -> None:
    print(f"[{datetime.now(BRT):%H:%M:%S}] {msg}", file=sys.stderr)


def baixar(url: str, timeout: int = 90, dados: dict | None = None) -> bytes:
    corpo = json.dumps(dados).encode() if dados is not None else None
    cab = dict(UA, **({"Content-Type": "application/json"} if corpo else {}))
    req = urllib.request.Request(url, data=corpo, headers=cab)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def num(txt) -> float | None:
    try:
        return float(str(txt).replace(",", "."))
    except (TypeError, ValueError):
        return None


def var(a, b) -> float | None:
    return round((a / b - 1) * 100, 1) if a and b else None


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower().replace("’", "'").strip()


def fbr(v: float, c: int = 1) -> str:
    return f"{v:,.{c}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pct(v) -> str:
    return "" if v is None else f"{'+' if v > 0 else ''}{fbr(v)}%"


def curto(txt: str, n: int = 40) -> str:
    """Nome do produto sem o detalhamento após a vírgula e cortado em palavra inteira."""
    t = re.sub(r",.*", "", txt).strip()
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0].rstrip(" ;,(") + "…"


def cartao(**k) -> dict:
    k.setdefault("extraido_em", HOJE)
    k.setdefault("automatico", True)
    return k


# ---------------------------------------------------------------- IBGE: PIB dos Municípios
def sidra(caminho: str):
    url = "https://apisidra.ibge.gov.br/values" + caminho
    d = json.loads(baixar(url).decode("utf-8"))
    return url, d[0], d[1:]


def col(cab: dict, nome: str) -> str:
    return next(k for k, v in cab.items() if v == nome)


def pib_municipal(dados: dict) -> list[dict]:
    mun = dados["ride"]["municipios"]
    cods = ",".join(str(m[2]) for m in mun)
    nomes = {str(m[2]): f"{m[0]} ({m[1]})" for m in mun}
    url, cab, linhas = sidra(f"/t/5938/n6/{cods}/v/37/p/last%201")
    kc, ka = col(cab, "Município (Código)"), col(cab, "Ano")
    ano = linhas[0][ka]
    pib = sorted(((nomes[l[kc]], num(l["V"])) for l in linhas if num(l["V"])), key=lambda x: -x[1])
    total = sum(v for _, v in pib)
    df = sum(v for n, v in pib if n.endswith("(DF)"))
    c1 = cartao(id="pib_ride", titulo=f"PIB dos municípios da RIDE-DF, {ano}",
                sub=(f"Total da RIDE-DF: R$ {fbr(total / 1e6)} bilhões, dos quais R$ {fbr(df / 1e6)} bilhões no Distrito Federal "
                     f"({fbr(df / total * 100)}%). Abaixo, os demais municípios, em R$ bilhões a preços correntes"),
                tipo="barras", barras=[[n, round(v / 1e6, 2), False] for n, v in pib if not n.endswith("(DF)")][:12], casas=2,
                fonte="IBGE, PIB dos Municípios, tabela 5938", link="https://sidra.ibge.gov.br/tabela/5938",
                endpoint=url)
    # Valor adicionado por setor: o SIDRA ainda não traz a abertura setorial dos anos mais recentes,
    # por isso cada variável usa o último ano em que há dado.
    vab = [("513", "Agropecuária"), ("517", "Indústria"), ("6575", "Serviços"), ("525", "Administração pública")]
    url2, cab2, l2 = sidra(f"/t/5938/n1/all/n3/53/n6/{cods}/v/{','.join(v for v, _ in vab)}/p/last%206")
    kv, ka2 = col(cab2, "Variável (Código)"), col(cab2, "Ano")
    anos = sorted({l[ka2] for l in l2 if num(l["V"]) is not None})
    if not anos:
        raise ValueError("sem valor adicionado por setor no SIDRA")
    av = anos[-1]
    soma = {"Brasil": {}, "Distrito Federal": {}, "RIDE-DF": {}}
    for l in l2:
        v = num(l["V"])
        if l[ka2] != av or v is None:
            continue
        alvo = "Brasil" if l["NN"] == "Brasil" else ("Distrito Federal" if l["NN"].startswith("Unidade") else "RIDE-DF")
        soma[alvo][l[kv]] = soma[alvo].get(l[kv], 0) + v
    linhas_t = []
    for terr, s in soma.items():
        tot = sum(s.values())
        if tot:
            linhas_t.append([terr] + [round(s.get(v, 0) / tot * 100, 1) for v, _ in vab])
    c2 = cartao(id="vab_setor", titulo=f"Estrutura do valor adicionado, {av}",
                sub="Participação de cada setor no valor adicionado bruto, %",
                tipo="tabela", colunas=["Território"] + [n for _, n in vab], linhas=linhas_t, casas=1,
                nota=(f"O IBGE publicou o PIB municipal até {ano}, mas a abertura por setor no SIDRA vai até {av}."
                      if av != ano else ""),
                fonte="IBGE, PIB dos Municípios, tabela 5938", link="https://sidra.ibge.gov.br/tabela/5938",
                endpoint=url2)
    log(f"PIB municipal {ano} e valor adicionado {av} atualizados")
    return [c1, c2]


# ---------------------------------------------------------------- MDIC: ComexStat
def comex(rota: str, corpo: dict) -> list[dict]:
    d = json.loads(baixar(f"{COMEX}{rota}?language=pt", dados=corpo).decode("utf-8"))
    return d["data"]["list"]


def periodo() -> tuple[int, int]:
    d = json.loads(baixar(f"{COMEX}/general/dates/updated").decode("utf-8"))["data"]
    return int(d["year"]), int(d["monthNumber"])


def acum(rota, fluxo, filtros, det, ano, mes, metricas=("metricFOB", "metricKG")):
    corpo = {"flow": fluxo, "monthDetail": False, "period": {"from": f"{ano}-01", "to": f"{ano}-{mes:02d}"},
             "filters": filtros, "details": det, "metrics": list(metricas)}
    return comex(rota, corpo)


def rot(ano, mes) -> str:
    return f"jan a {MESES[mes - 1]}/{ano}" if mes > 1 else f"jan/{ano}"


def municipios_comex(dados: dict) -> list[str]:
    tab = json.loads(baixar(f"{COMEX}/tables/cities?language=pt").decode("utf-8"))["data"]
    idx = {norm(c["text"]): c["id"] for c in tab}
    ids = [idx.get(norm(f"{m[0]} - {m[1]}")) for m in dados["ride"]["municipios"]]
    faltam = [m[0] for m, i in zip(dados["ride"]["municipios"], ids) if not i]
    if faltam:
        log(f"ComexStat: municípios sem código: {', '.join(faltam)}")
    return [i for i in ids if i]


def comex_ride(dados: dict, ano: int, mes: int) -> dict:
    ids = municipios_comex(dados)
    f = [{"filter": "city", "values": ids}]
    atual = acum("/cities", "export", f, ["heading"], ano, mes, ("metricFOB",))
    ant = acum("/cities", "export", f, [], ano - 1, mes, ("metricFOB",))
    tot = sum(num(x["metricFOB"]) for x in atual)
    tot_ant = sum(num(x["metricFOB"]) for x in ant)
    prods = sorted(atual, key=lambda x: -num(x["metricFOB"]))[:10]
    v = var(tot, tot_ant)
    return cartao(id="comex_ride", titulo=f"Exportações da RIDE-DF, {rot(ano, mes)}",
                  sub=(f"US$ milhões FOB por produto (SH4). Total: US$ {fbr(tot / 1e6)} milhões"
                       + (f", {pct(v)} sobre o mesmo período de {ano - 1}" if v is not None else "")),
                  tipo="barras", casas=1,
                  barras=[[curto(x["heading"]), round(num(x["metricFOB"]) / 1e6, 1), False] for x in prods],
                  nota="Soma dos 34 municípios da RIDE-DF, pelo domicílio fiscal da empresa exportadora.",
                  fonte="MDIC/Secex, ComexStat, exportações por município", link="https://comexstat.mdic.gov.br/pt/municipio",
                  endpoint=f"{COMEX}/cities")


GRAOS = [("Soja em grão", "export", ["1201"]), ("Milho", "export", ["1005"]),
         ("Farelo de soja", "export", ["2304"]), ("Fertilizantes (importação)", "import", ["3102", "3103", "3104", "3105"])]


def comex_graos(ano: int, mes: int) -> dict:
    linhas = []
    for nome, fluxo, sh in GRAOS:
        f = [{"filter": "heading", "values": sh}]
        corpo = lambda a, m1, m2: {"flow": fluxo, "monthDetail": False,  # noqa: E731
                                   "period": {"from": f"{a}-{m1:02d}", "to": f"{a}-{m2:02d}"},
                                   "filters": f, "details": [], "metrics": ["metricFOB", "metricKG"]}
        kg = lambda r: sum(num(x["metricKG"]) or 0 for x in r)  # noqa: E731
        m_at, m_an = kg(comex("/general", corpo(ano, mes, mes))), kg(comex("/general", corpo(ano - 1, mes, mes)))
        a_at, a_an = kg(comex("/general", corpo(ano, 1, mes))), kg(comex("/general", corpo(ano - 1, 1, mes)))
        linhas.append([nome, round(m_at / 1e9, 2), var(m_at, m_an), round(a_at / 1e9, 2), var(a_at, a_an)])
    return cartao(id="comex_graos", titulo=f"Grãos e fertilizantes, {MESES[mes - 1]}/{ano}",
                  sub="Brasil, milhões de toneladas e variação sobre o mesmo período do ano anterior, %",
                  tipo="tabela", casas=2,
                  colunas=["Produto", f"{MESES[mes - 1]}/{ano}", "Var. %", rot(ano, mes), "Var. %"], linhas=linhas,
                  nota="Fertilizantes: posições SH 3102 a 3105 (nitrogenados, fosfatados, potássicos e misturas).",
                  fonte="MDIC/Secex, ComexStat", link=COMEX_LINK, endpoint=f"{COMEX}/general")


def comex_agro(ano: int, mes: int) -> dict:
    f = [{"filter": "section", "values": ["I", "II", "III", "IV"]}]
    val = {}
    for fluxo in ("export", "import"):
        for a in (ano, ano - 1):
            val[(fluxo, a)] = sum(num(x["metricFOB"]) for x in acum("/general", fluxo, f, [], a, mes, ("metricFOB",)))
    lin = []
    for nome, k in (("Exportações", "export"), ("Importações", "import")):
        lin.append([nome, round(val[(k, ano)] / 1e9, 2), round(val[(k, ano - 1)] / 1e9, 2), var(val[(k, ano)], val[(k, ano - 1)])])
    s1, s0 = val[("export", ano)] - val[("import", ano)], val[("export", ano - 1)] - val[("import", ano - 1)]
    lin.append(["Saldo", round(s1 / 1e9, 2), round(s0 / 1e9, 2), var(s1, s0)])
    return cartao(id="balanca_agro", titulo=f"Balança de produtos agropecuários, {rot(ano, mes)}",
                  sub="Brasil, US$ bilhões FOB", tipo="tabela", casas=2,
                  colunas=["", str(ano), str(ano - 1), "Var. %"], linhas=lin,
                  nota=("Produtos das seções I a IV do Sistema Harmonizado (animais, vegetais, óleos e alimentos). "
                        "O Agrostat/MAPA usa um conceito mais amplo de agronegócio, que inclui celulose, couros e fibras."),
                  fonte="MDIC/Secex, ComexStat", link=COMEX_LINK, endpoint=f"{COMEX}/general",
                  link2="https://indicadores.agricultura.gov.br/agrostat/index.htm")


def comex_ue(ano: int, mes: int) -> dict:
    f = [{"filter": "economicBlock", "values": [22]}]
    ex = acum("/general", "export", f, ["heading"], ano, mes, ("metricFOB",))
    ex0 = sum(num(x["metricFOB"]) for x in acum("/general", "export", f, [], ano - 1, mes, ("metricFOB",)))
    im = sum(num(x["metricFOB"]) for x in acum("/general", "import", f, [], ano, mes, ("metricFOB",)))
    im0 = sum(num(x["metricFOB"]) for x in acum("/general", "import", f, [], ano - 1, mes, ("metricFOB",)))
    tot = sum(num(x["metricFOB"]) for x in ex)
    top = sorted(ex, key=lambda x: -num(x["metricFOB"]))[:8]
    fx = lambda v: fbr(v / 1e9)  # noqa: E731
    sinal = lambda v: "" if v is None else f" ({pct(v)})"  # noqa: E731
    return cartao(id="comex_ue", titulo=f"Comércio Brasil–União Europeia, {rot(ano, mes)}",
                  sub=(f"Exportações: US$ {fx(tot)} bilhões{sinal(var(tot, ex0))}. Importações: US$ {fx(im)} bilhões"
                       f"{sinal(var(im, im0))}. Principais produtos exportados, US$ milhões FOB"),
                  tipo="barras", casas=0,
                  barras=[[curto(x["heading"]), round(num(x["metricFOB"]) / 1e6), False] for x in top],
                  nota="Variação sobre o mesmo período do ano anterior. Bloco econômico União Europeia (27 países).",
                  fonte="MDIC/Secex, ComexStat, bloco União Europeia", link=COMEX_LINK, endpoint=f"{COMEX}/general")


# ---------------------------------------------------------------- USDA: PSD Online
PSD = "https://apps.fas.usda.gov/psdonline/downloads/psd_{}_csv.zip"
PSD_ITENS = [("oilseeds", "2222000", "Soja"), ("grains_pulses", "0440000", "Milho"),
             ("livestock", "0111000", "Carne bovina"), ("livestock", "0113000", "Carne suína"),
             ("livestock", "0115000", "Carne de frango")]


def usda() -> dict:
    cache, linhas, safras, rel = {}, [], set(), set()
    for arq, cod, nome in PSD_ITENS:
        if arq not in cache:
            z = zipfile.ZipFile(io.BytesIO(baixar(PSD.format(arq), timeout=180)))
            cache[arq] = list(csv.DictReader(io.TextIOWrapper(z.open(z.namelist()[0]), encoding="utf-8-sig")))
        reg = [r for r in cache[arq] if r["Commodity_Code"] == cod]
        ano = max(int(r["Market_Year"]) for r in reg)
        reg = [r for r in reg if int(r["Market_Year"]) == ano]
        soma = lambda attr, pais=None: sum(num(r["Value"]) or 0 for r in reg  # noqa: E731
                                           if r["Attribute_Description"] == attr and (pais is None or r["Country_Name"] == pais))
        pb, eb, pm, em = soma("Production", "Brazil"), soma("Exports", "Brazil"), soma("Production"), soma("Exports")
        un = next((r["Unit_Description"] for r in reg if r["Attribute_Description"] == "Production"), "")
        fator = 1000 if "1000 MT" in un else 1  # carnes vêm em mil t equivalente-carcaça
        linhas.append([nome, round(pb / fator, 1), round(eb / fator, 1), round(pm / fator, 1),
                       round(pb / pm * 100, 1) if pm else None, round(eb / em * 100, 1) if em else None])
        safras.add(f"{ano}/{str(ano + 1)[2:]}" if cod in ("2222000", "0440000") else str(ano))
        rel.update(f"{r['Calendar_Year']}-{r['Month']}" for r in reg)
    ult = max(rel)
    return cartao(id="usda_psd", titulo="Oferta mundial e o Brasil, projeções do USDA",
                  sub=f"Milhões de toneladas (carnes em equivalente-carcaça). Safras e anos: {', '.join(sorted(safras))}",
                  tipo="tabela", casas=1,
                  colunas=["Produto", "Produção Brasil", "Exportação Brasil", "Produção mundial",
                           "Brasil na produção, %", "Brasil na exportação, %"], linhas=linhas,
                  nota=f"Estimativas do relatório de {MESES[int(ult[5:7]) - 1]}/{ult[:4]} (WASDE/PSD). Exportação mundial = soma das exportações dos países.",
                  fonte="USDA/FAS, Production, Supply and Distribution (PSD Online)",
                  link="https://apps.fas.usda.gov/psdonline/app/index.html#/app/downloads",
                  endpoint=PSD.format("{oilseeds,grains_pulses,livestock}"))


# ---------------------------------------------------------------- Comissão Europeia
UE_API = "https://ec.europa.eu/agrifood/api"
UE_ITENS = [("Carcaça bovina (classe R3)", "beef", "€/100 kg"), ("Carcaça suína (classe E)", "pigmeat", "€/100 kg"),
            ("Frango inteiro", "poultry", "€/100 kg"), ("Leite cru ao produtor", "rawMilk", "€/100 kg")]


def preco(txt) -> float | None:
    return num(re.sub(r"[^\d,.\-]", "", str(txt)).replace(",", "")) if txt not in (None, "") else None


def precos_ue() -> dict:
    hoje = datetime.now(BRT)
    ini = (hoje - timedelta(days=120)).strftime("%d/%m/%Y")
    linhas, erros = [], []
    for nome, rota, un in UE_ITENS:
        try:
            url = f"{UE_API}/{rota}/prices?memberStateCodes=EU&beginDate={ini}&endDate={hoje:%d/%m/%Y}"
            reg = json.loads(baixar(url, timeout=20).decode("utf-8"))
            alvo = {"beef": "R3", "pigmeat": "E"}.get(rota)
            if alvo:  # prefere a classe de referência quando a API informa a classificação
                reg = [r for r in reg if any(str(v).upper().strip() in (alvo, "CLASS " + alvo) or str(v).upper().startswith(alvo + " ")
                                             for k, v in r.items() if k not in ("price", "unit"))] or reg
            reg = [r for r in reg if preco(r.get("price")) is not None]
            reg.sort(key=lambda r: datetime.strptime(r.get("beginDate", "01/01/1900"), "%d/%m/%Y"))
            if not reg:
                raise ValueError("sem preços")
            u, p = reg[-1], reg[0]
            linhas.append([nome, preco(u["price"]), u.get("unit", un), u.get("beginDate", ""),
                           var(preco(u["price"]), preco(p["price"]))])
        except Exception as e:  # noqa: BLE001
            erros.append(nome)
            log(f"Preços UE ({nome}): falhou ({e})")
    if not linhas:
        raise ValueError("API de preços da Comissão Europeia indisponível")
    return cartao(id="precos_ue", titulo="Preços agropecuários na União Europeia",
                  sub="Média da UE no último período informado e variação em cerca de quatro meses, %",
                  tipo="tabela", casas=2, colunas=["Produto", "Preço", "Unidade", "Período", "Var. %"], linhas=linhas,
                  nota=("Sem dados recentes para: " + ", ".join(erros) + ".") if erros else "",
                  fonte="Comissão Europeia, Agri-food Data Portal", link="https://agridata.ec.europa.eu/extensions/DataPortal/home.html",
                  endpoint=f"{UE_API}/{{beef,pigmeat,poultry,rawMilk}}/prices")


PROJECOES = cartao(
    id="projecoes", titulo="Projeções de longo prazo", tipo="links", automatico=False,
    sub="Relatórios anuais de referência sobre oferta, demanda e comércio agrícola na próxima década",
    links=[["USDA Agricultural Projections (até 2035)", "https://www.ers.usda.gov/topics/farm-economy/agricultural-baseline-projections"],
           ["EU Agricultural Outlook 2025-2035 (Comissão Europeia)", "https://agriculture.ec.europa.eu/data-and-analysis/markets/outlook/medium-term_en"],
           ["OECD-FAO Agricultural Outlook 2025-2034", "https://www.agri-outlook.org/"],
           ["Projeções do Agronegócio, Brasil 2024/25 a 2034/35 (MAPA)", "https://www.gov.br/agricultura/pt-br/assuntos/politica-agricola/todas-publicacoes-de-politica-agricola/projecoes-do-agronegocio"]],
    fonte="USDA, Comissão Europeia, OCDE/FAO e MAPA", link="https://www.ers.usda.gov/topics/farm-economy/agricultural-baseline-projections",
    endpoint="links para os relatórios oficiais (publicação anual)")


# ---------------------------------------------------------------- montagem
GRUPOS = [("territorio", "Economia do DF e da RIDE"), ("comercio", "Comércio exterior"), ("mundo", "Mundo: USDA e União Europeia")]


def main() -> None:
    dados = json.loads(DADOS.read_text(encoding="utf-8"))
    ant = {c["id"]: c for g in dados.get("cartoes", []) for c in g.get("cartoes", [])}
    novo: dict[str, dict] = {}

    def tenta(nome, f, *a):
        try:
            r = f(*a)
            for c in (r if isinstance(r, list) else [r]):
                novo[c["id"]] = c
        except Exception as e:  # noqa: BLE001
            log(f"{nome}: falhou ({e}); mantido o cartão anterior")

    tenta("PIB municipal", pib_municipal, dados)
    try:
        ano, mes = periodo()
        tenta("Exportações da RIDE", comex_ride, dados, ano, mes)
        tenta("Grãos e fertilizantes", comex_graos, ano, mes)
        tenta("Balança agropecuária", comex_agro, ano, mes)
        tenta("Comércio Brasil-UE", comex_ue, ano, mes)
    except Exception as e:  # noqa: BLE001
        log(f"ComexStat: falhou ({e})")
    tenta("USDA", usda)
    tenta("Preços na UE", precos_ue)
    novo["projecoes"] = PROJECOES
    if "precos_ue" not in novo and "precos_ue" not in ant:
        novo["precos_ue"] = cartao(
            id="precos_ue", titulo="Preços agropecuários na União Europeia", tipo="links", automatico=True,
            sub="A API pública da Comissão Europeia está fora do ar; o robô tenta de novo a cada atualização. Consulte os painéis oficiais:",
            links=[["Agri-food Data Portal: carnes, leite, grãos e insumos", "https://agridata.ec.europa.eu/extensions/DataPortal/home.html"],
                   ["Observatórios de mercado da Comissão Europeia", "https://agriculture.ec.europa.eu/data-and-analysis/markets/overviews/market-observatories_en"]],
            fonte="Comissão Europeia, Agri-food Data Portal", link="https://agridata.ec.europa.eu/extensions/DataPortal/home.html",
            endpoint=f"{UE_API}/{{beef,pigmeat,poultry,rawMilk}}/prices")
    ordem = {"territorio": ["pib_ride", "vab_setor", "comex_ride"],
             "comercio": ["balanca_agro", "comex_graos", "comex_ue"],
             "mundo": ["usda_psd", "precos_ue", "projecoes"]}
    dados["cartoes"] = [{"id": g, "titulo": t, "cartoes": [novo.get(i) or ant.get(i) for i in ordem[g] if novo.get(i) or ant.get(i)]}
                        for g, t in GRUPOS]
    DADOS.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    log("data/dados.json gravado (cartões de indicadores)")


if __name__ == "__main__":
    main()
