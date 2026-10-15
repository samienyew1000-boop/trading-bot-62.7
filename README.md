# 👑 HYBRID AI MULTI-ASSET TRADING BOT
### Assets: Gold (XAUUSD), Bitcoin (BTCUSD), US Tech 100 (USTEC)
### Architecture: Dual Engine (AI Sniper 83.4% WR + Institutional Trend Runner 1:2 R:R)

ይህ ቦት ሦስቱን ዋና ዋና የዓለም የፋይናንስ ገበያዎች (**XAUUSD - Gold, BTCUSD - Bitcoin, እና USTEC - US Tech 100**) በ 1H (H1) Timeframe በሁለት ተደጋጋፊ የኳንት ኢንጂኖች (Dual Engines) የሚያስተዳድር የላቀ የ **Hybrid AI Trading System** ነው።

---

### ⚙️ የሁለቱ ኢንጂኖች አሠራር (The Dual Engines)

1. **🎯 Engine 1: AI Sniper (Mean Reversion - 83.4% Win Rate)**
   * **ስልት፦** Larry Connors RSI(2) Quantitative Oversold/Overbought Pullback
   * **ደንብ፦** በዋናው አዝማሚያ (EMA 200) አቅጣጫ ገበያው እጅግ በጣም ሲለጠጥ (RSI-2 <= 10 ለግዢ፣ RSI-2 >= 90 ለሽያጭ) ይገባል።
   * **መውጫ፦** ዋጋው ወደ 5-EMA አማካይ ሲመለስ ወዲያውኑ ትርፉን ቆልፎ ይወጣል።
   * **ውጤት፦** **83.4% አጠቃላይ የማሸነፍ እድል (Win Rate)!**

2. **🚀 Engine 2: Institutional Trend Runner (1:2.0 R:R Ratio)**
   * **ስልት፦** EMA 20/50 Pullback + Liquidity Breakout (በወርቅና ቢትኮይን ላይ)
   * **ደንብ፦** ንጹህ አዝማሚያ ሲኖር ከ EMA 20 ድጋፍ/ተቃውሞ ላይ በመነሳት በ 1:2.0 Risk-to-Reward ረጅም ትርፍ ያሳድዳል።
   * **ውጤት፦** **+77.0 R የተጣራ ትርፍ!**

---

### 📊 በ 10,000 ሻማዎች (1.5 ዓመታት) የተረጋገጠ ባክቴስት (Quant Backtest Report)

| Asset (አሴት) | 🚀 Trend Runner (1:2 R:R) | 🎯 AI Sniper (83.4% WR) | ⭐ የተዋሃደ ውጤት (Combined) | 💰 Net Profit (in R) |
|---|---|---|---|---|
| **🥇 Gold (XAUUSD)** | 230 ትሬድ (39.1% WR) | 831 ትሬድ (84.6% WR) | **1,061 ትሬድ (74.7% WR)** | **+65.9 R** |
| **🪙 Bitcoin (BTCUSD)** | 392 ትሬድ (36.5% WR) | 803 ትሬድ (86.6% WR) | **1,195 ትሬድ (70.1% WR)** | **+59.6 R** |
| **💻 US Tech 100 (USTEC)**| *ጠባቂነት ሲባል ጠፍቷል* | 904 ትሬድ (79.5% WR) | **904 ትሬድ (79.5% WR)** | **+24.4 R** |
| **🏆 ጠቅላላ ፖርትፎሊዮ** | **622 ትሬድ (+77.0 R)** | **2,538 ትሬድ (+73.0 R)** | **3,160 ትሬድ (74.4% WR)** | **+150.0 R** |

> **💡 የተረጋገጠ የሂሳብ ሀቅ (Mathematical Edge)፦**
> * **3,160 ትሬዶች** ውስጥ **2,350 አሸናፊ** (Wins) እና **810 ተሸናፊ** ብቻ!
> * አጠቃላይ የፖርትፎሊዮ ዊን ሬት (Portfolio Win Rate) = **74.4%**!
> * የተጣራ ትርፍ = **+150.0 R** (በ 1% ሪስክ አካውንትዎን +150% አሳድጓል)!

---

### 📁 እያንዳንዱን ትሬድ ለማረጋገጥ (Verifiable CSV Proofs)
በዚህ ፎልደር ውስጥ የሚገኙትን የ CSV ፋይሎች በ Excel ከፍተው በየቀኑ የተደረጉትን ትሬዶች በዓይንዎ ማየት ይችላሉ፦
1. `hybrid_xauusd_verification.csv` (1,061 የወርቅ ትሬዶች)
2. `hybrid_btcusd_verification.csv` (1,195 የቢትኮይን ትሬዶች)
3. `hybrid_ustec_verification.csv` (904 የቴክ 100 ትሬዶች)

---

### 🚀 ቦቱን ለማስጀመር (How to Run)

1. **በባክቴስት ሪፖርቱን እራስዎ ለማስላት፦**
   ```bash
   python backtest.py
   ```
2. **ቦቱን ለማስኬድ (Windows One-Click)፦**
   * በቀጥታ `run_bot.bat` ላይ ደብል ክሊክ ያድርጉ!
   * ወዲያውኑ MT5 እና Telegram Interactive Admin Menu ይገናኛሉ።
