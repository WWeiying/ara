extern void replay_text(const char*);
extern int alias_v8_e16m8_prefix50_main(void);
int main(void){unsigned long vb;__asm__ volatile("csrr %0,vlenb":"=r"(vb));if(vb!=128){replay_text("BOARD_REPLAY_VLEN_FAIL\n");return 90;}
if(alias_v8_e16m8_prefix50_main()){replay_text("BOARD_CASE_FAIL alias_v8_e16m8_prefix50\n");return 1;}replay_text("BOARD_CASE_PASS alias_v8_e16m8_prefix50\nBOARD_REPLAY_PASS\n");return 0;}
