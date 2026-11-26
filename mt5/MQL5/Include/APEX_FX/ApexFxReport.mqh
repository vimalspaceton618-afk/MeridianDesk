#ifndef __APEX_FX_REPORT_MQH__
#define __APEX_FX_REPORT_MQH__

#include "ApexFxTypes.mqh"

string ApexFormatZone(const string symbol, const ApexZone &zone)
{
   if(!zone.valid)
      return "N/A";

   return ApexFormatPrice(symbol, zone.low) + " - " + ApexFormatPrice(symbol, zone.high);
}

string ApexYesNo(const bool value)
{
   return value ? "Yes" : "No";
}

string ApexConfirmingText(const ENUM_APEX_DIRECTION direction, const ENUM_APEX_DIRECTION bias)
{
   if(direction == APEX_DIR_NONE || bias == APEX_DIR_NONE)
      return ApexBiasToText(bias);

   if(direction == bias)
      return ApexBiasToText(bias) + " - confirms";

   return ApexBiasToText(bias) + " - conflicts";
}

string ApexBuildSignalReport(
   const string symbol,
   const ENUM_APEX_DIRECTION reportDirection,
   const datetime utcTime,
   const string session,
   const int totalScore,
   const int macroScore,
   const int smcScore,
   const int sentimentScore,
   const ENUM_APEX_DIRECTION rateDifferentialBias,
   const ENUM_APEX_DIRECTION relativeStrengthBias,
   const ENUM_APEX_DIRECTION yieldCurveBias,
   const string yieldCurveNote,
   const ApexSmcSignal &smc,
   const int cotCommercial6M,
   const int cotCommercial12M,
   const ENUM_APEX_DIRECTION specContrarianBias,
   const ENUM_APEX_DIRECTION openInterestBias,
   const string sentimentNote,
   const bool includeTradeParameters,
   const double entryPrice,
   const double lots,
   const double riskPct,
   const double accountBalance,
   const ApexRiskState &riskState,
   const string additionalRiskFlags,
   const string regimeNote,
   const string narrative
)
{
   string report = "";

   report += "===================================================\n";
   report += "APEX-FX SIGNAL REPORT\n";
   report += "===================================================\n";
   report += "CONFLUENCE SCORE: " + IntegerToString(totalScore) + "/10\n";
   report += "PAIR         : " + symbol + "\n";
   report += "DIRECTION    : " + ApexDirectionToString(reportDirection) + "\n";
   report += "TIMESTAMP    : " + TimeToString(utcTime, TIME_DATE | TIME_SECONDS) + " UTC\n";
   report += "SESSION      : " + session + "\n";
   report += "---------------------------------------------------\n";
   report += "MACRO LAYER  [" + IntegerToString(macroScore) + "/3]\n";
   report += "  Rate Differential : " + ApexConfirmingText(smc.direction, rateDifferentialBias) + "\n";
   report += "  Rel. Eco. Strength: " + ApexConfirmingText(smc.direction, relativeStrengthBias) + "\n";
   report += "  Yield Curve       : " + ApexConfirmingText(smc.direction, yieldCurveBias) + " | " + yieldCurveNote + "\n";
   report += "\n";
   report += "SMC LAYER    [" + IntegerToString(smcScore) + "/4]\n";
   report += "  Market Structure  : " + smc.marketStructureText + "\n";
   report += "  Liquidity Sweep   : " + ApexYesNo(smc.liquiditySweepConfirmed) + " - level " + ApexFormatPrice(symbol, smc.sweepLevel) + "\n";
   report += "  FVG Present       : " + ApexYesNo(smc.fvgPresent) + " - " + ApexFormatZone(symbol, smc.fvg) + "\n";
   report += "  OB Confluence     : " + ApexYesNo(smc.obConfluence) + " - " + ApexFormatZone(symbol, smc.ob) + "\n";
   report += "\n";
   report += "SENTIMENT    [" + IntegerToString(sentimentScore) + "/3]\n";
   report += "  COT Commercial Idx: 6M: " + IntegerToString(cotCommercial6M) + " | 12M: " + IntegerToString(cotCommercial12M) + "\n";
   report += "  Spec. Extreme     : " + ApexBiasToText(specContrarianBias) + "\n";
   report += "  OI Divergence     : " + ApexBiasToText(openInterestBias) + " | " + sentimentNote + "\n";
   report += "---------------------------------------------------\n";

   if(includeTradeParameters)
   {
      const double slPips = ApexPipsBetween(symbol, entryPrice, smc.stopLoss);
      const double tp1Pips = ApexPipsBetween(symbol, entryPrice, smc.takeProfit1);
      const double tp2Pips = ApexPipsBetween(symbol, entryPrice, smc.takeProfit2);
      const double rr1 = slPips > 0.0 ? tp1Pips / slPips : 0.0;
      const double rr2 = slPips > 0.0 ? tp2Pips / slPips : 0.0;

      report += "TRADE PARAMETERS\n";
      report += "  Entry Zone   : " + ApexFormatZone(symbol, smc.entryZone) + "\n";
      report += "  Entry Trigger: " + smc.triggerText + "\n";
      report += "  Stop Loss    : " + ApexFormatPrice(symbol, smc.stopLoss) + " (" + DoubleToString(slPips, 1) + " pips)\n";
      report += "  Take Profit 1: " + ApexFormatPrice(symbol, smc.takeProfit1) + " (" + DoubleToString(tp1Pips, 1) + " pips / RR: " + DoubleToString(rr1, 2) + ":1)\n";
      report += "  Take Profit 2: " + ApexFormatPrice(symbol, smc.takeProfit2) + " (" + DoubleToString(tp2Pips, 1) + " pips / RR: " + DoubleToString(rr2, 2) + ":1)\n";
      report += "  Position Size: " + DoubleToString(lots, 2) + " lots (risking " + DoubleToString(riskPct, 2) + "% of " + DoubleToString(accountBalance, 2) + ")\n";
      report += "---------------------------------------------------\n";
   }

   report += "NARRATIVE THESIS\n";
   report += "  " + narrative + "\n";
   report += "---------------------------------------------------\n";

   string flags = "";
   if(riskState.halted)
      flags = ApexAppendReason(flags, riskState.reason);

   if(smc.rejectionReason != "")
      flags = ApexAppendReason(flags, smc.rejectionReason);

   if(smc.obMitigated)
      flags = ApexAppendReason(flags, "order block previously mitigated");

   if(smc.priceTooDeepIntoFvg)
      flags = ApexAppendReason(flags, "price moved beyond configured FVG fill threshold");

   flags = ApexAppendReason(flags, additionalRiskFlags);

   if(flags == "")
      flags = "None active";

   report += "RISK FLAGS   : " + flags + "\n";
   report += "REGIME NOTE  : " + regimeNote + "\n";
   report += "DISCLAIMER   : This output is for informational and analytical purposes only. It does not constitute financial advice. All trading involves risk of capital loss. Past performance is not indicative of future results. Human review is required before execution.\n";
   report += "===================================================\n";

   return report;
}

#endif
