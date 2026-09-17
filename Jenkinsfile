pipeline {
    agent {
        node {
            label 'built-in'
            customWorkspace '/home/ubuntu/S15P21A306/deploy-workspace'
        }
    }

    environment {
        // Git 작업공간과 분리된 EC2-1 운영 환경 파일을 배포와 DW 초기화에 사용한다.
        EC2_ENV_FILE = '/home/ubuntu/S15P21A306/deploy/ec2-1/.env'
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
        booleanParam(
            name: 'INIT_DW_SCHEMA',
            defaultValue: false,
            description: 'EC2-1 MySQL의 dw 스키마를 최초 1회 생성하고 EC2-2 Spark 전용 계정을 부여합니다. 기존 dw가 있으면 안전을 위해 중단합니다.'
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

        stage('MySQL 스키마 마이그레이션') {
            when {
                expression { params.DEPLOY_TO_EC2 }
            }
            steps {
                sh '''
                    set -eu
                    # 모든 migration은 멱등 SQL이므로 커밋 diff와 무관하게 재적용한다.
                    # 이전 커밋에 포함된 migration이 아직 EC2에 적용되지 않은 경우도 보장한다.
                    migrations="$(find shop_backend/migrations -maxdepth 1 -type f -name '*.sql' | sort || true)"
                    if [ -z "$migrations" ]; then
                        echo '적용할 MySQL 마이그레이션이 없습니다.'
                        exit 0
                    fi

                    printf '%s\n' "$migrations" | sort | while IFS= read -r migration; do
                        target="/tmp/$(basename "$migration")"
                        echo "MySQL migration 적용: $migration"
                        docker cp "$migration" "ec2-1-mysql-1:$target"
                        docker exec ec2-1-mysql-1 sh -c \
                          'mysql -u root -p"$MYSQL_ROOT_PASSWORD" shop_backend < '"$target"
                        docker exec ec2-1-mysql-1 rm -f "$target"
                    done
                '''
            }
        }

        stage('EC2 배포') {
            when {
                expression { params.DEPLOY_TO_EC2 }
            }
            steps {
                sh '''
                    set -eu
                    test -f "$EC2_ENV_FILE"

                    # 최신 커밋이 merge 이후의 일반 커밋이면 HEAD^만 비교할 때
                    # merge에서 들어온 shop_backend 변경을 놓칠 수 있다. 최근 merge의
                    # 첫 부모부터 현재 HEAD까지 누적해 배포 대상 서비스를 계산한다.
                    latest_merge="$(git log -1 --merges --format='%H' 2>/dev/null || true)"
                    if [ -n "$latest_merge" ] && git rev-parse --verify "$latest_merge^1" >/dev/null 2>&1; then
                        changed="$(git diff --name-only "$latest_merge^1" HEAD)"
                    elif git rev-parse --verify HEAD^ >/dev/null 2>&1; then
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
                      --env-file "$EC2_ENV_FILE" \\
                      -f deploy/ec2-1/docker-compose.yml \\
                      up -d --build $services
                '''
            }
        }

        stage('DW 스키마 초기화') {
            when {
                allOf {
                    expression { params.DEPLOY_TO_EC2 }
                    expression { params.INIT_DW_SCHEMA }
                }
            }
            steps {
                sh '''
                    set -eu
                    # Jenkins sh의 기본 xtrace가 비밀 파일 값을 콘솔에 출력하지 않게 한다.
                    set +x
                    test -f "$EC2_ENV_FILE"
                    test -f contracts/dw/schema.sql
                    # 추천 서버 읽기 계정과 EC2-2 Spark 쓰기 계정을 분리한다.
                    set -a
                    . "$EC2_ENV_FILE"
                    set +a
                    : "${DW_MYSQL_USER:?Set DW_MYSQL_USER in EC2_ENV_FILE}"
                    : "${DW_MYSQL_PASSWORD:?Set DW_MYSQL_PASSWORD in EC2_ENV_FILE}"
                    : "${DW_MYSQL_WRITER_USER:?Set DW_MYSQL_WRITER_USER in EC2_ENV_FILE}"
                    : "${DW_MYSQL_WRITER_PASSWORD:?Set DW_MYSQL_WRITER_PASSWORD in EC2_ENV_FILE}"
                    : "${DW_MYSQL_WRITER_HOST:?Set DW_MYSQL_WRITER_HOST to EC2-2 private IP}"

                    # schema.sql의 CREATE TABLE은 재실행용이 아니다. 이미 DB가 있으면 기존 데이터를 보호한다.
                    if docker exec ec2-1-mysql-1 sh -c \
                      'mysql -N -u root -p"$MYSQL_ROOT_PASSWORD" -e "SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = '\''dw'\''"' \
                      | grep -qx 'dw'; then
                        echo 'dw 데이터베이스가 이미 있습니다. 기존 DW를 보호하기 위해 초기화를 중단합니다.' >&2
                        exit 1
                    fi

                    docker cp contracts/dw/schema.sql ec2-1-mysql-1:/tmp/dw-schema.sql
                    docker exec ec2-1-mysql-1 sh -c \
                      'mysql -u root -p"$MYSQL_ROOT_PASSWORD" < /tmp/dw-schema.sql'
                    docker exec ec2-1-mysql-1 rm -f /tmp/dw-schema.sql

                    # SQL 파일은 실행 직후 삭제한다. 작은따옴표는 SQL 방식으로 이스케이프한다.
                    sql_quote() { printf '%s' "$1" | sed "s/'/''/g"; }
                    reader_user="$(sql_quote "$DW_MYSQL_USER")"
                    reader_password="$(sql_quote "$DW_MYSQL_PASSWORD")"
                    writer_user="$(sql_quote "$DW_MYSQL_WRITER_USER")"
                    writer_password="$(sql_quote "$DW_MYSQL_WRITER_PASSWORD")"
                    writer_host="$(sql_quote "$DW_MYSQL_WRITER_HOST")"
                    grant_sql="$(mktemp)"
                    trap 'rm -f "$grant_sql"' EXIT
                    chmod 600 "$grant_sql"
                    cat > "$grant_sql" <<SQL
CREATE USER IF NOT EXISTS '$reader_user'@'%' IDENTIFIED BY '$reader_password';
ALTER USER '$reader_user'@'%' IDENTIFIED BY '$reader_password';
GRANT SELECT ON dw.* TO '$reader_user'@'%';
CREATE USER IF NOT EXISTS '$writer_user'@'$writer_host' IDENTIFIED BY '$writer_password';
ALTER USER '$writer_user'@'$writer_host' IDENTIFIED BY '$writer_password';
GRANT ALL PRIVILEGES ON dw.* TO '$writer_user'@'$writer_host';
FLUSH PRIVILEGES;
SQL
                    docker cp "$grant_sql" ec2-1-mysql-1:/tmp/dw-grant.sql
                    docker exec ec2-1-mysql-1 sh -c \
                      'mysql -u root -p"$MYSQL_ROOT_PASSWORD" < /tmp/dw-grant.sql'
                    docker exec ec2-1-mysql-1 rm -f /tmp/dw-grant.sql
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
