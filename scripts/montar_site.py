"""Monta o index.html do portal NEAGRO-DF.

Insere o retrato mais recente de data/dados.json, data/boletins.json, data/fotos.json, data/contato.json, data/painel.json e data/painel_quadros.json dentro da
página, para que ela funcione mesmo sem acesso aos arquivos JSON ou às APIs.

Uso:  python scripts/montar_site.py
"""
from pathlib import Path
import json

RAIZ = Path(__file__).resolve().parent.parent


def main() -> None:
    tpl = (RAIZ / "src" / "index.template.html").read_text(encoding="utf-8")
    dados = json.loads((RAIZ / "data" / "dados.json").read_text(encoding="utf-8"))
    bol = json.loads((RAIZ / "data" / "boletins.json").read_text(encoding="utf-8"))
    fotos = json.loads((RAIZ / "data" / "fotos.json").read_text(encoding="utf-8"))
    contato = json.loads((RAIZ / "data" / "contato.json").read_text(encoding="utf-8"))
    painel = json.loads((RAIZ / "data" / "painel.json").read_text(encoding="utf-8"))
    arq_q = RAIZ / "data" / "painel_quadros.json"
    quadros = json.loads(arq_q.read_text(encoding="utf-8")) if arq_q.exists() else None
    calc = (RAIZ / "src" / "painel-calc.js").read_text(encoding="utf-8")
    seguro = lambda o: json.dumps(o, ensure_ascii=False).replace("</", "<\\/")
    corpo = tpl.replace("/*DADOS*/", seguro(dados)).replace("/*BOLETINS*/", seguro(bol)).replace("/*FOTOS*/", seguro(fotos)).replace("/*CONTATO*/", seguro(contato)).replace("/*PAINEL*/", seguro(painel)).replace("/*QUADROS*/", seguro(quadros)).replace("/*PAINEL_CALC*/", calc)

    # Versão completa para hospedagem (servidor da UnB, Netlify, GitHub Pages).
    # Elementos obrigatórios do Governo Federal: entram apenas na versão hospedada.
    govbr = (
        "<script>(function(){if(/[?&]modo=wp\\b/.test(location.search))return;"
        "[\"https://barra.brasil.gov.br/barra_2.0.js\",\"https://vlibras.gov.br/app/vlibras-plugin.js\"]"
        ".forEach(function(u){var s=document.createElement(\"script\");s.src=u;s.defer=true;document.body.appendChild(s);});})();</script>"
    )
    (RAIZ / "src" / "preview.html").write_text(corpo.replace("<!--GOVBR-SCRIPTS-->", ""), encoding="utf-8")
    corpo = corpo.replace("<!--GOVBR-SCRIPTS-->", govbr)
    head, _, resto = corpo.partition("</style>")
    pagina = (
        '<!doctype html>\n<html lang="pt-BR">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        + head + "</style>\n</head>\n<body>\n" + resto + "\n</body>\n</html>\n"
    )
    (RAIZ / "index.html").write_text(pagina, encoding="utf-8")
    print("index.html gerado.")


if __name__ == "__main__":
    main()
