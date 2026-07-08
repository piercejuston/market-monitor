"""
Prediction Market Monitor
=========================
Real-time price & spread monitoring across Kalshi and Polymarket.
Reads from arb_trades_v2.db and serves a live web dashboard.

Usage:
    python market_monitor.py
    Then open http://localhost:8768
"""
import json, os, sqlite3
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

DB_PATH = os.getenv("DB_PATH", "arb_trades_v2.db")
PORT    = 8768
ASSETS  = ["BTC", "ETH", "SOL", "XRP"]
ALERT_THRESHOLD = 0.08   # flag spreads above 8%


def get_data() -> dict:
    if not os.path.exists(DB_PATH):
        return {"error": "Database not found — make sure the bot is running."}
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        # ── Per-asset price history (last 60 rows each) ──────────────────
        asset_series = {}
        for asset in ASSETS:
            rows = conn.execute("""
                SELECT ts,
                       kalshi_yes_ask, kalshi_no_ask,
                       poly_up_ask,   poly_down_ask,
                       spread_up,     spread_down
                FROM price_log
                WHERE asset = ?
                ORDER BY id DESC LIMIT 60
            """, (asset,)).fetchall()
            rows = list(reversed(rows))
            asset_series[asset] = {
                "labels":       [r["ts"] for r in rows],
                "kalshi":       [round(r["kalshi_yes_ask"] or 0, 4) for r in rows],
                "poly":         [round(r["poly_up_ask"]   or 0, 4) for r in rows],
                "spread":       [round((r["spread_up"]    or 0) * 100, 2) for r in rows],
                "kalshi_no":    [round(r["kalshi_no_ask"] or 0, 4) for r in rows],
                "poly_down":    [round(r["poly_down_ask"] or 0, 4) for r in rows],
                "spread_down":  [round((r["spread_down"]  or 0) * 100, 2) for r in rows],
            }

        # ── Latest prices per asset ──────────────────────────────────────
        latest = {}
        for asset in ASSETS:
            row = conn.execute("""
                SELECT kalshi_yes_ask, kalshi_yes_bid,
                       poly_up_ask,   poly_up_bid,
                       spread_up,     kalshi_strike
                FROM price_log WHERE asset = ?
                ORDER BY id DESC LIMIT 1
            """, (asset,)).fetchone()
            if row:
                spread = (row["spread_up"] or 0) * 100
                latest[asset] = {
                    "kalshi_ask":  round(row["kalshi_yes_ask"] or 0, 3),
                    "kalshi_bid":  round(row["kalshi_yes_bid"] or 0, 3),
                    "poly_ask":    round(row["poly_up_ask"]    or 0, 3),
                    "poly_bid":    round(row["poly_up_bid"]    or 0, 3),
                    "spread":      round(spread, 2),
                    "strike":      row["kalshi_strike"] or 0,
                    "alert":       spread >= ALERT_THRESHOLD * 100,
                }
            else:
                latest[asset] = {}

        # ── Alerts: spikes in the last 5 price rows ──────────────────────
        alerts = conn.execute("""
            SELECT ts, asset, ROUND(spread_up * 100, 1) as sprd
            FROM price_log
            WHERE ABS(spread_up) >= ?
            ORDER BY id DESC LIMIT 10
        """, (ALERT_THRESHOLD,)).fetchall()
        alerts = [dict(r) for r in alerts]

        # ── Summary stats ────────────────────────────────────────────────
        total_snaps  = conn.execute("SELECT COUNT(*) FROM price_log").fetchone()[0]
        total_trades = conn.execute("SELECT COUNT(*) FROM arb_trades").fetchone()[0]
        total_pnl    = conn.execute("SELECT COALESCE(SUM(pnl),0) FROM arb_trades").fetchone()[0]
        avg_spread   = conn.execute("""
            SELECT AVG(ABS(spread_up)) FROM price_log
            WHERE spread_up != 0
        """).fetchone()[0] or 0

        conn.close()

        return {
            "ok":           True,
            "ts":           datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
            "series":       asset_series,
            "latest":       latest,
            "alerts":       alerts,
            "total_snaps":  total_snaps,
            "total_trades": total_trades,
            "total_pnl":    round(total_pnl, 2),
            "avg_spread":   round(avg_spread * 100, 2),
            "alert_thresh": ALERT_THRESHOLD * 100,
        }
    except Exception as e:
        return {"error": str(e)}


# ── HTML ─────────────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Market Monitor — Kalshi × Polymarket</title>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Geist+Mono:wght@300;400;500&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg:      #f5f4f0;
  --paper:   #faf9f6;
  --ink:     #1a1916;
  --muted:   #8a8880;
  --border:  #e2e0da;
  --accent:  #1a1916;
  --green:   #1a6b45;
  --red:     #8b2020;
  --amber:   #92600a;
  --serif:   'Instrument Serif', Georgia, serif;
  --mono:    'Geist Mono', 'Courier New', monospace;
}

html, body {
  background: var(--bg);
  color: var(--ink);
  font-family: var(--mono);
  font-size: 13px;
  min-height: 100vh;
}

/* ── TOP BAR ── */
.topbar {
  background: var(--ink);
  color: var(--bg);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 32px;
  height: 52px;
  position: sticky;
  top: 0;
  z-index: 100;
}

.topbar-brand {
  font-family: var(--serif);
  font-size: 20px;
  letter-spacing: -0.5px;
  display: flex;
  align-items: center;
  gap: 16px;
}

.topbar-brand .divider-dot {
  width: 4px; height: 4px;
  border-radius: 50%;
  background: #555;
}

.topbar-brand .sub {
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 3px;
  color: #666;
  text-transform: uppercase;
  font-style: normal;
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 24px;
  font-size: 11px;
  color: #666;
  letter-spacing: 1px;
}

.live-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #4ade80;
  font-size: 10px;
  letter-spacing: 2px;
  text-transform: uppercase;
}

.live-dot {
  width: 5px; height: 5px;
  border-radius: 50%;
  background: #4ade80;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50%       { opacity: 0.5; transform: scale(0.8); }
}

/* ── LAYOUT ── */
.main {
  max-width: 1400px;
  margin: 0 auto;
  padding: 32px;
}

/* ── SUMMARY ROW ── */
.summary {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1px;
  background: var(--border);
  border: 1px solid var(--border);
  margin-bottom: 32px;
}

.stat {
  background: var(--paper);
  padding: 24px 28px;
  position: relative;
}

.stat-label {
  font-size: 9px;
  letter-spacing: 3px;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 10px;
}

.stat-val {
  font-family: var(--serif);
  font-size: 34px;
  letter-spacing: -1px;
  line-height: 1;
}

.stat-sub {
  font-size: 10px;
  color: var(--muted);
  margin-top: 6px;
  letter-spacing: 1px;
}

.green { color: var(--green); }
.red   { color: var(--red); }
.amber { color: var(--amber); }

/* ── ASSET GRID ── */
.asset-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1px;
  background: var(--border);
  border: 1px solid var(--border);
  margin-bottom: 32px;
}

.asset-panel {
  background: var(--paper);
  padding: 0;
  overflow: hidden;
}

.asset-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 24px;
  border-bottom: 1px solid var(--border);
}

.asset-name {
  font-family: var(--serif);
  font-size: 22px;
  letter-spacing: -1px;
  display: flex;
  align-items: center;
  gap: 10px;
}

.asset-color {
  width: 10px; height: 10px;
  border-radius: 50%;
}

.asset-prices {
  display: flex;
  gap: 20px;
  font-size: 11px;
}

.price-item { text-align: right; }
.price-item .plabel { color: var(--muted); margin-bottom: 3px; letter-spacing: 1px; }
.price-item .pval   { font-size: 15px; font-weight: 500; letter-spacing: -0.5px; }

.spread-badge {
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 1px;
  border: 1px solid currentColor;
}

.spread-badge.hot  { color: var(--red);   background: rgba(139,32,32,0.06); }
.spread-badge.warm { color: var(--amber); background: rgba(146,96,10,0.06); }
.spread-badge.cool { color: var(--muted); background: transparent; }

.chart-tabs {
  display: flex;
  border-bottom: 1px solid var(--border);
}

.chart-tab {
  padding: 10px 20px;
  font-size: 10px;
  letter-spacing: 2px;
  text-transform: uppercase;
  cursor: pointer;
  color: var(--muted);
  border-bottom: 2px solid transparent;
  transition: all 0.15s;
  background: none;
  border-left: none;
  border-right: none;
  border-top: none;
}

.chart-tab.active {
  color: var(--ink);
  border-bottom-color: var(--ink);
}

.chart-wrap {
  padding: 16px 20px 12px;
  height: 180px;
  position: relative;
}

.chart-canvas { display: none; width: 100%; height: 100%; }
.chart-canvas.active { display: block; }

/* ── BOTTOM ROW ── */
.bottom-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1px;
  background: var(--border);
  border: 1px solid var(--border);
}

.panel {
  background: var(--paper);
  overflow: hidden;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px;
  border-bottom: 1px solid var(--border);
}

.panel-title {
  font-size: 10px;
  letter-spacing: 3px;
  text-transform: uppercase;
  color: var(--muted);
}

.panel-body { padding: 0; }

/* Spread table */
.spread-table { width: 100%; border-collapse: collapse; }
.spread-table th {
  font-size: 9px;
  letter-spacing: 2px;
  text-transform: uppercase;
  color: var(--muted);
  font-weight: 400;
  padding: 10px 24px;
  text-align: left;
  border-bottom: 1px solid var(--border);
}
.spread-table td {
  padding: 14px 24px;
  border-bottom: 1px solid var(--border);
  font-size: 12px;
}
.spread-table tr:last-child td { border-bottom: none; }
.spread-table tr:hover td { background: rgba(0,0,0,0.02); }

.spread-bar-cell { width: 120px; }
.sbar-track { height: 2px; background: var(--border); width: 100%; }
.sbar-fill  { height: 100%; background: var(--ink); transition: width 0.5s ease; }

/* Alerts */
.alert-list { padding: 0; }
.alert-item {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px 24px;
  border-bottom: 1px solid var(--border);
  animation: alertIn 0.3s ease forwards;
}
@keyframes alertIn {
  from { opacity: 0; transform: translateX(-8px); }
  to   { opacity: 1; transform: translateX(0); }
}
.alert-item:last-child { border-bottom: none; }
.alert-icon { font-size: 14px; }
.alert-asset {
  font-family: var(--serif);
  font-size: 16px;
  letter-spacing: -0.5px;
  width: 40px;
}
.alert-spread { color: var(--red); font-weight: 500; flex: 1; }
.alert-time   { color: var(--muted); font-size: 11px; }
.no-alerts {
  padding: 32px 24px;
  color: var(--muted);
  font-size: 11px;
  letter-spacing: 1px;
  text-align: center;
}

/* ── ERROR STATE ── */
.error-wrap {
  padding: 80px 32px;
  text-align: center;
  color: var(--muted);
}
.error-title {
  font-family: var(--serif);
  font-size: 28px;
  color: var(--ink);
  margin-bottom: 12px;
}

/* ── FOOTER ── */
.footer {
  max-width: 1400px;
  margin: 0 auto;
  padding: 20px 32px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 10px;
  color: var(--muted);
  letter-spacing: 1px;
}

@media (max-width: 900px) {
  .asset-grid, .bottom-row { grid-template-columns: 1fr; }
  .summary { grid-template-columns: repeat(2, 1fr); }
}
</style>
</head>
<body>

<!-- TOP BAR -->
<div class="topbar">
  <div class="topbar-brand">
    Market Monitor
    <span class="divider-dot"></span>
    <span class="sub">Kalshi × Polymarket</span>
  </div>
  <div class="topbar-right">
    <div class="live-badge">
      <div class="live-dot"></div>
      Live
    </div>
    <span id="last-update">--:-- UTC</span>
    <span>Auto-refresh 10s</span>
  </div>
</div>

<div class="main" id="main-content">

  <!-- SUMMARY -->
  <div class="summary" id="summary">
    <div class="stat">
      <div class="stat-label">Price Snapshots</div>
      <div class="stat-val" id="s-snaps">—</div>
      <div class="stat-sub">Total recorded</div>
    </div>
    <div class="stat">
      <div class="stat-label">Arbs Detected</div>
      <div class="stat-val" id="s-trades">—</div>
      <div class="stat-sub">Sim trades logged</div>
    </div>
    <div class="stat">
      <div class="stat-label">Avg Spread</div>
      <div class="stat-val amber" id="s-spread">—</div>
      <div class="stat-sub">Across all assets</div>
    </div>
    <div class="stat">
      <div class="stat-label">Sim P&L</div>
      <div class="stat-val green" id="s-pnl">—</div>
      <div class="stat-sub">Paper trading only</div>
    </div>
  </div>

  <!-- ASSET CHARTS -->
  <div class="asset-grid" id="asset-grid">
    <!-- Injected by JS -->
  </div>

  <!-- BOTTOM ROW -->
  <div class="bottom-row">
    <div class="panel">
      <div class="panel-header">
        <span class="panel-title">Spread Comparison</span>
        <span style="font-size:10px;color:var(--muted)">Current · All Assets</span>
      </div>
      <div class="panel-body">
        <table class="spread-table">
          <thead>
            <tr>
              <th>Asset</th>
              <th>Kalshi Ask</th>
              <th>Poly Ask</th>
              <th>Spread</th>
              <th class="spread-bar-cell">Intensity</th>
            </tr>
          </thead>
          <tbody id="spread-tbody"></tbody>
        </table>
      </div>
    </div>

    <div class="panel">
      <div class="panel-header">
        <span class="panel-title">Spread Alerts</span>
        <span style="font-size:10px;color:var(--muted)" id="alert-thresh">— threshold</span>
      </div>
      <div class="panel-body">
        <div class="alert-list" id="alert-list">
          <div class="no-alerts">No alerts yet — monitoring...</div>
        </div>
      </div>
    </div>
  </div>

</div>

<div class="footer">
  <span>Prediction Market Monitor — Kalshi × Polymarket · 15-min crypto contracts</span>
  <span>BTC · ETH · SOL · XRP</span>
</div>

<script>
const ASSET_COLORS = {
  BTC: '#b87333',
  ETH: '#627eea',
  SOL: '#9945ff',
  XRP: '#0080c6',
};

const CHART_DEFAULTS = {
  responsive: true,
  maintainAspectRatio: false,
  animation: { duration: 400 },
  interaction: { mode: 'index', intersect: false },
  plugins: {
    legend: {
      display: true,
      position: 'top',
      labels: {
        font: { family: 'Geist Mono', size: 10 },
        color: '#8a8880',
        boxWidth: 12,
        padding: 12,
        usePointStyle: true,
        pointStyleWidth: 8,
      }
    },
    tooltip: {
      backgroundColor: '#1a1916',
      titleColor: '#8a8880',
      bodyColor: '#f5f4f0',
      borderColor: '#333',
      borderWidth: 1,
      padding: 12,
      titleFont: { family: 'Geist Mono', size: 10 },
      bodyFont:  { family: 'Geist Mono', size: 12 },
    }
  },
  scales: {
    x: {
      ticks: { color: '#aaa8a0', font: { family: 'Geist Mono', size: 9 }, maxTicksLimit: 6 },
      grid:  { color: 'rgba(0,0,0,0.04)' },
    },
    y: {
      ticks: { color: '#aaa8a0', font: { family: 'Geist Mono', size: 9 }, maxTicksLimit: 5 },
      grid:  { color: 'rgba(0,0,0,0.04)' },
    }
  }
};

// Build asset panels on first load
function buildPanels(assets) {
  const grid = document.getElementById('asset-grid');
  grid.innerHTML = '';
  assets.forEach(asset => {
    const color = ASSET_COLORS[asset] || '#555';
    grid.innerHTML += `
    <div class="asset-panel">
      <div class="asset-header">
        <div class="asset-name">
          <span class="asset-color" style="background:${color}"></span>
          ${asset}
        </div>
        <div class="asset-prices">
          <div class="price-item">
            <div class="plabel">Kalshi Ask</div>
            <div class="pval" id="p-kalshi-${asset}">—</div>
          </div>
          <div class="price-item">
            <div class="plabel">Poly Ask</div>
            <div class="pval" id="p-poly-${asset}">—</div>
          </div>
          <div class="price-item">
            <div class="plabel">Spread</div>
            <div id="p-badge-${asset}" class="spread-badge cool">—</div>
          </div>
        </div>
      </div>
      <div class="chart-tabs">
        <button class="chart-tab active" onclick="switchTab('${asset}','price',this)">Price</button>
        <button class="chart-tab" onclick="switchTab('${asset}','spread',this)">Spread</button>
      </div>
      <div class="chart-wrap">
        <canvas id="c-price-${asset}" class="chart-canvas active"></canvas>
        <canvas id="c-spread-${asset}" class="chart-canvas"></canvas>
      </div>
    </div>`;
  });
}

const charts = {};

function switchTab(asset, type, btn) {
  const wrap = btn.closest('.asset-panel').querySelector('.chart-wrap');
  wrap.querySelectorAll('.chart-canvas').forEach(c => c.classList.remove('active'));
  wrap.querySelector(`#c-${type}-${asset}`).classList.add('active');
  btn.closest('.chart-tabs').querySelectorAll('.chart-tab').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
}

function makeOrUpdate(id, type, labels, datasets) {
  const canvas = document.getElementById(id);
  if (!canvas) return;
  if (charts[id]) {
    charts[id].data.labels = labels;
    datasets.forEach((ds, i) => {
      if (charts[id].data.datasets[i]) {
        charts[id].data.datasets[i].data = ds.data;
      }
    });
    charts[id].update('none');
  } else {
    charts[id] = new Chart(canvas.getContext('2d'), {
      type,
      data: { labels, datasets },
      options: JSON.parse(JSON.stringify(CHART_DEFAULTS))
    });
  }
}

function render(d) {
  if (d.error) {
    document.getElementById('main-content').innerHTML = `
      <div class="error-wrap">
        <div class="error-title">No data yet</div>
        <p style="font-size:12px;margin-top:8px">${d.error}</p>
        <p style="margin-top:16px;font-size:11px;color:#aaa">Make sure kalshi_poly_arb_v2.py is running first.</p>
      </div>`;
    return;
  }

  document.getElementById('last-update').textContent = d.ts;

  // Summary stats
  document.getElementById('s-snaps').textContent  = d.total_snaps.toLocaleString();
  document.getElementById('s-trades').textContent = d.total_trades.toLocaleString();
  document.getElementById('s-spread').textContent = d.avg_spread + '%';
  const pnlEl = document.getElementById('s-pnl');
  pnlEl.textContent = (d.total_pnl >= 0 ? '+$' : '-$') + Math.abs(d.total_pnl).toFixed(2);
  pnlEl.className = 'stat-val ' + (d.total_pnl >= 0 ? 'green' : 'red');

  document.getElementById('alert-thresh').textContent = d.alert_thresh + '% threshold';

  // Build panels if not yet done
  if (!document.getElementById('asset-grid').hasChildNodes()) {
    buildPanels(Object.keys(d.series));
  }

  // Charts
  Object.entries(d.series).forEach(([asset, s]) => {
    const color = ASSET_COLORS[asset] || '#555';

    // Price chart
    makeOrUpdate(`c-price-${asset}`, 'line', s.labels, [
      {
        label: 'Kalshi YES ask',
        data: s.kalshi,
        borderColor: color,
        backgroundColor: color + '18',
        fill: true,
        tension: 0.4,
        pointRadius: 0,
        borderWidth: 1.5,
      },
      {
        label: 'Poly UP ask',
        data: s.poly,
        borderColor: '#1a1916',
        backgroundColor: 'rgba(0,0,0,0.04)',
        fill: false,
        tension: 0.4,
        pointRadius: 0,
        borderWidth: 1.5,
        borderDash: [4, 3],
      }
    ]);

    // Spread chart
    const spreadData = s.spread;
    const spreadColor = spreadData.slice(-1)[0] >= d.alert_thresh ? '#8b2020' : '#92600a';
    makeOrUpdate(`c-spread-${asset}`, 'line', s.labels, [
      {
        label: 'Spread %',
        data: spreadData,
        borderColor: spreadColor,
        backgroundColor: spreadColor + '15',
        fill: true,
        tension: 0.4,
        pointRadius: 0,
        borderWidth: 1.5,
      }
    ]);

    // Latest price chips
    const lat = d.latest[asset] || {};
    const kEl = document.getElementById(`p-kalshi-${asset}`);
    const pEl = document.getElementById(`p-poly-${asset}`);
    const bEl = document.getElementById(`p-badge-${asset}`);
    if (kEl) kEl.textContent = lat.kalshi_ask !== undefined ? lat.kalshi_ask.toFixed(3) : '—';
    if (pEl) pEl.textContent = lat.poly_ask   !== undefined ? lat.poly_ask.toFixed(3)   : '—';
    if (bEl) {
      const sp = lat.spread || 0;
      bEl.textContent = (sp >= 0 ? '+' : '') + sp.toFixed(1) + '%';
      bEl.className = 'spread-badge ' + (sp >= d.alert_thresh ? 'hot' : sp >= d.alert_thresh / 2 ? 'warm' : 'cool');
    }
  });

  // Spread comparison table
  const tbody = document.getElementById('spread-tbody');
  tbody.innerHTML = Object.entries(d.latest).map(([asset, lat]) => {
    const sp  = lat.spread || 0;
    const pct = Math.min(100, Math.abs(sp) / d.alert_thresh * 100);
    const col = sp >= d.alert_thresh ? 'var(--red)' : sp >= d.alert_thresh/2 ? 'var(--amber)' : 'var(--muted)';
    return `<tr>
      <td style="font-family:'Instrument Serif',serif;font-size:16px;letter-spacing:-0.5px">
        <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${ASSET_COLORS[asset]};margin-right:8px;vertical-align:middle"></span>
        ${asset}
      </td>
      <td>${lat.kalshi_ask !== undefined ? lat.kalshi_ask.toFixed(3) : '—'}</td>
      <td>${lat.poly_ask   !== undefined ? lat.poly_ask.toFixed(3)   : '—'}</td>
      <td style="color:${col};font-weight:500">${sp >= 0 ? '+' : ''}${sp.toFixed(1)}%</td>
      <td class="spread-bar-cell">
        <div class="sbar-track"><div class="sbar-fill" style="width:${pct}%;background:${col}"></div></div>
      </td>
    </tr>`;
  }).join('');

  // Alerts
  const alertList = document.getElementById('alert-list');
  if (d.alerts && d.alerts.length) {
    alertList.innerHTML = d.alerts.map((a, i) => `
      <div class="alert-item" style="animation-delay:${i*0.05}s">
        <span class="alert-icon">▲</span>
        <span class="alert-asset">${a.asset}</span>
        <span class="alert-spread">+${a.sprd}% spread detected</span>
        <span class="alert-time">${a.ts}</span>
      </div>`).join('');
  } else {
    alertList.innerHTML = '<div class="no-alerts">No spread alerts · Threshold ' + d.alert_thresh + '%</div>';
  }
}

async function refresh() {
  try {
    const r = await fetch('/api/data');
    render(await r.json());
  } catch(e) {
    console.warn('Refresh failed:', e);
  }
}

refresh();
setInterval(refresh, 10000);
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass

    def do_GET(self):
        if self.path == "/api/data":
            data = json.dumps(get_data()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
        elif self.path in ("/", "/monitor"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


def main():
    print(f"\n  Market Monitor — Kalshi × Polymarket")
    print(f"  =====================================")
    print(f"  Database : {os.path.abspath(DB_PATH)}")
    print(f"\n  Open     : http://localhost:{PORT}")
    print(f"\n  Refreshes every 10 seconds.")
    print(f"  Ctrl-C to stop.\n")
    server = HTTPServer(("localhost", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Monitor offline.")


if __name__ == "__main__":
    main()
