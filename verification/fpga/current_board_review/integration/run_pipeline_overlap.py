#!/usr/bin/env python3
"""Pinned successor: original overlap and mask RAW repros precede regressions."""
from pathlib import Path
import run_pipeline_comparison as previous

pipeline = previous.pipeline
pipeline.RTL = {
    'hardware/src/ara.sv': '1d190744249603d6c3d6e2c9c21cd5ac121fee2a9c65f5b227be239c320286da',
    'hardware/src/ara_dispatcher.sv': '8ea44e035165be966bc80cea3abc31a8af85fde3e46470116854480a92171ab2',
    'hardware/src/ara_sequencer.sv': 'f1d6095e1ade018b9225678a493438da04e7d84f68a956bdf7a116941bfafc5b',
    'hardware/src/lane/lane_sequencer.sv': '60137df7264ccd09b2a9a1548d2e522c4785bd43c26a06a27024a0c8eb114da0',
    'hardware/src/lane/vmfpu.sv': 'e9b8c8c2aa952b76661b01fa0a4b53d87e2f1d7219beb40a42a4d6998c5f7b12',
    'hardware/src/masku/masku.sv': '1bc71bbb732a842d59fdcc48d4f44aa79f830f2bb11444923b15910b8d875f3d',
    'hardware/src/masku/masku_operands.sv': 'c907488c75b5051a917e61c5ac08bca15859f2f0506fd61dae07dd576569456f',
    'hardware/src/sldu/sldu.sv': '1908da4368316c0979e388e934cf04dacf2d266297b36d35b1a803222d2a311e',
}
REVIEW = Path(__file__).resolve().parent.parent
previous.EXTRA += (
    ('extension-original', REVIEW / 'extension_overlap/measurement01/build/soc',
     ('extension_overlap_vl127',)),
    ('large-offset', REVIEW / 'large_offset_slide/prepared01/soc',
     ('e8_m8_single', 'e8_m4_single', 'e8_m4_sequence', 'e8_m8_sequence',
      'e16_m8_single', 'e16_m8_sequence')),
    ('extension-matrix', REVIEW / 'extension_overlap/matrix01/soc',
     ('extension_e16_m2_vf2', 'extension_e32_m2_vf2', 'extension_e64_m2_vf2',
      'extension_e32_m4_vf4', 'extension_e64_m4_vf4', 'extension_e64_m8_vf8')),
)
ORDER = ('build-image', 'extension-original', 'large-offset', 'singles', 'combined',
         'extended', 'gather', 'smokes', 'comparison', 'flags-sequence',
         'reduction-epoch', 'comparison-matrix', 'extension-matrix')


def inputs(args):
    pins = previous.inputs(args)
    pipeline.pin(pins, Path(__file__).resolve())
    return pins


def stages(args):
    result = previous.stages(args)
    if sorted(stage['name'] for stage in result) != sorted(ORDER):
        raise ValueError('Unexpected stage set')
    return sorted(result, key=lambda stage: ORDER.index(stage['name']))


pipeline.inputs = inputs
pipeline.stages = stages

if __name__ == '__main__':
    raise SystemExit(pipeline.main())
