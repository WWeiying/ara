/* Full512 results and two guards. Extra high bytes in the last LD are ignored. */
                    const uint64_t *gold_words=prefix_expected[checks];
                    unsigned left_guard=0;
                    for(unsigned chunk=0;chunk<64;++chunk) {
                        uint64_t actual=((volatile packed64 *)out)[chunk];
                        uint64_t expected=gold_words[chunk];
                        uint64_t different=actual^expected;
                        if(chunk==0) {
                            left_guard=actual&255;
                            different&=~UINT64_C(255);
                        }
                        if(different) {
                            for(unsigned byte=(chunk==0 ? 1:0);byte<8;++byte) {
                                unsigned i=chunk*8+byte-1;
                                unsigned got=(actual>>(byte*8))&255;
                                unsigned want=(expected>>(byte*8))&255;
                                if(got!=want)failure(op,seed,vl,mode,start,i,want,got);
                            }
                        }
                    }
                    uint64_t final_word=((volatile packed64 *)out)[64];
                    unsigned final_value=final_word&255;
                    unsigned final_expected=gold_words[64]&255;
                    if(final_value!=final_expected)
                        failure(op,seed,vl,mode,start,511,final_expected,final_value);
                    elements+=512;
                    if(vs>>32)failure(op,seed,vl,mode,start,cap+3,0,vs>>32);
                    unsigned right_guard=(final_word>>8)&255;
                    if(left_guard!=sentinel || right_guard!=sentinel)
                        failure(op,seed,vl,mode,start,cap+1,sentinel,right_guard);
