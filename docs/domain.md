# LCTT domain specification
Status: current

Purpose: the physics, formulas and conventions the LCTT lab module
(`sadi.labs.lctt`) implements. SADI is a USB data-acquisition board; the
load-controlled tensile test (LCTT) is a generic experiment built on it.

## 1. Experiment

A load-controlled tensile test loads a wire specimen with discrete
weights on a hanger and observes elongation with an LVDT (linear variable
differential transformer) read by one SADI analog input. The wire
diameter d gives the cross-section A = pi d^2 / 4; the unloaded gauge
length L0 is measured before the test.

Forces may be entered in newtons or as mass times g (kg * g, g =
9.80665 m/s^2); internally force is always newtons.

## 2. Hardware and device settings

- The LVDT output goes to one differential analog input; its supply is
  held constant and is never changed while the board is streaming.
- The ADC range is read once at start-up; changing it while running has
  no effect until restart.
- The LVDT is linear only inside its stroke; outside it the response
  folds back and the same voltage can repeat. Keep |V| below a
  configurable saturation threshold (default 4.9 V on a 5.12 V range).
- Each displayed sample is a block mean with the block sample standard
  deviation; block size and rate are configurable.
- The DAQ is treated as ideal: voltage uncertainty comes only from ADC
  scatter.

## 3. Quantities and formulas

All uncertainties are 95 % intervals combined first-order by
root-sum-square (RSS), treating inputs as uncorrelated unless stated.
Results are reported to 3 significant figures and uncertainties to 2; the
stored data keeps full precision. Correlated inputs (for example the
slope and intercept of the same fit) are handled by the covariance-aware
propagation in `sadi.uncertainty`; this page gives only the uncorrelated
closed forms.

### 3.1 Live voltage and uncertainty

- V = mean of the block of n samples; s = sample standard deviation.
- U_V = 2 s (k = 2, adequate for n > 200).
- Small repeated-reading sets use Student t: U = t(0.975, n - 1) s /
  sqrt(n), combined by RSS with the instrument uncertainty.

### 3.2 Tare

The tare is the LVDT voltage with the hanger empty and the specimen
still. Record B blocks i = 1..B of n samples, with block means m_i and
block sample standard deviations s_i, and pool them:

- N = n B;  M = mean(m_i)
- SS = sum((n-1) s_i^2) + n sum((m_i - M)^2)
- Sx = sqrt(SS / (N - 1))
- U_tare = 2 Sx
- Tare voltage = M; recording again replaces the previous tare.

A manual tare entry (a typed voltage and uncertainty) is also allowed.

### 3.3 LVDT calibration

Calibration is a linear least-squares fit of length L (m) against LVDT
voltage V from n points (V_i, L_i):

- xbar, ybar; Sxx = sum((x - xbar)^2); Sxy = sum((x - xbar)(y - ybar))
- slope m = Sxy / Sxx;  intercept b = ybar - m xbar
- SSres = sum((y_i - (m x_i + b))^2);  SStot = sum((y - ybar)^2)
- r^2 = 1 - SSres / SStot
- se_l = sqrt(SSres / (n - 2))
- se_m = se_l / sqrt(Sxx)
- se_b = se_l sqrt(1/n + xbar^2 / Sxx)
- t95 = Student t(0.975, n - 2);  U95_m = t95 se_m
- n < 3: standard errors, t95 and U95 are NaN; slope and intercept need
  n >= 2.

Only the slope is used to convert a voltage change to a displacement
change; the intercept is an arbitrary gauge offset. Use at least 3 points
(5 or more is better), all inside the linear region. The sign of the
slope matters: a negative slope with a stretching wire gives negative
strain, so check it.

### 3.4 Strain and stress

```
dV   = V - V_tare            U_dV  = sqrt(U_V^2 + U_tare^2)
dL   = m * dV                U_dL  = sqrt((dV*U_m)^2 + (m*U_dV)^2)
eps  = dL / L0               U_eps = sqrt((U_dL/L0)^2 + (dL*U_L0/L0^2)^2)
F    = W_load + W_hanger     U_F   = sqrt(U_load^2 + U_hanger^2)
A    = pi d^2 / 4            U_A   = pi d U_d / 2
sig  = F / A                 U_sig = sqrt((U_F/A)^2 + (F*U_A/A^2)^2)
```

W_load excludes the hanger. Each weight contributes an uncertainty, so
U_load = sqrt(U_typed^2 + N U_per^2) for N weights on the hanger.

### 3.5 Modulus

- Secant: E = sig / eps;
  U_E = sqrt((U_sig/eps)^2 + (sig U_eps/eps^2)^2), defined at sig = 0.
  NaN when |eps| is below 1E-9.
- Fitted: logged points (eps, U_eps, sig, U_sig) are fitted by least
  squares with the same linear fit as 3.3, sig = E eps + b, over a chosen
  first..last window. E needs n >= 2 points; U95 = t95(n - 2) se_slope
  needs n >= 3. The window is chosen by hand and may be suggested
  automatically but never silently applied.

### 3.6 Measured inputs

L0, diameter and hanger weight may be entered as repeated readings.
Readings that are NaN or exactly 0 are ignored (blank cells).

- n = 0: use the typed value and uncertainty.
- n = 1: value = the reading, U = instrument uncertainty.
- n >= 2: value = mean, s = sample standard deviation,
  U_stat = t(0.975, n - 1) s / sqrt(n), U = sqrt(U_stat^2 + U_inst^2).
  If the t interval is far below the instrument resolution, the
  resolution governs.

## 4. Data output

Each run is exported as CSV: RFC-4180, comma delimited, CRLF, numbers at
10 significant digits with "." as decimal separator, NaN and Inf written
literally. A metadata block (date, operator, description, tare,
calibration, specimen inputs, modulus fit) precedes a blank line and a
column header with one row per logged point. The durable session design
that guarantees no run is lost is in `data-safety.md`; the export format
is in `store/csv-export.md`.

## 5. Yield and offset

The yield point is found by the 0.2 % offset method: draw a line with the
elastic modulus E through (eps = 0.002, sig = 0) and take the first
intersection with the stress-strain curve. Show the elastic region, the
offset line and the regression region so the E window is clear. A brittle
specimen has no yield point. Load-and-unload cycles that check for
permanent deformation are an alternative.

## 6. Procedure outline

1. Leave the ADC range at its default and start the run.
2. Calibrate: enter the known length, capture a point, repeat for at
   least 3 points across the stroke.
3. Enter repeated readings of L0, d and the hanger weight.
4. With the hanger unloaded and the LVDT still, record the tare.
5. For each weight: add it, set the total load, wait until the strain
   settles (3.7), then log a point.
6. Stop the run; the data is already durable.

Mount the LVDT core near the middle of its stroke (about 0 V) and then
position it so the expected total elongation stays inside the linear
region. Estimate yield and breaking loads beforehand to choose a wire
length that breaks before saturating the LVDT. Use the same wire spool
across sessions for consistency.

## 7. Settle, creep and slip

- Settle: after a load step the strain keeps drifting. A point is
  settled when the drift rate stays below a tolerance over a window (see
  `lctt/settle.md`).
- Creep: in the plastic range metals creep at constant load, so strain
  rises slowly with log time; see `lctt/creep.md`.
- Slip: the wire can slip in the clamps, producing a strain jump with no
  load change; see `lctt/slip.md`. Initial slack looks similar.

The software cannot always tell these confounders apart from one another;
it flags them and leaves the decision to the operator.

## 8. Failure modes to model

- LVDT out of range (|V| above the saturation threshold): nonlinear,
  folded response.
- Negative strain: the core moves toward negative V as the wire
  stretches, or calibration lengths run the opposite way; check the sign
  of the slope.
- Calibration U95 is NaN with fewer than 3 points.
- Only one averager (tare or calibration capture) runs at a time.
- Rows lost if the process dies before they are durable; the session
  design prevents this (`data-safety.md`).
- Creep, clamp slip and initial slack as in section 7.
