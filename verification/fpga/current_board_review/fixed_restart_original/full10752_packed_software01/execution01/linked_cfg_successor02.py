"""Narrow correction: la sp is an AUIPC/ADDI pair, not a stack access."""
from pathlib import Path
import traceback
import linked_cfg_audit01 as base

HERE = Path(__file__).resolve().parent
base.OUT = HERE / 'linked_cfg02'
original_save = base.save


def bound_save(path, value):
    if Path(path).name == 'inputs_before.json':
        for p in (Path(__file__).resolve(), HERE / 'run_cfg_successor02.py'):
            value[str(p)] = base.sha(p)
    original_save(path, value)


base.save = bound_save


class CFG(base.CFG):
    def __init__(self, *args):
        super().__init__(*args)
        pairs = []
        for x in self.func['_start']:
            if x['op'] == 'auipc' and x['p'][0] == 'sp':
                second = self.code[x['pc'] + len(x['blob'])]
                base.require(second['op'] == 'addi' and second['p'][:2] == ['sp', 'sp'], 'Actual contiguous la sp pair')
                intermediate = (x['pc'] + base.signed(int(x['p'][1], 0) << 12, 32)) & base.MASK
                base.require((intermediate + int(second['p'][2], 0)) & base.MASK == self.s['__stack_top'], 'Actual la sp resolves exact stack symbol')
                pairs.append((x['pc'], second['pc'], intermediate))
        base.require(len(pairs) == 1, 'Exactly one linked startup stack-address pair')
        self.stack_pair = pairs[0]

    def set(self, register, value):
        if register == 'sp' and self.pc == self.stack_pair[0]:
            base.require(value & base.MASK == self.stack_pair[2], 'Exact temporary startup SP, no memory access')
            self.reg['sp'] = value & base.MASK
            return
        if register == 'sp' and self.pc == self.stack_pair[1]:
            base.require(value & base.MASK == self.s['__stack_top'], 'Completed stack address before use')
        super().set(register, value)


base.CFG = CFG
if __name__ == '__main__':
    try:
        base.main()
    except Exception as exc:
        if base.OUT.is_dir() and not (base.OUT / 'FIRST_FAILURE.json').exists():
            base.save(base.OUT / 'FIRST_FAILURE.json', dict(status='AUDITOR_FAILED_NOT_COST_RESULT', error=repr(exc), traceback=traceback.format_exc()))
        raise
