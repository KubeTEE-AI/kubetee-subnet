"""Publish a public validator dashboard to Hippius S3.

The validator writes a single self-contained index.html with all data baked
directly into the HTML elements (no JavaScript, no fetch, no CORS, no CDN
cache issues). The page is pure static HTML + CSS.
"""
from __future__ import annotations

import html
import json
import time

_DASHBOARD_VERSION = 1

_GPU_ORDER = ["B300", "B200", "H200", "H100"]


def _fmt(n, d=2):
    if n is None:
        return "–"
    if d == 0:
        return f"{round(n):,}"
    return f"{n:,.{d}f}"


def build_html(snapshot: dict) -> str:
    """Build a self-contained HTML page with data baked into the elements."""
    epoch = int(snapshot.get("epoch", 0))
    tempo = int(snapshot.get("tempo", 360))
    usd_per_alpha = float(snapshot.get("usd_per_alpha", 0.0))
    card = snapshot.get("card", {})
    effective_card = snapshot.get("effective_card", {})
    pricing_source = snapshot.get("pricing_source", "")
    card_source = snapshot.get("card_source", "")
    miner_usd = float(snapshot.get("miner_usd", 0.0))
    owner_usd = float(snapshot.get("owner_usd", 0.0))
    total_pool = float(snapshot.get("total_pool_usd", 0.0))
    fleet_gpus = snapshot.get("fleet_gpus", {})
    miners = snapshot.get("miners", [])
    published_at = float(snapshot.get("published_at", time.time()))
    from datetime import datetime
    pub_str = datetime.utcfromtimestamp(published_at).strftime("%Y-%m-%d %H:%M:%S UTC")
    age_min = int((time.time() - published_at) / 60)
    badge = "just now" if age_min < 1 else f"{age_min}m ago"
    badge_color = "#f4c15e" if age_min >= 90 else "#3ee98f"

    # GPU inventory chips
    gpu_chips = ""
    for klass in _GPU_ORDER:
        if klass in fleet_gpus:
            gpu_chips += f'<div class="gpu"><b>{html.escape(str(klass))}</b>{html.escape(str(fleet_gpus[klass]))}</div>\n'
    if not gpu_chips:
        gpu_chips = '<div class="gpu"><b>–</b>no GPUs</div>'

    # Pricing card chips (USD per GPU-hour per class)
    _card_chips = ""
    for klass in _GPU_ORDER:
        if klass in effective_card:
            price = effective_card[klass]
            _card_chips += f'<div class="gpu"><b>{html.escape(str(klass))}</b>${_fmt(price)}/GPU/hr</div>\n'
    if not _card_chips:
        _card_chips = '<div class="gpu"><b>–</b>no card</div>'

    # Targon live payout chips (SN4 per-card USD/hr)
    targon_payout = snapshot.get("targon_payout", {})
    _targon_chips = ""
    for klass in _GPU_ORDER:
        if klass in targon_payout:
            price = float(targon_payout[klass])
            committed = float(effective_card.get(klass, 0.0))
            arrow = "down" if price < committed else ("up" if price > committed else "=")
            _targon_chips += f'<div class="gpu"><b>{html.escape(str(klass))} {html.escape(str(arrow))}</b>${_fmt(price)}/card/hr</div>\n'
    if not _targon_chips:
        _targon_chips = '<div class="gpu"><b>–</b>Targon feed off</div>'

    # Miner table rows — all prices normalized per hour
    hours_per_epoch = float(snapshot.get("hours_per_epoch", 1.2))
    rows = ""
    for m in miners:
        uid = m.get("uid", "?")
        cluster = html.escape(str(m.get("cluster_name") or "—"))
        ready = m.get("ready", False)
        status = '<span style="color:#3ee98f">validated</span>' if ready else '<span style="color:#ff8494">not ready</span>'
        gpus = m.get("gpus", [])
        gpu_str = ", ".join(f"{html.escape(str(k))}:{html.escape(str(v))}" for k, v in gpus) if gpus else "—"
        # Payout/hr = sum(GPU_count * card_price) per class
        payout_hr = 0.0
        for klass, count in gpus:
            payout_hr += int(count) * float(effective_card.get(klass, 0.0))
        # USD/hr = earned USD / hours_per_epoch
        usd_epoch = float(m.get("usd", 0.0))
        usd_hr = usd_epoch / hours_per_epoch if hours_per_epoch > 0 else 0.0
        # Alpha/hr = alpha / hours_per_epoch
        alpha_epoch = float(m.get("alpha", 0.0))
        alpha_hr = alpha_epoch / hours_per_epoch if hours_per_epoch > 0 else 0.0
        share = float(m.get("share", 0.0))
        # Epoch total = payout/hr * hours_per_epoch
        epoch_total = payout_hr * hours_per_epoch
        rows += f"<tr><td>{uid}</td><td>{cluster}</td><td>{status}</td><td>{gpu_str}</td><td class='num'>${_fmt(payout_hr)}/hr</td><td class='num'>${_fmt(usd_hr)}/hr</td><td class='num'>{_fmt(alpha_epoch,4)}</td><td class='num'>${_fmt(epoch_total)}</td><td class='num'>{_fmt(share,1)}%</td></tr>\n"
    if not rows:
        rows = "<tr><td colspan='9' style='color:#8ea1c0'>No miners this epoch</td></tr>"

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<meta http-equiv="cache-control" content="no-cache, no-store, must-revalidate"/>
<meta http-equiv="pragma" content="no-cache"/>
<meta http-equiv="expires" content="0"/>
<link rel="icon" type="image/svg+xml" href="https://s3.hippius.com/kubetee-validator/favicon.svg"/>
<title>KubeTEE Validator (SN90)</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap" rel="stylesheet"/>
<style>
:root{{--bg:#0b0e14;--panel:rgba(18,26,44,0.72);--panel-solid:#121a2c;--border:rgba(79,156,255,0.18);--text:#e6eefc;--muted:#8ea1c0;--green:#3ee98f;--gold:#f4c15e;--red:#ff8494;--blue:#4f9cff}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:linear-gradient(180deg,#0b1224,#0b0e14 60%,#080a10);background-image:radial-gradient(1200px 800px at 10% -10%,rgba(79,156,255,0.12),transparent 60%),radial-gradient(900px 700px at 90% 10%,rgba(70,224,164,0.10),transparent 55%);color:var(--text);font-family:Inter,system-ui,sans-serif;padding:28px;max-width:1400px;margin:0 auto;min-height:100vh}}
.header{{display:flex;align-items:center;gap:14px;margin-bottom:20px}}
.header img{{height:36px;width:auto;filter:drop-shadow(0 0 10px rgba(255,255,255,0.18))}}
.badge{{margin-left:auto;padding:4px 10px;border-radius:999px;font-size:12px;font-weight:600}}
.panels-row{{display:flex;gap:16px;margin-bottom:16px}}
.panel{{background:var(--panel);border:1px solid var(--border);border-radius:14px;padding:20px;flex:1;box-shadow:0 12px 40px rgba(15,20,32,0.35),inset 0 1px 0 rgba(255,255,255,0.04)}}
.panel.full{{flex:1 1 100%;margin-bottom:16px}}
.panel h2{{font-size:12px;text-transform:uppercase;letter-spacing:1px;color:var(--muted);margin-bottom:12px;font-weight:600}}
.metric{{font-size:30px;font-weight:800}}
.kv{{font-size:24px;font-weight:800;color:var(--blue)}}
.gpus{{display:flex;gap:12px;flex-wrap:wrap;margin-top:6px}}
.gpu{{background:var(--panel-solid);border:1px solid var(--border);border-radius:12px;padding:12px 16px;font-size:16px;box-shadow:0 6px 20px rgba(0,0,0,0.25)}}
.gpu b{{display:block;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:0.5px}}
table{{width:100%;border-collapse:collapse}}
th,td{{text-align:left;padding:10px 14px;border-bottom:1px solid var(--border);font-size:14px}}
th{{color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:0.5px;font-size:11px}}
.num{{text-align:right}}
tr:hover td{{background:rgba(79,156,255,0.04)}}
.footer{{color:var(--muted);font-size:11px;margin-top:24px;text-align:center}}
</style>
</head>
<body>
<div class="header">
  <img src="https://s3.hippius.com/kubetee-validator/brand/logo.svg" alt="KubeTEE"/>
  <span class="badge" style="background:rgba(62,233,143,0.12);color:{badge_color}">last update: {html.escape(str(badge))}</span>
</div>

<div class="panels-row">
  <div class="panel">
    <h2>Epoch</h2>
    <div class="metric">{epoch:,}</div>
    <div style="margin-top:10px;font-size:14px">usd_per_alpha: <span class="kv">${_fmt(usd_per_alpha)}</span></div>
    <div style="margin-top:6px;font-size:13px;color:var(--muted)">pricing: {pricing_source} · card: {card_source}</div>
  </div>
  <div class="panel">
    <h2>Hour pool (USD/hr)</h2>
    <div class="metric">${_fmt(total_pool / hours_per_epoch if hours_per_epoch > 0 else 0)}/hr</div>
    <div style="margin-top:10px;font-size:14px">Miner: <b>${_fmt(miner_usd / hours_per_epoch if hours_per_epoch > 0 else 0)}/hr</b> · Recycled: <b>${_fmt(owner_usd / hours_per_epoch if hours_per_epoch > 0 else 0)}/hr</b></div>
  </div>
  <div class="panel">
    <h2>Epoch pool (USD)</h2>
    <div class="metric">${_fmt(total_pool)}</div>
    <div style="margin-top:10px;font-size:14px">Miner earned: <b>${_fmt(miner_usd)}</b> · Recycled: <b>${_fmt(owner_usd)}</b></div>
  </div>
</div>

<div class="panel full">
  <h2>Pricing card (USD per GPU-hour)</h2>
  <div class="gpus">
{_card_chips}  </div>
</div>

<div class="panel full">
  <h2>Targon SN4 live payout (USD per card-hour) — {pricing_source}</h2>
  <div class="gpus">
{_targon_chips}  </div>
</div>

<div class="panel full">
  <h2>GPU inventory this cycle</h2>
  <div class="gpus">
{gpu_chips}  </div>
</div>

<div class="panel full">
  <h2>Per-miner payout (USD → alpha)</h2>
  <table>
    <thead><tr><th>UID</th><th>Cluster</th><th>Status</th><th>GPUs</th><th class="num">Target rate</th><th class="num">Earned rate</th><th class="num">Alpha/epoch</th><th class="num">Epoch payout</th><th class="num">% of pool</th></tr></thead>
    <tbody>
{rows}    </tbody>
  </table>
</div>

<div class="footer">Published from the subnet-owner validator via the public Hippius S3 bucket · {pub_str}</div>
</body>
</html>
"""


def build_dashboard_json(snapshot: dict) -> dict:
    """Build the per-cycle public snapshot for the dashboard JSON."""
    total_earned = float(snapshot.get("miner_usd", 0.0))
    owner_usd = float(snapshot.get("owner_usd", 0.0))
    total_pool = total_earned + owner_usd
    usd_per_alpha = float(snapshot.get("usd_per_alpha", 0.0))
    miners = []
    for m in snapshot.get("miners", []):
        usd = float(m.get("usd", 0.0))
        share = (usd / total_pool * 100) if total_pool > 0 else (100.0 if usd > 0 else 0.0)
        alpha = (usd / usd_per_alpha) if usd_per_alpha > 0 else 0.0
        miners.append({
            "uid": int(m.get("uid", 0)),
            "cluster_name": m.get("cluster_name"),
            "ready": bool(m.get("ready", False)),
            "gpus": list(m.get("gpus", [])),
            "usd": round(usd, 2),
            "alpha": round(alpha, 4),
            "share": round(share, 1),
        })
    return {
        "version": _DASHBOARD_VERSION,
        "epoch": int(snapshot.get("epoch", 0)),
        "tempo": int(snapshot.get("tempo", 360)),
        "usd_per_alpha": round(usd_per_alpha, 2),
        "card": dict(snapshot.get("card", {})),
        "effective_card": dict(snapshot.get("effective_card", {})),
        "miners": miners,
        "fleet_gpus": dict(snapshot.get("fleet_gpus", {})),
        "miner_usd": round(total_earned, 2),
        "owner_usd": round(owner_usd, 2),
        "total_pool_usd": round(total_pool, 2),
        "block": int(snapshot.get("block", 0)),
        "pricing_source": snapshot.get("pricing_source", ""),
        "card_source": snapshot.get("card_source", ""),
        "published_at": float(time.time()),
    }


def publish_dashboard(store, snapshot: dict) -> None:
    """PUT dashboard.json + a self-contained index.html (no JS needed)."""
    blob = build_dashboard_json(snapshot)
    store.put_json("dashboard.json", blob)
    html = build_html(snapshot)
    store.put_raw("index.html", html.encode("utf-8"), content_type="text/html; charset=utf-8")
