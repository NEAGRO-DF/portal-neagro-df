"""Robô de atualização do portal NEAGRO-DF.

Busca os dados públicos que alimentam o portal e regrava data/dados.json,
registrando para cada item a fonte, o endpoint e a data de extração.
Se uma fonte falhar, o valor anterior é mantido e o erro vai para o log.

Fontes automáticas
  Banco Central (SGS): dólar (10813), euro (21619), Selic meta (432), IPCA 12 meses (13522),
      IGP-M (189, acumulado em 12 meses)
  IBGE (SIDRA): PAM tabela 5457 (DF e municípios da RIDE), PPM tabela 3939 (DF)
  IBGE (SIDRA): Contas Nacionais Trimestrais, tabela 5932 (PIB por setor)
  FAO: Food Price Index e subíndices (CSV mensal da FAO)
  Notícias: feeds RSS listados em data/fontes_noticias.json

Entradas manuais
  data/manual.json: indicadores Cepea/Esalq (o Cepea não oferece API pública)
  e textos de conjuntura. A coordenação atualiza esse arquivo semanalmente.

Uso:  python scripts/atualizar_dados.py   (só biblioteca padrão do Python 3.9+)
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DADOS = RAIZ / "data" / "dados.json"
MANUAL = RAIZ / "data" / "manual.json"
FEEDS = RAIZ / "data" / "fontes_noticias.json"
BRT = timezone(timedelta(hours=-3))
HOJE = datetime.now(BRT).strftime("%Y-%m-%d")
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
UA = {"User-Agent": "NEAGRO-DF/1.0 (FAV/UnB; portal de dados do agronegocio)"}


def log(msg: str) -> None:
    print(f"[{datetime.now(BRT):%H:%M:%S}] {msg}", file=sys.stderr)


def baixar(url: str, timeout: int = 40) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def baixar_json(url: str):
    return json.loads(baixar(url).decode("utf-8"))


def num(txt: str) -> float | None:
    try:
        return float(str(txt).replace(",", "."))
    except ValueError:
        return None  # SIDRA usa "-", "..." e "X" para dados ausentes ou sigilosos


# ---------------------------------------------------------------- Banco Central
def sgs(codigo: int, n: int):
    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados/ultimos/{n}?formato=json"
    return url, baixar_json(url)


def atualizar_bcb(ind: dict) -> None:
    alvo = {i["id"]: i for i in ind}
    try:
        url, s = sgs(10813, 20)
        i = alvo["dolar"]
        i.update(valor=float(s[-1]["valor"]), referencia=s[-1]["data"], endpoint=url, extraido_em=HOJE,
                 serie=[[p["data"][:5], float(p["valor"])] for p in s],
                 variacao_pct=round((float(s[-1]["valor"]) / float(s[0]["valor"]) - 1) * 100, 2),
                 variacao_desc="em 20 pregões")
        log("Câmbio atualizado")
    except Exception as e:  # noqa: BLE001
        log(f"Câmbio: falhou ({e}); mantido o valor anterior")
    try:
        url, s = sgs(432, 1)
        alvo["selic"].update(valor=float(s[-1]["valor"]), endpoint=url, extraido_em=HOJE,
                             referencia=f"vigente em {datetime.now(BRT):%m/%Y}")
        log("Selic atualizada")
    except Exception as e:  # noqa: BLE001
        log(f"Selic: falhou ({e})")
    try:
        url, s = sgs(13522, 12)

        def rot(p):
            _, m, y = p["data"].split("/")
            return f"{MESES[int(m) - 1]}/{y[2:]}"

        i = alvo["ipca12"]
        i.update(valor=float(s[-1]["valor"]), referencia=rot(s[-1]).replace("/", "/20"), endpoint=url,
                 extraido_em=HOJE, serie=[[rot(p), float(p["valor"])] for p in s],
                 variacao_desc=f"{rot(s[-2])}: {s[-2]['valor'].replace('.', ',')}%")
        log("IPCA atualizado")
    except Exception as e:  # noqa: BLE001
        log(f"IPCA: falhou ({e})")
    def novo(base: dict) -> dict:
        """Devolve o indicador já existente ou o cria logo depois dos indicadores macro."""
        if base["id"] not in alvo:
            pos = max((k for k, x in enumerate(ind) if x.get("grupo") == "macro"), default=len(ind) - 1) + 1
            ind.insert(pos, base)
            alvo[base["id"]] = base
        return alvo[base["id"]]

    try:
        url, s = sgs(21619, 20)
        i = novo({"id": "euro", "nome": "Euro", "unidade": "R$/€", "casas": 4, "grupo": "macro",
                  "fonte": "Banco Central do Brasil, SGS série 21619 (taxa de câmbio livre, euro, venda)",
                  "link": "https://www3.bcb.gov.br/sgspub/", "automatico": True})
        i.update(valor=float(s[-1]["valor"]), referencia=s[-1]["data"], endpoint=url, extraido_em=HOJE,
                 variacao_pct=round((float(s[-1]["valor"]) / float(s[0]["valor"]) - 1) * 100, 2),
                 variacao_desc="em 20 pregões")
        log("Euro atualizado")
    except Exception as e:  # noqa: BLE001
        log(f"Euro: falhou ({e})")
    try:
        url, s = sgs(189, 13)  # IGP-M mensal (FGV); acumulado em 12 meses calculado pelo produto das variações

        def ac(lista):
            f = 1.0
            for p in lista:
                f *= 1 + float(p["valor"]) / 100
            return (f - 1) * 100

        _, m, y = s[-1]["data"].split("/")
        i = novo({"id": "igpm12", "nome": "IGP-M 12 meses", "unidade": "%", "casas": 2, "grupo": "macro",
                  "fonte": "FGV via Banco Central do Brasil, SGS série 189 (IGP-M mensal, acumulado em 12 meses)",
                  "link": "https://portalibre.fgv.br/igp", "automatico": True})
        i.update(valor=round(ac(s[-12:]), 2), referencia=f"{MESES[int(m) - 1]}/{y}", endpoint=url, extraido_em=HOJE,
                 variacao_pct=None, variacao_desc=f"no mês: {s[-1]['valor'].replace('.', ',')}%")
        log("IGP-M atualizado")
    except Exception as e:  # noqa: BLE001
        log(f"IGP-M: falhou ({e})")


# ---------------------------------------------------------------- IBGE / SIDRA
def sidra(caminho: str):
    """Retorna (url, cabeçalho, linhas) de uma consulta à API do SIDRA."""
    url = "https://apisidra.ibge.gov.br/values" + caminho
    dados = baixar_json(url)
    return url, dados[0], dados[1:]


def coluna(cab: dict, inicio: str) -> str:
    """Chave da coluna do SIDRA: nome exato primeiro; depois o que começa pelo nome, sem pegar a coluna "(Código)"."""
    alvo = inicio.lower()
    for k, v in cab.items():
        if str(v).lower() == alvo:
            return k
    for k, v in cab.items():
        if str(v).lower().startswith(alvo) and "(código)" not in str(v).lower():
            return k
    for k, v in cab.items():
        if str(v).lower().startswith(alvo):
            return k
    raise KeyError(inicio)


def atualizar_pam_df(df: dict) -> None:
    try:
        url, cab, linhas = sidra("/t/5457/n3/53/v/215/p/last%201/c782/allxt")
        kp, kano = coluna(cab, "Produto das lavouras"), coluna(cab, "Ano")
        prods = [(l[kp].split(" (")[0].replace(" Total", ""), num(l["V"])) for l in linhas]
        maior: dict[str, float] = {}
        for n, v in prods:  # café aparece como Total, Arábica e Canephora: fica o maior (Total)
            if v and v > maior.get(n, 0):
                maior[n] = v
        prods = sorted(maior.items(), key=lambda p: -p[1])
        _, _, tot = sidra("/t/5457/n3/53/v/215/p/last%201/c782/0")
        ano = linhas[0][kano]
        df["pam"].update(titulo=f"Valor da produção agrícola do Distrito Federal, {ano}",
                         produtos=[[n, int(v)] for n, v in prods[:12]], total=int(num(tot[0]["V"])),
                         endpoint=url, extraido_em=HOJE)
        log(f"PAM DF {ano} atualizada")
    except Exception as e:  # noqa: BLE001
        log(f"PAM DF: falhou ({e})")


def atualizar_ppm_df(df: dict) -> None:
    nomes = {"Bovino": "Bovinos", "Bubalino": "Bubalinos", "Equino": "Equinos", "Suíno - total": "Suínos",
             "Caprino": "Caprinos", "Ovino": "Ovinos", "Galináceos - total": "Galináceos"}
    try:
        url, cab, linhas = sidra("/t/3939/n3/53/v/all/p/last%201/c79/allxt")
        kr, kano = coluna(cab, "Tipo de rebanho"), coluna(cab, "Ano")
        reb = [(nomes[l[kr]], num(l["V"])) for l in linhas if l[kr] in nomes and num(l["V"])]
        reb.sort(key=lambda r: -r[1])
        ano = linhas[0][kano]
        df["ppm"].update(titulo=f"Efetivo dos rebanhos do Distrito Federal, {ano}",
                         rebanhos=[[n, int(v)] for n, v in reb], endpoint=url, extraido_em=HOJE)
        log(f"PPM DF {ano} atualizada")
    except Exception as e:  # noqa: BLE001
        log(f"PPM DF: falhou ({e})")


def atualizar_ride(ride: dict) -> None:
    codigos = ",".join(str(m[2]) for m in ride["municipios"])
    try:
        url, cab, linhas = sidra(f"/t/5457/n6/{codigos}/v/215/p/last%201/c782/0")
        kcod, kano = coluna(cab, "Município (Código)"), coluna(cab, "Ano")
        val = {int(l[kcod]): num(l["V"]) for l in linhas}
        for m in ride["municipios"]:
            if val.get(m[2]) is not None:
                m[3] = int(val[m[2]])
        ano = linhas[0][kano]
        ride.update(titulo=f"Valor da produção agrícola na RIDE-DF, {ano}",
                    endpoint=url, extraido_em=HOJE)
        log(f"RIDE {ano} atualizada ({len(val)} municípios)")
    except Exception as e:  # noqa: BLE001
        log(f"RIDE: falhou ({e})")


# ---------------------------------------------------------------- FAO
FAO_PAGINA = "https://www.fao.org/worldfoodsituation/foodpricesindex/en/"
FAO_SUB = [("Carnes", 2), ("Lácteos", 3), ("Cereais", 4), ("Óleos vegetais", 5), ("Açúcar", 6)]


def atualizar_fao(dados: dict) -> None:
    """Índice FAO de preços de alimentos e subíndices, lidos do CSV oficial da FAO."""
    try:
        html = baixar(FAO_PAGINA).decode("utf-8", "ignore").replace("&amp;", "&")
        m = re.search(r'href="([^"]*food_price_indices_data[^"]*\.csv[^"]*)"', html, re.I)
        if not m:
            raise ValueError("link do CSV não encontrado na página")
        csv_url = m.group(1) if m.group(1).startswith("http") else "https://www.fao.org" + m.group(1)
        linhas = list(csv.reader(io.StringIO(baixar(csv_url).decode("utf-8-sig", "ignore"))))
        serie = [l for l in linhas if l and re.match(r"\d{4}-\d{2}$", l[0].strip()) and num(l[1])]
        ult, ant = serie[-1], serie[-2]
        y, mth = ult[0].strip()[:7].split("-")
        ym, ya = f"{MESES[int(mth) - 1]}/{y}", ant[0].strip()[:7].split("-")
        i = next(x for x in dados["indicadores"] if x["id"] == "fao")
        i.update(valor=round(num(ult[1]), 1), referencia=ym,
                 variacao_pct=round((num(ult[1]) / num(ant[1]) - 1) * 100, 2),
                 variacao_desc=f"sobre {MESES[int(ya[1]) - 1]}/{ya[0]}",
                 fonte="FAO, Food Price Index (2014-2016 = 100)", link=FAO_PAGINA,
                 endpoint=csv_url.split("?")[0], extraido_em=HOJE, automatico=True)
        dados["brasil"]["fao_subindices"].update(
            titulo=f"Índice FAO, variação em {ym}",
            linhas=[{"rotulo": r, "valor": round((num(ult[c]) / num(ant[c]) - 1) * 100, 1)} for r, c in FAO_SUB],
            fonte="FAO, Food Price Index, subíndices (2014-2016 = 100)", link=FAO_PAGINA,
            endpoint=csv_url.split("?")[0], extraido_em=HOJE)
        log(f"Índice FAO {ym} atualizado")
    except Exception as e:  # noqa: BLE001
        log(f"FAO: falhou ({e}); mantido o valor anterior")


# ---------------------------------------------------------------- PIB trimestral (IBGE)
PIB_SETORES = [("90707", "PIB total"), ("90687", "Agropecuária"), ("90691", "Indústria"), ("90696", "Serviços")]


def atualizar_pib_trimestral(dados: dict) -> None:
    """Contas Nacionais Trimestrais, SIDRA 5932: variação sobre o trimestre anterior (6564) e anual (6561)."""
    try:
        cats = ",".join(c for c, _ in PIB_SETORES)
        url, cab, linhas = sidra(f"/t/5932/n1/all/v/6561,6564/p/last%201/c11255/{cats}")
        kv, kc, kp = coluna(cab, "Variável (Código)"), coluna(cab, "Setores e subsetores (Código)"), next(k for k, v in cab.items() if v == "Trimestre")
        val = {(l[kv], l[kc]): num(l["V"]) for l in linhas}
        tri = linhas[0][kp]
        dados["brasil"]["pib_trimestral"].update(
            titulo=f"PIB do Brasil, {tri}",
            linhas=[{"rotulo": r, "tri": val.get(("6564", c)), "anual": val.get(("6561", c))} for c, r in PIB_SETORES],
            nota="Variação sobre o trimestre anterior (com ajuste sazonal) e sobre o mesmo trimestre do ano anterior.",
            fonte="IBGE, Contas Nacionais Trimestrais, tabela 5932", link="https://sidra.ibge.gov.br/tabela/5932",
            endpoint=url, extraido_em=HOJE)
        log(f"PIB trimestral ({tri}) atualizado")
    except Exception as e:  # noqa: BLE001
        log(f"PIB trimestral: falhou ({e}); mantido o valor anterior")


# ---------------------------------------------------------------- Notícias (RSS)
PALAVRAS = re.compile(r"agro|soja|milho|boi|bovin|su[ií]n|frango|ovo|leite|safra|conab|embrapa|"
                      r"pecu|lavoura|fertiliz|caf[eé]|algod|trigo|tilápia|pescado|cerrado|exporta", re.I)


def atualizar_noticias(dados: dict) -> None:
    if not FEEDS.exists():
        return
    feeds = json.loads(FEEDS.read_text(encoding="utf-8"))["feeds"]
    novas = []
    for f in feeds:
        try:
            raiz = ET.fromstring(baixar(f["url"]))
            for it in raiz.iter("item"):
                t, l = (it.findtext("title") or "").strip(), (it.findtext("link") or "").strip()
                if not t or not l or (f.get("filtrar", True) and not PALAVRAS.search(t)):
                    continue
                d = it.findtext("pubDate") or ""
                try:
                    d = datetime.strptime(d[:25].strip(), "%a, %d %b %Y %H:%M:%S").strftime("%Y-%m-%d")
                except ValueError:
                    d = HOJE
                novas.append({"titulo": t, "veiculo": f["veiculo"], "data": d, "tema": f.get("tema", "Agronegócio"),
                              "link": l})
            log(f"Notícias: {f['veiculo']} lido")
        except Exception as e:  # noqa: BLE001
            log(f"Notícias: {f['veiculo']} falhou ({e})")
    vistos, saida = set(), []
    for n in sorted(novas + dados.get("noticias", []), key=lambda n: n.get("data") or "", reverse=True):
        if n["link"] not in vistos:
            vistos.add(n["link"])
            saida.append(n)
    dados["noticias"] = saida[:20]


# ---------------------------------------------------------------- Cepea/Esalq (via Notícias Agrícolas)
CEPEA_NA = {
    "boi": ("https://www.noticiasagricolas.com.br/cotacoes/boi-gordo/boi-gordo-indicador-esalq-bmf",
            "Indicador do Boi Gordo Cepea/Esalq (estado de São Paulo), à vista, divulgado pelo Notícias Agrícolas",
            "https://www.cepea.org.br/br/indicador/boi-gordo.aspx"),
    "soja": ("https://www.noticiasagricolas.com.br/cotacoes/soja/soja-indicador-cepea-esalq-porto-paranagua",
             "Indicador da Soja Cepea/Esalq Paranaguá, divulgado pelo Notícias Agrícolas",
             "https://www.cepea.org.br/br/indicador/soja.aspx"),
    "milho": ("https://www.noticiasagricolas.com.br/cotacoes/milho/indicador-cepea-esalq-milho",
              "Indicador do Milho Esalq/B3 (Campinas), divulgado pelo Notícias Agrícolas",
              "https://www.cepea.org.br/br/indicador/milho.aspx"),
}
LINHA_NA = re.compile(r"<tbody[^>]*>\s*<tr>\s*<td>(\d{2}/\d{2}/\d{4})</td>\s*<td>([\d.,]+)</td>\s*<td>(-?[\d.,]+)%</td>", re.S)


def atualizar_cepea(ind: list) -> None:
    """O site do Cepea bloqueia robôs; o Notícias Agrícolas republica os indicadores diários do Cepea/Esalq."""
    alvo = {i["id"]: i for i in ind}
    for k, (url, fonte, link) in CEPEA_NA.items():
        try:
            m = LINHA_NA.search(baixar(url).decode("utf-8", "replace"))
            if not m or k not in alvo:
                raise ValueError("tabela não encontrada")
            data, valor, var = m.groups()
            alvo[k].update(valor=float(valor.replace(".", "").replace(",", ".")), referencia=data,
                           variacao_pct=float(var.replace(".", "").replace(",", ".")), variacao_desc="no dia",
                           fonte=fonte, link=link, endpoint=url, extraido_em=HOJE, automatico=True)
            log(f"Cepea {k}: {valor} em {data}")
        except Exception as e:  # noqa: BLE001
            log(f"Cepea {k}: falhou ({e}); mantido o valor anterior")


def _data_ref(i: dict):
    try:
        return datetime.strptime(str(i.get("referencia", "")), "%d/%m/%Y")
    except ValueError:
        return None


# ---------------------------------------------------------------- Entradas manuais
def aplicar_manual(dados: dict) -> None:
    if not MANUAL.exists():
        return
    man = json.loads(MANUAL.read_text(encoding="utf-8"))
    alvo = {i["id"]: i for i in dados["indicadores"]}
    for m in man.get("indicadores", []):
        if m["id"] in alvo:
            a, b = _data_ref(alvo[m["id"]]), _data_ref(m)
            if a and b and a > b:  # valor automático mais recente que o lançado à mão: fica o automático
                continue
            alvo[m["id"]].update(m)
        else:
            dados["indicadores"].append(m)
    for chave in ("pib_trimestral", "pib_agro_cepea", "fao_subindices"):
        if chave in man.get("brasil", {}):
            dados["brasil"][chave].update(man["brasil"][chave])
    log("Entradas manuais aplicadas")


def main() -> None:
    dados = json.loads(DADOS.read_text(encoding="utf-8"))
    atualizar_bcb(dados["indicadores"])
    atualizar_fao(dados)
    atualizar_pib_trimestral(dados)
    atualizar_pam_df(dados["df"])
    atualizar_ppm_df(dados["df"])
    atualizar_ride(dados["ride"])
    atualizar_noticias(dados)
    atualizar_cepea(dados["indicadores"])
    aplicar_manual(dados)
    dados["atualizado_em"] = datetime.now(BRT).isoformat(timespec="minutes")
    DADOS.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    log("data/dados.json gravado")


if __name__ == "__main__":
    main()
