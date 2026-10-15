#!/usr/bin/env python3
"""Combined masked-translation and fault-drain candidate, with pinned controls."""
from pathlib import Path
import run_pipeline as pipeline

HERE = Path(__file__).resolve().parent
REVIEW = HERE.parent
pipeline.RTL = {
    'hardware/src/vlsu/addrgen.sv': '470c6c92d26cd2e540562302788f58d8d85ae6f147886fb949668e7728be41da',
    'hardware/src/vlsu/vldu.sv': '4e46a4733530b15edb05bbaded651899511af930e2caffe77b7482528c4fc8ab',
    'hardware/src/ara_sequencer.sv': 'bf5d5a9be860340ca7a6f8d8c636da67cf9650f7b7b72d1123ce983e8eea5655',
}
pipeline.STAGES = (
    ('sv39', ('alloff_fault', 'active_fault_retry', 'alloff_valid')),
    pipeline.STAGES[-1],
)
base_inputs = pipeline.inputs


def inputs(args):
    pins = base_inputs(args)
    pipeline.pin(pins, Path(__file__).resolve())
    consumers = REVIEW / 'masked_translation/consumers'
    summary = consumers / 'ab_summary07.json'
    pipeline.pin(pins, summary)
    if pipeline.read(summary)['status'] != 'PASS_6_EXCEPTION_4_ARRIVAL':
        raise ValueError('VLDU local acceptance missing')
    seq = consumers / 'sequencer_final12/status.json'
    pipeline.pin(pins, seq)
    result = pipeline.read(seq)
    cases = result['cases']
    expected = {0: 9, 1: 21, 2: 21, 3: 25, 4: 15, 5: 9, 6: 9}
    if (result['state'] != 'PROBES_COMPLETE' or len(cases) != len(expected) or
            {c['observation']['case'] for c in cases} != set(expected)):
        raise ValueError('Sequencer probes incomplete')
    seq_pins = seq.parent / 'pins.json'
    pipeline.pin(pins, seq_pins)
    if pipeline.read(seq_pins)['files']['hardware/src/ara_sequencer.sv'] != \
            pipeline.RTL['hardware/src/ara_sequencer.sv']:
        raise ValueError('Sequencer probe used a different candidate')
    for case in cases:
        obs = case['observation']
        if (case['returncode'] != 0 or not case['probe_completed'] or
                obs['response'] != expected[obs['case']] or
                obs['early_fault_response'] or not obs['idle']):
            raise ValueError('Sequencer fault barrier acceptance missing')
    return pins


pipeline.inputs = inputs

if __name__ == '__main__':
    raise SystemExit(pipeline.main())
