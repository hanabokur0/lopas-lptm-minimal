## Overview　

This repository provides a minimal implementation of LPTM (LoPAS Phase Transition Model) enhanced with:

- Second-order PST dynamics (delta2_PST)
- HI2-style hysteresis layer control
- Improved robustness around critical oscillation band (COB)

It demonstrates how phase transition detection can move from static thresholding to motion-aware interpretation.

# LPTM Minimal with delta2_PST + HI2

A minimal LPTM implementation updated to support:

* **PST dynamics** (`pst`, `delta_pst`, `delta2_pst`)
* **HI2-style hysteresis** for stable layer transitions
* reduced chattering around the **COB** (critical oscillation band)

This patch changes LPTM from a single-point threshold classifier into a lightweight motion-aware transition detector.

---

## Why this patch exists

The previous minimal LPTM judged transitions mainly from a single PST value.

That was enough for rough routing, but it had two practical weaknesses:

1. **Noise vs real phase transition was hard to separate**
2. **Layer assignment could chatter near the threshold**

The updated version fixes this by adding:

* **`delta_pst`**: first-order change
* **`delta2_pst`**: second-order change / acceleration
* **HI2-style hysteresis**: layer transitions now depend on prior state, not only the current value

---

## Core concepts

### PST

The present transition signal.

### delta_PST

The first derivative of PST.
It measures whether the system is moving upward or downward.

### delta2_PST

The second derivative of PST.
It measures whether the movement is accelerating, flattening, or reversing.

### HI2

A hysteresis-style rule for layer assignment.
Once the system enters a higher layer, it does not immediately drop back on a small reversal.
This suppresses threshold chattering.

---

## What changed

### Added structures

* `PSTSnapshot`
* `LPTMLayer`

### Added functions

* `compute_base_pst(...)`
* `compute_pst_dynamics(...)`
* `classify_transition(...)`
* `apply_hysteresis(...)`

### Updated execution flow

`run_lptm_minimal(...)` now accepts previous PST values and previous layer to make motion-aware decisions.

---

## Transition interpretation

The implementation distinguishes several states:

* **`stable_or_noise`**: weak or non-meaningful movement
* **`cob_oscillation`**: threshold-near oscillation, likely critical-band chatter
* **`phase_rising`**: sustained upward transition movement
* **`false_peak`**: local high value that is already decelerating downward
* **`breakout`**: strong, likely genuine phase transition

This lets LPTM interpret not only *where the system is*, but *how it is moving*.

---

## Why hysteresis matters

Without hysteresis, PST near a boundary can produce unstable layer flips:

* `0.64 -> 0.66 -> 0.63 -> 0.67`

This often creates repeated `L1 <-> L2` switches.

With HI2-style hysteresis:

* entering `L2` requires a stronger upward condition
* exiting `L2` requires a different, lower boundary
* `L3` also has a separate decay rule

This is more faithful to phase behavior than a single threshold.

---

## Minimal usage

```python
from lptm_e2e_minimal import run_lptm_minimal, LPTMLayer

result = run_lptm_minimal(
    doq=0.70,
    cci=0.64,
    hgd=0.58,
    trs=0.62,
    prev_pst=0.63,
    prev_prev_pst=0.61,
    prev_layer=LPTMLayer.L1,
)

print(result)
```

Expected output includes:

* current `pst`
* `delta_pst`
* `delta2_pst`
* transition label
* hysteresis-adjusted `layer`

---

## Design intent

This is still a **minimal** implementation.
It does not attempt full probabilistic inference or full LPTM field modeling.
Instead, it introduces the smallest possible patch that materially improves:

* robustness
* interpretability
* threshold stability
* distinction between noise and genuine transition

---

## Recommended next steps

1. Add `pst_dynamics` to `/v1/eval`
2. Log transition class frequencies for calibration
3. Add RNC hard-gate behavior for `L3`
4. Introduce UDV-style deeper inference when uncertainty is high
5. Backtest against known cycle logs

---

## Summary

This patch upgrades minimal LPTM from:

* **single-point phase judgment**

to:

* **motion-aware phase interpretation**
* **history-aware layer stability**

In practical terms, it is the step from a static threshold model to a lightweight phase-transition detector.

## Cloudflare Worker API

Deployed endpoint:
- `GET /`
- `POST /v1/eval`

Example request body:

```json
{
  "doq": 0.70,
  "cci": 0.64,
  "hgd": 0.58,
  "trs": 0.62,
  "prev_pst": 0.63,
  "prev_prev_pst": 0.61,
  "prev_layer": "L1"
}
