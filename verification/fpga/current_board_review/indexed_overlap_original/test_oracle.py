#!/usr/bin/env python3
"""Offline negatives for complete original data, CSR, guards and terminal veto."""
import json
import sys
sys.dont_write_bytecode=True
from check_reference import check_point,check_terminal,value

def main():
    accepted=rejected=0
    for r in (0,49,50):
        good=[32,17,0,117,5]+[value(i) if r<50 or 7<=i<17 and i%2 else 0xfffffff9 for i in range(32)]+[0x5b12]*2
        check_point(good,r); accepted+=1
        for i in range(39):
            bad=good.copy(); bad[i]^=1
            try: check_point(bad,r)
            except ValueError: rejected+=1
            else: raise AssertionError(('Accepted corruption',r,i))
    marker='VECTOR_PASS loops=50 overlap=1 data_bits=32 index_bits=64 fault_pages=1 minor_faults=1600'
    good=[[1],0,0,0x525656303146494e,marker+'\nINDEXED_ORIGINAL_PASS\n',marker]
    check_terminal(*good); accepted+=1
    bads=[(0,[]),(0,[1,1]),(0,[3]),(1,1),(2,1),(3,0),(4,marker),
          (4,good[4]+'VECTOR_FAIL gather\n'),(4,good[4]+'BOARD_REPLAY_TRAP\n')]
    for i,v in bads:
        bad=good.copy(); bad[i]=v
        try: check_terminal(*bad)
        except ValueError: rejected+=1
        else: raise AssertionError(('Accepted bad terminal',i,v))
    print(json.dumps(dict(status='PASS_OFFLINE_ORACLE_NEGATIVES',valid_accepted=accepted,corruptions_rejected=rejected)))

if __name__=='__main__': main()
