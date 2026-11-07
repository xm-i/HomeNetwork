import urllib.request, json, time, csv, os
from constants import *

class Row():
    def __init__(self, line): 
        s = line.strip().split()
        self.time = s[0]
        self.mac = s[1]
        self.ip = s[2]
        self.host = s[3]
        self.id = s[4] if len(s) > 4 else "*"

    def get_vendorname(self, vendor_list):
        m = self.mac.replace(":","").upper()
        return next((v.organization_name for v in vendor_list if m.startswith(v.assignment)), "不明")

class Vendor():
    def __init__(self, csvrow):
        self.registry = csvrow[0]
        self.assignment = csvrow[1]
        self.organization_name = csvrow[2]
        self.organization_address = csvrow[3] if len(csvrow) > 3 else ""

def json_post(url, data):
    request = urllib.request.Request(url, json.dumps(data).encode("utf-8"), {"Content-Type" : "application/json"}, method="POST")
    response = urllib.request.urlopen(request)
    return response

def get_vendor_list():
    oui_path = "/var/lib/myscripts/oui.csv"
    if not os.path.exists(oui_path):
        return []
    with open(oui_path, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.reader(f)
        return [Vendor(csvrow) for csvrow in reader if len(csvrow) >= 3]

def read_leases(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8", errors="ignore") as file:
        return [line for line in file.readlines() if len(line.strip().split()) >= 4]

def main():
    vendor_list = get_vendor_list()
    before = None
    while True:
        if not vendor_list:
            vendor_list = get_vendor_list()
        path = "/var/lib/misc/dnsmasq.leases"
        lines = read_leases(path)
        time.sleep(1)
        lines_check = read_leases(path)
        
        # 不一致の場合、読み取り失敗の可能性があるため、読み込み直す
        if lines != lines_check:
            continue

        # 前回との差分を求める
        now = [Row(line) for line in lines]
        if before is not None:
            added = [nr for nr in now if nr.mac not in [br.mac for br in before]]
            removed = [br for br in before if br.mac not in [nr.mac for nr in now]]
            text = ""
            if len(removed) != 0:
                text += ":zzz:DHCP割当解除通知\n" + "\n".join([f"```Host={r.host}\nVendor={r.get_vendorname(vendor_list)}\nIP={r.ip}\nMAC={r.mac}```" for r in removed])

            if len(added) != 0:
                if len(text) != 0:
                    text += "\n\n"
                text += ":sunny:DHCP割当通知\n" + "\n".join([f"\n```Host={a.host}\nVendor={a.get_vendorname(vendor_list)}\nIP={a.ip}\nMAC={a.mac}```" for a in added])
            
            if len(text) != 0:
                json_post(WEBHOOK_URL, data={"text": text})
        before = now
        time.sleep(1)


if __name__ == "__main__":
    main()
