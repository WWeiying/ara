static unsigned bit(const uint8_t *p,unsigned i) {return (p[i/8]>>(i%8))&1;}
static unsigned lhs_index(unsigned seed,unsigned i) {return (i+seed+7*(seed/16))%16;}
static unsigned rhs_index(unsigned seed,unsigned i,unsigned op) {
    return op<4 ? (i*3+seed*5+seed/16)%16:seed%16;
}

static unsigned original_oracle(unsigned op,unsigned seed,unsigned vl,unsigned mode,unsigned sticky,uint64_t status,unsigned *returned_flags) {
unsigned cap=16,bytes=2,start=0,errors=0,flags=sticky;
(void)mode;
        if((uint32_t)status)++errors;
        for(unsigned i=0;i<cap;++i) {
            unsigned ai=lhs_index(seed,i),bi=rhs_index(seed,i,op);
            /* Quiet-NaN payloads have identical comparison/exception semantics. */
            if(UNBOXED_COMPARISONS && op>=4)bi=14;
            struct fixture wanted=expected[op<4 ? op:op-4][ai][bi];
            unsigned old=(0x5b>>(i%8))&1,actual=bit(output+1,i);
#if DESTINATION_KIND == 1
            old=((uint64_t)a[i/SEW]>>(i%SEW))&1;
#elif DESTINATION_KIND == 2
            old=((uint64_t)b[i/SEW]>>(i%SEW))&1;
#elif DESTINATION_KIND == 3
            old=bit(mask,i);
#endif
            unsigned active=i>=start && i<vl && (UNMASKED_COMPARISONS || bit(mask,i));
            if(active) {
                flags|=wanted.flags;
                if(actual!=wanted.bit)++errors;
            } else if(start>=vl || i<start) {
                if(actual!=old)++errors;
            } else if(i<vl) {
                /* A different-EEW source overlap forces mask agnostic. */
                unsigned agnostic=DESTINATION_KIND==1 || (DESTINATION_KIND==2 && op<4);
                if(actual!=old && !(agnostic && actual==1))++errors;
            } else if(actual!=old && actual!=1 && actual!=wanted.bit)++errors;
        }
        if((status>>32)!=flags)++errors;
        if(output[0]!=0x5b || output[bytes+1]!=0x5b)++errors;
*returned_flags=flags;return errors;
}
