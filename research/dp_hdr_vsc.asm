; RESEARCH DRAFT, NOT WIRED INTO THE PIPELINE, NOT HOOKED, NOT FLASHABLE.
;
; DP-output HDR colorimetry for the RTD2142, the DisplayPort counterpart of
; switch2_hub_patcher/asm/rtd2142_hdr_avi.asm. While PQ/HLG HDR metadata is
; present, mark the outgoing DP stream as BT.2020 the DP 1.4 way:
;   VSC SDP DB16 = pixel encoding << 4 | 6 (ITU-R BT.2020, RGB or YCbCr)
;   VSC SDP DB17 = CEA range << 7 | bpc     (copied from the stream's MSA MISC0)
;   VSC SDP DB18 = 0 (content type not defined)
;   MSA MISC1 bit6 = 1 (colorimetry is carried in the VSC SDP)
;   SEC_FUNCTION_CTRL bit2 = 1 (transmit the VSC SDP), latched at vblank.
;
; Register addresses are the RTD2172's DP 1.2 TX1 (pages BB/BC) from the public
; Realtek tool database. The stock RTD2142 dump (17eea728...d802) drives TX1 only:
; `survey` finds 31 TX1 references and none to TX0 (4Dxx/4Exx).
;
; What the stock dump shows (research/DP_HDR_AND_VRR.md, "Findings from the stock
; dump"), which changes the approach:
;  - the firmware already has a VSC colorimetry path for TX1: dptx1_program_msa
;    (bank 2 AFC4) and dptx1_update_colorimetry (bank 2 9E7D) take it only when
;    the TX colorimetry index DF2F[6:3] is 0x0D (extended) and DF25 bit 6 is set.
;    The path builds the VSC payload (bank 1 91F2) and header (bank 1 9FCD:
;    HB2/HB3 = 05h/13h), sets SEC_FUNCTION_CTRL bit 7 (not bit 2) and MISC1 bit 6;
;  - the VSC payload goes through the SDP payload port (BC8B/BC8C, slot BC8D), not
;    the SEC_PSR_DB registers below, which the firmware never addresses directly;
;  - the HDR static-metadata SDP (type 87h) is already forwarded on this port.
; So the likely patch is a hook at that colorimetry gate that also takes the path
; (with BT.2020 as the extended colorimetry) while PQ/HLG metadata is present,
; rather than this standalone routine. It is kept as a reference for the fields.
;
; Still open: the DP port's "HDR active" condition, and confirming DF25 bit 6 is
; the downstream DPCD 0x2210 bit 3 (VSC SDP colorimetry supported) flag.
;
; Interface: C=1 apply BT.2020 VSC colorimetry, C=0 restore SDR signalling.
; Uses A, R6, R7, DPTR. No RAM.

.module dp_hdr_vsc
.area DPHDR (ABS,CODE)
.org 0x0000

TX       = 0xbb00            ; DP TX1 MAC CTRL0 page (the port this firmware drives)
SEC      = 0xbc00            ; DP TX1 MAC CTRL1 page
MSA_CTRL = TX  + 0xb4        ; bit7 msa_db
MSA_MISC0 = TX + 0xb5        ; [7:5] bpc [3] CEA range [2:1] component format
MSA_MISC1 = TX + 0xb6        ; bit6 colorimetry in VSC SDP
SEC_FUNC = SEC + 0x00        ; bit2 psr_en (VSC SDP transmit)
SEC_DBUF = SEC + 0x02        ; bit0 sec_db, bit1 latch at vblank rising
VSC_DB16 = SEC + 0x14
VSC_DB17 = SEC + 0x15
VSC_DB18 = SEC + 0x16

dp_vsc_apply::
    jnc dp_vsc_restore
    mov dptr,#MSA_MISC0
    movx a,@dptr
    mov r6,a                 ; keep MISC0
    rr a                     ; component format [2:1] -> [1:0]
    anl a,#0x03
    cjne a,#0x01,not422
    mov a,#0x26              ; YCbCr422, BT.2020
    sjmp db16
not422:
    cjne a,#0x02,isrgb
    mov a,#0x16              ; YCbCr444, BT.2020
    sjmp db16
isrgb:
    mov a,#0x06              ; RGB, BT.2020
db16:
    mov dptr,#VSC_DB16
    movx @dptr,a
    mov a,r6                 ; DB17 = CEA range (MISC0 bit3) << 7 | bpc (MISC0 [7:5])
    swap a
    rr a
    anl a,#0x07
    mov r7,a
    mov a,r6
    jnb acc.3,db17_vesa
    mov a,r7
    orl a,#0x80
    sjmp db17
db17_vesa:
    mov a,r7
db17:
    mov dptr,#VSC_DB17
    movx @dptr,a
    clr a
    mov dptr,#VSC_DB18
    movx @dptr,a
    mov dptr,#MSA_MISC1
    movx a,@dptr
    orl a,#0x40
    movx @dptr,a
    mov dptr,#SEC_FUNC
    movx a,@dptr
    orl a,#0x04
    movx @dptr,a
    sjmp latch

dp_vsc_restore::
    mov dptr,#MSA_MISC1
    movx a,@dptr
    anl a,#0xbf
    movx @dptr,a
    clr a
    mov dptr,#VSC_DB16       ; RGB/sRGB in case the VSC SDP stays enabled
    movx @dptr,a

latch:                       ; latch SDP payload and MSA at the next vblank
    mov dptr,#SEC_DBUF
    movx a,@dptr
    orl a,#0x03
    movx @dptr,a
    mov dptr,#MSA_CTRL
    movx a,@dptr
    orl a,#0x80
    movx @dptr,a
    ret
