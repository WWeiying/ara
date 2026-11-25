# Resident low-overhead SDK candidate

This successor uses the direct lease environment and the same captured Qwen3 inputs.
Both arms query hardware once per lease, like the cached llama.cpp device helper;
INFO calls inside each measured SDK call must be zero. Query conversion, plan
validation, QK, Softmax, PV and output normalization remain timed. The Resident
arm uses the stackless PV leaf; the native arm keeps its original policy.

Built from pinned SDK 4a7361f51ba5447a616217dad1c8e72e3ee2b45b plus exactly the
six source overlays enumerated in result.json and hashed in source-pins.json.
It does not consume uncommitted akv_v2_attention_rvv.S. This is not the unmodified
pinned SDK and is not whole-model evidence. No numerical or speedup acceptance
is claimed until the board checker passes. It requires the new gate bitstream
and the matching v4 test kernel described in direct/BOARD_HANDOFF.md.

Use the existing run_environment.sh with a separately packaged successor bundle,
not the old delivery archive. Stop on any safety, route, output or flag mismatch.


V2 additionally consumes already-validated QK/PV controls without rebuilding
in each leaf and derives the tail from the admitted full tile. Six source
overlays are inventoried; v1 remains a separate immutable candidate.

