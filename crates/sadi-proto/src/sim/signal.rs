//! Signal model the simulator samples to build data packets.

/// Source of simulated analogue voltages and encoder position over time.
pub trait SignalSource: Send {
    /// Voltage in volts on channel `ch` at time `t` seconds.
    fn voltage(&self, ch: usize, t: f64) -> f64;
    /// Encoder count at time `t` seconds.
    fn encoder(&self, t: f64) -> i32;
}

#[cfg(test)]
mod tests {
    use super::*;

    struct Const;
    impl SignalSource for Const {
        fn voltage(&self, ch: usize, _t: f64) -> f64 {
            ch as f64
        }
        fn encoder(&self, _t: f64) -> i32 {
            7
        }
    }

    #[test]
    fn signal_source_is_usable_as_object() {
        let s: Box<dyn SignalSource> = Box::new(Const);
        assert_eq!(s.voltage(3, 0.0), 3.0);
        assert_eq!(s.encoder(1.0), 7);
    }
}
