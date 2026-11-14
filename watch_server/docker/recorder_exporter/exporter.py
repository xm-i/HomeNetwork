#!/usr/bin/env python3
"""
Recorder Prometheus Exporter & Alert Notifier
Monitors EPGStation and Mirakurun for recording health, conflicts, drops, storage, and tuners.
Requires no external dependencies (uses Python standard library).
"""

import os
import sys
import time
import json
import logging
import threading
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("recorder-exporter")

# Configurations
EPGSTATION_URL = os.environ.get("EPGSTATION_URL", "http://recorder.internal:8888").rstrip("/")
MIRAKURUN_URL = os.environ.get("MIRAKURUN_URL", "http://recorder.internal:40772").rstrip("/")
EXPORTER_PORT = int(os.environ.get("PORT", "9876"))
SCRAPE_INTERVAL = int(os.environ.get("SCRAPE_INTERVAL", "15"))
WEBHOOK_URL = os.environ.get("ALERT_WEBHOOK_URL") or os.environ.get("SNMP_TRAP_WEBHOOK_URL", "")
STORAGE_LOW_THRESHOLD_GB = float(os.environ.get("STORAGE_LOW_THRESHOLD_GB", "100"))
STORAGE_USED_PERCENT_THRESHOLD = float(os.environ.get("STORAGE_USED_PERCENT_THRESHOLD", "95"))
STORAGE_REMIND_INTERVAL_SECONDS = int(os.environ.get("STORAGE_REMIND_INTERVAL_SECONDS", "86400"))
TUNER_FAULT_THRESHOLD_SECONDS = int(os.environ.get("TUNER_FAULT_THRESHOLD_SECONDS", "600"))
SERVICE_DOWN_THRESHOLD_SECONDS = int(os.environ.get("SERVICE_DOWN_THRESHOLD_SECONDS", "180"))

class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.metrics_text = ""
        self.last_update = 0
        self.status_summary = {}

        # Alert tracking state
        self.epg_up = True
        self.epg_down_since = None
        self.mirakurun_up = True
        self.mirakurun_down_since = None
        self.active_conflicts = 0
        self.faulty_tuners = set()
        self.tuner_fault_since = {}
        self.low_storages = set()
        self.last_drops_total = 0
        self.alert_cooldowns = {}

state = State()

def fetch_json(url, timeout=5):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "recorder-exporter/1.0", "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

def send_webhook(title, message, color_emoji=":warning:"):
    if not WEBHOOK_URL:
        return
    now_str = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    payload_text = f"{color_emoji} **{title}**\n**時刻**: {now_str}\n{message}"
    data = json.dumps({"text": payload_text}).encode("utf-8")
    req = urllib.request.Request(
        WEBHOOK_URL,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "recorder-exporter/1.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            logger.info("Webhook notification sent. HTTP %s", res.status)
    except Exception as e:
        logger.error("Failed to send webhook notification: %s", e)

def _check_service_status(service_name, service_url, is_up, up_attr, down_since_attr, now):
    """Track service downtime duration and notify only when down continuously past the threshold."""
    was_up = getattr(state, up_attr)
    down_since = getattr(state, down_since_attr)
    if not is_up:
        if down_since is None:
            setattr(state, down_since_attr, now)
            down_since = now
        if was_up and (now - down_since) >= SERVICE_DOWN_THRESHOLD_SECONDS:
            setattr(state, up_attr, False)
            minutes = SERVICE_DOWN_THRESHOLD_SECONDS // 60
            time_desc = f"{minutes}分" if minutes > 0 else f"{SERVICE_DOWN_THRESHOLD_SECONDS}秒"
            send_webhook(
                f"{service_name} 接続異常",
                f"{service_name} ({service_url}) への接続失敗が **{time_desc}以上継続** しています。",
                ":rotating_light:"
            )
    else:
        setattr(state, down_since_attr, None)
        if not was_up:
            setattr(state, up_attr, True)
            send_webhook(
                f"{service_name} 接続復旧",
                f"{service_name} ({service_url}) との接続が復旧しました。",
                ":white_check_mark:"
            )

def check_alerts(epg_data, mirakurun_data):
    now = time.time()

    # 1. Service Up / Down
    epg_up = epg_data.get("up", False)
    _check_service_status("EPGStation", EPGSTATION_URL, epg_up, "epg_up", "epg_down_since", now)

    m_up = mirakurun_data.get("up", False)
    _check_service_status("Mirakurun", MIRAKURUN_URL, m_up, "mirakurun_up", "mirakurun_down_since", now)

    # 2. Reserve Conflicts (録画競合・重複エラー)
    if epg_up:
        conflicts = epg_data.get("reserves", {}).get("conflicts", 0)
        if conflicts > 0 and state.active_conflicts == 0:
            state.active_conflicts = conflicts
            send_webhook(
                "録画予約競合 (Conflict) 発生！",
                f"チューナー不足または時間重複により、**{conflicts} 件**の予約が競合しています。予約確認を行ってください。",
                ":rotating_light:"
            )
        elif conflicts == 0 and state.active_conflicts > 0:
            state.active_conflicts = 0
            send_webhook("録画予約競合 解消", "予約競合が解消されました。全予約が正常に割り当てられています。", ":white_check_mark:")

    # 3. Tuners Fault / Unavailability
    # Mirakurun が正常に応答している場合のみ判定（一時的なスクレイプ失敗で状態がクリアされるのを防止）
    if mirakurun_data.get("up", False) and "tuners" in mirakurun_data:
        raw_faulty = set()
        for t in mirakurun_data.get("tuners", []):
            t_name = t.get("name", f"Tuner{t.get('index')}")
            if t.get("isFault", False) or not t.get("isAvailable", True):
                raw_faulty.add(t_name)

        # 異常が検知されたチューナーのタイマー開始 / 継続
        for t_name in raw_faulty:
            if t_name not in state.tuner_fault_since:
                state.tuner_fault_since[t_name] = now

        # 正常に戻ったチューナーのタイマー解除
        for t_name in list(state.tuner_fault_since.keys()):
            if t_name not in raw_faulty:
                del state.tuner_fault_since[t_name]

        # 閾値（デフォルト10分: 600秒）以上継続して異常なチューナーを抽出
        confirmed_faulty = {
            t_name for t_name, start_time in state.tuner_fault_since.items()
            if (now - start_time) >= TUNER_FAULT_THRESHOLD_SECONDS
        }

        # 新規に障害確定したチューナー（未通知のもの）
        new_faulty = confirmed_faulty - state.faulty_tuners
        # 復旧したチューナー（過去に通知済みだが、現在は raw_faulty にいないもの）
        recovered_faulty = state.faulty_tuners - raw_faulty

        if new_faulty:
            minutes = TUNER_FAULT_THRESHOLD_SECONDS // 60
            time_desc = f"{minutes}分" if minutes > 0 else f"{TUNER_FAULT_THRESHOLD_SECONDS}秒"
            send_webhook(
                "チューナー障害検知",
                f"以下のチューナーが **{time_desc}以上継続** して利用不可または故障状態です: `{', '.join(sorted(new_faulty))}`",
                ":rotating_light:"
            )
            state.faulty_tuners.update(new_faulty)

        if recovered_faulty:
            send_webhook(
                "チューナー復旧検知",
                f"以下のチューナーが正常復旧しました: `{', '.join(sorted(recovered_faulty))}`",
                ":white_check_mark:"
            )
            state.faulty_tuners.difference_update(recovered_faulty)

    # 4. Storage Low warning
    if epg_up:
        current_low = {}
        for s in epg_data.get("storages", []):
            name = s.get("name", "unknown")
            avail_gb = s.get("available", 0) / (1024 ** 3)
            pct = (s.get("used", 0) / s.get("total", 1)) * 100 if s.get("total", 0) > 0 else 0
            if avail_gb < STORAGE_LOW_THRESHOLD_GB or pct >= STORAGE_USED_PERCENT_THRESHOLD:
                current_low[name] = (avail_gb, pct)

        current_low_names = set(current_low.keys())
        new_low = current_low_names - state.low_storages
        recovered_low = state.low_storages - current_low_names

        if new_low:
            messages = [
                f"- `{name}` (残 {current_low[name][0]:.1f}GB / 使用率 {current_low[name][1]:.1f}%)"
                for name in new_low
            ]
            send_webhook(
                "録画ストレージ容量警告",
                f"ストレージ容量が閾値を下回りました:\n" + "\n".join(messages),
                ":warning:"
            )
            for name in new_low:
                state.alert_cooldowns[f"storage_{name}"] = now

        # 閾値を下回った状態が長期間継続している場合のリマインド通知
        if STORAGE_REMIND_INTERVAL_SECONDS > 0:
            remind_low = []
            for name in current_low_names - new_low:
                last_alert = state.alert_cooldowns.get(f"storage_{name}", 0)
                if now - last_alert >= STORAGE_REMIND_INTERVAL_SECONDS:
                    state.alert_cooldowns[f"storage_{name}"] = now
                    remind_low.append(name)

            if remind_low:
                messages = [
                    f"- `{name}` (残 {current_low[name][0]:.1f}GB / 使用率 {current_low[name][1]:.1f}%)"
                    for name in remind_low
                ]
                send_webhook(
                    "録画ストレージ容量警告 (継続リマインド)",
                    f"ストレージ容量が閾値を下回った状態が続いています:\n" + "\n".join(messages),
                    ":warning:"
                )

        if recovered_low:
            messages = [f"- `{name}`" for name in recovered_low]
            send_webhook(
                "録画ストレージ容量復旧",
                f"以下のストレージ容量が正常範囲に回復しました:\n" + "\n".join(messages),
                ":white_check_mark:"
            )
            for name in recovered_low:
                state.alert_cooldowns.pop(f"storage_{name}", None)

        state.low_storages = current_low_names

    # 5. Drop Packets Warning
    if m_up:
        current_drops = mirakurun_data.get("total_drops", 0)
        if current_drops > state.last_drops_total:
            diff = current_drops - state.last_drops_total
            # Rate-limit drop alerts to once every 10 minutes
            last_alert = state.alert_cooldowns.get("drop", 0)
            if now - last_alert > 600:
                state.alert_cooldowns["drop"] = now
                send_webhook(
                    "ストリームドロップ (パケット欠落) 検知",
                    f"現在録画/配信中のストリームで **{diff}** パケットのドロップが発生しました。(合計ドロップ: {current_drops})",
                    ":warning:"
                )
        state.last_drops_total = current_drops

def collect_metrics():
    while True:
        try:
            # 1. Fetch EPGStation data
            epg_data = {"up": False, "reserves": {}, "storages": [], "encode": {}, "recording": {}}
            try:
                fetch_json(f"{EPGSTATION_URL}/api/version")
                epg_data["recording"] = fetch_json(f"{EPGSTATION_URL}/api/recording?isHalfWidth=true")
                epg_data["reserves"] = fetch_json(f"{EPGSTATION_URL}/api/reserves/cnts")
                storages_res = fetch_json(f"{EPGSTATION_URL}/api/storages")
                epg_data["storages"] = storages_res.get("items", [])
                epg_data["encode"] = fetch_json(f"{EPGSTATION_URL}/api/encode?isHalfWidth=true")
                epg_data["recorded"] = fetch_json(f"{EPGSTATION_URL}/api/recorded?isHalfWidth=true&limit=5")
                epg_data["up"] = True
            except Exception as e:
                logger.warning("EPGStation scrape failed: %s", e)

            # 2. Fetch Mirakurun data
            mirakurun_data = {"up": False, "status": {}, "tuners": [], "total_drops": 0, "tuner_drops": {}}
            try:
                mirakurun_data["status"] = fetch_json(f"{MIRAKURUN_URL}/api/status")
                tuners = fetch_json(f"{MIRAKURUN_URL}/api/tuners")
                mirakurun_data["tuners"] = tuners

                total_drops = 0
                for t in tuners:
                    idx = t.get("index", 0)
                    t_drop = 0
                    for u in t.get("users", []):
                        for pid, pdata in u.get("streamInfo", {}).items():
                            t_drop += pdata.get("drop", 0)
                    mirakurun_data["tuner_drops"][idx] = t_drop
                    total_drops += t_drop
                mirakurun_data["total_drops"] = total_drops
                mirakurun_data["up"] = True
            except Exception as e:
                logger.warning("Mirakurun scrape failed: %s", e)

            # Check and fire alerts
            check_alerts(epg_data, mirakurun_data)

            # Build Prometheus metrics text
            lines = []

            # Service health
            lines.append("# HELP recorder_service_up Status of recorder backend services (1=UP, 0=DOWN)")
            lines.append("# TYPE recorder_service_up gauge")
            lines.append(f'recorder_service_up{{service="epgstation"}} {1 if epg_data["up"] else 0}')
            lines.append(f'recorder_service_up{{service="mirakurun"}} {1 if mirakurun_data["up"] else 0}')

            if epg_data["up"]:
                # EPGStation Recording
                rec_total = epg_data["recording"].get("total", 0)
                lines.append("# HELP epgstation_recording_count Number of currently recording programs")
                lines.append("# TYPE epgstation_recording_count gauge")
                lines.append(f"epgstation_recording_count {rec_total}")

                # EPGStation Reserves
                res_cnt = epg_data["reserves"]
                lines.append("# HELP epgstation_reserves_count Number of scheduled recordings by state")
                lines.append("# TYPE epgstation_reserves_count gauge")
                lines.append(f'epgstation_reserves_count{{type="normal"}} {res_cnt.get("normal", 0)}')
                lines.append(f'epgstation_reserves_count{{type="conflicts"}} {res_cnt.get("conflicts", 0)}')
                lines.append(f'epgstation_reserves_count{{type="skips"}} {res_cnt.get("skips", 0)}')
                lines.append(f'epgstation_reserves_count{{type="overlaps"}} {res_cnt.get("overlaps", 0)}')

                # EPGStation Storages
                lines.append("# HELP epgstation_storage_bytes Storage partition space metrics in bytes")
                lines.append("# TYPE epgstation_storage_bytes gauge")
                lines.append("# HELP epgstation_storage_used_percent Storage partition space used percentage")
                lines.append("# TYPE epgstation_storage_used_percent gauge")
                for s in epg_data["storages"]:
                    sname = s.get("name", "unknown")
                    total = s.get("total", 0)
                    used = s.get("used", 0)
                    avail = s.get("available", 0)
                    pct = (used / total * 100.0) if total > 0 else 0.0
                    lines.append(f'epgstation_storage_bytes{{name="{sname}",type="total"}} {total}')
                    lines.append(f'epgstation_storage_bytes{{name="{sname}",type="used"}} {used}')
                    lines.append(f'epgstation_storage_bytes{{name="{sname}",type="available"}} {avail}')
                    lines.append(f'epgstation_storage_used_percent{{name="{sname}"}} {pct:.2f}')

                # EPGStation Encode
                enc = epg_data["encode"]
                lines.append("# HELP epgstation_encode_count Number of encoding tasks")
                lines.append("# TYPE epgstation_encode_count gauge")
                lines.append(f'epgstation_encode_count{{status="running"}} {len(enc.get("runningItems", []))}')
                lines.append(f'epgstation_encode_count{{status="waiting"}} {len(enc.get("waitItems", []))}')

                # Recorded summary
                rec_summary = epg_data.get("recorded", {})
                rec_total_count = rec_summary.get("total", 0)
                lines.append("# HELP epgstation_recorded_total_count Total number of recorded programs")
                lines.append("# TYPE epgstation_recorded_total_count gauge")
                lines.append(f"epgstation_recorded_total_count {rec_total_count}")

                # Check for zero-byte recorded files in recent items
                zero_files = 0
                for item in rec_summary.get("records", []):
                    vfiles = item.get("videoFiles", [])
                    if not vfiles or any(vf.get("size", 1) == 0 for vf in vfiles):
                        zero_files += 1
                lines.append("# HELP epgstation_recorded_zero_size_recent Number of recent recorded programs with empty files")
                lines.append("# TYPE epgstation_recorded_zero_size_recent gauge")
                lines.append(f"epgstation_recorded_zero_size_recent {zero_files}")

            if mirakurun_data["up"]:
                # Mirakurun Status & Errors
                m_stat = mirakurun_data["status"]
                errors = m_stat.get("errorCount", {})
                lines.append("# HELP mirakurun_error_count Mirakurun cumulative error counters")
                lines.append("# TYPE mirakurun_error_count counter")
                for err_k, err_v in errors.items():
                    lines.append(f'mirakurun_error_count{{type="{err_k}"}} {err_v}')

                epg = m_stat.get("epg", {})
                lines.append("# HELP mirakurun_epg_stored_events Number of EPG events stored in Mirakurun")
                lines.append("# TYPE mirakurun_epg_stored_events gauge")
                lines.append(f'mirakurun_epg_stored_events {epg.get("storedEvents", 0)}')

                streams = m_stat.get("streamCount", {})
                lines.append("# HELP mirakurun_stream_count Active stream counts in Mirakurun")
                lines.append("# TYPE mirakurun_stream_count gauge")
                for st_k, st_v in streams.items():
                    lines.append(f'mirakurun_stream_count{{type="{st_k}"}} {st_v}')

                # Mirakurun Tuners
                lines.append("# HELP mirakurun_tuner_status Tuner state metrics (1=true, 0=false)")
                lines.append("# TYPE mirakurun_tuner_status gauge")
                lines.append("# HELP mirakurun_stream_drops_total Cumulative drop packets on active streams")
                lines.append("# TYPE mirakurun_stream_drops_total counter")
                lines.append(f'mirakurun_stream_drops_total {mirakurun_data["total_drops"]}')

                for t in mirakurun_data["tuners"]:
                    idx = t.get("index", 0)
                    tname = t.get("name", f"Tuner{idx}")
                    types_str = ",".join(t.get("types", []))
                    is_avail = 1 if t.get("isAvailable", False) else 0
                    is_using = 1 if t.get("isUsing", False) else 0
                    is_fault = 1 if t.get("isFault", False) else 0
                    user_cnt = len(t.get("users", []))
                    lbl = f'index="{idx}",name="{tname}",types="{types_str}"'

                    lines.append(f'mirakurun_tuner_status{{{lbl},state="available"}} {is_avail}')
                    lines.append(f'mirakurun_tuner_status{{{lbl},state="using"}} {is_using}')
                    lines.append(f'mirakurun_tuner_status{{{lbl},state="fault"}} {is_fault}')
                    lines.append(f'mirakurun_tuner_status{{{lbl},state="users"}} {user_cnt}')

                    t_drops = mirakurun_data["tuner_drops"].get(idx, 0)
                    lines.append(f'mirakurun_tuner_stream_drops{{index="{idx}",name="{tname}"}} {t_drops}')

            output_text = "\n".join(lines) + "\n"

            with state.lock:
                state.metrics_text = output_text
                state.last_update = time.time()
                state.status_summary = {
                    "updated_at": datetime.now(JST).isoformat(),
                    "epgstation_up": epg_data["up"],
                    "mirakurun_up": mirakurun_data["up"],
                    "recording_count": epg_data["recording"].get("total", 0) if epg_data["up"] else 0,
                    "conflicts": epg_data["reserves"].get("conflicts", 0) if epg_data["up"] else 0,
                    "total_drops": mirakurun_data["total_drops"] if mirakurun_data["up"] else 0
                }

        except Exception as e:
            logger.error("Error in metric collection loop: %s", e)

        time.sleep(SCRAPE_INTERVAL)

class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/metrics":
            with state.lock:
                content = state.metrics_text.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        elif self.path in ("/", "/health", "/status"):
            with state.lock:
                content = json.dumps(state.status_summary, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Suppress routine HTTP GET logging to prevent log noise
        pass

def main():
    logger.info("Starting recorder-exporter on port %d...", EXPORTER_PORT)
    logger.info("Target EPGStation: %s", EPGSTATION_URL)
    logger.info("Target Mirakurun: %s", MIRAKURUN_URL)
    if WEBHOOK_URL:
        logger.info("Alert webhook is enabled.")
    else:
        logger.info("No alert webhook configured.")

    collector_thread = threading.Thread(target=collect_metrics, daemon=True)
    collector_thread.start()

    # Wait a moment for first collection
    time.sleep(1)

    server = HTTPServer(("0.0.0.0", EXPORTER_PORT), MetricsHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down exporter.")
        server.server_close()

if __name__ == "__main__":
    main()
