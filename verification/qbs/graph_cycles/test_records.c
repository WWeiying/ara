#include "records.h"
#include <assert.h>
#include <stdio.h>

int main(void) {
    struct qbs_graph_cycle_record records[8];
    struct qbs_graph_cycles p;
    qbs_graph_cycles_begin(&p,records,8,8,0,1,7,100);
    qbs_graph_cycles_append(&p,0,2,9,110,160);
    /* Empty/non-compute nodes can be skipped without inventing timings. */
    qbs_graph_cycles_append(&p,5,5,10,170,190);
    assert(qbs_graph_cycles_finish(&p,210,1));
    assert(p.count==2 && p.node_sum==70 && p.end-p.begin==110);
    assert(records[0].first==0 && records[0].last==2 && p.epoch==7);
    qbs_graph_cycles_append(&p,6,6,10,211,220);
    assert(p.count==2);

    qbs_graph_cycles_begin(&p,records,8,8,0,2,8,0);
    assert(!p.active && !qbs_graph_cycles_finish(&p,100,1));
    qbs_graph_cycles_begin(&p,records,7,8,0,1,8,0);
    assert(!p.active);
    qbs_graph_cycles_begin(&p,NULL,8,8,0,1,8,0);
    assert(!p.active);

    qbs_graph_cycles_begin(&p,records,8,8,0,1,8,100);
    qbs_graph_cycles_append(&p,0,2,9,110,160);
    qbs_graph_cycles_append(&p,2,3,9,170,180);
    assert(!qbs_graph_cycles_finish(&p,200,1));
    qbs_graph_cycles_begin(&p,records,8,8,0,1,8,100);
    qbs_graph_cycles_append(&p,0,8,9,110,160);
    assert(!p.valid);
    qbs_graph_cycles_begin(&p,records,8,8,0,1,8,100);
    qbs_graph_cycles_append(&p,0,0,9,99,160);
    assert(!p.valid);
    qbs_graph_cycles_begin(&p,records,8,8,0,1,8,100);
    qbs_graph_cycles_append(&p,0,0,9,110,109);
    assert(!p.valid);
    qbs_graph_cycles_begin(&p,records,8,8,0,1,8,100);
    qbs_graph_cycles_append(&p,0,0,9,110,160);
    assert(!qbs_graph_cycles_finish(&p,159,1));
    qbs_graph_cycles_begin(&p,records,8,8,0,1,8,100);
    assert(!qbs_graph_cycles_finish(&p,200,0));
    puts("GRAPH_CYCLE_RECORDS_PASS");
    return 0;
}
