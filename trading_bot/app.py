#!/usr/bin/env python3
"""Flask REST API + self-contained web dashboard for the trading bot.

Run with:  python app.py
Then open: http://localhost:5050

The dashboard is a single embedded HTML/CSS/JS page (no build step,
no separate frontend project) served by the '/' route below. All
Binance calls happen server-side -- the browser only ever talks to
this Flask app, so API keys never reach the client.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template_string, request

from Binance_trading_bot.trading_bot.bot.client import BinanceClient
from Binance_trading_bot.trading_bot.bot.exceptions import ConfigurationError, OrderExecutionError, TradingBotError, ValidationError
from Binance_trading_bot.trading_bot.bot.logging_config import setup_logger
from Binance_trading_bot.trading_bot.bot.orders import place_order
from Binance_trading_bot.trading_bot.bot.validators import VALID_SYMBOLS, validate_order_inputs

load_dotenv()
logger = setup_logger("trading_bot.api")

app = Flask(__name__)

_client: BinanceClient | None = None


def get_client() -> BinanceClient:
    """Lazily create a single shared BinanceClient. Raises
    ConfigurationError (caught by every route below) if credentials
    are missing, instead of crashing the whole server at import time."""
    global _client
    if _client is None:
        api_key = os.getenv("BINANCE_API_KEY")
        api_secret = os.getenv("BINANCE_API_SECRET")
        _client = BinanceClient(api_key, api_secret)
    return _client


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.route("/api/health", methods=["GET"])
def health():
    try:
        client = get_client()
        client.ping()
        return jsonify({"status": "ok", "testnet": True, "time_offset_ms": client.time_offset})
    except ConfigurationError as e:
        return jsonify({"status": "unconfigured", "error": str(e)}), 200
    except TradingBotError as e:
        return jsonify({"status": "error", "error": str(e)}), 200


@app.route("/api/prices", methods=["GET"])
def prices():
    """Single bulk call to Binance's 24hr ticker (unsigned, public)
    covers price + % change for every symbol in one request, rather
    than one request per watchlist symbol."""
    try:
        client = get_client()
        all_stats = client.get_24hr_stats()
        by_symbol = {row["symbol"]: row for row in all_stats}
        result = []
        for sym in VALID_SYMBOLS:
            row = by_symbol.get(sym)
            if not row:
                continue
            result.append({
                "symbol": sym,
                "price": float(row["lastPrice"]),
                "change_pct": float(row["priceChangePercent"]),
            })
        return jsonify({"prices": result})
    except TradingBotError as e:
        logger.error("Failed to fetch prices: %s", e)
        return jsonify({"error": str(e)}), 502


@app.route("/api/sparkline/<symbol>", methods=["GET"])
def sparkline(symbol):
    try:
        client = get_client()
        klines = client.get_klines(symbol.upper(), interval="5m", limit=24)
        closes = [float(k[4]) for k in klines]
        return jsonify({"symbol": symbol.upper(), "closes": closes})
    except TradingBotError as e:
        return jsonify({"error": str(e)}), 502


@app.route("/api/account", methods=["GET"])
def account():
    try:
        client = get_client()
        data = client.get_account()
        return jsonify({
            "balance": float(data.get("totalWalletBalance", 0)),
            "available": float(data.get("availableBalance", 0)),
            "unrealized_pnl": float(data.get("totalUnrealizedProfit", 0)),
            "margin_balance": float(data.get("totalMarginBalance", 0)),
        })
    except ConfigurationError as e:
        return jsonify({"error": str(e), "code": "unconfigured"}), 400
    except TradingBotError as e:
        logger.error("Failed to fetch account: %s", e)
        return jsonify({"error": str(e)}), 502


@app.route("/api/open-orders", methods=["GET"])
def open_orders():
    try:
        client = get_client()
        orders = client.get_open_orders()
        return jsonify({"orders": orders})
    except ConfigurationError as e:
        return jsonify({"error": str(e), "code": "unconfigured"}), 400
    except TradingBotError as e:
        logger.error("Failed to fetch open orders: %s", e)
        return jsonify({"error": str(e)}), 502


@app.route("/api/order", methods=["POST"])
def create_order():
    body = request.get_json(silent=True) or {}

    try:
        validated = validate_order_inputs(
            symbol=body.get("symbol"),
            side=body.get("side"),
            order_type=body.get("order_type"),
            quantity=body.get("quantity"),
            price=body.get("price"),
            stop_price=body.get("stop_price"),
        )
    except ValidationError as e:
        logger.error("Validation failed: %s", e)
        return jsonify({"error": str(e), "stage": "validation"}), 400

    try:
        client = get_client()
        response = place_order(client, validated)
    except ConfigurationError as e:
        return jsonify({"error": str(e), "stage": "configuration"}), 400
    except OrderExecutionError as e:
        logger.error("Order failed: %s", e)
        return jsonify({"error": str(e), "stage": "execution"}), 502
    except TradingBotError as e:
        logger.error("Unexpected trading bot error: %s", e)
        return jsonify({"error": str(e), "stage": "unknown"}), 500

    return jsonify({
        "order_id": response.get("orderId"),
        "status": response.get("status"),
        "executed_qty": response.get("executedQty"),
        "avg_price": response.get("avgPrice"),
        "symbol": validated.symbol,
        "side": validated.side,
        "order_type": validated.order_type,
        "quantity": validated.quantity,
    })


@app.route("/api/order", methods=["DELETE"])
def cancel_order():
    body = request.get_json(silent=True) or {}
    symbol = body.get("symbol")
    order_id = body.get("order_id")
    if not symbol or not order_id:
        return jsonify({"error": "symbol and order_id are required"}), 400

    try:
        client = get_client()
        response = client.cancel_order(symbol.upper(), int(order_id))
        return jsonify({"order_id": response.get("orderId"), "status": response.get("status")})
    except ConfigurationError as e:
        return jsonify({"error": str(e)}), 400
    except TradingBotError as e:
        logger.error("Cancel failed: %s", e)
        return jsonify({"error": str(e)}), 502


# ---------------------------------------------------------------------------
# Dashboard UI (single-page, embedded -- no separate frontend build)
# ---------------------------------------------------------------------------

@app.route("/", methods=["GET"])
def index():
    return render_template_string(DASHBOARD_HTML, symbols=VALID_SYMBOLS)


DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Trading Bot - Binance Futures Testnet</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root{
    --bg:#0a0a0a; --panel:#111214; --border:rgba(255,255,255,0.08);
    --text:#f0f0f0; --dim:#888; --dimmer:#555;
    --green:#00c896; --red:#ff5c5c; --amber:#ffb020; --blue:#4d9fff;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--bg);color:var(--text);font-family:'JetBrains Mono',monospace;min-height:100vh}
  input,select{background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);
    border-radius:8px;padding:10px 12px;color:var(--text);font-family:inherit;font-size:13px;width:100%}
  input:focus,select:focus{outline:none;border-color:rgba(255,255,255,0.3)}
  input[type=number]::-webkit-inner-spin-button{opacity:0.3}
  select{cursor:pointer;appearance:none}
  ::-webkit-scrollbar{width:6px;height:6px}
  ::-webkit-scrollbar-track{background:transparent}
  ::-webkit-scrollbar-thumb{background:#2a2a2a;border-radius:3px}
  .lbl{display:block;font-size:9px;font-weight:600;color:#666;letter-spacing:1.5px;
    text-transform:uppercase;margin-bottom:6px}
  .card{background:rgba(255,255,255,0.02);border:1px solid var(--border);border-radius:14px;padding:20px}
  .section-title{font-size:10px;color:#555;letter-spacing:2px;margin-bottom:14px;text-transform:uppercase}
  .price-val{font-size:17px;font-weight:700;color:#f0f0f0;line-height:1}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:0.35}}
  @keyframes fadeIn{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:translateY(0)}}
  @keyframes flashGreen{0%{background:rgba(0,200,150,0.25)}100%{background:transparent}}
  @keyframes flashRed{0%{background:rgba(255,92,92,0.25)}100%{background:transparent}}
  .fade-in{animation:fadeIn 0.3s ease forwards}
  .flash-up{animation:flashGreen 0.6s ease}
  .flash-down{animation:flashRed 0.6s ease}
  .dot-live{width:7px;height:7px;border-radius:50%;background:var(--green);box-shadow:0 0 8px var(--green);
    display:inline-block;animation:pulse 2s infinite}
  .dot-off{width:7px;height:7px;border-radius:50%;background:var(--dimmer);display:inline-block}
  .btn{cursor:pointer;border:none;border-radius:8px;font-family:inherit;font-weight:700;
    letter-spacing:0.5px;transition:filter 0.15s,transform 0.1s}
  .btn:hover{filter:brightness(1.15)}
  .btn:active{transform:scale(0.98)}
  .btn:disabled{opacity:0.4;cursor:not-allowed}
  .toggle{background:rgba(255,255,255,0.04);border:1px solid var(--border);color:#888;
    padding:9px 0;font-size:12px;font-weight:600;border-radius:8px;cursor:pointer;transition:all 0.15s}
  .toggle.active-buy{background:rgba(0,200,150,0.15);border-color:var(--green);color:var(--green)}
  .toggle.active-sell{background:rgba(255,92,92,0.15);border-color:var(--red);color:var(--red)}
  .toggle.active-type{background:rgba(77,159,255,0.15);border-color:var(--blue);color:var(--blue)}
  .row-2{display:grid;grid-template-columns:1fr 1fr;gap:8px}
  .row-3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px}
  .log-entry{font-size:11px;padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.04);
    display:flex;gap:10px;align-items:baseline}
  .log-time{color:#555;flex-shrink:0}
  .log-ok{color:var(--green)}
  .log-err{color:var(--red)}
  .log-info{color:#888}
  .badge{font-size:9px;padding:2px 7px;border-radius:20px;font-weight:700;letter-spacing:0.5px}
  .badge-testnet{background:rgba(255,176,32,0.15);color:var(--amber);border:1px solid rgba(255,176,32,0.3)}
  .tooltip{position:relative;cursor:help}
  .tooltip .tip{visibility:hidden;opacity:0;position:absolute;bottom:130%;left:50%;transform:translateX(-50%);
    background:#1c1c1e;color:#ddd;font-size:10px;padding:6px 9px;border-radius:6px;white-space:nowrap;
    border:1px solid var(--border);transition:opacity 0.15s;z-index:10}
  .tooltip:hover .tip{visibility:visible;opacity:1}
  @media(max-width:800px){.main-grid{grid-template-columns:1fr !important}.price-grid{grid-template-columns:repeat(2,1fr) !important}}
</style>
</head>
<body>

<!-- TOP BAR -->
<div style="display:flex;align-items:center;justify-content:space-between;padding:16px 24px;border-bottom:1px solid var(--border)">
  <div style="display:flex;align-items:center;gap:12px">
    <div style="width:34px;height:34px;border-radius:9px;background:linear-gradient(135deg,#00c896,#006650);
      display:flex;align-items:center;justify-content:center;font-size:16px">⚡</div>
    <div>
      <div style="font-size:14px;font-weight:700;letter-spacing:1px">TRADING BOT</div>
      <div style="font-size:9px;color:#555;letter-spacing:2px">BINANCE FUTURES TESTNET</div>
    </div>
    <span class="badge badge-testnet" style="margin-left:8px">TESTNET · NO REAL FUNDS</span>
  </div>
  <div style="display:flex;align-items:center;gap:8px">
    <span id="status-dot" class="dot-off"></span>
    <span id="status-txt" style="font-size:10px;color:#555;letter-spacing:1px">CONNECTING…</span>
  </div>
</div>

<div style="max-width:1200px;margin:0 auto;padding:24px 22px">

  <!-- PRICE CARDS -->
  <div id="price-grid" class="price-grid" style="display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin-bottom:22px"></div>

  <div class="main-grid" style="display:grid;grid-template-columns:1fr 1.3fr;gap:18px">

    <!-- ORDER FORM -->
    <div class="card fade-in">
      <div class="section-title">Place Order</div>

      <div style="margin-bottom:14px">
        <span class="lbl">Symbol</span>
        <select id="in-symbol">
          {% for s in symbols %}<option value="{{ s }}">{{ s }}</option>{% endfor %}
        </select>
      </div>

      <div style="margin-bottom:14px">
        <span class="lbl">Side</span>
        <div class="row-2">
          <button class="toggle active-buy" id="btn-buy" onclick="setSide('BUY')">▲ BUY</button>
          <button class="toggle" id="btn-sell" onclick="setSide('SELL')">▼ SELL</button>
        </div>
      </div>

      <div style="margin-bottom:14px">
        <span class="lbl">Order Type</span>
        <div class="row-3">
          <button class="toggle active-type" id="btn-market" onclick="setType('MARKET')">MARKET</button>
          <button class="toggle" id="btn-limit" onclick="setType('LIMIT')">LIMIT</button>
          <button class="toggle" id="btn-stoplimit" onclick="setType('STOP_LIMIT')">STOP-LIMIT</button>
        </div>
      </div>

      <div style="margin-bottom:14px">
        <span class="lbl">Quantity</span>
        <input type="number" id="in-quantity" step="0.001" placeholder="e.g. 0.01">
      </div>

      <div id="price-field" style="margin-bottom:14px;display:none">
        <span class="lbl tooltip">Price<span class="tip">Limit price for the order</span></span>
        <input type="number" id="in-price" step="0.01" placeholder="e.g. 60000">
      </div>

      <div id="stop-price-field" style="margin-bottom:14px;display:none">
        <span class="lbl tooltip">Stop Price<span class="tip">Trigger price, order activates once market reaches this</span></span>
        <input type="number" id="in-stop-price" step="0.01" placeholder="e.g. 60900">
      </div>

      <button class="btn" id="btn-submit" onclick="submitOrder()"
        style="width:100%;padding:13px;background:var(--green);color:#00251a;font-size:13px;margin-top:4px">
        ▲ PLACE BUY MARKET ORDER
      </button>

      <div id="order-feedback" style="margin-top:12px;font-size:11px"></div>
    </div>

    <!-- ACCOUNT + ORDERS + LOG -->
    <div style="display:flex;flex-direction:column;gap:18px">

      <div class="card fade-in">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
          <div class="section-title" style="margin:0">Account - Testnet</div>
          <span style="font-size:10px;color:#555;cursor:pointer" onclick="refreshAccount()">↻ refresh</span>
        </div>
        <div class="row-2" style="gap:12px">
          <div>
            <span class="lbl">Wallet Balance</span>
            <div class="price-val" id="acc-balance">--</div>
          </div>
          <div>
            <span class="lbl">Available</span>
            <div class="price-val" id="acc-available">--</div>
          </div>
          <div>
            <span class="lbl tooltip">Unrealized PnL<span class="tip">Profit/loss on open positions, not yet closed</span></span>
            <div class="price-val" id="acc-pnl">--</div>
          </div>
          <div>
            <span class="lbl">Margin Balance</span>
            <div class="price-val" id="acc-margin">--</div>
          </div>
        </div>
      </div>

      <div class="card fade-in" style="flex:1">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
          <div class="section-title" style="margin:0">Open Orders</div>
          <span style="font-size:10px;color:#555;cursor:pointer" onclick="refreshOrders()">↻ refresh</span>
        </div>
        <div id="open-orders" style="font-size:11px;color:#555">no open orders</div>
      </div>

      <div class="card fade-in" style="flex:1;display:flex;flex-direction:column">
        <div class="section-title">Activity Log</div>
        <div id="activity-log" style="flex:1;overflow-y:auto;max-height:220px"></div>
      </div>

    </div>
  </div>
</div>

<script>
const SYMBOLS = {{ symbols|tojson }};
let side = 'BUY', orderType = 'MARKET';
let lastPrices = {};

function log(msg, level='info'){
  const el = document.getElementById('activity-log');
  const time = new Date().toLocaleTimeString();
  const cls = level === 'ok' ? 'log-ok' : level === 'err' ? 'log-err' : 'log-info';
  const div = document.createElement('div');
  div.className = 'log-entry fade-in';
  div.innerHTML = `<span class="log-time">${time}</span><span class="${cls}">${msg}</span>`;
  el.prepend(div);
  while (el.children.length > 40) el.removeChild(el.lastChild);
}

function setSide(s){
  side = s;
  document.getElementById('btn-buy').className = 'toggle' + (s==='BUY' ? ' active-buy' : '');
  document.getElementById('btn-sell').className = 'toggle' + (s==='SELL' ? ' active-sell' : '');
  updateSubmitButton();
}

function setType(t){
  orderType = t;
  document.getElementById('btn-market').className = 'toggle' + (t==='MARKET' ? ' active-type' : '');
  document.getElementById('btn-limit').className = 'toggle' + (t==='LIMIT' ? ' active-type' : '');
  document.getElementById('btn-stoplimit').className = 'toggle' + (t==='STOP_LIMIT' ? ' active-type' : '');
  document.getElementById('price-field').style.display = (t==='LIMIT'||t==='STOP_LIMIT') ? 'block' : 'none';
  document.getElementById('stop-price-field').style.display = (t==='STOP_LIMIT') ? 'block' : 'none';
  updateSubmitButton();
}

function updateSubmitButton(){
  const btn = document.getElementById('btn-submit');
  const arrow = side === 'BUY' ? '▲' : '▼';
  const typeLabel = orderType.replace('_','-');
  btn.textContent = `${arrow} PLACE ${side} ${typeLabel} ORDER`;
  btn.style.background = side === 'BUY' ? 'var(--green)' : 'var(--red)';
  btn.style.color = side === 'BUY' ? '#00251a' : '#2a0000';
}

function sparklinePath(closes, w=100, h=28){
  if (!closes || closes.length < 2) return '';
  const min = Math.min(...closes), max = Math.max(...closes);
  const range = (max - min) || 1;
  const step = w / (closes.length - 1);
  return closes.map((c,i) => `${i*step},${h - ((c-min)/range)*h}`).join(' ');
}

async function refreshPrices(){
  try{
    const res = await fetch('/api/prices');
    const data = await res.json();
    if (data.error){ log('Price feed error: ' + data.error, 'err'); return; }
    const grid = document.getElementById('price-grid');
    grid.innerHTML = '';
    data.prices.forEach(p => {
      const prev = lastPrices[p.symbol];
      const flash = prev !== undefined ? (p.price > prev ? 'flash-up' : p.price < prev ? 'flash-down' : '') : '';
      lastPrices[p.symbol] = p.price;
      const up = p.change_pct >= 0;
      const div = document.createElement('div');
      div.className = 'card ' + flash;
      div.style.cursor = 'pointer';
      div.onclick = () => { document.getElementById('in-symbol').value = p.symbol; loadSparkline(p.symbol); };
      div.innerHTML = `
        <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px">
          <span class="dot-live" style="animation:none;box-shadow:none;width:6px;height:6px;background:${up?'var(--green)':'var(--red)'}"></span>
          <span style="font-size:10px;color:#888;letter-spacing:1px">${p.symbol}</span>
        </div>
        <div class="price-val">$${p.price.toLocaleString(undefined,{maximumFractionDigits:4})}</div>
        <div style="font-size:10px;color:${up?'var(--green)':'var(--red)'};margin-top:2px">${up?'▲':'▼'} ${Math.abs(p.change_pct).toFixed(2)}%</div>
        <svg width="100%" height="24" viewBox="0 0 100 28" style="margin-top:6px;overflow:visible">
          <polyline points="${sparklineCache[p.symbol]||''}" fill="none" stroke="${up?'#00c896':'#ff5c5c'}" stroke-width="1.5"/>
        </svg>`;
      grid.appendChild(div);
    });
  } catch(e){ log('Could not reach server for price feed', 'err'); }
}

const sparklineCache = {};
async function loadSparkline(symbol){
  try{
    const res = await fetch('/api/sparkline/' + symbol);
    const data = await res.json();
    if (data.closes) sparklineCache[symbol] = sparklinePath(data.closes);
  } catch(e){}
}

async function refreshAccount(){
  try{
    const res = await fetch('/api/account');
    const data = await res.json();
    if (data.error){
      document.getElementById('acc-balance').textContent = 'not configured';
      return;
    }
    document.getElementById('acc-balance').textContent = '$' + data.balance.toLocaleString(undefined,{maximumFractionDigits:2});
    document.getElementById('acc-available').textContent = '$' + data.available.toLocaleString(undefined,{maximumFractionDigits:2});
    const pnlEl = document.getElementById('acc-pnl');
    pnlEl.textContent = (data.unrealized_pnl>=0?'+':'') + '$' + data.unrealized_pnl.toLocaleString(undefined,{maximumFractionDigits:2});
    pnlEl.style.color = data.unrealized_pnl >= 0 ? 'var(--green)' : 'var(--red)';
    document.getElementById('acc-margin').textContent = '$' + data.margin_balance.toLocaleString(undefined,{maximumFractionDigits:2});
  } catch(e){ log('Could not fetch account data', 'err'); }
}

async function refreshOrders(){
  try{
    const res = await fetch('/api/open-orders');
    const data = await res.json();
    const el = document.getElementById('open-orders');
    if (data.error){ el.innerHTML = 'not configured'; return; }
    if (!data.orders || data.orders.length === 0){ el.innerHTML = 'no open orders'; return; }
    el.innerHTML = data.orders.map(o => `
      <div style="display:flex;justify-content:space-between;align-items:center;padding:7px 0;border-bottom:1px solid rgba(255,255,255,0.04)">
        <span>${o.side} ${o.type} <b>${o.symbol}</b> qty=${o.origQty} ${o.price>0?'@'+o.price:''}</span>
        <span style="color:#ff5c5c;cursor:pointer" onclick="cancelOrder('${o.symbol}',${o.orderId})">✕ cancel</span>
      </div>`).join('');
  } catch(e){ log('Could not fetch open orders', 'err'); }
}

async function cancelOrder(symbol, orderId){
  try{
    const res = await fetch('/api/order', {method:'DELETE', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({symbol, order_id: orderId})});
    const data = await res.json();
    if (data.error){ log(`Cancel failed: ${data.error}`, 'err'); return; }
    log(`Order ${orderId} cancelled`, 'ok');
    refreshOrders();
  } catch(e){ log('Cancel request failed', 'err'); }
}

async function submitOrder(){
  const btn = document.getElementById('btn-submit');
  const symbol = document.getElementById('in-symbol').value;
  const quantity = document.getElementById('in-quantity').value;
  const price = document.getElementById('in-price').value;
  const stopPrice = document.getElementById('in-stop-price').value;
  const feedback = document.getElementById('order-feedback');

  btn.disabled = true;
  feedback.innerHTML = '';

  try{
    const res = await fetch('/api/order', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        symbol, side, order_type: orderType, quantity,
        price: (orderType==='LIMIT'||orderType==='STOP_LIMIT') ? price : null,
        stop_price: orderType==='STOP_LIMIT' ? stopPrice : null,
      })
    });
    const data = await res.json();

    if (!res.ok){
      feedback.innerHTML = `<div style="color:var(--red)">✗ ${data.error}</div>`;
      log(`Order failed: ${data.error}`, 'err');
    } else {
      feedback.innerHTML = `<div style="color:var(--green)">✓ Order placed! ID: ${data.order_id} · Status: ${data.status} · Qty: ${data.executed_qty||0}</div>`;
      log(`${data.side} ${data.order_type} ${data.symbol} qty=${data.quantity} → ${data.status}`, 'ok');
      refreshAccount();
      refreshOrders();
    }
  } catch(e){
    feedback.innerHTML = `<div style="color:var(--red)">✗ Request failed, is the server running?</div>`;
    log('Order request failed to reach server', 'err');
  } finally {
    btn.disabled = false;
  }
}

async function checkHealth(){
  try{
    const res = await fetch('/api/health');
    const data = await res.json();
    const dot = document.getElementById('status-dot');
    const txt = document.getElementById('status-txt');
    if (data.status === 'ok'){
      dot.className = 'dot-live'; txt.textContent = 'CONNECTED'; txt.style.color = 'var(--green)';
    } else if (data.status === 'unconfigured'){
      dot.className = 'dot-off'; txt.textContent = 'API KEYS NOT SET'; txt.style.color = 'var(--amber)';
      log('BINANCE_API_KEY / BINANCE_API_SECRET not set in .env, trading disabled but price feed still live', 'err');
    } else {
      dot.className = 'dot-off'; txt.textContent = 'CONNECTION ERROR'; txt.style.color = 'var(--red)';
    }
  } catch(e){
    document.getElementById('status-txt').textContent = 'SERVER UNREACHABLE';
  }
}

// init
setType('MARKET'); setSide('BUY');
log('Dashboard loaded, connecting to local API', 'info');
checkHealth();
refreshPrices();
refreshAccount();
refreshOrders();
SYMBOLS.forEach(loadSparkline);
setInterval(refreshPrices, 5000);
setInterval(checkHealth, 15000);
setInterval(refreshAccount, 20000);
setInterval(refreshOrders, 20000);
setInterval(() => SYMBOLS.forEach(loadSparkline), 30000);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    logger.info("Starting Flask dashboard on http://localhost:5050")
    app.run(host="0.0.0.0", port=5050, debug=False)
