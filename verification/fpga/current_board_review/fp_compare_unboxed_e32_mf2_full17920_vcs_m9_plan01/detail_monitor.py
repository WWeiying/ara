"""Private extension of the mature monitor; retain its complete base FAIL_RE."""
import re

# Original non-restart source prints decimal fields and a final newline.
DETAIL_PATTERN = (r'(?m:^RVV_FP_COMPARE_DETAIL op=(?P<op>[0-9]+) seed=(?P<seed>[0-9]+)'
                  r' vl=(?P<vl>[0-9]+) mask=(?P<mask>[0-9]+) sticky=(?P<sticky>[0-9]+)'
                  r' expected_flags=(?P<expected_flags>[0-9]+) actual_flags=(?P<actual_flags>[0-9]+)'
                  r' errors=(?P<errors>[1-9][0-9]*)\n)')
DETAIL = re.compile(DETAIL_PATTERN)
OTHER = r'RVV_FP_COMPARE_(?:FAIL|CAPACITY_FAIL)|BOARD_\w*(?:FAIL|TRAP|MISMATCH)'

def combined(base):
    return re.compile('(?:'+base.pattern+')|'+DETAIL_PATTERN+'|'+OTHER,base.flags)

def contract():
    return dict(detail_pattern=DETAIL_PATTERN,other_pattern=OTHER,base_FAIL_RE_preserved=True,
                complete_newline_required=True,positive_error_required=True,
                monitor_tail_bytes=256,original_max_detail_bytes=210,
                first_tuple_receipt='detail_firstfailure.json')
