"""Filing-dated SEC history and conservative DCF inputs for covered issuers."""
from datetime import date
import json
import os
from pathlib import Path
import time
from urllib.request import Request, urlopen

CIKS={"AAPL":"0000320193","MSFT":"0000789019"}
BASE=Path(__file__).resolve().parent/"data"/"sec"
FIELDS={
    "net_income":("NetIncomeLoss",),"da":("DepreciationDepletionAndAmortization","DepreciationDepletionAndAmortizationPropertyPlantAndEquipment"),
    "depreciation":("Depreciation",),"intangible_amort":("AmortizationOfIntangibleAssets",),
    "maintenance_capex":("PaymentsToAcquirePropertyPlantAndEquipment",),
    "shares":("WeightedAverageNumberOfDilutedSharesOutstanding","WeightedAverageNumberOfSharesOutstandingBasic"),
    "cash":("CashAndCashEquivalentsAtCarryingValue",),"long_term_debt":("LongTermDebtNoncurrent","LongTermDebt"),
    "debt_current":("LongTermDebtCurrent","LongTermDebtAndFinanceLeaseObligationsCurrent"),
    "revenue":("RevenueFromContractWithCustomerExcludingAssessedTax","Revenues","SalesRevenueNet"),
    "gross_profit":("GrossProfit",),"ebit":("OperatingIncomeLoss",),
    "tax":("IncomeTaxExpenseBenefit",),"pretax":("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest","IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"),
    "equity":("StockholdersEquity",),"interest":("InterestExpenseNonoperating","InterestExpenseNonOperating","InterestExpense","InterestAndDebtExpense"),
    "current_assets":("AssetsCurrent",),"current_liabilities":("LiabilitiesCurrent",),
    "assets":("Assets",),"liabilities":("Liabilities",),"retained_earnings":("RetainedEarningsAccumulatedDeficit",),
    "operating_cf":("NetCashProvidedByUsedInOperatingActivities",)
}

def extract(payload,symbol,today=None):
    today=today or date.today().isoformat()
    facts=payload["facts"]["us-gaap"]
    by_end={}
    for field,tags in FIELDS.items():
        for priority,tag in enumerate(tags):
            unit="shares" if field=="shares" else "USD"
            for rec in facts.get(tag,{}).get("units",{}).get(unit,[]):
                if rec.get("form") not in ("10-K","10-K/A") or rec["filed"]>today or rec["end"]>today:
                    continue
                if rec.get("start") and not 330<=(date.fromisoformat(rec["end"])-date.fromisoformat(rec["start"])).days<=400:
                    continue
                # Current restated annual values are appropriate for today's snapshot only.
                point=by_end.setdefault(rec["end"],{})
                rank=(-priority,rec["filed"],rec.get("accn",""))
                if field not in point or rank>point[field][0]:
                    point[field]=(rank,rec["val"],rec["filed"])
    annual=[]; previous=None
    for ending,values in sorted(by_end.items()):
        r={k:v[1] for k,v in values.items()}
        if not all(k in r for k in ("net_income","current_assets","cash","current_liabilities","revenue")):
            continue
        if "da" not in r and "depreciation" in r and "intangible_amort" in r:
            r["da"]=r["depreciation"]+r["intangible_amort"]
        operating_wc=r["current_assets"]-r["cash"]-r["current_liabilities"]+r.get("debt_current",0)
        prior=previous
        previous=(ending,operating_wc)
        if not prior or not 330<=(date.fromisoformat(ending)-date.fromisoformat(prior[0])).days<=400:
            continue
        r.update(year=int(ending[:4]),filed=max(v[2] for v in values.values()),delta_wc=operating_wc-prior[1])
        if "long_term_debt" in r and "debt_current" in r:
            r["debt"]=r["long_term_debt"]+r["debt_current"]
        if all(k in r for k in ("debt","equity")):
            r["invested_capital"]=r["debt"]+r["equity"]-r["cash"]
        if r.get("pretax",0)>0 and "tax" in r:
            r["tax_rate"]=r["tax"]/r["pretax"]
        if all(k in r for k in ("ebit","tax_rate","maintenance_capex","da")):
            nopat=r["ebit"]*(1-r["tax_rate"])
            if nopat>0:
                r["reinvestment"]=max(0,min(1,(r["maintenance_capex"]-r["da"]+r["delta_wc"])/nopat))
        annual.append(r)
    return {"symbol":symbol,"asset_type":"equity","profile":"Enterprise_Software_Switching" if symbol=="MSFT" else "Consumer_Staples_Moat",
            "annual":annual[-10:],"as_of_basis":"retrieval","as_of":today,"source":"SEC Company Facts • total capital expenditure used as maintenance estimate",
            "governance_reviewed":False}

def cached(symbol):
    path=BASE/(symbol+".json")
    if symbol in CIKS and path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None

def refresh(symbol):
    if symbol not in CIKS:
        raise ValueError("SEC issuer coverage is available for AAPL and MSFT.")
    cik=CIKS[symbol]
    identity=os.getenv("MERIDIAN_SEC_CONTACT","Meridian Desk private desktop research")
    headers={"User-Agent":identity,"Accept":"application/json"}
    def fetch(url):
        with urlopen(Request(url,headers=headers),timeout=14) as resp:
            return json.loads(resp.read(45000000))
    facts=fetch("https://data.sec.gov/api/xbrl/companyfacts/CIK"+cik+".json")
    snapshot=extract(facts,symbol)
    time.sleep(.2)
    doc=fetch("https://data.sec.gov/submissions/CIK"+cik+".json")
    recent=doc["filings"]["recent"]
    snapshot["filings"]=[]
    for i,form in enumerate(recent["form"]):
        if form in ("10-K","10-Q","10-K/A","10-Q/A","8-K"):
            acc=recent["accessionNumber"][i].replace("-","")
            snapshot["filings"].append({"form":form,"filed":recent["filingDate"][i],
                "url":f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/"+recent["primaryDocument"][i]})
        if len(snapshot["filings"])>=15:
            break
    BASE.mkdir(parents=True,exist_ok=True)
    target=BASE/(symbol+".json")
    tmp=target.with_suffix(".tmp")
    tmp.write_text(json.dumps(snapshot,allow_nan=False),encoding="utf-8")
    tmp.replace(target)
    return snapshot
