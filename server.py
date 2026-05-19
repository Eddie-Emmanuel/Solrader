#!/usr/bin/env python3
"""
Solana Memecoin Migration Tracker — Backend v2
Sources : GMGN, Pump.fun, DexScreener (pairs + boosts)
Ages    : 1-3h | 3-6h | 6-12h | 12-18h | 18-24h
Viral   : volume velocity + price momentum + boost signal + recency
Run     : python server.py
Open    : http://localhost:8888
"""

import json, time, urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

import os
PORT = int(os.environ.get("PORT", 8888))
MIN_MC    = 25_000
CACHE_TTL = 60

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept":          "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://gmgn.ai/",
    "Origin":          "https://gmgn.ai",
}

# ── HELPERS ──────────────────────────────────────────────────────────────────

def fetch_url(url, extra=None):
    req = urllib.request.Request(url, headers={**HEADERS, **(extra or {})})
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"  [WARN] {url[:72]}... -> {e}")
        return None

def get_category(mins):
    h = mins / 60
    if  1 <= h <  3:  return "1-3"
    if  3 <= h <  6:  return "3-6"
    if  6 <= h < 12:  return "6-12"
    if 12 <= h < 18:  return "12-18"
    if 18 <= h <= 24: return "18-24"
    return None

# ── SOURCES ──────────────────────────────────────────────────────────────────

def fetch_gmgn():
    coins = []
    for w in ("1h", "6h", "24h"):
        url = (f"https://gmgn.ai/defi/quotation/v1/rank/sol/swaps/{w}"
               f"?orderby=marketcap&direction=desc&filters[]=not_honeypot&filters[]=pump&limit=50")
        print(f"  GMGN {w} ...")
        d = fetch_url(url)
        if d:
            coins.extend(d.get("data", {}).get("rank", []) or d.get("rank", []) or [])
        time.sleep(0.3)
    return coins

def fetch_pump():
    print("  Pump.fun migrated ...")
    url = ("https://frontend-api.pump.fun/coins"
           "?offset=0&limit=50&sort=last_trade_timestamp&order=DESC&includeNsfw=false&complete=true")
    d = fetch_url(url, {"Referer": "https://pump.fun/", "Origin": "https://pump.fun"})
    return d if isinstance(d, list) else []

def fetch_dex_pairs():
    print("  DexScreener pairs ...")
    d = fetch_url("https://api.dexscreener.com/latest/dex/search?q=solana")
    if d:
        return [p for p in (d.get("pairs") or []) if p.get("chainId") == "solana"]
    return []

def fetch_dex_boosts():
    print("  DexScreener boosts ...")
    d = fetch_url("https://api.dexscreener.com/token-boosts/latest/v1")
    if isinstance(d, list):
        return {x.get("tokenAddress", ""): x for x in d if x.get("chainId") == "solana"}
    return {}

# ── NORMALISE ─────────────────────────────────────────────────────────────────

def tw(sym):
    return f"https://twitter.com/search?q=%24{sym}&src=typed_query&f=live"

def norm_gmgn(c):
    now  = int(time.time() * 1000)
    ots  = (c.get("open_timestamp") or c.get("created_timestamp") or 0) * 1000
    mins = max(0, int((now - ots) / 60000)) if ots else 0
    addr = c.get("address") or ""
    sym  = c.get("symbol") or "?"
    return {
        "name": sym or c.get("name") or "?", "symbol": sym, "address": addr,
        "mc":        float(c.get("market_cap") or c.get("marketcap") or 0),
        "volume24h": float(c.get("volume") or c.get("volume_24h") or 0),
        "change1h":  float(c.get("price_change_percent") or c.get("change_percent") or 0),
        "liquidity": float(c.get("liquidity") or 0),
        "migratedMinsAgo": mins, "source": "gmgn",
        "dexUrl":     f"https://dexscreener.com/solana/{addr}",
        "gmgnUrl":    f"https://gmgn.ai/sol/token/{addr}",
        "twitterUrl": tw(sym),
    }

def norm_pump(c):
    now  = int(time.time() * 1000)
    cts  = (c.get("complete_timestamp") or c.get("last_reply") or 0) * 1000
    mins = max(0, int((now - cts) / 60000)) if cts else 0
    mc   = float(c.get("usd_market_cap") or c.get("market_cap") or 0)
    addr = c.get("mint") or ""
    sym  = c.get("symbol") or "?"
    return {
        "name": c.get("name") or "?", "symbol": sym, "address": addr,
        "mc": mc, "volume24h": float(c.get("volume") or 0),
        "change1h": float(c.get("price_change_1h") or 0),
        "liquidity": mc * 0.05, "migratedMinsAgo": mins, "source": "pump.fun",
        "dexUrl":     f"https://dexscreener.com/solana/{addr}",
        "gmgnUrl":    f"https://gmgn.ai/sol/token/{addr}",
        "twitterUrl": tw(sym),
    }

def norm_dex(p):
    now  = int(time.time() * 1000)
    cat  = p.get("pairCreatedAt") or 0
    mins = max(0, int((now - cat) / 60000)) if cat else 0
    bt   = p.get("baseToken") or {}
    addr = bt.get("address") or ""
    sym  = bt.get("symbol") or "?"
    return {
        "name": bt.get("name") or sym, "symbol": sym, "address": addr,
        "mc":        float(p.get("fdv") or p.get("marketCap") or 0),
        "volume24h": float((p.get("volume") or {}).get("h24") or 0),
        "change1h":  float((p.get("priceChange") or {}).get("h1") or 0),
        "liquidity": float((p.get("liquidity") or {}).get("usd") or 0),
        "migratedMinsAgo": mins, "source": "dexscreener",
        "dexUrl":     p.get("url") or f"https://dexscreener.com/solana/{addr}",
        "gmgnUrl":    f"https://gmgn.ai/sol/token/{addr}",
        "twitterUrl": tw(sym),
    }

# ── VIRAL / SOCIAL SCORE ─────────────────────────────────────────────────────
#
#  Component                           Max   Rationale
#  ─────────────────────────────────   ───   ─────────────────────────────────
#  1. Volume velocity  (vol / age_h)    35   CT buzz drives buy pressure
#  2. Price momentum   (1h % chg)       25   Pumping = people posting
#  3. Market cap size                   15   More holders = more sharers
#  4. DexScreener paid boost            15   Active paid social campaign
#  5. Age recency bonus                 10   1-3h = CT hottest discovery zone
#
#  0-100  →  Viral ≥75 | Trending ≥50 | Growing ≥30 | Low <30

def score_viral(coin, boosts):
    s    = 0
    age  = max(coin["migratedMinsAgo"] / 60, 0.25)
    vel  = coin["volume24h"] / age
    chg  = coin["change1h"]
    mc   = coin["mc"]
    addr = coin.get("address", "")

    # 1 volume velocity
    s += min(35, (vel / 500_000) * 35)

    # 2 price momentum
    if   chg >= 200: s += 25
    elif chg >= 100: s += 22
    elif chg >=  50: s += 18
    elif chg >=  20: s += 13
    elif chg >=   5: s += 7
    elif chg >=   0: s += 3
    else:            s += max(0, 3 + chg * 0.05)

    # 3 market cap
    if   mc >= 5_000_000:  s += 15
    elif mc >= 1_000_000:  s += 12
    elif mc >=   500_000:  s += 8
    elif mc >=   100_000:  s += 4
    elif mc >=    50_000:  s += 2

    # 4 dex boost
    boosted   = bool(addr and addr in boosts)
    boost_amt = 0
    if boosted:
        boost_amt = boosts[addr].get("amount", 0) or 0
        s += 15 if boost_amt >= 500 else (10 if boost_amt >= 100 else 5)
    coin["boosted"]     = boosted
    coin["boostAmount"] = boost_amt

    # 5 recency
    if   age <  3:  s += 10
    elif age <  6:  s += 6
    elif age < 12:  s += 3

    score = min(100, max(0, round(s)))
    coin["viralScore"] = score
    if   score >= 75: coin["viralLabel"] = "Viral";    coin["viralTier"] = 4
    elif score >= 50: coin["viralLabel"] = "Trending"; coin["viralTier"] = 3
    elif score >= 30: coin["viralLabel"] = "Growing";  coin["viralTier"] = 2
    else:             coin["viralLabel"] = "Low";      coin["viralTier"] = 1
    return coin

# ── ORCHESTRATION ─────────────────────────────────────────────────────────────

def fetch_all():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Fetch cycle starting ...")
    raw = []

    try:
        for c in fetch_gmgn():               raw.append(norm_gmgn(c))
    except Exception as e: print(f"  GMGN err: {e}")

    try:
        for c in fetch_pump():               raw.append(norm_pump(c))
    except Exception as e: print(f"  Pump err: {e}")

    try:
        for c in fetch_dex_pairs()[:30]:     raw.append(norm_dex(c))
    except Exception as e: print(f"  Dex err: {e}")

    boosts = {}
    try:
        boosts = fetch_dex_boosts()
        print(f"  Boosts: {len(boosts)} Solana tokens")
    except Exception as e: print(f"  Boost err: {e}")

    # dedup
    seen, deduped = set(), []
    for c in raw:
        k = c["address"] or (c["name"] + c["symbol"])
        if k not in seen:
            seen.add(k); deduped.append(c)

    # filter
    filtered = [c for c in deduped if c["mc"] >= MIN_MC and get_category(c["migratedMinsAgo"])]

    # score
    for c in filtered:
        score_viral(c, boosts)

    if not filtered:
        print("  No live data — using sample fallback")
        filtered = sample_data()
        for c in filtered: score_viral(c, {})

    print(f"  Done -> {len(filtered)} coins\n")
    return filtered

# ── SAMPLE FALLBACK ───────────────────────────────────────────────────────────

def sample_data():
    rows = [
        ("ROCKET FROG", "RFROG", "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU", 380000,  820000,  67.4,  75,   28000, "pump.fun"),
        ("CHAD PEPE",   "CPEPE", "3HFHn5DGx6PTFMpCwk8hoQdmN5hANhJsEK4MWZB3zQHa", 145000,  310000,  34.2,  105,  12000, "gmgn"),
        ("MOON DOGGO",  "MDGO",  "9bFNrXNb2WTx8fMHkQ2sNYe8HjM9GgZ8gTf2hErwKzMN", 92000,   175000,  18.9,  148,  8500,  "pump.fun"),
        ("SOLFIRE",     "SLFIRE","Fg6PaFpoGXkYsidMpWTK6W2BeZ7FEfcYkg476zPFsLnS",  58000,   95000,   44.1,  162,  6200,  "gmgn"),
        ("BOME CAT",    "BCAT",  "2uPfgCCR5b8KFyCEPLrj9EqJkMCKvHNwKBnXyGmJV8bP", 842000,  1200000, 12.4,  220,  55000, "gmgn"),
        ("DEGEN RAT",   "DRAT",  "4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU",  312000,  540000,  -5.2,  280,  22000, "pump.fun"),
        ("FROG CZAR",   "FCZAR","CKfatsPMUf8SkiURsDXs7eK6GWb4Jsd6UDbs7twMCWxo",  178000,  290000,  34.7,  310,  18500, "gmgn"),
        ("MEGA PEPE",   "MPEPE","TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",   2100000, 4500000, 8.1,   390,  145000,"pump.fun"),
        ("WIF UNCLE",   "WIFU", "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1",  88000,   120000,  2.3,   440,  9200,  "gmgn"),
        ("HARAMBE2",    "HRMB2","DezXAZ8z7PnrnRJjz3wXboRgixCa6xjnB7YaB1pPB263",  55000,   87000,   -11.6, 760,  7800,  "pump.fun"),
        ("SOLCAT",      "SCAT", "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",   1450000, 2200000, 21.9,  820,  98000, "gmgn"),
        ("BONK 2.0",    "BNKV2","Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  4200000, 9100000, 15.3,  1100, 310000,"gmgn"),
        ("MOON DOG",    "MDOG", "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",  195000,  340000,  44.2,  1080, 19000, "pump.fun"),
        ("RATSOL",      "RATS", "So11111111111111111111111111111111111111112",      78000,   102000,  -9.1,  1150, 8900,  "gmgn"),
        ("DOGE 2049",   "D2049","EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  3800000, 7200000, 19.1,  1300, 270000,"pump.fun"),
    ]
    out = []
    for r in rows:
        a, s = r[2], r[1]
        out.append({
            "name": r[0], "symbol": s, "address": a,
            "mc": r[3], "volume24h": r[4], "change1h": r[5],
            "migratedMinsAgo": r[6], "liquidity": r[7], "source": r[8],
            "dexUrl":     f"https://dexscreener.com/solana/{a}",
            "gmgnUrl":    f"https://gmgn.ai/sol/token/{a}",
            "twitterUrl": tw(s),
        })
    return [c for c in out if get_category(c["migratedMinsAgo"])]

# ── CACHE ─────────────────────────────────────────────────────────────────────

_cache = {"data": None, "ts": 0}

def cached(force=False):
    if force or _cache["data"] is None or (time.time() - _cache["ts"]) > CACHE_TTL:
        _cache["data"] = fetch_all()
        _cache["ts"]   = time.time()
    return _cache["data"]

# ── HTTP HANDLER ──────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): print(f"  HTTP {args[1]} {args[0]}")

    def cors(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200); self.cors(); self.end_headers()

    def do_GET(self):
        path  = self.path.split("?")[0]
        force = "force" in self.path

        if path == "/":
            try:
                data = open("index.html", "rb").read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.cors(); self.end_headers(); self.wfile.write(data)
            except FileNotFoundError:
                self.send_response(404); self.end_headers()
                self.wfile.write(b"index.html not found in the same folder as server.py")
            return

        if path == "/api/coins":
            coins     = cached(force=force)
            is_sample = bool(coins and coins[0].get("address","").startswith("7xKX"))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.cors(); self.end_headers()
            self.wfile.write(json.dumps({
                "ok": True, "ts": int(time.time()),
                "count": len(coins), "coins": coins, "sample": is_sample,
            }).encode())
            return

        if path == "/api/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.cors(); self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "time": datetime.now().isoformat()}).encode())
            return

        self.send_response(404); self.end_headers(); self.wfile.write(b"Not found")

# ── ENTRY ─────────────────────────────────────────────────────────────────────

def run():
    print("=" * 60)
    print("  Solana Memecoin Migration Tracker  — Backend v2")
    print("=" * 60)
    print(f"  Dashboard : http://localhost:{PORT}")
    print(f"  API       : http://localhost:{PORT}/api/coins")
    print(f"  Cache TTL : {CACHE_TTL}s     Min MC : ${MIN_MC:,}")
    print(f"  Ages      : 1-3h · 3-6h · 6-12h · 12-18h · 18-24h")
    print(f"  Viral     : vol velocity · momentum · boost · recency")
    print("=" * 60)
    print("  index.html must sit in the same folder.\n")
    srv = HTTPServer(("0.0.0.0", PORT), Handler)
    try:    srv.serve_forever()
    except KeyboardInterrupt: print("\n  Stopped.")

if __name__ == "__main__":
    run()
