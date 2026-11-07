#!/usr/bin/env python3
import sys
import os
import json
import urllib.request
from datetime import datetime

# デフォルトでWebhook通知をスキップするパターン（大文字小文字無視・部分一致）
DEFAULT_IGNORE_PATTERNS = [
    # NAS (ASUSTOR等) の定期的なストレージ使用量計算完了通知
    "storage usage calculating is complete",
]

def get_ignore_patterns():
    patterns = list(DEFAULT_IGNORE_PATTERNS)
    env_patterns = os.environ.get("SNMP_TRAP_IGNORE_PATTERNS", "")
    if env_patterns:
        for p in env_patterns.split(","):
            p = p.strip()
            if p:
                patterns.append(p)
    return patterns

def check_ignore(trap):
    """
    受信したトラップが無視対象パターンに合致するか判定する。
    合致した場合は (True, マッチしたパターン文字列) を返す。
    """
    patterns = get_ignore_patterns()
    if not patterns:
        return False, None

    candidates = []
    candidates.extend(trap.get("raw_lines", []))
    for k, v in trap.get("varbinds", {}).items():
        candidates.append(f"{k} = {v}")

    for text in candidates:
        text_lower = text.lower()
        for pattern in patterns:
            if pattern.lower() in text_lower:
                return True, pattern

    return False, None

def parse_trap():
    lines = [line.strip() for line in sys.stdin if line.strip()]
    if not lines:
        return None

    # snmptrapd passes:
    # 1st line: hostname / IP
    # 2nd line: transport info (e.g. UDP: [10.0.0.1]:51234->[0.0.0.0]:162)
    # 3rd+ lines: variable bindings (<OID> <value>)
    host = lines[0] if len(lines) > 0 else "unknown"
    transport = lines[1] if len(lines) > 1 else ""
    varbinds = {}

    for line in lines[2:]:
        parts = line.split(None, 1)
        if len(parts) == 2:
            oid, val = parts
            varbinds[oid] = val
        elif len(parts) == 1:
            varbinds[parts[0]] = ""

    return {
        "host": host,
        "transport": transport,
        "varbinds": varbinds,
        "raw_lines": lines
    }

def get_trap_title_and_icon(trap_oid):
    trap_str = str(trap_oid).lower()
    if "coldstart" in trap_str:
        return ":rotating_light:", "機器再起動検知 (ColdStart - 電源再投入)"
    elif "warmstart" in trap_str:
        return ":warning:", "機器再起動検知 (WarmStart)"
    elif "linkdown" in trap_str:
        return ":red_circle:", "インターフェース切断 (LinkDown)"
    elif "linkup" in trap_str:
        return ":large_green_circle:", "インターフェース復旧 (LinkUp)"
    elif "auth" in trap_str and "fail" in trap_str:
        return ":warning:", "SNMP認証失敗 (Authentication Failure)"
    elif "loopdetect" in trap_str or "loop" in trap_str:
        return ":no_entry:", "ネットワークループ検知 (Loop Detect)"
    elif "disk" in trap_str or "smart" in trap_str or "raid" in trap_str or "volume" in trap_str:
        return ":skull_and_crossbones:", "ストレージ・ディスク異常検知"
    elif "ups" in trap_str or "battery" in trap_str:
        return ":battery:", "UPS / バッテリー異常検知"
    elif "fanlock" in trap_str or "fan" in trap_str:
        return ":warning:", "ファン異常検知"
    elif "overtemp" in trap_str or "temperature" in trap_str:
        return ":fire:", "温度異常検知"
    elif "power" in trap_str or "psu" in trap_str:
        return ":zap:", "電源モジュール異常検知"
    else:
        return ":bell:", f"SNMPトラップ受信 ({trap_oid})"

def main():
    trap = parse_trap()
    if not trap:
        print("[snmptrapd-notify] Empty trap received")
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    host = trap["host"]
    varbinds = trap["varbinds"]

    # 代表的なOIDの抽出
    trap_oid = varbinds.get("SNMPv2-MIB::snmpTrapOID.0", varbinds.get("snmpTrapOID.0", "Unknown"))
    uptime = varbinds.get("DISMAN-EVENT-MIB::sysUpTimeInstance", varbinds.get("SNMPv2-MIB::sysUpTime.0", ""))

    icon, title = get_trap_title_and_icon(trap_oid)

    # ログ出力
    print(f"[{now}] Trap from {host}: {trap_oid}")
    for k, v in varbinds.items():
        print(f"  {k} = {v}")

    # フィルタリング判定
    ignored, matched_pattern = check_ignore(trap)
    if ignored:
        print(f"[snmptrapd-notify] Ignored trap by filter pattern: '{matched_pattern}' (skipping webhook)")
        return

    # Webhook 送信
    webhook_url = os.environ.get("SNMP_TRAP_WEBHOOK_URL")
    if not webhook_url:
        print("[snmptrapd-notify] SNMP_TRAP_WEBHOOK_URL is not set. Skipping webhook notification.")
        return

    details = []
    if uptime:
        details.append(f"稼働時間: {uptime}")

    for k, v in varbinds.items():
        if k in ("SNMPv2-MIB::snmpTrapOID.0", "snmpTrapOID.0", "DISMAN-EVENT-MIB::sysUpTimeInstance", "SNMPv2-MIB::sysUpTime.0"):
            continue
        details.append(f"{k} = {v}")

    detail_str = "\n".join(details)
    message_text = (
        f"{icon} **{title}**\n"
        f"**発生時刻**: {now}\n"
        f"**送信元ホスト**: `{host}`\n"
        f"**Trap OID**: `{trap_oid}`\n"
    )
    if detail_str:
        message_text += f"\n```text\n{detail_str}\n```"

    payload = json.dumps({"text": message_text}).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            print(f"[snmptrapd-notify] Webhook notification sent. Status: {response.status}")
    except Exception as e:
        print(f"[snmptrapd-notify] Failed to send webhook: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
