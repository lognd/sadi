//! Codec tests driven by docs/protocol-vectors.json (set v1_003_mom) plus proptests.
#![forbid(unsafe_code)]

use proptest::prelude::*;
use proptest::test_runner::{TestCaseError, TestRunner};
use sadi_proto::codec::{
    convert, AdcMode, AdcRange, Command, Decoder, Packet, PACKET_LEN, SAMPLES_PER_PACKET,
};
use serde_json::Value;

fn vectors() -> Value {
    let raw = include_str!("../../../docs/protocol-vectors.json");
    let v: Value = serde_json::from_str(raw).expect("vectors parse");
    v["v1_003_mom"].clone()
}

fn unhex(s: &str) -> Vec<u8> {
    (0..s.len() / 2)
        .map(|i| u8::from_str_radix(&s[2 * i..2 * i + 2], 16).expect("hex"))
        .collect()
}

fn find<'a>(list: &'a Value, name: &str) -> &'a Value {
    list.as_array()
        .expect("array")
        .iter()
        .find(|e| e["name"] == name)
        .expect("named vector")
}

fn close(a: f64, b: f64) -> bool {
    (a - b).abs() < 2e-8
}

// frob:ticket 01M6W7R0VNQVPZ47CD080SB0TA
// frob:tests crates/sadi-proto/src/codec/command.rs::Command.encode
// frob:tests crates/sadi-proto/src/codec/command.rs::Command.decode
#[test]
fn host_commands_match_vectors() {
    let v = vectors();
    for e in v["host_to_device"].as_array().unwrap() {
        let bytes = unhex(e["bytes"].as_str().unwrap());
        let cmd = Command::decode(&bytes).expect("decode");
        assert_eq!(cmd.encode().to_vec(), bytes, "{}", e["name"]);
        assert_eq!(
            u64::from(cmd.opcode()),
            e["decoded"]["cmd"].as_u64().unwrap()
        );
        if let Command::Start { ranges } = cmd {
            let want: Vec<u64> = e["decoded"]["adc_ranges"]
                .as_array()
                .unwrap()
                .iter()
                .map(|x| x.as_u64().unwrap())
                .collect();
            let got: Vec<u64> = ranges.iter().map(|r| u64::from(r.code())).collect();
            assert_eq!(got, want);
        }
    }
}

// frob:tests crates/sadi-proto/src/codec/command.rs::AdcRange.from_code
#[test]
fn invalid_range_codes_rejected() {
    let v = vectors();
    for c in v["invalid_range_codes"].as_array().unwrap() {
        assert!(AdcRange::from_code(c.as_u64().unwrap() as u8).is_err());
    }
    for r in v["adc_ranges"].as_array().unwrap() {
        let range = AdcRange::from_code(r["code"].as_u64().unwrap() as u8).unwrap();
        assert!(close(
            range.full_scale_volts(),
            r["full_scale_volts"].as_f64().unwrap()
        ));
        assert_eq!(range.is_bipolar(), r["bipolar"].as_bool().unwrap());
    }
}

// frob:tests crates/sadi-proto/src/codec/packet.rs::Packet.parse
#[test]
fn device_packets_match_vectors() {
    let v = vectors();
    let list = &v["device_to_host"];
    let boot = find(list, "boot_or_query_reply_fw_1_003_state_booted");
    match Packet::parse(&unhex(boot["bytes"].as_str().unwrap())).unwrap() {
        Packet::Version(p) => {
            assert_eq!((p.major, p.minor), (1, 3));
            assert!(close(p.fw_version(), 1.003));
        }
        other => panic!("expected version, got {other:?}"),
    }
    let ack = find(list, "stop_ack");
    assert!(matches!(
        Packet::parse(&unhex(ack["bytes"].as_str().unwrap())),
        Ok(Packet::StopAck(_))
    ));
}

// frob:tests crates/sadi-proto/src/codec/adc.rs::convert
// frob:tests crates/sadi-proto/src/codec/adc.rs::dll_int14
#[test]
fn adc_conversion_cases_match_in_both_modes() {
    let v = vectors();
    for c in v["adc_conversion_cases"].as_array().unwrap() {
        let range = AdcRange::from_code(c["range_code"].as_u64().unwrap() as u8).unwrap();
        let raw = c["raw"].as_u64().unwrap() as u16;
        assert_eq!(
            i64::from(sadi_proto::codec::dll_int14(range, raw)),
            c["int14_dll"].as_i64().unwrap(),
            "{c}"
        );
        let dll = convert(range, raw, AdcMode::DllCompatible);
        let ideal = convert(range, raw, AdcMode::Ideal);
        assert!(
            close(dll, c["volts_dll"].as_f64().unwrap()),
            "dll {c}: {dll}"
        );
        assert!(
            close(ideal, c["volts_ideal"].as_f64().unwrap()),
            "ideal {c}: {ideal}"
        );
    }
}

// frob:tests crates/sadi-proto/src/codec/packet.rs::Sample.volts
// frob:tests crates/sadi-proto/src/codec/packet.rs::Packet.encode
#[test]
fn data_packets_match_vectors_in_both_modes() {
    let v = vectors();
    for e in v["device_to_host"].as_array().unwrap() {
        if !e["name"].as_str().unwrap().starts_with("data_packet") {
            continue;
        }
        let bytes = unhex(e["bytes"].as_str().unwrap());
        let packet = Packet::parse(&bytes).unwrap();
        assert_eq!(packet.encode().to_vec(), bytes, "re-encode {}", e["name"]);
        let Packet::Data(p) = packet else {
            panic!("not data")
        };
        let d = &e["decoded"];
        assert_eq!(u64::from(p.msg_count), d["msg_count"].as_u64().unwrap());
        assert_eq!(
            u64::from(p.digital_inputs),
            d["digital_inputs"].as_u64().unwrap()
        );
        // Ranges come from the sibling Start vector named in the packet name.
        let ranges = if e["name"].as_str().unwrap().ends_with("0_5_11_15") {
            [0u8, 5, 11, 15]
        } else {
            [1, 1, 1, 1]
        }
        .map(|c| AdcRange::from_code(c).unwrap());
        let samples = d["samples"].as_array().unwrap();
        assert_eq!(samples.len(), SAMPLES_PER_PACKET);
        for (s, want) in p.samples.iter().zip(samples) {
            assert_eq!(i64::from(s.encoder), want["encoder"].as_i64().unwrap());
            for (mode, key) in [
                (AdcMode::DllCompatible, "volts_dll"),
                (AdcMode::Ideal, "volts_ideal"),
            ] {
                let got = s.volts(&ranges, mode);
                for (g, w) in got.iter().zip(want[key].as_array().unwrap()) {
                    assert!(close(*g, w.as_f64().unwrap()), "{key} {g} vs {w}");
                }
            }
        }
    }
}

// frob:tests crates/sadi-proto/src/codec/decoder.rs::Decoder.next_packet
#[test]
fn framing_cases_match_vectors() {
    let v = vectors();
    for f in v["framing_cases"].as_array().unwrap() {
        let stream = unhex(f["stream"].as_str().unwrap());
        let exp = &f["expected"];
        let mut d = Decoder::new();
        d.push(&stream);
        let out = d.drain();
        assert_eq!(
            out.len() as u64,
            exp["packets"].as_u64().unwrap(),
            "{}",
            f["name"]
        );
        if let Some(off) = exp.get("first_packet_offset") {
            assert_eq!(
                d.stats().dropped_bytes,
                off.as_u64().unwrap(),
                "{}",
                f["name"]
            );
        }
        if exp.get("decoded_type").is_some() {
            assert!(matches!(out[0], Ok(Packet::StopAck(_))));
        }
    }
}

fn clean_stream(n: u32) -> Vec<u8> {
    let v = vectors();
    let data = unhex(
        find(&v["device_to_host"], "data_packet_ranges_1_1_1_1")["bytes"]
            .as_str()
            .unwrap(),
    );
    let mut out = Vec::new();
    for i in 0..n {
        let mut p = data.clone();
        p[4..8].copy_from_slice(&i.to_le_bytes());
        out.extend(p);
    }
    out
}

// frob:tests crates/sadi-proto/src/codec/decoder.rs::Decoder.push
#[test]
fn resync_recovers_after_garbage_and_dropped_bytes() {
    let clean = clean_stream(6);
    let mut stream = vec![0x00, 0x55, 0x55, 0xAA, 0x13];
    stream.extend(&clean[..PACKET_LEN]); // packet 0 intact
    stream.extend(&clean[PACKET_LEN..PACKET_LEN + 400]); // packet 1 truncated
    stream.extend([0x55, 0x55, 0x01]); // garbage with false syncs
    stream.extend(&clean[2 * PACKET_LEN..]); // packets 2..5 intact
    let mut d = Decoder::new();
    // Feed in awkward chunk sizes.
    let mut got = Vec::new();
    for chunk in stream.chunks(97) {
        d.push(chunk);
        got.extend(d.drain());
    }
    let counts: Vec<u32> = got
        .into_iter()
        .filter_map(|r| match r {
            Ok(Packet::Data(p)) => Some(p.msg_count),
            _ => None,
        })
        .collect();
    assert_eq!(counts, vec![0, 2, 3, 4, 5]);
    let s = d.stats();
    assert_eq!(s.gap_events, 1);
    assert_eq!(s.missed_packets, 1);
    assert_eq!(s.dropped_bytes, 5 + 400 + 3);
}

fn run<S: Strategy>(strategy: S, test: impl Fn(S::Value) -> Result<(), TestCaseError>) {
    let mut runner = TestRunner::new(ProptestConfig {
        failure_persistence: None,
        ..ProptestConfig::default()
    });
    runner.run(&strategy, test).expect("property holds");
}

// frob:ticket 01M6W7R0VNQVPZ47CD080SB0TA
// frob:tests crates/sadi-proto/src/codec/decoder.rs::Decoder.drain
// frob:tests crates/sadi-proto/src/codec/decoder.rs::Decoder.buffered
#[test]
fn never_panics_on_arbitrary_bytes() {
    let chunk = proptest::collection::vec(any::<u8>(), 0..900);
    run(proptest::collection::vec(chunk, 0..8), |chunks| {
        let mut d = Decoder::new();
        for c in &chunks {
            d.push(c);
            let _ = d.drain();
        }
        prop_assert!(d.buffered() < PACKET_LEN);
        Ok(())
    });
}

// frob:tests crates/sadi-proto/src/codec/packet.rs::Packet.parse
// frob:tests crates/sadi-proto/src/codec/command.rs::Command.decode
#[test]
fn parsers_never_panic() {
    run(proptest::collection::vec(any::<u8>(), 0..700), |bytes| {
        let _ = Packet::parse(&bytes);
        let _ = Command::decode(&bytes);
        Ok(())
    });
}

// frob:tests crates/sadi-proto/src/codec/decoder.rs::Decoder.next_packet
#[test]
fn recovers_later_intact_packets() {
    let junk = proptest::collection::vec(any::<u8>(), 0..300);
    run((junk, 1usize..PACKET_LEN), |(junk, cut)| {
        // Damaged packet 0 (tail bytes dropped) behind junk, then intact 2..5.
        // Packet 2 may legitimately be swallowed (no CRC: its 0x55 can complete
        // a truncated frame's tail), so packets 3..5 must always be recovered.
        let clean = clean_stream(6);
        let mut stream = junk;
        stream.extend(&clean[..cut]);
        stream.extend(&clean[2 * PACKET_LEN..]);
        let mut d = Decoder::new();
        d.push(&stream);
        let counts: Vec<u32> = d
            .drain()
            .into_iter()
            .filter_map(|r| match r {
                Ok(Packet::Data(p)) => Some(p.msg_count),
                _ => None,
            })
            .collect();
        prop_assert!(counts.len() >= 3);
        prop_assert_eq!(&counts[counts.len() - 3..], &[3u32, 4, 5][..]);
        Ok(())
    });
}
