"""Compare independently checked six-call runs, never historical timing."""

ORDER = (0, 1, 2, 2, 1, 0)
MATCHED = ('trial', 'mode', 'output_bits', 'fcsr', 'vcsr', 'calls', 'dots',
           'commands', 'values', 'panels', 'copied', 'quantizations')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(report):
    require(report['state'] == 'THREEWAY_NUMERICAL_AND_WORK_CHECKED' and
            report['original_golden_checked'] is True, 'Run not original-golden checked')
    trials = report['trials']
    require(len(trials) == 6 and len(report['hardware_records']) == 16 and
            tuple(t['mode'] for t in trials) == ORDER and
            [t['trial'] for t in trials] == list(range(6)), 'Need six actual mirrored calls per executable')
    for t in trials:
        require(type(t['cycles']) is int and 0 < t['cycles'] < 2**64 and
                len(t['output_bits']) == 768 and type(t['fcsr']) is int and 0 <= t['fcsr'] <= 31 and
                type(t['vcsr']) is int and t['vcsr'] == 5, 'Wrong cycles/outputs/CSR extent')
    for first, last in ((0, 5), (1, 4), (2, 3)):
        require(all(trials[first][k] == trials[last][k] for k in ('output_bits', 'fcsr', 'vcsr')),
                'Same-executable repetition differs')
    sums = {str(mode): sum(t['cycles'] for t in trials if t['mode'] == mode) for mode in range(3)}
    require(report['sums'] == sums, 'Raw checker cycle sums differ')
    return sums


def compare(baseline, candidate):
    old, new = validate(baseline), validate(candidate)
    pairs = []
    for a, b in zip(baseline['trials'], candidate['trials']):
        require(all(a[k] == b[k] for k in MATCHED), 'Cross-executable output/CSR/work differs')
        pairs.append(dict(trial=a['trial'], mode=a['mode'], baseline_cycles=a['cycles'],
                          candidate_cycles=b['cycles'], cycle_delta=b['cycles']-a['cycles'],
                          baseline_over_candidate=a['cycles']/b['cycles'],
                          regressed=b['cycles'] > a['cycles']))
    modes = {str(mode): dict(baseline_cycles=old[str(mode)], candidate_cycles=new[str(mode)],
        cycle_delta=new[str(mode)]-old[str(mode)], baseline_over_candidate=old[str(mode)]/new[str(mode)],
        regressed=new[str(mode)] > old[str(mode)],
        baseline_repeat_cycles=[t['cycles'] for t in baseline['trials'] if t['mode'] == mode],
        candidate_repeat_cycles=[t['cycles'] for t in candidate['trials'] if t['mode'] == mode])
        for mode in range(3)}
    return dict(state='FRESH_SIX_CALL_PAIR_NUMERIC_CSR_WORK_MATCHED', trials=pairs, modes=modes,
                baseline_total_cycles=sum(old.values()), candidate_total_cycles=sum(new.values()),
                regressed_modes=[int(k) for k, v in modes.items() if v['regressed']],
                output_words_per_binary=4608, cross_binary_word_comparisons=4608,
                total_output_values_read=9216, historical_timing_used=False,
                same_image_required=True, same_elf=False, performance_acceptance=False,
                independent_parent_review_required=True, whole_model=False)
