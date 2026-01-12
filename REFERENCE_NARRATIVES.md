# Reference Narrative Set

> **Purpose**: A curated collection of real-world claims that demonstrate how AccountabilityMe transforms vague promises into verifiable, traceable assertions.

This document contains 18 claims across 6 domains, each with sufficient context to be operationalized by the system. These serve as:
1. **Examples** for understanding how the system works
2. **Test cases** for validation
3. **Templates** for editorial workflow

---

## Domain Categories

| Domain | Claims | Typical Sources |
|--------|--------|-----------------|
| Policy & Legislation | 4 | Government statements, press releases, speeches |
| Economic Forecasts | 3 | Federal Reserve, economists, financial institutions |
| Corporate Accountability | 3 | Earnings calls, CEO statements, ESG reports |
| Technology Claims | 3 | Product launches, tech announcements, roadmaps |
| Public Health | 3 | CDC, WHO, health officials |
| Climate & Environment | 2 | Climate reports, commitments, policy statements |

---

## Policy & Legislation

### CLAIM-POL-001: Inflation Reduction Act Impact

**Statement**: "The Inflation Reduction Act will cut the deficit by $300 billion over the next decade."

**Context**: White House statement upon signing of the Inflation Reduction Act, August 16, 2022.

**Source**: [White House Briefing Room](https://www.whitehouse.gov/briefing-room/statements-releases/2022/08/16/)

**Claim Type**: Predictive

**Scope**:
- Geographic: United States
- Policy Domain: Federal Budget
- Affected Population: US taxpayers

**Operationalization**:
- **Metric**: Cumulative deficit reduction attributable to IRA provisions (2023-2032)
- **Baseline**: CBO deficit projections without IRA (August 2022)
- **Target**: $300 billion cumulative reduction
- **Evaluation Date**: December 31, 2032
- **Data Sources**: Congressional Budget Office, Treasury Department
- **Success Conditions**: CBO reports >= $270B attributable deficit reduction (10% margin)
- **Partial Success**: $150B - $270B reduction
- **Failure**: < $150B reduction

---

### CLAIM-POL-002: Infrastructure Act Job Creation

**Statement**: "The Bipartisan Infrastructure Law will create 1.5 million jobs per year over the next decade."

**Context**: Presidential remarks at Infrastructure Bill signing ceremony, November 15, 2021.

**Source**: [White House Remarks](https://www.whitehouse.gov/briefing-room/speeches-remarks/2021/11/15/)

**Claim Type**: Predictive

**Scope**:
- Geographic: United States
- Policy Domain: Infrastructure/Employment
- Affected Population: US workforce

**Operationalization**:
- **Metric**: Net job creation in infrastructure-related sectors
- **Baseline**: BLS employment data, November 2021
- **Target**: 1.5 million additional jobs annually (15 million total over decade)
- **Evaluation Date**: November 15, 2031
- **Data Sources**: Bureau of Labor Statistics, Moody's Analytics
- **Success Conditions**: >= 1.35 million average annual job growth attributable to BIL
- **Partial Success**: 750K - 1.35M average annual
- **Failure**: < 750K average annual

---

### CLAIM-POL-003: Social Security Solvency

**Statement**: "Without reform, Social Security will only be able to pay 77% of scheduled benefits starting in 2034."

**Context**: Social Security Trustees Annual Report 2023.

**Source**: [SSA Trustees Report](https://www.ssa.gov/OACT/TR/2023/)

**Claim Type**: Predictive (warning)

**Scope**:
- Geographic: United States
- Policy Domain: Social Security
- Affected Population: Social Security beneficiaries

**Operationalization**:
- **Metric**: OASDI Trust Fund reserve ratio
- **Target**: Reserve depletion in 2034
- **Threshold**: 77% benefit coverage post-depletion
- **Evaluation Date**: December 31, 2034
- **Data Sources**: Social Security Administration
- **Verification**: Trust fund balance hits zero OR policy reform occurs

---

### CLAIM-POL-004: Border Wall Effectiveness

**Statement**: "The border wall will stop illegal immigration."

**Context**: Campaign and administration statements, 2016-2020.

**Source**: Various campaign speeches and official statements

**Claim Type**: Causal (policy → outcome)

**Scope**:
- Geographic: US-Mexico Border
- Policy Domain: Immigration
- Affected Population: Border communities, migrants

**Operationalization**:
- **Metric**: Apprehensions at border sections with new wall construction
- **Baseline**: Apprehension rates before wall construction (by sector)
- **Direction**: Decrease
- **Evaluation Date**: 24 months post-construction per sector
- **Data Sources**: CBP apprehension statistics
- **Success Conditions**: >= 50% reduction in apprehensions at walled sections
- **Partial Success**: 20-50% reduction
- **Failure**: < 20% reduction or increase

**Note**: This claim requires disaggregation—"illegal immigration" must be operationalized as measurable border crossing attempts.

---

## Economic Forecasts

### CLAIM-ECON-001: Fed Interest Rate Path

**Statement**: "The Federal Reserve expects to make three rate cuts in 2024."

**Context**: Federal Reserve December 2023 Summary of Economic Projections (dot plot).

**Source**: [Federal Reserve FOMC Projections](https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20231213.htm)

**Claim Type**: Predictive (institutional forecast)

**Scope**:
- Geographic: United States
- Policy Domain: Monetary Policy

**Operationalization**:
- **Metric**: Number of 25bp federal funds rate cuts
- **Baseline**: December 2023 rate (5.25-5.50%)
- **Target**: 3 cuts (75bp total reduction)
- **Evaluation Date**: December 31, 2024
- **Data Sources**: Federal Reserve, FOMC statements
- **Success**: Exactly 3 cuts
- **Partial Success**: 2-4 cuts
- **Failure**: 0-1 cuts or >= 5 cuts

---

### CLAIM-ECON-002: US Recession Probability

**Statement**: "There is a 65% probability of a US recession in 2023."

**Context**: Bloomberg Economics model forecast, December 2022.

**Source**: [Bloomberg Economics](https://www.bloomberg.com/graphics/us-economic-recession-tracker/)

**Claim Type**: Probabilistic prediction

**Scope**:
- Geographic: United States
- Policy Domain: Macroeconomics

**Operationalization**:
- **Metric**: NBER recession declaration
- **Definition**: Two consecutive quarters of negative GDP growth (common proxy)
- **Evaluation Date**: December 31, 2023
- **Data Sources**: NBER Business Cycle Dating Committee, BEA
- **Outcome**: Binary (recession occurred / did not occur)

**Resolution Notes**: This is a probabilistic claim. The model cannot be "wrong" in a simple sense—if recession didn't occur, the 35% probability scenario materialized.

---

### CLAIM-ECON-003: AI Productivity Gains

**Statement**: "Generative AI could add $2.6 to $4.4 trillion annually to the global economy."

**Context**: McKinsey Global Institute report, June 2023.

**Source**: [McKinsey Report](https://www.mckinsey.com/capabilities/mckinsey-digital/our-insights/the-economic-potential-of-generative-ai-the-next-productivity-frontier)

**Claim Type**: Projection (long-term)

**Scope**:
- Geographic: Global
- Policy Domain: Technology/Productivity

**Operationalization**:
- **Metric**: GDP growth attributable to generative AI adoption
- **Range**: $2.6T - $4.4T annually (when fully adopted)
- **Timeframe**: Not specified precisely—"over time"
- **Evaluation Date**: Requires interim milestones (2025, 2028, 2030)
- **Data Sources**: McKinsey follow-up reports, World Bank, IMF

**Note**: This claim is inherently vague ("could add") and lacks a specific timeframe. Operationalization should establish interim milestones and adoption metrics.

---

## Corporate Accountability

### CLAIM-CORP-001: Tesla Full Self-Driving

**Statement**: "We will have full self-driving this year."

**Context**: Tesla earnings calls and investor events, repeated annually (2016-2024).

**Source**: Multiple Tesla earnings call transcripts

**Claim Type**: Product prediction

**Scope**:
- Product: Tesla Autopilot/FSD
- Affected Population: Tesla owners, road users

**Operationalization**:
- **Metric**: SAE Level 4/5 autonomy achieved
- **Definition**: No human intervention required under defined operating conditions
- **Regulatory Benchmark**: Approval for unsupervised operation by NHTSA/state DMVs
- **Evaluation Date**: End of each calendar year claimed
- **Success**: Commercial availability of true FSD (no driver attention required)
- **Failure**: Software still requires driver supervision

**Status**: As of 2024, Tesla FSD remains Level 2 (driver assistance), requiring constant driver attention.

---

### CLAIM-CORP-002: Meta Metaverse Investment Returns

**Statement**: "The metaverse is the next chapter for the internet, and it's the next chapter for our company."

**Context**: Facebook rebranding to Meta announcement, October 2021.

**Source**: [Meta Connect 2021](https://about.fb.com/news/2021/10/facebook-company-is-now-meta/)

**Claim Type**: Strategic (implicit ROI prediction)

**Scope**:
- Company: Meta Platforms
- Domain: Virtual/Augmented Reality

**Operationalization**:
- **Metric**: Reality Labs revenue and operating income
- **Baseline**: Reality Labs losses ($10.2B in 2021)
- **Target**: Path to profitability for Reality Labs division
- **Interim Metric**: Quest headset sales, Horizon Worlds DAU
- **Evaluation Dates**: Annual earnings reports
- **Success**: Reality Labs achieves operating profit
- **Partial Success**: Losses decrease year-over-year with growing revenue
- **Failure**: Sustained or increasing losses with flat/declining revenue

---

### CLAIM-CORP-003: Boeing 737 MAX Return to Safety

**Statement**: "The 737 MAX is one of the safest airplanes in the sky."

**Context**: Post-ungrounding statements, December 2020.

**Source**: Boeing press releases, FAA certification documents

**Claim Type**: Safety claim

**Scope**:
- Product: Boeing 737 MAX
- Affected Population: Passengers, crew, airlines

**Operationalization**:
- **Metric**: Fatal accident rate per million departures
- **Benchmark**: Industry average for narrow-body aircraft
- **Trailing Period**: 5 years post-ungrounding
- **Data Sources**: FAA, NTSB, Aviation Safety Network
- **Success**: Zero fatal accidents AND incident rate below industry average
- **Failure**: Any fatal accident attributable to design/software issues

**Status**: As of January 2024, door plug incident on Alaska Airlines flight raised new concerns. Ongoing evaluation.

---

## Technology Claims

### CLAIM-TECH-001: Moore's Law Continuation

**Statement**: "Semiconductor transistor density continues to double every two years."

**Context**: Historical trend established by Gordon Moore (1965), ongoing industry benchmark.

**Source**: Intel, TSMC, Samsung foundry roadmaps

**Claim Type**: Trend prediction

**Scope**:
- Industry: Semiconductor manufacturing
- Technical: Logic chip density

**Operationalization**:
- **Metric**: Transistors per mm² at leading-edge node
- **Baseline**: ~100M transistors/mm² (7nm, 2018)
- **Expected**: ~200M transistors/mm² by 2020, ~400M by 2022
- **Data Sources**: IEEE IEDM papers, foundry announcements
- **Success**: Density doubles within 2.5 years
- **Partial Success**: Density doubles within 3-4 years
- **Failure**: Density gains stall for > 4 years

---

### CLAIM-TECH-002: EV Price Parity

**Statement**: "Electric vehicles will reach price parity with gasoline cars by 2025."

**Context**: BloombergNEF forecast, 2020.

**Source**: [BNEF Electric Vehicle Outlook](https://about.bnef.com/electric-vehicle-outlook/)

**Claim Type**: Market prediction

**Scope**:
- Industry: Automotive
- Product: Battery Electric Vehicles

**Operationalization**:
- **Metric**: Average transaction price, BEV vs. ICE in same segment
- **Definition**: Compact sedan segment (e.g., Tesla Model 3 vs. Toyota Camry)
- **Adjustment**: Exclude tax credits for base comparison
- **Evaluation Date**: December 31, 2025
- **Data Sources**: Kelley Blue Book, Edmunds, manufacturer MSRP
- **Success**: BEV ATP within 5% of comparable ICE
- **Partial Success**: BEV ATP 5-15% higher than ICE
- **Failure**: BEV ATP > 15% higher than ICE

---

### CLAIM-TECH-003: Quantum Computing Advantage

**Statement**: "Within five years, quantum computers will solve problems that are practically impossible for classical computers."

**Context**: IBM Quantum roadmap, 2020.

**Source**: [IBM Quantum Roadmap](https://www.ibm.com/quantum/roadmap)

**Claim Type**: Technology milestone prediction

**Scope**:
- Industry: Computing
- Domain: Quantum computing

**Operationalization**:
- **Metric**: Demonstrated quantum advantage on commercially relevant problem
- **Definition**: Problem solved faster on quantum than best classical algorithm
- **Exclusions**: Synthetic benchmarks designed for quantum (e.g., random circuit sampling)
- **Target Problems**: Drug discovery simulation, optimization, cryptography
- **Evaluation Date**: December 31, 2025
- **Data Sources**: Peer-reviewed publications, IBM announcements
- **Success**: Verified quantum advantage on real-world problem class
- **Failure**: No demonstrated advantage outside synthetic benchmarks

---

## Public Health

### CLAIM-HEALTH-001: COVID Vaccine Efficacy

**Statement**: "The Pfizer-BioNTech vaccine is 95% effective at preventing symptomatic COVID-19."

**Context**: Phase 3 clinical trial results, November 2020.

**Source**: [NEJM Publication](https://www.nejm.org/doi/full/10.1056/NEJMoa2034577)

**Claim Type**: Clinical efficacy (trial conditions)

**Scope**:
- Product: BNT162b2 (Pfizer-BioNTech COVID-19 vaccine)
- Population: Adults 16+
- Endpoint: Symptomatic COVID-19

**Operationalization**:
- **Metric**: Vaccine efficacy = 1 - (risk in vaccinated / risk in unvaccinated)
- **Definition**: Laboratory-confirmed symptomatic COVID-19
- **Timeline**: 7+ days after second dose
- **Data Sources**: FDA EUA review, peer-reviewed studies
- **Context**: Efficacy measured against original strain; subsequent variants may differ

**Resolution Notes**: Original claim was accurate for trial conditions against original strain. Real-world effectiveness varied with variants, waning immunity, and population differences.

---

### CLAIM-HEALTH-002: Opioid Manufacturer Claims

**Statement**: "OxyContin is less addictive than other opioids when taken as prescribed."

**Context**: Purdue Pharma marketing claims, 1996-2001.

**Source**: FDA warning letters, legal proceedings, Purdue internal documents

**Claim Type**: Safety/efficacy claim (marketing)

**Scope**:
- Product: OxyContin (oxycodone extended-release)
- Population: Chronic pain patients

**Operationalization**:
- **Metric**: Addiction/dependence rates compared to immediate-release opioids
- **Data Sources**: Post-marketing surveillance, epidemiological studies
- **Comparison**: OxyContin vs. other Schedule II opioids

**Resolution**: RESOLVED as FALSE. Legal proceedings established that:
1. Purdue knew addiction rates were comparable or higher
2. Marketing claims misrepresented clinical data
3. Company pleaded guilty to federal criminal charges (2020)

---

### CLAIM-HEALTH-003: US Life Expectancy Trajectory

**Statement**: "US life expectancy will continue to increase by about 1 year per decade."

**Context**: Historical trend assumption in actuarial models, Social Security projections.

**Source**: SSA actuarial assumptions, CDC NCHS data

**Claim Type**: Trend extrapolation

**Scope**:
- Geographic: United States
- Population: All residents

**Operationalization**:
- **Metric**: Life expectancy at birth
- **Baseline**: 78.9 years (2014)
- **Expected**: ~79.9 years by 2024
- **Data Sources**: CDC NCHS National Vital Statistics Reports
- **Success**: Life expectancy reaches 79.5+ years
- **Failure**: Life expectancy decreases or stagnates

**Status**: RESOLVED as NOT MET. US life expectancy declined from 78.9 (2014) to 76.4 (2021) due to opioid epidemic, COVID-19, and other factors. As of 2023, slight recovery to ~77.5 years.

---

## Climate & Environment

### CLAIM-CLIMATE-001: Paris Agreement Temperature Target

**Statement**: "Current national commitments put the world on track for 2.8°C warming by 2100."

**Context**: UN Environment Programme Emissions Gap Report 2022.

**Source**: [UNEP Emissions Gap Report](https://www.unep.org/resources/emissions-gap-report-2022)

**Claim Type**: Projection (conditional on current policies)

**Scope**:
- Geographic: Global
- Policy Domain: Climate policy

**Operationalization**:
- **Metric**: Projected global mean temperature increase by 2100
- **Baseline**: Pre-industrial levels (1850-1900 average)
- **Scenario**: Current policies (not pledged targets)
- **Data Sources**: IPCC, Climate Action Tracker, UNEP annual updates
- **Interim Metrics**: Global GHG emissions trajectory, NDC implementation rates
- **Evaluation**: Ongoing with annual updates

---

### CLAIM-CLIMATE-002: Corporate Net Zero Commitments

**Statement**: "Amazon will achieve net-zero carbon by 2040."

**Context**: Climate Pledge announcement, September 2019.

**Source**: [Amazon Climate Pledge](https://sustainability.aboutamazon.com/climate-pledge)

**Claim Type**: Corporate commitment

**Scope**:
- Company: Amazon
- Scope: All operations (Scopes 1, 2, 3 emissions)

**Operationalization**:
- **Metric**: Total GHG emissions (Scopes 1, 2, 3) reaching net zero
- **Definition**: Net zero = gross emissions - verified offsets/removals = 0
- **Interim Targets**: Renewable energy (100% by 2025), EV delivery fleet
- **Data Sources**: Amazon annual sustainability reports, third-party audits
- **Evaluation Date**: December 31, 2040
- **Interim Checkpoints**: Annual progress reports, 2025, 2030, 2035 milestones
- **Success**: Verified net-zero across all scopes
- **Partial Success**: Net-zero for Scopes 1 & 2, significant Scope 3 reduction
- **Failure**: Emissions trajectory inconsistent with 2040 target

---

## Using This Reference Set

### For Editors

1. **Select a claim** that matches your domain expertise
2. **Verify the source** is accurate and accessible
3. **Refine the operationalization** based on available data
4. **Identify data sources** for ongoing monitoring
5. **Enter into the system** with full attribution

### For Developers

These claims can be loaded as seed data to test:
- Different claim types (predictive, causal, factual)
- Various resolution states (met, not met, partially met, inconclusive)
- Multiple evidence sources per claim
- Long-term evaluation timelines

### For Researchers

This set demonstrates how accountability systems can:
- Transform vague political promises into testable predictions
- Track corporate commitments over time
- Aggregate institutional forecasts for meta-analysis
- Preserve the historical record of public claims

---

## Claim Selection Criteria

Claims in this reference set were selected based on:

1. **Verifiability**: Clear criteria exist or can be established
2. **Public Significance**: Affects policy, markets, or public health
3. **Attribution**: Original claimant is identifiable
4. **Data Availability**: Credible sources exist for evaluation
5. **Diversity**: Covers multiple domains and claim types

---

## Contributing

To suggest additions to this reference set:

1. Ensure the claim meets selection criteria above
2. Provide complete source documentation
3. Include preliminary operationalization
4. Submit via pull request with rationale

---

*Last updated: January 2026*
*Version: 1.0*
*Maintainer: AccountabilityMe Editorial Team*

