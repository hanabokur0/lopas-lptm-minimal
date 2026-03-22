from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from common_schema_models import (
    Domain,
    EngineName,
    FieldVoice,
    LoPASObservation,
)
from feature_extraction_v01 import build_observation_from_field_voices


# ============================================================
# LPTM minimal input / output
# ============================================================

@dataclass
class LPTMInput:
    dDoQ: float
    SCI: float
    CDI: float
    TRS: float
    field_heat: float
    field_quality: float
    shock: str
    strength: float
    time_lag: float


@dataclass
class PSTSnapshot:
    pst: float
    delta_pst: float = 0.0
    delta2_pst: float = 0.0


class LPTMLayer(str, Enum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


@dataclass
class LPTMOutput:
    PST: float
    delta_PST: float
    delta2_PST: float
    layer: str
    band: str
    confidence: float
    notes: str


# ============================================================
# Utility
# ============================================================


def clamp(value: float, min_value: float = 0.0, max_value: float = 1.0) -> float:
    return max(min_value, min(max_value, value))


def get_indicator_value(obs: LoPASObservation, key: str, default: float = 0.0) -> float:
    indicator = obs.indicators.get(key)
    if indicator is None:
        return default
    return float(indicator.value)


def summarize_shock(obs: LoPASObservation, max_items: int = 3) -> str:
    """
    Build a minimal shock summary from high-priority field voices.
    """
    voices = obs.payload.field_voices
    if not voices:
        return "no_field_voice"

    ranked = sorted(
        voices,
        key=lambda v: {"high": 3, "medium": 2, "low": 1}.get(v.priority, 1),
        reverse=True,
    )

    picked = []
    for voice in ranked[:max_items]:
        text = voice.content.strip().replace("\n", " ")
        if len(text) > 48:
            text = text[:48] + "..."
        picked.append(text)

    return " | ".join(picked)


def estimate_cdi_from_observation(obs: LoPASObservation) -> float:
    """
    Minimal CDI proxy.
    For v0.1, use imbalance / concentration proxy from:
    - field_heat
    - SCI
    - source concentration
    - location concentration

    Higher concentration + higher stress -> higher CDI.
    """
    voices = obs.payload.field_voices
    if not voices:
        return 0.0

    field_heat = get_indicator_value(obs, "field_heat", 0.0)
    sci = get_indicator_value(obs, "SCI", 0.0)

    source_counts: dict[str, int] = {}
    location_counts: dict[str, int] = {}

    for v in voices:
        if v.source_account:
            source_counts[v.source_account] = source_counts.get(v.source_account, 0) + 1
        if v.location:
            location_counts[v.location] = location_counts.get(v.location, 0) + 1

    n = len(voices)

    def hhi(counts: dict[str, int]) -> float:
        if not counts or n == 0:
            return 0.0
        return sum((c / n) ** 2 for c in counts.values())

    source_hhi = hhi(source_counts)
    location_hhi = hhi(location_counts)

    # Simple weighted proxy
    cdi = (
        0.35 * field_heat
        + 0.35 * sci
        + 0.15 * source_hhi
        + 0.15 * location_hhi
    )
    return clamp(cdi)


def estimate_strength(obs: LoPASObservation) -> float:
    """
    LPTM shock strength proxy.
    """
    ddoq = get_indicator_value(obs, "dDoQ", 0.0)
    sci = get_indicator_value(obs, "SCI", 0.0)
    field_heat = get_indicator_value(obs, "field_heat", 0.0)

    strength = 0.40 * sci + 0.35 * field_heat + 0.25 * ddoq
    return clamp(strength)


def estimate_time_lag(obs: LoPASObservation) -> float:
    """
    Minimal time_lag proxy:
    how temporally complete the voices are.
    """
    voices = obs.payload.field_voices
    if not voices:
        return 0.0

    with_timestamp = sum(1 for v in voices if v.observed_at is not None)
    return clamp(with_timestamp / len(voices))


# ============================================================
# Mapping: LoPASObservation -> LPTMInput
# ============================================================


def lopas_observation_to_lptm_input(obs: LoPASObservation) -> LPTMInput:
    """
    Convert Common Schema observation to LPTM input.

    Notes:
    - dDoQ, SCI, TRS, field_heat, field_quality are taken directly from indicators
    - CDI is estimated here as a v0.1 proxy
    - shock is summarized from field voices
    - strength / time_lag are proxy-generated here
    """
    ddoq = get_indicator_value(obs, "dDoQ", 0.0)
    sci = get_indicator_value(obs, "SCI", 0.0)
    trs = get_indicator_value(obs, "TRS", 0.0)
    field_heat = get_indicator_value(obs, "field_heat", 0.0)
    field_quality = get_indicator_value(obs, "field_quality", 0.0)

    cdi = estimate_cdi_from_observation(obs)
    shock = summarize_shock(obs)
    strength = estimate_strength(obs)
    time_lag = estimate_time_lag(obs)

    return LPTMInput(
        dDoQ=round(ddoq, 4),
        SCI=round(sci, 4),
        CDI=round(cdi, 4),
        TRS=round(trs, 4),
        field_heat=round(field_heat, 4),
        field_quality=round(field_quality, 4),
        shock=shock,
        strength=round(strength, 4),
        time_lag=round(time_lag, 4),
    )


# ============================================================
# Minimal mock LPTM with delta2_PST + HI2
# ============================================================


def compute_base_pst(lptm_input: LPTMInput) -> float:
    """
    Base PST score from the current observation only.
    """
    return clamp(
        0.22 * lptm_input.dDoQ
        + 0.20 * lptm_input.SCI
        + 0.14 * lptm_input.CDI
        + 0.12 * lptm_input.TRS
        + 0.10 * lptm_input.field_heat
        + 0.08 * lptm_input.field_quality
        + 0.06 * lptm_input.time_lag
        + 0.08 * lptm_input.strength
    )


def compute_pst_dynamics(prev_prev_pst: float, prev_pst: float, curr_pst: float) -> PSTSnapshot:
    delta_prev = prev_pst - prev_prev_pst
    delta_curr = curr_pst - prev_pst
    delta2 = delta_curr - delta_prev

    return PSTSnapshot(
        pst=curr_pst,
        delta_pst=delta_curr,
        delta2_pst=delta2,
    )


def classify_transition(snapshot: PSTSnapshot) -> str:
    pst = snapshot.pst
    d1 = snapshot.delta_pst
    d2 = snapshot.delta2_pst

    # Breakout: genuinely rising into a higher phase.
    if pst >= 0.82 and d1 > 0.03:
        return "breakout"

    # Phase rising: past the main L1/L2 boundary with non-negative acceleration.
    if pst >= 0.65 and d1 > 0.01 and d2 >= 0.0:
        return "phase_rising"

    # COB: critical oscillation band around the unstable boundary.
    if 0.58 <= pst <= 0.72 and abs(d1) < 0.01 and abs(d2) < 0.01:
        return "cob_oscillation"

    # False peak: looks elevated but is already losing momentum.
    if pst >= 0.65 and d1 < 0.0 and d2 < 0.0:
        return "false_peak"

    return "stable_or_noise"


def apply_hysteresis(snapshot: PSTSnapshot, prev_layer: LPTMLayer) -> LPTMLayer:
    """
    HI2-style hysteresis.

    Prevents chattering near the L1/L2 and L2/L3 boundaries by making
    layer changes depend on both trajectory and previous layer.
    """
    pst = snapshot.pst
    transition = classify_transition(snapshot)

    if prev_layer == LPTMLayer.L1:
        if transition in ("phase_rising", "breakout"):
            return LPTMLayer.L2
        return LPTMLayer.L1

    if prev_layer == LPTMLayer.L2:
        if transition == "breakout":
            return LPTMLayer.L3
        if pst < 0.58 and transition == "stable_or_noise":
            return LPTMLayer.L1
        return LPTMLayer.L2

    if prev_layer == LPTMLayer.L3:
        if pst < 0.76 and snapshot.delta_pst < 0.0:
            return LPTMLayer.L2
        return LPTMLayer.L3

    return prev_layer


def band_from_snapshot(snapshot: PSTSnapshot, layer: LPTMLayer) -> str:
    transition = classify_transition(snapshot)

    if layer == LPTMLayer.L3:
        return "Breakout" if transition == "breakout" else "Transition"
    if layer == LPTMLayer.L2:
        if transition == "cob_oscillation":
            return "COB"
        if transition == "false_peak":
            return "FalsePeak"
        return "Escalating"
    return "Stable"


def run_lptm_minimal(
    lptm_input: LPTMInput,
    prev_pst: float | None = None,
    prev_prev_pst: float | None = None,
    prev_layer: str | None = None,
) -> LPTMOutput:
    """
    Minimal LPTM stub for connection experiments.

    This version upgrades the original stub with:
    - delta_PST
    - delta2_PST
    - HI2-style hysteresis layer handling

    It is still a compact mock, but it now behaves more like a motion-sensitive
    phase classifier than a single-frame threshold switch.
    """
    curr_pst = compute_base_pst(lptm_input)

    if prev_pst is None:
        prev_pst = curr_pst
    if prev_prev_pst is None:
        prev_prev_pst = prev_pst

    if prev_layer is None:
        inferred_prev_layer = LPTMLayer.L1
    else:
        try:
            inferred_prev_layer = LPTMLayer(prev_layer)
        except ValueError:
            inferred_prev_layer = LPTMLayer.L1

    snapshot = compute_pst_dynamics(prev_prev_pst, prev_pst, curr_pst)
    layer = apply_hysteresis(snapshot, inferred_prev_layer)
    band = band_from_snapshot(snapshot, layer)

    confidence = clamp(
        0.55 * lptm_input.field_quality
        + 0.25 * lptm_input.time_lag
        + 0.20 * (1.0 if len(lptm_input.shock) > 0 else 0.0)
    )

    notes = (
        "Minimal LPTM stub run with delta2_PST + HI2. "
        f"shock_strength={lptm_input.strength:.3f}, "
        f"time_lag={lptm_input.time_lag:.3f}, "
        f"transition={classify_transition(snapshot)}"
    )

    return LPTMOutput(
        PST=round(snapshot.pst, 4),
        delta_PST=round(snapshot.delta_pst, 4),
        delta2_PST=round(snapshot.delta2_pst, 4),
        layer=layer.value,
        band=band,
        confidence=round(confidence, 4),
        notes=notes,
    )


# ============================================================
# Human review threshold
# ============================================================


def decide_human_review(obs: LoPASObservation, lptm_output: LPTMOutput) -> dict[str, Any]:
    """
    First threshold policy for experiment.
    """
    obs_conf = obs.meta.confidence
    sci = get_indicator_value(obs, "SCI", 0.0)
    ddoq = get_indicator_value(obs, "dDoQ", 0.0)

    reasons: list[str] = []

    if obs_conf < 0.75:
        reasons.append("low_feature_confidence")
    if sci > 0.80:
        reasons.append("high_sci_proxy")
    if ddoq > 0.70 and obs_conf < 0.85:
        reasons.append("high_ddoq_with_nonhigh_confidence")
    if lptm_output.layer == "L3" and lptm_output.confidence < 0.80:
        reasons.append("high_impact_lptm_low_confidence")

    return {
        "human_review_required": len(reasons) > 0,
        "reasons": reasons,
    }


# ============================================================
# End-to-end experiment
# ============================================================


def run_end_to_end_case() -> None:
    """
    Minimal connection experiment:
    FieldVoice -> Feature Extraction -> Common Schema -> LPTM Input -> LPTM -> Review decision
    """
    field_voices = [
        FieldVoice(
            priority="high",
            content="パフラヴィー皇太子、政権崩壊後の移行について安定したプロセスを構築すると発言。",
            source_account="@PahlaviComms",
            location="Tehran",
            observed_at=datetime(2026, 3, 3, 4, 17, tzinfo=timezone.utc),
            language="ja",
        ),
        FieldVoice(
            priority="medium",
            content="BBC Farsiが誤訳したとの批判。制度的責任と分析が必要だ。",
            source_account="@AkhoondeMorde",
            location="Tehran",
            observed_at=datetime(2026, 3, 3, 5, 57, tzinfo=timezone.utc),
            language="ja",
        ),
        FieldVoice(
            priority="high",
            content="後継危機と混乱が拡大し、崩壊リスクが高まっている。攻撃後の空白が続く。",
            source_account="@ConflictWatch",
            location="Qom",
            observed_at=datetime(2026, 3, 4, 6, 30, tzinfo=timezone.utc),
            language="ja",
        ),
    ]

    observation = build_observation_from_field_voices(
        field_voices,
        summary="Iran transition-related field voices",
        domain=Domain.geopolitics,
        requested_engines=[EngineName.LPTM],
    )

    lptm_input = lopas_observation_to_lptm_input(observation)

    # Minimal demo history so delta / delta2 can be observed.
    curr_pst = compute_base_pst(lptm_input)
    prev_prev_pst = max(0.0, curr_pst - 0.05)
    prev_pst = max(0.0, curr_pst - 0.02)
    prev_layer = LPTMLayer.L1.value

    lptm_output = run_lptm_minimal(
        lptm_input,
        prev_pst=prev_pst,
        prev_prev_pst=prev_prev_pst,
        prev_layer=prev_layer,
    )
    review = decide_human_review(observation, lptm_output)

    print("\n=== 1) Common Schema Observation ===")
    print(observation.model_dump_json(indent=2, exclude_none=True))

    print("\n=== 2) LPTM Input ===")
    print(asdict(lptm_input))

    print("\n=== 3) LPTM Output ===")
    print(asdict(lptm_output))

    print("\n=== 4) Review Decision ===")
    print(review)


if __name__ == "__main__":
    run_end_to_end_case()
