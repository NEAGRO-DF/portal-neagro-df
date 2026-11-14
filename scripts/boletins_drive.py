"""Atualiza a lista de boletins do portal NEAGRO-DF a partir das pastas públicas do Google Drive.

Lê as pastas listadas no "acervo" de cada série de data/boletins.json (somente links de pastas do
Google Drive), encontra os PDFs e acrescenta à lista "edicoes" os boletins que ainda não estão nela.
Basta salvar o PDF na pasta do ano no Drive: na execução seguinte do robô o boletim aparece no portal.
Todo PDF que estiver fora do portal (Drive, SharePoint ou outro site) é copiado para boletins/<ano>/,
e o catálogo passa a apontar para essa cópia; o endereço de origem fica guardado em "pdf_original".

Padrão de nome esperado: "6.032 - Boletim BOVINOS - NEAGRO-DF - 26.09.2026.pdf".
Arquivos fora do padrão entram com o nome do arquivo e a data da última modificação no Drive.
Edições lançadas à mão (por exemplo, as do morango) são mantidas.

Uso:  python scripts/boletins_drive.py
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import unicodedata
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARQ = RAIZ / "data" / "boletins.json"
PASTA_PDF = RAIZ / "boletins"
SITE = "https://neagro-df.github.io/portal-neagro-df/"
LISTA = "https://drive.google.com/embeddedfolderview?id={}"

ENTRADA = re.compile(
    r'<div class="flip-entry" id="entry-([\w-]+)".*?<div class="flip-entry-title">(.*?)</div>'
    r'.*?<div class="flip-entry-last-modified"><div>(.*?)</div>',
    re.S,
)
NOME = re.compile(
    r"^\s*(?P<num>\d+(?:\.\d+)?)\s*-\s*Boletim\s+(?P<tipo>.+?)\s*-\s*(?:NEAGRO-DF\s*-\s*)?"
    r"(?P<d>\d{2})\.(?P<m>\d{2})\.(?P<a>\d{4})\.pdf\s*$",
    re.I,
)

TODAS = ["Suinocultura", "Bovinocultura de corte", "Bovinocultura de leite", "Avicultura de corte",
         "Avicultura de postura", "Insumos"]
CADEIAS = [
    (r"insumo", ["Insumos"]),
    (r"corte e leite", ["Bovinocultura de corte", "Bovinocultura de leite"]),
    (r"bovino", ["Bovinocultura de corte"]),
    (r"su[ií]no.*ave", ["Suinocultura", "Avicultura de corte", "Avicultura de postura"]),
    (r"su[ií]no", ["Suinocultura"]),
    (r"ave|frango|ovo", ["Avicultura de corte", "Avicultura de postura"]),
    (r"leite", ["Bovinocultura de leite"]),
    (r"sistemas animais", TODAS),
]
TITULOS = {
    "Insumos": "Boletim de Mercado: Insumos (milho e farelo de soja)",
    "Bovinocultura de corte": "Boletim de Mercado: Bovinocultura de corte",
    "Suinocultura": "Boletim de Mercado: Suinocultura",
}


def pasta(link: str) -> str | None:
    m = re.search(r"drive\.google\.com/drive/(?:u/\d+/)?folders/([\w-]+)", link or "")
    return m.group(1) if m else None


def baixar(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (NEAGRO-DF portal)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def baixar_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (NEAGRO-DF portal)"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def baixar_sharepoint(link: str) -> bytes:
    """Link de compartilhamento público do SharePoint/OneDrive da UnB: abrir o link libera o acesso de convidado
    (cookie); a página indica o caminho do arquivo, baixado em seguida por download.aspx."""
    import http.cookiejar
    from urllib.parse import quote, unquote, urlsplit
    abridor = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    abridor.addheaders = [("User-Agent", "Mozilla/5.0 (NEAGRO-DF portal)")]
    with abridor.open(link.split("&download=")[0], timeout=120) as r:
        pagina = r.read().decode("utf-8", "replace")
        final = r.geturl()
    m = re.search(r"[?&]id=([^&\"'\\ ]+)", final) or re.search(r"onedrive\.aspx\?id=([^&\"'\\ ]+)", pagina)
    if not m:
        raise ValueError("a página do SharePoint não indicou o arquivo")
    caminho = unquote(m.group(1))
    pessoal = re.match(r"(/personal/[^/]+)/", caminho)
    if not pessoal:
        raise ValueError("caminho do SharePoint inesperado")
    base = "{0.scheme}://{0.netloc}".format(urlsplit(link))
    with abridor.open(f"{base}{pessoal.group(1)}/_layouts/15/download.aspx?SourceUrl={quote(caminho)}", timeout=120) as r:
        return r.read()


def url_download(link: str) -> str:
    """Endereço de download direto do PDF, conforme o serviço onde ele está guardado."""
    m = re.search(r"drive\.google\.com/file/d/([\w-]+)", link)
    if m:
        return f"https://drive.usercontent.google.com/download?id={m.group(1)}&export=download&confirm=t"
    return link


def slug(txt: str) -> str:
    t = unicodedata.normalize("NFD", txt)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def nome_pdf(e: dict) -> str:
    if e.get("serie") == "animal":
        tit = re.sub(r"^\s*boletim de mercado\s*:?\s*(?:d[ao]s?\s+)?", "", e.get("titulo", ""), flags=re.I)
        assunto = slug(tit)[:60].strip("-") or "producao-animal"
    else:
        assunto = slug(e.get("serie", "")) or "boletim"
    num = slug(e.get("numero", "")) or hashlib.sha1(e.get("pdf", "").encode()).hexdigest()[:8]
    data = e.get("data") or "sem-data"
    return f"{num}-boletim-{assunto}-neagro-df-{data}.pdf"


def espelhar(edicoes: list[dict], ignorar: set[str]) -> int:
    """Copia para o portal (pasta boletins/<ano>/) os PDFs que ainda estão no Google Drive ou em outros sites,
    e passa o catálogo a apontar para a cópia do portal. O link original fica em "pdf_original"."""
    feitos = 0
    for e in edicoes:
        link = e.get("pdf", "")
        if not link or link.startswith(SITE) or link in ignorar:
            continue
        ano = (e.get("data") or "")[:4] or "outros"
        destino = PASTA_PDF / ano / nome_pdf(e)
        try:
            dados = baixar_sharepoint(link) if "sharepoint.com" in link else baixar_bytes(url_download(link))
            if not dados.startswith(b"%PDF"):
                raise ValueError("o endereço não devolveu um PDF (arquivo privado ou link expirado?)")
            if destino.exists() and destino.read_bytes() != dados:
                destino = destino.with_name(destino.stem + "-" + hashlib.sha1(dados).hexdigest()[:6] + ".pdf")
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(dados)
            e["pdf_original"] = link
            e["pdf"] = SITE + destino.relative_to(RAIZ).as_posix()
            feitos += 1
            print(f"[boletins] copiado para o portal: {destino.relative_to(RAIZ)} ({len(dados) // 1024} KB)")
        except Exception as erro:  # noqa: BLE001
            print(f"[boletins] não foi possível copiar {e.get('numero') or e.get('titulo')} ({erro}); mantido o link externo")
    return feitos


def cadeias(tipo: str) -> list[str]:
    t = tipo.lower()
    for padrao, lista in CADEIAS:
        if re.search(padrao, t):
            return list(lista)
    return TODAS


def edicao(serie: str, fid: str, nome: str) -> dict | None:
    if not nome.lower().endswith(".pdf"):
        return None
    pdf = f"https://drive.google.com/file/d/{fid}/view"
    m = NOME.match(nome)
    if not m:
        return {"serie": serie, "numero": "", "data": "", "titulo": nome[:-4], "cadeias": [],
                "resumo": "", "destaques": [], "pdf": pdf, "origem": "drive"}
    tipo = m["tipo"].strip()
    cad = cadeias(tipo)
    if cad == TODAS:
        titulo = "Boletim de Mercado da Produção Animal do DF e Entorno"
    elif "Suinocultura" in cad and "Avicultura de corte" in cad:
        titulo = "Boletim de Mercado: Suinocultura e avicultura"
    elif "Bovinocultura de leite" in cad and "Bovinocultura de corte" in cad:
        titulo = "Boletim de Mercado: Bovinocultura de corte e de leite"
    else:
        titulo = TITULOS.get(cad[0], f"Boletim de Mercado: {tipo.title()}")
    data = f"{m['a']}-{m['m']}-{m['d']}"
    return {
        "serie": serie,
        "numero": m["num"],
        "data": data,
        "titulo": titulo,
        "cadeias": cad,
        "resumo": "Preços de insumos e produtos nas praças acompanhadas pelo NEAGRO-DF no DF e Entorno, "
                  "relações de troca entre insumo e produto e análise do comportamento do mercado no período.",
        "destaques": [],
        "pdf": pdf,
        "origem": "drive",
    }


def ler_pasta(fid: str, conteudo: str | None = None) -> list[tuple[str, str]]:
    texto = conteudo if conteudo is not None else baixar(LISTA.format(fid))
    return [(i, html.unescape(t).strip()) for i, t, _ in ENTRADA.findall(texto)]


def main() -> None:
    bol = json.loads(ARQ.read_text(encoding="utf-8"))
    edicoes = bol.get("edicoes", [])
    # "ignorar": links de PDF do Drive que não devem entrar no portal (ex.: edição ainda incompleta)
    ignorar = set(bol.get("ignorar", []))
    vistos = {e.get("pdf") for e in edicoes} | {e.get("pdf_original") for e in edicoes} | ignorar
    novas = 0
    for s in bol.get("series", []):
        for a in s.get("acervo", []):
            fid = pasta(a.get("link", ""))
            if not fid:
                continue
            try:
                arquivos = ler_pasta(fid)
            except Exception as e:  # noqa: BLE001
                print(f"[boletins] pasta {a.get('rotulo')} não lida ({e}); mantida a lista anterior")
                continue
            for arq_id, nome in arquivos:
                ed = edicao(s["id"], arq_id, nome)
                if ed and ed["pdf"] not in vistos:
                    edicoes.append(ed)
                    vistos.add(ed["pdf"])
                    novas += 1
    copiados = espelhar(edicoes, ignorar)
    edicoes.sort(key=lambda e: (e.get("data") or "", e.get("numero") or ""), reverse=True)
    bol["edicoes"] = edicoes
    ARQ.write_text(json.dumps(bol, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[boletins] {novas} boletim(ns) novo(s); {copiados} copiado(s) para o portal; {len(edicoes)} no total")


if __name__ == "__main__":
    main()
