extern unsigned long op_0(const word *,const word *,word *,unsigned long,unsigned long,const uint8_t *,unsigned long,unsigned long);
extern unsigned long op_1(const word *,const word *,word *,unsigned long,unsigned long,const uint8_t *,unsigned long,unsigned long);
extern unsigned long op_2(const word *,const word *,word *,unsigned long,unsigned long,const uint8_t *,unsigned long,unsigned long);
extern unsigned long op_3(const word *,const word *,word *,unsigned long,unsigned long,const uint8_t *,unsigned long,unsigned long);
extern unsigned long op_4(const word *,const word *,word *,unsigned long,unsigned long,const uint8_t *,unsigned long,unsigned long);
extern unsigned long op_5(const word *,const word *,word *,unsigned long,unsigned long,const uint8_t *,unsigned long,unsigned long);
extern unsigned long op_6(const word *,const word *,word *,unsigned long,unsigned long,const uint8_t *,unsigned long,unsigned long);
extern unsigned long op_7(const word *,const word *,word *,unsigned long,unsigned long,const uint8_t *,unsigned long,unsigned long);
#define OPERATION_COUNT 8
#define OPERATION_FUNCTIONS op_0,op_1,op_2,op_3,op_4,op_5,op_6,op_7
#define OPERATION_NAMES "vmacc.vv","vnmsac.vv","vmadd.vv","vnmsub.vv","vmacc.vx","vnmsac.vx","vmadd.vx","vnmsub.vx"
#define OPERATION_KINDS 4,4,4,4,4,4,4,4
#define INTEGER_EXTENSION 0
#define AGNOSTIC_POLICY 0
#define INTEGER_SCALAR_SUITE 1
#define INPUT_SEEDS 5
#define UNMASKED_SUITE 0
#define RESTART_SUITE 1
#define TRACE_RESTART_BOUNDARIES 1
#define INTEGER_MACC_SUITE 1
#define MACC_ACCUMULATORS 1
#define ACCUMULATOR_TRIALS 5
