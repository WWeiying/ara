#include "m4-reuse-policy.h"
#include <cstdio>
#include <cstdlib>

using namespace ggml_riscv_m4_reuse;
static unsigned checks=0;
static void need(bool ok) {++checks;if(!ok) {std::fprintf(stderr,"POLICY_FAIL check=%u\n",checks);std::exit(1);}}
static bool supported(const ggml_tensor *node) {
    return node->src[0]->type==GGML_TYPE_Q4_K;
}
int main() {
    ggml_init_params p{8*1024*1024,nullptr,false};
    auto *ctx=ggml_init(p);need(ctx);
    auto *w=ggml_new_tensor_2d(ctx,GGML_TYPE_Q4_K,256,32);
    auto *x=ggml_new_tensor_2d(ctx,GGML_TYPE_F32,256,15);
    auto *y=ggml_new_tensor_2d(ctx,GGML_TYPE_F32,256,15);
    auto *q=ggml_mul_mat(ctx,w,x),*v=ggml_mul_mat(ctx,w,x),*k=ggml_mul_mat(ctx,w,x);
    auto *g=ggml_new_graph_custom(ctx,256,false);
    ggml_build_forward_expand(g,q);ggml_build_forward_expand(g,v);ggml_build_forward_expand(g,k);
    auto at=[&](ggml_tensor *node) {for(int i=0;i<ggml_graph_n_nodes(g);++i) if(ggml_graph_node(g,i)==node) return i;return -1;};
    auto expect=[&](ggml_tensor *node,bool lookup,bool fill) {
        const auto r=select(g,at(node),node,supported);need(r.lookup==lookup && r.fill==fill);
    };
    expect(q,true,true);expect(v,true,true);expect(k,true,false);
    // A different activation is neither a hit hint nor a reason to allocate.
    v->src[1]=y;expect(q,false,false);expect(v,false,false);expect(k,false,false);v->src[1]=x;
    const auto old_op=v->op;v->op=GGML_OP_CUSTOM;
    expect(q,false,false);expect(k,false,false);v->op=old_op;
    auto *original=v->data;v->data=x->data;
    expect(q,false,false);expect(v,false,false);expect(k,false,false);v->data=original;
    // Strided source and unsupported shapes must stay on the existing path.
    const auto stride=x->nb[1];x->nb[1]+=4;expect(q,false,false);x->nb[1]=stride;
    const auto rows=x->ne[1];x->ne[1]=3;expect(q,false,false);x->ne[1]=rows;
    auto r=select(g,-1,q,supported);need(!r.lookup && !r.fill);
    r=select(g,at(v),q,supported);need(!r.lookup && !r.fill);
    r=select(nullptr,0,q,supported);need(!r.lookup && !r.fill);
    // Adjacent spans do not alias; a one-byte overlap does.
    v->data=static_cast<char *>(x->data)+ggml_nbytes(x);
    expect(q,true,true);v->data=static_cast<char *>(x->data)+ggml_nbytes(x)-1;
    expect(q,false,false);v->data=original;
    // No callback means no runtime capability proof.
    r=select(g,at(q),q,nullptr);need(!r.lookup && !r.fill);
    auto *float_weights=ggml_new_tensor_2d(ctx,GGML_TYPE_F32,256,32);
    auto *half_weights=ggml_new_tensor_2d(ctx,GGML_TYPE_F16,256,32);
    auto *other_quant=ggml_new_tensor_2d(ctx,GGML_TYPE_Q5_K,256,32);
    v->src[0]=float_weights;expect(q,true,true);expect(k,true,false);expect(v,false,false);
    v->src[0]=half_weights;expect(q,true,true);expect(k,true,false);
    v->src[0]=other_quant;expect(q,false,false);expect(k,false,false);v->src[0]=w;
    v->op=GGML_OP_VIEW;v->data=x->data;
    expect(q,true,true);expect(k,true,false);v->op=old_op;v->data=original;
    r=select(g,at(q),nullptr,supported);need(!r.lookup && !r.fill);
    v->op=GGML_OP_MUL_MAT_ID;expect(q,false,false);expect(k,false,false);v->op=old_op;
    x->ne[2]=2;expect(q,false,false);x->ne[2]=1;
    const auto old_k=x->ne[0];x->ne[0]=0;expect(q,false,false);x->ne[0]=old_k;
    x->type=GGML_TYPE_F16;expect(q,false,false);x->type=GGML_TYPE_F32;
    ggml_free(ctx);
    std::printf("M4_POLICY_PASS checks=%u\n",checks);
}
