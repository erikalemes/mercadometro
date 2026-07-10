# 🛒 MercadôMetro

Comparador de preços de mercado para o CEP 74655-080 (Goiânia-GO), com lista
de compras e link para finalizar a compra com entrega.

**Site:** https://erikalemes.github.io/mercadometro/

## Mercados monitorados

Entram só os que **publicam preço aberto** e **entregam no CEP**:

| Mercado | Entrega | Observação |
|---|---|---|
| Atacadão | Entrega padrão, ~1 dia útil | — |
| Sam's Club | ~2h, frete R$ 12,90 | Exige ser sócio para comprar |

Testados e descartados: **Bretas** (não entrega no CEP e só mostra preço após
login), **Carrefour** (não entrega mercado em Goiânia), **Assaí** (sem loja
online própria, vende via iFood), **Mart Minas** (site institucional, sem
e-commerce), **Villefort** (a API da loja online, `api-loja.villefortentrega.com.br`,
está fora do ar — recusa conexão).

## Como funciona

1. Todos os dias às 06:00 (horário de Goiânia), o GitHub Actions roda
   `scripts/coletar.py`, que consulta a API pública VTEX de cada mercado,
   regionalizada para o CEP em `dados/cesta.json`.
2. O robô busca os 56 termos da cesta, guarda o snapshot do dia em
   `docs/dados.js` e acumula a série histórica em `docs/historico.js` (200 dias).
3. O site em `docs/` (GitHub Pages) permite buscar, comparar mercados, montar
   a lista com total estimado e enviar pelo WhatsApp. A compra é finalizada no
   site do mercado.

## Comparação por unidade

O mesmo código de barras pode ser vendido como lata avulsa num mercado e como
fardo de 8 no outro. Comparar o preço cheio daria "88% mais barato", que é
falso. Por isso o coletor extrai o tamanho da embalagem (da propriedade
"Quantidade na Embalagem" ou do nome do produto) e **compara sempre o preço por
unidade**. Pares que continuam com mais de 60% de diferença depois disso são
descartados, por indicarem que ainda são produtos diferentes.

## Rodar a coleta manualmente

```bash
python scripts/coletar.py
```

A coleta só grava se cada mercado retornar produtos em pelo menos 70% dos
termos; caso contrário sai com erro e os dados anteriores permanecem no ar.

## Limitações conhecidas

- Os preços são do e-commerce e podem diferir da loja física ou do total final
  no fechamento da compra.
- O comparativo cobre só os produtos com código de barras presente nos dois
  mercados (hoje ~40 dos 905 coletados).
