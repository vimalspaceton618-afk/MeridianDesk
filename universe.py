"""Curated international equity discovery; research-only until licensed execution is built.

A catalog record is not a claim that live quotes or licensed redistribution exist.
Symbols are Yahoo-style listing identifiers, not globally unique company identities.
No Indian exchange listings are included in this product catalog.
"""
from __future__ import annotations

import re

# (market, listing venue, quote currency, ((provider symbol, issuer), ...))
# GBp means GBP pence per share rather than whole GBP.
_GROUPS = (
    ("United States", "NYSE/Nasdaq", "USD", (
        ("NVDA", "NVIDIA"), ("GOOGL", "Alphabet Class A"), ("GOOG", "Alphabet Class C"),
        ("AMZN", "Amazon"), ("META", "Meta Platforms"), ("TSLA", "Tesla"),
        ("AMD", "Advanced Micro Devices"), ("AVGO", "Broadcom"), ("ORCL", "Oracle"),
        ("CRM", "Salesforce"), ("JPM", "JPMorgan Chase"), ("V", "Visa"),
        ("MA", "Mastercard"), ("BRK-B", "Berkshire Hathaway Class B"),
        ("KO", "Coca-Cola"), ("PG", "Procter & Gamble"), ("XOM", "Exxon Mobil"),
        ("COST", "Costco"), ("NFLX", "Netflix"), ("WMT", "Walmart"),
    )),
    ("Canada", "Toronto Stock Exchange", "CAD", (
        ("RY.TO", "Royal Bank of Canada"), ("TD.TO", "Toronto-Dominion Bank"),
        ("SHOP.TO", "Shopify"), ("ENB.TO", "Enbridge"), ("CNQ.TO", "Canadian Natural Resources"),
        ("CNR.TO", "Canadian National Railway"), ("BNS.TO", "Bank of Nova Scotia"),
        ("SU.TO", "Suncor Energy"),
    )),
    ("United Kingdom", "London Stock Exchange", "GBp", (
        ("SHEL.L", "Shell"), ("AZN.L", "AstraZeneca"), ("HSBA.L", "HSBC Holdings"),
        ("ULVR.L", "Unilever"), ("BP.L", "BP"), ("RIO.L", "Rio Tinto"),
        ("GSK.L", "GSK"), ("BARC.L", "Barclays"), ("REL.L", "RELX"),
    )),
    ("Germany", "Xetra", "EUR", (
        ("SAP.DE", "SAP"), ("SIE.DE", "Siemens"), ("ALV.DE", "Allianz"),
        ("BMW.DE", "BMW"), ("BAS.DE", "BASF"), ("DTE.DE", "Deutsche Telekom"),
        ("VOW3.DE", "Volkswagen Preference"), ("MBG.DE", "Mercedes-Benz Group"),
    )),
    ("France", "Euronext Paris", "EUR", (
        ("MC.PA", "LVMH"), ("OR.PA", "L'Oreal"), ("TTE.PA", "TotalEnergies"),
        ("SAN.PA", "Sanofi"), ("AIR.PA", "Airbus"), ("SU.PA", "Schneider Electric"),
        ("BNP.PA", "BNP Paribas"), ("AI.PA", "Air Liquide"),
    )),
    ("Netherlands", "Euronext Amsterdam", "EUR", (
        ("ASML.AS", "ASML"), ("ADYEN.AS", "Adyen"), ("HEIA.AS", "Heineken"),
        ("INGA.AS", "ING Group"), ("PHIA.AS", "Philips"), ("WKL.AS", "Wolters Kluwer"),
    )),
    ("Switzerland", "SIX Swiss Exchange", "CHF", (
        ("NESN.SW", "Nestle"), ("NOVN.SW", "Novartis"), ("ROG.SW", "Roche Holding"),
        ("UBSG.SW", "UBS Group"), ("ABBN.SW", "ABB"), ("ZURN.SW", "Zurich Insurance"),
    )),
    ("Sweden", "Nasdaq Stockholm", "SEK", (
        ("VOLV-B.ST", "Volvo Class B"), ("ATCO-A.ST", "Atlas Copco Class A"),
        ("ERIC-B.ST", "Ericsson Class B"), ("INVE-B.ST", "Investor Class B"),
        ("SEB-A.ST", "SEB Class A"),
    )),
    ("Norway", "Oslo Bors", "NOK", (
        ("EQNR.OL", "Equinor"), ("DNB.OL", "DNB Bank"), ("NHY.OL", "Norsk Hydro"),
    )),
    ("Denmark", "Nasdaq Copenhagen", "DKK", (
        ("NOVO-B.CO", "Novo Nordisk Class B"), ("DSV.CO", "DSV"),
        ("MAERSK-B.CO", "A.P. Moller-Maersk Class B"),
    )),
    ("Spain", "Bolsa de Madrid", "EUR", (
        ("SAN.MC", "Banco Santander"), ("ITX.MC", "Inditex"), ("IBE.MC", "Iberdrola"),
        ("BBVA.MC", "BBVA"), ("TEF.MC", "Telefonica"),
    )),
    ("Italy", "Borsa Italiana", "EUR", (
        ("ENI.MI", "Eni"), ("ISP.MI", "Intesa Sanpaolo"), ("UCG.MI", "UniCredit"),
        ("ENEL.MI", "Enel"), ("RACE.MI", "Ferrari"), ("STLAM.MI", "Stellantis"),
    )),
    ("Finland", "Nasdaq Helsinki", "EUR", (
        ("NOKIA.HE", "Nokia"), ("KNEBV.HE", "Kone Class B"),
    )),
    ("Belgium", "Euronext Brussels", "EUR", (
        ("ABI.BR", "Anheuser-Busch InBev"), ("KBC.BR", "KBC Group"),
    )),
    ("Japan", "Tokyo Stock Exchange", "JPY", (
        ("7203.T", "Toyota Motor"), ("6758.T", "Sony Group"), ("9984.T", "SoftBank Group"),
        ("8035.T", "Tokyo Electron"), ("6861.T", "Keyence"), ("7974.T", "Nintendo"),
        ("8306.T", "Mitsubishi UFJ Financial"), ("9432.T", "NTT"),
        ("6501.T", "Hitachi"), ("8058.T", "Mitsubishi Corporation"),
    )),
    ("Hong Kong", "Hong Kong Stock Exchange", "HKD", (
        ("0700.HK", "Tencent"), ("9988.HK", "Alibaba Group"),
        ("1299.HK", "AIA Group"), ("0005.HK", "HSBC Holdings"),
        ("3690.HK", "Meituan"), ("2318.HK", "Ping An Insurance"),
        ("1810.HK", "Xiaomi"), ("0388.HK", "Hong Kong Exchanges"),
    )),
    ("Australia", "Australian Securities Exchange", "AUD", (
        ("BHP.AX", "BHP Group"), ("CBA.AX", "Commonwealth Bank"),
        ("CSL.AX", "CSL"), ("WBC.AX", "Westpac Banking"),
        ("NAB.AX", "National Australia Bank"), ("RIO.AX", "Rio Tinto"),
        ("WDS.AX", "Woodside Energy"), ("MQG.AX", "Macquarie Group"),
        ("WES.AX", "Wesfarmers"),
    )),
    ("Singapore", "Singapore Exchange", "SGD", (
        ("D05.SI", "DBS Group"), ("O39.SI", "OCBC Bank"),
        ("U11.SI", "United Overseas Bank"), ("Z74.SI", "Singtel"),
    )),
    ("Taiwan", "Taiwan Stock Exchange", "TWD", (
        ("2330.TW", "Taiwan Semiconductor"), ("2317.TW", "Hon Hai Precision"),
        ("2454.TW", "MediaTek"), ("2308.TW", "Delta Electronics"),
        ("2303.TW", "United Microelectronics"),
    )),
    ("South Korea", "Korea Exchange", "KRW", (
        ("005930.KS", "Samsung Electronics"), ("000660.KS", "SK Hynix"),
        ("035420.KS", "NAVER"), ("005380.KS", "Hyundai Motor"),
        ("051910.KS", "LG Chem"),
    )),
    ("Brazil", "B3 Sao Paulo", "BRL", (
        ("PETR4.SA", "Petrobras Preference"), ("VALE3.SA", "Vale"),
        ("ITUB4.SA", "Itau Unibanco Preference"), ("BBDC4.SA", "Bradesco Preference"),
        ("ABEV3.SA", "Ambev"), ("WEGE3.SA", "WEG"),
        ("B3SA3.SA", "B3"),
    )),
    ("Mexico", "Bolsa Mexicana", "MXN", (
        ("AMXL.MX", "America Movil Series L"), ("WALMEX.MX", "Walmart de Mexico"),
        ("FEMSAUBD.MX", "FEMSA"), ("GFNORTEO.MX", "Grupo Financiero Banorte"),
        ("CEMEXCPO.MX", "Cemex"),
    )),
    ("South Africa", "Johannesburg Stock Exchange", "ZAR", (
        ("NPN.JO", "Naspers"), ("SOL.JO", "Sasol"),
        ("SBK.JO", "Standard Bank"), ("AGL.JO", "Anglo American"),
    )),
    ("Indonesia", "Indonesia Stock Exchange", "IDR", (
        ("BBCA.JK", "Bank Central Asia"), ("BBRI.JK", "Bank Rakyat Indonesia"),
        ("TLKM.JK", "Telkom Indonesia"),
    )),
    ("Malaysia", "Bursa Malaysia", "MYR", (
        ("1155.KL", "Maybank"), ("1023.KL", "CIMB Group"),
        ("5347.KL", "Tenaga Nasional"),
    )),
    ("Thailand", "Stock Exchange of Thailand", "THB", (
        ("PTT.BK", "PTT"), ("ADVANC.BK", "Advanced Info Service"),
        ("AOT.BK", "Airports of Thailand"),
    )),
    ("Saudi Arabia", "Saudi Exchange", "SAR", (
        ("2222.SR", "Saudi Aramco"), ("1120.SR", "Al Rajhi Bank"),
    )),
)

_ALLOWED = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,23}$")
CATALOG = {}
for country, exchange, currency, entries in _GROUPS:
    for symbol, name in entries:
        if not _ALLOWED.fullmatch(symbol) or symbol in CATALOG:
            raise RuntimeError("Invalid or duplicate catalog symbol: " + symbol)
        CATALOG[symbol] = {
            "symbol": symbol, "name": name, "country": country, "exchange": exchange,
            "currency": currency, "asset": "Equity", "execution": "research-only",
        }


def entries():
    """Return a copy; no provider query and no broker authority."""
    return [dict(record) for record in CATALOG.values()]


def available(symbol):
    return symbol in CATALOG
