# -*- coding: utf-8 -*-
"""Coleta diária de preços dos mercados que entregam no CEP alvo (Goiânia).

Mercados: só entram os que publicam preço aberto E entregam no CEP.
  - Atacadão   (VTEX, entrega padrão)
  - Sam's Club (VTEX, entrega em 2h; exige ser sócio para comprar)

Gera:
  docs/dados.js      -> snapshot do dia (window.DADOS)
  docs/historico.js  -> série histórica por produto (window.HISTORICO)

Validação: a coleta só é gravada se cada mercado retornar produtos em pelo
menos MIN_TERMOS_OK dos termos; caso contrário sai com erro 1 e os dados do
dia anterior permanecem publicados.
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARQ_CESTA = RAIZ / "dados" / "cesta.json"
ARQ_DADOS = RAIZ / "docs" / "dados.js"
ARQ_HIST = RAIZ / "docs" / "historico.js"

# regionId sai de /api/checkout/pub/regions?postalCode=<cep>; ambos valem p/ Goiânia.
MERCADOS = [
    {
        "chave": "atacadao",
        "nome": "Atacadão",
        "hosts": ["https://www.atacadao.com.br",
                  "https://atacadaobr.vtexcommercestable.com.br"],
        "regionId": "v2.8B9D31DB122678F95B30FA0A6A5D8B0C",
        "site": "https://www.atacadao.com.br",
        "entrega": "Entrega padrão, ~1 dia útil",
        "aviso": "",
    },
    {
        "chave": "sams",
        "nome": "Sam's Club",
        "hosts": ["https://www.samsclub.com.br"],
        "regionId": "U1cjc2Ftc2NsdWI0OTM0",
        "site": "https://www.samsclub.com.br",
        "entrega": "Entrega em ~2h, frete R$ 12,90",
        "aviso": "Exige ser sócio para comprar",
    },
]

CAMINHO_BUSCA = "/api/io/_v/api/intelligent-search/product_search/trade-policy/1"
RESULTADOS_POR_TERMO = 12
MIN_TERMOS_OK = 0.7
DIAS_HISTORICO = 200
FUSO_GO = timezone(timedelta(hours=-3))

# Um mesmo código de barras pode ser vendido como unidade num mercado e como
# fardo/pacote no outro (o Sam's faz muito isso). Comparar sem normalizar dá
# "88% mais barato" que é falso. Depois de dividir pelo tamanho da embalagem,
# uma diferença acima disso indica que ainda são coisas diferentes: descartamos.
DIF_MAX_CONFIAVEL = 0.60

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def buscar(mercado, termo):
    params = urllib.parse.urlencode({
        "query": termo,
        "count": RESULTADOS_POR_TERMO,
        "regionId": mercado["regionId"],
        "hideUnavailableItems": "true",
    })
    for host in mercado["hosts"]:
        url = f"{host}{CAMINHO_BUSCA}?{params}"
        for tentativa in range(2):
            try:
                req = urllib.request.Request(url, headers={
                    "User-Agent": UA, "Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=25) as resp:
                    return json.load(resp).get("products", [])
            except Exception as e:
                print(f"  aviso: {host} tentativa {tentativa+1} falhou ({e})")
                time.sleep(2)
    return []


PADROES_EMBALAGEM = [
    re.compile(r"(\d{1,2})\s*[xX]\s*\d", re.I),          # 8x350ml
    re.compile(r"[-–]\s*(\d{1,2})\s*unidades?", re.I),   # - 4 unidades
    re.compile(r"\bc/\s*(\d{1,2})\b", re.I),             # c/ 12
    re.compile(r"\b(\d{1,2})\s*un(?:id)?\b", re.I),      # 12 un
    re.compile(r"\bpack\s*(\d{1,2})\b", re.I),           # pack 6
    re.compile(r"\bkit\s*(\d{1,2})\b", re.I),            # kit 5
]


def tamanho_embalagem(produto):
    """Quantas unidades vêm no pacote. Prioriza a propriedade da loja."""
    for prop in (produto.get("properties") or []):
        if "quantidade na embalagem" in prop.get("name", "").lower():
            for valor in prop.get("values", []):
                m = re.search(r"(\d{1,3})", str(valor))
                if m and 1 <= int(m.group(1)) <= 100:
                    return int(m.group(1))
    nome = produto.get("productName", "")
    for padrao in PADROES_EMBALAGEM:
        m = padrao.search(nome)
        if m and 2 <= int(m.group(1)) <= 100:
            return int(m.group(1))
    return 1


def extrair(produto, mercado, termo, categoria):
    """Converte um produto VTEX no formato do app. None se não tiver preço."""
    itens = produto.get("items") or []
    if not itens:
        return None
    item = itens[0]
    oferta = None
    for v in (item.get("sellers") or []):
        o = v.get("commertialOffer") or {}
        if o.get("Price") and o.get("AvailableQuantity"):
            oferta = o
            break
    if not oferta:
        return None
    imagens = item.get("images") or []
    link_texto = produto.get("linkText", "")
    preco = round(float(oferta["Price"]), 2)
    emb = tamanho_embalagem(produto)
    return {
        "id": f"{mercado['chave']}:{item.get('itemId')}",
        "ean": (item.get("ean") or "").strip(),
        "nome": produto.get("productName", "").strip(),
        "marca": produto.get("brand", ""),
        "mercado": mercado["chave"],
        "categoria": categoria,
        "termo": termo,
        "preco": preco,
        "precoDe": round(float(oferta.get("ListPrice") or 0), 2),
        "emb": emb,
        "precoUnit": round(preco / emb, 4),
        "link": f"{mercado['site']}/{link_texto}/p",
        "img": (imagens[0].get("imageUrl", "") if imagens else ""),
    }


def carregar_historico():
    if not ARQ_HIST.exists():
        return {}
    texto = ARQ_HIST.read_text(encoding="utf-8")
    ini, fim = texto.find("{"), texto.rfind("}")
    if ini < 0:
        return {}
    return json.loads(texto[ini:fim + 1])


def coletar_mercado(mercado, cesta):
    produtos, vistos = [], set()
    total = ok = 0
    for cat in cesta["categorias"]:
        for termo in cat["termos"]:
            total += 1
            novos = 0
            for p in buscar(mercado, termo):
                reg = extrair(p, mercado, termo, cat["nome"])
                if reg and reg["id"] not in vistos:
                    vistos.add(reg["id"])
                    produtos.append(reg)
                    novos += 1
            if novos:
                ok += 1
            print(f"  [{mercado['nome']}] {termo}: {novos}")
            time.sleep(0.6)
    return produtos, ok, total


def main():
    cesta = json.loads(ARQ_CESTA.read_text(encoding="utf-8"))
    hoje = datetime.now(FUSO_GO)
    dia = hoje.strftime("%Y-%m-%d")

    todos = []
    for mercado in MERCADOS:
        print(f"== {mercado['nome']} ==")
        produtos, ok, total = coletar_mercado(mercado, cesta)
        taxa = ok / max(total, 1)
        if taxa < MIN_TERMOS_OK:
            print(f"ERRO: {mercado['nome']} só respondeu {ok}/{total} termos "
                  f"({taxa:.0%}). Dados NÃO gravados.")
            sys.exit(1)
        print(f"   {len(produtos)} produtos, {ok}/{total} termos")
        todos.extend(produtos)

    # Comparativo: mesmo código de barras em mais de um mercado, comparado
    # sempre pelo preço POR UNIDADE (fardo de 8 vs lata avulsa).
    por_ean = {}
    for p in todos:
        if p["ean"]:
            atual = por_ean.setdefault(p["ean"], {}).get(p["mercado"])
            if atual is None or p["precoUnit"] < atual["precoUnit"]:
                por_ean[p["ean"]][p["mercado"]] = p

    comparaveis, descartados = {}, 0
    for ean, d in por_ean.items():
        if len(d) < 2:
            continue
        unit = [v["precoUnit"] for v in d.values()]
        menor, maior = min(unit), max(unit)
        if maior and (maior - menor) / maior > DIF_MAX_CONFIAVEL:
            descartados += 1
            continue
        comparaveis[ean] = {m: {"precoUnit": v["precoUnit"], "preco": v["preco"],
                                "emb": v["emb"], "id": v["id"]}
                            for m, v in d.items()}
    print(f"Comparáveis: {len(comparaveis)} "
          f"({descartados} descartados por diferença implausível)")

    historico = carregar_historico()
    corte = (hoje - timedelta(days=DIAS_HISTORICO)).strftime("%Y-%m-%d")
    for reg in todos:
        h = historico.setdefault(reg["id"], {"n": reg["nome"], "p": {}})
        h["n"] = reg["nome"]
        h["p"][dia] = reg["preco"]
        h["p"] = {d: v for d, v in sorted(h["p"].items()) if d >= corte}

    dados = {
        "geradoEm": hoje.isoformat(timespec="minutes"),
        "cidade": cesta["cidade"],
        "cep": cesta["cep"],
        "mercados": [{k: m[k] for k in ("chave", "nome", "site", "entrega", "aviso")}
                     for m in MERCADOS],
        "categorias": [c["nome"] for c in cesta["categorias"]],
        "comparaveis": comparaveis,
        "produtos": todos,
    }
    ARQ_DADOS.write_text(
        "window.DADOS = " + json.dumps(dados, ensure_ascii=False) + ";\n",
        encoding="utf-8")
    ARQ_HIST.write_text(
        "window.HISTORICO = " + json.dumps(historico, ensure_ascii=False) + ";\n",
        encoding="utf-8")
    print(f"OK: {len(todos)} produtos de {len(MERCADOS)} mercados. "
          f"Histórico com {len(historico)} itens.")


if __name__ == "__main__":
    main()
