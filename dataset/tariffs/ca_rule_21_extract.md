# California Public Utilities Commission (CPUC) Electric Rule 21
## Generating Facility Interconnections

### Section C: General Rules, Rights, and Obligations
#### Section C.1: Fast Track Eligibility
Any generating facility with a gross aggregate nameplate capacity of 3,000 kW (3.0 MW) or less interconnecting to a distribution system may request evaluation under the Fast Track process. Fast Track projects undergo the Initial Review screens detailed in Section D.

#### Section C.2: Deficiency Notices & Cure Timelines
If the Distribution Provider identifies technical deficiencies, missing exhibits, non-compliant Single-Line Diagrams, or uncertified equipment during the Initial Review, a formal **Deficiency Notice** shall be issued within 10 business days of completing the screening. The Applicant shall have ten (10) business days from receipt of the Deficiency Notice to cure all noted non-conformances. Failure to cure within the statutory deadline shall result in application withdrawal without prejudice.

---

### Section D: Technical Interconnection Screens (Initial Review)

#### Screen A: Interconnection Applicability
Is the Generating Facility capable of export? If the Generating Facility is non-exporting or certified reverse-power protected, it passes Screen A. If exporting, it must proceed to Screen B.

#### Screen B: Certified Equipment (Inverter Compliance)
Does the Generating Facility utilize certified inverter and interconnection equipment?
1. Inverter equipment must be certified under **UL 1741 Supplement SB (UL 1741-SB)** and comply with the smart inverter mandates of **IEEE 1547-2018**.
2. Equipment lacking UL 1741-SB certification or lacking listing with the California Energy Commission (CEC) fails Screen B.
3. *Remedy upon failure*: Projects failing Screen B cannot qualify for Fast Track approval and require a Comprehensive Interconnection Study unless certified replacement inverters are resubmitted.

#### Screen C: Starting Voltage Drop
Does the starting or sudden disconnection of the Generating Facility cause a rapid voltage change exceeding 3.0% at the Point of Common Coupling (PCC)? Generating units must comply with flicker limits defined in IEEE 1453.

#### Screen D: Aggregate Feeder Penetration (15% Peak Load Screen)
Does the aggregate generation capacity connected to the distribution circuit line section (including proposed capacity and all existing connected or pre-queued distributed energy resources) exceed **15% of the annual feeder peak load**?
- **Formula**: `Penetration Percentage = (Existing Connected Gen [kW] + Proposed Gen [kW]) / Feeder Annual Peak Load [kW] * 100%`
- **Threshold**:
  - If `Penetration <= 15.0%`: The application **PASSES** Screen D.
  - If `Penetration > 15.0%`: The application **FAILS** Screen D.
- *Remedy upon failure*: Failure of Screen D indicates risk of reverse power flow through the substation regulator and voltage rise. The application fails Initial Review and must proceed to **Supplemental Review** (Screens N, O, and P) or a Detailed System Impact Study.

#### Screen E: Short-Circuit Current Duty Limit
Does the proposed Generating Facility contribute more than 2.5% to the maximum fault current of the distribution circuit? If the contribution exceeds 2.5% or pushes total fault duty over 100% of circuit breaker interrupting ratings, the project fails Screen E.

#### Screen F: Short Circuit Ratio Threshold
Is the short-circuit ratio (SCR) of available system fault MVA to the rated generating facility MVA at least 20? SCR values below 20 represent a weak grid connection requiring dedicated stability review.

#### Screen H: Manual Disconnect Switch and Safety Requirements
All inverter-based facilities greater than 10 kW must provide a utility-accessible, exterior-mounted, visible-break, lockable manual AC disconnect switch installed immediately adjacent to the utility revenue meter.
- The switch must provide a clear visible gap in the open position to guarantee line worker safety during de-energized line maintenance.
- The location, rating, and mechanical locking provisions of the AC disconnect switch must be explicitly depicted on the engineering Single-Line Diagram (SLD).
- Omission of this switch on the SLD constitutes a critical safety defect and mandates immediate issuance of a formal Deficiency Notice under Section C.2.

#### Screen I: Anti-Islanding Protection
Does the Generating Facility possess certified anti-islanding protection capable of disconnecting the generating unit within **2.0 seconds** of unintentional islanding, in compliance with IEEE 1547-2018 Clause 8.1?
