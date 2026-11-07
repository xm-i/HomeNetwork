#!/usr/bin/env python3
import csv
import datetime
import html
import json
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler

OUI_PATH = "/var/lib/myscripts/oui.csv"
LEASES_PATH = "/var/lib/misc/dnsmasq.leases"
PORT = 80

class OuiDatabase:
    def __init__(self, path):
        self.path = path
        self.mtime = 0
        self.oui_map = {}

    def load(self):
        if not os.path.exists(self.path):
            return
        mtime = os.path.getmtime(self.path)
        if mtime == self.mtime:
            return
        try:
            oui_map = {}
            with open(self.path, "r", encoding="utf-8", errors="ignore") as f:
                reader = csv.reader(f)
                for row in reader:
                    if len(row) >= 3:
                        assignment = row[1].strip().upper()
                        org_name = row[2].strip()
                        if assignment:
                            oui_map[assignment] = org_name
            self.oui_map = oui_map
            self.mtime = mtime
        except Exception as e:
            print(f"Error loading OUI database: {e}", file=sys.stderr)

    def lookup(self, mac):
        clean_mac = mac.replace(":", "").replace("-", "").upper()
        # 6文字, 7文字, 9文字のOUI対応
        for prefix_len in (9, 7, 6):
            prefix = clean_mac[:prefix_len]
            if prefix in self.oui_map:
                return self.oui_map[prefix]
        return "不明"

oui_db = OuiDatabase(OUI_PATH)

def get_leases():
    oui_db.load()
    leases = []
    if not os.path.exists(LEASES_PATH):
        return leases
    try:
        with open(LEASES_PATH, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 4:
                    raw_time, mac, ip, host = parts[0], parts[1], parts[2], parts[3]
                    client_id = parts[4] if len(parts) > 4 else "*"
                    try:
                        exp_time = datetime.datetime.fromtimestamp(int(raw_time)).strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        exp_time = raw_time
                    vendor = oui_db.lookup(mac)
                    leases.append({
                        "expiry": exp_time,
                        "mac": mac,
                        "ip": ip,
                        "host": host if host != "*" else "(unknown)",
                        "vendor": vendor,
                        "client_id": client_id
                    })
    except Exception as e:
        print(f"Error reading leases: {e}", file=sys.stderr)
    # IP順にソート (数値比較)
    def ip_key(item):
        try:
            return [int(p) for p in item["ip"].split(".")]
        except Exception:
            return [0, 0, 0, 0]
    leases.sort(key=ip_key)
    return leases

def render_html(leases):
    rows_html = ""
    for item in leases:
        rows_html += f"""
        <tr>
            <td><code>{html.escape(item['ip'])}</code></td>
            <td><strong>{html.escape(item['host'])}</strong></td>
            <td><code>{html.escape(item['mac'])}</code></td>
            <td>{html.escape(item['vendor'])}</td>
            <td>{html.escape(item['expiry'])}</td>
        </tr>
        """
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DHCP Leases - HomeNetwork</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: #f6f8fa;
            margin: 0;
            padding: 24px;
            color: #24292f;
        }}
        .container {{
            max-width: 1100px;
            margin: 0 auto;
            background: #ffffff;
            border: 1px solid #d0d7de;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
            padding: 24px;
        }}
        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid #d0d7de;
            padding-bottom: 16px;
            margin-bottom: 20px;
        }}
        h1 {{
            font-size: 20px;
            margin: 0;
        }}
        .badge {{
            background: #0969da;
            color: white;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 13px;
            font-weight: 600;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }}
        th, td {{
            padding: 10px 12px;
            text-align: left;
            border-bottom: 1px solid #d0d7de;
        }}
        th {{
            background-color: #f6f8fa;
            font-weight: 600;
            color: #57606a;
        }}
        tr:hover {{
            background-color: #f6f8fa;
        }}
        code {{
            background: #afb8c133;
            padding: 2px 6px;
            border-radius: 4px;
            font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
            font-size: 13px;
        }}
        .footer {{
            margin-top: 20px;
            text-align: right;
            font-size: 12px;
            color: #57606a;
        }}
        .refresh-btn {{
            background: #f6f8fa;
            border: 1px solid #d0d7de;
            padding: 6px 14px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
            font-weight: 500;
        }}
        .refresh-btn:hover {{
            background: #f3f4f6;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>DHCP リース一覧 (dnsmasq)</h1>
            <div>
                <span class="badge">{len(leases)} 機器接続中</span>
                <button class="refresh-btn" onclick="location.reload()">再読込</button>
            </div>
        </header>
        <table>
            <thead>
                <tr>
                    <th>IPアドレス</th>
                    <th>ホスト名</th>
                    <th>MACアドレス</th>
                    <th>ベンダー</th>
                    <th>有効期限</th>
                </tr>
            </thead>
            <tbody>
                {rows_html if rows_html else '<tr><td colspan="5" style="text-align:center; padding: 24px;">リース情報がありません</td></tr>'}
            </tbody>
        </table>
        <div class="footer">
            Powered by Python 3 Lightweight DHCP Viewer | HomeNetwork
        </div>
    </div>
</body>
</html>
"""

class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/leases":
            leases = get_leases()
            data = json.dumps(leases, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            leases = get_leases()
            content = render_html(leases).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

    def log_message(self, format, *args):
        # ログ出力抑制（必要に応じてstderrに出力）
        pass

def main():
    server_address = ("", PORT)
    httpd = HTTPServer(server_address, RequestHandler)
    print(f"Starting DHCP Lease Web Server on port {PORT}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()

if __name__ == "__main__":
    main()
