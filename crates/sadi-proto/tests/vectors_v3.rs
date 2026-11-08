//! v3.41 codec tests driven by docs/protocol-vectors.json (set v3_41_generic).
#![cfg(feature = "v3")]
#![forbid(unsafe_code)]

use proptest::prelude::*;
use proptest::test_runner::TestRunner;
use sadi_proto::v3::{
    crc16, AckPacket, Command, HostOpcode, InitMode, Packet, V3Error, VendorRange, CRC_CHECK_VALUE,
};
use serde_json::Value;

fn vectors() -> Value {
    let raw = include_str!("../../../docs/protocol-vectors.json");
    let v: Value = serde_json::from_str(raw).expect("vectors parse");
    v["v3_41_generic"].clone()
}

fn unhex(s: &str) -> Vec<u8> {
    (0..s.len() / 2)
        .map(|i| u8::from_str_radix(&s[2 * i..2 * i + 2], 16).expect("hex"))
        .collect()
}

// frob:ticket 01M6W7R121020FDM1SK2GGPZ5K
// frob:tests crates/sadi-proto/src/v3/crc.rs::crc16
#[test]
fn crc_cases_match_vectors() {
    assert_eq!(crc16(b"123456789"), CRC_CHECK_VALUE);
    for e in vectors()["crc_cases"].as_array().unwrap() {
        let data = unhex(e["data"].as_str().unwrap());
        let want = u16::from_str_radix(e["crc16_be"].as_str().unwrap(), 16).unwrap();
        assert_eq!(crc16(&data), want);
    }
}

// frob:ticket 01M6W7R121020FDM1SK2GGPZ5K
// frob:tests crates/sadi-proto/src/v3/command.rs::Command.encode
// frob:tests crates/sadi-proto/src/v3/command.rs::Command.decode
#[test]
fn host_commands_match_vectors() {
    for e in vectors()["host_to_device"].as_array().unwrap() {
        let name = e["name"].as_str().unwrap();
        let bytes = unhex(e["bytes"].as_str().unwrap());
        let opcode = e["decoded"]["opcode"].as_u64().unwrap();
        if opcode == 0x92 || opcode == 0x63 {
            // Not implemented by this codec (0x92 ignored by firmware; 0x63 out of scope).
            assert!(Command::decode(&bytes).is_err(), "{name}");
            continue;
        }
        let cmd = Command::decode(&bytes).expect(name);
        assert_eq!(cmd.encode(), bytes, "{name}");
        assert_eq!(u64::from(cmd.opcode().byte()), opcode, "{name}");
        if let Command::PredefInit {
            loop_freq_hz, mode, ..
        } = cmd
        {
            let p = unhex(e["decoded"]["payload"].as_str().unwrap());
            assert_eq!(loop_freq_hz, u16::from_le_bytes([p[0], p[1]]));
            assert_eq!(mode.code(), u16::from_le_bytes([p[2], p[3]]));
        }
    }
}

// frob:ticket 01M6W7R121020FDM1SK2GGPZ5K
// frob:tests crates/sadi-proto/src/v3/packet.rs::Packet.decode
#[test]
fn device_packets_match_vectors() {
    for e in vectors()["device_to_host"].as_array().unwrap() {
        let name = e["name"].as_str().unwrap();
        let bytes = unhex(e["bytes"].as_str().unwrap());
        let d = &e["decoded"];
        match Packet::decode(&bytes).expect(name) {
            Packet::Version(v) => {
                assert!((f64::from(v.fw_version) - d["fw_version"].as_f64().unwrap()).abs() < 1e-6);
            }
            Packet::Ack(AckPacket { echoed, status }) => {
                assert_eq!(
                    u64::from(echoed.byte()),
                    d["echoed_opcode"].as_u64().unwrap()
                );
                assert_eq!(u64::from(status), d["status"].as_u64().unwrap());
            }
            Packet::Data(p) => {
                let raw: Vec<u64> = d["adc_raw"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|x| x.as_u64().unwrap())
                    .collect();
                let got: Vec<u64> = p.adc_raw.iter().map(|&x| u64::from(x)).collect();
                assert_eq!(got, raw);
                assert_eq!(i64::from(p.encoder0), d["encoder0"].as_i64().unwrap());
                assert_eq!(
                    u64::from(p.input_capture),
                    d["input_capture"].as_u64().unwrap()
                );
                assert_eq!(i64::from(p.encoder1), d["encoder1"].as_i64().unwrap());
                assert_eq!(
                    u64::from(p.encoder_velocity),
                    d["encoder_velocity"].as_u64().unwrap()
                );
                assert_eq!(
                    u64::from(p.inputs_12bit),
                    d["inputs_12bit"].as_u64().unwrap()
                );
                assert_eq!(u64::from(p.msg_count), d["msg_count"].as_u64().unwrap());
            }
            other => panic!("unexpected {other:?}"),
        }
    }
}

// frob:ticket 01M6W7R121020FDM1SK2GGPZ5K
// frob:tests crates/sadi-proto/src/v3/packet.rs::Packet.decode
#[test]
fn rejects_bad_frames() {
    let mut ok = unhex("55f2f5013c99");
    assert!(Packet::decode(&ok).is_ok());
    ok[3] ^= 1;
    assert!(matches!(Packet::decode(&ok), Err(V3Error::BadCrc { .. })));
    assert!(matches!(
        Packet::decode(&unhex("55f2f501")),
        Err(V3Error::BadLength { .. })
    ));
    assert!(matches!(
        Packet::decode(&unhex("56f2f5013c99")),
        Err(V3Error::BadSync(0x56))
    ));
    assert!(matches!(
        Packet::decode(&[0x55]),
        Err(V3Error::BadLength { .. })
    ));
    assert!(matches!(
        Packet::decode(&unhex("5599")),
        Err(V3Error::UnknownDeviceOpcode(0x99))
    ));
}

fn range() -> impl Strategy<Value = VendorRange> {
    prop_oneof![0u8..=5, 9u8..=12].prop_map(|c| VendorRange::try_from(c).unwrap())
}

// frob:ticket 01M6W7R121020FDM1SK2GGPZ5K
// frob:tests crates/sadi-proto/src/v3/command.rs::Command.encode
#[test]
fn predef_init_round_trips() {
    let strat = (
        any::<u16>(),
        any::<bool>(),
        proptest::array::uniform4(range()),
    );
    TestRunner::default()
        .run(&strat, |(f, mom, r)| {
            let mode = if mom {
                InitMode::Mom
            } else {
                InitMode::Pendulum
            };
            let cmd = Command::PredefInit {
                loop_freq_hz: f,
                mode,
                ranges: r,
            };
            let bytes = cmd.encode();
            prop_assert_eq!(bytes.len(), HostOpcode::PredefInit.frame_len());
            prop_assert_eq!(Command::decode(&bytes), Ok(cmd));
            Ok(())
        })
        .unwrap();
}

// frob:ticket 01M6W7R121020FDM1SK2GGPZ5K
// frob:tests crates/sadi-proto/src/v3/packet.rs::Packet.decode
#[test]
fn decode_never_panics() {
    let strat = proptest::collection::vec(any::<u8>(), 0..64);
    TestRunner::default()
        .run(&strat, |bytes| {
            let _ = Packet::decode(&bytes);
            let _ = Command::decode(&bytes);
            Ok(())
        })
        .unwrap();
}
