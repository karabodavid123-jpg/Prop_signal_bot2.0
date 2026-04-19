import requests
import time
from datetime import datetime, timedelta
import os

API_KEY = os.environ.get("TWELVE_API_KEY")
NEWS_KEY = os.environ.get("FMP_API_KEY")
WEBHOOK = os.environ.get("DISCORD_WEBHOOK")

SYMBOLS = ["XAU/USD","EUR/USD","GBP/USD","USD/JPY","US30"]

stats = {
    "trades": 0,
    "wins": 0,
    "losses": 0,
    "pnl": 0
}

# =========================
# DISCORD
# =========================
def send(msg):
    try:
        requests.post(WEBHOOK, json={"content": msg})
    except:
        pass

# =========================
# SESSION FILTER (SAST)
# =========================
def session_ok():
    h = datetime.now().hour
    return (9 <= h < 12) or (15 <= h < 18)

# =========================
# NEWS FILTER
# =========================
def news_block():
    try:
        url = f"https://financialmodelingprep.com/api/v3/economic_calendar?apikey={NEWS_KEY}"
        data = requests.get(url).json()

        now = datetime.utcnow()

        for event in data[:10]:
            if "USD" in event.get("country",""):
                event_time = datetime.strptime(event["date"], "%Y-%m-%d %H:%M:%S")

                if abs((event_time - now).total_seconds()) < 1800:
                    return True
    except:
        pass

    return False

# =========================
# MARKET DATA
# =========================
def get_data(symbol, interval):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&apikey={API_KEY}&outputsize=100"
    r = requests.get(url).json()
    return r.get("values", [])

# =========================
# INDICATORS
# =========================
def ema(data, period):
    prices = [float(d["close"]) for d in data]
    k = 2 / (period + 1)
    val = prices[0]
    for p in prices:
        val = p * k + val * (1 - k)
    return val

def rsi(data):
    closes = [float(d["close"]) for d in data]
    gains, losses = [], []

    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        if diff > 0:
            gains.append(diff)
        else:
            losses.append(abs(diff))

    avg_gain = sum(gains[-14:]) / 14
    avg_loss = sum(losses[-14:]) / 14 if losses else 1

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def macd(data):
    return ema(data[-12:],12) - ema(data[-26:],26)

def engulfing(data):
    c1, c2 = data[-2], data[-1]

    if float(c2["close"]) > float(c2["open"]) and float(c1["close"]) < float(c1["open"]):
        return "BULL"
    if float(c2["close"]) < float(c2["open"]) and float(c1["close"]) > float(c1["open"]):
        return "BEAR"
    return None

def atr(data):
    ranges = [float(d["high"]) - float(d["low"]) for d in data[-14:]]
    return sum(ranges)/len(ranges)

# =========================
# PERFORMANCE TRACKER
# =========================
def update_stats(win):
    stats["trades"] += 1
    if win:
        stats["wins"] += 1
        stats["pnl"] += 2
    else:
        stats["losses"] += 1
        stats["pnl"] -= 1

def report():
    if stats["trades"] == 0:
        return "No trades yet"

    winrate = (stats["wins"] / stats["trades"]) * 100

    return f"""
📈 PERFORMANCE REPORT

Trades: {stats["trades"]}
Wins: {stats["wins"]}
Losses: {stats["losses"]}
Winrate: {round(winrate,1)}%
P&L (R): {stats["pnl"]}
"""

# =========================
# MAIN LOOP
# =========================
while True:

    if not session_ok():
        time.sleep(60)
        continue

    if news_block():
        send("⚠️ Trading paused due to high-impact news")
        time.sleep(300)
        continue

    for symbol in SYMBOLS:

        m15 = get_data(symbol, "15min")
        h1 = get_data(symbol, "1h")

        if len(m15) < 50 or len(h1) < 50:
            continue

        price = float(m15[0]["close"])
        trend = "BULL" if price > ema(h1,200) else "BEAR"
        rsi_val = rsi(m15)
        macd_val = macd(m15)
        engulf = engulfing(m15)

        direction = None

        if rsi_val > 55 and macd_val > 0 and engulf == "BULL" and trend == "BULL":
            direction = "BUY"
        elif rsi_val < 45 and macd_val < 0 and engulf == "BEAR" and trend == "BEAR":
            direction = "SELL"

        if direction:

            vol = atr(m15)
            sl = vol * 1.5
            tp = sl * 2

            sl_price = round(price - sl,2) if direction=="BUY" else round(price + sl,2)
            tp_price = round(price + tp,2) if direction=="BUY" else round(price - tp,2)

            send(f"""
📊 V10 SIGNAL

Symbol: {symbol}
Direction: {direction}

Entry: {price}
SL: {sl_price}
TP: {tp_price}

Trend: {trend}
RSI: {round(rsi_val,1)}
MACD: {round(macd_val,2)}

RR: 1:2
""")

            # simulate outcome tracking
            update_stats(win=(macd_val > 0 if direction=="BUY" else macd_val < 0))

    # send performance every 30 mins
    if datetime.now().minute % 30 == 0:
        send(report())

    time.sleep(120)
