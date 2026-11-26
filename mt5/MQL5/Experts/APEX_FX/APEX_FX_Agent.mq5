#property strict
#property version   "1.00"
#property description "APEX-FX institutional-style MT5 agent: macro/COT manual inputs, SMC scan, risk-first execution gates."

#include <Trade\Trade.mqh>
#include "..\..\Include\APEX_FX\ApexFxTypes.mqh"
#include "..\..\Include\APEX_FX\ApexFxRisk.mqh"
#include "..\..\Include\APEX_FX\ApexFxSMC.mqh"
#include "..\..\Include\APEX_FX\ApexFxReport.mqh"

input group "Execution"
input bool            InpAllowLiveTrading          = false;
input int             InpMagicNumber               = 20260503;
input ENUM_TIMEFRAMES InpSignalTimeframe           = PERIOD_H1;
input int             InpDeviationPoints           = 20;
input bool            InpOnePositionPerSymbol      = true;

input group "SMC Scan"
input int             InpLookbackBars              = 250;
input int             InpSwingDepth                = 2;
input int             InpMaxBarsAfterSweep         = 8;
input double          InpMaxFvgFillPct             = 50.0;

input group "Macro Manual Layer"
input ENUM_APEX_DIRECTION InpRateDifferentialBias  = APEX_DIR_NONE;
input ENUM_APEX_DIRECTION InpRelativeStrengthBias  = APEX_DIR_NONE;
input ENUM_APEX_DIRECTION InpYieldCurveBias        = APEX_DIR_NONE;
input string              InpYieldCurveNote        = "Manual input required";
input int                 InpMacroDataAgeDays      = 0;

input group "Sentiment Manual Layer"
input int                 InpCotCommercialIndex6M  = 50;
input int                 InpCotCommercialIndex12M = 50;
input ENUM_APEX_DIRECTION InpLargeSpecFadeBias     = APEX_DIR_NONE;
input ENUM_APEX_DIRECTION InpOpenInterestBias      = APEX_DIR_NONE;
input string              InpSentimentNote         = "Manual COT/OI input required";
input int                 InpCotDataAgeDays        = 0;

input group "Risk Governance"
input double          InpAccountBalanceOverride    = 0.0;
input double          InpRiskPerTradePct           = 1.0;
input double          InpMaxDailyDrawdownPct       = 3.0;
input double          InpMaxPortfolioDrawdownPct   = 10.0;
input int             InpMaxOpenTrades             = 3;
input int             InpMaxCorrelatedPairs        = 1;
input bool            InpUseFractionalKelly        = true;
input double          InpModelWinRate              = 0.50;
input double          InpAverageRewardRisk         = 2.0;
input double          InpKellyFraction             = 0.25;

input group "Execution Filters"
input bool            InpHighImpactNewsBlackout    = false;
input bool            InpUseSessionFilter          = true;
input bool            InpAllowAsianJpyCarrySetups  = false;
input int             InpSpreadLookbackBars        = 120;
input double          InpSpreadMultiplierLimit     = 3.0;

CTrade           g_trade;
CApexRiskManager g_risk;
CApexSmcAnalyzer g_smc;

datetime g_lastSignalBarTime = 0;
double   g_dayStartEquity = 0.0;
int      g_dayKey = 0;
string   g_lastReport = "";

int CurrentUtcDayKey()
{
   MqlDateTime parts;
   TimeToStruct(TimeGMT(), parts);
   return parts.year * 1000 + parts.day_of_year;
}

void RefreshDailyEquityAnchor()
{
   const int dayKey = CurrentUtcDayKey();

   if(dayKey != g_dayKey || g_dayStartEquity <= 0.0)
   {
      g_dayKey = dayKey;
      g_dayStartEquity = AccountInfoDouble(ACCOUNT_EQUITY);
   }
}

bool HasNewClosedSignalBar()
{
   const datetime closedBarTime = iTime(_Symbol, InpSignalTimeframe, 1);

   if(closedBarTime <= 0)
      return false;

   if(closedBarTime == g_lastSignalBarTime)
      return false;

   g_lastSignalBarTime = closedBarTime;
   return true;
}

bool BiasConfirms(const ENUM_APEX_DIRECTION candidate, const ENUM_APEX_DIRECTION bias)
{
   return candidate != APEX_DIR_NONE && candidate == bias;
}

int MacroScore(const ENUM_APEX_DIRECTION candidate)
{
   int score = 0;

   if(BiasConfirms(candidate, InpRateDifferentialBias))
      score++;

   if(BiasConfirms(candidate, InpRelativeStrengthBias))
      score++;

   if(BiasConfirms(candidate, InpYieldCurveBias))
      score++;

   return score;
}

int SmcScore(const ApexSmcSignal &signal)
{
   int score = 0;

   if(signal.marketStructureAligned && !signal.consolidation)
      score++;

   if(signal.liquiditySweepConfirmed)
      score++;

   if(signal.fvgPresent)
      score++;

   if(signal.obConfluence)
      score++;

   return score;
}

bool CotConfirms(const ENUM_APEX_DIRECTION candidate)
{
   if(candidate == APEX_DIR_LONG)
      return InpCotCommercialIndex6M >= 75 && InpCotCommercialIndex12M >= 75;

   if(candidate == APEX_DIR_SHORT)
      return InpCotCommercialIndex6M <= 25 && InpCotCommercialIndex12M <= 25;

   return false;
}

int SentimentScore(const ENUM_APEX_DIRECTION candidate)
{
   int score = 0;

   if(CotConfirms(candidate))
      score++;

   if(BiasConfirms(candidate, InpLargeSpecFadeBias))
      score++;

   if(BiasConfirms(candidate, InpOpenInterestBias))
      score++;

   return score;
}

bool SessionAllowsExecution(const string symbol, const datetime utcTime)
{
   if(!InpUseSessionFilter)
      return true;

   if(ApexIsPreferredExecutionSession(utcTime))
      return true;

   if(InpAllowAsianJpyCarrySetups && ApexSymbolContainsCurrency(symbol, "JPY") && ApexSessionName(utcTime) == "Asian")
      return true;

   return false;
}

string DataFreshnessFlags()
{
   string flags = "";

   if(InpCotDataAgeDays > 7)
      flags = ApexAppendReason(flags, "[DATA STALE — CONFIRM BEFORE ACTING] COT data older than 7 days");

   if(InpMacroDataAgeDays > 30)
      flags = ApexAppendReason(flags, "[DATA STALE — CONFIRM BEFORE ACTING] macro data older than 30 days");

   return flags;
}

string BuildExecutionFlags(
   const int totalScore,
   const ApexSmcSignal &signal,
   const bool sessionAllowed,
   const bool geometryValid
)
{
   string flags = DataFreshnessFlags();

   if(totalScore < 7)
      flags = ApexAppendReason(flags, "confluence score below 7/10");

   if(InpHighImpactNewsBlackout)
      flags = ApexAppendReason(flags, "manual high-impact news blackout active");

   if(!sessionAllowed)
      flags = ApexAppendReason(flags, "outside preferred London open or NY/London overlap window");

   if(signal.consolidation)
      flags = ApexAppendReason(flags, "market structure consolidation");

   if(signal.obMitigated)
      flags = ApexAppendReason(flags, "order block previously mitigated");

   if(signal.priceTooDeepIntoFvg)
      flags = ApexAppendReason(flags, "price already moved beyond configured FVG fill threshold");

   if(!signal.obConfluence)
      flags = ApexAppendReason(flags, "no valid OB/FVG confluence entry zone");

   if(!signal.triggerConfirmed)
      flags = ApexAppendReason(flags, "awaiting confirmation candle");

   if(!geometryValid)
      flags = ApexAppendReason(flags, "invalid stop/target geometry");

   if(!InpAllowLiveTrading)
      flags = ApexAppendReason(flags, "paper mode active - live order not sent");

   return flags;
}

bool TradeGeometryValid(const ENUM_APEX_DIRECTION direction, const double entryPrice, const ApexSmcSignal &signal)
{
   if(direction == APEX_DIR_LONG)
      return signal.stopLoss < entryPrice && signal.takeProfit1 > entryPrice && signal.takeProfit2 > entryPrice;

   if(direction == APEX_DIR_SHORT)
      return signal.stopLoss > entryPrice && signal.takeProfit1 < entryPrice && signal.takeProfit2 < entryPrice;

   return false;
}

string BuildNarrative(
   const ENUM_APEX_DIRECTION candidate,
   const int macroScore,
   const int smcScore,
   const int sentimentScore,
   const ApexSmcSignal &signal
)
{
   string thesis = "";

   thesis += "The candidate bias is " + ApexDirectionToString(candidate) +
      " with macro " + IntegerToString(macroScore) + "/3, SMC " + IntegerToString(smcScore) +
      "/4, and sentiment " + IntegerToString(sentimentScore) + "/3. ";

   if(signal.liquiditySweepConfirmed && signal.fvgPresent)
      thesis += "The chart footprint shows a liquidity sweep followed by displacement into an FVG, with invalidation beyond the sweep wick. ";
   else
      thesis += "The institutional footprint is incomplete, so survival-first sizing requires standing aside. ";

   thesis += "Druckenmiller liquidity primacy is applied by requiring displacement after a sweep, while the Jones rule is enforced by never adding to losers.";

   return thesis;
}

string RegimeNote(const ApexSmcSignal &signal)
{
   if(InpHighImpactNewsBlackout)
      return "news-driven";

   if(signal.consolidation)
      return "ranging";

   return "trending";
}

double CurrentEntryPrice(const ENUM_APEX_DIRECTION direction)
{
   if(direction == APEX_DIR_LONG)
      return SymbolInfoDouble(_Symbol, SYMBOL_ASK);

   if(direction == APEX_DIR_SHORT)
      return SymbolInfoDouble(_Symbol, SYMBOL_BID);

   return 0.0;
}

void StoreTp1ForOpenPosition(const double tp1)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      const ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;

      if(PositionGetString(POSITION_SYMBOL) != _Symbol)
         continue;

      if((int)PositionGetInteger(POSITION_MAGIC) != InpMagicNumber)
         continue;

      const string ticketText = IntegerToString((long)ticket);
      const string key = "APEXFX_TP1_" + ticketText;
      const string partialKey = "APEXFX_PARTIAL_" + ticketText;

      if(!GlobalVariableCheck(key))
         GlobalVariableSet(key, tp1);

      if(!GlobalVariableCheck(partialKey))
         GlobalVariableSet(partialKey, 0.0);
   }
}

double NormalizeCloseVolume(const string symbol, const double volume)
{
   const double minVolume = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   const double step = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);

   if(step <= 0.0 || volume < minVolume)
      return 0.0;

   double normalized = MathFloor(volume / step) * step;

   int digits = 0;
   double scaledStep = step;
   while(digits < 8 && MathAbs(scaledStep - MathRound(scaledStep)) > 0.00000001)
   {
      scaledStep *= 10.0;
      digits++;
   }

   return NormalizeDouble(normalized, digits);
}

void ManageOpenPositions()
{
   g_trade.SetExpertMagicNumber(InpMagicNumber);
   g_trade.SetDeviationInPoints(InpDeviationPoints);

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      const ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;

      if((int)PositionGetInteger(POSITION_MAGIC) != InpMagicNumber)
         continue;

      const string symbol = PositionGetString(POSITION_SYMBOL);
      const string ticketText = IntegerToString((long)ticket);
      const string key = "APEXFX_TP1_" + ticketText;
      const string partialKey = "APEXFX_PARTIAL_" + ticketText;

      if(!GlobalVariableCheck(key))
         continue;

      if(GlobalVariableCheck(partialKey) && GlobalVariableGet(partialKey) >= 1.0)
         continue;

      const double tp1 = GlobalVariableGet(key);
      const ENUM_POSITION_TYPE type = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      const double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
      const double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
      const bool tp1Hit = (type == POSITION_TYPE_BUY && bid >= tp1) || (type == POSITION_TYPE_SELL && ask <= tp1);

      if(!tp1Hit)
         continue;

      const double volume = PositionGetDouble(POSITION_VOLUME);
      const double closeVolume = NormalizeCloseVolume(symbol, volume * 0.5);

      if(closeVolume <= 0.0 || closeVolume >= volume)
         continue;

      if(g_trade.PositionClosePartial(ticket, closeVolume))
      {
         const double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
         const double takeProfit = PositionGetDouble(POSITION_TP);
         g_trade.PositionModify(ticket, openPrice, takeProfit);
         GlobalVariableSet(partialKey, 1.0);
         Print("APEX-FX: TP1 partial close executed for ticket ", ticket, ". Stop moved to break-even.");
      }
   }
}

bool ExecuteSignal(
   const ApexSmcSignal &signal,
   const double lots,
   const double entryPrice
)
{
   if(lots <= 0.0)
   {
      Print("APEX-FX: order skipped because calculated lot size is zero.");
      return false;
   }

   g_trade.SetExpertMagicNumber(InpMagicNumber);
   g_trade.SetDeviationInPoints(InpDeviationPoints);

   const string comment = "APEX-FX " + ApexDirectionToString(signal.direction);
   bool sent = false;

   if(signal.direction == APEX_DIR_LONG)
      sent = g_trade.Buy(lots, _Symbol, 0.0, signal.stopLoss, signal.takeProfit2, comment);

   if(signal.direction == APEX_DIR_SHORT)
      sent = g_trade.Sell(lots, _Symbol, 0.0, signal.stopLoss, signal.takeProfit2, comment);

   if(sent)
   {
      StoreTp1ForOpenPosition(signal.takeProfit1);
      Print("APEX-FX: live order sent at reference price ", DoubleToString(entryPrice, _Digits), ".");
      return true;
   }

   Print("APEX-FX: order send failed. Retcode=", g_trade.ResultRetcode(), " ", g_trade.ResultRetcodeDescription());
   return false;
}

void EvaluateSignal()
{
   RefreshDailyEquityAnchor();

   ApexSmcSignal smcSignal;
   g_smc.BuildSignal(
      _Symbol,
      InpSignalTimeframe,
      InpLookbackBars,
      InpSwingDepth,
      InpMaxBarsAfterSweep,
      InpMaxFvgFillPct,
      smcSignal
   );

   const ENUM_APEX_DIRECTION candidate = smcSignal.direction;
   const int macroScore = MacroScore(candidate);
   const int smcScore = SmcScore(smcSignal);
   const int sentimentScore = SentimentScore(candidate);
   const int totalScore = macroScore + smcScore + sentimentScore;

   const datetime utcTime = TimeGMT();
   const string session = ApexSessionName(utcTime);
   const bool sessionAllowed = SessionAllowsExecution(_Symbol, utcTime);
   const double entryPrice = CurrentEntryPrice(candidate);
   const bool geometryValid = TradeGeometryValid(candidate, entryPrice, smcSignal);

   ApexRiskState riskState;
   g_risk.BuildRiskState(
      InpMagicNumber,
      _Symbol,
      candidate,
      g_dayStartEquity,
      InpMaxDailyDrawdownPct,
      InpMaxPortfolioDrawdownPct,
      InpMaxOpenTrades,
      InpMaxCorrelatedPairs,
      InpOnePositionPerSymbol,
      InpSpreadLookbackBars,
      InpSpreadMultiplierLimit,
      riskState
   );

   const double effectiveRiskPct = g_risk.EffectiveRiskPct(
      InpRiskPerTradePct,
      InpUseFractionalKelly,
      InpModelWinRate,
      InpAverageRewardRisk,
      InpKellyFraction
   );

   const double accountBase = g_risk.AccountBase(InpAccountBalanceOverride);
   const double lots = g_risk.CalculateLots(
      _Symbol,
      InpAccountBalanceOverride,
      effectiveRiskPct,
      entryPrice,
      smcSignal.stopLoss
   );

   const bool hardRejected =
      totalScore < 7 ||
      InpHighImpactNewsBlackout ||
      riskState.halted ||
      !sessionAllowed ||
      smcSignal.consolidation ||
      smcSignal.obMitigated ||
      smcSignal.priceTooDeepIntoFvg ||
      !smcSignal.obConfluence ||
      !geometryValid;

   const bool executable =
      !hardRejected &&
      smcSignal.triggerConfirmed &&
      InpAllowLiveTrading &&
      lots > 0.0;

   ENUM_APEX_DIRECTION reportDirection = APEX_DIR_NONE;
   if(totalScore >= 7 && !hardRejected)
      reportDirection = candidate;

   const string executionFlags = BuildExecutionFlags(totalScore, smcSignal, sessionAllowed, geometryValid);
   const string narrative = BuildNarrative(candidate, macroScore, smcScore, sentimentScore, smcSignal);
   const bool includeTradeParameters = totalScore >= 7 && smcSignal.entryZone.valid && geometryValid;

   g_lastReport = ApexBuildSignalReport(
      _Symbol,
      reportDirection,
      utcTime,
      session,
      totalScore,
      macroScore,
      smcScore,
      sentimentScore,
      InpRateDifferentialBias,
      InpRelativeStrengthBias,
      InpYieldCurveBias,
      InpYieldCurveNote,
      smcSignal,
      InpCotCommercialIndex6M,
      InpCotCommercialIndex12M,
      InpLargeSpecFadeBias,
      InpOpenInterestBias,
      InpSentimentNote,
      includeTradeParameters,
      entryPrice,
      lots,
      effectiveRiskPct,
      accountBase,
      riskState,
      executionFlags,
      RegimeNote(smcSignal),
      narrative
   );

   Print(g_lastReport);
   Comment(g_lastReport);

   if(executable)
      ExecuteSignal(smcSignal, lots, entryPrice);
}

int OnInit()
{
   g_trade.SetExpertMagicNumber(InpMagicNumber);
   g_trade.SetDeviationInPoints(InpDeviationPoints);
   RefreshDailyEquityAnchor();
   Print("APEX-FX Agent initialized on ", _Symbol, " ", ApexTimeframeToString(InpSignalTimeframe), ". Live trading=", InpAllowLiveTrading ? "true" : "false");
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   Comment("");
   Print("APEX-FX Agent deinitialized. Reason=", reason);
}

void OnTick()
{
   ManageOpenPositions();

   if(!HasNewClosedSignalBar())
      return;

   EvaluateSignal();
}
