# -*- coding: utf-8 -*-
"""Coleta diária de preços do Atacadão (Goiânia) via API pública VTEX.

Gera:
  docs/dados.js      -> snapshot do dia (window.DADOS)
  docs/historico.js  -> série histórica por produto (window.HISTORICO)

Validação: a coleta só é gravada se pelo menos MIN_TERMOS_OK dos termos
da cesta retornarem produtos com preço; caso contrário sai com erro 1 e
os dados do dia anterior permanecem publicados.
"""
import json
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

REGION_ID = "v2.8B9D31DB122678F95B30FA0A6A5D8B0C"  # CEP 74810-100, Goiânia-GO
HOSTS = [
    "https://www.atacadao.com.br",
    "https://atacadaobr.vtexcommercestable.com.br",
]
CAMINHO_BUSCA = "/api/io/_v/api/intelligent-search/product_search/trade-policy/1"
RESULTADOS_POR_TERMO = 12
MIN_TERMOS_OK = 0.7  # fração mínima de termos com resultado
DIAS_HISTORICO = 200
FUSO_GO = timezone(timedelta(hours=-3))

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def buscar(termo):
    """Consulta um termo na API; tenta os hosts na ordem. Retorna lista de produtos."""
    params = urllib.parse.urlencode({
        "query": termo,
        "count": RESULTADOS_POR_TERMO,
        "regionId": REGION_ID,
        "hideUnavailableItems": "true",
    })
    for host in HOSTS:
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


def extrair(produto, termo, categoria):
    """Converte um produto VTEX no formato enxuto do app. None se sem preço."""
    itens = produto.get("items") or []
    if not itens:
        return None
    item = itens[0]
    vendedores = item.get("sellers") or []
    oferta = None
    for v in vendedores:
        o = v.get("commertialOffer") or {}
        if o.get("Price") and o.get("AvailableQuantity"):
            oferta = o
            break
    if not oferta:
        return None
    imagens = item.get("images") or []
    return {
        "id": item.get("itemId"),
        "ean": item.get("ean") or "",
        "nome": produto.get("productName", "").strip(),
        "marca": produto.get("brand", ""),
        "categoria": categoria,
        "termo": termo,
        "preco": round(float(oferta["Price"]), 2),
        "precoDe": round(float(oferta.get("ListPrice") or 0), 2),
        "link": f"https://www.atacadao.com.br/{produto.get('linkText','')}/p",
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


def main():
    cesta = json.loads(ARQ_CESTA.read_text(encoding="utf-8"))
    hoje = datetime.now(FUSO_GO)
    dia = hoje.strftime("%Y-%m-%d")

    produtos, vistos = [], set()
    total_termos = ok_termos = 0
    for cat in cesta["categorias"]:
        for termo in cat["termos"]:
            total_termos += 1
            achados = buscar(termo)
            novos = 0
            for p in achados:
                reg = extrair(p, termo, cat["nome"])
                if reg and reg["id"] not in vistos:
                    vistos.add(reg["id"])
                    produtos.append(reg)
                    novos += 1
            if novos:
                ok_termos += 1
            print(f"[{ok_termos}/{total_termos}] {termo}: {novos} produtos")
            time.sleep(0.6)

    taxa = ok_termos / max(total_termos, 1)
    if taxa < MIN_TERMOS_OK:
        print(f"ERRO: só {ok_termos}/{total_termos} termos retornaram "
              f"({taxa:.0%} < {MIN_TERMOS_OK:.0%}). Dados NÃO gravados.")
        sys.exit(1)

    historico = carregar_historico()
    corte = (hoje - timedelta(days=DIAS_HISTORICO)).strftime("%Y-%m-%d")
    for reg in produtos:
        h = historico.setdefault(reg["id"], {"n": reg["nome"], "p": {}})
        h["n"] = reg["nome"]
        h["p"][dia] = reg["preco"]
        h["p"] = {d: v for d, v in sorted(h["p"].items()) if d >= corte}

    dados = {
        "geradoEm": hoje.isoformat(timespec="minutes"),
        "cidade": cesta["cidade"],
        "mercado": {"nome": "Atacadão", "site": "https://www.atacadao.com.br"},
        "categorias": [c["nome"] for c in cesta["categorias"]],
        "produtos": produtos,
    }
    ARQ_DADOS.write_text(
        "window.DADOS = " + json.dumps(dados, ensure_ascii=False) + ";\n",
        encoding="utf-8")
    ARQ_HIST.write_text(
        "window.HISTORICO = " + json.dumps(historico, ensure_ascii=False) + ";\n",
        encoding="utf-8")
    print(f"OK: {len(produtos)} produtos de {ok_termos}/{total_termos} termos. "
          f"Histórico com {len(historico)} itens.")


if __name__ == "__main__":
    main()
