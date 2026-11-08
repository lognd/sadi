# Open questions for the user
Status: draft

Only the user can settle
these. Each lists the default I would assume if unanswered.

## Scope

1. Live DAQ or post-processing? Default: both, with a simulated source.
2. CSV layout: the 32-column layout is the default; other layouts are
   export options, not defaults.
3. Should the E-fit window auto-select the linear elastic region, or stay
   as manual first/last point? Default: manual; auto only as a hint.
4. Target sample rate and block size? Default: configurable, 2500
   samples per block.

## Method and uncertainty

5. U voltage: keep U_V = 2 s of a single block (N > 200), or use the
   standard error of the mean (2 s/sqrt(N), about 100 times smaller)?
   Default: 2 s, with the alternative as an option.
6. Calibration lengths may be absolute gauge positions; only the slope
   matters and the intercept is an offset.
8. Default L0 and maximum load: maximum wire length is bounded by the LVDT
   travel and the break strain.
9. Handling creep and slip: hold times, unload cycles and offset-yield
   analysis are supported (see lctt/creep.md, lctt/slip.md).
10. LVDT sign: warn when the calibration slope times dV is negative for a
   rising load rather than flipping the sign silently.

## Reporting

13. Significant figures: 3 s.f. for results and 2 s.f. for uncertainties by
    default; configurable (see core/formatting.md).

## Confirm

14. Saturation threshold (4.9 V) vs mounting guidance (4.8 V) vs ADC
    range (5.12 V); throughput inferred from block size and row rate.

Real runs through break are not in the repo; the simulator (`sadi_proto::sim`)
is the oracle for settle, creep and slip logic.
