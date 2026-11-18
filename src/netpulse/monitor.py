from __future__ import annotations

import json
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[2]


def classify_link_health(retrans_pct: float, rx_dropped: int) -> str:
    if retrans_pct >= 2.5 or rx_dropped > 100:
        return "CONGESTED"
    if retrans_pct >= 0.8:
        return "ELEVATED_RETRANS"
    return "LOW_LATENCY_OPTIMAL"


def sample_network(sample_ms: int = 120) -> dict:
    probe = ROOT / "netpulse-probe"
    out = subprocess.check_output([str(probe), "--sample-ms", str(sample_ms), "--json"], text=True, timeout=4.0)
    data = json.loads(out)
    data["health"] = classify_link_health(
        float(data.get("retrans_pct", 0.0)),
        int(data.get("rx_dropped", 0)),
    )
    return data
