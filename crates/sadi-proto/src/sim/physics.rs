//! Copper-wire and LVDT physics: load program to stress, strain and volts.
//!
//! Strain model (all additive): elastic `sigma/E`, plastic hardening past
//! yield (permanent, set by the peak stress so far), log-time creep after
//! each load change (Boltzmann superposition), and slip jumps that happen
//! with no load change. The LVDT maps length to volts linearly.

use serde::{Deserialize, Serialize};
use tracing::{debug, trace};

/// Standard gravity in m/s^2, used to turn hanging mass into force.
pub const GRAVITY: f64 = 9.80665;
/// Short-sample gauge length in metres (L0 is correct for the short sample).
pub const DEFAULT_L0_M: f64 = 0.08313;
/// Calibration slope from the reference calibration, metres per volt.
pub const DEFAULT_LVDT_SLOPE_M_PER_V: f64 = 2.114583e-3;

/// Error for a value that violates a newtype invariant.
#[derive(Debug, Clone, Copy, PartialEq, thiserror::Error)]
#[error("value must be {expected}, got {got}")]
pub struct RangeError {
    /// Human description of the required range.
    pub expected: &'static str,
    /// Offending value.
    pub got: f64,
}

/// A finite, strictly positive quantity; invalid values cannot be built.
#[derive(Debug, Clone, Copy, PartialEq, PartialOrd, Serialize, Deserialize)]
#[serde(try_from = "f64", into = "f64")]
pub struct Positive(f64);

impl Positive {
    /// Smart constructor: accepts only finite values greater than zero.
    pub fn new(v: f64) -> Result<Self, RangeError> {
        if v.is_finite() && v > 0.0 {
            Ok(Self(v))
        } else {
            Err(RangeError {
                expected: "finite and > 0",
                got: v,
            })
        }
    }

    /// Wrapped value.
    #[must_use]
    pub fn get(self) -> f64 {
        self.0
    }

    /// Constant known valid at the call site (programmer bug if not).
    pub(crate) fn lit(v: f64) -> Self {
        Self::new(v).expect("literal default must be positive")
    }
}

impl TryFrom<f64> for Positive {
    type Error = RangeError;
    fn try_from(v: f64) -> Result<Self, RangeError> {
        Self::new(v)
    }
}

impl From<Positive> for f64 {
    fn from(p: Positive) -> f64 {
        p.0
    }
}

/// A finite quantity that is zero or greater; invalid values cannot be built.
#[derive(Debug, Clone, Copy, PartialEq, PartialOrd, Serialize, Deserialize)]
#[serde(try_from = "f64", into = "f64")]
pub struct NonNegative(f64);

impl NonNegative {
    /// Smart constructor: accepts only finite values >= 0.
    pub fn new(v: f64) -> Result<Self, RangeError> {
        if v.is_finite() && v >= 0.0 {
            Ok(Self(v))
        } else {
            Err(RangeError {
                expected: "finite and >= 0",
                got: v,
            })
        }
    }

    /// Wrapped value.
    #[must_use]
    pub fn get(self) -> f64 {
        self.0
    }

    /// Constant known valid at the call site (programmer bug if not).
    pub(crate) fn lit(v: f64) -> Self {
        Self::new(v).expect("literal default must be non-negative")
    }
}

impl TryFrom<f64> for NonNegative {
    type Error = RangeError;
    fn try_from(v: f64) -> Result<Self, RangeError> {
        Self::new(v)
    }
}

impl From<NonNegative> for f64 {
    fn from(p: NonNegative) -> f64 {
        p.0
    }
}

/// Copper wire geometry and mechanical constants.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct WireSpec {
    /// Wire diameter in metres.
    pub diameter_m: Positive,
    /// Unloaded gauge length L0 in metres.
    pub l0_m: Positive,
    /// Elastic (Young's) modulus E in pascals.
    pub youngs_modulus_pa: Positive,
    /// Stress at which plastic flow starts, in pascals.
    pub yield_stress_pa: f64,
    /// Plastic hardening modulus (stress per plastic strain) in pascals.
    pub hardening_modulus_pa: Positive,
}

impl Default for WireSpec {
    fn default() -> Self {
        Self {
            diameter_m: Positive::lit(0.5e-3),
            l0_m: Positive::lit(DEFAULT_L0_M),
            youngs_modulus_pa: Positive::lit(110e9),
            yield_stress_pa: 70e6,
            hardening_modulus_pa: Positive::lit(1.5e9),
        }
    }
}

impl WireSpec {
    /// Cross-section area in square metres.
    #[must_use]
    pub fn area_m2(&self) -> f64 {
        std::f64::consts::PI * self.diameter_m.get() * self.diameter_m.get() / 4.0
    }
}

/// One timed weight change: from `t_s` onward the hanging mass is `mass_kg`.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LoadStep {
    /// Time of the change in seconds.
    pub t_s: f64,
    /// Total hanging mass after the change, in kilograms.
    pub mass_kg: f64,
}

/// Timed weight steps; mass is zero before the first step.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct LoadProgram {
    /// Steps in strictly increasing time order.
    pub steps: Vec<LoadStep>,
}

impl LoadProgram {
    /// Hanging mass in kilograms at time `t` seconds.
    #[must_use]
    pub fn mass_at(&self, t: f64) -> f64 {
        self.steps
            .iter()
            .take_while(|s| s.t_s <= t)
            .last()
            .map_or(0.0, |s| s.mass_kg)
    }

    /// Peak hanging mass in kilograms reached up to and including `t`.
    #[must_use]
    pub fn peak_mass_until(&self, t: f64) -> f64 {
        self.steps
            .iter()
            .take_while(|s| s.t_s <= t)
            .map(|s| s.mass_kg)
            .fold(0.0, f64::max)
    }

    /// True when the steps are finite and strictly increasing in time.
    #[must_use]
    pub fn is_ordered(&self) -> bool {
        self.steps
            .iter()
            .all(|s| s.t_s.is_finite() && s.mass_kg.is_finite())
            && self.steps.windows(2).all(|w| w[0].t_s < w[1].t_s)
    }
}

/// Log-time creep law: each load change adds `amp * ln(1 + dt/tau)`.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct CreepLaw {
    /// Creep amplitude per ln-unit as a fraction of the elastic strain step.
    pub coeff: f64,
    /// Time constant in seconds that regularises the log at dt = 0.
    pub tau_s: Positive,
}

impl Default for CreepLaw {
    fn default() -> Self {
        Self {
            coeff: 0.0,
            tau_s: Positive::lit(1.0),
        }
    }
}

/// A sudden strain jump with no load change (clamp slip).
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SlipStep {
    /// Time of the slip in seconds.
    pub t_s: f64,
    /// Strain added permanently at and after `t_s` (dimensionless).
    pub strain: f64,
}

/// Sign convention of the LVDT output.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
#[non_exhaustive]
pub enum Polarity {
    /// Longer wire reads more positive volts.
    #[default]
    Positive,
    /// Longer wire reads more negative volts.
    Negative,
}

impl Polarity {
    /// Multiplier (+1.0 or -1.0) applied to the LVDT voltage.
    #[must_use]
    pub fn factor(self) -> f64 {
        match self {
            Polarity::Positive => 1.0,
            Polarity::Negative => -1.0,
        }
    }
}

/// LVDT transfer: `V = sign * (length - offset) / slope`.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct LvdtSpec {
    /// Calibration slope in metres per volt.
    pub slope_m_per_v: Positive,
    /// Length in metres that reads 0 V; `None` puts the unloaded length at 1 V.
    pub offset_m: Option<f64>,
    /// Output sign convention.
    pub polarity: Polarity,
}

impl Default for LvdtSpec {
    fn default() -> Self {
        Self {
            slope_m_per_v: Positive::lit(DEFAULT_LVDT_SLOPE_M_PER_V),
            offset_m: None,
            polarity: Polarity::Positive,
        }
    }
}

impl LvdtSpec {
    /// Offset in metres, resolving the default against the unloaded length.
    #[must_use]
    pub fn resolved_offset_m(&self, l0_m: f64) -> f64 {
        self.offset_m.unwrap_or(l0_m - self.slope_m_per_v.get())
    }

    /// Clean LVDT volts for a wire of length `length_m`.
    #[must_use]
    pub fn voltage(&self, length_m: f64, l0_m: f64) -> f64 {
        self.polarity.factor() * (length_m - self.resolved_offset_m(l0_m))
            / self.slope_m_per_v.get()
    }

    /// Invert [`LvdtSpec::voltage`]: wire length in metres from volts.
    #[must_use]
    pub fn length_m(&self, volts: f64, l0_m: f64) -> f64 {
        self.polarity.factor() * volts * self.slope_m_per_v.get() + self.resolved_offset_m(l0_m)
    }
}

/// Engineering stress in pascals at time `t` for the load program.
#[must_use]
pub fn stress_pa(wire: &WireSpec, load: &LoadProgram, t: f64) -> f64 {
    load.mass_at(t) * GRAVITY / wire.area_m2()
}

/// Permanent plastic strain from the peak stress reached by time `t`.
#[must_use]
pub fn plastic_strain(wire: &WireSpec, load: &LoadProgram, t: f64) -> f64 {
    let peak = load.peak_mass_until(t) * GRAVITY / wire.area_m2();
    let eps = ((peak - wire.yield_stress_pa) / wire.hardening_modulus_pa.get()).max(0.0);
    if eps > 0.0 {
        trace!(t, peak_pa = peak, eps, "plastic regime");
    }
    eps
}

/// Creep strain at `t`: superposed log-time response to every stress change.
#[must_use]
pub fn creep_strain(wire: &WireSpec, load: &LoadProgram, creep: &CreepLaw, t: f64) -> f64 {
    if creep.coeff == 0.0 {
        return 0.0;
    }
    let area = wire.area_m2();
    let mut prev_stress = 0.0;
    let mut total = 0.0;
    for step in load.steps.iter().take_while(|s| s.t_s <= t) {
        let stress = step.mass_kg * GRAVITY / area;
        let amp = creep.coeff * (stress - prev_stress) / wire.youngs_modulus_pa.get();
        total += amp * (1.0 + (t - step.t_s) / creep.tau_s.get()).ln();
        prev_stress = stress;
    }
    total
}

/// Sum of slip strains that have occurred by time `t`.
#[must_use]
pub fn slip_strain(slips: &[SlipStep], t: f64) -> f64 {
    slips.iter().filter(|s| s.t_s <= t).map(|s| s.strain).sum()
}

/// Total strain at `t`: elastic + plastic + creep + slip.
#[must_use]
pub fn strain_at(
    wire: &WireSpec,
    load: &LoadProgram,
    creep: &CreepLaw,
    slips: &[SlipStep],
    t: f64,
) -> f64 {
    let elastic = stress_pa(wire, load, t) / wire.youngs_modulus_pa.get();
    elastic
        + plastic_strain(wire, load, t)
        + creep_strain(wire, load, creep, t)
        + slip_strain(slips, t)
}

/// Log the physical parameters once when a model is assembled.
pub(crate) fn log_model(wire: &WireSpec, lvdt: &LvdtSpec, load: &LoadProgram) {
    debug!(
        d_m = wire.diameter_m.get(),
        l0_m = wire.l0_m.get(),
        e_pa = wire.youngs_modulus_pa.get(),
        slope = lvdt.slope_m_per_v.get(),
        steps = load.steps.len(),
        "physics model assembled"
    );
}

#[cfg(test)]
mod tests {
    use super::*;

    fn prog() -> LoadProgram {
        LoadProgram {
            steps: vec![
                LoadStep {
                    t_s: 10.0,
                    mass_kg: 0.5,
                },
                LoadStep {
                    t_s: 20.0,
                    mass_kg: 0.0,
                },
            ],
        }
    }

    #[test]
    fn mass_follows_steps() {
        let p = prog();
        assert_eq!(p.mass_at(5.0), 0.0);
        assert_eq!(p.mass_at(10.0), 0.5);
        assert_eq!(p.mass_at(25.0), 0.0);
        assert_eq!(p.peak_mass_until(25.0), 0.5);
        assert!(p.is_ordered());
    }

    #[test]
    fn lvdt_round_trips() {
        let l = LvdtSpec {
            polarity: Polarity::Negative,
            ..LvdtSpec::default()
        };
        let v = l.voltage(0.0835, DEFAULT_L0_M);
        assert!((l.length_m(v, DEFAULT_L0_M) - 0.0835).abs() < 1e-12);
    }
}
