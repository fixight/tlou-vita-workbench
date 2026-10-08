Addresses are FILE offsets in user-supplied PS4 eboot.bin.

FUNCTION/RANGE 0x79e390
0079e390: push rbp
0079e391: mov rbp, rsp
0079e394: push r15
0079e396: push r14
0079e398: push r13
0079e39a: push r12
0079e39c: push rbx
0079e39d: sub rsp, 0xa8
0079e3a4: mov r15, r9
0079e3a7: mov rbx, rsi
0079e3aa: mov qword ptr [rbp - 0xb8], r8
0079e3b1: mov qword ptr [rbp - 0xb0], rcx
0079e3b8: mov qword ptr [rbp - 0x98], rdx
0079e3bf: test r15, r15
0079e3c2: je 0x79e3cb
0079e3c4: mov qword ptr [r15], 0
0079e3cb: lea rax, [rip + 0xd9132e]
0079e3d2: mov rdi, qword ptr [rbx + 8]
0079e3d6: mov r14, qword ptr [rax + 0x48]
0079e3da: call 0x8414b0
0079e3df: mov rdi, r14
0079e3e2: mov esi, eax
0079e3e4: call 0x7aa310
0079e3e9: xor r12d, r12d
0079e3ec: test rax, rax
0079e3ef: je 0x79e770
0079e3f5: mov rsi, qword ptr [rbx]
0079e3f8: mov edx, 0x89335b6e
0079e3fd: mov rdi, rax
0079e400: mov qword ptr [rbp - 0xa0], r15
0079e407: call 0x7a4a60
0079e40c: mov r15, rax
0079e40f: cmp dword ptr [r15 + 8], 0
0079e414: je 0x79e770
0079e41a: mov r13, qword ptr [r15]
0079e41d: nop dword ptr [rax]
0079e420: mov esi, dword ptr [rbx + 0x10]
0079e423: mov r14, qword ptr [r13]
0079e427: test esi, esi
0079e429: je 0x79e440
0079e42b: mov rdi, r14
0079e42e: call 0x8110a0
0079e433: test rax, rax
0079e436: je 0x79e440
0079e438: mov eax, dword ptr [rax + 8]
0079e43b: cmp eax, dword ptr [rbx + 0x14]
0079e43e: jne 0x79e4a2
0079e440: mov rsi, qword ptr [rbx]
0079e443: vxorps xmm0, xmm0, xmm0
0079e447: xor edx, edx
0079e449: xor ecx, ecx
0079e44b: mov r8d, 1
0079e451: xor r9d, r9d
0079e454: mov rdi, r14
0079e457: call 0x812820
0079e45c: test al, al
0079e45e: je 0x79e4a2
0079e460: mov edi, dword ptr [r14 + 8]
0079e464: call 0x7a9b20
0079e469: test rax, rax
0079e46c: jne 0x79e734
0079e472: mov esi, 0xf131b5e1
0079e477: mov rdi, r14
0079e47a: call 0x811b70
0079e47f: mov ecx, 1
0079e484: test rax, rax
0079e487: je 0x79e4c2
0079e489: mov esi, 0xf131b5e1
0079e48e: mov edx, 1
0079e493: mov rdi, r14
0079e496: call 0x811e00
0079e49b: mov rcx, rax
0079e49e: test ecx, ecx
0079e4a0: jg 0x79e4c2
0079e4a2: movsxd rax, dword ptr [r15 + 8]
0079e4a6: add r13, 8
0079e4aa: xor r12d, r12d
0079e4ad: shl rax, 3
0079e4b1: add rax, qword ptr [r15]
0079e4b4: cmp r13, rax
0079e4b7: jne 0x79e420
0079e4bd: jmp 0x79e770
0079e4c2: lea r15, [rbp - 0x48]
0079e4c6: lea rsi, [rip + 0x9866e9]
0079e4cd: xor eax, eax
0079e4cf: mov edx, ecx
0079e4d1: mov qword ptr [rbp - 0xc0], rbx
0079e4d8: mov qword ptr [rbp - 0xc8], rcx
0079e4df: xor r12d, r12d
0079e4e2: mov rbx, rcx
0079e4e5: mov rdi, r15
0079e4e8: call 0x6def30
0079e4ed: mov esi, 1
0079e4f2: mov rdi, r15
0079e4f5: call 0xbf3270
0079e4fa: lea r13, [rbp - 0x68]
0079e4fe: mov r15d, eax
0079e501: lea rsi, [rip + 0x9866b7]
0079e508: xor eax, eax
0079e50a: mov edx, ebx
0079e50c: mov rdi, r13
0079e50f: mov dword ptr [rbp - 0xa4], r15d
0079e516: call 0x6def30
0079e51b: mov esi, 1
0079e520: mov rdi, r13
0079e523: call 0xbf3270
0079e528: cmp ebx, 1
0079e52b: mov ebx, 0x3729e786
0079e530: mov dword ptr [rbp - 0xa8], eax
0079e536: mov ecx, 0xc4c6f3cc
0079e53b: cmovne ebx, eax
0079e53e: mov ax, word ptr [r14 + 0x30]
0079e543: cmovne ecx, r15d
0079e547: mov dword ptr [rbp - 0xa0], ecx
0079e54d: test ax, ax
0079e550: jle 0x79e6d5
0079e556: xor r15d, r15d
0079e559: nop dword ptr [rax]
0079e560: mov rcx, qword ptr [r14 + 0x40]
0079e564: mov rdx, r15
0079e567: shl rdx, 4
0079e56b: mov esi, dword ptr [rcx + rdx]
0079e56e: cmp esi, ebx
0079e570: je 0x79e5a0
0079e572: cmp esi, dword ptr [rbp - 0xa8]
0079e578: je 0x79e5a0
0079e57a: cmp esi, dword ptr [rbp - 0xa0]
0079e580: je 0x79e5a0
0079e582: cmp esi, 0x4f807b48
0079e588: je 0x79e5a0
0079e58a: cmp esi, dword ptr [rbp - 0xa4]
0079e590: jne 0x79e6c5
0079e596: nop word ptr cs:[rax + rax]
0079e5a0: mov rdi, qword ptr [rcx + rdx + 8]
0079e5a5: mov esi, 1
0079e5aa: lea r13, [rcx + rdx]
0079e5ae: mov qword ptr [rbp - 0x70], rdi
0079e5b2: call 0xbf3270
0079e5b7: lea rcx, [rip + 0xeb1342]
0079e5be: mov dword ptr [rbp - 0x78], eax
0079e5c1: mov rdi, qword ptr [rcx]
0079e5c4: test rdi, rdi
0079e5c7: je 0x79e5d7
0079e5c9: mov rax, qword ptr [rdi]
0079e5cc: lea rsi, [rbp - 0x78]
0079e5d0: lea rdx, [rbp - 0x70]
0079e5d4: call qword ptr [rax + 0x30]
0079e5d7: mov eax, dword ptr [r13]
0079e5db: cmp eax, 0x4f807b48
0079e5e0: sete cl
0079e5e3: cmp eax, dword ptr [rbp - 0xa4]
0079e5e9: sete dl
0079e5ec: or dl, cl
0079e5ee: mov rcx, qword ptr [rbp - 0x98]
0079e5f5: cmp eax, dword ptr [rbp - 0xa0]
0079e5fb: sete r13b
0079e5ff: movsxd rax, dword ptr [rcx + 0xc00]
0079e606: or r13b, dl
0079e609: test rax, rax
0079e60c: je 0x79e646
0079e60e: lea rcx, [rax*8]
0079e616: mov edx, dword ptr [rbp - 0x78]
0079e619: lea rsi, [rcx + rcx*2]
0079e61d: mov rcx, qword ptr [rbp - 0x98]
0079e624: nop word ptr cs:[rax + rax]
0079e630: cmp dword ptr [rcx + 8], edx
0079e633: je 0x79e6b2
0079e635: add rcx, 0x18
0079e639: add rsi, -0x18
0079e63d: jne 0x79e630
0079e63f: cmp eax, 0x80
0079e644: je 0x79e6c0
0079e646: mov rsi, qword ptr [rbp - 0x70]
0079e64a: lea rdi, [rbp - 0x90]
0079e651: call 0x7b13a0
0079e656: mov al, byte ptr [rbp - 0x82]
0079e65c: mov rdx, qword ptr [rbp - 0x98]
0079e663: and al, 0xfe
0079e665: or al, r13b
0079e668: mov byte ptr [rbp - 0x82], al
0079e66e: movsxd rax, dword ptr [rdx + 0xc00]
0079e675: lea ecx, [rax + 1]
0079e678: lea rax, [rax + rax*2]
0079e67c: mov dword ptr [rdx + 0xc00], ecx
0079e682: mov rcx, qword ptr [rbp - 0x90]
0079e689: mov qword ptr [rdx + rax*8], rcx
0079e68d: mov ecx, dword ptr [rbp - 0x88]
0079e693: mov dword ptr [rdx + rax*8 + 8], ecx
0079e697: lea rcx, [rbp - 0x84]
0079e69e: mov rsi, rcx
0079e6a1: mov ecx, dword ptr [rsi + 8]
0079e6a4: mov dword ptr [rdx + rax*8 + 0x14], ecx
0079e6a8: mov rcx, qword ptr [rsi]
0079e6ab: mov qword ptr [rdx + rax*8 + 0xc], rcx
0079e6b0: jmp 0x79e6c0
0079e6b2: test r13b, r13b
0079e6b5: jne 0x79e6c0
0079e6b7: and byte ptr [rcx + 0xe], 0xfe
0079e6bb: nop dword ptr [rax + rax]
0079e6c0: movzx eax, word ptr [r14 + 0x30]
0079e6c5: inc r15
0079e6c8: movsx rcx, ax
0079e6cc: cmp r15, rcx
0079e6cf: jl 0x79e560
0079e6d5: mov rax, qword ptr [rbp - 0xb0]
0079e6dc: test eax, eax
0079e6de: jle 0x79e6f0
0079e6e0: mov rax, qword ptr [rbp - 0xb8]
0079e6e7: mov r12d, 1
0079e6ed: mov qword ptr [rax], r14
0079e6f0: cmp byte ptr [rbp + 0x10], 0
0079e6f4: je 0x79e770
0079e6f6: mov edi, 2
0079e6fb: call 0xc8f2a0
0079e700: mov rax, qword ptr [rbp - 0xc0]
0079e707: mov rbx, qword ptr [r14]
0079e70a: mov rdi, qword ptr [rax + 8]
0079e70e: call 0x840e20
0079e713: mov rcx, qword ptr [rbp - 0xc8]
0079e71a: lea rdi, [rip + 0x9864b2]
0079e721: lea rdx, [rip + 0x98648d]
0079e728: xor eax, eax
0079e72a: mov rsi, rbx
0079e72d: call 0xc8f2d0
0079e732: jmp 0x79e770
0079e734: mov rcx, qword ptr [rbp - 0xb0]
0079e73b: xor r12d, r12d
0079e73e: test ecx, ecx
0079e740: jle 0x79e752
0079e742: mov rcx, qword ptr [rbp - 0xb8]
0079e749: mov r12d, 1
0079e74f: mov qword ptr [rcx], r14
0079e752: mov rcx, qword ptr [rbp - 0xa0]
0079e759: test rcx, rcx
0079e75c: je 0x79e761
0079e75e: mov qword ptr [rcx], rax
0079e761: mov rsi, qword ptr [rbp - 0x98]
0079e768: mov rdi, rax
0079e76b: call 0x7a9990
0079e770: mov rax, qword ptr [rbp - 0xb0]
0079e777: cmp r12d, eax
0079e77a: jge 0x79e79b
0079e77c: mov rcx, qword ptr [rbp - 0xb8]
0079e783: dec eax
0079e785: xor esi, esi
0079e787: sub eax, r12d
0079e78a: lea rdx, [rax*8 + 8]
0079e792: lea rdi, [rcx + r12*8]
0079e796: call 0x1090c60
0079e79b: add rsp, 0xa8
0079e7a2: pop rbx
0079e7a3: pop r12
0079e7a5: pop r13
0079e7a7: pop r14
0079e7a9: pop r15
0079e7ab: pop rbp
0079e7ac: ret 
0079e7ad: nop 
0079e7ae: nop 
0079e7af: nop 

FUNCTION/RANGE 0x7a4a60
007a4a60: push rbp
007a4a61: mov rbp, rsp
007a4a64: push r15
007a4a66: push r14
007a4a68: push r13
007a4a6a: push r12
007a4a6c: push rbx
007a4a6d: and rsp, 0xffffffffffffffc0
007a4a71: sub rsp, 0xc0
007a4a78: mov al, byte ptr [rip + 0xeaa532]
007a4a7e: mov r12d, edx
007a4a81: mov r15, rsi
007a4a84: mov rbx, rdi
007a4a87: test al, al
007a4a89: jne 0x7a4abc
007a4a8b: lea rdi, [rip + 0xeaa51e]
007a4a92: call 0x1090b10
007a4a97: test eax, eax
007a4a99: je 0x7a4abc
007a4a9b: lea rdi, [rip + 0xeaa50e]
007a4aa2: mov qword ptr [rip + 0xeaa4f3], 0
007a4aad: mov dword ptr [rip + 0xeaa4f1], 0
007a4ab7: call 0x1090b20
007a4abc: mov rcx, qword ptr [rbx + 0x1a0]
007a4ac3: lea rax, [rip + 0xeaa4d6]
007a4aca: test rcx, rcx
007a4acd: je 0x7a4d03
007a4ad3: mov r13, qword ptr [rcx]
007a4ad6: test r13, r13
007a4ad9: je 0x7a4d03
007a4adf: mov r14, qword ptr [rbx + 0x1b0]
007a4ae6: test r14, r14
007a4ae9: je 0x7a4b19
007a4aeb: lea rdi, [rsp + 0x40]
007a4af0: call 0xc75950
007a4af5: lea rbx, [r14 + 0xb0]
007a4afc: add r14, 0x90
007a4b03: cmp byte ptr [rsp + 0x78], 0
007a4b08: cmovns rbx, r14
007a4b0c: test al, al
007a4b0e: cmove rbx, r14
007a4b12: vmovups xmm0, xmmword ptr [rbx + 0x10]
007a4b17: jmp 0x7a4b25
007a4b19: vmovups xmm0, xmmword ptr [rip + 0x98071f]
007a4b21: add rbx, 0x20
007a4b25: vmovups xmm1, xmmword ptr [r15]
007a4b2a: vpermilps xmm3, xmm0, 9
007a4b30: vpermilps xmm4, xmm0, 0xff
007a4b36: mov rax, qword ptr [r13 + 0x20]
007a4b3a: mov edx, dword ptr [r13 + 0x28]
007a4b3e: vsubps xmm1, xmm1, xmmword ptr [rbx]
007a4b42: mov rcx, rax
007a4b45: shr rcx, 0x20
007a4b49: vpermilps xmm2, xmm1, 9
007a4b4f: vmulps xmm3, xmm3, xmm1
007a4b53: vmulps xmm2, xmm0, xmm2
007a4b57: vsubps xmm2, xmm3, xmm2
007a4b5b: vpermilps xmm3, xmm2, 9
007a4b61: vmulps xmm2, xmm0, xmm2
007a4b65: vmulps xmm4, xmm4, xmm3
007a4b69: vpermilps xmm3, xmm3, 9
007a4b6f: vmulps xmm0, xmm0, xmm3
007a4b73: vpermilps xmm2, xmm2, 9
007a4b79: vsubps xmm0, xmm2, xmm0
007a4b7d: vpermilps xmm0, xmm0, 9
007a4b83: vaddps xmm0, xmm4, xmm0
007a4b87: vxorps xmm4, xmm4, xmm4
007a4b8b: vaddps xmm0, xmm0, xmm0
007a4b8f: vaddps xmm0, xmm1, xmm0
007a4b93: vmovups xmm1, xmmword ptr [r13 + 0x10]
007a4b99: vsubps xmm0, xmm0, xmmword ptr [r13]
007a4b9f: vrcpps xmm2, xmm1
007a4ba3: vmulps xmm1, xmm1, xmm2
007a4ba7: vaddps xmm1, xmm1, xmmword ptr [rip + 0x9806a1]
007a4baf: vsubps xmm1, xmm4, xmm1
007a4bb3: vmulps xmm1, xmm2, xmm1
007a4bb7: vaddps xmm1, xmm2, xmm1
007a4bbb: vmulps xmm0, xmm1, xmm0
007a4bbf: vcmpltps xmm5, xmm0, xmmword ptr [rip + 0x980698]
007a4bc8: vcvtsi2ss xmm3, xmm0, eax
007a4bcc: vcvtsi2ss xmm2, xmm0, ecx
007a4bd0: vcvtsi2ss xmm1, xmm0, edx
007a4bd4: vmovmskps esi, xmm5
007a4bd8: and esi, 7
007a4bdb: cmp esi, 7
007a4bde: jne 0x7a4c39
007a4be0: vcmpleps xmm4, xmm4, xmm0
007a4be5: vmovmskps esi, xmm4
007a4be9: and esi, 7
007a4bec: cmp esi, 7
007a4bef: jne 0x7a4c39
007a4bf1: vinsertps xmm3, xmm3, xmm2, 0x10
007a4bf7: vinsertps xmm3, xmm3, xmm1, 0x20
007a4bfd: vinsertps xmm3, xmm3, xmm2, 0x30
007a4c03: vmulps xmm0, xmm3, xmm0
007a4c07: vroundss xmm3, xmm0, xmm0, 9
007a4c0d: vmulss xmm2, xmm2, xmm3
007a4c11: vmovshdup xmm3, xmm0
007a4c15: vroundss xmm3, xmm0, xmm3, 9
007a4c1b: vpermilpd xmm0, xmm0, 1
007a4c21: vmulss xmm2, xmm1, xmm2
007a4c25: vroundss xmm0, xmm0, xmm0, 9
007a4c2b: vmulss xmm1, xmm1, xmm3
007a4c2f: vaddss xmm1, xmm2, xmm1
007a4c33: vaddss xmm0, xmm0, xmm1
007a4c37: jmp 0x7a4c41
007a4c39: vmulss xmm0, xmm3, xmm2
007a4c3d: vmulss xmm0, xmm1, xmm0
007a4c41: vcvttss2si ebx, xmm0
007a4c45: test ebx, ebx
007a4c47: js 0x7a4c53
007a4c49: imul edx, eax
007a4c4c: imul edx, ecx
007a4c4f: cmp ebx, edx
007a4c51: jle 0x7a4c86
007a4c53: call 0xc91770
007a4c58: test rax, rax
007a4c5b: je 0x7a4c84
007a4c5d: lea rdi, [rip + 0x981851]
007a4c64: lea rsi, [rip + 0x981883]
007a4c6b: lea rdx, [rip + 0x981896]
007a4c72: lea rcx, [rip + 0x980854]
007a4c79: mov r8d, 0x100
007a4c7f: xor r9d, r9d
007a4c82: call rax
007a4c84: int 0x41
007a4c86: movsxd rax, ebx
007a4c89: xor esi, esi
007a4c8b: mov r9, qword ptr [r13 + rax*8 + 0x30]
007a4c90: mov edx, dword ptr [r9 + 8]
007a4c94: movsxd r8, edx
007a4c97: jmp 0x7a4cb0
007a4c99: dec edi
007a4c9b: inc ebx
007a4c9d: sub edi, edx
007a4c9f: mov esi, ebx
007a4ca1: mov edx, edi
007a4ca3: nop word ptr cs:[rax + rax]
007a4cb0: mov edi, edx
007a4cb2: test edi, edi
007a4cb4: jle 0x7a4cd4
007a4cb6: mov edx, edi
007a4cb8: mov rcx, qword ptr [r9]
007a4cbb: shr edx, 0x1f
007a4cbe: add edx, edi
007a4cc0: sar edx, 1
007a4cc2: lea ebx, [rdx + rsi]
007a4cc5: movsxd rax, ebx
007a4cc8: shl rax, 4
007a4ccc: cmp dword ptr [rcx + rax], r12d
007a4cd0: jae 0x7a4cb0
007a4cd2: jmp 0x7a4c99
007a4cd4: mov rcx, qword ptr [r9]
007a4cd7: movsxd rdx, esi
007a4cda: shl r8, 4
007a4cde: shl rdx, 4
007a4ce2: add r8, rcx
007a4ce5: cmp dword ptr [rcx + rdx], r12d
007a4ce9: jne 0x7a4cf0
007a4ceb: add rcx, rdx
007a4cee: jmp 0x7a4cf3
007a4cf0: mov rcx, r8
007a4cf3: lea rax, [rip + 0xeaa2a6]
007a4cfa: cmp rcx, r8
007a4cfd: je 0x7a4d03
007a4cff: mov rax, qword ptr [rcx + 8]
007a4d03: lea rsp, [rbp - 0x28]
007a4d07: pop rbx
007a4d08: pop r12
007a4d0a: pop r13
007a4d0c: pop r14
007a4d0e: pop r15
007a4d10: pop rbp
007a4d11: ret 

FUNCTION/RANGE 0x812820
00812820: push rbp
00812821: mov rbp, rsp
00812824: push r15
00812826: push r14
00812828: push r13
0081282a: push r12
0081282c: push rbx
0081282d: sub rsp, 0x88
00812834: vmovups xmm1, xmmword ptr [rip + 0x91c254]
0081283c: vmovss dword ptr [rbp - 0x64], xmm0
00812841: vxorps xmm0, xmm0, xmm0
00812845: mov r13, r9
00812848: mov ebx, r8d
0081284b: mov r12, rdx
0081284e: mov r15, rsi
00812851: mov r14, rdi
00812854: test cl, cl
00812856: vmovups xmmword ptr [rbp - 0x50], xmm0
0081285b: vmovups xmmword ptr [rbp - 0x40], xmm1
00812860: jne 0x81287d
00812862: lea rsi, [rbp - 0x50]
00812866: mov rdi, r14
00812869: call 0x811ec0
0081286e: test al, al
00812870: jne 0x81287d
00812872: test bl, bl
00812874: jne 0x81287d
00812876: xor ebx, ebx
00812878: jmp 0x8129de
0081287d: xor ecx, ecx
0081287f: test r12, r12
00812882: jne 0x8128a6
00812884: test r13, r13
00812887: jne 0x8128a6
00812889: test byte ptr [r14 + 0xe], 1
0081288e: jne 0x8129cd
00812894: mov rdi, r14
00812897: call 0x811160
0081289c: mov cl, 1
0081289e: test al, al
008128a0: je 0x8129dc
008128a6: vmovups xmm4, xmmword ptr [rbp - 0x40]
008128ab: vmovups xmm0, xmmword ptr [r15]
008128b0: vmovups xmm5, xmmword ptr [rbp - 0x50]
008128b5: mov dword ptr [rbp - 0x68], ecx
008128b8: lea rsi, [rbp - 0x60]
008128bc: mov rdi, r14
008128bf: mov rdx, r12
008128c2: mov rcx, r13
008128c5: vpermilps xmm1, xmm0, 9
008128cb: vpermilps xmm2, xmm4, 9
008128d1: vpermilps xmm3, xmm4, 0xff
008128d7: vmovaps xmmword ptr [rbp - 0xa0], xmm5
008128df: vmovaps xmmword ptr [rbp - 0x80], xmm4
008128e4: vmovaps xmmword ptr [rbp - 0x90], xmm2
008128ec: vmulps xmm1, xmm4, xmm1
008128f0: vmulps xmm2, xmm0, xmm2
008128f4: vmovaps xmmword ptr [rbp - 0xb0], xmm3
008128fc: vsubps xmm1, xmm1, xmm2
00812900: vpermilps xmm2, xmm1, 9
00812906: vmulps xmm1, xmm4, xmm1
0081290a: vmulps xmm3, xmm3, xmm2
0081290e: vpermilps xmm2, xmm2, 9
00812914: vmulps xmm2, xmm4, xmm2
00812918: vpermilps xmm1, xmm1, 9
0081291e: vsubps xmm1, xmm2, xmm1
00812922: vpermilps xmm1, xmm1, 9
00812928: vaddps xmm1, xmm3, xmm1
0081292c: vaddps xmm1, xmm1, xmm1
00812930: vaddps xmm0, xmm0, xmm1
00812934: vaddps xmm0, xmm5, xmm0
00812938: vmovups xmmword ptr [rbp - 0x60], xmm0
0081293d: vmovss xmm0, dword ptr [rbp - 0x64]
00812942: call 0x80f440
00812947: mov bl, al
00812949: test r13, r13
0081294c: je 0x8129b5
0081294e: vmovups xmm0, xmmword ptr [r13]
00812954: vmovaps xmm4, xmmword ptr [rbp - 0x80]
00812959: vsubps xmm0, xmm0, xmmword ptr [rbp - 0xa0]
00812961: vmulps xmm2, xmm0, xmmword ptr [rbp - 0x90]
00812969: vpermilps xmm1, xmm0, 9
0081296f: vmulps xmm1, xmm4, xmm1
00812973: vsubps xmm1, xmm2, xmm1
00812977: vpermilps xmm2, xmm1, 9
0081297d: vmulps xmm1, xmm4, xmm1
00812981: vmulps xmm3, xmm2, xmmword ptr [rbp - 0xb0]
00812989: vpermilps xmm2, xmm2, 9
0081298f: vmulps xmm2, xmm4, xmm2
00812993: vpermilps xmm1, xmm1, 9
00812999: vsubps xmm1, xmm1, xmm2
0081299d: vpermilps xmm1, xmm1, 9
008129a3: vaddps xmm1, xmm3, xmm1
008129a7: vaddps xmm1, xmm1, xmm1
008129ab: vaddps xmm0, xmm0, xmm1
008129af: vmovups xmmword ptr [r13], xmm0
008129b5: mov eax, dword ptr [rbp - 0x68]
008129b8: test al, al
008129ba: jne 0x8129d3
008129bc: test byte ptr [r14 + 0xe], 1
008129c1: jne 0x8129d1
008129c3: mov rdi, r14
008129c6: call 0x811160
008129cb: jmp 0x8129d3
008129cd: xor ebx, ebx
008129cf: jmp 0x8129de
008129d1: xor eax, eax
008129d3: test al, al
008129d5: setne al
008129d8: and bl, al
008129da: jmp 0x8129de
008129dc: xor ebx, ebx
008129de: mov al, bl
008129e0: add rsp, 0x88
008129e7: pop rbx
008129e8: pop r12
008129ea: pop r13
008129ec: pop r14
008129ee: pop r15
008129f0: pop rbp
008129f1: ret 

FUNCTION/RANGE 0x811160
00811160: push rbp
00811161: mov rbp, rsp
00811164: push r15
00811166: push r14
00811168: push r13
0081116a: push r12
0081116c: push rbx
0081116d: push rax
0081116e: mov r12, rdi
00811171: mov edi, 0xe1a8c886
00811176: and byte ptr [r12 + 0xe], 0xf7
0081117c: mov rdx, qword ptr [r12 + 0x40]
00811181: movsx esi, word ptr [r12 + 0x30]
00811187: call 0x7ae390
0081118c: mov r14, rax
0081118f: test r14, r14
00811192: je 0x81120c
00811194: mov ax, word ptr [r12 + 0x30]
0081119a: xor r13d, r13d
0081119d: mov ebx, 8
008111a2: test ax, ax
008111a5: jle 0x8111f8
008111a7: xor r15d, r15d
008111aa: nop word ptr [rax + rax]
008111b0: mov rcx, qword ptr [r12 + 0x40]
008111b5: cmp dword ptr [rcx + rbx - 8], 0x3da64e6a
008111bd: jne 0x8111df
008111bf: mov esi, dword ptr [r14 + 8]
008111c3: mov edx, dword ptr [rcx + rbx]
008111c6: lea rdi, [rip + 0xe44243]
008111cd: call 0x8406a0
008111d2: test al, al
008111d4: jne 0x81120c
008111d6: movzx eax, word ptr [r12 + 0x30]
008111dc: inc r15d
008111df: inc r13
008111e2: add rbx, 0x10
008111e6: movsx rcx, ax
008111ea: cmp r13, rcx
008111ed: jl 0x8111b0
008111ef: test r15d, r15d
008111f2: je 0x8111f8
008111f4: xor eax, eax
008111f6: jmp 0x811218
008111f8: mov esi, dword ptr [r14 + 8]
008111fc: lea rdi, [rip + 0xe4420d]
00811203: call 0x840670
00811208: test al, al
0081120a: je 0x811216
0081120c: or byte ptr [r12 + 0xe], 8
00811212: mov al, 1
00811214: jmp 0x811218
00811216: xor eax, eax
00811218: add rsp, 8
0081121c: pop rbx
0081121d: pop r12
0081121f: pop r13
00811221: pop r14
00811223: pop r15
00811225: pop rbp
00811226: ret 

FUNCTION/RANGE 0x80f710
0080f710: vmovups xmm0, xmmword ptr [rip + 0x91f158]
0080f718: shr eax, 0x10
0080f71b: mov r9d, 0
0080f721: je 0x80f795
0080f723: vmovaps xmm0, xmmword ptr [rip + 0x91f155]
0080f72b: vmovups xmm2, xmmword ptr [rip + 0x91f13d]
0080f733: lea rcx, [r13 + 0x60]
0080f737: neg rax
0080f73a: xor r9d, r9d
0080f73d: vblendps xmm1, xmm0, xmmword ptr [rsi], 7
0080f743: nop word ptr cs:[rax + rax]
0080f750: vmulps xmm0, xmm1, xmmword ptr [rcx]
0080f754: lea rbx, [rcx - 0x40]
0080f758: vpermilps xmm3, xmm0, 0x39
0080f75e: vaddps xmm0, xmm0, xmm3
0080f762: vpermilpd xmm3, xmm0, 1
0080f768: vaddps xmm0, xmm0, xmm3
0080f76c: vpermilps xmm0, xmm0, 0
0080f772: vcmpltps xmm3, xmm2, xmm0
0080f777: vmovmskps edi, xmm3
0080f77b: cmp edi, 0xf
0080f77e: je 0x80f784
0080f780: vmovaps xmm0, xmm2
0080f784: cmove r9, rbx
0080f788: add rcx, 0x70
0080f78c: vmovaps xmm2, xmm0
0080f790: inc rax
0080f793: jne 0x80f750
0080f795: mov bl, 1
0080f797: vucomiss xmm12, xmm0
0080f79b: ja 0x80f7a0
0080f79d: mov bl, r12b
0080f7a0: test r8, r8

FUNCTION/RANGE 0x80fe34
0080fe34: test r15, r15
0080fe37: je 0x80fe50
0080fe39: vmovaps xmm1, xmmword ptr [rbp - 0x100]
0080fe41: vucomiss xmm1, xmm0
0080fe45: jb 0x80fe55
0080fe47: mov byte ptr [r15], 1
0080fe4b: mov r12b, bl
0080fe4e: jmp 0x80fe60
0080fe50: mov r12b, bl
0080fe53: jmp 0x80fe60
0080fe55: mov r12b, bl
0080fe58: nop dword ptr [rax + rax]
0080fe60: mov r13, qword ptr [r13]
0080fe64: mov al, r12b
0080fe67: and al, 1
0080fe69: sete cl
0080fe6c: test r13, r13
0080fe6f: je 0x80fe79
0080fe71: test cl, cl
0080fe73: jne 0x80f5e0
0080fe79: and al, 1
0080fe7b: add rsp, 0xe8
0080fe82: pop rbx
0080fe83: pop r12
0080fe85: pop r13
0080fe87: pop r14
0080fe89: pop r15
0080fe8b: pop rbp
0080fe8c: ret 

FUNCTION/RANGE 0x8093e0
008093e0: push rbp
008093e1: mov rbp, rsp
008093e4: push r15
008093e6: push r14
008093e8: push r13
008093ea: push r12
008093ec: push rbx
008093ed: sub rsp, 0x18
008093f1: mov rbx, rdi
008093f4: mov r14, rdx
008093f7: mov r12, rsi
008093fa: lea rdi, [rbp - 0x38]
008093fe: mov r15, rcx
00809401: mov qword ptr [rbx + 0x10], r14
00809405: mov rsi, qword ptr [r14 + 0x20]
00809409: call 0x812f20
0080940e: mov eax, dword ptr [rbp - 0x30]
00809411: mov dword ptr [rbx + 0x20], eax
00809414: mov rax, qword ptr [rbp - 0x38]
00809418: mov qword ptr [rbx + 0x18], rax
0080941c: test byte ptr [r12 + 0xc], 1
00809422: je 0x8094ae
00809428: mov r13, qword ptr [r14 + 0x10]
0080942c: test r13, r13
0080942f: je 0x809450
00809431: test byte ptr [r13], 3
00809436: je 0x809450
00809438: mov rdi, r13
0080943b: call 0x80ff60
00809440: test al, al
00809442: je 0x809450
00809444: mov rsi, qword ptr [rbx + 0x10]
00809448: mov rdi, r13
0080944b: call 0x810020
00809450: add r12, 8
00809454: test r15, r15
00809457: lea r13, [r15 + 0xa8]
0080945e: mov rdi, qword ptr [rbx + 0x10]
00809462: mov esi, 0x1157c38c
00809467: cmove r13, r12
0080946b: xor ecx, ecx
0080946d: mov edx, dword ptr [r13]
00809471: call 0x811be0
00809476: lea r15, [rip + 0xf6b3c3]
0080947d: mov esi, 1
00809482: mov rdi, r15
00809485: call 0xa82d30
0080948a: mov edx, dword ptr [r13]
0080948e: mov rsi, qword ptr [rbx + 0x10]
00809492: mov edi, 0x26919b57
00809497: call 0x809a10
0080949c: xor esi, esi
0080949e: mov rdi, r15
008094a1: call 0xa82d30
008094a6: mov rdi, r14
008094a9: call 0xa6bb60
008094ae: add rsp, 0x18
008094b2: pop rbx
008094b3: pop r12
008094b5: pop r13
008094b7: pop r14
008094b9: pop r15
008094bb: pop rbp
008094bc: ret 
008094bd: nop 
008094be: nop 
008094bf: nop 
008094c0: push rbp
008094c1: mov rbp, rsp
008094c4: push r15
008094c6: push r14
008094c8: push r13
008094ca: push r12
008094cc: push rbx
008094cd: sub rsp, 0x48
008094d1: mov r12, qword ptr [rdi + 0x10]
008094d5: lea r15, [rdi + 0x10]
008094d9: mov dword ptr [rbp - 0x64], r8d
008094dd: mov qword ptr [rbp - 0x50], rcx
008094e1: vmovss dword ptr [rbp - 0x34], xmm0
008094e6: mov qword ptr [rbp - 0x30], rdx
008094ea: mov qword ptr [rbp - 0x70], rsi
008094ee: mov qword ptr [rbp - 0x40], rdi
008094f2: cmp r12, r15
008094f5: je 0x80969b
008094fb: vaddss xmm0, xmm1, dword ptr [rbp - 0x34]
00809500: mov rdx, qword ptr [rbp - 0x50]
00809504: mov rcx, qword ptr [rbp - 0x40]
00809508: mov rbx, r12
0080950b: lea r14, [rcx + 0x30]
0080950f: lea rax, [rdx + 0xa8]
00809516: lea rcx, [rcx + 8]
0080951a: test rdx, rdx
0080951d: cmovne rcx, rax
00809521: mov qword ptr [rbp - 0x60], r14
00809525: mov qword ptr [rbp - 0x58], rcx
00809529: vmovss dword ptr [rbp - 0x48], xmm0
0080952e: nop 
00809530: mov r13, r12
00809533: lea rdi, [rbx + 0x18]
00809537: mov r12, qword ptr [r13]
0080953b: call 0x812f40
00809540: test rax, rax
00809543: je 0x809658
00809549: mov eax, dword ptr [rbp - 0x64]
0080954c: mov rdi, qword ptr [rbx + 0x10]
00809550: test al, al
00809552: je 0x80955e
00809554: test byte ptr [rdi + 0xe], 4
00809558: je 0x80968f
0080955e: mov rsi, qword ptr [rbp - 0x30]
00809562: vmovss xmm0, dword ptr [rbp - 0x48]
00809567: xor edx, edx
00809569: xor ecx, ecx
0080956b: xor r8d, r8d
0080956e: xor r9d, r9d
00809571: call 0x812820
00809576: test al, al
00809578: je 0x8095e0
0080957a: mov rax, qword ptr [rbp - 0x40]
0080957e: test byte ptr [rax + 0xc], 1
00809582: je 0x80968f
00809588: lea rax, [rip + 0xe48a96]
0080958f: cmp byte ptr [rax], 0
00809592: je 0x8095ab
00809594: mov rdi, qword ptr [rbx + 0x10]
00809598: mov esi, 0xd21293b8
0080959d: call 0x811b70
008095a2: test rax, rax
008095a5: jne 0x80968f
008095ab: mov r13, qword ptr [rbp - 0x58]
008095af: mov rdi, qword ptr [rbx + 0x10]
008095b3: mov esi, 0xf131b5e1
008095b8: mov ecx, 1
008095bd: mov edx, dword ptr [r13]
008095c1: call 0x811be0
008095c6: mov edx, dword ptr [r13]
008095ca: mov rsi, qword ptr [rbx + 0x10]
008095ce: mov edi, 0xfd1c5374
008095d3: call 0x809a10
008095d8: jmp 0x80968f
008095dd: nop dword ptr [rax]
008095e0: lea rax, [rip + 0xf16949]
008095e7: cmp byte ptr [rax], 0
008095ea: jne 0x809650
008095ec: mov rax, qword ptr [rbp - 0x40]
008095f0: test byte ptr [rax + 0xc], 1
008095f4: je 0x809650
008095f6: mov r14, qword ptr [rbp - 0x58]
008095fa: mov rsi, qword ptr [rbx + 0x10]
008095fe: mov edi, 0xf17aea1
00809603: mov edx, dword ptr [r14]
00809606: call 0x809a10
0080960b: mov edx, dword ptr [r14]
0080960e: mov rdi, qword ptr [rbx + 0x10]
00809612: mov r14, qword ptr [rbp - 0x60]
00809616: mov esi, 0x5b4bfb24
0080961b: mov ecx, 2
00809620: call 0x811be0
00809625: mov rdi, qword ptr [rbx + 0x10]
00809629: call 0xa6bcf0
0080962e: mov rax, qword ptr [rbx + 0x10]
00809632: mov rdi, qword ptr [rax + 0x10]
00809636: test rdi, rdi
00809639: je 0x809650
0080963b: test byte ptr [rdi], 2
0080963e: je 0x809650
00809640: mov esi, 7
00809645: call 0x8101e0
0080964a: nop word ptr [rax + rax]

FUNCTION/RANGE 0x809940
00809940: mov r15, qword ptr [rbx]
00809943: mov rdx, qword ptr [rbp - 0x30]
00809947: vmovss xmm0, dword ptr [rbp - 0x34]
0080994c: mov rsi, r13
0080994f: mov rdi, r15
00809952: call 0x812a00
00809957: cmp eax, 2
0080995a: je 0x8099a0
0080995c: cmp eax, 1
0080995f: jne 0x8099d0
00809961: mov r14, qword ptr [rbp - 0x40]
00809965: mov edi, 0xf17aea1
0080996a: mov rsi, r15
0080996d: mov edx, dword ptr [r14 + 8]
00809971: call 0x809a10
00809976: mov edx, dword ptr [r14 + 8]
0080997a: mov esi, 0x5b4bfb24
0080997f: mov ecx, 2
00809984: mov rdi, r15
00809987: call 0x811be0
0080998c: mov rdi, r15
0080998f: call 0xa6bcf0
00809994: jmp 0x8099d0
00809996: nop word ptr cs:[rax + rax]
008099a0: mov r14, qword ptr [rbp - 0x40]
008099a4: mov esi, 0x1157c38c
008099a9: xor ecx, ecx
008099ab: mov rdi, r15
008099ae: mov edx, dword ptr [r14 + 8]
008099b2: call 0x811be0
008099b7: mov edx, dword ptr [r14 + 8]
008099bb: mov edi, 0x26919b57
008099c0: mov rsi, r15
008099c3: call 0x809a10
008099c8: mov rdi, r15
008099cb: call 0xa6bb60