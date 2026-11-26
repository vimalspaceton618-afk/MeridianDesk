#ifndef __APEX_FX_SMC_MQH__
#define __APEX_FX_SMC_MQH__

#include "ApexFxTypes.mqh"

struct ApexSwing
{
   bool     valid;
   int      index;
   double   price;
   datetime time;
};

void ApexResetSwing(ApexSwing &swing)
{
   swing.valid = false;
   swing.index = -1;
   swing.price = 0.0;
   swing.time = 0;
}

class CApexSmcAnalyzer
{
private:
   bool IsSwingHigh(MqlRates &rates[], const int index, const int depth)
   {
      for(int d = 1; d <= depth; d++)
      {
         if(rates[index].high <= rates[index - d].high)
            return false;

         if(rates[index].high < rates[index + d].high)
            return false;
      }

      return true;
   }

   bool IsSwingLow(MqlRates &rates[], const int index, const int depth)
   {
      for(int d = 1; d <= depth; d++)
      {
         if(rates[index].low >= rates[index - d].low)
            return false;

         if(rates[index].low > rates[index + d].low)
            return false;
      }

      return true;
   }

   void FindLatestSwings(
      MqlRates &rates[],
      const int total,
      const int depth,
      ApexSwing &latestHigh,
      ApexSwing &previousHigh,
      ApexSwing &latestLow,
      ApexSwing &previousLow
   )
   {
      ApexResetSwing(latestHigh);
      ApexResetSwing(previousHigh);
      ApexResetSwing(latestLow);
      ApexResetSwing(previousLow);

      for(int i = depth + 1; i < total - depth; i++)
      {
         if(!latestHigh.valid && IsSwingHigh(rates, i, depth))
         {
            latestHigh.valid = true;
            latestHigh.index = i;
            latestHigh.price = rates[i].high;
            latestHigh.time = rates[i].time;
         }
         else if(latestHigh.valid && !previousHigh.valid && IsSwingHigh(rates, i, depth))
         {
            previousHigh.valid = true;
            previousHigh.index = i;
            previousHigh.price = rates[i].high;
            previousHigh.time = rates[i].time;
         }

         if(!latestLow.valid && IsSwingLow(rates, i, depth))
         {
            latestLow.valid = true;
            latestLow.index = i;
            latestLow.price = rates[i].low;
            latestLow.time = rates[i].time;
         }
         else if(latestLow.valid && !previousLow.valid && IsSwingLow(rates, i, depth))
         {
            previousLow.valid = true;
            previousLow.index = i;
            previousLow.price = rates[i].low;
            previousLow.time = rates[i].time;
         }

         if(latestHigh.valid && previousHigh.valid && latestLow.valid && previousLow.valid)
            return;
      }
   }

   double AverageRange(MqlRates &rates[], const int total, const int startIndex, const int length)
   {
      double sum = 0.0;
      int count = 0;

      for(int i = startIndex; i < total && count < length; i++)
      {
         sum += MathAbs(rates[i].high - rates[i].low);
         count++;
      }

      if(count <= 0)
         return 0.0;

      return sum / (double)count;
   }

   bool IsBullishDisplacement(MqlRates &rates[], const int oldIndex, const double avgRange)
   {
      const int impulseIndex = oldIndex - 1;
      if(impulseIndex < 1)
         return false;

      const double range = MathAbs(rates[impulseIndex].high - rates[impulseIndex].low);
      return rates[impulseIndex].close > rates[impulseIndex].open &&
         (avgRange <= 0.0 || range >= avgRange * 1.1);
   }

   bool IsBearishDisplacement(MqlRates &rates[], const int oldIndex, const double avgRange)
   {
      const int impulseIndex = oldIndex - 1;
      if(impulseIndex < 1)
         return false;

      const double range = MathAbs(rates[impulseIndex].high - rates[impulseIndex].low);
      return rates[impulseIndex].close < rates[impulseIndex].open &&
         (avgRange <= 0.0 || range >= avgRange * 1.1);
   }

   bool IsBullishFvg(MqlRates &rates[], const int oldIndex, ApexZone &zone)
   {
      ApexResetZone(zone);

      if(oldIndex < 2)
         return false;

      const int newIndex = oldIndex - 2;

      if(rates[newIndex].low > rates[oldIndex].high)
      {
         ApexSetZone(zone, rates[oldIndex].high, rates[newIndex].low, "Bullish FVG");
         return true;
      }

      return false;
   }

   bool IsBearishFvg(MqlRates &rates[], const int oldIndex, ApexZone &zone)
   {
      ApexResetZone(zone);

      if(oldIndex < 2)
         return false;

      const int newIndex = oldIndex - 2;

      if(rates[newIndex].high < rates[oldIndex].low)
      {
         ApexSetZone(zone, rates[newIndex].high, rates[oldIndex].low, "Bearish FVG");
         return true;
      }

      return false;
   }

   bool FindPriorSweepLevel(
      MqlRates &rates[],
      const int total,
      const int sweepIndex,
      const int depth,
      const ENUM_APEX_DIRECTION direction,
      ApexSwing &sweptSwing
   )
   {
      ApexResetSwing(sweptSwing);

      for(int i = sweepIndex + depth + 1; i < total - depth; i++)
      {
         if(direction == APEX_DIR_LONG && IsSwingLow(rates, i, depth))
         {
            if(rates[sweepIndex].low < rates[i].low && rates[sweepIndex].close > rates[i].low)
            {
               sweptSwing.valid = true;
               sweptSwing.index = i;
               sweptSwing.price = rates[i].low;
               sweptSwing.time = rates[i].time;
               return true;
            }
         }

         if(direction == APEX_DIR_SHORT && IsSwingHigh(rates, i, depth))
         {
            if(rates[sweepIndex].high > rates[i].high && rates[sweepIndex].close < rates[i].high)
            {
               sweptSwing.valid = true;
               sweptSwing.index = i;
               sweptSwing.price = rates[i].high;
               sweptSwing.time = rates[i].time;
               return true;
            }
         }
      }

      return false;
   }

   bool FindFvgAfterSweep(
      MqlRates &rates[],
      const int total,
      const int sweepIndex,
      const ENUM_APEX_DIRECTION direction,
      const int maxBarsAfterSweep,
      int &fvgOldIndex,
      ApexZone &fvg
   )
   {
      fvgOldIndex = -1;
      ApexResetZone(fvg);

      const double avgRange = AverageRange(rates, total, sweepIndex + 1, 20);
      const int newestOldIndex = (sweepIndex - maxBarsAfterSweep) < 3 ? 3 : (sweepIndex - maxBarsAfterSweep);

      for(int oldIndex = sweepIndex - 1; oldIndex >= newestOldIndex; oldIndex--)
      {
         if(direction == APEX_DIR_LONG)
         {
            if(IsBullishFvg(rates, oldIndex, fvg) && IsBullishDisplacement(rates, oldIndex, avgRange))
            {
               fvgOldIndex = oldIndex;
               return true;
            }
         }

         if(direction == APEX_DIR_SHORT)
         {
            if(IsBearishFvg(rates, oldIndex, fvg) && IsBearishDisplacement(rates, oldIndex, avgRange))
            {
               fvgOldIndex = oldIndex;
               return true;
            }
         }
      }

      return false;
   }

   bool FindOrderBlock(
      MqlRates &rates[],
      const int total,
      const int sweepIndex,
      const int fvgOldIndex,
      const ENUM_APEX_DIRECTION direction,
      int &obIndex,
      ApexZone &ob
   )
   {
      obIndex = -1;
      ApexResetZone(ob);

      for(int i = fvgOldIndex + 1; i <= sweepIndex && i < total; i++)
      {
         if(direction == APEX_DIR_LONG && rates[i].close < rates[i].open)
         {
            obIndex = i;
            ApexSetZone(ob, rates[i].low, rates[i].high, "Bullish order block");
            return true;
         }

         if(direction == APEX_DIR_SHORT && rates[i].close > rates[i].open)
         {
            obIndex = i;
            ApexSetZone(ob, rates[i].low, rates[i].high, "Bearish order block");
            return true;
         }
      }

      return false;
   }

   bool IsOrderBlockMitigated(
      MqlRates &rates[],
      const int fvgOldIndex,
      const ApexZone &ob
   )
   {
      if(!ob.valid)
         return true;

      for(int i = fvgOldIndex - 3; i >= 3; i--)
      {
         if(rates[i].low <= ob.high && rates[i].high >= ob.low)
            return true;
      }

      return false;
   }

   bool BuildEntryZone(const ApexZone &fvg, const ApexZone &ob, ApexZone &entryZone)
   {
      ApexResetZone(entryZone);

      if(!fvg.valid || !ob.valid)
         return false;

      if(ApexZonesOverlap(fvg, ob))
      {
         ApexSetZone(entryZone, MathMax(fvg.low, ob.low), MathMin(fvg.high, ob.high), "OB/FVG overlap");
         return true;
      }

      return false;
   }

   bool PriceTooDeep(
      const ENUM_APEX_DIRECTION direction,
      const double price,
      const ApexZone &fvg,
      const double maxFillPct
   )
   {
      if(!fvg.valid || maxFillPct <= 0.0)
         return false;

      const double size = fvg.high - fvg.low;
      if(size <= 0.0)
         return false;

      if(direction == APEX_DIR_LONG)
      {
         if(price > fvg.high)
            return false;

         const double filledPct = (fvg.high - price) / size * 100.0;
         return filledPct > maxFillPct;
      }

      if(direction == APEX_DIR_SHORT)
      {
         if(price < fvg.low)
            return false;

         const double filledPct = (price - fvg.low) / size * 100.0;
         return filledPct > maxFillPct;
      }

      return false;
   }

   bool BullishTrigger(MqlRates &rates[], const ApexZone &entryZone, const ApexZone &ob, string &triggerText)
   {
      triggerText = "No confirmation candle";

      if(!entryZone.valid || !ob.valid)
         return false;

      const bool touchedZone = rates[1].low <= entryZone.high && rates[1].high >= entryZone.low;
      const bool closeAboveOb = rates[1].close > ob.high;

      const bool engulfing =
         rates[2].close < rates[2].open &&
         rates[1].close > rates[1].open &&
         rates[1].close > rates[2].open &&
         rates[1].open <= rates[2].close;

      const double body = MathAbs(rates[1].close - rates[1].open);
      const double lowerWick = MathMin(rates[1].open, rates[1].close) - rates[1].low;
      const double upperWick = rates[1].high - MathMax(rates[1].open, rates[1].close);
      const bool pinBar = rates[1].close > rates[1].open && lowerWick >= body * 2.0 && lowerWick > upperWick;

      if(touchedZone && closeAboveOb && engulfing)
      {
         triggerText = "Bullish engulfing close above OB";
         return true;
      }

      if(touchedZone && closeAboveOb && pinBar)
      {
         triggerText = "Bullish pin bar close above OB";
         return true;
      }

      return false;
   }

   bool BearishTrigger(MqlRates &rates[], const ApexZone &entryZone, const ApexZone &ob, string &triggerText)
   {
      triggerText = "No confirmation candle";

      if(!entryZone.valid || !ob.valid)
         return false;

      const bool touchedZone = rates[1].low <= entryZone.high && rates[1].high >= entryZone.low;
      const bool closeBelowOb = rates[1].close < ob.low;

      const bool engulfing =
         rates[2].close > rates[2].open &&
         rates[1].close < rates[1].open &&
         rates[1].close < rates[2].open &&
         rates[1].open >= rates[2].close;

      const double body = MathAbs(rates[1].close - rates[1].open);
      const double lowerWick = MathMin(rates[1].open, rates[1].close) - rates[1].low;
      const double upperWick = rates[1].high - MathMax(rates[1].open, rates[1].close);
      const bool pinBar = rates[1].close < rates[1].open && upperWick >= body * 2.0 && upperWick > lowerWick;

      if(touchedZone && closeBelowOb && engulfing)
      {
         triggerText = "Bearish engulfing close below OB";
         return true;
      }

      if(touchedZone && closeBelowOb && pinBar)
      {
         triggerText = "Bearish pin bar close below OB";
         return true;
      }

      return false;
   }

   bool FindOpposingLiquidityTarget(
      MqlRates &rates[],
      const int total,
      const int depth,
      const ENUM_APEX_DIRECTION direction,
      const double entryPrice,
      double &target
   )
   {
      target = 0.0;

      for(int i = depth + 1; i < total - depth; i++)
      {
         if(direction == APEX_DIR_LONG && IsSwingHigh(rates, i, depth) && rates[i].high > entryPrice)
         {
            target = rates[i].high;
            return true;
         }

         if(direction == APEX_DIR_SHORT && IsSwingLow(rates, i, depth) && rates[i].low < entryPrice)
         {
            target = rates[i].low;
            return true;
         }
      }

      return false;
   }

   void AssignTargets(
      MqlRates &rates[],
      const int total,
      const int depth,
      const string symbol,
      ApexSmcSignal &signal
   )
   {
      const double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
      const double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
      const double entryPrice = signal.direction == APEX_DIR_LONG ? ask : bid;
      double target = 0.0;

      if(signal.direction == APEX_DIR_LONG)
      {
         signal.stopLoss = ApexNormalizePrice(symbol, signal.sweepWick);

         if(FindOpposingLiquidityTarget(rates, total, depth, signal.direction, entryPrice, target))
            signal.takeProfit1 = ApexNormalizePrice(symbol, target);
         else
            signal.takeProfit1 = ApexNormalizePrice(symbol, entryPrice + (entryPrice - signal.stopLoss));

         signal.takeProfit2 = ApexNormalizePrice(symbol, entryPrice + (entryPrice - signal.stopLoss) * 2.0);
      }

      if(signal.direction == APEX_DIR_SHORT)
      {
         signal.stopLoss = ApexNormalizePrice(symbol, signal.sweepWick);

         if(FindOpposingLiquidityTarget(rates, total, depth, signal.direction, entryPrice, target))
            signal.takeProfit1 = ApexNormalizePrice(symbol, target);
         else
            signal.takeProfit1 = ApexNormalizePrice(symbol, entryPrice - (signal.stopLoss - entryPrice));

         signal.takeProfit2 = ApexNormalizePrice(symbol, entryPrice - (signal.stopLoss - entryPrice) * 2.0);
      }
   }

   bool FindInstitutionalSetup(
      MqlRates &rates[],
      const int total,
      const string symbol,
      const int depth,
      const ENUM_APEX_DIRECTION direction,
      const int maxBarsAfterSweep,
      const double maxFvgFillPct,
      ApexSmcSignal &signal
   )
   {
      ApexSwing sweptSwing;
      ApexResetSwing(sweptSwing);

      const int maxSweepIndex = (total - depth - 3) < 80 ? (total - depth - 3) : 80;
      const int minSweepIndex = (depth + 4) > 8 ? (depth + 4) : 8;

      for(int sweepIndex = minSweepIndex; sweepIndex <= maxSweepIndex; sweepIndex++)
      {
         if(!FindPriorSweepLevel(rates, total, sweepIndex, depth, direction, sweptSwing))
            continue;

         int fvgOldIndex = -1;
         ApexZone fvg;
         ApexResetZone(fvg);

         if(!FindFvgAfterSweep(rates, total, sweepIndex, direction, maxBarsAfterSweep, fvgOldIndex, fvg))
            continue;

         int obIndex = -1;
         ApexZone ob;
         ApexResetZone(ob);

         const bool hasOb = FindOrderBlock(rates, total, sweepIndex, fvgOldIndex, direction, obIndex, ob);

         signal.valid = true;
         signal.direction = direction;
         signal.liquiditySweepConfirmed = true;
         signal.sweepLevel = sweptSwing.price;
         signal.sweepTime = rates[sweepIndex].time;
         signal.sweepWick = direction == APEX_DIR_LONG ? rates[sweepIndex].low : rates[sweepIndex].high;
         signal.fvgPresent = true;
         signal.fvg = fvg;
         signal.setupTime = rates[fvgOldIndex - 2].time;

         if(hasOb)
         {
            signal.ob = ob;
            signal.obMitigated = IsOrderBlockMitigated(rates, fvgOldIndex, ob);
            signal.obConfluence = !signal.obMitigated && BuildEntryZone(fvg, ob, signal.entryZone);
         }

         const double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
         const double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
         const double price = direction == APEX_DIR_LONG ? bid : ask;
         signal.priceTooDeepIntoFvg = PriceTooDeep(direction, price, fvg, maxFvgFillPct);

         if(direction == APEX_DIR_LONG)
            signal.triggerConfirmed = BullishTrigger(rates, signal.entryZone, signal.ob, signal.triggerText);

         if(direction == APEX_DIR_SHORT)
            signal.triggerConfirmed = BearishTrigger(rates, signal.entryZone, signal.ob, signal.triggerText);

         AssignTargets(rates, total, depth, symbol, signal);
         return true;
      }

      return false;
   }

public:
   bool BuildSignal(
      const string symbol,
      const ENUM_TIMEFRAMES timeframe,
      const int lookbackBars,
      const int swingDepth,
      const int maxBarsAfterSweep,
      const double maxFvgFillPct,
      ApexSmcSignal &signal
   )
   {
      ApexResetSmcSignal(signal);

      MqlRates rates[];
      ArraySetAsSeries(rates, true);
      const int requestedBars = lookbackBars < 100 ? 100 : lookbackBars;
      const int copied = CopyRates(symbol, timeframe, 0, requestedBars, rates);

      const int minimumBars = (swingDepth * 6) > 50 ? (swingDepth * 6) : 50;
      if(copied < minimumBars)
      {
         signal.rejectionReason = "insufficient candles for SMC scan";
         return false;
      }

      ApexSwing latestHigh;
      ApexSwing previousHigh;
      ApexSwing latestLow;
      ApexSwing previousLow;
      FindLatestSwings(rates, copied, swingDepth, latestHigh, previousHigh, latestLow, previousLow);

      if(!latestHigh.valid || !previousHigh.valid || !latestLow.valid || !previousLow.valid)
      {
         signal.rejectionReason = "insufficient confirmed swings";
         return false;
      }

      ENUM_APEX_DIRECTION structureDirection = APEX_DIR_NONE;

      if(latestHigh.price > previousHigh.price && latestLow.price > previousLow.price)
      {
         structureDirection = APEX_DIR_LONG;
         signal.marketStructureText =
            "Bullish HH/HL - HH " + DoubleToString(latestHigh.price, _Digits) +
            " / HL " + DoubleToString(latestLow.price, _Digits);
      }
      else if(latestHigh.price < previousHigh.price && latestLow.price < previousLow.price)
      {
         structureDirection = APEX_DIR_SHORT;
         signal.marketStructureText =
            "Bearish LH/LL - LH " + DoubleToString(latestHigh.price, _Digits) +
            " / LL " + DoubleToString(latestLow.price, _Digits);
      }
      else
      {
         signal.consolidation = true;
         signal.marketStructureText = "Mixed swings - consolidation/range risk";
         signal.rejectionReason = "market structure is not directional";
         return false;
      }

      signal.consolidation = false;
      signal.marketStructureAligned = true;
      signal.direction = structureDirection;

      if(!FindInstitutionalSetup(
            rates,
            copied,
            symbol,
            swingDepth,
            structureDirection,
            maxBarsAfterSweep,
            maxFvgFillPct,
            signal
         ))
      {
         signal.direction = structureDirection;
         signal.valid = false;
         signal.rejectionReason = "no liquidity sweep plus displacement/FVG sequence found";
      }

      signal.marketStructureAligned = true;
      signal.consolidation = false;

      return signal.valid;
   }
};

#endif
