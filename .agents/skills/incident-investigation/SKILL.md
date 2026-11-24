---
name: incident-investigation
description: >-
  Use this skill when the user requests incident investigation, alert triage,
  outage analysis, error debugging, or connectivity troubleshooting
  (障害調査、アラート対応、不具合調査、サービス停止・エラー・疎通不良の原因調査)
  in the HomeNetwork infrastructure. Enforces strictly read-only diagnostics
  via repository files, monitoring endpoints, and SSH, and requires explicit
  user approval before any state-changing operation.
---

# 障害調査スキル (Incident Investigation)

HomeNetwork 環境で障害・アラート・エラー・疎通不良などの調査を依頼された際に使用する手順書です。
**調査は Read-Only（読み取り専用）に徹し、状態を変更する操作は必ず事前にユーザーの許可を得てから実施します。**

詳細やホスト・サービス一覧は [infrastructure-map.md](./references/infrastructure-map.md) を参照してください。

---

## 1. 絶対ルール（安全原則）

### 原則 1: 調査は Read-Only に厳密に限定する
- リポジトリ内の定義確認、外形監視・監視基盤の確認、および **SSH 経由の読み取り専用コマンド** のみで原因を切り分ける。
- 以下の操作は **調査フェーズでは一切実行しない**:
  - ファイルの作成・編集・追記・削除・リダイレクト（`>`, `>>`, `tee`, `sed -i`, `rm`, `mv`, `cp`, `touch`, `mkdir`, `chmod`, `chown` 等）
  - サービス・デーモンの起動 / 停止 / 再起動 / 設定リロード（`systemctl start/stop/restart/reload/enable/disable` 等）
  - コンテナの起動 / 停止 / 再作成 / 削除 / 状態を変更するコマンド実行（`docker compose up/down/restart`, `podman stop/rm/restart` 等）
  - VM 操作（`qm start/shutdown/reboot/stop` 等）
  - データベースの更新・削除・スキーマ変更（`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE` 等）
  - パッケージ操作（`apt update/install/upgrade/remove` 等）
  - 状態を変更する HTTP リクエスト（`POST`, `PUT`, `PATCH`, `DELETE` 等。例: AdGuard Home の保護切り替え API など）
  - 本番サーバーへ変更を加える可能性のある `ansible-playbook` の実行
- 秘密鍵、`env_file`、パスワード、Webhook URL などの **機密情報は表示・出力しない**（有無やパーミッションのみ確認する）。

### 原則 2: 状態変更が必要な場合は必ず事前許可を得る
調査のための暫定変更（ログレベル変更、切り分け用ファイルの配置など）、復旧作業（サービス再起動、コンテナ再作成、プロセス停止、キャッシュ削除など）、恒久修正が必要になった場合は、**実行前に必ずユーザーへ確認し、明示的な許可を得てから実施する。**

許可を求める際は、必ず以下を明示する:
1. **対象**: 対象サーバー、サービス名、コンテナ名、またはファイルパス
2. **実施内容**: 実行する具体的なコマンド、または変更内容の差分
3. **目的と影響**: 期待される効果、想定されるダウンタイム・副作用、ロールバック手順
4. **反映方法の選択**:
   - `AGENTS.md` の IaC 原則に従い **リポジトリ修正 → GitHub push → Jenkins デプロイ** で適用するか
   - 緊急復旧・切り分けのため **ユーザー許可のもと SSH で直接実施** するか（直接実施した場合、後続で IaC リポジトリへ反映する必要があるかも併せて提案する）

> [!CAUTION]
> ユーザーから明示的な許可を得るまで、状態変更を伴うコマンドやリポジトリ外への変更を実行しないでください。

---

## 2. SSH 接続ルール（Windows / PowerShell）

- **接続先指定**: 原則として `~/.ssh/config` のホストエイリアスを使用する（例: `home`, `db`, `watch`, `batch`, `pinpon`, `cicd`, `dns`, `dnsfilter`, `aquarium`, `proxmox`, `recorder`）。
- **フォールバック**: DNS 障害などで名前解決できない場合やエイリアスが使えない場合は、`inventory` または [infrastructure-map.md](./references/infrastructure-map.md) の IP アドレスと `./ssh_keys/id_ed25519` を指定する。
  - 例: `ssh -i ./ssh_keys/id_ed25519 -o BatchMode=yes -o ConnectTimeout=5 dns@10.0.0.2 'systemctl status dnsmasq --no-pager'`
- **安全な実行オプション**:
  - 対話プロンプトでハングしないよう、常に `-o BatchMode=yes -o ConnectTimeout=5` を付与する。
  - PowerShell から実行する際は、ローカル側での `$` 変数展開や引用符崩れを防ぐため、リモートコマンドは原則シングルクォート `'...'` で囲む。
  - root 権限が必要な参照は `sudo -n`（パスワードなしのみ実行）を使用し、パスワードを求められて失敗した場合は迂回・突破を試みず、参照できなかった範囲としてユーザーへ報告する。

---

## 3. 調査ワークフロー

### Step 1: 事象把握と構成確認（ローカル）
1. ユーザー報告から **症状・対象 URL / ホスト・発生時刻・エラーメッセージ・アラート内容** を整理する。
2. [infrastructure-map.md](./references/infrastructure-map.md) および関連ファイルを確認し、依存経路を特定する。
   - Nginx ルーティング: `home_server/nginx/sites-available/default`
   - アラートルール / 監視対象: `watch_server/docker/prometheus/rules.yml`, `watch_server/docker/prometheus/prometheus.yml`
   - 各サーバー構成: `<server>_server.yaml`, `dns_server/dnsmasq/dnsmasq.conf`, `dns_server/dnsmasq/dnsmasq-hosts`

### Step 2: 監視基盤・外形状態の Read-Only 確認
個別サーバーの深掘りの前に、まず監視情報や外形疎通で異常箇所を絞り込む。

- **WatchServer (`watch`) 経由でのアラート・ターゲット確認**:
  ```powershell
  ssh -o BatchMode=yes -o ConnectTimeout=5 watch 'docker ps --format "table {{.Names}}\t{{.Status}}"'
  ssh -o BatchMode=yes -o ConnectTimeout=5 watch 'curl -sS --max-time 5 http://localhost:9093/api/v2/alerts'
  ssh -o BatchMode=yes -o ConnectTimeout=5 watch 'curl -sS --max-time 5 http://localhost:9090/api/v1/alerts'
  ```
- **外形疎通確認（GET/HEAD のみ）**:
  ```powershell
  ssh -o BatchMode=yes -o ConnectTimeout=5 home 'curl -Ik -sS --max-time 5 https://dashboard.home.internal/'
  ```

### Step 3: 対象サーバーでの Read-Only 深掘り調査
特定したサーバーに対して、必要な観点の Read-Only コマンドのみを実行する。

#### 共通（OS・リソース・systemd）
```powershell
ssh -o BatchMode=yes -o ConnectTimeout=5 <host> 'uptime; free -h; df -h; systemctl --failed --no-pager'
ssh -o BatchMode=yes -o ConnectTimeout=5 <host> 'systemctl status <service> --no-pager'
ssh -o BatchMode=yes -o ConnectTimeout=5 <host> 'journalctl -u <service> -n 100 --no-pager'
```

#### Nginx / Web (`home`)
```powershell
ssh -o BatchMode=yes -o ConnectTimeout=5 home 'sudo -n tail -n 100 /var/log/nginx/error.log'
ssh -o BatchMode=yes -o ConnectTimeout=5 home 'ss -tulpn'
```

#### コンテナ（Podman: `cicd`, `dnsfilter` / Docker: `watch`, `db`）
```powershell
# Podman (rootful なサービスが多いため必要時は sudo -n を併用)
ssh -o BatchMode=yes -o ConnectTimeout=5 cicd 'sudo -n podman ps -a'
ssh -o BatchMode=yes -o ConnectTimeout=5 cicd 'sudo -n podman logs --tail 100 jenkins'

# Docker
ssh -o BatchMode=yes -o ConnectTimeout=5 watch 'docker logs --tail 100 alertmanager'
```

#### DNS / ネットワーク (`dns`, `dnsfilter`)
```powershell
ssh -o BatchMode=yes -o ConnectTimeout=5 dns 'systemctl status dnsmasq dhcp_web dhcp_assign_notifier --no-pager'
ssh -o BatchMode=yes -o ConnectTimeout=5 dns 'dig @127.0.0.1 home.internal +short'
ssh -o BatchMode=yes -o ConnectTimeout=5 dnsfilter 'dig @127.0.0.1 google.com +short'
```

#### DB (`db`, `batch`)
```powershell
# SELECT 等の読み取りクエリのみ実行する
ssh -o BatchMode=yes -o ConnectTimeout=5 db 'systemctl status postgresql --no-pager'
ssh -o BatchMode=yes -o ConnectTimeout=5 db 'sudo -n -u postgres psql -c "SELECT pid, usename, datname, state, wait_event_type, left(query, 80) FROM pg_stat_activity WHERE state != '\''idle'\'';"'
```

#### Proxmox VM 無応答時 (`proxmox` / `10.0.0.7`)
```powershell
ssh -o BatchMode=yes -o ConnectTimeout=5 root@10.0.0.7 'qm list'
```

### Step 4: 調査結果の整理と報告
以下の構成で簡潔・正確に報告する:
1. **事象と影響範囲**: どのサービス・ホストがどのような状態か
2. **観測した事実**: 実際に実行したコマンドの結果・ログ抜粋・タイムスタンプ（推測を含めない）
3. **原因（または有力仮説）**: 事実に基づく根本原因の分析と、未確認点があればその明記
4. **対応方針の提案**:
   - Read-Only 調査だけで完結する場合はその結論を報告
   - 状態変更（再起動、設定変更、IaC 修正等）が必要な場合は、**「原則 2」の 4 項目を提示してユーザーの許可を待つ**

### Step 5: 許可取得後の実施と復旧検証（許可された場合のみ）
1. ユーザーが許可した内容・範囲のみを実行する。
2. 実行後、Read-Only コマンド（`systemctl status`, `docker ps`, `journalctl`, `curl -I`, Alertmanager の解消確認等）で正常復旧を確認し、結果を報告する。
3. サーバー上で直接対処した場合は、`AGENTS.md` の IaC ルールとの整合性を保つため、リポジトリへの反映要否をユーザーに確認・案内する。

---

## 4. 操作可否の判断早見表

| 操作分類 | Read-Only（確認なしで実施可） | 状態変更（必ず事前許可が必要） |
| :--- | :--- | :--- |
| **情報・ログ参照** | `cat`, `head`, `tail`, `grep`, `less`, `ls`, `stat`, `journalctl`, `docker/podman logs` | リダイレクト (`>`, `>>`), `tee`, 一時ファイル作成 |
| **プロセス・サービス** | `ps`, `top -bn1`, `free`, `df`, `uptime`, `systemctl status/is-active`, `qm list` | `systemctl start/stop/restart/reload`, `kill`, `qm start/reboot` |
| **コンテナ** | `docker/podman ps`, `inspect`, `logs`, `stats --no-stream` | `up`, `down`, `restart`, `stop`, `rm`, `exec` での変更作業 |
| **NW・HTTP確認** | `ss`, `ip addr/route`, `ping -c 3`, `dig`, `curl -I` / `GET`（参照 API のみ） | `POST/PUT/DELETE` API 実行、FW/ルーティング変更 |
| **DB** | `SELECT`（状態参照・件数確認）, `\l`, `\dt`, `pg_stat_activity` | `INSERT`, `UPDATE`, `DELETE`, `VACUUM`, `ALTER`, DB 再起動 |
| **デプロイ・設定** | リポジトリ内ファイル閲覧、`git status/diff/log` | サーバー上の設定編集、`scp` 転送、`ansible-playbook` 実行 |
