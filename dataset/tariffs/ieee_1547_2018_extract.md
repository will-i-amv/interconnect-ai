# IEEE 1547-2018
## Standard for Interconnection and Interoperability of Distributed Energy Resources with Associated Electric Power Systems Interfaces

### Clause 5: Reactive Power Capability and Voltage/Power Control
#### Clause 5.1: Power Factor Requirements
Distributed Energy Resources (DER) shall be capable of providing dynamic reactive power support. The DER shall be capable of operating continuously across a power factor range of:
- **0.90 leading (absorbing reactive power, under-excited)** to
- **0.90 lagging (injecting reactive power, over-excited)**
at all active power output levels greater than 20% of rated nameplate capacity.

#### Clause 5.2: Voltage and Active Power Modulation (Volt-Var and Volt-Watt)
All certified inverters shall support autonomous Volt-Var and Volt-Watt grid stabilization curves configured according to the local distribution provider's operating parameters.

---

### Clause 6: Response to Area EPS Abnormal Conditions (Ride-Through)
#### Clause 6.1: Mandatory Voltage Ride-Through
DER units certified for Category II and Category III must remain connected and ride through transient undervoltage dips (down to 0.50 p.u. for 1.0 second) without tripping, unless cleared by distribution protection schemes.

#### Clause 6.2: Frequency Disturbance Limits
- High Frequency Trip (OF2): Frequency >= 62.0 Hz, clearing time = 0.16 seconds.
- High Frequency Mandatory Operation: 60.0 Hz to 60.5 Hz continuous operation.
- Low Frequency Mandatory Operation: 58.5 Hz to 60.0 Hz continuous operation.
- Low Frequency Trip (UF2): Frequency <= 56.5 Hz, clearing time = 0.16 seconds.

---

### Clause 8: Unintentional Islanding Protection
#### Clause 8.1: Anti-Islanding Clearing Time
For an unintentional island in which the DER and local load are isolated from the Area EPS, the DER shall detect the island and cease to energize the Area EPS within **2.0 seconds** of island formation. Inverter anti-islanding schemes must be validated under UL 1741 Supplement SB testing protocols.
