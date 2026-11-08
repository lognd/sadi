//! Simulator submodule: scenario/fault-plan loading and live runtime control.
//!
//! `sim.open` returns a `Session` plus a [`SimControl`] sharing the same
//! scenario behind a mutex, so Python can change the load program, inject slip
//! steps and reseed noise from any thread while the session streams. All
//! inputs are validated before they replace shared state; a bad plan leaves
//! the running scenario untouched and raises `ScenarioFailure`.
// frob:ticket 01M6W7R226VMAMHYPDBQTAS277
// frob:ticket 01M6W7R2M88JFNKRESHJBD8YVD

use std::sync::{Arc, Mutex, MutexGuard, PoisonError};

use pyo3::prelude::*;
use pyo3::types::PyModule;
use sadi_proto::session::SessionConfig as ProtoConfig;
use sadi_proto::sim::device::{SimConfig, SimDevice};
use sadi_proto::sim::physics::LoadStep;
use sadi_proto::sim::physics::SlipStep;
use sadi_proto::sim::scenario::{Scenario, ScenarioError};
use sadi_proto::sim::signal::SignalSource;
use sadi_proto::sim::signal_faults::FaultPlan;
use sadi_proto::Transport;

use crate::errors::BindError;
use crate::session::Session;

/// Scenario plus the latest simulated time the device sampled.
#[derive(Debug)]
struct SimState {
    scenario: Scenario,
    now_s: f64,
}

/// Mutex-shared scenario: the device samples it, `SimControl` mutates it.
#[derive(Debug, Clone)]
struct SharedSim(Arc<Mutex<SimState>>);

impl SharedSim {
    /// Wraps `scenario` with simulated time starting at zero.
    fn new(scenario: Scenario) -> Self {
        Self(Arc::new(Mutex::new(SimState {
            scenario,
            now_s: 0.0,
        })))
    }

    /// Locks the state; a poisoned lock still holds a valid scenario.
    fn lock(&self) -> MutexGuard<'_, SimState> {
        self.0.lock().unwrap_or_else(|e| {
            tracing::warn!("sim state mutex was poisoned; continuing with its data");
            PoisonError::into_inner(e)
        })
    }

    /// Latest simulated time in seconds the device has sampled.
    fn now_s(&self) -> f64 {
        self.lock().now_s
    }

    /// Replaces the whole scenario after validating it.
    fn set_scenario(&self, scenario: Scenario) -> Result<(), BindError> {
        scenario.validate()?;
        tracing::info!(name = %scenario.name, "sim scenario replaced");
        self.lock().scenario = scenario;
        Ok(())
    }

    /// Replaces the fault plan.
    fn set_fault_plan(&self, plan: FaultPlan) {
        tracing::info!(seed = plan.seed.0, "sim fault plan replaced");
        self.lock().scenario.faults = plan;
    }

    /// Replaces the load program; steps must be finite and strictly increasing.
    fn set_load(&self, steps: Vec<LoadStep>) -> Result<(), BindError> {
        let mut st = self.lock();
        let mut candidate = st.scenario.clone();
        candidate.load.steps = steps;
        candidate.validate().map_err(|e| {
            tracing::warn!(error = %e, "load program rejected");
            e
        })?;
        tracing::info!(
            steps = candidate.load.steps.len(),
            "sim load program replaced"
        );
        st.scenario = candidate;
        Ok(())
    }

    /// Changes the hanging mass by `delta_kg` starting at the current sim time.
    fn change_weight(&self, delta_kg: f64) -> Result<f64, BindError> {
        let mut st = self.lock();
        let now = st.now_s;
        let mass = st.scenario.load.mass_at(now) + delta_kg;
        if !delta_kg.is_finite() || !mass.is_finite() || mass < 0.0 {
            tracing::warn!(delta_kg, mass, "weight change rejected");
            return Err(ScenarioError::Invalid(format!(
                "weight change {delta_kg} kg would give mass {mass} kg (must be finite and >= 0)"
            ))
            .into());
        }
        if st.scenario.load.steps.last().is_some_and(|s| s.t_s >= now) {
            tracing::warn!(now, "weight change rejected: not after the last load step");
            return Err(ScenarioError::Invalid(format!(
                "weight change at t={now} s must be after the last load step"
            ))
            .into());
        }
        st.scenario.load.steps.push(LoadStep {
            t_s: now,
            mass_kg: mass,
        });
        tracing::info!(t_s = now, delta_kg, mass_kg = mass, "sim weight changed");
        Ok(mass)
    }

    /// Injects an instantaneous slip of `strain` at the current sim time.
    fn inject_slip(&self, strain: f64) -> Result<f64, BindError> {
        if !strain.is_finite() {
            tracing::warn!(strain, "slip rejected");
            return Err(ScenarioError::Invalid("slip strain must be finite".into()).into());
        }
        let mut st = self.lock();
        let now = st.now_s;
        st.scenario.faults.slips.push(SlipStep { t_s: now, strain });
        tracing::info!(t_s = now, strain, "sim slip injected");
        Ok(now)
    }

    /// Reseeds the noise generator.
    fn set_seed(&self, seed: u64) {
        tracing::info!(seed, "sim seed changed");
        let mut st = self.lock();
        let faults = st.scenario.faults.clone().with_seed(seed);
        st.scenario.faults = faults;
    }
}

impl SignalSource for SharedSim {
    /// Samples the shared scenario and records `t` as the current sim time.
    fn voltage(&self, ch: usize, t: f64) -> f64 {
        let mut st = self.lock();
        st.now_s = t;
        st.scenario.voltage(ch, t)
    }

    /// Encoder position from the shared scenario.
    fn encoder(&self, t: f64) -> i32 {
        self.lock().scenario.encoder(t)
    }
}

/// Renders a JSON string or JSON-serialisable Python object as JSON text.
fn json_text(obj: &Bound<'_, PyAny>) -> Result<String, BindError> {
    if let Ok(s) = obj.extract::<String>() {
        return Ok(s);
    }
    let py = obj.py();
    let dumps = py
        .import("json")
        .and_then(|m| m.call_method1("dumps", (obj,)))
        .and_then(|s| s.extract::<String>());
    dumps.map_err(|e| {
        tracing::warn!(error = %e, "object is not JSON serialisable");
        BindError::Config(format!("value is not JSON serialisable: {e}"))
    })
}

/// Parses a scenario from a builtin name, JSON text or a dict.
fn scenario_from(obj: &Bound<'_, PyAny>) -> Result<Scenario, BindError> {
    let text = json_text(obj)?;
    if text.trim_start().starts_with('{') {
        Ok(Scenario::from_json(&text)?)
    } else {
        Ok(Scenario::builtin(&text)?)
    }
}

/// Parses and validates a fault plan from JSON text or a dict.
fn plan_from(obj: &Bound<'_, PyAny>) -> Result<FaultPlan, BindError> {
    let text = json_text(obj)?;
    serde_plan(&text)
}

/// Parses fault-plan JSON by routing through a scenario so no serde dependency is needed.
fn serde_plan(text: &str) -> Result<FaultPlan, BindError> {
    let wrapped = format!("{{\"faults\": {text}}}");
    let sc = Scenario::from_json(&wrapped).map_err(|e| {
        tracing::warn!(error = %e, "fault plan rejected");
        e
    })?;
    Ok(sc.faults)
}

/// Live handle for changing a running simulator; safe to share across threads.
#[pyclass(frozen, module = "sadi_py.sim", name = "SimControl")]
pub struct SimControl {
    shared: SharedSim,
}

#[pymethods]
impl SimControl {
    /// Simulated time in seconds the device last sampled.
    #[getter]
    fn now_s(&self) -> f64 {
        self.shared.now_s()
    }

    /// Hanging mass in kg at the current simulated time.
    #[getter]
    fn mass_kg(&self) -> f64 {
        let st = self.shared.lock();
        st.scenario.load.mass_at(st.now_s)
    }

    /// Number of slip steps injected or configured.
    #[getter]
    fn slip_count(&self) -> usize {
        self.shared.lock().scenario.faults.slips.len()
    }

    /// Current noise seed.
    #[getter]
    fn seed(&self) -> u64 {
        self.shared.lock().scenario.faults.seed.0
    }

    /// Replaces the scenario (name, JSON text or dict).
    fn set_scenario(&self, scenario: &Bound<'_, PyAny>) -> Result<(), BindError> {
        self.shared.set_scenario(scenario_from(scenario)?)
    }

    /// Replaces the fault plan (JSON text or dict).
    fn set_fault_plan(&self, plan: &Bound<'_, PyAny>) -> Result<(), BindError> {
        self.shared.set_fault_plan(plan_from(plan)?);
        Ok(())
    }

    /// Replaces the load program with `(t_s, mass_kg)` steps.
    fn set_load_program(&self, steps: Vec<(f64, f64)>) -> Result<(), BindError> {
        self.shared.set_load(
            steps
                .into_iter()
                .map(|(t_s, mass_kg)| LoadStep { t_s, mass_kg })
                .collect(),
        )
    }

    /// Adds `kg` of hanging mass now; returns the new total mass.
    fn add_weight(&self, kg: f64) -> Result<f64, BindError> {
        if !kg.is_finite() || kg < 0.0 {
            return Err(BindError::Config(
                "add_weight needs a finite kg >= 0".into(),
            ));
        }
        self.shared.change_weight(kg)
    }

    /// Removes `kg` of hanging mass now; returns the new total mass.
    fn remove_weight(&self, kg: f64) -> Result<f64, BindError> {
        if !kg.is_finite() || kg < 0.0 {
            return Err(BindError::Config(
                "remove_weight needs a finite kg >= 0".into(),
            ));
        }
        self.shared.change_weight(-kg)
    }

    /// Injects a slip step of `strain` now; returns the sim time it took effect.
    fn inject_slip(&self, strain: f64) -> Result<f64, BindError> {
        self.shared.inject_slip(strain)
    }

    /// Reseeds the noise generator.
    fn set_seed(&self, seed: u64) {
        self.shared.set_seed(seed);
    }
}

/// Opens a simulator session and its runtime control handle.
///
/// `scenario` is a builtin name, JSON text or a dict; `seed` overrides the
/// plan's seed.
#[pyfunction]
#[pyo3(signature = (scenario, seed=None))]
fn open(
    scenario: &Bound<'_, PyAny>,
    seed: Option<u64>,
) -> Result<(Session, SimControl), BindError> {
    let sc = scenario_from(scenario)?;
    let shared = SharedSim::new(sc);
    if let Some(seed) = seed {
        shared.set_seed(seed);
    }
    let sim = SimDevice::new(Box::new(shared.clone()), SimConfig::default());
    tracing::info!(?seed, "controllable simulator opened");
    let session = Session::new(Box::new(sim) as Box<dyn Transport>, ProtoConfig::default());
    Ok((session, SimControl { shared }))
}

/// Validates a scenario (name, JSON text or dict) without opening anything.
#[pyfunction]
fn validate_scenario(scenario: &Bound<'_, PyAny>) -> Result<(), BindError> {
    scenario_from(scenario).map(|_| ())
}

/// Validates a fault plan (JSON text or dict) without opening anything.
#[pyfunction]
fn validate_fault_plan(plan: &Bound<'_, PyAny>) -> Result<(), BindError> {
    plan_from(plan).map(|_| ())
}

/// Registers the `sim` submodule.
pub(crate) fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    let sub = PyModule::new(m.py(), "sim")?;
    sub.add_class::<SimControl>()?;
    sub.add_function(wrap_pyfunction!(open, &sub)?)?;
    sub.add_function(wrap_pyfunction!(validate_scenario, &sub)?)?;
    sub.add_function(wrap_pyfunction!(validate_fault_plan, &sub)?)?;
    m.add_submodule(&sub)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn shared() -> SharedSim {
        SharedSim::new(Scenario::builtin("clean").expect("clean builtin"))
    }

    // frob:tests crates/sadi-py/src/sim.rs::SharedSim.change_weight
    #[test]
    fn weight_changes_at_sim_now() {
        let s = shared();
        s.set_load(Vec::new()).expect("empty load");
        s.voltage(0, 1.0);
        assert_eq!(s.change_weight(0.5).expect("add"), 0.5);
        s.voltage(0, 2.0);
        assert_eq!(s.change_weight(-0.2).expect("remove"), 0.3);
        assert!(s.change_weight(-5.0).is_err());
    }

    // frob:tests crates/sadi-py/src/sim.rs::SharedSim.set_load
    #[test]
    fn unordered_load_is_rejected_and_state_kept() {
        let s = shared();
        let bad = vec![
            LoadStep {
                t_s: 2.0,
                mass_kg: 1.0,
            },
            LoadStep {
                t_s: 1.0,
                mass_kg: 2.0,
            },
        ];
        assert!(matches!(s.set_load(bad), Err(BindError::Scenario(_))));
        assert!(s
            .set_load(vec![LoadStep {
                t_s: 0.0,
                mass_kg: 1.0
            }])
            .is_ok());
    }

    // frob:tests crates/sadi-py/src/sim.rs::SharedSim.inject_slip
    #[test]
    fn slip_changes_voltage_after_now() {
        let s = shared();
        s.set_load(vec![LoadStep {
            t_s: 0.0,
            mass_kg: 1.0,
        }])
        .expect("load");
        let before = s.voltage(0, 1.0);
        s.inject_slip(1e-3).expect("slip");
        assert_ne!(before, s.voltage(0, 1.0));
        assert!(s.inject_slip(f64::NAN).is_err());
    }

    // frob:tests crates/sadi-py/src/sim.rs::serde_plan
    #[test]
    fn bad_plan_is_typed_error() {
        assert!(matches!(
            serde_plan("{\"bogus\": 1}"),
            Err(BindError::Scenario(_))
        ));
        assert!(serde_plan("{\"seed\": 7}").is_ok());
    }

    // frob:tests crates/sadi-py/src/sim.rs::SharedSim.set_seed
    #[test]
    fn concurrent_control_is_safe() {
        let s = shared();
        let handles: Vec<_> = (0..4u64)
            .map(|i| {
                let s = s.clone();
                std::thread::spawn(move || {
                    for k in 0..100 {
                        s.voltage(0, k as f64);
                        s.set_seed(i);
                        let _ = s.inject_slip(1e-6);
                    }
                })
            })
            .collect();
        for h in handles {
            h.join().expect("thread");
        }
        assert_eq!(s.lock().scenario.faults.slips.len(), 400);
    }
}
