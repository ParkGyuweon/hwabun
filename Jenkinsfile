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
                    set -eu
                    test -f /run/secrets/ec2-1.env

                    # merge 커밋은 diff-tree 기본 동작이 변경 파일을 비워 둔다. 그러면
                    # 수동 배포가 "변경된 서비스 없음"으로 끝나므로, 첫 부모 대비 diff를
                    # 사용해 현재 배포 대상에 들어온 변경을 정확히 잡는다.
                    if git rev-parse --verify HEAD^ >/dev/null 2>&1; then
                        changed="$(git diff --name-only HEAD^ HEAD)"
                    else
                        changed="$(git diff-tree --no-commit-id --name-only -r HEAD)"
                    fi
                    services=""

                    if printf '%s\\n' "$changed" | grep -Eq '^(backend/|deploy/backend[.]Dockerfile$)'; then
                        services="$services backend"
                    fi
                    if printf '%s\\n' "$changed" | grep -Eq '^(shop_backend/|deploy/shop_backend[.]Dockerfile$)'; then
                        services="$services shop-backend"
                    fi
                    if printf '%s\\n' "$changed" | grep -Eq '^(frontend/|deploy/nginx[.]Dockerfile$|deploy/nginx/)'; then
                        services="$services nginx"
                    fi
                    if printf '%s\\n' "$changed" | grep -Eq '^(batch/|simulator/personas/data/|simulator/feedback/|deploy/recommend[.]Dockerfile$|deploy/recommend-entrypoint[.]sh$)'; then
                        services="$services recommend"
                    fi
                    if printf '%s\\n' "$changed" | grep -Eq '^monitoring/'; then
                        services="$services prometheus grafana"
                    fi
                    if printf '%s\\n' "$changed" | grep -Eq '^deploy/ec2-1/(docker-compose[.]yml|prometheus[.]yml|[.]env[.]example)$'; then
                        services="$services backend shop-backend mysql recommend prometheus grafana nginx"
                    fi
                    # Jenkinsfile 변경은 서비스 선택·Compose 실행 방식을 바꿀 수 있다.
                    # 수동 빌드에서는 HEAD 한 커밋만 보므로, 바로 전 Compose 변경이
                    # 누락되지 않게 전체 구성을 재적용한다.
                    if printf '%s\\n' "$changed" | grep -Eq '^Jenkinsfile$'; then
                        services="$services backend shop-backend mysql recommend prometheus grafana nginx"
                    fi

                    services="$(printf '%s\\n' "$services" | xargs -n1 | sort -u | tr '\\n' ' ')"
                    if [ -z "$(printf '%s' "$services" | tr -d ' ')" ]; then
                        echo '변경된 배포 대상 서비스가 없어 Docker 재빌드를 건너뜁니다.'
                        exit 0
                    fi

                    echo "변경된 서비스만 배포합니다:$services"
                    docker compose \\
                      -p ec2-1 \\
                      --env-file /run/secrets/ec2-1.env \\
                      -f deploy/ec2-1/docker-compose.yml \\
                      up -d --build $services
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
