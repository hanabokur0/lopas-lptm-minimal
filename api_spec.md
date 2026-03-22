# API Specification: LPTM Minimal with delta2_PST + HI2

## Version

`v0.2-minimal-dynamics`

---

## Overview

This API extends minimal LPTM evaluation with:

* PST dynamics
* second-order transition sensitivity
* hysteresis-based layer assignment

The purpose is to improve the stability and interpretability of phase judgments in borderline conditions.

---

## Endpoint

### `POST /v1/eval`

Evaluates a single minimal LPTM state and returns phase-transition dynamics.

---

## Request body

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
```

### Fields

#### `doq`

* Type: `number`
* Range: `0.0 - 1.0`
* Description: current DoQ score

#### `cci`

* Type: `number`
* Range: `0.0 - 1.0`
* Description: current CCI score

#### `hgd`

* Type: `number`
* Range: `0.0 - 1.0`
* Description: current HGD score

#### `trs`

* Type: `number`
* Range: `0.0 - 1.0`
* Description: current TRS score

#### `prev_pst`

* Type: `number`
* Range: `0.0 - 1.0`
* Description: PST from the previous cycle

#### `prev_prev_pst`

* Type: `number`
* Range: `0.0 - 1.0`
* Description: PST from two cycles ago

#### `prev_layer`

* Type: `string`
* Allowed: `L1`, `L2`, `L3`
* Description: previously assigned LPTM layer

---

## Response body

```json
{
  "pst": 0.652,
  "delta_pst": 0.022,
  "delta2_pst": 0.014,
  "transition": "phase_rising",
  "layer": "L2"
}
```

### Fields

#### `pst`

* Type: `number`
* Description: current computed PST value

#### `delta_pst`

* Type: `number`
* Description: first-order change of PST

#### `delta2_pst`

* Type: `number`
* Description: second-order change of PST

#### `transition`

* Type: `string`
* Allowed values:

  * `stable_or_noise`
  * `cob_oscillation`
  * `phase_rising`
  * `false_peak`
  * `breakout`

#### `layer`

* Type: `string`
* Allowed: `L1`, `L2`, `L3`
* Description: hysteresis-adjusted current layer

---

## Semantics

### Base PST

`pst` is the present transition signal computed from current indicator inputs.

### First-order change

`delta_pst` indicates direction and speed of change.

### Second-order change

`delta2_pst` indicates acceleration or deceleration.
This helps distinguish a real breakout from a local noisy fluctuation.

### Hysteresis

`layer` is not assigned by a single fixed threshold.
Instead, it depends on:

* current PST dynamics
* transition class
* previous layer

This reduces unstable toggling near the critical band.

---

## Layer policy

### `L1`

Individual or low-intensity phase.

### `L2`

Social or field-relevant phase.
Entered when upward motion is sustained enough to justify promotion.

### `L3`

High-risk or high-impact phase.
Should normally be paired with external governance rules or human review in full protocol mode.

---

## Example interpretations

### Case A: noisy threshold crossing

Input pattern:

* PST near `0.65`
* low `delta_pst`
* near-zero `delta2_pst`

Expected response:

* `transition = cob_oscillation`
* layer remains stable under hysteresis

### Case B: genuine transition growth

Input pattern:

* PST rising
* positive `delta_pst`
* non-negative `delta2_pst`

Expected response:

* `transition = phase_rising`
* possible promotion to `L2`

### Case C: breakout

Input pattern:

* high PST
* strong positive `delta_pst`

Expected response:

* `transition = breakout`
* possible promotion to `L3`

---

## Validation rules

* all score inputs should be normalized to `0.0 - 1.0`
* `prev_layer` must be one of `L1`, `L2`, `L3`
* missing prior values should be initialized conservatively, typically:

  * `prev_prev_pst = prev_pst = current pst estimate`
  * `prev_layer = L1`

---

## Compatibility notes

This specification is intentionally minimal.
It is designed to fit current `lptm_e2e_minimal.py` structure without requiring full protocol-engine integration.

Future compatible extensions may include:

* `confidence`
* `human_review`
* `risk_gate_triggered`
* `uncertainty_budget`
* `cob_score`
* `rnc_blocked`

---

## Suggested next endpoints

### `POST /v1/mdp-simulate`

Future multi-step transition simulation using PST dynamics as state history.

### `POST /v1/phase-transition`

Safe-path exploration across candidate interventions.

### `POST /v1/calibrate`

Re-weighting and calibration based on accumulated cycle logs.

---

## Summary

This API spec defines the minimal operational interface for a motion-aware LPTM evaluator.

It upgrades phase interpretation from:

* threshold-only evaluation

to:

* dynamic transition-sensitive evaluation
* hysteresis-aware layer control
* reduced COB chattering
