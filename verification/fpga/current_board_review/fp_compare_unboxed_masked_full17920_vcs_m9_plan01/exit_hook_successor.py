"""Actual local hook: shared successor collector subprocess and numeric receipt."""
from shared import module
from scope import HERE
_m=module('masked17920_actual_exit_hook','exit_hook_successor.py',
    constants=[('PASS_FULL17920_FP32_M9_METADATA_COLLECTED_NOT_LINUX',
                'PASS_FULL17920_MASKED_FP16_M9_METADATA_COLLECTED_NOT_LINUX',1)],
    local_file=HERE/'exit_hook_successor.py')
if __name__=='__main__':raise SystemExit(_m.main())
