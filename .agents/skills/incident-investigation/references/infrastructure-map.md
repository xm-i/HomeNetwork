# HomeNetwork インフラ構成マップ（障害調査リファレンス）

## 1. サーバー一覧（SSH 接続先・管理サービス）

ローカルからの SSH 接続は `~/.ssh/config` のエイリアスを優先し、名前解決不可時は IP と `./ssh_keys/id_ed25519` を使用します。

| エイリアス | FQDN | IP | SSH ユーザー | 主な稼働サービス / コンテナ | 主な設定・確認先 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `dns` | `dns-server.internal` | `10.0.0.2` | `dns` | `dnsmasq`, `dhcp_web` (:80), `dhcp_assign_notifier`, `prometheus-node-exporter` (:9100) | `/etc/dnsmasq.conf`, `/etc/dnsmasq-hosts`, `/var/lib/misc/dnsmasq.leases`, `/home/dns/services/` |
| `dnsfilter` | `dnsfilter.internal` | `10.0.3.8` | `dnsfilter` | `dnsfilter.service` (Podman: `dnsfilter` / AdGuard Home, `:3000`, `:53`), `prometheus-node-exporter` (:9100) | `/opt/dnsfilter/conf/AdGuardHome.yaml`, `/opt/dnsfilter/work/`, `/opt/dnsfilter/scripts/update_280blocker.py` |
| `home` | `home.internal` | `10.0.3.1` | `home` | `nginx` (:80/:443), `back_end_api` (:5000), `electric_power_monitor`, `home_automation`, `prometheus-node-exporter` (:9100) | `/etc/nginx/sites-available/default`, `/etc/nginx/certs/`, `/var/log/nginx/`, `/opt/back-end-api-service/`, `/var/www/html/dashboard` |
| `db` | `db-server.internal` | `10.0.3.2` | `db` | `postgresql` / `postgresql@*-main` (:5432), `prometheus-node-exporter` (:9100) | PostgreSQL ログ (`/var/log/postgresql/`), `db_server/docker/` |
| `watch` | `watch-server.internal` | `10.0.3.3` | `watch` | `docker.service` (Compose: `prometheus`:9090, `alertmanager`:9093, `grafana`:3000, `blackbox-exporter`:9115, `snmp-exporter`:9116, `snmptrapd`:162/udp, `recorder-exporter`:9876), `prometheus-node-exporter` (:9100) | `/home/watch/docker/` (`docker-compose.yml`, `prometheus/`, `alertmanager/`, `grafana/`) |
| `batch` | `batch-server.internal` | `10.0.3.5` | `batch` | `rundeckd` (:4440), `postgresql@*-main`, `prometheus-node-exporter` (:9100) | `/var/log/rundeck/` |
| `pinpon` | `pinpon-server.internal` | `10.0.3.6` | `pinpon` (Ansible: `root`) | `pinpon` (:5000, .NET 10), `prometheus-node-exporter` (:9100) | `/opt/pinpon/`, `journalctl -u pinpon` |
| `cicd` | `cicd.internal` | `10.0.3.7` | `cicd` | Podman 系 systemd: `jenkins` (:8080/:50000), `sonarqube` (:9000), `tailscale-funnel`, `prometheus-node-exporter` (:9100) | `/opt/jenkins/home`, `/opt/sonarqube/logs`, `/opt/tailscale/config/serve.json` |
| `recorder` | `recorder.internal` | `10.0.0.8` | `recorder` | EPGStation (:8888), Mirakurun (:40772) | `watch` 上の `recorder-exporter` 経由でも状態確認可 |
| `proxmox`（旧 `kvm`） | `proxmox.internal`（旧 `kvm-host.internal`） | `10.0.0.7` | `root` | Proxmox VE 9.2 ハイパーバイザ, `prometheus-node-exporter` (:9100) | `qm list`, `pct list`, `vmbr0`, Web UI (`https://pve.home.internal/` / `:8006`) |
| `aquarium` | `aqua-raspi.internal` | `10.0.0.11` | `pi` | `aqua_state_reporter`, `prometheus-node-exporter`（※現在監視アラート対象外） | `/home/pi/services/aqua_state_reporter/` |

### SSH 対象外の監視・ネットワーク・ストレージ機器（SNMP 監視）
- `rtx1210.internal` (`10.0.0.1`): Yamaha RTX1210 ルーター（SNMP ポーリング & トラップ）
- `xs708t.internal` (`10.0.0.3`): NETGEAR 10G L2 スイッチ（SNMP ポーリング & トラップ）
- `gs108pe.internal` (`10.0.0.4`): L2 スイッチ
- `nas.internal` (`10.0.0.5`) / `nas-management.internal` (`10.0.0.6`): ASUSTOR NAS（SNMP 監視・`rsync` バックアップ先）

---

## 2. HTTPS リバースプロキシ経路（`home` Nginx → バックエンド）

`home_server/nginx/sites-available/default` に基づく主要エンドポイントと転送先:

| URL | 転送先 / 実体 |
| :--- | :--- |
| `https://home.internal/` | `https://dashboard.home.internal/` へリダイレクト |
| `https://dashboard.home.internal/` | `home` 上の `/var/www/html/dashboard`（静的配信） |
| `https://dashboard-api.home.internal/` | `home` 上の `http://localhost:5000` (`back_end_api.service`) |
| `https://jenkins.home.internal/` | `http://cicd.internal:8080` (`jenkins.service`) |
| `https://sonarqube.home.internal/` | `http://cicd.internal:9000` (`sonarqube.service` / DB: `db-server.internal:5432`) |
| `https://monitor.home.internal/` / `https://grafana.home.internal/` | `http://watch-server.internal:3000` (`grafana` コンテナ) |
| `https://recorder.home.internal/`（および `:8888`） | `http://recorder.internal:8888` (EPGStation) |
| `https://rundeck.home.internal/` | `http://batch-server.internal:4440` (`rundeckd.service`) |
| `https://pinpon.home.internal/` | `http://pinpon-server.internal:5000` (`pinpon.service`) |
| `https://dnsfilter.home.internal/` | `http://dnsfilter.internal:3000` (`dnsfilter.service`) |
| `https://pve.home.internal/` | `https://proxmox.internal:8006` (Proxmox VE Web UI) |

※ 旧ドメイン `*.home-server.internal` は `https://<subdomain>.home.internal` へ `307` リダイレクトされます。

---

## 3. Prometheus アラートルール概要（`watch_server/docker/prometheus/rules.yml`）

- `HostDown`: `node_exporter` が 3 分以上応答なし（`aqua-raspi.internal` 除外）
- `SystemdServiceDown`: 主要 systemd ユニットが 2 分以上 `active` ではない
  - `home`: `nginx`, `back_end_api`, `home_automation`
  - `db`: `postgresql@*-main`
  - `dns`: `dnsmasq`, `dhcp_web`, `dhcp_assign_notifier`
  - `batch`: `rundeckd`, `postgresql@*-main`
  - `pinpon`: `pinpon`
  - `watch`: `docker`
  - `cicd`: `sonarqube`, `jenkins`, `tailscale-funnel`
  - `dnsfilter`: `dnsfilter`
- `HttpsEndpointDown`: Blackbox Exporter の HTTPS プローブが 3 分以上失敗
- `SslCertificateExpiringSoon`: TLS 証明書の残有効期限が 30 日未満
- `BlackboxExporterDown` / `RecorderExporterDown`: 各エクスポーターの取得失敗が 3 分以上継続

---

## 4. 事象別の初期切り分けポイント

1. **Web サービス (`*.home.internal`) にアクセスできない / 502・504**
   - `home` の `nginx` 状態・`/var/log/nginx/error.log`・証明書期限を確認
   - 転送先ホストの対象サービス / コンテナ稼働状態とポート待受 (`ss -tulpn`) を確認
2. **名前解決できない / ネットに繋がらない**
   - IP 直指定 (`10.0.0.2`) で `dns` の `dnsmasq` 状態・`/etc/dnsmasq-hosts` を確認
   - DHCP 動的クライアント経由の広告ブロック影響なら `dnsfilter` (`10.0.3.8`) の `dnsfilter.service` / Podman ログ・`AdGuardHome.yaml` を確認
3. **ホストごと疎通不可 (`HostDown`)**
   - `proxmox` (`10.0.0.7`, user: `root`) で `qm list` および `pct list` を確認し、VM / LXC 停止・ハングかネットワーク問題かを切り分け
4. **Jenkins Webhook が届かない / CI 失敗**
   - `cicd` の `jenkins.service` / `tailscale-funnel.service` と `podman logs`、SonarQube 利用時は `sonarqube.service` と `db` の PostgreSQL 疎通を確認
5. **録画異常・予約競合アラート**
   - `watch` の `recorder-exporter` ログ、および `recorder` (`10.0.0.8`) の EPGStation / Mirakurun 稼働状況・ストレージ残量を確認
