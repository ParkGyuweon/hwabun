pipeline {
    agent {
        node {
            label 'built-in'
            customWorkspace '/home/ubuntu/S15P21A306/deploy-workspace'
        }
    }

    environment {
        // Git 작업공간과 분리된 EC2-1 운영 환경 파일을 애플리케이션 배포에 사용한다.
        EC2_ENV_FILE = '/home/ubuntu/S15P21A306/deploy/ec2-1/.env'
        // 헬스체크 curl은 Jenkins 컨테이너에서 실행된다. EC2 호스트의 접근 가능한 주소를 사용한다.
        NGINX_HEALTH_RESOLVE_IP = '172.26.8.48'
    }

    options {
        timestamps()
        disableConcurrentBuilds()
    }

    parameters {
        booleanParam(
            name: 'DEPLOY_TO_EC2',
            defaultValue: false,
            description: '변경 경로를 자동 판별해 EC2 서비스를 배포합니다. 특정 서비스만 배포하려면 아래 항목을 선택하세요.'
        )
        booleanParam(
            name: 'DEPLOY_FRONTEND',
            defaultValue: false,
            description: '프론트엔드(Nginx)만 재빌드·재기동합니다.'
        )
        booleanParam(
            name: 'DEPLOY_BACKEND',
            defaultValue: false,
            description: '수집 백엔드(backend)만 재빌드·재기동합니다.'
        )
        booleanParam(
            name: 'DEPLOY_SHOP_BACKEND',
            defaultValue: false,
            description: '쇼핑 백엔드(shop-backend)만 재빌드·재기동합니다. 재기동 전에 멱등 마이그레이션(deploy/ec2-1/apply-shop-migrations.sh)을 먼저 적용하고, 실패하면 재기동하지 않습니다. MySQL 컨테이너는 재시작하지 않습니다.'
        )
        booleanParam(
            name: 'DEPLOY_RECOMMEND',
            defaultValue: false,
            description: '추천 서버(recommend)만 재빌드·재기동합니다.'
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
                    expression { params.DEPLOY_BACKEND }
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
                    expression { params.DEPLOY_SHOP_BACKEND }
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
                    expression { params.DEPLOY_FRONTEND }
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
                anyOf {
                    expression { params.DEPLOY_TO_EC2 }
                    expression { params.DEPLOY_FRONTEND }
                    expression { params.DEPLOY_BACKEND }
                    expression { params.DEPLOY_SHOP_BACKEND }
                    expression { params.DEPLOY_RECOMMEND }
                }
            }
            steps {
                sh '''
                    set -eu
                    test -f "$EC2_ENV_FILE"

                    services=""
                    # 수동 선택은 코드 변경 경로와 관계없이 정확히 해당 서비스만 배포한다.
                    if [ "${DEPLOY_FRONTEND}" = "true" ]; then
                        services="$services nginx"
                    fi
                    if [ "${DEPLOY_BACKEND}" = "true" ]; then
                        services="$services backend"
                    fi
                    if [ "${DEPLOY_SHOP_BACKEND}" = "true" ]; then
                        services="$services shop-backend"
                    fi
                    if [ "${DEPLOY_RECOMMEND}" = "true" ]; then
                        services="$services recommend"
                    fi

                    # 최신 커밋이 merge 이후의 일반 커밋이면 HEAD^만 비교할 때
                    # merge에서 들어온 shop_backend 변경을 놓칠 수 있다. 최근 merge의
                    # 첫 부모부터 현재 HEAD까지 누적해 배포 대상 서비스를 계산한다.
                    if [ "${DEPLOY_TO_EC2}" = "true" ]; then
                        latest_merge="$(git log -1 --merges --format='%H' 2>/dev/null || true)"
                        if [ -n "$latest_merge" ] && git rev-parse --verify "$latest_merge^1" >/dev/null 2>&1; then
                            changed="$(git diff --name-only "$latest_merge^1" HEAD)"
                        elif git rev-parse --verify HEAD^ >/dev/null 2>&1; then
                            changed="$(git diff --name-only HEAD^ HEAD)"
                        else
                            changed="$(git diff-tree --no-commit-id --name-only -r HEAD)"
                        fi

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
                            services="$services backend shop-backend recommend prometheus grafana nginx"
                        fi
                        # Jenkinsfile 변경은 서비스 선택·Compose 실행 방식을 바꿀 수 있다.
                        # 수동 빌드에서는 HEAD 한 커밋만 보므로, 바로 전 Compose 변경이
                        # 누락되지 않게 전체 구성을 재적용한다.
                        if printf '%s\\n' "$changed" | grep -Eq '^Jenkinsfile$'; then
                            services="$services backend shop-backend recommend prometheus grafana nginx"
                        fi
                    fi

                    services="$(printf '%s\\n' "$services" | xargs -n1 | sort -u | tr '\\n' ' ')"
                    if [ -z "$(printf '%s' "$services" | tr -d ' ')" ]; then
                        echo '변경된 배포 대상 서비스가 없어 Docker 재빌드를 건너뜁니다.'
                        exit 0
                    fi

                    # MySQL은 Jenkins 자동 배포에서 절대 대상으로 삼지 않는다.
                    # 서비스 계산 로직이 바뀌어 mysql이 포함되면 배포 전에 실패시킨다.
                    if printf '%s\\n' "$services" | tr ' ' '\\n' | grep -Fxq 'mysql'; then
                        echo 'MySQL은 Jenkins 배포 대상이 아닙니다. DB 컨테이너는 변경하지 않습니다.' >&2
                        exit 1
                    fi

                    echo "변경된 서비스만 배포합니다:$services"

                    # 되돌리기용: 지금 돌고 있는 이미지를 <이미지>:previous 로 남긴다 (실패해도 배포는 계속)
                    bash deploy/ec2-1/deploy-helpers.sh tag-previous $services || true

                    # shop-backend 는 ddl-auto: validate 라 컬럼이 없으면 뜨지 않는다. 다시 띄우기 전에
                    # 멱등 마이그레이션을 먼저 적용한다. 실패하면 set -e 로 여기서 멈추고
                    # 어떤 서비스도 재기동하지 않는다 (지금 돌고 있는 컨테이너는 그대로).
                    case " $services " in
                        *" shop-backend "*)
                            bash deploy/ec2-1/apply-shop-migrations.sh
                            ;;
                    esac

                    # --no-deps로 대상 서비스의 의존 서비스(MySQL 포함)도 기동·재생성하지 않는다.
                    docker compose \\
                      -p ec2-1 \\
                      --env-file "$EC2_ENV_FILE" \\
                      -f deploy/ec2-1/docker-compose.yml \\
                      up -d --build --no-deps $services

                    # 새 이미지에 커밋 SHA 태그 (서비스별 최근 5개만 유지, 실패해도 배포는 계속)
                    bash deploy/ec2-1/deploy-helpers.sh tag-commit "$(git rev-parse --short=12 HEAD)" $services || true

                    # 헬스 체크: 뜨지 않으면 빌드를 실패로 표시한다. 자동 롤백은 하지 않는다 —
                    # 되돌리기 절차는 deploy/ec2-1/README.md "배포 확인과 되돌리기".
                    bash deploy/ec2-1/deploy-helpers.sh health $services
                '''
            }
        }

    }
}
