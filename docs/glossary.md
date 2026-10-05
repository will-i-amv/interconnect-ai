# InterconnectAI — Electric Interconnection Domain Glossary

This document serves as the authoritative domain dictionary and business logic reference for **InterconnectAI**. It details the regulatory frameworks, technical screens, electrical engineering concepts, application exhibits, and software architecture terms used across utility distributed energy resource (DER) interconnection reviews.

---

## Table of Contents

1. [Regulatory Frameworks & Governing Authorities](#1-regulatory-frameworks--governing-authorities)
2. [Interconnection Review Pathways](#2-interconnection-review-pathways)
3. [Deterministic Technical Screens (CPUC Rule 21 & IEEE 1547)](#3-deterministic-technical-screens-cpuc-rule-21--ieee-1547)
4. [Electrical Engineering & Distribution System Concepts](#4-electrical-engineering--distribution-system-concepts)
5. [Application Exhibits & Engineering Artifacts](#5-application-exhibits--engineering-artifacts)
6. [Statutory Notices & Workflow Artifacts](#6-statutory-notices--workflow-artifacts)

---

## 1. Regulatory Frameworks & Governing Authorities

### CPUC Electric Rule 21
The California Public Utilities Commission (CPUC) tariff governing the interconnection of distributed generation and storage facilities to utility distribution systems (PG&E, SCE, SDG&E). Rule 21 establishes standardized technical screening criteria (Screens A through M), timelines, cost responsibilities, and smart inverter operational mandates.

### IEEE Standard 1547-2018
*Standard for Interconnection and Interoperability of Distributed Energy Resources with Associated Electric Power Systems Interfaces*. An American National Standard providing technical requirements for DER performance, operation, testing, safety considerations, and maintenance. Key mandates include abnormal voltage/frequency ride-through, reactive power/voltage regulation, and anti-islanding.

### FERC Order 2023 & 2023-A
The Federal Energy Regulatory Commission landmark order reforming generator interconnection procedures and agreements. Order 2023 transitions nationwide transmission queues from a "first-come, first-served" serial study process to a "first-ready, first-served" cluster study model with increased financial readiness milestones, study delay penalties, and affected system coordination.

### UL 1741 (UL 1741 SA / UL 1741 SB)
The Underwriters Laboratories safety standard for inverters, converters, controllers, and interconnection system equipment (ISE).
- **UL 1741 SA**: Supplement A covering smart inverter grid-support functions (Rule 21 Phase 1/2).
- **UL 1741 SB**: Supplement B testing compliance with the updated IEEE 1547-2018 and IEEE 1547.1-2020 requirements (interoperability, ride-through, and grid support protocols).

### NERC-CIP
The North American Electric Reliability Corporation Critical Infrastructure Protection standards. Defines cybersecurity and operational compliance standards for bulk electric system assets, requiring utility-grade air-gapped or on-premises data governance for critical utility operational data.

---

## 2. Interconnection Review Pathways

### Simplified Interconnection
An expedited evaluation path for certified, inverter-based DER facilities (typically residential or small commercial solar/storage up to 10–30 kW) that export no power or meet strict anti-islanding criteria.

### Fast Track / Initial Review
A standardized, rapid engineering assessment process for projects (typically up to 3 MW to 5 MW depending on system voltage) evaluated against initial deterministic technical screens (Screens A through I). If all screens pass, the application is approved without requiring costly supplemental or detailed engineering studies.

### Supplemental Review
A secondary evaluation phase triggered when an application fails or produces inconclusive results in one or more Initial Review screens. Consists of Screens J (Minimum Daytime Load), K (Voltage Excursion), and L (Safety and Protective Device Coordination). Passing Supplemental Review grants approval without a full system study.

### Detailed Study (Interconnection Study Process)
A comprehensive engineering evaluation required when an application fails Fast Track and Supplemental Review. It entails:
1. **Scoping Meeting**: Initial alignment between utility engineers and applicant.
2. **System Impact Study (SIS)**: Full power-flow, short-circuit, and dynamic stability modeling.
3. **Facilities Study (FS)**: Engineering design and cost estimation for required utility grid upgrades.
4. **Interconnection Agreement (IA)**: Execution of the final binding contract.

---

## 3. Deterministic Technical Screens (CPUC Rule 21 & IEEE 1547)

```text
Application Intake
       │
       ▼
┌──────────────┐      Pass
│ Screen A - I ├─────────────► Fast Track Approval
└──────┬───────┘
       │ Fail
       ▼
┌──────────────┐      Pass
│ Screen J - M ├─────────────► Supplemental Approval
└──────┬───────┘
       │ Fail
       ▼
Detailed Study (SIS / FS)
```

### Screen A — Export / Non-Export Capacity
Verifies whether the DER facility is designed as non-exporting or inadvertent export only. Certified non-export facilities with certified power control systems bypass several downstream capacity screens.

### Screen B — Certified Equipment
Verifies that all inverters and interconnection equipment are certified by a Nationally Recognized Testing Laboratory (NRTL) to UL 1741 SB and IEEE 1547-2018 standards.

### Screen C — 15% Feeder Penetration
Evaluates whether total aggregate generation (existing plus proposed) on the medium-voltage distribution circuit exceeds 15% of the circuit's historical annual peak load.
$$\text{Penetration} = \frac{\sum P_{\text{DER}}}{P_{\text{Feeder Peak}}} \le 15\%$$
If penetration exceeds 15%, reverse power flow and voltage rise risks require Supplemental Review.

### Screen D — 15% Line Section Penetration
Evaluates whether aggregate generation on the specific line section (downstream of sectionalizing devices, reclosers, or fuses) exceeds 15% of that line section's peak load.

### Screen E — Short-Circuit Current Contribution
Determines whether the DER's short-circuit current contribution exceeds 10% of the distribution circuit's total fault current at the primary substation bus. Excessive contribution can desensitize utility relays.
$$\frac{I_{\text{fault, DER}}}{I_{\text{fault, total}}} \le 10\%$$

### Screen F — Fault Current Interrupting Capability
Verifies that the combined short-circuit current (utility grid contribution plus all DER contributions) does not exceed 100% of the interrupting rating of any utility circuit breaker, recloser, or fuse.

### Screen G — Line Configuration & Grounding
Assesses the transformer winding configuration and grounding compatibility (e.g., four-wire multigrounded wye vs delta primary) to prevent temporary overvoltage (TOV) on unfaulted phases during single line-to-ground faults.

### Screen H — Starting Voltage Drop & Flicker
Calculates the transient voltage drop caused by the starting or sudden connection of the DER (in-rush current) across the grid impedance. Must not exceed IEEE 1453 limits (typically $\le 3.0\%$ to $5.0\%$ instantaneous voltage drop).

### Screen I — Secondary Network Interconnection
Restricts power export into secondary grid or spot networks (dense urban networks). Generation must not cause reverse power flow through network protectors.

### Screen J — Minimum Daytime Load (Supplemental Review)
Verifies that aggregate generation does not exceed 100% of the minimum recorded daytime feeder load (MDL) between 10:00 AM and 4:00 PM, avoiding backfeed through the substation transformer bank.

---

## 4. Electrical Engineering & Distribution System Concepts

### DER (Distributed Energy Resource)
Any electric generation, storage facility, or controllable load connected to the distribution system, including solar photovoltaic (PV), battery energy storage systems (BESS), fuel cells, and microturbines.

### BESS (Battery Energy Storage System)
An electrochemical energy storage facility capable of bidirectional four-quadrant operation (charging and discharging), utilizing grid-forming or grid-following inverters.

### POI (Point of Interconnection) / PCC (Point of Common Coupling)
The physical and electrical location where the generator's interconnection facilities connect to the utility's distribution or transmission system.

### Nameplate Capacity vs. Export Capacity
- **Nameplate Capacity**: The gross manufacturer-rated continuous alternating current (AC) output of the generation/storage equipment (in kW or MW).
- **Export Capacity**: The maximum continuous power (kW or MW) permitted to flow across the POI into the electric grid, enforced by physical equipment or an approved Power Control System (PCS).

### Feeder / Distribution Circuit
A medium-voltage electrical line (commonly 4.16 kV, 12 kV, 13.8 kV, 21 kV, or 34.5 kV) radiating from an electric distribution substation to serve retail customers and interconnect distributed generation.

### Line Section
A discrete segment of a distribution circuit bounded by protective, sectionalizing, or switching devices such as reclosers, sectionalizers, fuses, or automated switches.

### Substation Transformer Bank
The power transformer at an electrical substation that steps down high-voltage transmission or sub-transmission power to medium-voltage distribution circuits.

### Minimum Daytime Load (MDL)
The lowest aggregate electrical load measured on a feeder or substation transformer bank during daylight hours (typically 10:00 AM to 4:00 PM local time). Crucial for calculating solar saturation and reverse power flow.

### Annual Peak Load
The maximum electrical demand (in MW or MVA) recorded or forecasted on a distribution feeder or substation bank over a rolling 12-month period.

### Reverse Power Flow
Condition where total local generation exceeds local load, causing electrical energy to flow backward across distribution transformers or into substation buses and transmission equipment.

### Effective Grounding & Temporary Overvoltage (TOV)
A system condition where the ratio of zero-sequence reactance to positive-sequence reactance ($X_0/X_1$) is positive and $< 3$, and zero-sequence resistance to positive-sequence reactance ($R_0/X_1$) is $< 1$. Effective grounding ensures line-to-ground faults do not create destructive overvoltages on healthy phases.

### Short-Circuit Ratio (SCR)
A measure of grid strength at the POI, defined as the ratio of the grid's three-phase short-circuit MVA to the rated MW capacity of the interconnecting DER. Low SCR values ($< 2.0$) indicate weak grid conditions vulnerable to instability.

### Interrupting Rating (AIC)
Amps Interrupting Capacity. The maximum symmetrical fault current that a circuit breaker, fuse, or protective device can safely interrupt without mechanical failure or explosive arc flash.

### Anti-Islanding Protection
A safety protection scheme mandated by IEEE 1547 and UL 1741 that forces DER inverters to cease energizing and disconnect within 2.0 seconds whenever the utility grid loses power, preventing dangerous energized islands.

### Voltage Ride-Through (VRT) & Frequency Ride-Through (FRT)
The capability of a DER inverter to remain connected and operating during momentary abnormal voltage or frequency grid disturbances, rather than tripping offline and exacerbating grid collapse.

### Smart Inverter Reactive Power Controls
- **Volt-VAR**: Automatically absorbs or injects reactive power (VARs) in response to local voltage deviations to stabilize circuit voltage.
- **Volt-Watt**: Curtains active power output (Watts) when local voltage exceeds high statutory limits (e.g. $> 1.06$ per unit).
- **Frequency-Watt**: Automatically curtails active power when system frequency rises above nominal (60 Hz).

---

## 5. Application Exhibits & Engineering Artifacts

### SLD (Single-Line Diagram)
A standardized, one-line electrical schematic illustrating the electrical relationships between equipment, including inverters, transformers, disconnects, circuit breakers, fuses, meters, instrument transformers (CTs/PTs), and the POI.

### Three-Line Diagram
An expanded electrical schematic showing all three individual electrical phase conductors ($A, B, C$), neutral conductors, ground conductors, and instrument wiring for protective relays.

### Equipment Cut-Sheet / Datasheet
The official manufacturer specification document providing technical specifications, electrical ratings, UL certification listings, and operational settings for inverters, transformers, and switchgear.

### PE Stamp & Signature
The legal seal and signature of a registered Professional Engineer (PE), attesting that the submitted engineering drawings and technical calculations comply with state engineering laws and technical codes.

### Power Control System (PCS)
An electronic or software-based control system compliant with UL 1741 (PCS listing) that limits or restricts export from a generating or storage facility to a pre-defined threshold.

---

## 6. Statutory Notices & Workflow Artifacts

### Deemed Complete / Completeness Notice
A formal statutory notification issued by the utility confirming that an application contains all required technical drawings, cut-sheets, and metadata to commence engineering screening.

### Deficiency Notice (Notice of Incomplete Application)
A legally binding utility notice detailing specific missing exhibits, technical inaccuracies, or failed screening parameters. It triggers a statutory cure clock (typically 10 to 30 business days) for the applicant to rectify issues.

### Initial Review Results Summary (IRRS) / Decision Memo
A comprehensive engineering report issued at the conclusion of Fast Track review documenting the pass/fail determinations of Screens A through I, technical findings, and required next steps.

### Interconnection Agreement (IA)
The final executed contract between the utility and the generator defining legal terms, operational requirements, export caps, maintenance responsibilities, and financial terms.

### Human-in-the-Loop (HITL) PE Override
A controlled software review action where a licensed utility Professional Engineer reviews AI-generated findings, inputs engineering rationale, overrides specific screen determinations, and signs off.

---
