"""Shared test doubles."""

import collections
import os

from nunatak.collect.execution import Executor, Invocation


class ScriptedExecutor(Executor):
    """Deterministic stand-in for the subprocess executor."""

    def __init__(self, system="Linux", blocked=None):
        self._system = system
        self._blocked = blocked
        self.calls = []
        self._responses = collections.defaultdict(collections.deque)

    @property
    def system(self):
        return self._system

    def sampling_blocked(self):
        return self._blocked

    def on(self, program, stdout="", stderr="", exit_code=0):
        """Queue a canned response for the next invocation of `program`."""
        self._responses[program].append((exit_code, stdout, stderr))
        return self

    def run(self, argv, capture=True, env=None, cwd=None):
        """Record the call and serve the next canned response."""
        self.calls.append(list(argv))
        queue = self._responses.get(os.path.basename(argv[0]))
        exit_code, stdout, stderr = queue.popleft() if queue else (0, "", "")
        return Invocation(
            argv=tuple(argv),
            exit_code=exit_code,
            stdout=stdout if capture else None,
            stderr=stderr if capture else None,
        )


# Verbatim `llvm-readelf -S` outputs (LLVM 19.1.7, Ubuntu 25.04, x86_64):
# a fully stripped shared library (.dynsym only), the workload compiled
# `gcc -O2 -g` (.symtab and DWARF), and the same without `-g`.
READELF_STRIPPED_LIB = 'There are 24 section headers, starting at offset 0x3100:\n\nSection Headers:\n  [Nr] Name              Type            Address          Off    Size   ES Flg Lk Inf Al\n  [ 0]                   NULL            0000000000000000 000000 000000 00      0   0  0\n  [ 1] .note.gnu.property NOTE           00000000000002a8 0002a8 000020 00   A  0   0  8\n  [ 2] .note.gnu.build-id NOTE           00000000000002c8 0002c8 000024 00   A  0   0  4\n  [ 3] .gnu.hash         GNU_HASH        00000000000002f0 0002f0 000024 00   A  4   0  8\n  [ 4] .dynsym           DYNSYM          0000000000000318 000318 000090 18   A  5   1  8\n  [ 5] .dynstr           STRTAB          00000000000003a8 0003a8 00005c 00   A  0   0  1\n  [ 6] .rela.dyn         RELA            0000000000000408 000408 0000a8 18   A  4   0  8\n  [ 7] .init             PROGBITS        0000000000001000 001000 00001b 00  AX  0   0  4\n  [ 8] .plt              PROGBITS        0000000000001020 001020 000010 10  AX  0   0 16\n  [ 9] .plt.got          PROGBITS        0000000000001030 001030 000010 10  AX  0   0 16\n  [10] .text             PROGBITS        0000000000001040 001040 000139 00  AX  0   0 64\n  [11] .fini             PROGBITS        000000000000117c 00117c 00000d 00  AX  0   0  4\n  [12] .rodata           PROGBITS        0000000000002000 002000 000008 08  AM  0   0  8\n  [13] .eh_frame_hdr     PROGBITS        0000000000002008 002008 000024 00   A  0   0  4\n  [14] .eh_frame         PROGBITS        0000000000002030 002030 000070 00   A  0   0  8\n  [15] .init_array       INIT_ARRAY      0000000000003e68 002e68 000008 08  WA  0   0  8\n  [16] .fini_array       FINI_ARRAY      0000000000003e70 002e70 000008 08  WA  0   0  8\n  [17] .dynamic          DYNAMIC         0000000000003e78 002e78 000150 10  WA  5   0  8\n  [18] .got              PROGBITS        0000000000003fc8 002fc8 000020 08  WA  0   0  8\n  [19] .got.plt          PROGBITS        0000000000003fe8 002fe8 000018 08  WA  0   0  8\n  [20] .data             PROGBITS        0000000000004000 003000 000008 00  WA  0   0  8\n  [21] .bss              NOBITS          0000000000004008 003008 000008 00  WA  0   0  1\n  [22] .comment          PROGBITS        0000000000000000 003008 000026 01  MS  0   0  1\n  [23] .shstrtab         STRTAB          0000000000000000 00302e 0000ce 00      0   0  1\nKey to Flags:\n  W (write), A (alloc), X (execute), M (merge), S (strings), I (info),\n  L (link order), O (extra OS processing required), G (group), T (TLS),\n  C (compressed), x (unknown), o (OS specific), E (exclude),\n  R (retain), l (large), p (processor specific)\n'

READELF_WITH_SYMTAB = 'There are 40 section headers, starting at offset 0x4038:\n\nSection Headers:\n  [Nr] Name              Type            Address          Off    Size   ES Flg Lk Inf Al\n  [ 0]                   NULL            0000000000000000 000000 000000 00      0   0  0\n  [ 1] .note.gnu.property NOTE           0000000000000350 000350 000030 00   A  0   0  8\n  [ 2] .note.gnu.build-id NOTE           0000000000000380 000380 000024 00   A  0   0  4\n  [ 3] .interp           PROGBITS        00000000000003a4 0003a4 00001c 00   A  0   0  1\n  [ 4] .gnu.hash         GNU_HASH        00000000000003c0 0003c0 000024 00   A  5   0  8\n  [ 5] .dynsym           DYNSYM          00000000000003e8 0003e8 0000d8 18   A  6   1  8\n  [ 6] .dynstr           STRTAB          00000000000004c0 0004c0 0000ad 00   A  0   0  1\n  [ 7] .gnu.version      VERSYM          000000000000056e 00056e 000012 02   A  5   0  2\n  [ 8] .gnu.version_r    VERNEED         0000000000000580 000580 000040 00   A  6   1  8\n  [ 9] .rela.dyn         RELA            00000000000005c0 0005c0 0000c0 18   A  5   0  8\n  [10] .rela.plt         RELA            0000000000000680 000680 000048 18  AI  5  25  8\n  [11] .init             PROGBITS        0000000000001000 001000 00001b 00  AX  0   0  4\n  [12] .plt              PROGBITS        0000000000001020 001020 000040 10  AX  0   0 16\n  [13] .plt.got          PROGBITS        0000000000001060 001060 000010 10  AX  0   0 16\n  [14] .plt.sec          PROGBITS        0000000000001070 001070 000030 10  AX  0   0 16\n  [15] .text             PROGBITS        00000000000010c0 0010c0 0001e9 00  AX  0   0 64\n  [16] .fini             PROGBITS        00000000000012ac 0012ac 00000d 00  AX  0   0  4\n  [17] .rodata           PROGBITS        0000000000002000 002000 000028 00   A  0   0 16\n  [18] .eh_frame_hdr     PROGBITS        0000000000002028 002028 000034 00   A  0   0  4\n  [19] .eh_frame         PROGBITS        0000000000002060 002060 0000a8 00   A  0   0  8\n  [20] .note.ABI-tag     NOTE            0000000000002108 002108 000020 00   A  0   0  4\n  [21] .note.package     NOTE            0000000000002128 002128 000070 00   A  0   0  4\n  [22] .init_array       INIT_ARRAY      0000000000003da8 002da8 000008 08  WA  0   0  8\n  [23] .fini_array       FINI_ARRAY      0000000000003db0 002db0 000008 08  WA  0   0  8\n  [24] .dynamic          DYNAMIC         0000000000003db8 002db8 0001f0 10  WA  6   0  8\n  [25] .got              PROGBITS        0000000000003fa8 002fa8 000058 08  WA  0   0  8\n  [26] .data             PROGBITS        0000000000004000 003000 000010 00  WA  0   0  8\n  [27] .bss              NOBITS          0000000000004010 003010 000008 00  WA  0   0  1\n  [28] .comment          PROGBITS        0000000000000000 003010 000026 01  MS  0   0  1\n  [29] .debug_aranges    PROGBITS        0000000000000000 003036 000030 00      0   0  1\n  [30] .debug_info       PROGBITS        0000000000000000 003066 0002e6 00      0   0  1\n  [31] .debug_abbrev     PROGBITS        0000000000000000 00334c 0001d7 00      0   0  1\n  [32] .debug_line       PROGBITS        0000000000000000 003523 000134 00      0   0  1\n  [33] .debug_str        PROGBITS        0000000000000000 003657 000128 01  MS  0   0  1\n  [34] .debug_line_str   PROGBITS        0000000000000000 00377f 00006a 01  MS  0   0  1\n  [35] .debug_loclists   PROGBITS        0000000000000000 0037e9 0000be 00      0   0  1\n  [36] .debug_rnglists   PROGBITS        0000000000000000 0038a7 000058 00      0   0  1\n  [37] .symtab           SYMTAB          0000000000000000 003900 000390 18     38  18  8\n  [38] .strtab           STRTAB          0000000000000000 003c90 00020a 00      0   0  1\n  [39] .shstrtab         STRTAB          0000000000000000 003e9a 000198 00      0   0  1\nKey to Flags:\n  W (write), A (alloc), X (execute), M (merge), S (strings), I (info),\n  L (link order), O (extra OS processing required), G (group), T (TLS),\n  C (compressed), x (unknown), o (OS specific), E (exclude),\n  R (retain), l (large), p (processor specific)\n'

READELF_NO_DEBUG = 'There are 32 section headers, starting at offset 0x3700:\n\nSection Headers:\n  [Nr] Name              Type            Address          Off    Size   ES Flg Lk Inf Al\n  [ 0]                   NULL            0000000000000000 000000 000000 00      0   0  0\n  [ 1] .note.gnu.property NOTE           0000000000000350 000350 000030 00   A  0   0  8\n  [ 2] .note.gnu.build-id NOTE           0000000000000380 000380 000024 00   A  0   0  4\n  [ 3] .interp           PROGBITS        00000000000003a4 0003a4 00001c 00   A  0   0  1\n  [ 4] .gnu.hash         GNU_HASH        00000000000003c0 0003c0 000024 00   A  5   0  8\n  [ 5] .dynsym           DYNSYM          00000000000003e8 0003e8 0000d8 18   A  6   1  8\n  [ 6] .dynstr           STRTAB          00000000000004c0 0004c0 0000ad 00   A  0   0  1\n  [ 7] .gnu.version      VERSYM          000000000000056e 00056e 000012 02   A  5   0  2\n  [ 8] .gnu.version_r    VERNEED         0000000000000580 000580 000040 00   A  6   1  8\n  [ 9] .rela.dyn         RELA            00000000000005c0 0005c0 0000c0 18   A  5   0  8\n  [10] .rela.plt         RELA            0000000000000680 000680 000048 18  AI  5  25  8\n  [11] .init             PROGBITS        0000000000001000 001000 00001b 00  AX  0   0  4\n  [12] .plt              PROGBITS        0000000000001020 001020 000040 10  AX  0   0 16\n  [13] .plt.got          PROGBITS        0000000000001060 001060 000010 10  AX  0   0 16\n  [14] .plt.sec          PROGBITS        0000000000001070 001070 000030 10  AX  0   0 16\n  [15] .text             PROGBITS        00000000000010c0 0010c0 0001e9 00  AX  0   0 64\n  [16] .fini             PROGBITS        00000000000012ac 0012ac 00000d 00  AX  0   0  4\n  [17] .rodata           PROGBITS        0000000000002000 002000 000028 00   A  0   0 16\n  [18] .eh_frame_hdr     PROGBITS        0000000000002028 002028 000034 00   A  0   0  4\n  [19] .eh_frame         PROGBITS        0000000000002060 002060 0000a8 00   A  0   0  8\n  [20] .note.ABI-tag     NOTE            0000000000002108 002108 000020 00   A  0   0  4\n  [21] .note.package     NOTE            0000000000002128 002128 000070 00   A  0   0  4\n  [22] .init_array       INIT_ARRAY      0000000000003da8 002da8 000008 08  WA  0   0  8\n  [23] .fini_array       FINI_ARRAY      0000000000003db0 002db0 000008 08  WA  0   0  8\n  [24] .dynamic          DYNAMIC         0000000000003db8 002db8 0001f0 10  WA  6   0  8\n  [25] .got              PROGBITS        0000000000003fa8 002fa8 000058 08  WA  0   0  8\n  [26] .data             PROGBITS        0000000000004000 003000 000010 00  WA  0   0  8\n  [27] .bss              NOBITS          0000000000004010 003010 000008 00  WA  0   0  1\n  [28] .comment          PROGBITS        0000000000000000 003010 000026 01  MS  0   0  1\n  [29] .symtab           SYMTAB          0000000000000000 003038 000390 18     30  18  8\n  [30] .strtab           STRTAB          0000000000000000 0033c8 00020a 00      0   0  1\n  [31] .shstrtab         STRTAB          0000000000000000 0035d2 000128 00      0   0  1\nKey to Flags:\n  W (write), A (alloc), X (execute), M (merge), S (strings), I (info),\n  L (link order), O (extra OS processing required), G (group), T (TLS),\n  C (compressed), x (unknown), o (OS specific), E (exclude),\n  R (retain), l (large), p (processor specific)\n'


# The exact source the workload-c corpus entries were compiled from.
WORKLOAD_C = """\
#include <stdio.h>
#include <stdlib.h>

static inline double axpy_element(double a, double x, double y) {
    return a * x + y;
}

static double reduce(const double *v, int n) {
    double s = 0.0;
    for (int i = 0; i < n; i++)
        s += axpy_element(2.0, v[i], s);
    return s;
}

int main(void) {
    int n = 1 << 20;
    double *v = malloc(n * sizeof(double));
    for (int i = 0; i < n; i++) v[i] = i * 0.5;
    double s = 0.0;
    for (int r = 0; r < 200; r++) s += reduce(v, n);
    printf("%f\\n", s);
    free(v);
    return 0;
}
"""
