pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
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
                }
            }
            steps {
                echo 'EC2 실행 구성 관련 변경이 감지되었습니다. 현재는 CI만 수행하며 배포하지 않습니다.'
            }
        }
    }
}
