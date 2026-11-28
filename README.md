# 自宅ネットワーク環境構築

Ansibleを使いネットワークまわりの設定を行う。

# 前提手順

## DNS兼DHCP Server (dns-server)

1. Proxmox VMを作成し、Ubuntuをインストールする（ユーザー名: `dns`、ホスト名: `dns-server`）。
2. ネットワーク設定を行う。
    - IPアドレスは `10.0.0.2/20`（Gateway: `10.0.0.1`、DNS: `1.1.1.1, 8.8.8.8`）で固定しておく。
    - 公開鍵認証で `dns` ユーザーにログインできるようにする。
        - `dns-server` の `~/.ssh/authorized_keys` に全サーバー共通の公開鍵を保存する。
        - Ansibleを実行する側の `./ssh_keys/id_ed25519` に秘密鍵を保存する。(OpenSSH形式・全サーバー共通)

## DNS Filter Server (dnsfilter.internal / 現行実装: AdGuard Home)

1. Proxmox VMを作成し、Ubuntuをインストールする（ユーザー名: `dnsfilter`、ホスト名: `dnsfilter`）。
2. ネットワーク設定を行う。
    - IPアドレスは `10.0.3.8/20`（Gateway: `10.0.0.1`、DNS: `10.0.0.2`）で固定しておく。
    - 公開鍵認証で `dnsfilter` ユーザーにログインできるようにする（全サーバー共通の公開鍵を `~/.ssh/authorized_keys` に保存）。
3. （任意）NAS (`nas.internal`) 側に設定バックアップ用の rsync モジュール `dnsfilter_backup` を作成する。
4. （再構築時など）MACアドレスが変わった場合は `dns_server/dnsmasq/dnsmasq.conf` の `# DNSFilter-Server` の `dhcp-host` 行を更新する。

### DNS 振り分け・運用・一時解除

- **DNS 配り分けルール (`dnsmasq.conf`)**:
  - `dhcp-host` に登録済みの固定IP端末 (`known`): `10.0.0.2`（`dnsmasq` 直結／広告ブロックなし）
  - `dhcp-host` 未登録の動的DHCP端末 (`!known`: スマホ等) および `set:dnsfilter` を付与した端末: `10.0.3.8`（DNS フィルタ／広告ブロックあり）
  - `.internal` ドメインおよびプライベート逆引き (`10.x.x.x`) は `10.0.0.2` へフォワードされます。
- **280blocker の自動更新**:
  - `update_280blocker.py` が毎日 05:15 に当月（未公開時は前月）の `280blocker_domain_ag_YYYYMM.txt` を取得し、変更時のみ反映します。
- **設定の永続化 (方式 X)**:
  - 現行バックエンド（AdGuard Home）の `dnsfilter_server/config/AdGuardHome.yaml` は初回のみ配置 (`force: no`) されるため、Web UI 上で追加したホワイトリスト等の変更は Ansible で上書きされません。設定ディレクトリ `/opt/dnsfilter/conf/` は毎日 13:45 に NAS へ `rsync` バックアップされます。
- **広告ブロックの手軽な一時解除**:
  - **Web UI**: `https://dnsfilter.home.internal/` の「保護を無効化」から時間指定（1分 / 10分 / 1時間等）で一時停止できます（自動復帰、`blocked_response_ttl: 10` 秒のため解除後すぐ効きます）。
  - **ワンタップAPI（iOS ショートカット等向け）**: 以下のリクエストを投げると 5 分間（`300000` ms）だけ停止し、自動で再開します。
    ```text
    POST https://dnsfilter.home.internal/control/protection
    Content-Type: application/json
    Body: {"enabled": false, "duration": 300000}
    ```
    ※ 端末に mkcert CA を入れていない場合は `http://dnsfilter.internal:3000/control/protection` を使用してください。また、Web UI で認証パスワードを設定した場合は Basic 認証ヘッダを付与してください。

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
        - RaspberryPiの `~/.ssh/authorized_keys` に全サーバー共通の公開鍵を保存する。
        - Ansibleを実行する側の `./ssh_keys/id_ed25519` に秘密鍵を保存する。(OpenSSH形式・全サーバー共通)

# Proxmox VMたち

1. ゲストを作ってUbuntu20.04をインストールする。
1. SSH接続出来るよう全サーバー共通の公開鍵を `~/.ssh/authorized_keys` に登録する（ローカルからAnsibleを実行する場合は `./ssh_keys/id_ed25519` に共通秘密鍵を配置する）。
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
- jenkinsでデプロイ、ansible実行が出来るよう、JenkinsServerのknown_hostsにfingerprintを登録していく

    ```
    su jenkins
    ssh 10.0.0.2
    ssh home.internal
    ssh aquaraspi.internal
    ssh dns-server.internal
    ssh ...全ホストやる
    ```

# GitHub Webhook 連携 (Tailscale Funnel)

`jenkins.internal` 上の `tailscale-funnel.service`（Tailscale userspace-networking / systemd）により、`/github-webhook/` のみを HTTPS で外部公開し、`http://127.0.0.1:8080/github-webhook/` へ転送します。RTX1210 のポート開放は不要で、Jenkins 管理画面は外部非公開のまま複数リポジトリで単一の Webhook URL を共用できます。

### 1. Tailscale 側の事前設定
1. Tailscale 管理画面の **DNS** で **MagicDNS** と **HTTPS Certificates** を有効化します。
2. **Access Controls** で Funnel が許可されていることを確認します（デフォルト ACL で許可済み）。
3. **Settings → Keys → Generate auth key** で **Reusable** な Auth Key を発行します（必要に応じて Pre-approved を有効化）。

### 2. `group_vars/jenkins.yaml` に Auth Key を設定
ローカルの `group_vars/jenkins.yaml` および Jenkins の Managed Files（`08db25be-824e-4efb-8883-f9a0c9a39827`）に以下を追記してからデプロイします：

```yaml
tailscale:
  authkey: "tskey-auth-xxxxxxxxxxxx"
  # hostname: "jenkins-webhook"  # 省略時は jenkins-webhook
```

※ 初回起動後、Tailscale 管理画面の **Machines** で `jenkins-webhook` ノードの **Disable key expiry** を有効化しておくと 180 日ごとの鍵失効を防げます。

### 3. Jenkins 側の設定
- GitHub Plugin を利用します。セキュリティのため **Manage Jenkins → System → GitHub → Advanced → Shared secret** に Webhook Secret を登録してください（GitHub 側の Secret と一致させます）。
- キックしたい各ジョブ（`HomeNetwork` や別リポジトリのジョブ）の設定で **「GitHub hook trigger for GITScm polling」** を有効化してください（Jenkins の CSRF 保護は無効化不要です）。

### 4. GitHub 各リポジトリの Webhook 設定
リポジトリの **Settings → Webhooks → Add webhook** から以下を設定します：
- **Payload URL**: `https://jenkins-webhook.<tailnet>.ts.net/github-webhook/`（末尾の `/` 必須。正確なホスト名は Tailscale 管理画面の Machines で確認）
- **Content type**: `application/json`
- **Secret**: Jenkins 側に設定した Shared secret と同じ値
- **Which events**: `Just the push event`

別リポジトリからも同じ Payload URL を指定すれば、Jenkins の GitHub Plugin がリポジトリ URL に基づき該当ジョブへ自動振り分けします。

### 5. （任意）旧設定の片付け
Jenkins Managed Files の旧 `external`（`007d1ea8-f543-45a2-b446-b52b3af1a3c5`）や `group_vars/home.yaml` の `ddns` 項目は不要になったため任意で削除できます。

# Proxmox VE ホスト (`proxmox.internal` / `10.0.0.7`)

- 仮想化基盤は **Proxmox VE 9.2**（ASRock DeskMini B760 / ブリッジ `vmbr0` / IP: `10.0.0.7/20`, GW: `10.0.0.1`, DNS: `10.0.0.2`）。
- Web UI: `https://pve.home.internal/`（Nginx 経由）または `https://10.0.0.7:8006/`。
- `ElectricPowerMonitor` へ電力監視用 FTDI USB UART（`0403:6001`）を LXC デバイスパススルー接続（Unprivileged LXC 作成後に Proxmox ホスト上で設定）:
  ```bash
  pct set <CTID> -dev0 /dev/ttyUSB0,gid=20,mode=0660
  pct reboot <CTID>
  ```
- 監視のため Proxmox ホストに `prometheus-node-exporter` を導入しています（`apt update && apt install -y prometheus-node-exporter`）。

# 監視サーバー (WatchServer)

Prometheus + Grafana + Node Exporter によるインフラメトリクス監視。

- **URL**: `https://monitor.home.internal/` (または `https://grafana.home.internal/`)
- **初期アカウント**: `admin` / `admin`
- **ダッシュボード**: 「Nodes Overview」が自動プロビジョニングされ、全サーバーのCPU・メモリ・ディスク・NW状態が一覧確認可能
- **監視対象ノード**:
  - proxmox.internal (10.0.0.7 / Proxmox VE ハイパーバイザ)
  - watch-server (監視サーバー自身)
  - home.internal (10.0.3.1 / Web リバースプロキシ & フロントエンド)
  - dashboard-ap.internal (10.0.3.9 / Dashboard API)
  - electric-power-monitor.internal (10.0.3.10 / 電力監視)
  - home-automation.internal (10.0.3.11 / ホームオートメーション)
  - db-server (PostgreSQL)
  - batch-server
  - dns-server.internal (10.0.0.2 / DNS & DHCP)
  - pinpon-server (10.0.3.6 / Pinpon Web サービス)
  - jenkins.internal (10.0.3.7 / Jenkins / Tailscale Funnel)
  - sonarqube.internal (10.0.3.12 / SonarQube)
  - dnsfilter.internal (10.0.3.8 / DNS フィルタ・AdGuard Home)
  - aqua-raspi (アクアリウムIoT ※現在アラート対象外)
  - rtx1210 (10.0.0.1 / ルーター / SNMPポーリング & トラップ監視)
  - xs708t (10.0.0.3 / 10G L2スイッチ / ポートトラフィック監視)
  - nas (10.0.0.5 / ASUSTOR NAS / CPU・メモリ・温度・ディスク健康状態監視)
  - recorder (10.0.0.8 / EPGStation & Mirakurun / 録画健全性・予約競合・チューナードロップ監視)
  - `*.home.internal` 各 HTTPS エンドポイント (Blackbox Exporter による外形・TLS 証明書期限監視)

## 死活・サービス停止アラート (Prometheus + Alertmanager)

`watch_server/prometheus/rules.yml` および `watch_server/alertmanager/alertmanager.yml` により、以下の異常検知と復旧通知を Slack へ送信します。

- **通知先**: `watch_server/env_file` の `ALERT_WEBHOOK_URL`（未設定時は `SNMP_TRAP_WEBHOOK_URL` にフォールバック）
- **主なアラートルール**:
  - `HostDown`: `node` ジョブの `up == 0` が 3 分継続（`aqua-raspi.internal` 除外）
  - `SystemdServiceDown`: `nginx` / `jenkins` / `tailscale-funnel` / `back_end_api` / `electric_power_monitor` / `home_automation` / `postgresql` / `dnsmasq` / `dhcp_web` / `dhcp_assign_notifier` / `rundeckd` / `pinpon` / `prometheus` / `prometheus-alertmanager` / `grafana-server` / `prometheus-blackbox-exporter` / `prometheus-snmp-exporter` / `snmptrapd` / `recorder-exporter` / `sonarqube` / `dnsfilter` の停止（2 分継続）
  - `HttpsEndpointDown`: Nginx 配下全 `*.home.internal` の HTTPS プローブ失敗（3 分継続）
  - `SslCertificateExpiringSoon`: TLS 証明書の残り有効期限が 30 日未満
  - `BlackboxExporterDown` / `RecorderExporterDown`: 各エクスポーターの取得失敗（3 分継続）

## 録画サーバー監視 (Recorder / EPGStation & Mirakurun)

WatchServer 内の `recorder-exporter` サービスが `recorder.internal` (10.0.0.8) の EPGStation および Mirakurun からメトリクスを自動収集します。

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
  - `watch_server/env_file` の `ALERT_WEBHOOK_URL` (または `SNMP_TRAP_WEBHOOK_URL`) を設定すると、予約競合発生時、全チューナー利用不可時、ストレージ容量低下時、サービスダウン時に Discord / Slack へアラート通知が送信されます。

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

※ Discord / Slack へのトラップ通知を行いたい場合は、`./watch_server/env_file` の `SNMP_TRAP_WEBHOOK_URL` に Webhook URL を設定してください。
