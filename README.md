# SMC Price Action Telegram Trading Bot

ይህ ቦት የ **Pure Price Action (SMC - Smart Money Concepts)** ስትራቴጂን በመጠቀም **EURUSD**, **XAUUSD (Gold)** እና **USDCAD**ን በ MetaTrader 5 (MT5) አማካኝነት 24/7 በመከታተል ሴትአፕ ሲገኝ በቀጥታ ወደ ቴሌግራም የሚያሳውቅ ነው።

---

### የቦቱ 5 ዋና ዋና ኖቲፊኬሽኖች (Notifications)

1. 🟢 / 🔴 **BOS ተደርጓል (Break of Structure):**
   * ሻማው በ **Body Close** የቀደመውን Swing High ወይም Low ሲሰብር ይላካል።
2. 🔄 **Market Direction Shift:**
   * አቅጣጫው ከ Bullish ወደ Bearish ወይም ከ Bearish ወደ Bullish ሲቀየር ያሳውቃል።
3. 📍 **OB Mitigate ተደርጓል (Alert 1):**
   * ዋጋው ተመልሶ የ 1H Valid Order Block (OB) ሲነካ ይላካል።
4. ⚡ **Reaction ሰጥቷል (Alert 2):**
   * በ 5M Timeframe ላይ ገበያው ከዞኑ ተመልሶ Reaction/Rejection ሲያሳይ ይላካል።
5. 🎯 **ተመልሷል ENTRY! (Alert 3):**
   * ዋጋው ወደ 5M OB ተመልሶ Retest ሲያደርግ እና የማረጋገጫ ሻማ ሲዘጋ ከ **Entry Price**, **Stop Loss (SL)** እና **Take Profit (TP 1:3)** ጋር ይላካል።
6. ❌ **Fail አድርጓል (OB Invalidation):**
   * ሻማው በ **Body Close** የ OBውን ወሰን ሲሰብር ብቻ Fail መደረጉ ይገለጻል (Wick ግን እንደ Liquidity grab ይቆጠራል እንጂ Fail አያደርገውም)።

---

### ቦቱን እንዴት ማስጀመር ይቻላል?

1. **MetaTrader 5 (Exness)** በኮምፒውተርዎ ላይ ክፍት መሆኑን ያረጋግጡ።
2. ፎልደሩ ውስጥ ያለውን **`run_bot.bat`** የተባለውን ፋይል ደብል ክሊክ (Double click) ያድርጉት።
3. ቦቱ ራሱ ቴሌግራም ላይ *"🤖 የ SMC የትሬዲንግ ቦት ስራ ጀምሯል!"* ብሎ ይልክልዎታል።
