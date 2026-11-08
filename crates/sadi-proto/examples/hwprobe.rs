//! hwprobe: scripted, read-mostly bench probe for the SADI board (docs/device/hwprobe.md).
//!
//! Every subcommand runs one HW1 check from docs/hardware-verification.md,
//! records every raw byte to an append-only `.bin` capture (never overwritten)
//! and writes a JSON report next to it. Sources: `--sim`, `--replay`, `--port`.
//! Library-style logging goes through `tracing`; stdout carries only the result line.
#![forbid(unsafe_code)]
#![allow(dead_code)]

use std::collections::BTreeMap;
use std::fs::OpenOptions;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::ExitCode;
use std::str::FromStr;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use serde::Serialize;
use serde_json::{json, Value};
use tracing::{debug, error, info, warn};

use sadi_proto::codec::{AdcChannel, AdcMode, AdcRange, DataPacket, SAMPLES_PER_PACKET};
use sadi_proto::replay::{CaptureError, CaptureSet, RecordingTransport, ReplayTransport};
use sadi_proto::session::{
    Block, Connected, Handshake, Session, SessionConfig, SessionError, Streaming,
};
use sadi_proto::sim::device::{SimConfig, SimDevice, DEFAULT_SAMPLE_RATE_HZ};
use sadi_proto::{Transport, TransportError};

/// Tool name written into every report.
const TOOL: &str = "hwprobe";
/// Encoder step (counts per 20 us sample) above which a jump is flagged as a discontinuity.
const JUMP_THRESHOLD: i64 = 1_000;
/// Cap on stored series entries so a long run cannot exhaust memory.
const SERIES_CAP: usize = 10_000;
/// Bytes in one data packet on the wire (protocol.md section 3).
const PACKET_BYTES: u64 = 612;
/// Inter-block gap histogram upper edges in milliseconds.
const GAP_EDGES_MS: [f64; 5] = [1.0, 2.0, 5.0, 10.0, 50.0];
/// Boot-time histogram upper edges in milliseconds.
const BOOT_EDGES_MS: [f64; 7] = [10.0, 50.0, 100.0, 250.0, 500.0, 1000.0, 2000.0];

/// Failures of a probe run.
#[derive(Debug, thiserror::Error)]
pub enum ProbeError {
    /// Bad command line.
    #[error("usage: {0}")]
    Usage(String),
    /// A safety gate flag was not given.
    #[error("safety gate: {0}")]
    Gate(String),
    /// Source could not be opened.
    #[error("cannot open source: {0}")]
    Source(String),
    /// Capture or report file problem.
    #[error(transparent)]
    Capture(#[from] CaptureError),
    /// File I/O failure.
    #[error("I/O error on {path}: {source}")]
    Io {
        /// File involved.
        path: PathBuf,
        /// Underlying failure.
        #[source]
        source: std::io::Error,
    },
    /// Session operation failed.
    #[error("session: {0}")]
    Session(#[from] SessionError),
    /// Transport failed.
    #[error("transport: {0}")]
    Transport(#[from] TransportError),
    /// Report serialization failed.
    #[error("report: {0}")]
    Json(#[from] serde_json::Error),
}

/// One HW1 check.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Subcommand {
    /// List candidate FTDI ports.
    Enumerate,
    /// Query the version and state repeatedly.
    Query,
    /// Reset and time the boot packet.
    ResetBootTime,
    /// Stream and record throughput and gaps.
    Stream,
    /// Per-channel statistics for chosen ADC ranges.
    RangeSweep,
    /// Encoder delta/wrap analysis.
    EncoderSpin,
    /// PORTD digital-input byte analysis.
    DigitalIn,
}

impl Subcommand {
    /// Returns the command-line name.
    fn name(self) -> &'static str {
        match self {
            Subcommand::Enumerate => "enumerate",
            Subcommand::Query => "query",
            Subcommand::ResetBootTime => "reset-boot-time",
            Subcommand::Stream => "stream-60s-with-gap-stats",
            Subcommand::RangeSweep => "range-sweep",
            Subcommand::EncoderSpin => "encoder-spin",
            Subcommand::DigitalIn => "digital-in",
        }
    }

    /// Default run length for the timed subcommands.
    fn default_duration(self) -> Duration {
        match self {
            Subcommand::Stream => Duration::from_secs(60),
            Subcommand::EncoderSpin => Duration::from_secs(30),
            Subcommand::DigitalIn => Duration::from_secs(20),
            Subcommand::Enumerate
            | Subcommand::Query
            | Subcommand::ResetBootTime
            | Subcommand::RangeSweep => Duration::from_secs(1),
        }
    }
}

impl FromStr for Subcommand {
    type Err = ProbeError;

    /// Parses a subcommand name.
    fn from_str(s: &str) -> Result<Self, ProbeError> {
        const ALL: [Subcommand; 7] = [
            Subcommand::Enumerate,
            Subcommand::Query,
            Subcommand::ResetBootTime,
            Subcommand::Stream,
            Subcommand::RangeSweep,
            Subcommand::EncoderSpin,
            Subcommand::DigitalIn,
        ];
        ALL.into_iter()
            .find(|c| c.name() == s || (*c == Subcommand::Stream && s == "stream"))
            .ok_or_else(|| ProbeError::Usage(format!("unknown subcommand {s:?}")))
    }
}

/// Where bytes come from.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Source {
    /// Built-in simulator scenario.
    Sim(String),
    /// A captured `.bin` file.
    Replay(PathBuf),
    /// A real serial port.
    Port(String),
}

impl Source {
    /// Short label for reports.
    fn label(&self) -> String {
        match self {
            Source::Sim(n) => format!("sim:{n}"),
            Source::Replay(p) => format!("replay:{}", p.display()),
            Source::Port(p) => format!("port:{p}"),
        }
    }
}

/// Parsed command line.
#[derive(Debug, Clone)]
pub struct Invocation {
    /// Check to run.
    pub sub: Subcommand,
    /// Byte source (optional only for `enumerate`).
    pub source: Option<Source>,
    /// Output directory.
    pub out_dir: PathBuf,
    /// Board label used in file names.
    pub label: String,
    /// Repetitions for query / reset-boot-time.
    pub count: u32,
    /// Run length for timed checks.
    pub duration: Duration,
    /// Packets per range in range-sweep.
    pub packets: u64,
    /// ADC range codes for range-sweep.
    pub codes: Vec<AdcRange>,
    /// Operator accepts that Reset silences the board.
    pub allow_reset: bool,
    /// Operator confirmed the inputs are safe for non-default ranges.
    pub inputs_safe: bool,
}

/// Returns the usage text.
pub fn usage() -> &'static str {
    "hwprobe <enumerate|query|reset-boot-time|stream-60s-with-gap-stats|range-sweep|encoder-spin|digital-in>\n  \
     (--sim SCENARIO | --replay FILE.bin | --port NAME)\n  \
     [--out DIR] [--label L] [--count N] [--duration-secs S] [--packets N]\n  \
     [--codes 1,2,..] [--allow-reset] [--inputs-safe]"
}

/// Fetches the value following a flag.
fn value<'a>(it: &mut std::slice::Iter<'a, String>, flag: &str) -> Result<&'a str, ProbeError> {
    it.next()
        .map(String::as_str)
        .ok_or_else(|| ProbeError::Usage(format!("{flag} needs a value")))
}

/// Parses a number flag value.
fn number<N: FromStr>(s: &str, flag: &str) -> Result<N, ProbeError> {
    s.parse()
        .map_err(|_| ProbeError::Usage(format!("{flag}: bad number {s:?}")))
}

impl Invocation {
    /// Parses `args` (without the program name).
    pub fn parse(args: &[String]) -> Result<Self, ProbeError> {
        let mut it = args.iter();
        let sub: Subcommand = it
            .next()
            .ok_or_else(|| ProbeError::Usage("missing subcommand".into()))?
            .parse()?;
        let mut inv = Invocation {
            sub,
            source: None,
            out_dir: PathBuf::from("hwprobe-out"),
            label: "board".into(),
            count: if sub == Subcommand::ResetBootTime {
                20
            } else {
                5
            },
            duration: sub.default_duration(),
            packets: 20,
            codes: vec![AdcRange::default()],
            allow_reset: false,
            inputs_safe: false,
        };
        while let Some(flag) = it.next() {
            match flag.as_str() {
                "--sim" => inv.source = Some(Source::Sim(value(&mut it, flag)?.to_owned())),
                "--replay" => inv.source = Some(Source::Replay(value(&mut it, flag)?.into())),
                "--port" => inv.source = Some(Source::Port(value(&mut it, flag)?.to_owned())),
                "--out" => inv.out_dir = value(&mut it, flag)?.into(),
                "--label" => inv.label = value(&mut it, flag)?.to_owned(),
                "--count" => inv.count = number(value(&mut it, flag)?, flag)?,
                "--packets" => inv.packets = number(value(&mut it, flag)?, flag)?,
                "--duration-secs" => {
                    let s: f64 = number(value(&mut it, flag)?, flag)?;
                    inv.duration = Duration::try_from_secs_f64(s)
                        .ok()
                        .filter(|d| !d.is_zero())
                        .ok_or_else(|| ProbeError::Usage("--duration-secs must be > 0".into()))?;
                }
                "--codes" => {
                    inv.codes = value(&mut it, flag)?
                        .split(',')
                        .map(|c| {
                            let code: u8 = number(c.trim(), flag)?;
                            AdcRange::try_from(code).map_err(|e| ProbeError::Usage(e.to_string()))
                        })
                        .collect::<Result<_, _>>()?;
                }
                "--allow-reset" => inv.allow_reset = true,
                "--inputs-safe" => inv.inputs_safe = true,
                other => return Err(ProbeError::Usage(format!("unknown argument {other:?}"))),
            }
        }
        if inv.count == 0 || inv.packets == 0 || inv.codes.is_empty() {
            return Err(ProbeError::Usage(
                "count, packets and codes must be non-empty".into(),
            ));
        }
        if inv.source.is_none() && inv.sub != Subcommand::Enumerate {
            return Err(ProbeError::Usage(
                "a source (--sim/--replay/--port) is required".into(),
            ));
        }
        Ok(inv)
    }

    /// Checks the safety gates (docs/hardware-verification.md section 1) before anything is opened.
    pub fn check_gates(&self) -> Result<(), ProbeError> {
        if self.sub == Subcommand::ResetBootTime && !self.allow_reset {
            return Err(ProbeError::Gate(
                "reset-boot-time silences the board; pass --allow-reset when no test is running"
                    .into(),
            ));
        }
        if self.sub == Subcommand::RangeSweep
            && !self.inputs_safe
            && self.codes.iter().any(|c| *c != AdcRange::default())
        {
            return Err(ProbeError::Gate(
                "non-default ranges need a bench source inside the range; pass --inputs-safe"
                    .into(),
            ));
        }
        Ok(())
    }

    /// Returns the packet budget for a timed run.
    fn packet_budget(&self) -> u64 {
        let per_sec = u64::from(DEFAULT_SAMPLE_RATE_HZ) / SAMPLES_PER_PACKET as u64;
        ((self.duration.as_secs_f64() * per_sec as f64).ceil() as u64).max(1)
    }
}

// ---------------------------------------------------------------------------
// Statistics helpers
// ---------------------------------------------------------------------------

/// Online mean/variance/min/max accumulator.
#[derive(Debug, Clone, Copy)]
struct Running {
    n: u64,
    mean: f64,
    m2: f64,
    min: f64,
    max: f64,
}

impl Running {
    /// Empty accumulator.
    fn new() -> Self {
        Self {
            n: 0,
            mean: 0.0,
            m2: 0.0,
            min: f64::INFINITY,
            max: f64::NEG_INFINITY,
        }
    }

    /// Adds one observation (Welford).
    fn push(&mut self, x: f64) {
        self.n += 1;
        let d = x - self.mean;
        self.mean += d / self.n as f64;
        self.m2 += d * (x - self.mean);
        self.min = self.min.min(x);
        self.max = self.max.max(x);
    }

    /// Summarises as JSON (nulls when empty).
    fn json(&self) -> Value {
        if self.n == 0 {
            return json!({"n": 0});
        }
        json!({"n": self.n, "mean": self.mean, "std": (self.m2 / self.n as f64).sqrt(),
               "min": self.min, "max": self.max})
    }
}

/// Counts `values` into buckets bounded above by `edges` (last bucket is open).
fn histogram(values: &[f64], edges: &[f64]) -> Vec<Value> {
    let mut counts = vec![0u64; edges.len() + 1];
    for v in values {
        let i = edges.iter().position(|e| v < e).unwrap_or(edges.len());
        counts[i] += 1;
    }
    counts
        .iter()
        .enumerate()
        .map(|(i, c)| json!({"lt_ms": edges.get(i), "count": c}))
        .collect()
}

/// Returns min/median/max of `values` as JSON.
fn spread(values: &[f64]) -> Value {
    let mut v = values.to_vec();
    v.sort_by(f64::total_cmp);
    match (v.first(), v.get(v.len() / 2), v.last()) {
        (Some(min), Some(med), Some(max)) => {
            json!({"min_ms": min, "median_ms": med, "max_ms": max})
        }
        _ => json!({}),
    }
}

/// Milliseconds in a duration as f64.
fn ms(d: Duration) -> f64 {
    d.as_secs_f64() * 1000.0
}

// ---------------------------------------------------------------------------
// Session helpers
// ---------------------------------------------------------------------------

/// Connects with the gentle Query-only handshake (no Reset) unless told otherwise.
fn connect<T: Transport>(t: T, handshake: Handshake) -> Result<Connected<T>, ProbeError> {
    let cfg = SessionConfig::default().with_handshake(handshake);
    info!(?handshake, "connecting");
    Session::new(t, cfg)
        .connect()
        .map_err(|e| ProbeError::Session(e.into_parts().0))
}

/// Closes a connected session's transport, logging (not failing) on error.
fn release<T: Transport>(conn: Connected<T>) {
    let mut t = conn.disconnect().into_transport();
    if let Err(e) = t.close() {
        warn!(error = %e, "close failed");
    }
}

/// Summary of one streaming run.
#[derive(Debug, Default)]
struct StreamRun {
    blocks: u64,
    packets: u64,
    wall: Duration,
    dropped_bytes: u64,
    malformed: u64,
    gap_events: u64,
    missed_packets: u64,
    gaps_ms: Vec<f64>,
    read_error: Option<String>,
}

/// Starts streaming, feeds each block to `on_block` until the budget or wall guard, then stops.
///
/// Returns to `Connected` so the caller can run another phase; a failed Stop is fatal.
fn stream<T: Transport>(
    conn: Connected<T>,
    ranges: [AdcRange; 4],
    budget_packets: u64,
    wall_guard: Duration,
    mut on_block: impl FnMut(&Block),
) -> Result<(Connected<T>, StreamRun), ProbeError> {
    let mut s: Streaming<T> = conn
        .start(ranges)
        .map_err(|e| ProbeError::Session(e.into_parts().0))?;
    let mut run = StreamRun::default();
    let begin = Instant::now();
    let mut last = begin;
    while run.packets < budget_packets && begin.elapsed() < wall_guard {
        match s.read_block() {
            Ok(b) => {
                let now = Instant::now();
                run.gaps_ms.push(ms(now - last));
                last = now;
                let st = b.stats();
                run.blocks += 1;
                run.packets += b.packets().len() as u64;
                run.dropped_bytes += st.dropped_bytes;
                run.malformed += st.malformed;
                run.gap_events += st.gap_events;
                run.missed_packets += st.missed_packets;
                on_block(&b);
            }
            Err(e) => {
                warn!(error = %e, "read_block failed; stopping run");
                run.read_error = Some(e.to_string());
                break;
            }
        }
    }
    run.wall = begin.elapsed();
    let mut stopped = match s.stop() {
        Ok(st) => st,
        Err(e) => {
            error!(error = %e.error(), "Stop failed; the board may still be streaming");
            return Err(ProbeError::Session(e.into_parts().0));
        }
    };
    let trailing = stopped.take_trailing().len();
    debug!(trailing, "stream stopped");
    Ok((stopped.restart(), run))
}

/// Common JSON fields of a streaming run.
fn run_json(r: &StreamRun) -> Value {
    json!({
        "blocks": r.blocks, "packets": r.packets, "wall_s": r.wall.as_secs_f64(),
        "dropped_bytes": r.dropped_bytes, "malformed": r.malformed,
        "gap_events": r.gap_events, "missed_packets": r.missed_packets,
        "read_error": r.read_error,
    })
}

// ---------------------------------------------------------------------------
// Subcommands
// ---------------------------------------------------------------------------

/// Runs `enumerate`: lists allow-listed FTDI ports without opening any.
fn enumerate(inv: &Invocation) -> Result<Value, ProbeError> {
    #[cfg(feature = "serial")]
    {
        use sadi_proto::serial::{list_ports, FTDI_ALLOW_LIST};
        if matches!(inv.source, None | Some(Source::Port(_))) {
            let ports = list_ports(&FTDI_ALLOW_LIST)?;
            let list: Vec<Value> = ports
                .iter()
                .map(|p| json!({"name": p.name(), "vid_pid": p.id().to_string(), "product": p.product()}))
                .collect();
            info!(found = list.len(), "enumerated ports");
            return Ok(json!({"ports": list}));
        }
    }
    info!("enumerate: non-port source, nothing to list");
    Ok(json!({"ports": [], "note": "source is not a serial port"}))
}

/// Runs `query`: repeated Query round trips with latency.
fn query<T: Transport>(t: T, inv: &Invocation) -> Result<Value, ProbeError> {
    let mut conn = connect(t, Handshake::QueryOnly)?;
    let mut rows = Vec::new();
    for i in 0..inv.count {
        let at = Instant::now();
        match conn.query() {
            Ok(v) => rows.push(
                json!({"i": i, "ok": true, "state": format!("{:?}", v.state),
                "fw": v.fw_version(), "rtt_ms": ms(at.elapsed())}),
            ),
            Err(e) => {
                warn!(i, error = %e, "query failed");
                rows.push(json!({"i": i, "ok": false, "error": e.to_string()}));
            }
        }
    }
    release(conn);
    Ok(json!({"queries": rows}))
}

/// Runs `reset-boot-time`: Reset repeatedly and time the boot packet.
fn reset_boot_time<T: Transport>(t: T, inv: &Invocation) -> Result<Value, ProbeError> {
    let mut conn = connect(t, Handshake::QueryOnly)?;
    let mut times = Vec::new();
    let mut timeouts = 0u32;
    for i in 0..inv.count {
        let at = Instant::now();
        match conn.reset() {
            Ok(_) => times.push(ms(at.elapsed())),
            Err(e) => {
                warn!(i, error = %e, "reset failed");
                timeouts += 1;
            }
        }
    }
    release(conn);
    Ok(
        json!({"attempts": inv.count, "timeouts": timeouts, "boot_ms": spread(&times),
              "histogram": histogram(&times, &BOOT_EDGES_MS)}),
    )
}

/// Runs `stream-60s-with-gap-stats`: sustained throughput and gap histogram.
fn stream_check<T: Transport>(t: T, inv: &Invocation) -> Result<Value, ProbeError> {
    let conn = connect(t, Handshake::QueryOnly)?;
    let guard = inv.duration * 2 + Duration::from_secs(5);
    let (conn, run) = stream(
        conn,
        [AdcRange::default(); 4],
        inv.packet_budget(),
        guard,
        |_| {},
    )?;
    release(conn);
    let bytes = run.packets * PACKET_BYTES;
    let secs = run.wall.as_secs_f64().max(f64::EPSILON);
    let mut out = run_json(&run);
    out["bytes"] = json!(bytes);
    out["bytes_per_s"] = json!(bytes as f64 / secs);
    out["max_gap_ms"] = json!(run.gaps_ms.iter().copied().fold(0.0, f64::max));
    out["gap_histogram"] = json!(histogram(&run.gaps_ms, &GAP_EDGES_MS));
    Ok(out)
}

/// Runs `range-sweep`: per-channel statistics for each selected range.
fn range_sweep<T: Transport>(t: T, inv: &Invocation) -> Result<Value, ProbeError> {
    let mut conn = connect(t, Handshake::QueryOnly)?;
    let mut table = Vec::new();
    for range in &inv.codes {
        let ranges = [*range; 4];
        let mut raw = [Running::new(); 4];
        let mut ideal = [Running::new(); 4];
        let mut dll = [Running::new(); 4];
        let (c, run) = stream(conn, ranges, inv.packets, Duration::from_secs(10), |b| {
            for s in b.samples() {
                for ch in AdcChannel::ALL {
                    let i = ch.index();
                    raw[i].push(f64::from(s.raw(ch)));
                    ideal[i].push(s.volt(ch, &ranges, AdcMode::Ideal).get());
                    dll[i].push(s.volt(ch, &ranges, AdcMode::DllCompatible).get());
                }
            }
        })?;
        conn = c;
        let channels: Vec<Value> = (0..4)
            .map(|i| {
                json!({"channel": i, "raw": raw[i].json(), "volts_ideal": ideal[i].json(),
                            "volts_dll": dll[i].json()})
            })
            .collect();
        table.push(json!({"code": range.code(), "range": format!("{range:?}"),
                          "run": run_json(&run), "channels": channels}));
    }
    release(conn);
    Ok(json!({"ranges": table}))
}

/// Direction of net encoder travel.
#[derive(Debug, Clone, Copy, Serialize)]
#[serde(rename_all = "snake_case")]
enum Travel {
    Increasing,
    Decreasing,
    Static,
}

/// Runs `encoder-spin`: signed deltas, wraps and discontinuities.
fn encoder_spin<T: Transport>(t: T, inv: &Invocation) -> Result<Value, ProbeError> {
    let conn = connect(t, Handshake::QueryOnly)?;
    let guard = inv.duration * 2 + Duration::from_secs(5);
    let mut prev: Option<i32> = None;
    let (mut total, mut up, mut down, mut max_step, mut jumps, mut high_changes) =
        (0i64, 0u64, 0u64, 0i64, 0u64, 0u64);
    let (mut lo, mut hi) = (i32::MAX, i32::MIN);
    let mut series: Vec<i64> = Vec::new();
    let (conn, run) = stream(
        conn,
        [AdcRange::default(); 4],
        inv.packet_budget(),
        guard,
        |b| {
            let mut net = 0i64;
            for s in b.samples() {
                lo = lo.min(s.encoder);
                hi = hi.max(s.encoder);
                if let Some(p) = prev {
                    let d = i64::from(s.encoder.wrapping_sub(p));
                    net += d;
                    total += d;
                    up += u64::from(d > 0);
                    down += u64::from(d < 0);
                    max_step = max_step.max(d.abs());
                    jumps += u64::from(d.abs() > JUMP_THRESHOLD);
                    high_changes += u64::from((s.encoder >> 16) != (p >> 16));
                }
                prev = Some(s.encoder);
            }
            if series.len() < SERIES_CAP {
                series.push(net);
            }
        },
    )?;
    release(conn);
    let travel = match total.signum() {
        1 => Travel::Increasing,
        -1 => Travel::Decreasing,
        _ => Travel::Static,
    };
    let mut out = run_json(&run);
    out["net_delta"] = json!(total);
    out["travel"] = json!(travel);
    out["positive_steps"] = json!(up);
    out["negative_steps"] = json!(down);
    out["max_abs_step"] = json!(max_step);
    out["discontinuities"] = json!(jumps);
    out["high_word_changes"] = json!(high_changes);
    out["min"] = json!(lo);
    out["max"] = json!(hi);
    out["block_delta_series"] = json!(series);
    Ok(out)
}

/// Runs `digital-in`: distinct PORTD bytes, transitions and toggled bits.
fn digital_in<T: Transport>(t: T, inv: &Invocation) -> Result<Value, ProbeError> {
    let conn = connect(t, Handshake::QueryOnly)?;
    let guard = inv.duration * 2 + Duration::from_secs(5);
    let mut counts: BTreeMap<u8, u64> = BTreeMap::new();
    let mut transitions: Vec<Value> = Vec::new();
    let (mut any, mut all) = (0u8, 0xFFu8);
    let mut last: Option<u8> = None;
    let mut index = 0u64;
    let mut visit = |p: &DataPacket| {
        let v = p.digital_inputs;
        *counts.entry(v).or_default() += 1;
        any |= v;
        all &= v;
        if let Some(prev) = last.filter(|prev| *prev != v) {
            if transitions.len() < SERIES_CAP {
                transitions.push(json!({"packet": index, "from": prev, "to": v}));
            }
        }
        last = Some(v);
        index += 1;
    };
    let (conn, run) = stream(
        conn,
        [AdcRange::default(); 4],
        inv.packet_budget(),
        guard,
        |b| {
            b.packets().iter().for_each(&mut visit);
        },
    )?;
    release(conn);
    let mut out = run_json(&run);
    let seen: BTreeMap<String, u64> = counts
        .iter()
        .map(|(k, v)| (format!("0x{k:02x}"), *v))
        .collect();
    out["values_seen"] = json!(seen);
    out["toggled_bits_mask"] = json!(any & !all);
    out["transitions"] = json!(transitions);
    Ok(out)
}

/// Dispatches one transport-using subcommand.
fn probe<T: Transport>(t: T, inv: &Invocation) -> Result<Value, ProbeError> {
    match inv.sub {
        Subcommand::Enumerate => enumerate(inv),
        Subcommand::Query => query(t, inv),
        Subcommand::ResetBootTime => reset_boot_time(t, inv),
        Subcommand::Stream => stream_check(t, inv),
        Subcommand::RangeSweep => range_sweep(t, inv),
        Subcommand::EncoderSpin => encoder_spin(t, inv),
        Subcommand::DigitalIn => digital_in(t, inv),
    }
}

/// Opens the source, wraps it in the recorder and probes.
fn open_and_probe(inv: &Invocation, captures: CaptureSet) -> Result<Value, ProbeError> {
    let Some(source) = &inv.source else {
        return enumerate(inv);
    };
    match source {
        Source::Sim(name) => {
            let dev = SimDevice::with_scenario(name, SimConfig::default())
                .map_err(|e| ProbeError::Source(e.to_string()))?;
            probe(RecordingTransport::new(dev, captures), inv)
        }
        Source::Replay(path) => {
            let r = ReplayTransport::open(path)?;
            probe(RecordingTransport::new(r, captures), inv)
        }
        Source::Port(name) => open_port(name, inv, captures),
    }
}

/// Opens a real serial port (feature `serial`) and probes it.
#[cfg(feature = "serial")]
fn open_port(name: &str, inv: &Invocation, captures: CaptureSet) -> Result<Value, ProbeError> {
    use sadi_proto::serial::{SerialConfig, SerialTransport};
    let cfg = SerialConfig::new(name).map_err(|e| ProbeError::Source(e.to_string()))?;
    let port = SerialTransport::open(&cfg)?;
    probe(RecordingTransport::new(port, captures), inv)
}

/// Reports that serial support is compiled out.
#[cfg(not(feature = "serial"))]
fn open_port(_: &str, _: &Invocation, _: CaptureSet) -> Result<Value, ProbeError> {
    Err(ProbeError::Source(
        "built without the `serial` feature".into(),
    ))
}

// ---------------------------------------------------------------------------
// Report and entry points
// ---------------------------------------------------------------------------

/// JSON report written beside the capture.
#[derive(Serialize)]
struct Report<'a> {
    tool: &'a str,
    subcommand: &'a str,
    source: String,
    label: &'a str,
    started_unix_ms: u128,
    elapsed_ms: f64,
    status: &'a str,
    error: Option<String>,
    capture_rx: String,
    capture_tx: String,
    rx_bytes: u64,
    tx_bytes: u64,
    data: Value,
}

/// Where a finished run left its files.
#[derive(Debug, Clone)]
pub struct RunSummary {
    /// Report path.
    pub report: PathBuf,
    /// RX capture path.
    pub capture_rx: PathBuf,
    /// TX capture path.
    pub capture_tx: PathBuf,
    /// True when the probe itself succeeded.
    pub ok: bool,
}

/// Size of a file in bytes, 0 if unreadable.
fn file_len(p: &Path) -> u64 {
    std::fs::metadata(p).map(|m| m.len()).unwrap_or(0)
}

/// Runs one invocation end to end: gates, capture, probe, report. Never overwrites a file.
pub fn run(args: &[String], out: &mut dyn Write) -> Result<RunSummary, ProbeError> {
    let inv = Invocation::parse(args)?;
    inv.check_gates()?;
    let started = Instant::now();
    let started_unix_ms = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(0, |d| d.as_millis());
    let stem = format!("{}-{}", inv.label, inv.sub.name());
    let captures = CaptureSet::create_new(&inv.out_dir, &stem)?;
    let (rx, tx) = (
        captures.rx_path().to_path_buf(),
        captures.tx_path().to_path_buf(),
    );
    let report_path = inv.out_dir.join(format!("{}.json", captures.stem()));
    let mut report_file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&report_path)
        .map_err(|source| ProbeError::Io {
            path: report_path.clone(),
            source,
        })?;
    info!(sub = inv.sub.name(), report = %report_path.display(), "probe starting");
    let result = open_and_probe(&inv, captures);
    let (status, error, data) = match &result {
        Ok(v) => ("ok", None, v.clone()),
        Err(e) => {
            error!(error = %e, "probe failed");
            ("error", Some(e.to_string()), Value::Null)
        }
    };
    let report = Report {
        tool: TOOL,
        subcommand: inv.sub.name(),
        source: inv
            .source
            .as_ref()
            .map_or_else(|| "none".into(), Source::label),
        label: &inv.label,
        started_unix_ms,
        elapsed_ms: ms(started.elapsed()),
        status,
        error,
        capture_rx: rx.display().to_string(),
        capture_tx: tx.display().to_string(),
        rx_bytes: file_len(&rx),
        tx_bytes: file_len(&tx),
        data,
    };
    let text = serde_json::to_string_pretty(&report)?;
    report_file
        .write_all(text.as_bytes())
        .and_then(|()| report_file.sync_all())
        .map_err(|source| ProbeError::Io {
            path: report_path.clone(),
            source,
        })?;
    let ok = result.is_ok();
    writeln!(
        out,
        "{} {} report={} rx={}",
        inv.sub.name(),
        status,
        report_path.display(),
        rx.display()
    )
    .map_err(|source| ProbeError::Io {
        path: report_path.clone(),
        source,
    })?;
    Ok(RunSummary {
        report: report_path,
        capture_rx: rx,
        capture_tx: tx,
        ok,
    })
}

/// Program entry: runs the invocation and maps the outcome to an exit code.
fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let mut stdout = std::io::stdout();
    match run(&args, &mut stdout) {
        Ok(s) if s.ok => ExitCode::SUCCESS,
        Ok(_) => ExitCode::from(1),
        Err(e @ ProbeError::Usage(_)) => {
            eprintln!("{e}\n{}", usage());
            ExitCode::from(2)
        }
        Err(e) => {
            eprintln!("{e}");
            ExitCode::from(1)
        }
    }
}
