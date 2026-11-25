#!/usr/bin/env python3
"""Refine AKV first-X evidence with exact unused ALU-B FIFO state."""
import argparse
import importlib.util
from pathlib import Path

BASE = Path('/home/wangwy/openproject/ara_dsa/verification/performance/power_eval_20261117')
spec=importlib.util.spec_from_file_location('akv_original_offline_audit',BASE/'akv_x_audit_v1.py')
a=importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)
original=a.wanted
PREFIX=a.LANE+'.i_operand_queues.i_operand_queue_alu_b'


def wanted(path):
    owner,_,leaf=path.rpartition('.')
    return original(path) or owner in (PREFIX,PREFIX+'.i_input_buffer') and leaf in (
        'operand_i','operand_o','operand_valid_i','operand_valid_o','operand_ready_i',
        'operand_issued_i','operand_queue_cmd_valid_i','ibuf_operand','ibuf_usage_q',
        'data_i','data_o','usage_o','push_i','pop_i','read_pointer_q','write_pointer_q','mem_q')


if __name__=='__main__':
    p=argparse.ArgumentParser(allow_abbrev=False)
    p.add_argument('--output',type=Path,required=True)
    a.wanted=wanted
    a.analyze(p.parse_args().output.resolve())
