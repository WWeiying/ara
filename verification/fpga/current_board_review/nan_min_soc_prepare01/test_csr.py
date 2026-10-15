"""Successor Host only: explicit previous-write/current-delta/returned-read chain."""
import copy
from common import *
import check_reference as successor
from raw_mutations import insert_nv
from test_host import witness


def main():
    rows = []
    for shape in SHAPES:
        spec = successor.specification(HERE/shape)
        explicit = witness(spec)
        successor.validate(spec, explicit)
        omitted = copy.deepcopy(explicit)
        omitted['helper'][11]['csrs'].pop('fflags')
        successor.validate(spec, omitted)
        # Host raw witness, not an invented architectural acceptance record.
        raw = (f"core   0: 3 0x{spec['helper'][11][0]:016x} (0x14881c57) e32 m1 l3 "
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
                     'state_negatives':negatives,
                     'raw_omission_positive':True,'raw_inserted_NV_negative':raw_nv_reason,
                     'baseline_negatives':baseline})
    save(HERE/'csr_host01.json',{'status':'PASS_HOST_ONLY_NOT_RAW_ACCEPTANCE','cases':rows,
         'successor_checker_sha256':sha(HERE/'check_reference.py'),
         'sealed_MAX_unmodified':True,'second_full_parse':False,'reference_dispatch':False})
    print('SUCCESSOR_FULL_CSR_HOST_PASS_NO_RAW_REPARSE')


if __name__ == '__main__':
    main()
