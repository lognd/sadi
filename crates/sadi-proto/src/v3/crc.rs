//! CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF, no reflection, no xorout).

/// CRC of the ASCII bytes "123456789", used as a self-test constant.
pub const CRC_CHECK_VALUE: u16 = 0x29B1;

/// Computes CRC-16/CCITT-FALSE over `data`; frames store it big-endian.
#[must_use]
pub fn crc16(data: &[u8]) -> u16 {
    let mut crc: u16 = 0xFFFF;
    for &b in data {
        crc ^= u16::from(b) << 8;
        for _ in 0..8 {
            crc = if crc & 0x8000 != 0 {
                (crc << 1) ^ 0x1021
            } else {
                crc << 1
            };
        }
    }
    crc
}

#[cfg(test)]
mod tests {
    use super::*;

    // frob:ticket 01M6W7R121020FDM1SK2GGPZ5K
    // frob:tests crates/sadi-proto/src/v3/crc.rs::crc16
    #[test]
    fn check_value() {
        assert_eq!(crc16(b"123456789"), CRC_CHECK_VALUE);
        assert_eq!(crc16(&[]), 0xFFFF);
    }
}
