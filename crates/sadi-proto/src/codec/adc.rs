//! Raw ADS8688 code to volts conversion, bug-compatible and ideal.

use super::command::AdcRange;

/// Which raw-to-volts formula to apply; always chosen explicitly by the caller.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum AdcMode {
    /// Reproduce momLab.dll arithmetic including its quirks (protocol.md section 4).
    DllCompatible,
    /// ADS8688 datasheet straight-binary conversion.
    Ideal,
}

/// Returns the 14-bit integer momLab.dll stores for `raw` (truncating div by 4).
#[must_use]
pub fn dll_int14(range: AdcRange, raw: u16) -> i16 {
    if range.is_bipolar() {
        (raw.wrapping_add(0x7FFF) as i16) / 4
    } else {
        (raw as i16) / 4
    }
}

/// Converts a raw big-endian ADC word to volts for `range` in the given `mode`.
pub fn convert(range: AdcRange, raw: u16, mode: AdcMode) -> f64 {
    let fs = range.full_scale_volts();
    let v = match mode {
        AdcMode::DllCompatible => {
            let int14 = f64::from(dll_int14(range, raw));
            if range.is_bipolar() {
                int14 * fs / 8191.0
            } else {
                int14 * fs / 16383.0
            }
        }
        AdcMode::Ideal => {
            if range.is_bipolar() {
                (f64::from(raw) - 32768.0) / 32768.0 * fs
            } else {
                f64::from(raw) / 65535.0 * fs
            }
        }
    };
    tracing::trace!(?range, raw, ?mode, volts = v, "adc convert");
    v
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn dll_quirk_raw_zero_is_plus_full_scale() {
        assert_eq!(convert(AdcRange::Pm5_12, 0, AdcMode::DllCompatible), 5.12);
        assert_eq!(convert(AdcRange::Pm5_12, 0, AdcMode::Ideal), -5.12);
    }

    #[test]
    fn dll_unipolar_upper_half_is_negative() {
        assert!(convert(AdcRange::Unipolar5_12, 0x9000, AdcMode::DllCompatible) < 0.0);
        assert!(convert(AdcRange::Unipolar5_12, 0x9000, AdcMode::Ideal) > 0.0);
    }

    #[test]
    fn every_raw_code_is_finite() {
        for r in AdcRange::ALL {
            for raw in [0u16, 1, 0x7FFF, 0x8000, 0xFFFF] {
                for m in [AdcMode::DllCompatible, AdcMode::Ideal] {
                    assert!(convert(r, raw, m).is_finite());
                }
            }
        }
    }
}
