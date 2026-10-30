#include "value_cache.hpp"
#include <algorithm>
#include <cstdlib>
#include <iostream>
#include <vector>

using namespace q8k_m4_experiment;
static unsigned checks=0;
static void check(bool ok) {
    ++checks;
    if(!ok) {std::cerr<<"FAIL check "<<checks<<'\n';std::exit(1);}
}
static bool fail_allocation=false;
static uint8_t *allocate(size_t n) {
    return fail_allocation ? nullptr:new(std::nothrow) uint8_t[n];
}
int main() {
    constexpr size_t in=256*16,out=4*QBS_Q8_K_BLOCK_BYTES,total=in+out;
    key k;k.k=256;k.producer_tag=1;
    std::vector<uint8_t> a(in,1),b(in,2),c(in,3),packed(out,42),saved=packed;
    std::vector<uint8_t> dest(out+2,0xa5);
    unsigned flags=99;
    value_cache<2,total*2,total> cache(allocate);
    auto get=[&](const std::vector<uint8_t> &x) {
        return cache.get(k,x.data(),in,dest.data()+1,out,flags);
    };
    check(!get(a) && flags==99);
    check(cache.put(k,a.data(),in,packed.data(),out,1));
    packed.assign(out,7);
    check(get(a) && flags==1);
    check(std::equal(saved.begin(),saved.end(),dest.begin()+1));
    check(dest.front()==0xa5 && dest.back()==0xa5);
    auto equal=a;
    check(get(equal));
    for(size_t p:{size_t(0),in/2,in-1}) {
        a[p]^=1;flags=99;dest[1]=0x77;
        check(!get(a) && flags==99 && dest[1]==0x77);
        a[p]^=1;check(get(a));
    }
    check(cache.put(k,b.data(),in,saved.data(),out,1));
    check(get(a));
    check(cache.put(k,c.data(),in,saved.data(),out,1));
    check(!get(b) && get(a) && get(c));
    check(cache.retained_bytes()==2*total && cache.size()==2);
    const auto stores=cache.statistics().stores;
    check(cache.put(k,a.data(),in,saved.data(),out,1));
    check(cache.statistics().stores==stores);
    fail_allocation=true;
    check(!cache.put(k,b.data(),in,saved.data(),out,1));
    check(get(a) && get(c));fail_allocation=false;
    check(!cache.put(k,a.data(),in,packed.data(),out,1));
    check(!get(a) && cache.statistics().conflicts==1);
    check(cache.put(k,a.data(),in,saved.data(),out,1));
    check(!cache.put(k,a.data(),in,saved.data(),out,2) && !get(a));
    for(unsigned field=0;field<8;++field) {
        key bad=k;
        switch(field) {
        case 0:bad.k=257;break;case 1:bad.producer_tag=0;break;
        case 2:bad.rows=3;break;case 3:bad.profile=255;break;
        case 4:bad.layout=255;break;case 5:bad.frm=1;break;
        case 6:bad.vstart=1;break;case 7:bad.k=0;break;
        }
        flags=99;dest[1]=0x77;
        check(!cache.get(bad,a.data(),in,dest.data()+1,out,flags));
        check(flags==99 && dest[1]==0x77);
        check(!cache.put(bad,a.data(),in,saved.data(),out,1));
    }
    check(!cache.get(k,nullptr,in,dest.data()+1,out,flags));
    check(!cache.get(k,a.data(),in,nullptr,out,flags));
    check(!cache.get(k,a.data(),in-1,dest.data()+1,out,flags));
    check(!cache.get(k,a.data(),in,dest.data()+1,out-1,flags));
    check(!cache.get(k,a.data(),in,a.data()+1,out,flags));
    check(!cache.put(k,a.data(),in,a.data()+1,out,1));
    check(!cache.put(k,a.data(),in,saved.data(),out,32));
    value_cache<1,total,total> exact;
    check(exact.put(k,a.data(),in,saved.data(),out,0));
    check(exact.retained_bytes()==total);
    value_cache<1,total-1,total> small_budget;
    check(!small_budget.put(k,a.data(),in,saved.data(),out,0));
    value_cache<1,total,total-1> small_entry;
    check(!small_entry.put(k,a.data(),in,saved.data(),out,0));
    key other=k;other.producer_tag=2;
    check(!exact.get(other,a.data(),in,dest.data()+1,out,flags));
    cache.clear();check(cache.size()==0 && cache.retained_bytes()==0);
    check(!get(c));
    check(exact.get(k,a.data(),in,dest.data()+1,out,flags) && flags==0);
    // Reused source addresses must not substitute pointer identity for value equality.
    uint32_t rng=19;
    for(unsigned iteration=0;iteration<2000;++iteration) {
        rng=rng*1664525u+1013904223u;
        size_t p=rng%in;a[p]^=uint8_t((rng>>24)|1);
        check(!exact.get(k,a.data(),in,dest.data()+1,out,flags));
        check(exact.put(k,a.data(),in,saved.data(),out,iteration%32));
        check(exact.get(k,a.data(),in,dest.data()+1,out,flags));
        check(flags==iteration%32 && dest.front()==0xa5 && dest.back()==0xa5);
    }
    std::cout<<"PASS "<<checks<<" cache checks\n";
}
