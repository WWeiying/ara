"""Successor Host only: explicit previous-write/current-delta/returned-read chain."""
import copy
from common import *
import check_reference as old
import check_reference02 as successor
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
                     'baseline_negatives':baseline})
    save(HERE/'observer_host02.json',{'status':'PASS_HOST_ONLY_NOT_RAW_ACCEPTANCE','cases':rows,
         'successor_checker_sha256':sha(HERE/'check_reference02.py'),
         'original_checker_sha256':sha(HERE/'check_reference.py'),
         'original_STOPPED_preserved':True,'second_full_parse':False,'reference_dispatch':False})
    print('SUCCESSOR_OBSERVER_HOST_PASS_NO_RAW_REPARSE')


if __name__ == '__main__':
    main()
