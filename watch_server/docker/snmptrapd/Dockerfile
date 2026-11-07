FROM alpine:3.20

RUN apk add --no-cache net-snmp net-snmp-tools python3 tzdata

ENV TZ=Asia/Tokyo

WORKDIR /app

COPY snmptrapd.conf /etc/snmp/snmptrapd.conf
COPY notify.py /app/notify.py

EXPOSE 162/udp

# -f: フォアグラウンド実行
# -Lo: 標準出力へログ出力
# -C -c /etc/snmp/snmptrapd.conf: 指定した設定ファイルのみ読み込む
# -M ... -m ALL: MIBファイルを読み込んでOIDを名前解決
CMD ["snmptrapd", "-f", "-Lo", "-C", "-c", "/etc/snmp/snmptrapd.conf", "-M", "/usr/share/snmp/mibs:/etc/snmp/mibs", "-m", "ALL"]
