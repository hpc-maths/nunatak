# -g is what gives Hotspots their source lines, -O2 what makes the
# measurement worth taking. The tutorial asks for both and says why.
CFLAGS = -O2 -g -march=native

# gemm is built at -O3 on purpose: at -O2 gcc leaves the inner loop
# scalar and the kernel runs at a quarter of the speed, which makes it
# useless as a point of comparison against a known peak.
GEMM_CFLAGS = -O3 -g -march=native

all: stencil gemm

stencil: stencil.o kernels.o
	$(CC) $(CFLAGS) -o $@ $^

stencil.o kernels.o: %.o: %.c kernels.h
	$(CC) $(CFLAGS) -c -o $@ $<

gemm: gemm.o gemm_kernel.o
	$(CC) $(GEMM_CFLAGS) -o $@ $^

gemm.o gemm_kernel.o: %.o: %.c gemm.h
	$(CC) $(GEMM_CFLAGS) -c -o $@ $<

clean:
	rm -f stencil gemm *.o

.PHONY: all clean
