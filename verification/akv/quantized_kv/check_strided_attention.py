"""Full-cost strided-cache ABBA gate; numerical/work checks stay independent."""
import re

from check_attention import ORDER, check_log as check_attention
from check_batch_qk import TERMINAL
from check_rvv_qbs import require


def capability(kind):
    row = 72 if kind else 136
    return ('QUANT_STRIDED_CAP map_timed=1 admission_timed=1 gather_timed=1 '
            f'workspace=13120 k_token_stride={2 * row} v_token_stride=272')


def entry(kind, trial):
    row = 72 if kind else 136
    return (f'QUANT_STRIDED_ENTRY trial={trial} map=0 status=0 selection=0 groups=1 '
            f'commands=8 values=128 panels=4 copied={128 * row}')


def check_log(text, kind, golden, rtl):
    require(kind in (0, 1), 'Unsupported strided profile')
    cap = terminal = False
    active = None
    finished, entries = [], []
    for line in text.splitlines():
        if line == TERMINAL:
            terminal = True
        if 'QUANT_STRIDED_' in line:
            require(not terminal, 'Strided record after termination')
            if line == capability(kind):
                require(not cap and active is None and not finished, 'Duplicate/late strided capability')
                cap = True
            elif active in (1, 2) and line == entry(kind, active):
                require(cap and active not in entries, 'Unexpected/duplicate strided entry')
                entries.append(active)
            else:
                raise ValueError('Malformed/unknown strided evidence')
        if 'QUANT_COMMON_' in line:
            raise ValueError('Contiguous-only evidence cannot substitute for strided execution')
        if line.startswith('QUANT_ATTN_CAP '):
            require(cap, 'Missing strided capability declaration')
        if line.startswith('QUANT_ATTN_BEGIN '):
            trial = len(finished)
            require(cap and active is None and trial < 4 and line ==
                    f'QUANT_ATTN_BEGIN trial={trial} shared={ORDER[trial]}', 'Wrong ABBA order')
            active = trial
        elif line.startswith('QUANT_ATTN_RESULT '):
            require(active is not None and ((active in entries) == bool(ORDER[active])),
                    'Missing candidate entry or native work attributed to baseline')
            finished.append(active)
            active = None
    require(cap and terminal and finished == [0, 1, 2, 3] and entries == [1, 2],
            'Incomplete strided-cache inquiry')
    result = check_attention(text, kind, golden, rtl)
    require(len({trial['fcsr'] for trial in result['trials']}) == 1,
            'Shared and ordinary FCSR differ')
    result.update(state='STRIDED_ATTENTION_NUMERICAL_AND_WORK_CHECKED', mapping_timed=True,
                  admission_timed=True, gather_timed=True, workspace_bytes=13120,
                  key_token_stride=144 if kind else 272, value_token_stride=272,
                  gathered_key_panels=8, copied_key_bytes=256 * (72 if kind else 136),
                  public_entry_trials=entries, same_rvv_value_decoder=True,
                  hardware_only=False, software_schedule_changed=True, whole_model=False,
                  backend_memory_extent_timed=False, graph_dispatch_timed=False,
                  scope='One real six-Query-head KV-head-0 group in a two-KV-head physical cache; '
                        'candidate includes mapping, admission and bounded K gathering; not model execution')
    return result
