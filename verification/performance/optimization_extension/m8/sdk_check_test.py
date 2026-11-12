import copy
import unittest
import sdk_check as c


def fixture():
    build = dict(trials=[4, 8, 8, 4], flag_seeds=[0, 8, 0, 8], m=8, k=2048, n=32, commands=8,
        outputs_per_trial=256, activation_payload_bytes=18688, q8_equal_before_oracle=True,
        cache=False, context_replay=False, build_id='frozen', prep_flags=1, engine_flags=1)
    lines = []
    for trial, mode in enumerate(c.MODES):
        tn = 16 if mode == 8 else 32
        for part in range(2):
            p = dict(seq=trial*2+part+1, success=1, fault=0, validation_fault=0, read_fault=0,
                validation_error=0, busy_cycles=10, m=mode, n=tn, vlen=1024, lanes=4, weight_bytes=tn*8*144,
                activation_bytes=mode*8*292, useful_pairs=mode*tn*2048, pair_capacity=mode*tn*2048,
                dot_active_cycles=4096 if mode == 8 else 8192, tiles=64, activation_access=0,
                context_fill_count=0, context_reuse_count=0, context_validation_fault_count=0)
            p.update({k: int(k == 'phase_compute_cycles')*10 for k in c.PHASES})
            lines.append('[QBS_PERF] '+' '.join(k+'='+str(v) for k, v in p.items()))
            for lane in range(4):
                count = 4096 if mode == 8 else 0
                lines.append(f'STAGE2_SOC_LOAN lane={lane} seq={trial*2+part+1} accepted={count} core_issued={count} core_completed={count} returned={count}')
    lines.append('EXTENSION_M8_META id=frozen m=8 k=2048 n=32 trials=4 whole_model=0 cache=0')
    for trial, mode in enumerate(c.MODES):
        lines.append(f'EXTENSION_M8_TRIAL id={trial} mode={mode} status=0 commands=2 coop=1 prep=10 plan=10 execute=40 drain=10 total=70 '
            f'flags={1|c.SEEDS[trial]} prep_flags={1|c.SEEDS[trial]} vcsr=5 payload_bad=0 output_bad=0 guard_bad=0')
        for row in range(8):
            for col in range(32): lines.append(f'EXTENSION_M8_OUTPUT trial={trial} row={row} col={col} bits=00000000')
    lines += ['EXTENSION_M8_PASS errors=0', 'Core Test *** SUCCESS ***']
    for lane in range(4): lines.append(f'STAGE2_SOC_LOAN_DONE lane={lane} commands=8 accepted=16384 returned=16384')
    return '\n'.join(lines), build, bytes(1024)


class Check(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(c.check(*fixture())['outputs_bit_exact'], 1024)

    def test_reject_mutations(self):
        text, build, gold = fixture()
        mutations = (
            text.replace('bits=00000000', 'bits=00000001', 1),
            text.replace('EXTENSION_M8_OUTPUT trial=3 row=7 col=31 bits=00000000', ''),
            text.replace('payload_bad=0', 'payload_bad=1', 1),
            text.replace('flags=9', 'flags=1', 1),
            text.replace('mode=8', 'mode=4', 1),
            text.replace('coop=1', 'coop=0', 1),
            text.replace('commands=2', 'commands=1', 1),
            text.replace('dot_active_cycles=4096', 'dot_active_cycles=8192', 1),
            text.replace('core_completed=4096', 'core_completed=4095', 1),
            text+'\nUVM_ERROR : broken', text+'\nEXTENSION_M8_PASS errors=0',
            text.replace('total=70', 'total=71', 1))
        for mutation in mutations:
            with self.subTest(mutation=mutation[:80]):
                with self.assertRaises(ValueError): c.check(mutation, build, gold)
        changed = copy.deepcopy(build); changed['cache'] = True
        with self.assertRaises(ValueError): c.check(text, changed, gold)


if __name__ == '__main__': unittest.main()
