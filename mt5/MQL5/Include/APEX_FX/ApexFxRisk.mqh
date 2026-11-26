#ifndef __APEX_FX_RISK_MQH__
#define __APEX_FX_RISK_MQH__

#include "ApexFxTypes.mqh"

class CApexRiskManager
{
private:
   double NormalizeVolume(const string symbol, const double lots)
   {
      const double minVolume = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
      const double maxVolume = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
      const double step = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);

      if(step <= 0.0 || lots <= 0.0)
         return 0.0;

      double normalized = MathFloor(lots / step) * step;
      normalized = MathMax(minVolume, MathMin(maxVolume, normalized));

      int digits = 0;
      double scaledStep = step;
      while(digits < 8 && MathAbs(scaledStep - MathRound(scaledStep)) > 0.00000001)
      {
         scaledStep *= 10.0;
         digits++;
      }

      return NormalizeDouble(normalized, digits);
   }

   int ExposureForCurrency(
      const string symbol,
      const ENUM_POSITION_TYPE positionType,
      const string currency
   )
   {
      const string base = ApexBaseCurrency(symbol);
      const string quote = ApexQuoteCurrency(symbol);

      if(currency == "")
         return 0;

      if(positionType == POSITION_TYPE_BUY)
      {
         if(currency == base)
            return 1;
         if(currency == quote)
            return -1;
      }

      if(positionType == POSITION_TYPE_SELL)
      {
         if(currency == base)
            return -1;
         if(currency == quote)
            return 1;
      }

      return 0;
   }

   int NewExposureForCurrency(
      const string symbol,
      const ENUM_APEX_DIRECTION direction,
      const string currency
   )
   {
      const string base = ApexBaseCurrency(symbol);
      const string quote = ApexQuoteCurrency(symbol);

      if(direction == APEX_DIR_LONG)
      {
         if(currency == base)
            return 1;
         if(currency == quote)
            return -1;
      }

      if(direction == APEX_DIR_SHORT)
      {
         if(currency == base)
            return -1;
         if(currency == quote)
            return 1;
      }

      return 0;
   }

   bool ExistingGoldLong(const int magic)
   {
      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         const ulong ticket = PositionGetTicket(i);
         if(ticket == 0 || !PositionSelectByTicket(ticket))
            continue;

         if((int)PositionGetInteger(POSITION_MAGIC) != magic)
            continue;

         const string symbol = PositionGetString(POSITION_SYMBOL);
         const ENUM_POSITION_TYPE type = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
         if(StringFind(symbol, "XAU") == 0 && type == POSITION_TYPE_BUY)
            return true;
      }

      return false;
   }

   bool ExistingLongJpy(const int magic)
   {
      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         const ulong ticket = PositionGetTicket(i);
         if(ticket == 0 || !PositionSelectByTicket(ticket))
            continue;

         if((int)PositionGetInteger(POSITION_MAGIC) != magic)
            continue;

         const string symbol = PositionGetString(POSITION_SYMBOL);
         const ENUM_POSITION_TYPE type = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
         if(ExposureForCurrency(symbol, type, "JPY") > 0)
            return true;
      }

      return false;
   }

public:
   double EffectiveRiskPct(
      const double hardRiskPct,
      const bool useKelly,
      const double winRate,
      const double averageRewardRisk,
      const double kellyFraction
   )
   {
      if(!useKelly)
         return MathMax(0.0, hardRiskPct);

      const double w = MathMax(0.0, MathMin(1.0, winRate));
      const double r = MathMax(0.01, averageRewardRisk);
      const double l = 1.0 - w;
      const double fullKelly = (w * r - l) / r;
      const double fractionalKellyPct = MathMax(0.0, fullKelly * MathMax(0.0, kellyFraction) * 100.0);

      return MathMin(MathMax(0.0, hardRiskPct), fractionalKellyPct);
   }

   double AccountBase(
      const double accountBalanceOverride
   )
   {
      if(accountBalanceOverride > 0.0)
         return accountBalanceOverride;

      return AccountInfoDouble(ACCOUNT_BALANCE);
   }

   double CalculateLots(
      const string symbol,
      const double accountBalanceOverride,
      const double riskPct,
      const double entryPrice,
      const double stopLoss
   )
   {
      const double account = AccountBase(accountBalanceOverride);
      const double riskMoney = account * MathMax(0.0, riskPct) / 100.0;
      const double tickSize = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_SIZE);
      const double tickValue = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_VALUE);
      const double stopDistance = MathAbs(entryPrice - stopLoss);

      if(account <= 0.0 || riskMoney <= 0.0 || tickSize <= 0.0 || tickValue <= 0.0 || stopDistance <= 0.0)
         return 0.0;

      const double ticksAtRisk = stopDistance / tickSize;
      const double rawLots = riskMoney / (ticksAtRisk * tickValue);

      return NormalizeVolume(symbol, rawLots);
   }

   int CountOpenTrades(const int magic)
   {
      int count = 0;

      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         const ulong ticket = PositionGetTicket(i);
         if(ticket == 0 || !PositionSelectByTicket(ticket))
            continue;

         if((int)PositionGetInteger(POSITION_MAGIC) == magic)
            count++;
      }

      return count;
   }

   bool HasOpenSymbolPosition(const int magic, const string symbol)
   {
      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         const ulong ticket = PositionGetTicket(i);
         if(ticket == 0 || !PositionSelectByTicket(ticket))
            continue;

         if((int)PositionGetInteger(POSITION_MAGIC) != magic)
            continue;

         if(PositionGetString(POSITION_SYMBOL) == symbol)
            return true;
      }

      return false;
   }

   int CountConsecutiveLosses(const int magic, const int lookbackDays = 90)
   {
      const datetime toTime = TimeCurrent();
      const datetime fromTime = toTime - (datetime)(lookbackDays * 86400);

      if(!HistorySelect(fromTime, toTime))
         return 0;

      int losses = 0;
      const int totalDeals = (int)HistoryDealsTotal();

      for(int i = totalDeals - 1; i >= 0; i--)
      {
         const ulong deal = HistoryDealGetTicket(i);
         if(deal == 0)
            continue;

         if((int)HistoryDealGetInteger(deal, DEAL_MAGIC) != magic)
            continue;

         const ENUM_DEAL_ENTRY entry = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(deal, DEAL_ENTRY);
         if(entry != DEAL_ENTRY_OUT && entry != DEAL_ENTRY_INOUT && entry != DEAL_ENTRY_OUT_BY)
            continue;

         const double profit =
            HistoryDealGetDouble(deal, DEAL_PROFIT) +
            HistoryDealGetDouble(deal, DEAL_SWAP) +
            HistoryDealGetDouble(deal, DEAL_COMMISSION);

         if(profit < 0.0)
         {
            losses++;
            continue;
         }

         if(profit > 0.0)
            break;
      }

      return losses;
   }

   bool HasCorrelatedExposure(
      const int magic,
      const string symbol,
      const ENUM_APEX_DIRECTION direction,
      const int maxCorrelated,
      string &currency
   )
   {
      currency = "";

      if(direction == APEX_DIR_NONE || maxCorrelated <= 0)
         return false;

      const string base = ApexBaseCurrency(symbol);
      const string quote = ApexQuoteCurrency(symbol);
      string currencies[2];
      currencies[0] = base;
      currencies[1] = quote;

      for(int c = 0; c < 2; c++)
      {
         int matchingExposure = 0;
         const int newExposure = NewExposureForCurrency(symbol, direction, currencies[c]);

         if(currencies[c] == "" || newExposure == 0)
            continue;

         for(int i = PositionsTotal() - 1; i >= 0; i--)
         {
            const ulong ticket = PositionGetTicket(i);
            if(ticket == 0 || !PositionSelectByTicket(ticket))
               continue;

            if((int)PositionGetInteger(POSITION_MAGIC) != magic)
               continue;

            const string existingSymbol = PositionGetString(POSITION_SYMBOL);
            const ENUM_POSITION_TYPE existingType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
            const int existingExposure = ExposureForCurrency(existingSymbol, existingType, currencies[c]);

            if(existingExposure == newExposure)
               matchingExposure++;
         }

         if(matchingExposure >= maxCorrelated)
         {
            currency = currencies[c];
            return true;
         }
      }

      const bool newGoldLong = StringFind(symbol, "XAU") == 0 && direction == APEX_DIR_LONG;
      const bool newLongJpy = NewExposureForCurrency(symbol, direction, "JPY") > 0;

      if(newGoldLong && ExistingLongJpy(magic))
      {
         currency = "JPY/XAU safe-haven cluster";
         return true;
      }

      if(newLongJpy && ExistingGoldLong(magic))
      {
         currency = "JPY/XAU safe-haven cluster";
         return true;
      }

      return false;
   }

   bool SpreadIsWide(
      const string symbol,
      const int lookbackBars,
      const double multiplier,
      double &currentSpreadPoints,
      double &averageSpreadPoints
   )
   {
      const double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
      const double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
      const double bid = SymbolInfoDouble(symbol, SYMBOL_BID);

      currentSpreadPoints = 0.0;
      averageSpreadPoints = 0.0;

      if(point <= 0.0 || ask <= 0.0 || bid <= 0.0)
         return false;

      currentSpreadPoints = (ask - bid) / point;

      MqlRates rates[];
      ArraySetAsSeries(rates, true);
      const int barsToCopy = lookbackBars < 10 ? 10 : lookbackBars;
      const int copied = CopyRates(symbol, PERIOD_M1, 1, barsToCopy, rates);

      if(copied <= 5)
         return false;

      double spreadTotal = 0.0;
      int spreadCount = 0;

      for(int i = 0; i < copied; i++)
      {
         if(rates[i].spread <= 0)
            continue;

         spreadTotal += (double)rates[i].spread;
         spreadCount++;
      }

      if(spreadCount <= 0)
         return false;

      averageSpreadPoints = spreadTotal / (double)spreadCount;

      if(averageSpreadPoints <= 0.0)
         return false;

      return currentSpreadPoints > averageSpreadPoints * MathMax(1.0, multiplier);
   }

   void BuildRiskState(
      const int magic,
      const string symbol,
      const ENUM_APEX_DIRECTION direction,
      const double dailyStartEquity,
      const double maxDailyDrawdownPct,
      const double maxPortfolioDrawdownPct,
      const int maxOpenTrades,
      const int maxCorrelated,
      const bool onePositionPerSymbol,
      const int spreadLookbackBars,
      const double spreadMultiplier,
      ApexRiskState &state
   )
   {
      ApexResetRiskState(state);

      const double equity = AccountInfoDouble(ACCOUNT_EQUITY);
      state.openTrades = CountOpenTrades(magic);
      state.consecutiveLosses = CountConsecutiveLosses(magic);
      state.spreadWide = SpreadIsWide(
         symbol,
         spreadLookbackBars,
         spreadMultiplier,
         state.currentSpreadPoints,
         state.averageSpreadPoints
      );

      if(dailyStartEquity > 0.0 && equity > 0.0)
         state.dailyDrawdownPct = MathMax(0.0, (dailyStartEquity - equity) / dailyStartEquity * 100.0);

      const string highWaterKey = "APEXFX_HWM_" + IntegerToString(magic);
      double highWater = equity;

      if(GlobalVariableCheck(highWaterKey))
         highWater = GlobalVariableGet(highWaterKey);

      if(equity > highWater || highWater <= 0.0)
      {
         highWater = equity;
         GlobalVariableSet(highWaterKey, highWater);
      }

      if(highWater > 0.0 && equity > 0.0)
         state.portfolioDrawdownPct = MathMax(0.0, (highWater - equity) / highWater * 100.0);

      state.correlatedExposure = HasCorrelatedExposure(
         magic,
         symbol,
         direction,
         maxCorrelated,
         state.correlatedCurrency
      );

      if(maxDailyDrawdownPct > 0.0 && state.dailyDrawdownPct >= maxDailyDrawdownPct)
      {
         state.halted = true;
         state.reason = ApexAppendReason(state.reason, "daily drawdown circuit breaker active");
      }

      if(maxPortfolioDrawdownPct > 0.0 && state.portfolioDrawdownPct >= maxPortfolioDrawdownPct)
      {
         state.halted = true;
         state.reason = ApexAppendReason(state.reason, "portfolio drawdown circuit breaker active");
      }

      if(state.consecutiveLosses >= 3)
      {
         state.halted = true;
         state.reason = ApexAppendReason(state.reason, "3 consecutive losing trades pause active");
      }

      if(maxOpenTrades > 0 && state.openTrades >= maxOpenTrades)
      {
         state.halted = true;
         state.reason = ApexAppendReason(state.reason, "max open trades reached");
      }

      if(onePositionPerSymbol && HasOpenSymbolPosition(magic, symbol))
      {
         state.halted = true;
         state.reason = ApexAppendReason(state.reason, "existing position on symbol");
      }

      if(state.correlatedExposure)
      {
         state.halted = true;
         state.reason = ApexAppendReason(state.reason, "correlated exposure limit reached: " + state.correlatedCurrency);
      }

      if(state.spreadWide)
      {
         state.halted = true;
         state.reason = ApexAppendReason(state.reason, "spread exceeds allowed multiple of average");
      }
   }
};

#endif
