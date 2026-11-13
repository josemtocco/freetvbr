#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Imprime um resumo da ultima execucao em formato Markdown.
Usado pelo GitHub Actions para montar a pagina de resumo."""

import json
import os

ARQ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "relatorio.json")


def main():
    try:
        with open(ARQ, encoding="utf-8") as f:
            r = json.load(f)
    except Exception:
        print("Relatorio nao encontrado.")
        return

    print("## FreeTV Brasil - M3U")
    print()
    print("Atualizado em: **%s**" % r.get("atualizacao", "?"))
    print()
    print("| Item | Quantidade |")
    print("|---|---|")
    print("| Canais encontrados no site | %s |" % r.get("encontrados_no_site", 0))
    print("| Canais na lista M3U | %s |" % r.get("na_lista", 0))
    pr = r.get("por_resultado", {})
    print("| Tocando (teste real) | %s |" % pr.get("ok", 0))
    print("| Links quebrados | %s |" % pr.get("falha", 0))
    print("| Inconclusivos (geo/rede, nao removem) | %s |" % pr.get("inconclusivo", 0))
    print("| Novos canais | %s |" % r.get("novos", 0))
    print("| Canais removidos | %s |" % r.get("removidos", 0))
    print()
    print("Limite para remover um canal: %s atualizacoes seguidas com falha."
          % r.get("limite_falhas", 6))


if __name__ == "__main__":
    main()
