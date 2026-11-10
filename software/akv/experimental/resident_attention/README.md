# Experimental Resident Attention Helpers

This is a stage-3 candidate, not a default runtime path or a board delivery.
The capability remains zero until composed RTL and complete-call acceptance.

`qk.S` issues one resident QK command, then stores only the active FP32 scores.
The helper uses the same 256-byte head stride as the existing Attention
workspace and supports one or two heads. The command reads Q and K from the
already-loaded context; it does not reload a query pointer from memory.

| Argument | Meaning |
|---|---|
| `scores` | Writable FP32 output, with 64 elements reserved per head |
| `tokens` | Active tokens in the current tile, 1 through 64 |
| `heads` | One or two consecutive query rows |
| `dimensions` | Head dimension 64, 96 or 128 |
| `query_base` | First resident Q row, with `query_base + heads <= loaded_queries` |

The caller must own a valid resident context with matching D and sufficient T,
check the hardware capability/configuration, and satisfy the FP-state, rounding
mode and vstart requirements before issuing the command. `qk.h` checks argument
geometry only; it does not establish ownership, check pointer capacity or
advertise device support. Do not route unsupported calls here.

Each output is a positive-zero FP32 accumulator followed by dimension-ordered
FP32 FMAs on exactly widened F16 inputs. The helper does not apply attention
scaling, masks, softmax or output normalization. Those remain in the caller.
Vector registers v0 through v3 and caller-saved integer temporaries are
clobbered. The command preserves architectural VL/VTYPE; the subsequent normal
RVV stores configure VL/VTYPE as needed, as existing software helpers do.

`verification/performance/resident_rvv/qk_shared/test_sdk_helper.py` checks host
geometry and the real GNU-assembled opcode/store fields. It is not a substitute
for executing this helper on the candidate RTL.
