//! Pty loopback (unix) and `#[ignore]`d hardware tests for the serial backend.
#![cfg(feature = "serial")]

use std::time::Duration;

#[cfg(unix)]
use sadi_proto::serial::RxLimit;
use sadi_proto::serial::{list_ports, SerialConfig, SerialTransport, FTDI_ALLOW_LIST};
use sadi_proto::{Transport, TransportError};

/// Build a transport on one end of a pty pair; None if ptys are unavailable.
#[cfg(unix)]
fn pty_pair(limit: RxLimit) -> Option<(SerialTransport, serialport::TTYPort)> {
    match serialport::TTYPort::pair() {
        Ok((master, slave)) => Some((
            SerialTransport::from_port(Box::new(slave), "pty-slave".into(), limit),
            master,
        )),
        Err(e) => {
            eprintln!("skipping: pty unavailable: {e}");
            None
        }
    }
}

// frob:tests crates/sadi-proto/src/serial.rs::SerialTransport.write_all
// frob:tests crates/sadi-proto/src/serial.rs::SerialTransport.read
// frob:tests crates/sadi-proto/src/serial.rs::SerialTransport.description
#[cfg(unix)]
#[test]
fn pty_round_trip() {
    use std::io::{Read, Write};
    let Some((mut t, mut master)) = pty_pair(RxLimit::DEFAULT) else {
        return;
    };
    t.write_all(b"hello").unwrap();
    let mut got = [0u8; 5];
    master.read_exact(&mut got).unwrap();
    assert_eq!(&got, b"hello");

    master.write_all(b"world").unwrap();
    let mut buf = [0u8; 16];
    let n = t.read(&mut buf, Duration::from_millis(500)).unwrap();
    assert_eq!(&buf[..n], b"world");
    assert_eq!(t.description(), "serial:pty-slave");
}

// frob:tests crates/sadi-proto/src/serial.rs::SerialTransport.read
#[cfg(unix)]
#[test]
fn pty_read_times_out() {
    let Some((mut t, _master)) = pty_pair(RxLimit::DEFAULT) else {
        return;
    };
    let mut buf = [0u8; 4];
    let r = t.read(&mut buf, Duration::from_millis(20));
    assert!(matches!(r, Err(TransportError::Timeout(_))), "{r:?}");
}

// frob:tests crates/sadi-proto/src/serial.rs::SerialTransport.purge
// frob:tests crates/sadi-proto/src/serial.rs::SerialTransport.close
// frob:tests crates/sadi-proto/src/serial.rs::SerialTransport.shutdown
#[cfg(unix)]
#[test]
fn pty_purge_close_semantics() {
    use std::io::Write;
    let Some((mut t, mut master)) = pty_pair(RxLimit::DEFAULT) else {
        return;
    };
    master.write_all(b"junk").unwrap();
    std::thread::sleep(Duration::from_millis(50));
    t.purge().unwrap();
    let mut buf = [0u8; 4];
    assert!(matches!(
        t.read(&mut buf, Duration::from_millis(20)),
        Err(TransportError::Timeout(_))
    ));
    t.close().unwrap();
    assert!(matches!(t.close(), Err(TransportError::Closed)));
    assert!(matches!(t.write_all(b"x"), Err(TransportError::Closed)));
    assert!(matches!(t.purge(), Err(TransportError::Closed)));

    let Some((t2, _m2)) = pty_pair(RxLimit::DEFAULT) else {
        return;
    };
    t2.shutdown().unwrap();
}

// frob:tests crates/sadi-proto/src/serial.rs::SerialTransport.read
#[cfg(unix)]
#[test]
fn pty_rx_overflow_is_typed() {
    use std::io::Write;
    let Some((mut t, mut master)) = pty_pair(RxLimit::new(4).unwrap()) else {
        return;
    };
    master.write_all(b"0123456789").unwrap();
    std::thread::sleep(Duration::from_millis(50));
    let mut buf = [0u8; 4];
    match t.read(&mut buf, Duration::from_millis(50)) {
        Err(TransportError::Overflow { pending, limit }) => {
            assert!(pending > limit);
            assert_eq!(limit, 4);
        }
        other => panic!("expected overflow, got {other:?}"),
    }
    t.purge().unwrap();
}

// frob:tests crates/sadi-proto/src/serial.rs::list_ports
#[test]
fn list_ports_runs_without_hardware() {
    // Enumeration may fail on hosts without udev; it must never panic.
    let _ = list_ports(&FTDI_ALLOW_LIST);
}

/// Hardware row 1 (docs/hardware-verification.md): enumerate the SADI board.
// frob:tests crates/sadi-proto/src/serial.rs::list_ports
#[test]
#[ignore = "needs a SADI board on USB"]
fn hw_enumerate_finds_sadi() {
    let ports = list_ports(&FTDI_ALLOW_LIST).unwrap();
    assert!(!ports.is_empty(), "no FTDI port found");
    println!("{ports:?}");
}

/// Hardware row 1: open the first FTDI port and purge cleanly.
// frob:tests crates/sadi-proto/src/serial.rs::SerialTransport.open
#[test]
#[ignore = "needs a SADI board on USB"]
fn hw_open_purge_close() {
    let ports = list_ports(&FTDI_ALLOW_LIST).unwrap();
    let first = ports.first().expect("no FTDI port found");
    let cfg = SerialConfig::new(first.name()).unwrap();
    let mut t = SerialTransport::open(&cfg).unwrap();
    t.purge().unwrap();
    t.shutdown().unwrap();
}
