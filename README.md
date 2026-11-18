# NetPulse BPF

[![License: MIT](https://img.shields.io/badge/License-MIT-indigo.svg)](LICENSE)
[![Engine: eBPF sock_ops + C](https://img.shields.io/badge/Engine-eBPF%20%2B%20TCP%20BBR-818cf8.svg)](#)
[![UI: GTK4 Indigo-Gold](https://img.shields.io/badge/UI-GTK4%20%2B%20Cairo-fbbf24.svg)](#)

**Real-time Linux TCP BBR / `fq` qdisc congestion telemetry, `/proc/net/snmp` retransmit analytics, per-process socket descriptor profiling, and eBPF `sock_ops` RTT hooks in C and Python/GTK4.**

<p align="center">
  <img src="docs/screenshots/showcase.gif" alt="NetPulse BPF Telemetry" width="900"/>
</p>

## Highlights

- **eBPF `sock_ops` RTT Hook:** Compiles `bpf/sock_rtt.bpf.c` directly to eBPF ELF bytecode tracking smoothed RTT and retransmit callbacks.
- **TCP BBR & Qdisc Verification:** Reads kernel `tcp_congestion_control`, `default_qdisc`, SNMP retransmit ratios, and active interface RX/TX rates.
- **Process Socket Blame:** Ranks processes by active `socket:[*]` file descriptors cleanly without leaking remote IPs.

## Build & Run

```bash
make test
./netpulse-probe --json
PYTHONPATH=src /usr/bin/python3 -m netpulse.gui
```

MIT License — Copyright (c) 2026 Furkan (**lwrlock**). Built with assistance from Google DeepMind Antigravity.
