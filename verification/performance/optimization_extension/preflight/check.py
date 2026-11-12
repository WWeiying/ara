"""Strict benchmark parsing; Spike counters are functional, never performance."""
import re
import statistics


def require(ok, why):
    if not ok:
        raise ValueError(why)


FIELDS = ('k trial candidate cycles instructions bytes fcsr vcsr queries hits producers '
          'misses stores rejected conflicts allocation_failures evictions comparison_bytes_requested '
          'copied_payload_bytes vstart guard_bytes payload_equal payload_hash errors').split()
DONE = 'EXT_PREFLIGHT_DONE shapes=2 trials=8 calls=24 errors=0'


def successful(text):
    require(text.count('Core Test *** SUCCESS ***') == 1, 'Missing/duplicate successful EOC')
    require(not re.search(r'(?im)(^\s*(?:Fatal:|Fatal-|Error:|Error-)|\$fatal|Assertion failed|'
                          r'\bFAILED\b|\bTIMEOUT\b)', text), 'EOC/assertion failure')
    for line in text.splitlines():
        if re.search(r'\bUVM_(ERROR|FATAL)\b', line):
            require(re.fullmatch(r'\s*UVM_(ERROR|FATAL)\s*:\s*0\s*', line), 'UVM failure')
    for kind in ('ERROR', 'FATAL'):
        require(len(re.findall(r'^\s*UVM_'+kind+r'\s*:\s*0\s*$', text, re.M)) == 1,
                'Missing/duplicate UVM severity summary')


def numerical(text, *, vcs=False, reference=None):
    if vcs:
        successful(text)
    require('EXT_PREFLIGHT_FAIL' not in text and not re.search(r'\bTRAP\b', text), 'Target failure')
    lines = []
    for line in text.splitlines():
        if 'EXT_PREFLIGHT_' in line:
            require(line.startswith('EXT_PREFLIGHT_'), 'Malformed benchmark prefix')
            lines.append(line)
    require(len(lines) == 9 and lines[-1] == DONE, 'Missing/extra/truncated benchmark records')
    trials = []
    for index, line in enumerate(lines[:-1]):
        pattern = 'EXT_PREFLIGHT_TRIAL' + ''.join(' '+key+r'=(\d+)' for key in FIELDS)
        match = re.fullmatch(pattern, line)
        require(match is not None, 'Malformed/duplicate/unknown trial fields')
        row = dict(zip(FIELDS, map(int, match.groups())))
        k = 2048 if index < 4 else 4096
        b = k // 256 * 1168
        expected = dict(k=k, trial=index % 4, candidate=int(index % 4 in (1, 2)), bytes=b,
                        fcsr=17, vcsr=5, queries=3, hits=2, producers=1, misses=1, stores=1,
                        rejected=0, conflicts=0, allocation_failures=0, evictions=0,
                        comparison_bytes_requested=2*k*16, copied_payload_bytes=k*16+3*b,
                        vstart=0, guard_bytes=128, payload_equal=1, errors=0)
        require(all(row[key] == value for key, value in expected.items()), 'Trial contract mismatch')
        require(0 < row['cycles'] < 2**63 and 0 < row['instructions'] < 2**63 and
                0 < row['payload_hash'] < 2**64, 'Invalid counters/digest')
        trials.append(row)
    for start in (0, 4):
        require(len({r['payload_hash'] for r in trials[start:start+4]}) == 1, 'Payload disagreement')
    functional = [{key: value for key, value in r.items() if key not in ('cycles', 'instructions')}
                  for r in trials]
    if reference is not None:
        require(functional == reference['functional'], 'VCS/Spike functional evidence differs')
    metrics = []
    if vcs:
        for start in (0, 4):
            a, b, c, d = trials[start:start+4]
            baseline = statistics.mean((a['cycles'], d['cycles']))
            candidate = statistics.mean((b['cycles'], c['cycles']))
            metrics.append(dict(k=a['k'], baseline_cycles=[a['cycles'], d['cycles']],
                                candidate_cycles=[b['cycles'], c['cycles']], baseline_mean=baseline,
                                candidate_mean=candidate, baseline_over_candidate=baseline/candidate,
                                cycle_reduction_fraction=1-candidate/baseline))
    return dict(state='PASS', trials=trials, functional=functional, performance_measured=vcs,
                cycle_metrics=metrics, full_model_claim=False,
                scope='K2048 first four real Qwen3 attn_norm rows; K4096 same 8x2048 bytes '
                      'reshaped to 4x4096, NOT a real K4096 operator')


def protocol(proof, identities):
    require(proof.get('status') == 'PASS' and proof.get('issues') == [], 'Independent protocol failed')
    require(all(proof.get(key) == value for key, value in identities.items()), 'Protocol identity differs')
    counts = proof['contract_counts']
    require(all(counts[key] == 0 for key in ('exceptions', 'protocol_errors', 'outstanding')),
            'Protocol not drained')
    require(counts['requests'] > 0 and counts['requests'] == counts['responses'], 'Empty/unbalanced protocol')
