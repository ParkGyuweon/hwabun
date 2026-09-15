pipeline {
    agent {
        node {
            label 'built-in'
            customWorkspace '/home/ubuntu/S15P21A306/deploy-workspace'
        }
    }

    options {
        timestamps()
        disableConcurrentBuilds()
    }

    parameters {
        booleanParam(
            name: 'DEPLOY_TO_EC2',
            defaultValue: false,
            description: 'CI 성공 후 EC2의 backend/shop-backend/mysql/recommend/prometheus/grafana를 배포합니다.'
        )
        booleanParam(
            name: 'LOAD_DB_SEED',
            defaultValue: false,
            description: '배포 후 shop_backend_seed.sql을 MySQL에 적용합니다. 데이터 변경 작업이므로 필요할 때만 선택합니다.'
        )
    }

    stages {
        stage('GitLab 연결 확인') {
            steps {
                sh '''
                    echo "Jenkins와 GitLab 연결 성공"
                    echo "현재 작업 디렉터리:"
                    pwd
                    echo "현재 브랜치:"
                    git branch --show-current
                    echo "현재 커밋:"
                    git log -1 --oneline
                '''
            }
        }

        stage('Backend 테스트') {
            when {
                anyOf {
                    changeset 'backend/**'
                    changeset 'Jenkinsfile'
                    expression { params.DEPLOY_TO_EC2 }
                }
            }
            steps {
                dir('backend') {
                    sh '''
                        chmod +x gradlew
                        ./gradlew clean test --no-daemon
                    '''
                }
            }
        }

        stage('Shop Backend 테스트') {
            when {
                anyOf {
                    changeset 'shop_backend/**'
                    changeset 'Jenkinsfile'
                    expression { params.DEPLOY_TO_EC2 }
                }
            }
            steps {
                dir('shop_backend') {
                    sh '''
                        chmod +x gradlew
                        ./gradlew clean test --no-daemon
                    '''
                }
            }
        }

        stage('Frontend Docker 빌드 검증') {
            when {
                anyOf {
                    changeset 'frontend/**'
                    changeset 'deploy/nginx.Dockerfile'
                    changeset 'Jenkinsfile'
                    expression { params.DEPLOY_TO_EC2 }
                }
            }
            steps {
                sh '''
                    docker build \
                      --target frontend-build \
                      -f deploy/nginx.Dockerfile \
                      -t s15p21a306-frontend-ci:${BUILD_NUMBER} \
                      .
                '''
            }
        }

        stage('EC2 구성 변경 감지') {
            when {
                anyOf {
                    changeset 'deploy/**'
                    changeset 'monitoring/**'
                    changeset 'batch/**'
                    changeset 'contracts/**'
                    changeset 'simulator/personas/data/**'
                    changeset 'simulator/feedback/**'
                    changeset 'Jenkinsfile'
                    expression { params.DEPLOY_TO_EC2 }
                }
            }
            steps {
                echo 'EC2 실행 구성 관련 변경이 감지되었습니다. 현재는 CI만 수행하며 배포하지 않습니다.'
            }
        }

        stage('EC2 배포') {
            when {
                expression { params.DEPLOY_TO_EC2 }
            }
            steps {
                sh '''
                    test -f /run/secrets/ec2-1.env
                    docker compose \\
                      -p ec2-1 \\
                      --env-file /run/secrets/ec2-1.env \\
                      -f deploy/ec2-1/docker-compose.yml \\
                      up -d --build \\
                      backend shop-backend mysql recommend prometheus grafana nginx
                '''
            }
        }

        stage('MySQL seed 적용') {
            when {
                allOf {
                    expression { params.DEPLOY_TO_EC2 }
                    expression { params.LOAD_DB_SEED }
                }
            }
            steps {
                sh '''
                    docker cp shop_backend/seed/shop_backend_seed.sql ec2-1-mysql-1:/tmp/shop_backend_seed.sql
                    docker exec ec2-1-mysql-1 sh -c 'mysql -u root -p"$MYSQL_ROOT_PASSWORD" shop_backend < /tmp/shop_backend_seed.sql'
                    docker exec ec2-1-mysql-1 rm -f /tmp/shop_backend_seed.sql
                '''
            }
        }
    }
}
