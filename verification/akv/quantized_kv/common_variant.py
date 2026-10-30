"""Classify decoder metadata only; this does not validate pins or execution."""

ORIGINAL_DECODERS = "ORIGINAL_DECODERS"
CANDIDATE_RVV_DECODE = "CANDIDATE_RVV_DECODE"
BOTH_RVV_DECODE = "BOTH_RVV_DECODE"

# Exact scope strings emitted by the three sealed attention builders.
_BUILD_SCOPES = {
    ORIGINAL_DECODERS: "Original six-head KV-head-0 group; public GGML mapping/runtime candidate, not model execution",
    CANDIDATE_RVV_DECODE: "Same public-entry ABBA Attention; only candidate V decode uses RVV",
    BOTH_RVV_DECODE: "Public-entry ABBA; both schedules use identical RVV V decoder",
}
_SCALAR_LABEL = "unchanged production scalar decoder"
_RVV_LABEL = "same RVV decoder as candidate"


def classify(report):
    """Return fresh JSON-safe annotations, or raise ValueError on ambiguity.

    Missing flags mean False, but every present flag must have exact bool type.
    The original build must omit ordinary_value_decode entirely. RVV builds
    must carry their exact builder label. Optional scope/variant labels must
    agree; unrelated build/provenance fields are neither validated nor copied.
    No execution, numerical acceptance, or performance benefit is inferred.
    """
    if not isinstance(report, dict):
        raise ValueError("report must be a JSON object")
    for key in ("rvv_value_decode", "rvv_baseline_decode"):
        if key in report and type(report[key]) is not bool:
            raise ValueError(key + " must be an exact bool when present")
    candidate_rvv = report.get("rvv_value_decode", False)
    ordinary_rvv = report.get("rvv_baseline_decode", False)
    if ordinary_rvv and not candidate_rvv:
        raise ValueError("RVV baseline requires RVV candidate")

    if not candidate_rvv:
        if "ordinary_value_decode" in report:
            raise ValueError("Original decoder metadata must omit ordinary_value_decode")
        variant = ORIGINAL_DECODERS
    else:
        variant = BOTH_RVV_DECODE if ordinary_rvv else CANDIDATE_RVV_DECODE
        expected = _RVV_LABEL if ordinary_rvv else _SCALAR_LABEL
        if type(report.get("ordinary_value_decode")) is not str or report["ordinary_value_decode"] != expected:
            raise ValueError("ordinary_value_decode disagrees with decoder flags")

    for key, expected in (("scope", _BUILD_SCOPES[variant]), ("variant", variant)):
        if key in report and (type(report[key]) is not str or report[key] != expected):
            raise ValueError(key + " disagrees with decoder configuration")

    matched = candidate_rvv == ordinary_rvv
    attribution = {
        ORIGINAL_DECODERS: "QBS plus sharing with production scalar decode on both sides",
        CANDIDATE_RVV_DECODE: "Combined decoder vectorization plus QBS and sharing",
        BOTH_RVV_DECODE: "QBS plus sharing after equal RVV software decode",
    }[variant]
    return {
        "variant": variant,
        "ordinary_value_decode": "RVV decoder" if ordinary_rvv else "production scalar decoder",
        "candidate_value_decode": "RVV decoder" if candidate_rvv else "production scalar decoder",
        "decoder_implementation_matched": matched,
        "fairness": (
            "Matched decoder implementation; decode counts and schedules may differ"
            if matched else "Decoder mismatch; cannot isolate QBS/sharing from decoder vectorization"
        ),
        "attribution": attribution,
        "scope": "Captured six-head KV-head-0 public-entry comparison, not model execution",
        "hardware_only_claim_supported": False,
        "model_speedup_claim_supported": False,
    }
