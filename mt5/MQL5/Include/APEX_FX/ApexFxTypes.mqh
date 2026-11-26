#ifndef __APEX_FX_TYPES_MQH__
#define __APEX_FX_TYPES_MQH__

enum ENUM_APEX_DIRECTION
{
   APEX_DIR_SHORT = -1,
   APEX_DIR_NONE  = 0,
   APEX_DIR_LONG  = 1
};

struct ApexZone
{
   bool   valid;
   double low;
   double high;
   string label;
};

struct ApexSmcSignal
{
   bool                valid;
   ENUM_APEX_DIRECTION direction;
   string              rejectionReason;
   string              marketStructureText;
   bool                marketStructureAligned;
   bool                consolidation;
   bool                liquiditySweepConfirmed;
   double              sweepLevel;
   double              sweepWick;
   datetime            sweepTime;
   bool                fvgPresent;
   ApexZone            fvg;
   bool                obConfluence;
   ApexZone            ob;
   ApexZone            entryZone;
   bool                obMitigated;
   bool                priceTooDeepIntoFvg;
   bool                triggerConfirmed;
   string              triggerText;
   double              stopLoss;
   double              takeProfit1;
   double              takeProfit2;
   datetime            setupTime;
};

struct ApexRiskState
{
   bool   halted;
   string reason;
   double dailyDrawdownPct;
   double portfolioDrawdownPct;
   int    consecutiveLosses;
   int    openTrades;
   bool   correlatedExposure;
   string correlatedCurrency;
   bool   spreadWide;
   double currentSpreadPoints;
   double averageSpreadPoints;
};

string ApexDirectionToString(const ENUM_APEX_DIRECTION direction)
{
   if(direction == APEX_DIR_LONG)
      return "LONG";
   if(direction == APEX_DIR_SHORT)
      return "SHORT";
   return "NO TRADE";
}

string ApexBiasToText(const ENUM_APEX_DIRECTION bias)
{
   if(bias == APEX_DIR_LONG)
      return "long bias";
   if(bias == APEX_DIR_SHORT)
      return "short bias";
   return "neutral";
}

double ApexPipSize(const string symbol)
{
   const int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   const double point = SymbolInfoDouble(symbol, SYMBOL_POINT);

   if(digits == 3 || digits == 5)
      return point * 10.0;

   return point;
}

double ApexPipsBetween(const string symbol, const double priceA, const double priceB)
{
   const double pip = ApexPipSize(symbol);
   if(pip <= 0.0)
      return 0.0;

   return MathAbs(priceA - priceB) / pip;
}

double ApexNormalizePrice(const string symbol, const double price)
{
   const int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   return NormalizeDouble(price, digits);
}

void ApexResetZone(ApexZone &zone)
{
   zone.valid = false;
   zone.low = 0.0;
   zone.high = 0.0;
   zone.label = "";
}

void ApexSetZone(ApexZone &zone, const double low, const double high, const string label)
{
   zone.valid = true;
   zone.low = MathMin(low, high);
   zone.high = MathMax(low, high);
   zone.label = label;
}

bool ApexZonesOverlap(const ApexZone &left, const ApexZone &right)
{
   if(!left.valid || !right.valid)
      return false;

   return left.low <= right.high && right.low <= left.high;
}

void ApexResetSmcSignal(ApexSmcSignal &signal)
{
   signal.valid = false;
   signal.direction = APEX_DIR_NONE;
   signal.rejectionReason = "";
   signal.marketStructureText = "Unresolved";
   signal.marketStructureAligned = false;
   signal.consolidation = true;
   signal.liquiditySweepConfirmed = false;
   signal.sweepLevel = 0.0;
   signal.sweepWick = 0.0;
   signal.sweepTime = 0;
   signal.fvgPresent = false;
   ApexResetZone(signal.fvg);
   signal.obConfluence = false;
   ApexResetZone(signal.ob);
   ApexResetZone(signal.entryZone);
   signal.obMitigated = false;
   signal.priceTooDeepIntoFvg = false;
   signal.triggerConfirmed = false;
   signal.triggerText = "No confirmation candle";
   signal.stopLoss = 0.0;
   signal.takeProfit1 = 0.0;
   signal.takeProfit2 = 0.0;
   signal.setupTime = 0;
}

void ApexResetRiskState(ApexRiskState &state)
{
   state.halted = false;
   state.reason = "";
   state.dailyDrawdownPct = 0.0;
   state.portfolioDrawdownPct = 0.0;
   state.consecutiveLosses = 0;
   state.openTrades = 0;
   state.correlatedExposure = false;
   state.correlatedCurrency = "";
   state.spreadWide = false;
   state.currentSpreadPoints = 0.0;
   state.averageSpreadPoints = 0.0;
}

string ApexTimeframeToString(const ENUM_TIMEFRAMES timeframe)
{
   switch(timeframe)
   {
      case PERIOD_M1:  return "M1";
      case PERIOD_M5:  return "M5";
      case PERIOD_M15: return "M15";
      case PERIOD_M30: return "M30";
      case PERIOD_H1:  return "H1";
      case PERIOD_H4:  return "H4";
      case PERIOD_D1:  return "D1";
      case PERIOD_W1:  return "W1";
      case PERIOD_MN1: return "MN1";
      default:         return IntegerToString((int)timeframe);
   }
}

string ApexSessionName(const datetime gmtTime)
{
   MqlDateTime parts;
   TimeToStruct(gmtTime, parts);

   if(parts.hour >= 13 && parts.hour < 16)
      return "Overlap";

   if(parts.hour >= 7 && parts.hour < 13)
      return "London";

   if(parts.hour >= 16 && parts.hour < 22)
      return "NY";

   return "Asian";
}

bool ApexIsPreferredExecutionSession(const datetime gmtTime)
{
   MqlDateTime parts;
   TimeToStruct(gmtTime, parts);
   return (parts.hour >= 7 && parts.hour < 9) || (parts.hour >= 13 && parts.hour < 16);
}

bool ApexSymbolContainsCurrency(const string symbol, const string currency)
{
   return StringFind(symbol, currency) >= 0;
}

string ApexBaseCurrency(const string symbol)
{
   if(StringLen(symbol) < 3)
      return "";

   return StringSubstr(symbol, 0, 3);
}

string ApexQuoteCurrency(const string symbol)
{
   if(StringLen(symbol) < 6)
      return "";

   return StringSubstr(symbol, 3, 3);
}

string ApexFormatPrice(const string symbol, const double price)
{
   const int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   return DoubleToString(price, digits);
}

string ApexAppendReason(const string existingReason, const string newReason)
{
   if(newReason == "")
      return existingReason;

   if(existingReason == "")
      return newReason;

   return existingReason + "; " + newReason;
}

#endif
