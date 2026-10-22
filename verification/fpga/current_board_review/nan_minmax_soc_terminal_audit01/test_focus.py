"""Small observer-specific Host checks, not another full worker Host suite."""
import copy
from pathlib import Path
import sys

sys.dont_write_bytecode=True
import audit


def expect_rejection(fn):
    try: fn()
    except (AssertionError,ValueError): return
    raise ValueError('focused observer negative accepted')


def main():
    worker,protocol,module=audit.modules()
    checked=[]
    for name in audit.NAMES:
        spec=worker.checker.specification(name)
        source=audit.SOURCE/worker.shape(name)
        expected=0x7fc00000 if spec['config']['mask_byte'] else 0x7fc12345
        audit.require(module.independent_oracle(0x7fc12345,spec['config']['mask_byte'])==expected,'source oracle')
        expect_rejection(lambda:module.independent_oracle(0x7f812345,spec['config']['mask_byte']))
        observer=module.Observer(spec,source,protocol)
        audit.require(observer.regs[0]==0 and all(v is None for v in observer.regs[1:]),'Unknown GPR must stay unknown')
        observer.helper=[dict(order=i) for i in range(10)]
        pc=spec['routine'][10]['pc']
        row=dict(pc=f'{pc:x}',rd='0',rd_wdata='0',mem_addr='0',mem_rmask='0',mem_wmask='0',mem_wdata='0')
        expect_rejection(lambda:observer.retirement(row,0,int(spec['routine'][10]['insn'],16),10))
        observer=module.Observer(spec,source,protocol)
        observer.helper=[dict(order=i) for i in range(21)]
        address=spec['symbols']['output']
        row=dict(pc=f"{spec['sites']['output_read']:x}",rd='10',rd_wdata='5b',
                 mem_addr=f'{address:x}',mem_rmask=f'{1<<(address%8):x}',mem_wmask='0',mem_wdata='0')
        encoding=int(spec['instructions'][row['pc']]['insn'],16)
        observer.retirement(row,0,encoding,21)
        observer=module.Observer(spec,source,protocol)
        observer.helper=[dict(order=i) for i in range(21)]
        bad=dict(row,rd_wdata='0')
        expect_rejection(lambda:observer.retirement(bad,0,encoding,21))
        checked.append(dict(name=name,oracle=True,unknown_GPR_rejected=True,guard_positive=True,guard_negative=True))
    csr=0x00802573
    audit.require(protocol._validate_retired_request_sequence([csr],[csr,csr])==1,'Exact frozen CSR replay filter')
    expect_rejection(lambda:protocol._validate_retired_request_sequence([0x1c881c57],[0x1c881c57,0x1c881c57]))
    audit.save(audit.HERE/'host01.json',dict(status='PASS_FOCUSED_HOST_ONLY',cases=checked,
         frozen_replay_positive=True,nonCSR_replay_rejected=True,active_CSV_reads=0,DUT_reference_launches=0))
    print('PASS_FOCUSED_HOST_ONLY_NO_ACTIVE_CSV')


if __name__=='__main__':
    main()
