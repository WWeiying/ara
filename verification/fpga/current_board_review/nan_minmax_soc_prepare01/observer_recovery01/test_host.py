"""Successor Host only: explicit previous-write/current-delta/returned-read chain."""
import copy
import re
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from common import *
RECOVERY = Path(__file__).resolve().parent
import check_reference as old
import importlib.util
_spec = importlib.util.spec_from_file_location('offline_successor',RECOVERY/'checker.py')
successor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(successor)
from raw_mutations import insert_nv
from test_host import witness


def main():
    require(sha(HERE/'check_reference.py') == '72d276601b3e3d8723ebb0abaf677096e50b09c077f56ec8478d137d86b9539b',
            'sealed checker untouched')
    rows = []
    for shape in SHAPES:
        spec = successor.specification(HERE/shape)
        explicit = witness(spec)
        successor.validate(spec, explicit)
        omitted = copy.deepcopy(explicit)
        omitted['helper'][11]['csrs'].pop('fflags')
        successor.validate(spec, omitted)
        # Host raw witness, not an invented architectural acceptance record.
        raw = (f"core   0: 3 0x{spec['helper'][11][0]:016x} (0x1c881c57) e32 m1 l3 "
               "c8_vstart 0x0000000000000000 v24 0x" +
               bytes.fromhex(omitted['helper'][11]['vectors']['24'])[::-1].hex() + "\n")
        def decode_delta(line):
            row = copy.deepcopy(omitted['helper'][11])
            match = successor.LINE.fullmatch(line.rstrip('\n'))
            require(match is not None, 'Host raw syntax')
            row['pc'], row['insn'] = int(match[1],16), match[2][2:]
            row['csrs'] = {k:int(v,16) for k,v in successor.CSR.findall(match[3])}
            row['vectors'] = {k:int(v,16).to_bytes(128,'little').hex()
                              for k,v in successor.VECTOR.findall(match[3])}
            return row
        raw_positive = copy.deepcopy(omitted)
        raw_positive['helper'][11] = decode_delta(raw)
        successor.validate(spec, raw_positive)
        raw_bad = copy.deepcopy(omitted)
        raw_bad['helper'][11] = decode_delta(insert_nv(raw))
        try:
            successor.validate(spec, raw_bad)
        except ValueError as error:
            raw_nv_reason = str(error)
        else:
            raise ValueError('inserted raw NV accepted')
        try:
            old.validate(spec, omitted)
        except ValueError as error:
            require(str(error) == 'raw bitwise result/flags/vstart', 'original observer first cause')
        else:
            raise ValueError('old checker unexpectedly accepted unchanged flags omission')
        checks = {
            'old_NV_at_clear': lambda d:d['helper'][10]['csrs'].update({'fflags':16}),
            'missing_actual_prior_write': lambda d:d['helper'][10]['csrs'].pop('fflags'),
            'wrong_prior_instruction': lambda d:d['helper'][10].update({'insn':'00181073'}),
            'nonadjacent_prior': lambda d:d['helper'][10].update({'ordinal':1}),
            'nonzero_prior_operand': lambda d:d['helper'][10]['before_regs'].__setitem__(17,16),
            'missing_prior_row': lambda d:d['helper'].pop(10),
            'returned_NV': lambda d:d['helper'][13]['regs'].update({'6':16}),
            'returned_vstart': lambda d:d['helper'][12]['regs'].update({'10':1}),
            'explicit_new_NV': lambda d:d['helper'][11]['csrs'].update({'fflags':16}),
            'result_wrong': lambda d:d['helper'][11]['vectors'].update({'24':'00'*128}),
            'unknown_CSR_delta': lambda d:d['helper'][11]['csrs'].update({'unknown':0}),
            'fcsr_NV_conflict': lambda d:d['helper'][11]['csrs'].update({'fcsr':16}),
            'fcsr_frm_conflict': lambda d:d['helper'][11]['csrs'].update({'fcsr':32}),
            'extra_CSR_on_read': lambda d:d['helper'][13]['csrs'].update({'fflags':0}),
            'missing_returned_flags': lambda d:d['helper'][13]['regs'].clear(),
        }
        negatives=[]
        for name, change in checks.items():
            bad = copy.deepcopy(omitted)
            change(bad)
            try:
                successor.validate(spec, bad)
            except ValueError as error:
                negatives.append({'negative':name,'reason':str(error)})
            else:
                raise ValueError('successor observer negative accepted: '+name)
        baseline = successor.host_negatives(spec, explicit)
        rows.append({'shape':shape,'explicit_delta_positive':True,'unchanged_omission_positive':True,
                     'old_observer_rejects_same_omission':True,'state_negatives':negatives,
                     'raw_omission_positive':True,'raw_inserted_NV_negative':raw_nv_reason,
                     'baseline_negatives':baseline})
    save(RECOVERY/'host02.json',{'status':'PASS_HOST_ONLY_NOT_RAW_ACCEPTANCE','cases':rows,
         'successor_checker_sha256':sha(RECOVERY/'checker.py'),
         'original_checker_sha256':sha(HERE/'check_reference.py'),
         'original_STOPPED_preserved':True,'second_full_parse':False,'reference_dispatch':False})
    print('SUCCESSOR_FULL_CSR_HOST_PASS_NO_RAW_REPARSE')


if __name__ == '__main__':
    main()

