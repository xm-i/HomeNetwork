properties([
  disableConcurrentBuilds(),
  pipelineTriggers([githubPush()])
])

node {
  def sshCredentialsId = '02c7532f-3df9-4393-bddb-eca365b6fef9'
  try{
    stage('CheckOut'){
      checkout([$class: 'GitSCM', branches: [[name: '*/master']], doGenerateSubmoduleConfigurations: false, extensions: [], submoduleCfg: [], userRemoteConfigs: [[url: 'https://github.com/xm-i/HomeNetwork']]])
    }

    stage('Configuration'){
      configFileProvider([configFile(fileId: 'a387649d-770b-40b3-8863-8dc851c476a0', targetLocation: 'dns_server/services/dhcp_assign_notifier/constants.py')]) {}
      configFileProvider([configFile(fileId: 'c2d55a3f-ec4b-45c3-8b3f-ff15ed21ba3f', targetLocation: 'group_vars/home.yaml')]) {}
      configFileProvider([configFile(fileId: '937aec52-0ffe-4840-b3a8-f725ce16b8ec', targetLocation: 'group_vars/db.yaml')]) {}
      configFileProvider([configFile(fileId: '00822a4e-2506-42a6-ab2f-320c805c8cdc', targetLocation: 'group_vars/watch.yaml')]) {}
      configFileProvider([configFile(fileId: '1ac1e035-f68a-4f76-bda0-17a5e8cb9892', targetLocation: 'group_vars/batch.yaml')]) {}
      configFileProvider([configFile(fileId: '7261e61a-8049-4b23-88cd-59cc328c41c5', targetLocation: 'group_vars/pinpon.yaml')]) {}
      configFileProvider([configFile(fileId: '08db25be-824e-4efb-8883-f9a0c9a39827', targetLocation: 'group_vars/cicd.yaml')]) {}
      configFileProvider([configFile(fileId: '60dd20c7-4ea3-49b6-a4b4-e60d63ba82bc', targetLocation: 'home_server/nginx/certs/_wildcard.home-server.internal+1.pem')]) {}
      configFileProvider([configFile(fileId: 'bfaba23a-ed00-44f7-b5bc-d324931b9203', targetLocation: 'home_server/nginx/certs/_wildcard.home-server.internal+1-key.pem')]) {}
      configFileProvider([configFile(fileId: 'd7188f02-d5be-4135-8275-8b1d34fbd2e9', targetLocation: 'home_server/nginx/certs/_wildcard.home.internal+1.pem')]) {}
      configFileProvider([configFile(fileId: 'e0a983d0-7952-4c93-bc16-894370672f91', targetLocation: 'home_server/nginx/certs/_wildcard.home.internal+1-key.pem')]) {}
      configFileProvider([configFile(fileId: '67930ad9-94b3-45a8-b9e4-f0bc43890e3c', targetLocation: 'watch_server/docker/env_file')]) {}
      // configFileProvider([configFile(fileId: '175e94a1-29f4-4133-a270-b42f8cb6a7b8', targetLocation: 'watch_server/docker/zabbix-server/env_file')]) {}
      // configFileProvider([configFile(fileId: '0deaffda-78a8-4e02-86ad-1d963b074f72', targetLocation: 'watch_server/docker/zabbix-web/env_file')]) {}
    }
    stage('Ansible dns_server'){
      ansiblePlaybook credentialsId: sshCredentialsId, inventory: 'inventory_jenkins', limit: 'dns', playbook: 'playbook.yaml'
    }

    stage('Ansible dnsfilter_server'){
      ansiblePlaybook credentialsId: sshCredentialsId, inventory: 'inventory_jenkins', limit: 'dnsfilter', playbook: 'playbook.yaml'
    }

    stage('Ansible home_server'){
      ansiblePlaybook credentialsId: sshCredentialsId, inventory: 'inventory_jenkins', limit: 'home', playbook: 'playbook.yaml'
    }

    stage('Ansible aquarium_raspi'){
      ansiblePlaybook credentialsId: sshCredentialsId, inventory: 'inventory_jenkins', limit: 'aquarium', playbook: 'playbook.yaml'
    }

    stage('Ansible db_server'){
      ansiblePlaybook credentialsId: sshCredentialsId, inventory: 'inventory_jenkins', limit: 'db', playbook: 'playbook.yaml'
    }

    stage('Ansible watch_server'){
      ansiblePlaybook credentialsId: sshCredentialsId, inventory: 'inventory_jenkins', limit: 'watch', playbook: 'playbook.yaml'
    }

    stage('Ansible batch_server'){
      ansiblePlaybook credentialsId: sshCredentialsId, inventory: 'inventory_jenkins', limit: 'batch', playbook: 'playbook.yaml'
    }

    stage('Ansible pinpon_server'){
      ansiblePlaybook credentialsId: sshCredentialsId, inventory: 'inventory_jenkins', limit: 'pinpon', playbook: 'playbook.yaml'
    }

    stage('Ansible cicd_server'){
      ansiblePlaybook credentialsId: sshCredentialsId, inventory: 'inventory_jenkins', limit: 'cicd', playbook: 'playbook.yaml'
    }

    stage('Notify Slack'){
      slackSend(
        color: 'good',
        message: "Ansible実行が完了しました。"
      )
    }
  }catch( Exception e ) {
      slackSend(
        color: 'danger',
        message: "Ansible実行に失敗しました。"
      )
  }
}
