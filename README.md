# 📈 TradingView Scraper

TradingView Scraper is a **free and open-source** scraper that gets you **unlimited** detailed TradingView market data for free.

## ✨ What Can I Get?

- 📈 **Full data on 450K+ stocks, crypto, forex, futures & bonds** — price, market cap, valuation, earnings, analyst targets & dividends
- 🕯️ **5,000 OHLCV candles per call** — 1-minute to monthly bars, plus Buy/Sell technicals on 10 timeframes and 20 years of financials
- 🔎 **Screeners for 71 countries, 2,400+ coins & ETFs** — 25 ready-made screens, any filter, plus earnings, dividend & economic calendars
- 💬 **News, trading ideas, Pine scripts & Minds** — full story text, comment threads, open-source Pine code & trader profiles

## 🎥 Example: A Full TradingView Symbol

```json
{
  "symbol": "NASDAQ:NVDA",
  "name": "NVIDIA Corporation",
  "link": "https://www.tradingview.com/symbols/NASDAQ-NVDA/",
  "logo": "https://s3-symbol-logo.tradingview.com/nvidia.svg",
  "isin": "US67066G1040",
  "sector": "Electronic Technology",
  "industry": "Semiconductors",
  "employees": 42000,
  "price": { "last": 202.06, "open": 207.53, "high": 209.9769, "low": 201.66, "change_percent": -1.2607505863956139, "volume": 119271454 },
  "market_cap": 4869645941162.001,
  "performance": { "performance_ytd": 6.439802986804327, "performance_5y": 682.5110371001472, "beta": 1.745773 },
  "ranges": { "high_52_week": 243.37, "low_52_week": 164.27, "all_time_high": 243.37 },
  "valuation": { "pe_ratio_ttm": 25.542942381108894, "revenue_ttm": 302969000000, "net_income_ttm": 192879000000, "gross_margin_ttm": 74.6746366790002 },
  "dividends": { "yield": 0.257349302187469, "recent": { "ex_date": "2026-09-10", "payment_date": "2026-10-01", "amount": 0.25 } },
  "earnings": { "last_release_date": "2026-08-26", "next_release_date": "2026-11-17", "eps_surprise_percent": 6.221279046940797, "revenue_forecast_next_quarter": 108801531183 },
  "analysts": {
    "price_target": { "average": 332.7276, "median": 318.2, "high": 710.29, "low": 180 },
    "recommendations": { "strong_buy": 62, "buy": 7, "hold": 3, "sell": 0, "strong_sell": 1, "total": 73 }
  },
  "technicals": { "rating": -0.5575757575757576, "label": "strong_sell", "rsi": 33.30534068239335 }
}
```

*Trimmed for readability.*

## 🚀 Unlimited Free TradingView Data — Get It in 60 Seconds

1️⃣ Clone and install:
```bash
git clone https://github.com/omkarcloud/tradingview-scraper
cd tradingview-scraper
python -m pip install -r requirements.txt
```

2️⃣ Start the API:
```bash
python run.py
```

3️⃣ Get your first data:
```bash
curl "http://localhost:8000/symbols/details?symbol=NASDAQ:NVDA"
```

```json
{
  "symbol": "NASDAQ:NVDA",
  "name": "NVIDIA Corporation",
  "link": "https://www.tradingview.com/symbols/NASDAQ-NVDA/",
  "sector": "Electronic Technology",
  "industry": "Semiconductors",
  "employees": 42000,
  "price": { "last": 202.06, "change_percent": -1.2607505863956139, "volume": 119271454 },
  "market_cap": 4869645941162.001,
  "valuation": { "pe_ratio_ttm": 25.542942381108894, "revenue_ttm": 302969000000, "net_income_ttm": 192879000000 },
  "earnings": { "next_release_date": "2026-11-17", "eps_forecast_next_quarter": 2.472418 },
  "analysts": {
    "price_target": { "average": 332.7276, "high": 710.29, "low": 180 },
    "recommendations": { "strong_buy": 62, "buy": 7, "hold": 3, "sell": 0, "strong_sell": 1, "total": 73 }
  },
  "technicals": { "rating": -0.5575757575757576, "label": "strong_sell", "rsi": 33.30534068239335 }
}
```

All 23 endpoints are now live at `http://localhost:8000`.

No proxy needed — TradingView served every endpoint to a home connection and a cloud server alike. If you ever see 502 "blocked" errors at high volume, set `TRADINGVIEW_PROXY` (`TRADINGVIEW_PROXY=http://user:pass@host:port python run.py`).

## 📚 Endpoints

23 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| Symbol Details | `/symbols/details` | Price, valuation, earnings, analyst targets, dividends and FAQ in one call |
| Search Symbols | `/symbols/search` | Stocks, crypto, forex, futures and ETFs by name, ticker or ISIN |
| Get Quotes | `/symbols/quote` | Live price, change, volume and rating for up to 20 symbols |
| Price History | `/symbols/history` | Up to 5,000 OHLCV candles, from 1-minute to monthly bars |
| Technical Analysis | `/symbols/technicals` | Buy/Sell gauge, 40+ indicators and pivots on 10 timeframes |
| Financial Statements | `/symbols/financials` | Income, balance sheet, cash flow and ratios, up to 20 years |
| Symbol Markets | `/symbols/markets` | Every exchange a symbol trades on, with price and volume |
| Screeners | `/screener/scan`, `/screener/crypto`, `/screener/etf` | Stocks in 71 countries, 2,400+ coins and ETFs, 50 per page |
| Calendars | `/calendar/earnings`, `/calendar/economic`, `/calendar/dividends` | Earnings surprises, economic releases and ex-dividend dates by date |
| News | `/news/search`, `/news/details` | Latest headlines by symbol, market or provider, plus full story text |
| Trading Ideas | `/ideas/search`, `/ideas/details`, `/ideas/comments` | Ideas by symbol, author or text, with full text and comments |
| Pine Scripts | `/scripts/search`, `/scripts/details` | Indicators and strategies with likes, plus open-source Pine code |
| Minds | `/minds/search`, `/minds/details` | Trader posts for any symbol or member, with every comment |
| User Profile | `/users/details` | Followers, idea and script counts, badges and socials |

## 🔍 Exploring Parameters

The same API is published on RapidAPI, and its playground is the easiest place to try parameters and see raw responses. Once a request looks right, run it locally for **unlimited free** data.

1. [Subscribe to the free plan](https://rapidapi.com/OmkarCloud/api/best-tradingview-scraper-free-1000-calls/pricing) — 1,000 calls/month, no credit card.
2. [Try the endpoints in the playground](https://rapidapi.com/OmkarCloud/api/best-tradingview-scraper-free-1000-calls/playground) — every param is pre-filled, so you see real data in one click.
3. Copy the generated code and replace `https://best-tradingview-scraper-free-1000-calls.p.rapidapi.com` with `http://localhost:8000`. It will now run against your local API.

```python
import requests

# generated by the playground, host swapped for the local API
response = requests.get(
    "http://localhost:8000/screener/scan",
    params={"market": "america", "preset": "gainers"},
)
print(response.json())
```

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about TradingView Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://www.omkar.cloud/l/tradingview-scraper-github-whatsapp)

[![Ask Us by Email about TradingView Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Help%20with%20TradingView%20Scraper%20API&body=I%20need%20help%20using%20the%20TradingView%20Scraper%20API.)

## ⚡ Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website
- [**AliExpress Scraper**](https://www.omkar.cloud/tools/aliexpress-scraper-api) — live product details, SKU variants, stock & shipping
- [**Booking Scraper**](https://www.omkar.cloud/tools/booking-scraper) — Booking.com hotels: prices, ratings, rooms & amenities
- [**Etsy Scraper**](https://www.omkar.cloud/tools/etsy-scraper) — Etsy products: prices, discounts, shops & variations

## ⭐ Love It? [Star It ⭐!](https://github.com/omkarcloud/tradingview-scraper)

Star the repo ⭐ and become my star hero!

It's just 1 click, but it means the world to me.

[![Star us on GitHub](https://raw.githubusercontent.com/omkarcloud/google-maps-scraper/master/screenshots/star-us.png)](https://github.com/omkarcloud/tradingview-scraper)
