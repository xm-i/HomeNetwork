# 自宅ネットワーク環境構築

Ansibleを使いネットワークまわりの設定を行う。

# 前提手順

## DNS兼DHCP Server

1. Raspbianをインストールする。
2. bootディレクトリにsshという名前の空ファイルを作成し、SSH接続できるようにする。
3. ネットワーク設定を行う。
    - IPアドレスは 10.0.0.2で固定しておく  
        /etc/dhcpcd.confに以下を追記してreboot。

        ```
        interface eth0
        static ip_address=10.0.0.2/20
        static routers=10.0.0.1
        static domain_name_servers=8.8.8.8,2001:4860:4860::8888
        static ip6_address=fe80::ae44:f2ff:fe70:3874/64
        ```

    - 公開鍵認証でpiユーザーにログインできるようにする。
        - RaspberryPiの/.ssh/authorized_keysに公開鍵を保存する。
        - Ansibleを実行する側の./raspi_dhcp/ssh_keys/raspberrypi.keyに秘密鍵を保存する。(OpenSSH形式)

## DHCP通知用設定

SlackにDHCP割当通知を行うための設定を行う。

1. SlackでAppとそのIncoming Webhook URLを生成しておく。
2. Ansibleを実行する側の

    ```
    ./raspi_dhcp/services/dhcp_assign_notifier/common/constants_default.py
    ```

    を

    ```
    ./raspi_dhcp/services/dhcp_assign_notifier/common/constants.py
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
    ssh home-server.localnet
    ssh aquaraspi.localnet
    ssh raspi.localnet
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

- **URL**: `http://monitor.home-server.localnet/` (または `http://grafana.home-server.localnet/`)
- **初期アカウント**: `admin` / `admin`
- **ダッシュボード**: 「Nodes Overview」が自動プロビジョニングされ、全サーバーのCPU・メモリ・ディスク・NW状態が一覧確認可能
- **監視対象ノード**:
  - watch-server (監視サーバー自身)
  - home-server (Web / Nginx / Jenkins)
  - db-server (PostgreSQL)
  - batch-server
  - raspi.localnet (10.0.0.2 / DNS & DHCP)
  - aqua-raspi (アクアリウムIoT)
