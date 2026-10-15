extern unsigned long op_0(const word *,const word *,word *,unsigned long,unsigned long,const uint8_t *,unsigned long,unsigned long);
extern unsigned long op_1(const word *,const word *,word *,unsigned long,unsigned long,const uint8_t *,unsigned long,unsigned long);
extern unsigned long op_2(const word *,const word *,word *,unsigned long,unsigned long,const uint8_t *,unsigned long,unsigned long);
extern unsigned long op_3(const word *,const word *,word *,unsigned long,unsigned long,const uint8_t *,unsigned long,unsigned long);
#define OPERATION_COUNT 4
#define OPERATION_FUNCTIONS op_0,op_1,op_2,op_3
#define OPERATION_NAMES "vsmul.vv","vsadd.vv","vsaddu.vv","vssub.vv"
#define OPERATION_KINDS 4,4,4,4
#define INTEGER_EXTENSION 1
#define AGNOSTIC_POLICY 0

#define RESTART_SUITE 1
#define TRACE_RESTART_BOUNDARIES 1
