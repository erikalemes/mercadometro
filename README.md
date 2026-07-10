# 🛒 MercadôMetro

Busca de preços de mercado em Goiânia-GO com lista de compras e link para
finalizar a compra com entrega.

**Site:** https://erikalemes.github.io/mercadometro/

## Como funciona

1. Todos os dias às 06:00 (horário de Goiânia), o GitHub Actions roda
   `scripts/coletar.py`, que consulta a API pública da loja online do
   Atacadão (plataforma VTEX) regionalizada para Goiânia (CEP 74810-100).
2. O robô busca os 56 termos da cesta em `dados/cesta.json`, guarda o
   snapshot do dia em `docs/dados.js` e acumula a série histórica de cada
   produto em `docs/historico.js` (até 200 dias).
3. O site em `docs/` (GitHub Pages) permite buscar produtos, montar a lista
   de compras com total estimado, ver o que caiu ou subiu de preço e enviar
   a lista pelo WhatsApp. A compra é finalizada no site do mercado ou no iFood.

## Rodar a coleta manualmente

```bash
python scripts/coletar.py
```

A coleta só grava se pelo menos 70% dos termos retornarem produtos com
preço; caso contrário os dados anteriores permanecem.

## Limitações conhecidas

- Só o Atacadão publica preços abertos e regionalizados para Goiânia.
  Bretas exige login no app; Carrefour não entrega mercado em Goiânia;
  Assaí não tem loja online própria (compra via iFood).
- Os preços são do e-commerce e podem diferir da loja física ou do total
  final no fechamento da compra.
