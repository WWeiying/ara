"""Independent MIN truth tables distinguish numeric order and signed zero."""
from common import *
from oracle import minimum, bitwise_oracle


def main():
    pairs = [
        (0x7fc12345,0x7fc12345,0x7fc00000,0),
        (0x7f812345,0x7fc12345,0x7fc00000,16),
        (0x7fc12345,0x3f800000,0x3f800000,0),
        (0x3f800000,0x7f812345,0x3f800000,16),
        (0x80000000,0,0x80000000,0), (0,0x80000000,0x80000000,0),
        (0,0,0,0),
        (0xbf800000,0xc0000000,0xc0000000,0),
        (0x7f800000,0xff800000,0xff800000,0),
        (1,0x80000001,0x80000001,0),
        (0x3f800000,0x40000000,0x3f800000,0),
    ]
    for a,b,result,flags in pairs:
        require(minimum(a,b)==(result,flags) and minimum(b,a)==(result,flags), 'MIN IEEE truth table')
    require(bitwise_oracle(0x7fc12345,[0x7fc12345]*3,0x24)==(0x7fc00000,0),'element2 active')
    require(bitwise_oracle(0x7fc12345,[0x7f812345]*3,0)==(0x7fc12345,0),'alloff payload no NV')
    require(bitwise_oracle(0x7f812345,[0x7f812345]*3,0)==(0x7f812345,0),'alloff sNaN untouched')
    require(bitwise_oracle(0x7fc12345,[0x7f812345]*3,0x24)==(0x7fc00000,16),'active sNaN NV')
    save(HERE/'oracle_host01.json',dict(status='PASS_HOST_ONLY',truth_tables=len(pairs),
         reduction_tests=4,no_fixture_or_reference_result_used=True,operation='MIN_NOT_MAX'))
    print('MIN_ORACLE_HOST_PASS')


if __name__=='__main__': main()
