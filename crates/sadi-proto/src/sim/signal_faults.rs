//! Serde-configurable signal faults: noise, drift, creep, slip, saturation.
//!
//! Noise is a pure function of `(seed, channel, sample index)` so the
//! simulator is deterministic and `SignalSource::voltage(&self, ..)` needs
//! no mutable state.

use serde::{Deserialize, Serialize};
use tracing::trace;

use crate::sim::physics::{CreepLaw, NonNegative, Positive, SlipStep};

/// Channel carrying the LVDT; drift and saturation only affect this one.
pub const LVDT_CHANNEL: usize = 0;
/// Per-sample noise sd in volts from the preliminary data analysis.
pub const DEFAULT_NOISE_SD_V: f64 = 0.0345;
/// ADC input limit in volts beyond which the response saturates.
pub const DEFAULT_SATURATION_V: f64 = 4.9;

/// Seed of the deterministic noise generator.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(transparent)]
pub struct Seed(pub u64);

/// The kinds of fault a [`FaultPlan`] can inject.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[non_exhaustive]
pub enum FaultKind {
    /// Per-sample noise.
    Noise,
    /// Linear or thermal drift.
    Drift,
    /// Log-time creep after load changes.
    Creep,
    /// Sudden strain jumps with no load change.
    Slip,
    /// Clamp or fold at the ADC limit.
    Saturation,
}

impl FaultKind {
    /// Every kind, in a stable order.
    pub const ALL: [FaultKind; 5] = [
        FaultKind::Noise,
        FaultKind::Drift,
        FaultKind::Creep,
        FaultKind::Slip,
        FaultKind::Saturation,
    ];

    /// Whether `plan` actually injects this kind of fault.
    #[must_use]
    pub fn is_active(self, plan: &FaultPlan) -> bool {
        match self {
            FaultKind::Noise => plan.noise.sd_v.get() > 0.0,
            FaultKind::Drift => plan.drift.linear_v_per_s != 0.0 || plan.drift.thermal_amp_v != 0.0,
            FaultKind::Creep => plan.creep.coeff != 0.0,
            FaultKind::Slip => !plan.slips.is_empty(),
            FaultKind::Saturation => plan.saturation.is_some(),
        }
    }
}

/// Noise colour.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
#[non_exhaustive]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum NoiseKind {
    /// Independent gaussian samples.
    White,
    /// Moving average of `window` white samples, rescaled to keep the sd.
    Coloured {
        /// Number of samples averaged (>= 1).
        window: u32,
    },
}

/// Per-sample noise configuration.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct NoiseSpec {
    /// Standard deviation in volts (0 disables noise).
    pub sd_v: NonNegative,
    /// Noise colour.
    pub kind: NoiseKind,
}

impl Default for NoiseSpec {
    fn default() -> Self {
        Self {
            sd_v: NonNegative::lit(DEFAULT_NOISE_SD_V),
            kind: NoiseKind::White,
        }
    }
}

/// Slow additive drift of the LVDT voltage.
#[derive(Debug, Clone, Copy, Default, PartialEq, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct DriftSpec {
    /// Linear drift in volts per second.
    pub linear_v_per_s: f64,
    /// Thermal sinusoid amplitude in volts.
    pub thermal_amp_v: f64,
    /// Thermal period in seconds (ignored when the amplitude is 0).
    pub thermal_period_s: f64,
}

/// What happens beyond the saturation limit.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
#[non_exhaustive]
pub enum SaturationMode {
    /// Output is held at the limit.
    Clamp,
    /// Output reflects back (triangle wave), so voltages repeat.
    Fold,
}

/// Saturation configuration.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SaturationSpec {
    /// Limit in volts (|V| above this saturates).
    pub limit_v: Positive,
    /// Clamp or fold response.
    pub mode: SaturationMode,
}

/// Complete fault plan for a simulated run.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct FaultPlan {
    /// Seed for the deterministic noise generator.
    pub seed: Seed,
    /// Noise sample rate in Hz: one independent draw per 1/rate seconds.
    pub sample_rate_hz: Positive,
    /// Noise configuration.
    pub noise: NoiseSpec,
    /// Drift configuration.
    pub drift: DriftSpec,
    /// Creep law injected into the wire physics.
    pub creep: CreepLaw,
    /// Slip steps injected into the wire physics (no load change).
    pub slips: Vec<SlipStep>,
    /// Optional saturation response.
    pub saturation: Option<SaturationSpec>,
}

impl Default for FaultPlan {
    fn default() -> Self {
        Self {
            seed: Seed(0),
            sample_rate_hz: Positive::new(10.0).expect("10 Hz is positive"),
            noise: NoiseSpec::default(),
            drift: DriftSpec::default(),
            creep: CreepLaw::default(),
            slips: Vec::new(),
            saturation: None,
        }
    }
}

pub(crate) fn splitmix64(x: u64) -> u64 {
    let mut z = x.wrapping_add(0x9E37_79B9_7F4A_7C15);
    z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    z ^ (z >> 31)
}

/// Open-interval uniform in (0, 1) from 64 random bits.
pub(crate) fn unit(h: u64) -> f64 {
    ((h >> 11) as f64 + 0.5) / (1u64 << 53) as f64
}

/// Standard normal deviate keyed by seed, channel and sample index.
fn gauss(seed: u64, ch: usize, idx: i64) -> f64 {
    let h1 =
        splitmix64(splitmix64(seed ^ (ch as u64).wrapping_mul(0xD6E8_FEB8_6659_FD93)) ^ idx as u64);
    let h2 = splitmix64(h1);
    (-2.0 * unit(h1).ln()).sqrt() * (std::f64::consts::TAU * unit(h2)).cos()
}

/// Fold `v` into `[-limit, limit]` as a triangle wave so voltages repeat.
#[must_use]
pub fn fold(v: f64, limit: f64) -> f64 {
    let m = v.abs().rem_euclid(2.0 * limit);
    let r = if m <= limit { m } else { 2.0 * limit - m };
    v.signum() * r
}

impl FaultPlan {
    /// Builder step: set the noise seed.
    #[must_use]
    pub fn with_seed(mut self, seed: u64) -> Self {
        self.seed = Seed(seed);
        self
    }

    /// Builder step: replace the noise configuration.
    #[must_use]
    pub fn with_noise(mut self, noise: NoiseSpec) -> Self {
        self.noise = noise;
        self
    }

    /// Builder step: replace the saturation response.
    #[must_use]
    pub fn with_saturation(mut self, sat: Option<SaturationSpec>) -> Self {
        self.saturation = sat;
        self
    }

    /// Builder step: replace the drift configuration.
    #[must_use]
    pub fn with_drift(mut self, drift: DriftSpec) -> Self {
        self.drift = drift;
        self
    }

    /// Kinds of fault this plan actually injects.
    #[must_use]
    pub fn active_kinds(&self) -> Vec<FaultKind> {
        FaultKind::ALL
            .into_iter()
            .filter(|k| k.is_active(self))
            .collect()
    }

    /// Noise voltage for channel `ch` at time `t` seconds.
    #[must_use]
    pub fn noise_v(&self, ch: usize, t: f64) -> f64 {
        if self.noise.sd_v.get() == 0.0 {
            return 0.0;
        }
        let idx = (t * self.sample_rate_hz.get()).round() as i64;
        let unit_noise = match self.noise.kind {
            NoiseKind::White => gauss(self.seed.0, ch, idx),
            NoiseKind::Coloured { window } => {
                let w = i64::from(window.max(1));
                let sum: f64 = (0..w).map(|k| gauss(self.seed.0, ch, idx - k)).sum();
                sum / (w as f64).sqrt()
            }
        };
        self.noise.sd_v.get() * unit_noise
    }

    /// Drift voltage added to the LVDT channel at time `t` seconds.
    #[must_use]
    pub fn drift_v(&self, t: f64) -> f64 {
        let d = &self.drift;
        let thermal = if d.thermal_amp_v != 0.0 && d.thermal_period_s > 0.0 {
            d.thermal_amp_v * (std::f64::consts::TAU * t / d.thermal_period_s).sin()
        } else {
            0.0
        };
        d.linear_v_per_s * t + thermal
    }

    /// Apply the saturation response (if configured) to a voltage.
    #[must_use]
    pub fn saturate(&self, v: f64) -> f64 {
        let Some(sat) = self.saturation else { return v };
        let limit = sat.limit_v.get();
        if v.abs() <= limit {
            return v;
        }
        let out = match sat.mode {
            SaturationMode::Clamp => v.signum() * limit,
            SaturationMode::Fold => fold(v, limit),
        };
        trace!(v, out, mode = ?sat.mode, "saturation engaged");
        out
    }

    /// Turn a clean voltage into the faulted voltage seen on `ch` at `t`.
    #[must_use]
    pub fn apply(&self, ch: usize, t: f64, clean_v: f64) -> f64 {
        if ch == LVDT_CHANNEL {
            self.saturate(clean_v + self.drift_v(t) + self.noise_v(ch, t))
        } else {
            clean_v + self.noise_v(ch, t)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fold_reflects_and_repeats() {
        assert!((fold(5.0, 4.9) - 4.8).abs() < 1e-12);
        assert!((fold(-5.0, 4.9) + 4.8).abs() < 1e-12);
        assert!((fold(2.0, 4.9) - 2.0).abs() < 1e-12);
        assert!((fold(9.8, 4.9)).abs() < 1e-12);
    }

    #[test]
    fn noise_is_deterministic() {
        let p = FaultPlan::default().with_seed(7);
        assert_eq!(p.noise_v(0, 1.3), p.noise_v(0, 1.3));
        assert_ne!(p.noise_v(0, 1.3), p.noise_v(1, 1.3));
    }
}
