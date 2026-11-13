#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FreeTV Brasil -> M3U para SS IPTV
==================================

Gera uma lista M3U com todos os canais brasileiros do freetv.studio,
organizada nas categorias originais do site, com teste real de reproducao
e reconciliacao entre atualizacoes (mantem ativos / remove inativos apos
N falhas consecutivas / adiciona novos).

Uso normal (atualiza a lista):
    python freetv_br.py

Opcoes uteis:
    --sem-teste          nao testa os links (so coleta e monta a lista)
    --testar-tudo        testa todos os canais, mesmo os que ja estavam ok
    --sem-reconciliar    nao mexe no estado (nao conta falhas, nao remove)
    --incluir-instaveis  inclui tambem canais que falharam no teste
    --limite-falhas N    quantas atualizacoes seguidas com falha antes de
                         remover o canal (padrao: 6)
    --debug              log detalhado de cada etapa

Sem dependencias externas: usa somente a biblioteca padrao do Python 3.8+.
"""

import argparse
import concurrent.futures
import gzip
import io
import json
import os
import re
import socket
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# Configuracao
# ---------------------------------------------------------------------------

BASE = "https://freetv.studio"
PAIS = "br"
LOCALE = "pt"

DIR_PROJETO = os.path.dirname(os.path.abspath(__file__))
ARQ_SAIDA = os.path.join(DIR_PROJETO, "freetv_br.m3u")
ARQ_ESTADO = os.path.join(DIR_PROJETO, "estado_canais.json")
ARQ_RELATORIO = os.path.join(DIR_PROJETO, "relatorio.json")

LIMITE_FALHAS_PADRAO = 6
WORKERS_COLETA = 8
WORKERS_TESTE = 16
TIMEOUT_HTTP = 20
TIMEOUT_STREAM = 12

UA_SITE = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
UA_PLAYER = "VLC/3.0.20 LibVLC/3.0.20"

# Nome bonito para cada categoria do site (slug -> titulo usado no M3U).
# Se o site criar uma categoria nova, o script usa o nome que ele achar na
# propria pagina; este dicionario serve de traducao/fallback.
NOMES_CATEGORIAS = {
    "general": "Geral",
    "news": "Noticias",
    "religious": "Religioso",
    "entertainment": "Entretenimento",
    "education": "Educacao",
    "movies": "Filmes",
    "culture": "Cultura",
    "sports": "Esportes",
    "music": "Musica",
    "outdoor": "Ao Ar Livre",
    "kids": "Infantil",
    "classic": "Classicos",
    "legislative": "Legislativo",
    "series": "Series",
    "travel": "Viagem",
    "comedy": "Comedia",
    "documentary": "Documentario",
    "public": "Publico",
    "shop": "Compras",
    "animation": "Animacao",
    "lifestyle": "Estilo de Vida",
    "business": "Negocios",
    "family": "Familia",
    "auto": "Automotivo",
    "cooking": "Culinaria",
    "health": "Saude",
    "science": "Ciencia",
    "weather": "Clima",
    "top": "Destaques",
}

CATEGORIA_FALLBACK = "general"
FUSO_BR = timezone(timedelta(hours=-3))

# Alguns canais nao tem categoria no site. Para eles, tentamos adivinhar a
# categoria pelo nome, em vez de jogar tudo em "Outros".
# A ordem importa: a primeira regra que casar vence.
REGRAS_POR_NOME = [
    (r"globo|sbt|record|band|rede ?tv|cn?t\b|gazeta|cultura|brasil\b", "general"),
    (r"novela|serie", "series"),
    (r"internacional|cnn|bbc", "news"),
    (r"justica|senado|camara|legislativ|assembleia", "legislative"),
    (r"can[cç][aã]o nova|boas novas|fam[ií]lia|gospel|crist|deus|f[eé]", "religious"),
    (r"ra ?tim ?bum|infantil|kids|cartoon|anime", "kids"),
    (r"esporte|futebol", "sports"),
    (r"m[uú]sica|music", "music"),
    (r"filme|cinema|movie|sony|axn|warner|universal", "movies"),
    (r"edu|sesc|universid|academ", "education"),
    (r"turismo|viagem|travel", "travel"),
]


def categoria_por_nome(nome):
    """Tenta descobrir a categoria pelo nome do canal. Pode devolver None."""
    n = unicodedata.normalize("NFKD", nome.lower())
    n = "".join(c for c in n if not unicodedata.combining(c))
    for padrao, slug in REGRAS_POR_NOME:
        if re.search(padrao, n):
            return slug
    return None


# ---------------------------------------------------------------------------
# Log
# ---------------------------------------------------------------------------

_DEBUG = False


def log(msg):
    print(msg, flush=True)


def debug(msg):
    if _DEBUG:
        print("   [debug] " + str(msg), flush=True)


def linha(caractere="-", tamanho=62):
    log(caractere * tamanho)


# ---------------------------------------------------------------------------
# Utilidades HTTP
# ---------------------------------------------------------------------------


def http_get(url, timeout=TIMEOUT_HTTP, headers=None, limite=4_000_000):
    """GET simples, com descompressao gzip manual e User-Agent de navegador."""
    h = {
        "User-Agent": UA_SITE,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
    }
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    resp = urllib.request.urlopen(req, timeout=timeout)
    dados = resp.read(limite)
    if resp.headers.get("Content-Encoding") == "gzip" or dados[:2] == b"\x1f\x8b":
        try:
            dados = gzip.decompress(dados)
        except Exception:
            try:
                with gzip.GzipFile(fileobj=io.BytesIO(dados)) as f:
                    dados = f.read()
            except Exception:
                pass
    return dados.decode("utf-8", "ignore"), resp.status, dict(resp.headers)


def http_get_bytes(url, timeout=TIMEOUT_STREAM, limite=400_000):
    h = {"User-Agent": UA_PLAYER, "Accept": "*/*", "Accept-Encoding": "gzip, deflate"}
    req = urllib.request.Request(url, headers=h)
    resp = urllib.request.urlopen(req, timeout=timeout)
    dados = resp.read(limite)
    if resp.headers.get("Content-Encoding") == "gzip" or dados[:2] == b"\x1f\x8b":
        try:
            dados = gzip.decompress(dados)
        except Exception:
            pass
    return dados


# ---------------------------------------------------------------------------
# Coleta: descoberta de canais
# ---------------------------------------------------------------------------

RE_CARD = re.compile(r'data-ga-id="([^"]+)"')
RE_CAT_PILL = re.compile(
    r'country/br[?]cat=([a-z0-9-]+)"><span>([^<]+)</span><span[^>]*>(\d+)</span>'
)
RE_LOC = re.compile(r"<loc>([^<]+)</loc>")


def buscar_categorias():
    """Le a barra de categorias da pagina de pais. Devolve {slug: nome}."""
    url = "%s/%s/country/%s" % (BASE, LOCALE, PAIS)
    html, _, _ = http_get(url)
    cats = {}
    for slug, nome, _qtd in RE_CAT_PILL.findall(html):
        cats[slug] = nome.strip()
    debug("categorias encontradas na pagina de pais: %d" % len(cats))
    return cats


def ids_da_pagina(html):
    return re.findall(RE_CARD, html)


def coletar_do_catalogo():
    """Percorre a pagina 'todos' e cada categoria, devolvendo
    {channel_id: set(categorias)}."""
    encontrados = {}

    url_todos = "%s/%s/country/%s" % (BASE, LOCALE, PAIS)
    html, _, _ = http_get(url_todos)
    ids = ids_da_pagina(html)
    for i in ids:
        encontrados.setdefault(i, set())
    log("  Vitrine (todos os canais)........: %d canais" % len(ids))

    categorias = buscar_categorias()
    log("  Categorias no site...............: %d" % len(categorias))

    for slug in sorted(categorias):
        url = "%s/%s/country/%s?cat=%s" % (BASE, LOCALE, PAIS, slug)
        try:
            html, _, _ = http_get(url)
        except Exception as e:
            log("  [aviso] categoria %s falhou: %s" % (slug, e))
            continue
        ids_cat = ids_da_pagina(html)
        for i in ids_cat:
            encontrados.setdefault(i, set()).add(slug)
        log(
            "    categoria %-16s %3d canais" % (slug, len(ids_cat))
        )

    return encontrados, categorias


def coletar_do_sitemap():
    """O sitemap traz canais que nao aparecem na vitrine. Fonte extra."""
    ids = set()
    try:
        txt, _, _ = http_get(BASE + "/sitemap.xml", limite=30_000_000)
    except Exception as e:
        log("  [aviso] sitemap indisponivel: %s" % e)
        return ids
    for loc in RE_LOC.findall(txt):
        m = re.search(r"/channel/([^/]+)$", loc.strip())
        if not m:
            continue
        cid = m.group(1)
        if cid.lower().endswith("." + PAIS):
            ids.add(cid)
    log("  Sitemap (canais do Brasil).......: %d canais" % len(ids))
    return ids


# ---------------------------------------------------------------------------
# Coleta: dados de cada canal
# ---------------------------------------------------------------------------

RE_H1 = re.compile(r"<h1[^>]*>(.*?)</h1>", re.S)
RE_LOGO = re.compile(r'<img[^>]+src="([^"]+)"[^>]*alt="[^"]*logo', re.I)
RE_LOGO2 = re.compile(r'<img[^>]+src="([^"]+)"[^>]*width="64"')
RE_STREAMS = re.compile(r'streamUrls\\+"?\s*:\s*\[([^\]]*)\]')
RE_CAT_LINK = re.compile(r'href="/pt/category/([a-z0-9-]+)"')
RE_LD_CHANNEL = re.compile(
    r'\{\\"@type\\":\\"BroadcastService\\".*?\\"name\\":\\"(.*?)\\"', re.S
)


def limpar_texto(t):
    t = re.sub(r"<[^>]+>", "", t)
    t = t.replace("&amp;", "&").replace("&#39;", "'").replace("&quot;", '"')
    t = t.replace("&lt;", "<").replace("&gt;", ">").replace("&nbsp;", " ")
    return " ".join(t.split()).strip()


def extrair_streams(html):
    """Pega a lista de URLs HLS do payload da pagina do canal."""
    urls = []
    m = RE_STREAMS.search(html)
    if m:
        bruto = m.group(1)
        for pedaco in bruto.split(","):
            u = pedaco.replace("\\", "").strip().strip('"').strip()
            if u.startswith("http"):
                urls.append(u)
    # fallback: qualquer .m3u8/.mpd solto na pagina
    if not urls:
        for u in re.findall(r'https?://[^\s"\\<]+?\.(?:m3u8|mpd)(?:\?[^\s"\\<]*)?', html):
            if "api/hls" not in u:
                urls.append(u)
    # remove duplicados preservando ordem
    vistos, saida = set(), []
    for u in urls:
        if u not in vistos:
            vistos.add(u)
            saida.append(u)
    return saida


def coletar_canal(cid):
    url = "%s/%s/channel/%s" % (BASE, LOCALE, cid)
    try:
        html, _, _ = http_get(url)
    except Exception as e:
        return cid, {"erro": "pagina: %s" % e}

    nome = ""
    m = RE_H1.search(html)
    if m:
        nome = limpar_texto(m.group(1))
    if not nome:
        m = RE_LD_CHANNEL.search(html)
        if m:
            nome = limpar_texto(m.group(1))
    if not nome:
        nome = cid.rsplit(".", 1)[0]

    logo = ""
    m = RE_LOGO.search(html) or RE_LOGO2.search(html)
    if m:
        logo = m.group(1).replace("&amp;", "&")

    cats = []
    for c in RE_CAT_LINK.findall(html):
        if c not in cats:
            cats.append(c)

    streams = extrair_streams(html)

    return cid, {
        "nome": nome,
        "logo": logo,
        "categorias": cats,
        "streams": streams,
        "pagina": url,
    }


# ---------------------------------------------------------------------------
# Teste de reproducao (le o manifesto e baixa um segmento de video real)
# ---------------------------------------------------------------------------

RESULTADO_OK = "ok"
RESULTADO_FALHA = "falha"          # link ruim de verdade (404, 410, nao e HLS...)
RESULTADO_NEUTRO = "inconclusivo"  # rede/geo: NAO conta como falha do canal

# Codigos HTTP que indicam problema do proprio link
HTTP_LINK_RUIM = {400, 401, 404, 410, 451}
# Codigos que costumam ser bloqueio de regiao / protecao do servidor
HTTP_GEO = {403, 407, 429, 500, 502, 503, 504}


def _url_absoluta(base, rel):
    return urllib.parse.urljoin(base, rel.strip())


def testar_stream(url, timeout=TIMEOUT_STREAM):
    """Devolve (resultado, detalhe).

    ok           -> manifesto HLS valido e um segmento de video baixado
    falha        -> o link esta quebrado (404/410, nao e HLS, segmento 404)
    inconclusivo -> bloqueio de rede/regiao (000, 403, 5xx, DNS, timeout)
    """
    try:
        dados = http_get_bytes(url, timeout)
    except urllib.error.HTTPError as e:
        if e.code in HTTP_LINK_RUIM:
            return RESULTADO_FALHA, "HTTP %d" % e.code
        return RESULTADO_NEUTRO, "HTTP %d (geo/bloqueio)" % e.code
    except urllib.error.URLError as e:
        motivo = str(getattr(e, "reason", e))
        if isinstance(getattr(e, "reason", None), socket.gaierror):
            return RESULTADO_FALHA, "DNS inexistente"
        return RESULTADO_NEUTRO, "sem conexao (geo/rede)"
    except (socket.timeout, TimeoutError):
        return RESULTADO_NEUTRO, "timeout (geo/rede)"
    except Exception as e:
        return RESULTADO_NEUTRO, "rede: %s" % type(e).__name__

    texto = dados.decode("utf-8", "ignore")
    if "#EXTM3U" not in texto[:300]:
        return RESULTADO_FALHA, "nao e HLS"

    if "#EXT-X-STREAM-INF" in texto:
        variantes = [
            l.strip() for l in texto.splitlines() if l.strip() and not l.startswith("#")
        ]
        if not variantes:
            return RESULTADO_FALHA, "manifesto vazio"
        url_var = _url_absoluta(url, variantes[0])
        try:
            d2 = http_get_bytes(url_var, timeout)
        except urllib.error.HTTPError as e:
            if e.code in HTTP_LINK_RUIM:
                return RESULTADO_FALHA, "variante HTTP %d" % e.code
            return RESULTADO_NEUTRO, "variante HTTP %d (geo)" % e.code
        except Exception:
            return RESULTADO_NEUTRO, "variante inacessivel"
        text2 = d2.decode("utf-8", "ignore")
        base_seg = url_var
    else:
        text2 = texto
        base_seg = url

    segmentos = [l.strip() for l in text2.splitlines() if l.strip() and not l.startswith("#")]
    if not segmentos:
        return RESULTADO_FALHA, "sem segmentos"
    url_seg = _url_absoluta(base_seg, segmentos[-1])

    try:
        seg = http_get_bytes(url_seg, timeout, limite=250_000)
    except urllib.error.HTTPError as e:
        if e.code in HTTP_LINK_RUIM:
            return RESULTADO_FALHA, "segmento HTTP %d" % e.code
        return RESULTADO_NEUTRO, "segmento HTTP %d (geo)" % e.code
    except Exception:
        return RESULTADO_NEUTRO, "segmento inacessivel (geo/rede)"

    if len(seg) < 2000:
        return RESULTADO_FALHA, "segmento vazio (%d bytes)" % len(seg)

    # byte de sincronismo de TS (0x47) ou caixa fMP4
    if seg[:1] == b"\x47" or b"ftyp" in seg[:64] or seg[:4] == b"\x00\x00\x00\x01":
        return RESULTADO_OK, "tocando (%d KB)" % (len(seg) // 1024)
    return RESULTADO_OK, "tocando (%d KB)" % (len(seg) // 1024)


def testar_canal(streams, tentar_todos=False):
    """Testa as URLs do canal em ordem. Para no primeiro que tocar.
    Devolve (url_boa, resultado, detalhe)."""
    if not streams:
        return None, RESULTADO_FALHA, "sem link"
    ultimo = (None, RESULTADO_FALHA, "sem link")
    for u in streams:
        res, det = testar_stream(u)
        if res == RESULTADO_OK:
            return u, res, det
        # guarda o resultado mais grave encontrado
        if res == RESULTADO_FALHA or ultimo[1] == RESULTADO_FALHA and res == RESULTADO_NEUTRO:
            ultimo = (u, res, det)
        else:
            ultimo = (u, res, det)
        if not tentar_todos and res == RESULTADO_NEUTRO and len(streams) == 1:
            break
    return ultimo


# ---------------------------------------------------------------------------
# Estado e reconciliacao
#
# Estrutura de estado_canais.json:
# {
#   "canais": {
#     "AXN.br": {
#       "nome": "AXN",
#       "logo": "...",
#       "categorias": ["movies"],
#       "url": "http://.../index.m3u8",
#       "streams": ["..."],
#       "falhas": 0,
#       "ultimo_ok": "2026-11-14T10:00:00-03:00",
#       "inativo": false
#     }
#   },
#   "meta": {"atualizacao": "...", "limite_falhas": 6}
# }
# ---------------------------------------------------------------------------


def carregar_estado():
    if not os.path.exists(ARQ_ESTADO):
        return {"canais": {}, "meta": {}}
    try:
        with open(ARQ_ESTADO, encoding="utf-8") as f:
            est = json.load(f)
    except Exception as e:
        log("[aviso] estado ilegivel (%s); comecando do zero" % e)
        return {"canais": {}, "meta": {}}
    est.setdefault("canais", {})
    est.setdefault("meta", {})
    return est


def salvar_json(caminho, obj):
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, caminho)


def agora_br():
    return datetime.now(FUSO_BR).replace(microsecond=0).isoformat()


# ---------------------------------------------------------------------------
# Montagem do M3U
# ---------------------------------------------------------------------------


def ordenar_categorias(slugs):
    """Ordem fixa e amigavel, com categorias desconhecidas no fim."""
    ordem = list(NOMES_CATEGORIAS.keys())
    conhecidas = [s for s in ordem if s in slugs]
    outras = sorted(s for s in slugs if s not in ordem)
    return conhecidas + outras


def nome_categoria(slug, nomes_site=None):
    if nomes_site and slug in nomes_site and nomes_site[slug].strip():
        return nomes_site[slug].strip()
    return NOMES_CATEGORIAS.get(slug, slug.capitalize())


def chave_ordenacao(texto):
    """Ordena ignorando acentos e maiusculas."""
    n = unicodedata.normalize("NFKD", texto)
    n = "".join(c for c in n if not unicodedata.combining(c))
    return n.lower()


def montar_m3u(canais_incluidos, nomes_site, cabecalho_extra=None):
    """canais_incluidos: lista de dicts com nome, logo, url, categorias."""

    def grupos_do_canal(c):
        """Devolve a lista de slugs de categoria de um canal.
        Se o site nao informar, tenta pelo nome; senao cai em 'outros'."""
        if c["categorias"]:
            return c["categorias"]
        adivinhada = categoria_por_nome(c["nome"])
        return [adivinhada] if adivinhada else ["outros"]

    # Cada canal entra UMA unica vez na lista, na sua primeira categoria.
    # (Antes, um canal com 4 categorias aparecia 4 vezes.)
    categoria_do_canal = {}
    urls_usadas = set()
    unicos = []
    for c in canais_incluidos:
        url = (c.get("url") or "").strip()
        if not url or url in urls_usadas:
            continue  # mesmo link m3u: mantem somente um
        urls_usadas.add(url)
        grupo_slug = grupos_do_canal(c)[0]
        categoria_do_canal[id(c)] = grupo_slug
        unicos.append(c)

    todas_cats = set(categoria_do_canal[id(c)] for c in unicos)

    linhas = ['#EXTM3U x-tvg-url=""']
    total = 0

    if cabecalho_extra:
        linhas.append("")
        for l in cabecalho_extra:
            linhas.append(l)
        linhas.append("")

    for slug in ordenar_categorias(list(todas_cats)):
        grupo = "Outros" if slug == "outros" else nome_categoria(slug, nomes_site)

        do_grupo = [c for c in unicos if categoria_do_canal[id(c)] == slug]
        if not do_grupo:
            continue
        do_grupo.sort(key=lambda c: chave_ordenacao(c["nome"]))

        for c in do_grupo:
            nome = c["nome"].replace(",", " ").strip()
            attrs = ['tvg-name="%s"' % nome]
            if c.get("logo"):
                attrs.append('tvg-logo="%s"' % c["logo"].replace('"', ""))
            attrs.append('group-title="%s"' % grupo.replace('"', ""))
            attrs.append('content-type="video"')
            linhas.append("#EXTINF:-1 %s,%s" % (" ".join(attrs), nome))
            linhas.append(c["url"])
            total += 1

    linhas.append("")
    return "\n".join(linhas), total


# ---------------------------------------------------------------------------
# Principal
# ---------------------------------------------------------------------------


def main():
    global _DEBUG

    ap = argparse.ArgumentParser(description="Gera M3U dos canais brasileiros do freetv.studio")
    ap.add_argument("--sem-teste", action="store_true", help="nao testa os links")
    ap.add_argument("--testar-tudo", action="store_true", help="testa todos os canais novamente")
    ap.add_argument("--sem-reconciliar", action="store_true", help="nao altera o estado de falhas")
    ap.add_argument("--incluir-instaveis", action="store_true", help="inclui canais que falharam no teste")
    ap.add_argument("--limite-falhas", type=int, default=None, help="falhas seguidas antes de remover (padrao 6)")
    ap.add_argument("--debug", action="store_true", help="log detalhado")
    args = ap.parse_args()
    _DEBUG = args.debug

    inicio = time.time()
    log("")
    linha("=")
    log("  FreeTV Brasil -> M3U para SS IPTV")
    log("  " + agora_br())
    linha("=")

    estado = carregar_estado()
    canais_estado = estado["canais"]
    limite_falhas = args.limite_falhas or estado.get("meta", {}).get("limite_falhas") or LIMITE_FALHAS_PADRAO
    log("Atualizacao anterior: %s" % estado.get("meta", {}).get("atualizacao", "(primeira execucao)"))
    log("Canais no estado......: %d" % len(canais_estado))
    log("Limite de falhas......: %d atualizacoes seguidas" % limite_falhas)
    linha()

    # ---------------------------- 1) Coleta ----------------------------
    log("[1/4] Coletando canais do site")
    desde_catalogo, categorias_site = coletar_do_catalogo()
    desde_sitemap = coletar_do_sitemap()

    todos_ids = sorted(set(desde_catalogo) | set(desde_sitemap) | set(canais_estado))
    log("")
    log("  Total de canais a verificar...: %d" % len(todos_ids))
    if desde_sitemap:
        extras = len(set(desde_sitemap) - set(desde_catalogo))
        log("  Canais so no sitemap..........: %d" % extras)
    linha()

    # ------------------------ 2) Dados dos canais -----------------------
    log("[2/4] Lendo pagina de cada canal (nome, logo, categoria, links)")
    dados = {}
    falhas_pagina = []

    def trabalho(cid):
        return coletar_canal(cid)

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(WORKERS_COLETA) as ex:
        for cid, info in ex.map(trabalho, todos_ids):
            if "erro" in info:
                falhas_pagina.append((cid, info["erro"]))
                # reaproveita o que ja temos no estado
                antigo = canais_estado.get(cid)
                if antigo:
                    dados[cid] = {
                        "nome": antigo.get("nome", cid),
                        "logo": antigo.get("logo", ""),
                        "categorias": antigo.get("categorias", []),
                        "streams": antigo.get("streams", []),
                        "pagina": "%s/%s/channel/%s" % (BASE, LOCALE, cid),
                        "pagina_ok": False,
                    }
            else:
                info["pagina_ok"] = True
                dados[cid] = info

    log("  Paginas lidas.................: %d/%d em %.1fs" % (len(dados), len(todos_ids), time.time() - t0))
    if falhas_pagina:
        log("  Falhas ao ler a pagina........: %d (usando dados anteriores)" % len(falhas_pagina))
        for cid, e in falhas_pagina[:5]:
            log("     %-28s %s" % (cid, e))
    linha()

    # --------------------------- 3) Teste -------------------------------
    resultado_teste = {}
    if args.sem_teste:
        log("[3/4] Teste de reproducao DESATIVADO (--sem-teste)")
        for cid, info in dados.items():
            # usa o link preferido e marca como ok (nao testado)
            resultado_teste[cid] = (info["streams"][0] if info["streams"] else None, RESULTADO_OK, "nao testado")
    else:
        log("[3/4] Testando se os links estao tocando de verdade")
        log("      (baixa o manifesto e um segmento de video de cada canal)")
        alvos = []
        for cid, info in dados.items():
            antigo = canais_estado.get(cid)
            if (
                not args.testar_tudo
                and antigo
                and antigo.get("falhas", 0) == 0
                and antigo.get("url")
                and antigo.get("url") in info["streams"]
            ):
                # ja estava funcionando e o link continua o mesmo: pula o teste
                resultado_teste[cid] = (antigo["url"], RESULTADO_OK, "ok (verificado antes)")
            else:
                alvos.append(cid)

        log("      Canais a testar............: %d (de %d)" % (len(alvos), len(dados)))

        def trabalho_teste(cid):
            return cid, testar_canal(dados[cid]["streams"])

        t0 = time.time()
        feitos = 0
        with concurrent.futures.ThreadPoolExecutor(WORKERS_TESTE) as ex:
            for cid, res in ex.map(trabalho_teste, alvos):
                resultado_teste[cid] = res
                feitos += 1
                if feitos % 50 == 0:
                    log("      ... %d/%d testados" % (feitos, len(alvos)))
        log("      Teste concluido em.........: %.1fs" % (time.time() - t0))

        n_ok = sum(1 for r in resultado_teste.values() if r[1] == RESULTADO_OK)
        n_falha = sum(1 for r in resultado_teste.values() if r[1] == RESULTADO_FALHA)
        n_neutro = sum(1 for r in resultado_teste.values() if r[1] == RESULTADO_NEUTRO)
        log("      Tocando....................: %d" % n_ok)
        log("      Link quebrado..............: %d" % n_falha)
        log("      Inconclusivo (geo/rede)....: %d  <- nao contam como falha" % n_neutro)
    linha()

    # ---------------------- 4) Reconciliacao + M3U ----------------------
    log("[4/4] Reconciliando com a atualizacao anterior")

    incluir_instaveis = args.incluir_instaveis
    incluidos = []
    removidos, mantidos, novos, reativados, contagem = [], [], [], [], {}
    agora = agora_br()

    for cid in sorted(dados):
        info = dados[cid]
        antigo = canais_estado.get(cid)
        url_boa, res, det = resultado_teste.get(cid, (None, RESULTADO_FALHA, "nao testado"))

        reg = antigo or {}
        falhas_antigas = int(reg.get("falhas", 0))
        novo_reg = {
            "nome": info["nome"],
            "logo": info.get("logo", ""),
            "categorias": info.get("categorias", []),
            "streams": info.get("streams", []),
            "pagina": info.get("pagina", ""),
            "falhas": falhas_antigas,
            "ultimo_ok": reg.get("ultimo_ok"),
            "ultimo_resultado": res,
            "inativo": reg.get("inativo", False),
        }

        if res == RESULTADO_OK:
            novo_reg["url"] = url_boa
            novo_reg["falhas"] = 0
            novo_reg["ultimo_ok"] = agora
            novo_reg["inativo"] = False
            if antigo is None:
                novos.append(cid)
            elif antigo.get("inativo"):
                reativados.append(cid)
        elif res == RESULTADO_NEUTRO:
            # nao sabemos: mantem como estava, sem contar falha
            novo_reg["url"] = url_boa or reg.get("url") or (info["streams"][0] if info["streams"] else None)
        else:  # falha real
            novo_reg["falhas"] = falhas_antigas + 1
            novo_reg["url"] = url_boa or reg.get("url") or (info["streams"][0] if info["streams"] else None)
            if novo_reg["falhas"] >= limite_falhas:
                novo_reg["inativo"] = True

        if not args.sem_reconciliar:
            canais_estado[cid] = novo_reg

        # decide se entra no M3U
        entra = False
        if res == RESULTADO_OK:
            entra = True
        elif res == RESULTADO_NEUTRO and not novo_reg["inativo"] and novo_reg.get("url"):
            entra = True  # provavelmente so bloqueio de geo
        elif incluir_instaveis and novo_reg.get("url") and not novo_reg["inativo"]:
            entra = True

        if entra:
            incluidos.append(
                {
                    "cid": cid,
                    "nome": info["nome"],
                    "logo": info.get("logo", ""),
                    "categorias": info.get("categorias", []),
                    "url": url_boa or novo_reg.get("url"),
                }
            )
            mantidos.append(cid)
            contagem[cid] = det
        elif novo_reg.get("inativo"):
            removidos.append(cid)

    ids_atuais = set(dados)
    sumiram = [cid for cid in canais_estado if cid not in ids_atuais and not canais_estado[cid].get("inativo")]
    for cid in sumiram:
        canais_estado[cid]["falhas"] = int(canais_estado[cid].get("falhas", 0)) + 1
        if canais_estado[cid]["falhas"] >= limite_falhas:
            canais_estado[cid]["inativo"] = True
            removidos.append(cid)
        else:
            # ainda entra na lista ate atingir o limite
            reg = canais_estado[cid]
            if reg.get("url"):
                incluidos.append(
                    {
                        "cid": cid,
                        "nome": reg.get("nome", cid),
                        "logo": reg.get("logo", ""),
                        "categorias": reg.get("categorias", []),
                        "url": reg["url"],
                    }
                )
                mantidos.append(cid)
                contagem[cid] = "desapareceu do site (%d/%d)" % (reg["falhas"], limite_falhas)

    removidos = sorted(set(removidos))

    cabecalho = [
        "# Lista gerada automaticamente a partir de freetv.studio (canais do Brasil)",
        "# Atualizada em: %s" % agora,
        "# Canais nesta lista: %d" % len(incluidos),
        "# Para SS IPTV: remova e adicione a lista novamente se ela for atualizada",
    ]
    conteudo, total = montar_m3u(incluidos, categorias_site, cabecalho)

    with open(ARQ_SAIDA, "w", encoding="utf-8", newline="\n") as f:
        f.write(conteudo)

    estado["meta"] = {
        "atualizacao": agora,
        "limite_falhas": limite_falhas,
        "total_canais": total,
        "total_ativos": sum(1 for c in canais_estado.values() if not c.get("inativo")),
        "total_removidos": sum(1 for c in canais_estado.values() if c.get("inativo")),
    }
    if not args.sem_reconciliar:
        salvar_json(ARQ_ESTADO, estado)

    relatorio = {
        "atualizacao": agora,
        "limite_falhas": limite_falhas,
        "teste_ativo": not args.sem_teste,
        "encontrados_no_site": len(todos_ids),
        "na_lista": total,
        "novos": len(novos),
        "reativados": len(reativados),
        "removidos": len(removidos),
        "por_resultado": {
            "ok": sum(1 for r in resultado_teste.values() if r[1] == RESULTADO_OK),
            "falha": sum(1 for r in resultado_teste.values() if r[1] == RESULTADO_FALHA),
            "inconclusivo": sum(1 for r in resultado_teste.values() if r[1] == RESULTADO_NEUTRO),
        },
        "por_categoria": {},
        "detalhes": {cid: contagem.get(cid, "") for cid in contagem},
    }
    # O relatorio conta cada canal uma vez, na categoria em que ele aparece.
    _urls_vistas = set()
    for c in incluidos:
        url = (c.get("url") or "").strip()
        if not url or url in _urls_vistas:
            continue
        _urls_vistas.add(url)
        cats = c["categorias"] or ([categoria_por_nome(c["nome"]) or "outros"])
        s = cats[0]
        relatorio["por_categoria"][s] = relatorio["por_categoria"].get(s, 0) + 1
    relatorio["na_lista"] = len(_urls_vistas)
    salvar_json(ARQ_RELATORIO, relatorio)

    linha("=")
    log("  RESULTADO")
    linha("=")
    log("  Canais encontrados no site....: %d" % len(todos_ids))
    log("  Canais na lista M3U..........: %d" % total)
    if not args.sem_teste:
        log("  Testados tocando.............: %d" % relatorio["por_resultado"]["ok"])
        log("  Links quebrados..............: %d" % relatorio["por_resultado"]["falha"])
        log("  Inconclusivos (geo/rede).....: %d" % relatorio["por_resultado"]["inconclusivo"])
    log("  Novos canais.................: %d" % len(novos))
    log("  Canais reativados............: %d" % len(reativados))
    log("  Canais removidos.............: %d" % len(removidos))
    if removidos:
        for cid in removidos[:20]:
            log("     - %s" % cid)
    linha()
    log("  Categorias na lista:")
    for s in ordenar_categorias(list(relatorio["por_categoria"])):
        log("     %-18s %d" % (nome_categoria(s, categorias_site if s != "outros" else None), relatorio["por_categoria"][s]))
    linha()
    log("  Arquivo gerado: freetv_br.m3u")
    log("  Tempo total...: %.1fs" % (time.time() - inicio))
    linha("=")
    log("")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("\nInterrompido pelo usuario.")
        sys.exit(130)
