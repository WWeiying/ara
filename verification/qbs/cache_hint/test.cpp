#include "original_cache.h"
#include "hinted_cache.h"
#include <cassert>
#include <cstdio>
#include <vector>

namespace base=ggml_riscv_q8_K_cache;
namespace hinted=ggml_riscv_q8_K_cache_hint;
static bool fail_alloc;
static uint8_t *allocate(size_t n) {return fail_alloc ? nullptr:new(std::nothrow) uint8_t[n];}

int main() {
    constexpr size_t In=4096,Out=1168,Total=In+Out;
    base::value_cache<2,2*Total,Total> a(allocate);
    hinted::value_cache<2,2*Total,Total> b(allocate);
    base::key ka;ka.k=256;ka.producer_tag=3;
    hinted::key kb;kb.k=256;kb.producer_tag=3;
    std::vector<uint8_t> input[4],packed(Out,42),oa(Out+2),ob(Out+2);
    for(unsigned i=0;i<4;++i) input[i].assign(In,uint8_t(i+1));
    size_t hints[4]={2,2,2,2};
    unsigned checks=0;
    auto get=[&](unsigned i) {
        oa.assign(Out+2,0xa5);ob=oa;
        unsigned fa=99,fb=99;
        bool ha=a.get(ka,input[i].data(),In,oa.data()+1,Out,fa);
        bool hb=b.get(kb,input[i].data(),In,ob.data()+1,Out,fb,&hints[i]);
        assert(ha==hb && fa==fb && oa==ob);++checks;
        return ha;
    };
    auto put=[&](unsigned i,unsigned flags) {
        bool pa=a.put(ka,input[i].data(),In,packed.data(),Out,flags);
        bool pb=b.put(kb,input[i].data(),In,packed.data(),Out,flags,&hints[i]);
        assert(pa==pb);++checks;return pa;
    };
    assert(put(0,1) && put(1,2));
    const uint64_t ca=a.statistics().comparison_bytes_requested,cb=b.statistics().comparison_bytes_requested;
    assert(get(1));
    assert(a.statistics().comparison_bytes_requested-ca==2*In);
    assert(b.statistics().comparison_bytes_requested-cb==In);
    hints[0]=99;assert(get(0)); // Out-of-range hint must fall back.
    hints[0]=hints[1];assert(get(0)); // Wrong valid slot must fall back.
    input[2]=input[0];hints[2]=hints[1];assert(get(2)); // Cross-group duplicates remain reusable.
    assert(put(2,1));
    assert(put(3,4));assert(!get(1)); // Replacement leaves a stale hint.
    fail_alloc=true;assert(!put(1,2));assert(get(0));fail_alloc=false;
    packed[0]^=1;assert(!put(0,1));assert(!get(0));packed[0]^=1;
    assert(put(0,1));assert(!put(0,8)); // Conflicting flags invalidate both implementations.
    uint32_t rng=19;
    for(unsigned i=0;i<10000;++i) {
        rng=rng*1664525u+1013904223u;
        unsigned group=(rng>>24)%4;
        switch(rng%7) {
        case 0: a.clear();b.clear();break; // Hints deliberately remain stale.
        case 1: input[group][(rng>>8)%In]^=uint8_t((rng>>16)|1);break;
        case 2: hints[group]=(rng>>12)%5;break;
        case 3: (void)put(group,rng%32);break;
        case 4: fail_alloc=true;(void)put(group,rng%32);fail_alloc=false;break;
        case 5: ka.producer_tag=kb.producer_tag=1+(rng%3);break;
        default:(void)get(group);break;
        }
        const auto &x=a.statistics();const auto &y=b.statistics();
        assert(x.queries==y.queries && x.hits==y.hits && x.misses==y.misses &&
            x.stores==y.stores && x.evictions==y.evictions && x.rejected==y.rejected &&
            x.allocation_failures==y.allocation_failures && x.conflicts==y.conflicts &&
            x.copied_payload_bytes==y.copied_payload_bytes &&
            a.size()==b.size() && a.retained_bytes()==b.retained_bytes());
    }
    std::printf("CACHE_HINT_HOST_PASS comparisons=%u randomized_operations=10000\n",checks);
}
