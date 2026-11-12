; EXPERIMENTAL derivative of native responder v2. No programming operation here.
; Hook339D replaces MOV14,#46 with LCALL7B40; IRAM13 is already zero.
; Default selector70 (7W); selector30 (3W) ONLY for fixed15V EXACT3A entry.
; Other voltages/types/input currents retain the original reservation policy.
; No new RAM or upstream PDO/RDO edits. No direct protection-register writes;
; later native configuration and physical protection behavior remain unmeasured.
; Preserve all caller registers/flags and full IE; bounded critical section.
; Hardware self-consumption/headroom is UNMEASURED; test with USB ports empty.
.module power_15v
.area POWER15 (ABS,CODE)
.org 0x7b40
reserve_15v:
    push 0xe0
    push 0xf0
    push 0x82
    push 0x83
    push 0xd0
    push 0xa8
    clr 0xaf
    mov 0x14,#0x46          ; original default:70 x100mW
    mov a,0x67
    clr c
    subb a,#7
    jnc reserve_done
    mov a,0x67
    mov b,#7
    mul ab
    add a,#0x68
    mov dpl,a
    clr a
    addc a,#0x28
    mov dph,a
    movx a,@dptr
    anl a,#0xc0            ; fixed PDO only
    jnz reserve_done
    inc dptr
    inc dptr
    inc dptr
    movx a,@dptr
    cjne a,#1,reserve_done
    inc dptr
    movx a,@dptr
    cjne a,#0x2c,reserve_done ; voltage300 x50mV =15V
    inc dptr
    movx a,@dptr
    cjne a,#1,reserve_done
    inc dptr
    movx a,@dptr
    cjne a,#0x2c,reserve_done ; current300 x10mA =3A before subtraction
    mov 0x14,#0x1e          ; 3W reservation ->280 x10mA advertised
reserve_done:
    pop 0xa8
    pop 0xd0
    pop 0x83
    pop 0x82
    pop 0xf0
    pop 0xe0
    ret
