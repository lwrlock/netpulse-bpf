# NetPulse BPF

[![License: MIT](https://img.shields.io/badge/License-MIT-indigo.svg)](LICENSE)
[![Engine: eBPF sock_ops + C](https://img.shields.io/badge/Engine-eBPF%20%2B%20TCP%20BBR-818cf8.svg)](#architecture)
[![UI: GTK4 Indigo-Gold](https://img.shields.io/badge/UI-GTK4%20%2B%20Cairo-fbbf24.svg)](#gallery)
[![Suite: FF Systems](https://img.shields.io/badge/Suite-FF%20Linux%20Systems-6366f1.svg)](https://github.com/lwrlock/ff-power-manager)

**Real-time Linux TCP BBR / `fq` qdisc congestion telemetry, `/proc/net/snmp` retransmit analytics, per-process socket descriptor profiling, and eBPF `sock_ops` RTT hooks in C and Python/GTK4.**

<p align="center">
  <img src="docs/screenshots/showcase.gif" alt="NetPulse BPF Telemetry" width="900"/>
</p>

## Architecture

```mermaid
flowchart LR
  SOCK["eBPF sock_ops RTT / Retransmit Hook"] -->|clang -target bpf| BPF["sock_rtt.bpf.o"]
  NET["/sys/class/net/*/statistics + /proc/net/snmp"] --> C["netpulse-probe Native C Engine"]
  BPF --> C
  C -->|RX/TX KB/s & BBR Status| UI["GTK4 Indigo-Gold Throughput HUD"]
```

## Highlights

- **eBPF `sock_ops` RTT Hook:** Compiles `bpf/sock_rtt.bpf.c` directly to eBPF ELF bytecode tracking smoothed RTT and retransmit callbacks.
- **TCP BBR & Qdisc Verification:** Reads kernel `tcp_congestion_control`, `default_qdisc`, SNMP retransmit ratios, and active interface RX/TX rates.
- **Process Socket Blame:** Ranks processes by active `socket:[*]` file descriptors cleanly without exposing private IPs.

<details>
<summary><b>Full-Resolution UI Screenshot</b></summary>

<p align="center">
  <img src="docs/screenshots/overview.png" alt="NetPulse BPF Overview" width="880"/>
</p>

</details>

## Build & Run

```bash
make test
./netpulse-probe --json
PYTHONPATH=src /usr/bin/python3 -m netpulse.gui
```

---

### FF Linux Kernel & Systems Suite
[FF Power Manager](https://github.com/lwrlock/ff-power-manager) · [eBPF Latency Guard](https://github.com/lwrlock/ebpf-latency-guard) · [VRAM Atlas](https://github.com/lwrlock/vram-atlas) · [Waylens Privacy](https://github.com/lwrlock/waylens-privacy) · [MemPulse](https://github.com/lwrlock/mempulse) · **NetPulse BPF** · [NVMe Sentinel](https://github.com/lwrlock/nvme-sentinel)

MIT License — Copyright (c) 2026 Furkan (**lwrlock**). Built with assistance from Google DeepMind Antigravity.
