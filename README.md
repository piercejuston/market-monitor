# Prediction Market Monitor

![Market Monitor Demo](demo.gif)

Real-time market monitoring dashboard for cross-platform prediction market
spreads, built as part of a longer-running project scanning **Kalshi** and
**Polymarket's** overlapping 15-minute crypto contracts (BTC, ETH, SOL, XRP).

This isn't a weekend toy. It's the visualization layer on top of a bot that's
been running continuously — polling two separate REST/CLOB APIs every 30
seconds, matching contracts across platforms, detecting spreads, simulating
fill-adjusted execution, and logging every scan to a persistent database. This
repo shows the piece of that system built to *watch* it happen in real time.

## What's actually going on under the hood

- **Two live data sources, polled in parallel** — Kalshi's authenticated REST
  API (RSA-signed requests) and Polymarket's CLOB API, matched against each
  other every 30 seconds across four assets
- **A real database backend** — every price snapshot and simulated trade is
  persisted to SQLite, not just held in memory, so history survives restarts
  and can be queried independently of the live process
- **Spread detection with realistic execution modeling** — simulated trades
  account for per-leg slippage, partial fill rates, and spread decay from
  timing lag, rather than assuming perfect theoretical arbitrage
- **This dashboard** — reads that database and serves a live, auto-refreshing
  web UI: per-asset price charts, a spread comparison table with intensity
  bars, and a real-time spread alert feed

## Run it

Python 3, standard library only — no dependencies to install.

```bash
python market_monitor.py
```

Open **http://localhost:8768**. It refreshes every 10 seconds against
`arb_trades_v2.db` in the same folder.

## The data in this repo is real

`arb_trades_v2.db` is seeded with an actual ~50-minute slice of logged output
from a live run of the bot — **344 real price snapshots and 45 real simulated
trades**, not synthetic filler. You're looking at genuine spread behavior
between two markets pricing the same underlying event slightly differently,
including the moments that behavior briefly looked like real opportunity and
the (more common) moments it evaporated before execution could happen.

## What it looks like

- **Live price charts** — Kalshi vs. Polymarket price lines per asset,
  switchable to a spread view
- **Spread comparison table** — all four assets side by side with animated
  bars scaled to alert threshold
- **Spread alert feed** — timestamped log of every spread spike above 8%
- **Summary stats** — snapshot count, trades detected, average spread,
  simulated P&L

## Design

Editorial rather than terminal — Instrument Serif for headers, Geist Mono
for data, meant to read closer to a financial newspaper than a dark trading
console.

## Context

This dashboard is one component of a larger cross-platform arbitrage-bot
project. The full system also includes authenticated Kalshi API integration,
a fee- and slippage-adjusted trade simulator, and a second dashboard variant.
This repo isolates the monitoring layer for showcase purposes.
