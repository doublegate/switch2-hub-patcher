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
; Register addresses are the RTD2172's DP 1.2 TX0 (pages 4D/4E) from the public
; Realtek tool database; `switch2-hub-patcher survey <rtd2142 dump>` shows whether
; the RTD2142 firmware drives TX0 (4Dxx) or TX1 (BBxx/BCxx). Change TX/SEC below.
;
; Open items before this can become a patch (see research/DP_HDR_AND_VRR.md):
;  - hook points: where the firmware programs MSA MISC0/1 and the SDP enables
;    for the DP output, and where HDR metadata on/off is detected for that port;
;  - the "HDR active" condition for the DP port (the HDMI patch reads E362 bit1 /
;    DD9F for logical port 1; the DP port's flags are not known yet);
;  - only apply when the downstream sink sets DPCD 0x2210 bit3 (VSC SDP
;    colorimetry supported); otherwise leave MSA colorimetry alone;
;  - VSC SDP header revision (HB2=05h, HB3=13h): the TX header register was not
;    found in the RTD2172 database; it may be generated in hardware.
;
; Interface: C=1 apply BT.2020 VSC colorimetry, C=0 restore SDR signalling.
; Uses A, R6, R7, DPTR. No RAM.

.module dp_hdr_vsc
.area DPHDR (ABS,CODE)
.org 0x0000

TX       = 0x4d00            ; DP TX MAC CTRL0 page (TX1 would be 0xbb00)
SEC      = 0x4e00            ; DP TX MAC CTRL1 page (TX1 would be 0xbc00)
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
