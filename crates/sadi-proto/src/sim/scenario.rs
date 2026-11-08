//! Named simulator scenarios: physics plus fault plan, loadable from JSON.
//!
//! The JSON files in `crates/sadi-proto/scenarios/` are compiled in and are
//! the shared oracle for settle, creep and slip logic downstream.

use serde::{Deserialize, Serialize};
use tracing::{debug, error, info};

use crate::sim::physics::{self, LoadProgram, LvdtSpec, WireSpec};
use crate::sim::signal::SignalSource;
use crate::sim::signal_faults::{FaultPlan, LVDT_CHANNEL};

/// Failure to build a scenario.
#[derive(Debug, thiserror::Error)]
#[non_exhaustive]
pub enum ScenarioError {
    /// JSON was malformed or had unknown fields.
    #[error("invalid scenario JSON: {0}")]
    Parse(#[from] serde_json::Error),
    /// Parsed but physically or logically inconsistent.
    #[error("invalid scenario: {0}")]
    Invalid(String),
    /// No built-in scenario has this name.
    #[error("unknown scenario {0:?}")]
    Unknown(String),
}

/// Names of the shipped scenarios, in a stable order.
pub const SCENARIO_NAMES: [&str; 7] = [
    "clean",
    "noisy",
    "drifting",
    "creeping",
    "slipping",
    "saturating",
    "combined",
];

const CLEAN: &str = include_str!("../../scenarios/clean.json");
const NOISY: &str = include_str!("../../scenarios/noisy.json");
const DRIFTING: &str = include_str!("../../scenarios/drifting.json");
const CREEPING: &str = include_str!("../../scenarios/creeping.json");
const SLIPPING: &str = include_str!("../../scenarios/slipping.json");
const SATURATING: &str = include_str!("../../scenarios/saturating.json");
const COMBINED: &str = include_str!("../../scenarios/combined.json");

/// A complete simulated specimen test, usable as a [`SignalSource`].
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Scenario {
    /// Scenario name.
    pub name: String,
    /// Human description of what the scenario exercises.
    pub description: String,
    /// Wire geometry and material.
    pub wire: WireSpec,
    /// LVDT transfer function.
    pub lvdt: LvdtSpec,
    /// Timed weight steps.
    pub load: LoadProgram,
    /// Injected faults.
    pub faults: FaultPlan,
}

impl Default for Scenario {
    fn default() -> Self {
        Self {
            name: "default".into(),
            description: String::new(),
            wire: WireSpec::default(),
            lvdt: LvdtSpec::default(),
            load: LoadProgram::default(),
            faults: FaultPlan::default(),
        }
    }
}

impl Scenario {
    /// Parse and validate a scenario from JSON text.
    pub fn from_json(text: &str) -> Result<Self, ScenarioError> {
        let s: Scenario = serde_json::from_str(text).map_err(|e| {
            error!(%e, "scenario parse failed");
            e
        })?;
        s.validate()?;
        physics::log_model(&s.wire, &s.lvdt, &s.load);
        info!(name = %s.name, "scenario loaded");
        Ok(s)
    }

    /// Load one of the shipped scenarios by name (see [`SCENARIO_NAMES`]).
    pub fn builtin(name: &str) -> Result<Self, ScenarioError> {
        let text = match name {
            "clean" => CLEAN,
            "noisy" => NOISY,
            "drifting" => DRIFTING,
            "creeping" => CREEPING,
            "slipping" => SLIPPING,
            "saturating" => SATURATING,
            "combined" => COMBINED,
            other => {
                error!(name = other, "unknown scenario");
                return Err(ScenarioError::Unknown(other.to_owned()));
            }
        };
        Self::from_json(text)
    }

    /// Reject what the field newtypes cannot express (load step ordering).
    #[must_use = "validation result must be checked"]
    pub fn validate(&self) -> Result<(), ScenarioError> {
        if !self.load.is_ordered() {
            return Err(ScenarioError::Invalid(
                "load steps must be finite and strictly increasing".into(),
            ));
        }
        debug!(name = %self.name, "scenario validated");
        Ok(())
    }

    /// Noise-free, fault-free-of-noise LVDT-channel voltage before drift and saturation.
    #[must_use]
    pub fn clean_lvdt_v(&self, t: f64) -> f64 {
        let eps = physics::strain_at(
            &self.wire,
            &self.load,
            &self.faults.creep,
            &self.faults.slips,
            t,
        );
        self.lvdt
            .voltage(self.wire.l0_m.get() * (1.0 + eps), self.wire.l0_m.get())
    }

    /// Builder step: replace the fault plan.
    #[must_use]
    pub fn with_faults(mut self, faults: FaultPlan) -> Self {
        self.faults = faults;
        self
    }

    /// Copy of this scenario with noise switched off (for exact-recovery tests).
    #[must_use]
    pub fn without_noise(&self) -> Self {
        let mut s = self.clone();
        s.faults.noise.sd_v = crate::sim::physics::NonNegative::lit(0.0);
        s
    }
}

impl SignalSource for Scenario {
    fn voltage(&self, ch: usize, t: f64) -> f64 {
        let clean = if ch == LVDT_CHANNEL {
            self.clean_lvdt_v(t)
        } else {
            0.0
        };
        self.faults.apply(ch, t, clean)
    }

    fn encoder(&self, _t: f64) -> i32 {
        0
    }
}
