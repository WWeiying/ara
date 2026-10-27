#include "m4-reuse-policy.h"
#include <cstdio>
#include <cstdlib>
#include <initializer_list>

using namespace ggml_riscv_m4_reuse;
static unsigned checks=0;
static void need(bool ok) {
    ++checks;
    if(!ok) {std::fprintf(stderr,"POLICY_MATRIX_FAIL check=%u\n",checks);std::exit(1);}
}
// This callback tests graph policy, not hardware format admission.
static bool formats(const ggml_tensor *node) {
    switch(node->src[0]->type) {
        case GGML_TYPE_Q2_K:case GGML_TYPE_Q3_K:case GGML_TYPE_Q4_K:
        case GGML_TYPE_Q5_K:case GGML_TYPE_Q6_K:return true;
        default:return false;
    }
}
static int index(ggml_cgraph *graph,ggml_tensor *node) {
    for(int i=0;i<ggml_graph_n_nodes(graph);++i) if(ggml_graph_node(graph,i)==node) return i;
    return -1;
}
static void matrix() {
    const ggml_type types[]={GGML_TYPE_Q2_K,GGML_TYPE_Q3_K,GGML_TYPE_Q4_K,
                            GGML_TYPE_Q5_K,GGML_TYPE_Q6_K};
    const int rows[]={1,2,3,4,7,8,15,32,36,64};
    for(auto type:types) for(int m:rows) {
        auto *ctx=ggml_init({8*1024*1024,nullptr,false});need(ctx);
        auto *w=ggml_new_tensor_2d(ctx,type,256,32);
        auto *x=ggml_new_tensor_2d(ctx,GGML_TYPE_F32,256,m);
        auto *q=ggml_mul_mat(ctx,w,x),*v=ggml_mul_mat(ctx,w,x),*k=ggml_mul_mat(ctx,w,x);
        auto *g=ggml_new_graph_custom(ctx,256,false);
        for(auto *node:{q,v,k}) ggml_build_forward_expand(g,node);
        for(auto *node:{q,v,k}) {
            const auto p=select(g,index(g,node),node,formats);
            need(p.lookup==(m>=4) && p.fill==(m>=4 && node!=k));
        }
        // All aliases of the source range must prohibit a write crossing.
        auto *saved=v->data;
        v->data=static_cast<char *>(x->data)+ggml_nbytes(x)-1;
        const auto p=select(g,index(g,q),q,formats);
        need(!p.lookup && !p.fill);v->data=saved;
        ggml_free(ctx);
    }
}
static void scan_boundary() {
    for(int gaps:{0,1,126,127,128,129}) {
        auto *ctx=ggml_init({8*1024*1024,nullptr,false});need(ctx);
        auto *w=ggml_new_tensor_2d(ctx,GGML_TYPE_Q4_K,256,32);
        auto *x=ggml_new_tensor_2d(ctx,GGML_TYPE_F32,256,4);
        auto *q=ggml_mul_mat(ctx,w,x),*k=ggml_mul_mat(ctx,w,x);
        auto *g=ggml_new_graph_custom(ctx,512,false);
        auto *last=q;
        for(int i=0;i<gaps;++i) last=ggml_scale(ctx,last,1.0f);
        ggml_build_forward_expand(g,last);ggml_build_forward_expand(g,k);
        const auto a=select(g,index(g,q),q,formats),b=select(g,index(g,k),k,formats);
        need(a.lookup==(gaps<128) && a.fill==(gaps<128));
        need(b.lookup==(gaps<128) && !b.fill);
        ggml_free(ctx);
    }
}
int main() {
    matrix();scan_boundary();
    std::printf("M4_POLICY_MATRIX_PASS checks=%u\n",checks);
}
