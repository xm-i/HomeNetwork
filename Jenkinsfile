node {
  try{
    stage('CheckOut'){
      checkout([$class: 'GitSCM', branches: [[name: '*/master']], doGenerateSubmoduleConfigurations: false, extensions: [], submoduleCfg: [], userRemoteConfigs: [[url: 'https://github.com/southernwind/HomeNetwork']]])
    }

    stage('Configuration'){
      configFileProvider([configFile(fileId: 'a387649d-770b-40b3-8863-8dc851c476a0', targetLocation: 'raspi_dhcp/services/dhcp_assign_notifier/constants.py')]) {}
      configFileProvider([configFile(fileId: 'c2d55a3f-ec4b-45c3-8b3f-ff15ed21ba3f', targetLocation: 'group_vars/home.yaml')]) {}
      configFileProvider([configFile(fileId: '937aec52-0ffe-4840-b3a8-f725ce16b8ec', targetLocation: 'group_vars/db.yaml')]) {}
      configFileProvider([configFile(fileId: '00822a4e-2506-42a6-ab2f-320c805c8cdc', targetLocation: 'group_vars/watch.yaml')]) {}
      configFileProvider([configFile(fileId: '1ac1e035-f68a-4f76-bda0-17a5e8cb9892', targetLocation: 'group_vars/batch.yaml')]) {}
      configFileProvider([configFile(fileId: '007d1ea8-f543-45a2-b446-b52b3af1a3c5', targetLocation: 'home_server/nginx/sites-available/external')]) {}
      configFileProvider([configFile(fileId: '07960749-1250-4882-8653-b3127500f143', targetLocation: 'db_server/docker/mariadb/env_file')]) {}
      configFileProvider([configFile(fileId: 'f8b32646-b514-45e4-8871-df5aa7d403b6', targetLocation: 'db_server/copy/root/.my.cnf')]) {}
      configFileProvider([configFile(fileId: '67930ad9-94b3-45a8-b9e4-f0bc43890e3c', targetLocation: 'watch_server/docker/env_file')]) {}
      // configFileProvider([configFile(fileId: '175e94a1-29f4-4133-a270-b42f8cb6a7b8', targetLocation: 'watch_server/docker/zabbix-server/env_file')]) {}
      // configFileProvider([configFile(fileId: '0deaffda-78a8-4e02-86ad-1d963b074f72', targetLocation: 'watch_server/docker/zabbix-web/env_file')]) {}
    }
    stage('Ansible home_server'){
      ansiblePlaybook credentialsId: 'a03bad98-9a5c-4855-b3a9-27e120a90447', inventory: 'inventory_jenkins', limit: 'home', playbook: 'playbook.yaml'
    }

    stage('Ansible aquarium_raspi'){
      ansiblePlaybook credentialsId: '84abccbc-f317-430f-be13-ea3d41b7e713', inventory: 'inventory_jenkins', limit: 'aquarium', playbook: 'playbook.yaml'
    }

    stage('Ansible db_server'){
      ansiblePlaybook credentialsId: 'cac5742e-58df-4e7b-9f34-dc04c160aa4b', inventory: 'inventory_jenkins', limit: 'db', playbook: 'playbook.yaml'
    }

    stage('Ansible watch_server'){
      ansiblePlaybook credentialsId: 'fbab430f-02f2-47f2-82e6-e32b266a3abb', inventory: 'inventory_jenkins', limit: 'watch', playbook: 'playbook.yaml'
    }

    stage('Ansible batch_server'){
      ansiblePlaybook credentialsId: '1f4f3d15-c26b-4d2e-86a7-def517f966b3', inventory: 'inventory_jenkins', limit: 'batch', playbook: 'playbook.yaml'
    }

    stage('Ansible raspi_dhcp'){
      ansiblePlaybook credentialsId: 'b27d104d-bfbf-4381-9945-539905a7392e', inventory: 'inventory_jenkins', limit: 'dhcp', playbook: 'playbook.yaml'
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