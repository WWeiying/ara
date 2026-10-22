/* Host C observations only; RV64 asm is checked independently after linking. */
static unsigned probe_on, probe_step;
static const volatile uint64_t *probe_output;
static unsigned probe_ordinal;

static void observe_actual(const volatile uint64_t *p, uint64_t value) {
    read_event(p,value);
    if (probe_on) {
        need(probe_step<132 && !(probe_step&1),"probe actual-before-expected");
        need(p==probe_output+probe_step/2 && value==*p,"probe exact actual address/value");
        ++probe_step;
    }
}

static void expected_event(const volatile uint64_t *p, uint64_t value) {
    if (monitoring) {
        need(calls && calls<=5985 && expected_count<66,"expected read phase");
        unsigned i=expected_count;
        const uint64_t *wanted=e64m4_dictionary[e64m4_block_ids[calls-1][i/8]]+i%8;
        need(p==wanted && value==expected_words[calls-1][i],"all66 expected actual dictionary addresses and values");
        ++expected_count; ++total_expected;
    }
    if (probe_on) {
        need(probe_step<132 && (probe_step&1),"probe expected-after-actual");
        unsigned i=probe_step/2;
        const uint64_t *wanted=e64m4_dictionary[e64m4_block_ids[probe_ordinal][i/8]]+i%8;
        need(p==wanted && value==expected_words[probe_ordinal][i],"probe expected address/value including tail");
        ++probe_step;
    }
}

static void sticky_load_probes(void) {
    /* Every byte corruption is checked below with all132 observed reads. */
    uint64_t sample[66];
    for (unsigned ordinal=0;ordinal<5985;ordinal+=5984) {
        probe_ordinal=ordinal; probe_output=sample;
        for(unsigned test=0;test<536;++test) {
            memcpy(sample,expected_words[ordinal],sizeof(sample));
            if(test<528) ((unsigned char *)sample)[test]^=1;
            else if(test==529) sample[0]^=UINT64_C(1)<<63;
            else if(test==530) sample[33]^=UINT64_C(1)<<63;
            else if(test==531) sample[65]^=UINT64_C(1)<<63;
            else if(test==532) sample[64]^=UINT64_C(1)<<63;
            else if(test==533){sample[1]^=1;sample[2]^=1;}
            else if(test==534) sample[1]^=1;
            else if(test==535){sample[0]^=1;sample[65]^=1;}
            probe_step=0;probe_on=1;
            int bad=e64m4_packed_mismatch(sample,ordinal);
            probe_on=0;
            need(bad==(test!=528),"sticky mismatch, later matches never clear, equal differences never cancel");
            need(probe_step==132,"all66+66 reads even after first/middle/last mismatch");
        }
    }
}
