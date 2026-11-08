# Lab final project: LCTT domain specification
Status: current

Purpose: everything needed to re-implement the LabVIEW final project
(the reference lab VI) in Python. Sources are cited inline.
Source key:

- GUIDE = the lab guide (local)
- VI = description strings embedded in the reference VI,
  the basic variant and the lctt sub-VIs (local)
- REF = the local oracle script (independent Python oracle:
  linest, tare_stats, rss, measured, secant, efit, rss_N, t95)
- T20 / T22 / T27 = transcripts (local;
  session transcripts of 10-20, 10-22, 10-27; timestamps hh:mm:ss)
- INLAB = the in-lab procedure PDF; INTRO =
  the intro procedure PDF
- CAL = the local calibration file; SHORT =
  the local short-run run

## 1. Experiment

Load-controlled tensile test (LCTT) of annealed 32 AWG copper wire. Stress
is imposed with discrete brass weights on a hanger; strain is observed
with an LVDT (displacement transducer) read by the SADI board on AIN0.
(INLAB p3: "use weights to incrementally load a wire and measure
elongation with a LVDT"; T22 08:34:53: "we're going to use an LVDT to
estimate the change in length of the wire".) Only the SADI DAQ from the
lab kit is needed for the final project (INLAB p2).

Wire diameter pre-filled in the VI: d = 2.019E-4 m (GUIDE). Area
A = pi d^2 / 4 = 3.2016E-8 m^2 (verified against SHORT).

## 2. Hardware and device settings

| Item | Value | Source |
|---|---|---|
| DAQ | SADI board, USB; state machine below | GUIDE |
| LVDT signal | AIN0+/AIN0- (ACH0) | INLAB p10 |
| LVDT power | +12 to 20 VDC on RED, -12 to 20 VDC on BLUE, leave supply constant | INLAB p10 |
| ADC range ACH0 | p/m 5.12 V, read once at start-up; changes while running do nothing until restart | GUIDE |
| LVDT output | about +/-5 V over +/-10 mm (20 mm stroke), about 2 mm/V nominal | GUIDE, T22 08:35:25 |
| Linear region | only inside stroke; "5V will occur again" outside, so the same voltage repeats | INLAB p16, T22 08:51:53 |
| Core placement | centre core (about 0 V), then lower mount until |V| about 4.8 V; DO NOT EXCEED 5 V | INLAB p15 |
| Block size | 2500 samples per loop, reported as mean and sample std dev | GUIDE |
| Row rate | about 20 rows/s when "Record continuously" is on (=> about 50 kS/s) | GUIDE |
| Tare averaging | about 85,000 samples in 2 s (=> about 42.5 kS/s) | GUIDE |
| Averaging duration | default 10 s on Test tab; 5-10 s "plenty" | GUIDE |
| No-SADI behaviour | VI goes straight to Close | GUIDE |

Note the two throughput figures differ (50 vs 42.5 kS/s); the true rate is
unknown (see open-questions.md).

SADI state machine (GUIDE): `SADI_check -> Connect_boot -> Check_SW_FW ->
Pend_Start -> Run -> Stop -> Store -> Close`. All user work happens in
Run. The DAQ is treated as perfect: voltage uncertainty comes only from
ADC scatter (GUIDE).

Related earlier-lab files (`data/lab-1`, `data/lab-2`): 16/17-column
tab-delimited dumps from `lab1.vi`/`lab2.vi` (no usable header, 0.151 s
row spacing = 6.6 rows/s). They belong to earlier labs (strain gauge,
Wheatstone bridge; column 14 is 6.9E10 = aluminium E). They are not LCTT
data and are not needed for the port, except that the basic variant
saves lab2's 16 columns first.

## 3. Quantities and formulas

All uncertainties are 95 %, combined by root-sum-square (RSS),
first-order, uncorrelated (VI `lctt_stress_strain_rss.vi`). Guide:
"Report uncertainties to 2 significant figures in your write-up. The file
keeps full precision."

### 3.1 Live voltage

- V = mean of the 2500-sample block; s = sample std dev of the block.
- U_V = 2 s  ("N = 2500 > 200", GUIDE).

### 3.2 Tare (`lctt_tare_stats.vi`)

Blocks i = 1..B of n = 2500 samples, block means m_i, block sample
std devs s_i.

- N = n B;  M = mean(m_i)
- SS = sum((n-1) s_i^2) + n sum((m_i - M)^2)
- Sx = sqrt(SS / (N - 1))
- U_tare = 2 Sx  (k = 2; "95% for N > 200")
- Tare V = M, "Tare N" column = N (samples used)

Record Tare averages for Averaging duration (s); pressing it again
replaces the old tare. Hanger empty, LVDT still.

### 3.3 LVDT calibration (`lctt_linest.vi`; equals LINEST(L, V, TRUE, TRUE))

Points (V_i, L_i), i = 1..n, length L in m.

- xbar, ybar; Sxx = sum((x - xbar)^2); Sxy = sum((x-xbar)(y-ybar))
- slope m = Sxy / Sxx;  intercept b = ybar - m xbar
- SSres = sum((y_i - (m x_i + b))^2);  SStot = sum((y - ybar)^2)
- r^2 = 1 - SSres / SStot
- se_l = sqrt(SSres / (n - 2))
- se_m = se_l / sqrt(Sxx)
- se_b = se_l sqrt(1/n + xbar^2 / Sxx)
- t95 = Student t(0.975, n - 2);  U95_m = t95 * se_m
- n < 3: all std errors, t95 and U95 are NaN; slope/intercept need n >= 2.

Only the slope is used for converting dV to dL (GUIDE). Expected: r^2 >=
0.9999, slope about 0.002 m/V. Capture: type "Cal point length (m)" first;
the length latched is the value at the moment Capture Cal Point is pressed
(the iteration where recording starts). Capture averages V for Averaging
duration using the block pooling of 3.2; point stored as (mean V, length,
U95). At least 3 points, 5+ better; stay inside |V| <= 4.9 V. Remove Last
Cal Point / Clear Cal Points edit the set; "Use manual cal table" switches
to typed voltages and lengths. Export Calibration writes
`lvdt_calibration.txt` (tab-delimited: header, one (V, L) line per point,
then name/value lines in order slope, intercept, se slope, se intercept,
r^2, se l, n, t95, U95 slope, Tare V, U Tare V, Tare Sx, Tare N).

Reference result (CAL, n = 12): slope 2.114583E-3 m/V, intercept
2.472866E-2 m, se slope 6.734580E-6, se intercept 1.970728E-5, r^2
0.9998986, se_l 6.790817E-5 m, t95 2.228139, U95 slope 1.500558E-5 m/V.
I re-fitted the 12 points in SHORT's header with numpy and reproduced
these to 6 digits (slope 0.00211458, se_m 6.734591E-6, r^2 0.99989858).

### 3.4 Strain and stress (`lctt_stress_strain_rss_N.vi`)

```
dV   = V - V_tare            U_dV  = sqrt(U_V^2 + U_tare^2)
dL   = m * dV                U_dL  = sqrt((dV*U_m)^2 + (m*U_dV)^2)
eps  = dL / L0               U_eps = sqrt((U_dL/L0)^2 + (dL*U_L0/L0^2)^2)
F    = W_load + W_hanger     U_F   = sqrt(U_load^2 + U_hanger^2)
A    = pi d^2 / 4            U_A   = pi d U_d / 2
sig  = F / A                 U_sig = sqrt((U_F/A)^2 + (F*U_A/A^2)^2)
```

Weights are entered in newtons (balance reads N), so no g in the "_N"
variant (the kg variant `lctt_stress_strain_rss.vi` uses F = (m_load +
m_hanger) g). W_load excludes the hanger. Verified against SHORT: strain
reproduced to 2E-11, stress to 0.05 Pa.

### 3.5 Moduli

- Secant (`lctt_E_secant.vi`): E = sig / eps;
  U_E = sqrt((U_sig/eps)^2 + (sig U_eps/eps^2)^2)
  (= E sqrt((U_sig/sig)^2 + (U_eps/eps)^2) but defined at sig = 0).
  NaN when |eps| < 1E-9.
- Fitted (`lctt_E_fit.vi`): logged points (eps, U_eps, sig, U_sig) are
  stored on every Log single point; E_fit = slope of the least-squares
  line sig = E eps + b using the same linest over points first..last
  (1-based; last <= 0 means all). E needs n >= 2, U95 = t95(n-2) *
  se_slope needs n >= 3. Also stores r^2 and intercept. Cleared by Clear
  E points, trimmed by Remove last E point, emptied on the first call of
  each run. Graph shows stress in MPa. GUIDE: "Annealed copper should
  give roughly 110-130 GPa."

### 3.6 Measured inputs (`lctt_measured_rss.vi`; L0, d, hanger weight)

Readings that are NaN or exactly 0 are ignored (blank cells).

- n = 0: value = typed value, U = typed U (Test-tab values keep working)
- n = 1: value = the reading, U_stat = 0, U = U_inst
- n >= 2: value = mean, s = sample std dev, t95 = t(0.975, n - 1),
  U_stat = t95 s / sqrt(n), U = sqrt(U_stat^2 + U_inst^2)

Each is logged to the header as `<name> readings, n readings, mean, U
stat, U inst, used, U used`. Defaults visible in SHORT: U_inst L0 =
0.0005 m, d = 2.5E-6 m, hanger = 1E-4 N.

### 3.7 Load uncertainty (`lctt_load_u.vi`)

U_load = sqrt(U_typed^2 + N U_per^2), N = number of weights on the hanger
(N <= 0 counts as 0). Header rows: `U load weight typed (N)`, `U per
weight (N)`, `number of weights on hanger`.

## 4. CSV output

Writer `lctt_write_csv.vi`: RFC-4180, comma delimited, CRLF, overwrites;
numbers `%#_10g` (10 significant digits, trailing zeros removed, "."
decimal regardless of locale); NaN written `NaN`, `Inf`/`-Inf`. Fields
containing comma, quote, CR, LF are quoted with doubled quotes. Empty
path or Not-a-Path => save dialog (`*.csv`, default `lctt_YYYYMMDD_HHMMSS.csv`);
cancelling writes nothing (run lost). The file is written ONLY at Stop;
rows are held in memory (`lctt_QueueSave.vi`, a functional global with
named queue `_lctt_save_all_data`; a FALSE->TRUE change of Save Data?
counts one more segment).

Layout (verified against SHORT):

1. `<course> LCTT final project data`
2. `date,YYYY-MM-DD HH:MM:SS`
3. `operator,...`
4. `description,...`
5. key,value metadata rows, in this order in SHORT: ACH0 range, Averaging
   duration (s), Tare V, U Tare V, Tare Sx, Tare N, Cal slope, Cal
   intercept, Cal std err slope, Cal std err intercept, Cal r^2, Cal n,
   Cal t95, Cal U95 slope, wire dia d typed, U d typed, L0 typed, U L0
   typed, hanger weight typed, U hanger typed, `cal point i` ("V,L"
   quoted), then the three measured-input blocks (L0, wire dia d, hanger
   weight; 7 rows each), `U load weight typed (N)`, `U per weight (N)`,
   `number of weights on hanger`, `E fit (Pa)`, `U95 E fit (Pa)`,
   `E fit intercept (Pa)`, `E fit r^2`, `E fit n`, `E fit first point`,
   `E fit last point`, `E points logged`, `E point i` =
   "strain,U strain,stress,U stress".
6. blank line
7. column header, then one line per row (below).

32 columns (GUIDE; confirmed by SHORT header line):

| # | Column | Meaning |
|---|---|---|
| 1 | Elapsed Time (s) | seconds since VI start |
| 2 | LVDT V (V) | block mean |
| 3 | LVDT std dev (V) | block sample std dev |
| 4 | U LVDT V (V) | 2 x std dev |
| 5 | Tare V (V) | tare mean |
| 6 | U Tare V (V) | 2 Sx |
| 7 | Tare N | samples used |
| 8 | Cal slope (m/V) | |
| 9 | Cal U95 slope (m/V) | |
| 10 | Cal intercept (m) | |
| 11 | Cal r^2 | |
| 12 | Cal n | |
| 13 | dV (V) | V - Tare V |
| 14 | U dV (V) | |
| 15 | dL (m) | slope dV |
| 16 | U dL (m) | |
| 17 | L0 (m) | |
| 18 | U L0 (m) | |
| 19 | load weight (N) | added weights, no hanger |
| 20 | U load weight (N) | |
| 21 | hanger weight (N) | |
| 22 | U hanger weight (N) | |
| 23 | d (m) | |
| 24 | U d (m) | |
| 25 | F (N) | load + hanger |
| 26 | U F (N) | |
| 27 | strain | dL / L0 |
| 28 | U strain | |
| 29 | stress (Pa) | F / A |
| 30 | U stress (Pa) | |
| 31 | E secant (Pa) | sig / eps |
| 32 | U E secant (Pa) | |

Discrepancy: the the reference VI description string says "30 columns
per row" whereas GUIDE and SHORT have 32 (the E secant pair was added
later). The 32 is authoritative. the basic variant (backup) saves
lab2's 16 columns followed by 24 LVDT columns = 40, via the older
`tools\QueueSave.vi` / WriteSpreadsheet path, with manual calibration
slope, manual tare (button "Tare = current reading" uses a single block's
mean and 2 std dev), and `lctt_stress_strain_rss.vi`.

## 5. UI inventory (reference VI)

Seven tabs (GUIDE): Start here, Test, Measurements, Modulus, Calibration,
Details, Device / DAQ setup. (The VI description lists five names - Start
here, Test, Calibration, Details, Device / DAQ setup - and predates the
Measurements and Modulus tabs.)

Test tab: Stop, elapsed time, Record Tare, Averaging duration (s), Log
single point, Record continuously (switch, about 20 rows/s), CSV file path,
Operator / group, Run description, live LVDT V (V) readout and chart,
Tare V / U Tare V, SPECIMEN INPUTS (L0, wire dia d, hanger weight (N),
load weight (N), each with an uncertainty box; SI units), RESULTS (dL,
strain, stress with U), MODULUS (secant E), Saved to, Rows recorded,
Segments Saved, Recording progress (s).
Measurements tab: readings arrays + instrument U for L0, d, hanger weight;
U per weight (N); number of weights on hanger.
Modulus tab: E fit, U95, r^2, E fit first point / last point (last = 0 =
all), Clear E points, Remove last E point, stress (MPa) vs strain graph.
Calibration tab: Cal point length (m), Capture Cal Point, Remove Last Cal
Point, Clear Cal Points, three Captured arrays, Use manual cal table,
Manual Cal Voltages (V), Manual Cal Lengths (m), slope/intercept/r^2/n,
graph, Export Calibration....
Details tab: LVDT std dev, tare Sx and N, fit standard errors and t,
intermediate dV / F / A, loop timing, Saved column order, error clusters
(calculation / save error out).
Device / DAQ setup: SADI connection codes (Number of SADI), ADC range for
ACH0-ACH3, software/firmware versions, SADI State.

Lights and thresholds:

| Light | Condition |
|---|---|
| RECORDING | a data row is being saved this loop |
| Recording... | a tare or cal average in progress; only one at a time; if both pressed in the same instant the calibration capture wins |
| LVDT near saturation | |V| > 4.9 V; never lights if the ADC range is smaller than +/-5.12 V |
| error out | green check = OK; otherwise code and source |

Behaviour notes: values in the input boxes are sampled at the moment a
row is logged ("Every saved row uses the values shown at the moment it is
logged"). Log single point also adds an E point. Press Stop (not Abort)
to write the file.

## 6. Lab procedure (what the student does)

GUIDE short version: (1) leave ACH0 at p/m 5.12 V, Run; (2) calibrate: type
length, Capture Cal Point, >= 3 points; (3) type repeated readings of L0,
d, hanger weight; (4) hanger unloaded, Record Tare; (5) enter operator,
description, path; (6) per weight add it, set load weight (N) to the total
added, wait to settle, Log single point; (7) Stop. Also see INLAB:
clamp wire on the hanger and the fixture with one or two wraps around the
binding posts (INLAB p11-14); slide the LVDT mount so the core sits near
the middle of the 20 mm travel (about 10 mm proud of the coil), confirm
about 0 V, then lower the mount until |V| approaches 4.8 V (INLAB p15,
p18-19). Hanger has mass; decide where active length is measured; "Weights
go somewhere when wire breaks!" (INLAB p21). Units: SI recommended; area
in m^2 and force in N give Pa; strain in consistent units (INLAB p6).
Suggested prelab: estimate yield and breaking loads (INLAB p7; T22
08:46:25); decide whether to weigh weight groups together or individually
(INLAB p7, T22 08:52:45-08:52:51: "that's going to have to be defended
quantitatively"); compute the longest wire that will break before
saturating the 20 mm LVDT (INLAB p8; T22 08:46:55 "make sure you choose
appropriate lengths for the part of the stress strain curve you're trying
to define").

Procedure design expectations from the instructor (transcripts):

- T20 09:01:44 "there's a lot of nuances to implementation of the
  procedure to actually find yield points, [elasticity], and ultimates."
- T20 09:01:54-09:01:58 "Once you're in the plastic range with a copper
  wire, copper creeps. Pretty significantly. And so your procedure needs
  to acknowledge that and try to address that."
- T20 09:02:31 plan an exploratory session, then iterate: "not think that
  you're going to get the procedure implementation correct the first
  time."
- T20 09:02:06 groups of up to 5; leniency is low; the procedure "just has
  to anticipate all the issues".
- T22 08:41:11 "typically with yield point determination with load
  control, you can iteratively load and unload, checking for permanent
  deformation." T22 08:41:29 or "take a pretty rich set of data ... and
  plot it and do an offset yield point".
- T22 08:36:04 tare is still needed "because of how we're using it".
- T22 08:47:22-08:47:56 a single spool of wire; spools test differently,
  so use the same spool for consistency across lab sessions.
- T22 08:51:53 outside the linear range "your calibration constant doesn't
  matter".

## 7. Grading and reporting requirements

Compiled from the transcripts; the course rubric itself is NOT in
the provided material (see open-questions.md).

- Final project is due the day after Dec 1 (T27 08:32:45: "December 1st ...
  catch-all closeout lecture ... because the final project is due the next
  day" - i.e. due Dec 2). Groups 3 to 5 students (T20 08:58:15).
- Uncertainty: 95 % confidence from a Student t distribution (T20
  08:43:25: "do a 95% confidence interval based on a student's t-
  distribution"). Where ASTM D6272 (flexure) defines results use its
  definitions, but keep the class sig-fig convention for random uncertainty
  (T20 08:44:42-08:44:53). Dimension measurement: take 10 measurements and
  use Student's t (T20 09:06:18); if the t-interval is much smaller than the
  instrument resolution, the instrument resolution governs (T20 09:06:31).
- Significant figures: "milestone has instructions on units and
  significant figures. Follow those explicitly" (T27 08:34:34); "three
  significant figures in our final reporting result" (T27 08:34:43); "right
  to 5 sig figs. They really should be" for calculation checks (T27
  08:37:08). GUIDE: 2 significant figures for uncertainties in write-up.
- Yield: for a brittle material do not expect a yield point (T27
  08:41:54); for offset yield, show a subplot of the elastic region plus a
  little plastic, the offset line and the regression region; "make sure the
  reader understands the regions" used for E (T27 08:42:15-08:42:32). Note
  these are about Lab 4, but the same logic applies to the offset yield of
  the wire.
- Regrades: only through the posted procedure (T27 08:41:22, 08:44:29).
- Late changes: group moves cost 10 points each time (T20 08:59:14).

## 8. Failure modes to model

- LVDT out of range (|V| > 4.9 V) => nonlinear, folded response.
- Strain negative: core moves toward negative V when the wire stretches,
  or calibration lengths run in the opposite direction; check the sign of
  the cal slope (GUIDE). SHORT shows exactly this (see
  preliminary-data-analysis.md).
- Cal U95 NaN with < 3 points.
- Only one averager at a time.
- Rows lost if the run is aborted or the save dialog cancelled.
- Copper creep in the plastic range (T20 09:01:54), wire slip in the
  clamps (the same lecture series notes a specimen "slipped out of the
  grips" in Lab 3: T27 08:49:56, with viscoelastic recovery noted at
  08:50:36), and initial slack are the physical confounders; the software
  cannot distinguish them from one another.
- Python port oracle: the local oracle script and
  the local CSV check script already encode the formulas and the
  CSV check; reuse them as the acceptance test.
