//! Statistical and physical tests of the simulator oracle (ticket 8XCPH41).
//!
//! Each test recovers an injected quantity from sampled output only.

use sadi_proto::sim::physics::{
    LoadProgram, LoadStep, NonNegative, Polarity, Positive, SlipStep, DEFAULT_L0_M, GRAVITY,
};
use sadi_proto::sim::scenario::{Scenario, ScenarioError, SCENARIO_NAMES};
use sadi_proto::sim::signal::SignalSource;
use sadi_proto::sim::signal_faults::{
    FaultKind, FaultPlan, NoiseKind, NoiseSpec, SaturationMode, SaturationSpec,
};

fn scen(name: &str) -> Scenario {
    Scenario::builtin(name).expect("builtin scenario")
}

/// Strain recovered from an LVDT voltage via the scenario's transfer function.
fn strain_of(s: &Scenario, v: f64) -> f64 {
    let l0 = s.wire.l0_m.get();
    (s.lvdt.length_m(v, l0) - l0) / l0
}

fn mean_v(s: &Scenario, t0: f64, t1: f64) -> f64 {
    let n = ((t1 - t0) * 10.0) as usize;
    (0..n)
        .map(|i| s.voltage(0, t0 + i as f64 / 10.0))
        .sum::<f64>()
        / n as f64
}

fn ls_slope(x: &[f64], y: &[f64]) -> f64 {
    let n = x.len() as f64;
    let (mx, my) = (x.iter().sum::<f64>() / n, y.iter().sum::<f64>() / n);
    let sxy: f64 = x.iter().zip(y).map(|(a, b)| (a - mx) * (b - my)).sum();
    let sxx: f64 = x.iter().map(|a| (a - mx).powi(2)).sum();
    sxy / sxx
}

// frob:tests crates/sadi-proto/src/sim/scenario.rs::Scenario.builtin
#[test]
fn all_named_scenarios_load() {
    for name in SCENARIO_NAMES {
        let s = scen(name);
        assert_eq!(s.name, name);
    }
    assert!(matches!(
        Scenario::builtin("nope"),
        Err(ScenarioError::Unknown(_))
    ));
}

#[test]
fn unknown_fields_and_bad_values_are_rejected() {
    assert!(Scenario::from_json(r#"{"bogus":1}"#).is_err());
    assert!(Scenario::from_json(r#"{"wire":{"diameter_m":-1.0}}"#).is_err());
    assert!(Positive::new(0.0).is_err());
    assert!(NonNegative::new(-0.1).is_err());
    let unordered = r#"{"load":{"steps":[{"t_s":5.0,"mass_kg":1.0},{"t_s":1.0,"mass_kg":0.0}]}}"#;
    assert!(matches!(
        Scenario::from_json(unordered),
        Err(ScenarioError::Invalid(_))
    ));
}

#[test]
fn scenario_json_round_trips() {
    for name in SCENARIO_NAMES {
        let s = scen(name);
        let back = Scenario::from_json(&serde_json::to_string(&s).unwrap()).unwrap();
        assert_eq!(s, back);
    }
}

#[test]
fn elastic_modulus_is_recovered_below_yield() {
    let mut s = scen("clean");
    s.load = LoadProgram {
        steps: vec![LoadStep {
            t_s: 1.0,
            mass_kg: 1.0,
        }],
    };
    let sigma = 1.0 * GRAVITY / s.wire.area_m2();
    let eps = strain_of(&s, s.voltage(0, 5.0)) - strain_of(&s, s.voltage(0, 0.0));
    let e = sigma / eps;
    assert!(
        (e / s.wire.youngs_modulus_pa.get() - 1.0).abs() < 1e-6,
        "E = {e}"
    );
}

#[test]
fn plastic_hardening_adds_permanent_strain() {
    let s = scen("clean"); // peaks at 2 kg (> yield), ends at 1.5 kg
    let h = s.wire.hardening_modulus_pa.get();
    let peak = 2.0 * GRAVITY / s.wire.area_m2();
    let plastic = (peak - s.wire.yield_stress_pa) / h;
    let elastic_end = 1.5 * GRAVITY / s.wire.area_m2() / s.wire.youngs_modulus_pa.get();
    let end = strain_of(&s, s.voltage(0, 800.0)) - strain_of(&s, s.voltage(0, 0.0));
    assert!((end - (plastic + elastic_end)).abs() < 1e-9);
}

#[test]
fn polarity_flips_sign_about_offset() {
    let mut s = scen("clean");
    let v_pos = s.voltage(0, 100.0);
    s.lvdt.polarity = Polarity::Negative;
    assert!(v_pos * s.voltage(0, 100.0) < 0.0);
}

#[test]
fn unloaded_clean_voltage_reads_one_volt_by_default() {
    assert!((scen("clean").voltage(0, 0.0) - 1.0).abs() < 1e-12);
    assert_eq!(scen("clean").wire.l0_m.get(), DEFAULT_L0_M);
}

// frob:tests crates/sadi-proto/src/sim/signal_faults.rs::FaultPlan.noise_v
#[test]
fn noise_sd_matches_preliminary_value() {
    let s = scen("noisy");
    let clean = scen("clean");
    let r: Vec<f64> = (0..20_000)
        .map(|i| {
            let t = 700.0 + i as f64 / 10.0;
            s.voltage(0, t) - clean.voltage(0, t)
        })
        .collect();
    let m = r.iter().sum::<f64>() / r.len() as f64;
    let sd = (r.iter().map(|x| (x - m).powi(2)).sum::<f64>() / r.len() as f64).sqrt();
    assert!((sd / 0.0345 - 1.0).abs() < 0.03, "sd = {sd}");
    assert!(m.abs() < 0.002);
}

#[test]
fn coloured_noise_keeps_sd_but_is_correlated() {
    let plan = FaultPlan::default().with_noise(NoiseSpec {
        sd_v: NonNegative::new(0.1).unwrap(),
        kind: NoiseKind::Coloured { window: 8 },
    });
    let r: Vec<f64> = (0..20_000)
        .map(|i| plan.noise_v(0, i as f64 / 10.0))
        .collect();
    let sd = (r.iter().map(|x| x * x).sum::<f64>() / r.len() as f64).sqrt();
    assert!((sd / 0.1 - 1.0).abs() < 0.05, "sd = {sd}");
    let lag1 = r.windows(2).map(|w| w[0] * w[1]).sum::<f64>() / r.len() as f64 / (sd * sd);
    assert!(lag1 > 0.7, "lag1 = {lag1}");
}

#[test]
fn same_seed_is_identical_and_different_seed_differs() {
    let a = scen("combined");
    let b = scen("combined");
    let c = a.clone().with_faults(a.faults.clone().with_seed(99));
    let ts: Vec<f64> = (0..500).map(|i| i as f64 * 0.7).collect();
    let va: Vec<f64> = ts.iter().map(|&t| a.voltage(0, t)).collect();
    assert_eq!(va, ts.iter().map(|&t| b.voltage(0, t)).collect::<Vec<_>>());
    assert_ne!(va, ts.iter().map(|&t| c.voltage(0, t)).collect::<Vec<_>>());
}

#[test]
fn linear_drift_slope_is_recovered() {
    let s = scen("drifting");
    let c = scen("clean");
    let t: Vec<f64> = (0..9000).map(|i| i as f64 / 10.0).collect();
    let y: Vec<f64> = t
        .iter()
        .map(|&x| s.voltage(0, x) - c.voltage(0, x))
        .collect();
    // thermal term averages out over three whole periods; slope is 0.001 V/s
    let slope = ls_slope(&t, &y);
    assert!((slope / 0.001 - 1.0).abs() < 0.05, "slope = {slope}");
}

// frob:tests crates/sadi-proto/src/sim/physics.rs::creep_strain
#[test]
fn creep_slope_vs_log_time_is_recovered_exactly_without_noise() {
    let s = scen("creeping").without_noise();
    let tau = s.faults.creep.tau_s.get();
    // first hold: load change at t = 10, next at 310
    let (x, y): (Vec<f64>, Vec<f64>) = (0..2900)
        .map(|i| 10.0 + 0.1 + i as f64 / 10.0)
        .map(|t| {
            (
                (1.0 + (t - 10.0) / tau).ln(),
                strain_of(&s, s.voltage(0, t)),
            )
        })
        .unzip();
    let injected =
        s.faults.creep.coeff * (1.0 * GRAVITY / s.wire.area_m2()) / s.wire.youngs_modulus_pa.get();
    let fit = ls_slope(&x, &y);
    assert!(
        (fit / injected - 1.0).abs() < 1e-6,
        "fit {fit} vs {injected}"
    );
}

#[test]
fn creep_slope_is_recovered_through_noise() {
    let s = scen("creeping");
    let tau = s.faults.creep.tau_s.get();
    let (x, y): (Vec<f64>, Vec<f64>) = (0..2900)
        .map(|i| 10.0 + 0.1 + i as f64 / 10.0)
        .map(|t| {
            (
                (1.0 + (t - 10.0) / tau).ln(),
                strain_of(&s, s.voltage(0, t)),
            )
        })
        .unzip();
    let injected =
        s.faults.creep.coeff * (1.0 * GRAVITY / s.wire.area_m2()) / s.wire.youngs_modulus_pa.get();
    let fit = ls_slope(&x, &y);
    assert!(
        (fit / injected - 1.0).abs() < 0.15,
        "fit {fit} vs {injected}"
    );
}

// frob:tests crates/sadi-proto/src/sim/physics.rs::slip_strain
#[test]
fn slip_step_sizes_are_recovered_with_no_load_change() {
    let s = scen("slipping");
    for slip in &s.faults.slips {
        let SlipStep { t_s, strain } = *slip;
        // no load step inside the +-50 s window around either slip
        assert!(s.load.steps.iter().all(|l| (l.t_s - t_s).abs() > 50.0));
        let dv = mean_v(&s, t_s + 5.0, t_s + 50.0) - mean_v(&s, t_s - 50.0, t_s - 5.0);
        let got = dv * s.lvdt.slope_m_per_v.get() / s.wire.l0_m.get();
        assert!(
            (got / strain - 1.0).abs() < 0.1,
            "slip at {t_s}: {got} vs {strain}"
        );
    }
}

// frob:tests crates/sadi-proto/src/sim/signal_faults.rs::FaultPlan.saturate
// frob:tests crates/sadi-proto/src/sim/signal_faults.rs::FaultPlan.apply
#[test]
fn saturation_clamps_and_folds() {
    let sat = |mode| {
        let mut s = scen("clean");
        s.faults = s
            .faults
            .clone()
            .with_drift(sadi_proto::sim::signal_faults::DriftSpec {
                linear_v_per_s: 0.02,
                ..Default::default()
            });
        s.faults = s.faults.with_saturation(Some(SaturationSpec {
            limit_v: Positive::new(4.9).unwrap(),
            mode,
        }));
        s
    };
    let clamp = sat(SaturationMode::Clamp);
    let fold = sat(SaturationMode::Fold);
    let raw = |s: &Scenario, t| s.clean_lvdt_v(t) + s.faults.drift_v(t);
    // raw ~ 1 + 0.02 t + load; at t = 300 raw is about 7 V
    assert!(raw(&clamp, 300.0) > 4.9);
    assert_eq!(clamp.voltage(0, 300.0), 4.9);
    let expect = 2.0 * 4.9 - raw(&fold, 300.0);
    assert!((fold.voltage(0, 300.0) - expect).abs() < 1e-9);
}

#[test]
fn saturating_scenario_actually_saturates() {
    let s = scen("saturating").without_noise();
    let peak = (0..9000)
        .map(|i| s.voltage(0, i as f64 / 10.0).abs())
        .fold(0.0, f64::max);
    assert!(peak <= 4.9 + 1e-12);
    assert!((0..9000).any(|i| {
        let t = i as f64 / 10.0;
        s.clean_lvdt_v(t) + s.faults.drift_v(t) > 4.9
    }));
}

#[test]
fn active_fault_kinds_match_scenarios() {
    assert!(scen("clean").faults.active_kinds().is_empty());
    assert_eq!(scen("noisy").faults.active_kinds(), vec![FaultKind::Noise]);
    assert_eq!(
        scen("combined").faults.active_kinds(),
        FaultKind::ALL.to_vec()
    );
}
