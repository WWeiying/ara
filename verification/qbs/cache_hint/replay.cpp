#include "original_cache.h"
#include "hinted_cache.h"
#include <cassert>
#include <cstdio>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>

namespace base=ggml_riscv_q8_K_cache;
namespace hinted=ggml_riscv_q8_K_cache_hint;

// This checks cache semantics, not quantization: payloads are deterministic
// opaque bytes. Real captured activation bytes are the exact-match keys.
int main(int argc,char **argv) {
    assert(argc>1 && (argc-1)%3==0);
    base::value_cache<> a;
    hinted::value_cache<> b;
    size_t hints[8]={8,8,8,8,8,8,8,8};
    for(int arg=1;arg<argc;arg+=3) {
        const size_t k=std::stoul(argv[arg]),m=std::stoul(argv[arg+1]);
        std::ifstream file(argv[arg+2],std::ios::binary);
        assert(file.good());
        std::vector<unsigned char> raw((std::istreambuf_iterator<char>(file)),{});
        assert(k && k%256==0 && raw.size()==k*m*4);
        const size_t in=k*16,out=k/256*4*292;
        base::key ka;ka.k=k;ka.producer_tag=3;
        hinted::key kb;kb.k=k;kb.producer_tag=3;
        for(size_t group=0;group<m/4 && group<8;++group) {
            const auto *input=raw.data()+group*in;
            std::vector<unsigned char> expected(out),oa(out+128,0xa5),ob=oa;
            unsigned flags=0;
            uint32_t state=2166136261u;
            for(size_t i=0;i<in;++i) state=(state^input[i])*16777619u;
            flags=state&31;
            for(size_t i=0;i<out;++i) {
                state=state*1664525u+1013904223u;
                expected[i]=state>>24;
            }
            unsigned fa=99,fb=99;
            const bool ha=a.get(ka,input,in,oa.data()+64,out,fa);
            const bool hb=b.get(kb,input,in,ob.data()+64,out,fb,&hints[group]);
            assert(ha==hb && fa==fb && oa==ob);
            if(ha) {
                assert(fa==flags);
                for(size_t i=0;i<out;++i) assert(oa[64+i]==expected[i]);
            } else {
                const bool pa=a.put(ka,input,in,expected.data(),out,flags);
                const bool pb=b.put(kb,input,in,expected.data(),out,flags,&hints[group]);
                assert(pa==pb);
            }
            for(size_t i=0;i<64;++i)
                assert(oa[i]==0xa5 && oa[64+out+i]==0xa5 && ob[i]==0xa5 && ob[64+out+i]==0xa5);
            const auto &x=a.statistics();const auto &y=b.statistics();
            assert(x.queries==y.queries && x.hits==y.hits && x.misses==y.misses &&
                x.stores==y.stores && x.evictions==y.evictions && x.rejected==y.rejected &&
                x.allocation_failures==y.allocation_failures && x.conflicts==y.conflicts &&
                x.copied_payload_bytes==y.copied_payload_bytes &&
                a.size()==b.size() && a.retained_bytes()==b.retained_bytes());
        }
        const auto &x=a.statistics();const auto &y=b.statistics();
        std::printf("operation=%d k=%zu m=%zu queries=%llu hits=%llu misses=%llu "
            "baseline_requested_bytes=%llu hinted_requested_bytes=%llu\n",
            (arg-1)/3,k,m,(unsigned long long)x.queries,(unsigned long long)x.hits,
            (unsigned long long)x.misses,(unsigned long long)x.comparison_bytes_requested,
            (unsigned long long)y.comparison_bytes_requested);
    }
    a.clear();b.clear();assert(a.size()==0 && b.size()==0);
    std::puts("CACHE_HINT_CAPTURE_PASS scope=opaque_payload_cache_semantics_only");
}
