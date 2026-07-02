# Trading Bot - Binance USDT-M Futures Testnet

This is a CLI tool that places Market, Limit, and Stop-Limit orders on Binance's USDT-M
Futures Testnet. I built it for the Primetrade.ai Python Developer application task.

I went with direct REST calls and signed everything by hand (HMAC-SHA256) instead of using
the `python-binance` library. The task allows either, but I wanted to actually understand how
Binance's signing works rather than just calling a wrapper for it.

There's also a small web dashboard (`app.py`) I added on the side. It's not the main
deliverable though, the CLI is what actually gets graded, so that's what I focused on.

## Project structure

```
trading_bot/
├── bot/
│   ├── __init__.py
│   ├── client.py           # talks to Binance: signing, retries, all the endpoint calls
│   ├── orders.py           # builds order params and places the order
│   ├── validators.py       # input validation, no network dependency at all
│   ├── logging_config.py   # one shared logger, file + console
│   └── exceptions.py       # custom exceptions so errors are easy to catch and handle
├── cli.py                  # argument parsing, calls into bot/. no logic of its own
├── app.py                  # optional dashboard, bonus only
├── tests/
│   └── test_validators.py
├── logs/                   # created automatically when you run the bot
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

The idea behind the layering: `cli.py` doesn't know how to sign a request or call `requests`
directly. `client.py` doesn't validate anything, it just trusts what it's given. `validators.py`
doesn't import `requests` at all, so it can be tested without touching the network.

## Setup

### 1. Get testnet API keys

1. Go to https://testnet.binancefuture.com
2. Log in (it uses GitHub login)
3. Go to API Management and create an API key
4. Copy the API Key and Secret Key somewhere safe

### 2. Install

```bash
python3 -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Add your credentials

```bash
cp .env.example .env
```

Then open `.env` and paste in your keys:

```
BINANCE_API_KEY=your_testnet_api_key_here
BINANCE_API_SECRET=your_testnet_api_secret_here
```

`.env` is gitignored so it won't get committed by accident.

## Usage

### CLI (this is the actual deliverable)

```bash
# Market order
python cli.py --symbol BTCUSDT --side BUY --type MARKET --quantity 0.01

# Limit order
python cli.py --symbol BTCUSDT --side SELL --type LIMIT --quantity 0.01 --price 60000

# Stop-Limit order (the bonus order type)
python cli.py --symbol BTCUSDT --side BUY --type STOP_LIMIT --quantity 0.01 --price 61000 --stop-price 60900
```

What it prints looks like this:

```
-- Order Request ---------------------------
  Symbol      : BTCUSDT
  Side        : BUY
  Type        : MARKET
  Quantity    : 0.01

-- Order Response --------------------------
  Order ID    : 13488xxxxx
  Status      : NEW
  Executed Qty: 0.01
  Avg Price   : 60123.40

Order placed: MARKET BUY for BTCUSDT (orderId=13488xxxxx)
```

### Dashboard (optional, not the main thing)

```bash
python app.py
```

Then open http://localhost:5050. It shows live prices, account balance, an order form, open
orders, and an activity log. Built it mostly because I wanted to see the account state live
while testing, but the CLI above is what actually matters for grading.

## Running the tests

```bash
python -m unittest discover tests -v
```

or if you prefer pytest:

```bash
python -m pytest tests/ -v
```

15 tests, all just checking `validators.py`. No network needed since that module doesn't touch
the internet at all.

## A few assumptions and decisions I made

- **Used Decimal instead of float** for quantity and price. Floats round in weird ways
  sometimes (0.1 + 0.2 isn't quite 0.3), and for anything involving money I didn't want to
  risk that. Converted to string before sending to the API rather than float, to avoid any
  floating point noise creeping into the request.
- **Signed requests manually** rather than using python-binance. Wanted the HMAC signing logic
  to actually be visible in the code instead of hidden behind a library call.
- **recvWindow set to 5000ms** on every signed request. This handles the case where your
  computer's clock is a bit off from Binance's server clock, which otherwise causes a
  confusing "invalid timestamp" error that has nothing to do with your actual request.
- **Retries only happen on 500/502/503/504 errors**, meaning actual server problems, not on
  a rejected order. If Binance says "insufficient balance" or "invalid price," retrying won't
  fix that, it'll just burn through the rate limit for no reason.
- **Stop-Limit is built on Binance's STOP order type**, which needs both a trigger price and a
  limit price. Picked this as the bonus feature since it's a natural extension of Market/Limit
  and easy to test with one command.
- **GTC (good till cancelled)** for time in force on Limit and Stop-Limit orders. The task
  doesn't specify one so I went with the common default.
- **Only 5 symbols supported** (BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, XRPUSDT). Kept the symbol
  list fixed rather than open-ended to keep validation and the dashboard's price feed simple.

## Troubleshooting

A few error codes that are worth knowing about if you hit them while testing:

| Code          | What it means                                                | What to do                                                                                                                           |
| ------------- | ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| -1021         | Timestamp outside recvWindow                                 | Usually your system clock is off. The bot already corrects for small drift automatically, but check your clock if it keeps happening |
| -2019         | Margin is insufficient                                       | Lower the quantity, or add more testnet funds through the faucet on the testnet site                                                 |
| -4164         | Order notional too small                                     | Testnet has a minimum order value (roughly 100 USDT worth). Increase quantity or pick a symbol where that's easier to hit            |
| -1013 / -4014 | Price or quantity doesn't match the symbol's precision rules | Round to the tick size Binance expects.`/fapi/v1/exchangeInfo` lists the exact filter per symbol if you need to check              |

These are documented Binance error codes rather than ones I necessarily ran into myself, just
listing them here since they're the ones people most commonly hit with this kind of setup.

## About the required log files

The task asks for log files from a real Market order and a real Limit order placed on
testnet. To get those, fill in your `.env` with your own keys and run:

```bash
python cli.py --symbol BTCUSDT --side BUY --type MARKET --quantity 0.01
python cli.py --symbol BTCUSDT --side SELL --type LIMIT --quantity 0.01 --price 60000
```

After that, `logs/trading_bot.log` will have real entries for both, which is what gets
submitted alongside the code.
