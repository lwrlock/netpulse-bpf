CC ?= gcc
CLANG ?= clang
CFLAGS ?= -O2 -Wall -Wextra -D_GNU_SOURCE
BPF_FLAGS ?= -O2 -g -target bpf -I/usr/include/x86_64-linux-gnu

.PHONY: all bpf native test clean

all: bpf native

bpf: bpf/sock_rtt.bpf.o

bpf/sock_rtt.bpf.o: bpf/sock_rtt.bpf.c
	$(CLANG) $(BPF_FLAGS) -c $< -o $@

native: netpulse-probe

netpulse-probe: src/native/net_probe.c
	$(CC) $(CFLAGS) -o $@ $<

test: all
	/usr/bin/python3 -m py_compile src/netpulse/*.py
	./netpulse-probe --sample-ms 80 --json >/dev/null
	PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests -v

clean:
	rm -f netpulse-probe bpf/sock_rtt.bpf.o
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
