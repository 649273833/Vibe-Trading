# Market Adaptation Reference (Reference on Demand, Not Execution Instructions)

## A-Share (China) Specifics

### Key Differences vs US Markets

| Dimension | US Original | A-Share Adaptation |
|-----------|------------|-------------------|
| Policy weight | Lower (market-driven) | **Extremely high** (policy directly catalyzes sectors) |
| Dominant capital | Hedge funds / institutions | **Mutual funds + private equity + hot money**, retail speculation is fierce |
| Retail structure | Smaller | **High retail participation**, high sentiment volatility |
| Shell value | No such concept | Small caps carry a **shell-value** premium |
| Domestic substitution | Not core | **One of the core logics** (chokepoint list) |

### A-Share Unique Signal Dimensions

1. **Dragon-Tiger List (龙虎榜)**: trading desk retail seat exposure reveals short-term sentiment
2. **Margin Trading (融资融券)**: leveraged capital sentiment (margin balance surge = bullish)
3. **Major Capital Inflow (主力净流入)**: single-day major inflow >¥500M = clear institutional accumulation
4. **Government Work Report (政府工作报告)**: updated each March, major directional signal
5. **Chokepoint List (卡脖子清单)**: State Council published, guides domestic substitution direction

### A-Share Toolkit

**neodata-financial-search** (quotes/research reports/capital flows):

```
"[sector name] quotes capital flow"          # sector-wide quotes
"[material/component] supply-demand gap domestic substitution"  # supply chain key links
"[company name] brokerage report price target"  # research report signals
"[sector] policy support"                    # policy catalysts
"[sector name] constituents A-share"         # sector constituents
```

**westock-data** (position distribution/block trades/institutional):

```
[ticker].westock: chip_cost           # cost distribution
[ticker].westock: block_trade         # block trades
[ticker].westock: margin              # margin balance
[ticker].westock: institution_rating  # institutional ratings
[ticker].westock: hk_hold             # Northbound (HK) connect holdings
```

> **No-tool fallback**: If neodata/westock MCP tools are not installed in the environment, obtain similar information via web search on CNINFO (cninfo.com.cn), Eastmoney (eastmoney.com), 10jqka (10jqka.com). Mark data source and date.

### A-Share Data Discipline (Parallel to US Data Discipline)

US primary sources are SEC filings (10-K/10-Q/8-K). The A-share primary source system is different and requires parallel rules:

| Data Item | A-Share Primary Source | Search Path |
|-----------|----------------------|-------------|
| Revenue structure / segment breakdown | Annual Report (年度报告) | CNINFO → search company name → annual report → "primary business by industry/product" |
| Customer concentration | Annual Report + Semi-annual Report | Annual report → "major customers" or "top 5 customers" |
| Earnings preview / flash report | Exchange announcements | SZSE/SSE website → announcement search → earnings preview/flash |
| Inquiry letter responses | Exchange announcements | CNINFO → search "inquiry letter" → view response (often contains customer/supplier details) |
| Major shareholders / share reduction | Exchange announcements | CNINFO → search "share reduction" "equity change" |
| Research reports / price targets | Brokerage reports | Eastmoney research center, 10jqka research channel (side evidence only, not primary source) |
| Dragon-Tiger list / block trades | Exchange daily disclosure | SZSE/SSE → trading public information / block trades |
| Margin trading | Exchange daily disclosure | Exchange website → margin data |
| Northbound (HK) connect holdings | HKEX / Exchange | Shanghai-Shenzhen-HK Stock Connect holding data (Eastmoney or Wind) |

**Timeliness requirements:**

- Annual report disclosure windows: Jan-Apr (annual), Jul-Aug (semi-annual), Oct (Q3 report)
- Earnings preview windows: Jan (annual preview), Jul (semi-annual preview), Oct (Q3 preview)
- Fast-changing fields (Dragon-Tiger/margin/block trades): use last 5 trading days data, mark as-of
- Inquiry letter responses: specifically search for new inquiry letters within 90 days before as-of (analogous to the US 60-day 8-K rule)

**Fabrication guard (A-share version)**: Search CNINFO for annual/semi-annual report originals first; mark as `Confirmed` when found. Only mark `[Inference]` after genuinely searching and not finding. Board secretary replies on interactive platforms (互动易/e互动) qualify as `Management Claim` level — do not upgrade to `Confirmed`.

---

## US Market Specifics

### SEC Filings Path

| Filing | Key Information |
|--------|----------------|
| **10-K/10-Q/8-K** | Revenue structure, customer concentration, backlog, dilution risk (ATM/converts/warrants) |
| **Earnings transcripts** | Capacity maxed out, certifications nearing end, next year ramp, customer name-drops |
| **Investor presentations** | Roadmap, TAM, market share |
| **S-3/ATM risk** | Dilution risk warnings |
| **Insider transactions** | Insider buying/selling (clear-out at highs = red flag) |
| **DEF 14A (Proxy)** | Management compensation, equity incentives (for assessing incentive alignment) |
| **13F/13D/13G** | Institutional position changes (determining if "institutions are building positions") |

### Liquidity / Dilution Risk

| Indicator | Threshold | Meaning |
|-----------|-----------|---------|
| Float | <20% | Squeeze risk |
| Short interest | >20% | Squeeze potential |
| ATM programs | Continuous issuance | Infinite dilution = hard veto |
| Convertibles/Warrants | Large maturities | Potential dilution |
| Shelf registrations | On-demand issuance | Supply pressure |

---

## Global Markets

### Hong Kong (HK Stocks)

- **Disclosure sources**: HKEX filings (hkexnews.hk), annual/interim reports, placings, connected transactions
- **Key concerns**: Mainland policy exposure, liquidity, Southbound eligibility
- **Typical chokepoint companies**: Sunny Optical (optics), Q Technology (camera modules), Hua Hong Semi (foundry)
- **Special risk**: "Old thousand" stock risk (frequent share consolidations/splits/name changes in small caps = hard veto)

### Taiwan (TW Stocks)

- **Disclosure sources**: Market Observation Post System (mops.twse.com.tw), monthly revenue announcements, investor conferences
- **Key concerns**: TSMC supply chain, ASE packaging, MediaTek design
- **Unique feature**: Monthly revenue data is trackable, more timely than quarterly reports

### Japan (JP Stocks)

- **Disclosure sources**: EDINET (Financial Services Agency electronic disclosure), company quarterly reports, company IR
- **Key concerns**: Semiconductor equipment (Tokyo Electron / SCREEN), materials (Shin-Etsu / SUMCO), optics (HOYA)

### Korea (KR Stocks)

- **Disclosure sources**: DART (Financial Supervisory Service), company IR
- **Key concerns**: Samsung / SK Hynix supply chain (HBM/DRAM/NAND)

### Europe (EU Stocks)

- **Disclosure sources**: National exchange filings, company IR, trade journals
- **Key concerns**: ASML (lithography), STMicro (SiC/GaN), Infineon (power semiconductors)
- **Unique feature**: European small caps are often overlooked by US institutions (Serenity's "European small caps first" heuristic)

### General Notes

- FX/geopolitical exposure: assess currency risk and China export control impact for every market
- Data source priority: local exchange official disclosure > company IR > local financial media > international aggregators
