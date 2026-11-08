# Open questions for the user
Status: draft

Only the user (or the instructor material not in the repo) can settle
these. Each lists the default I would assume if unanswered.

## Scope of the Python port

1. Live DAQ or post-processing? Must the Python tool talk to the SADI
   board (wire protocol under reverse engineering in a separate task) or
   only read/validate CSVs and compute? Default: both, with a simulated
   source.
2. Which VI is the target: the reference VI (32 columns) or
   the basic variant (40 columns)? Default: 32-column
   reference VI; the "30 columns" in its description is stale.
3. Should the E-fit window auto-select the linear elastic region, or stay
   as manual first/last point? Default: manual, as in LabVIEW.
4. Target sample rate and block size (2500 samples at about 20 rows/s vs
   the 50 or 42.5 kS/s inferred)? Default: configurable.

## Method and uncertainty

5. U voltage: keep U_V = 2 s of a single block (class rule, N > 200),
   or use the standard error of the mean (2 s/sqrt(N), about 100 times
   smaller)? The first is as specified; the second is statistically
   defensible for the mean. Default: 2 s, with the alternative as an
   option.
6. "Heights" in the calibration: the cal lengths in the data are absolute
   gauge positions (15.6 to 34.7 mm). Confirm that only the slope matters
   and the intercept is just a height offset.
8. Intended L0 and maximum load: the file uses L0 = 0.08313 m, the guide
   says typically 0.5 m. Which should defaults use? Maximum wire length is
   bounded by the 20 mm LVDT travel and break strain.
9. Handling creep and slip: should the tool support hold times, unload
   cycles, or an offset-yield analysis? The instructor says the procedure
   must address creep (T20 09:01:54).
10. LVDT sign: should the Python tool flip strain sign automatically
    when the cal slope times dV is negative for a rising load, or just warn?
    the local short-run file has negative strain for positive stress.

## Data provenance

11. Is the local short-run run a real run or a simulated one? Why was no tare
    recorded, and why do all typed uncertainties read 0? Is its
    low modulus (about 16 GPa initially) a real finding?
12. Is there any other LCTT data, e.g. a complete run through break?
    Only this file exists.

## Grading

13. The course rubric and milestone text are not in the repo
    (only transcripts). Please supply them to check units and
    significant-figure requirements (3 s.f. results, 2 s.f. uncertainty)
    against what the tool should print.
14. Discrepancies to confirm: saturation light at 4.9 V vs setup at 4.8 V
    vs ADC range 5.12 V; throughput 50 vs 42.5 kS/s; tab count 7 (guide)
    vs 5 (VI description).

## Coverage that I could not fully close

- The `.vi` binaries are compressed; only embedded descriptions were
  extracted, so control labels beyond those are inferred from the guide.
- `example_main.c`, `momLab.lvlib`, `SADI_MOM_V1_2_start.vi`, SADI_FIRMWARE
  and FTDI folders were not read (hardware protocol, covered by the
  separate agent ab17e8869063d0659, still running).
- Several PDF pages are images (INLAB pages 5 and 9), not extractable.
