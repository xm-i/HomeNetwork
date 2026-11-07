# 自宅ネットワーク環境構築

Ansibleを使いネットワークまわりの設定を行う。

# 前提手順

## DNS兼DHCP Server (dns-server)

1. KVMゲストを作成し、Ubuntuをインストールする（ユーザー名: `dns`、ホスト名: `dns-server`）。
2. ネットワーク設定を行う。
    - IPアドレスは `10.0.0.2/20`（Gateway: `10.0.0.1`、DNS: `1.1.1.1, 8.8.8.8`）で固定しておく。
    - 公開鍵認証で `dns` ユーザーにログインできるようにする。
        - `dns-server` の `~/.ssh/authorized_keys` に公開鍵を保存する。
        - Ansibleを実行する側の `./dns_server/ssh_keys/dns_server.key` に秘密鍵を保存する。(OpenSSH形式)

## DHCP通知用設定

SlackにDHCP割当通知を行うための設定を行う。

1. SlackでAppとそのIncoming Webhook URLを生成しておく。
2. Ansibleを実行する側の

    ```
    ./dns_server/services/dhcp_assign_notifier/constants_default.py
    ```

    を

    ```
    ./dns_server/services/dhcp_assign_notifier/constants.py
    ```

    にコピーして、WEBHOOK_URLに投稿先SlackのIncoming Webhook URLを代入する。

## アクアリウム用Raspi

1. 以下のものを準備する。
    - DHT22(AM2302)
    - DS18B20
    - 4.7KΩ抵抗2つ
1. 組み立てる。  
    ![curcuit-diagram](aquarium/circuit-diagram/circuit-diagram.png)
1. Raspbianをインストールする
1. bootディレクトリにsshという名前の空ファイルを作成し、SSH接続できるようにする。
1. bootディレクトリに無線LAN接続用にwpa_supplicant.confを用意する。

    ``` config
    country=JP
    ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
    update_config=1
    network={
        ssid="{{ssid}}"
        psk="{{pw}}"
    }
    ```

1. bootディレクトリのconfig.txtに一行追記する

    ``` config
    dtoverlay=w1-gpio-pullup,gpiopin=4
    ```

1. ネットワーク設定を行う。
    - 公開鍵認証でpiユーザーにログインできるようにする。
        - RaspberryPiの/.ssh/authorized_keysに公開鍵を保存する。
        - Ansibleを実行する側の./aquarium/ssh_keys/aquapi.keyに秘密鍵を保存する。(OpenSSH形式)

# KVMゲストたち

1. ゲストを作ってUbuntu20.04をインストールする。
1. SSH接続出来るよう公開鍵を登録する。
1. この手順をHomeServer,DbServer,WatchServerの4つ分やっておく

# 実行 (初回のみ。2回目以降はGitHubにpushするとJenkinsが実施してくれる。)

```
sh execute.sh
```

# Ansible実行後にやること

- アクアリウム用Raspiで、以下のコマンドを実行

    ```
    git clone https://github.com/adafruit/Adafruit_Python_DHT.git
    cd Adafruit_Python_DHT
    sudo python3 setup.py install
    ```

- Jenkinsにパイプライン構築
- jenkinsでデプロイ、ansible実行が出来るよう、HomeServerのknown_hostsにfingerprintを登録していく

    ```
    su jenkins
    ssh 10.0.0.2
    ssh home-server.internal
    ssh aquaraspi.internal
    ssh dns-server.internal
    ssh ...全ホストやる
    ```

# KVM Hostのネットワーク設定

- ゲストのネットワークをブリッジする必要があるので以下を実行する。

    ```
    nmcli con add type bridge ifname for-kvm0
    nmcli con modify bridge-for-kvm0 bridge.stp no
    nmcli con modify bridge-for-kvm0 ipv4.method manual ipv4.address "10.0.0.7/20" ipv4.gateway "10.0.0.1" ipv4.dns "10.0.0.2"
    nmcli con add type bridge-slave ifname enp2s0 master bridge-for-kvm0
    nmcli con del netplan-enp2s0
    ```
# 監視サーバー (WatchServer)

Prometheus + Grafana + Node Exporter によるインフラメトリクス監視。

- **URL**: `http://monitor.home-server.internal/` (または `http://grafana.home-server.internal/`)
- **初期アカウント**: `admin` / `admin`
- **ダッシュボード**: 「Nodes Overview」が自動プロビジョニングされ、全サーバーのCPU・メモリ・ディスク・NW状態が一覧確認可能
- **監視対象ノード**:
  - watch-server (監視サーバー自身)
  - home-server (Web / Nginx / Jenkins)
  - db-server (PostgreSQL)
  - batch-server
  - dns-server.internal (10.0.0.2 / DNS & DHCP)
  - aqua-raspi (アクアリウムIoT)
  - rtx1210 (10.0.0.1 / ルーター / SNMPポーリング & トラップ監視)
  - xs708t (10.0.0.3 / 10G L2スイッチ / ポートトラフィック監視)
  - nas (10.0.0.5 / ASUSTOR NAS / CPU・メモリ・温度・ディスク健康状態監視)
  - recorder (10.0.0.8 / EPGStation & Mirakurun / 録画健全性・予約競合・チューナードロップ監視)

## 録画サーバー監視 (Recorder / EPGStation & Mirakurun)

WatchServer 内の `recorder-exporter` コンテナが `recorder.internal` (10.0.0.8) の EPGStation および Mirakurun からメトリクスを自動収集します。

- **Grafanaダッシュボード**: 「Recorder / 録画監視 (EPGStation & Mirakurun)」
- **主な監視項目**:
  - **EPGStation / Mirakurun 死活監視**: プロセスが正常に応答しているか (UP / DOWN)
  - **録画中番組数**: リアルタイムの録画実行数
  - **予約競合 (Conflict)**: チューナー枯渇や重複等による録画スキップ・衝突の有無 (**赤色アラート**)
  - **ストリームドロップ (Drops)**: リアルタイム受信ストリームのパケット欠落数 (アンテナ・受信状況の健全性)
  - **チューナー状態 (PX-MLT5)**: 5チューナーそれぞれの利用可否 (`available`)、使用中 (`using`)、故障検知 (`fault`)
  - **ストレージ容量・使用率**: 録画保存先 (`recorded`) および一時録画領域 (`recording`) の残容量と使用率 (残100GB未満/95%以上で警告)
  - **Mirakurunエラー・ストリーム**: バッファオーバーフロー、チューナーデバイス再起動回数、アクティブストリーム数
- **Webhook通知**:
  - `watch_server/docker/env_file` の `ALERT_WEBHOOK_URL` (または `SNMP_TRAP_WEBHOOK_URL`) を設定すると、予約競合発生時、チューナー障害時、ストレージ容量低下時、サービスダウン時に Discord / Slack へ即時アラート通知が送信されます。

## ネットワーク機器・NASのSNMP設定

### 1. RTX1210 (ルーター)
RTX1210 にログインし、`administrator` コマンドで管理者モードに入ってから以下を実行します。

```text
administrator
(パスワード入力)

# 監視サーバー (10.0.3.3) に対するSNMP許可とコミュニティ名
snmp host 10.0.3.3 public
snmpv2c host 10.0.3.3 public

# SNMPトラップ送信先と有効化
snmp trap host 10.0.3.3 public
snmpv2c trap host 10.0.3.3 public
snmp trap enable snmp all
snmp trap enable switch default all

# 設定保存
save
```

### 2. L2 Switch (XS708T)
Web管理画面（またはCLI）から以下を設定します：
- **SNMP**: 有効（Version 2c）
- **Read-Only コミュニティ名**: `public`
- **Trap レシーバー**: IP `10.0.3.3`、Port `162`、Community `public`
- **Trap イベント**: リンクダウン、再起動、ループ検知等にチェック

### 3. ASUSTOR NAS
ADM（管理画面）の「サービス」→「SNMP」から以下を設定します：
- **SNMPサービスを有効化**: チェック
- **バージョン**: v1 / v2c
- **コミュニティ**: `public`
- **SNMPトラップを有効化**:
  - トラップサーバーIP: `10.0.3.3`
  - コミュニティ: `public`

※ Discord / Slack へのトラップ通知を行いたい場合は、`./watch_server/docker/env_file` の `SNMP_TRAP_WEBHOOK_URL` に Webhook URL を設定してください。
