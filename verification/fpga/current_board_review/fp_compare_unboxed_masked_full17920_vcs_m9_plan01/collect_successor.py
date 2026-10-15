"""Reuse mature metadata collector, only exact masked counts/status differ."""
from shared import module
from scope import HERE
_m=module('masked17920_terminal_collector','collect_successor.py',
    expressions=[('[17920,286720,35840,17920,17920,326144,3,878080,286720,17920,2240,10752]',
                  '[17920,286720,35840,17920,17920,326144,3,734720,143360,17920,8960,10752]',1)],
    constants=[('PASS_FULL17920_FP32_M9_METADATA_COLLECTED_NOT_LINUX',
                'PASS_FULL17920_MASKED_FP16_M9_METADATA_COLLECTED_NOT_LINUX',2)],
    local_file=HERE/'collect_successor.py')
if __name__=='__main__':raise SystemExit(_m.main())
