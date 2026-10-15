"""Host truth tables independently specified as IEEE FP32 bit patterns."""
from common import *
from oracle import maximum, bitwise_oracle


def main():
    pairs = [
        (0x7fc12345,0x7fc12345,0x7fc00000,0),
        (0x7f812345,0x7fc12345,0x7fc00000,16),
        (0x7fc12345,0x3f800000,0x3f800000,0),
        (0x3f800000,0x7f812345,0x3f800000,16),
        (0x80000000,0,0,0), (0,0x80000000,0,0),
        (0x80000000,0x80000000,0x80000000,0),
        (0xbf800000,0xc0000000,0xbf800000,0),
        (0x7f800000,0xff800000,0x7f800000,0),
        (1,0x80000001,1,0),
    ]
    for a,b,wanted,flags in pairs:
        require(maximum(a,b) == (wanted,flags), 'IEEE truth table')
    require(bitwise_oracle(0x7fc12345,[0x7fc12345]*3,0x24) == (0x7fc00000,0), 'element2 active')
    require(bitwise_oracle(0x7fc12345,[0x7f812345]*3,0) == (0x7fc12345,0), 'alloff payload no NV')
    require(bitwise_oracle(0x7f812345,[0x7f812345]*3,0) == (0x7f812345,0), 'alloff sNaN untouched')
    require(bitwise_oracle(0x7fc12345,[0x7f812345]*3,0x24) == (0x7fc00000,16), 'active sNaN NV')
    save(HERE/'oracle_host01.json', {'status':'PASS_HOST_ONLY','truth_tables':len(pairs),
         'reduction_tests':4,'no_fixture_or_reference_result_used':True})
    print('ORACLE_HOST14_PASS')


if __name__ == '__main__':
    main()
