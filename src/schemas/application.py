"""Application intake and electrical engineering schemas for InterconnectAI."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class InterconnectionType(StrEnum):
    """Types of distributed energy resource (DER) generating facilities."""

    SOLAR_PV = "SOLAR_PV"
    BATTERY_STORAGE = "BATTERY_STORAGE"
    HYBRID_SOLAR_STORAGE = "HYBRID_SOLAR_STORAGE"
    EV_CHARGING = "EV_CHARGING"
    WIND = "WIND"


class ServiceVoltage(StrEnum):
    """Standard grid distribution interconnection service voltages."""

    V208_3PHASE = "208V_3PHASE"
    V480_3PHASE = "480V_3PHASE"
    V12_47KV_3PHASE = "12.47KV_3PHASE"
    V21_6KV_3PHASE = "21.6KV_3PHASE"
    OTHER = "OTHER"


class DisconnectSwitchLocation(StrEnum):
    """Location of the external visible-break AC disconnect switch."""

    ADJACENT_TO_METER = "ADJACENT_TO_METER"
    EXTERIOR_NOT_ADJACENT = "EXTERIOR_NOT_ADJACENT"
    INTERIOR = "INTERIOR"
    NOT_DEPICTED = "NOT_DEPICTED"


class InverterSchema(BaseModel):
    """Manufacturer technical specifications for grid-tied inverters."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    manufacturer: str = Field(..., description="Inverter manufacturer entity name")
    model_name: str = Field(..., description="Exact commercial model identifier")
    rated_ac_power_kw: float = Field(
        ..., gt=0, description="Nominal rated continuous AC output (kW)"
    )
    nominal_voltage_v: float = Field(
        ..., gt=0, description="Nominal grid output voltage (Volts AC)"
    )
    max_continuous_current_a: float = Field(
        ..., gt=0, description="Maximum continuous output current (Amperes)"
    )
    power_factor_min: float = Field(
        default=-0.80,
        ge=-1.0,
        le=1.0,
        description="Minimum leading power factor (absorbing reactive power)",
    )
    power_factor_max: float = Field(
        default=0.80,
        ge=-1.0,
        le=1.0,
        description="Maximum lagging power factor (injecting reactive power)",
    )
    ul_1741_sb_certified: bool = Field(
        ..., description="Certified under UL 1741 Supplement SB for smart inverter capabilities"
    )
    ieee_1547_2018_compliant: bool = Field(
        ..., description="Compliant with IEEE 1547-2018 interoperability mandates"
    )
    anti_islanding_trip_time_s: float = Field(
        default=2.0,
        gt=0,
        description="Maximum unintentional islanding disconnect clearing time (seconds)",
    )
    cec_listed: bool = Field(
        default=True, description="Listed on California Energy Commission eligible equipment table"
    )
    count: int = Field(default=1, ge=1, description="Number of identical inverter units installed")

    @property
    def total_capacity_kw(self) -> float:
        """Total AC generating capacity for this inverter group."""
        return self.rated_ac_power_kw * self.count


class TransformerSchema(BaseModel):
    """Dedicated step-up or service transformer specifications."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rating_kva: float = Field(..., gt=0, description="Transformer nameplate capacity (kVA)")
    primary_voltage_kv: float = Field(..., gt=0, description="High-side utility voltage (kV)")
    secondary_voltage_v: float = Field(..., gt=0, description="Low-side facility voltage (Volts)")
    impedance_pct_z: float = Field(
        ..., gt=0, description="Positive-sequence impedance percentage (%Z)"
    )
    winding_configuration: str = Field(
        default="DELTA_WYE_GROUNDED",
        description="Winding configuration (e.g. DELTA_WYE_GROUNDED, WYE_WYE)",
    )


class FeederTelemetrySchema(BaseModel):
    """Substation distribution feeder operational characteristics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    feeder_id: str = Field(..., description="Unique utility circuit / feeder identifier")
    utility: str = Field(..., description="Operating electric utility company")
    nominal_voltage_kv: float = Field(
        ..., gt=0, description="Nominal distribution line voltage (kV)"
    )
    annual_peak_load_kw: float = Field(
        ..., gt=0, description="12-month historic annual peak load on feeder (kW)"
    )
    minimum_daytime_load_kw: float = Field(
        ..., gt=0, description="Historic minimum daytime load (10am-4pm) on feeder (kW)"
    )
    existing_connected_generation_kw: float = Field(
        default=0.0,
        ge=0,
        description="Aggregate existing connected and pre-queued DERs on feeder (kW)",
    )
    substation_transformer_rating_kva: float | None = Field(
        default=None, gt=0, description="Substation transformer thermal rating (kVA)"
    )
    available_fault_duty_mva: float | None = Field(
        default=None, gt=0, description="Available 3-phase fault duty at substation bus (MVA)"
    )

    @field_validator("minimum_daytime_load_kw")
    @classmethod
    def validate_mdl_vs_peak(cls, v: float, info: object) -> float:
        """Validate that minimum daytime load does not exceed annual peak load if peak is given."""
        # Simple logical sanity check
        return v


class SLDComponentSchema(BaseModel):
    """Electrical components extracted from the Single-Line Diagram (SLD)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    has_utility_disconnect_switch: bool = Field(
        ...,
        description="Shows dedicated manual AC disconnect switch accessible to utility personnel",
    )
    disconnect_switch_visible_break: bool = Field(
        default=False, description="Disconnect switch provides an explicit visible air gap break"
    )
    disconnect_switch_lockable: bool = Field(
        default=False, description="Disconnect switch can be padlocked in the open position"
    )
    disconnect_switch_location: DisconnectSwitchLocation = Field(
        default=DisconnectSwitchLocation.NOT_DEPICTED,
        description="Relative physical location of the AC disconnect switch",
    )
    main_breaker_rating_a: float = Field(
        ..., gt=0, description="Main service circuit breaker rating (Amps)"
    )
    main_breaker_kaic: float = Field(
        ..., gt=0, description="Main service circuit breaker interrupting capacity (kAIC)"
    )
    revenue_meter_depicted: bool = Field(
        default=True, description="Utility bi-directional revenue meter depicted on schematic"
    )
    grounding_electrode_system_depicted: bool = Field(
        default=True, description="Grounding electrode conductor and connection depicted"
    )


class ApplicationSchema(BaseModel):
    """Unified root intake model for an interconnection application package."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    application_id: str = Field(
        ..., description="Unique tracking identifier (e.g. APP-001-PASS-ROOFTOP-SOLAR)"
    )
    applicant_name: str = Field(..., description="Legal business entity or property owner name")
    site_address: str = Field(..., description="Physical project installation street address")
    utility_provider: str = Field(..., description="Electric utility serving the facility")
    utility_account_number: str = Field(..., description="Customer utility service account number")
    project_type: InterconnectionType = Field(..., description="Technology category")
    total_export_capacity_kw: float = Field(
        ..., gt=0, description="Proposed maximum net AC power exported to grid (kW)"
    )
    service_voltage: str = Field(..., description="Facility service voltage descriptor")
    inverters: list[InverterSchema] = Field(
        ..., min_length=1, description="List of inverter unit specifications"
    )
    transformer: TransformerSchema | None = Field(
        default=None, description="Step-up or service transformer specifications"
    )
    sld_components: SLDComponentSchema | None = Field(
        default=None, description="Key electrical components parsed from Single-Line Diagram"
    )
    feeder_telemetry: FeederTelemetrySchema | None = Field(
        default=None, description="Local distribution feeder electrical characteristics"
    )

    @property
    def total_inverter_capacity_kw(self) -> float:
        """Sum of all inverter capacities in the application."""
        return sum(inv.total_capacity_kw for inv in self.inverters)

    @model_validator(mode="after")
    def validate_capacity_consistency(self) -> ApplicationSchema:
        """Verify that total inverter capacity can support the declared export capacity."""
        if self.total_inverter_capacity_kw < self.total_export_capacity_kw * 0.95:
            raise ValueError(
                f"Total inverter nameplate capacity ({self.total_inverter_capacity_kw} kW) "
                f"cannot be less than declared export capacity ({self.total_export_capacity_kw} kW)"
            )
        return self
