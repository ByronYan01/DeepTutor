pipeline {
    agent any
    options {
        gitLabConnection('xzinfra-gitlab')
        skipDefaultCheckout()
    }
    triggers {
        gitlab(triggerOnPush: true, triggerOnMergeRequest: true, branchFilterType: 'All')
    }
    stages {
        stage('Build & Push Docker Image') {
            // PLATFORM_DOCKER = 'linux/arm64,linux/amd64' 暂时去掉arm
            environment {
                PLATFORM_DOCKER = 'linux/amd64'
                DOCKERFILE      = 'Dockerfile'
                REGISTRY        = 'harbor.xzinfra.com/spiritx-app'
                REPOSITORY      = 'deeptutor'
            }
            steps {
                checkout scm
                script {
                    // 与现有项目 Tag 策略保持一致：
                    // main/release 分支：优先用 git tag，否则用分支名+日期+commit hash
                    // 其他分支：仅用分支名+日期+commit hash
                    if (env.BRANCH_NAME == 'main' || env.BRANCH_NAME.startsWith('release/')) {
                        env.ARTIFACT_TAG = sh(
                            script: '[[ $(git rev-list HEAD --max-count=1) == $(git rev-list --tags --max-count=1) ]] && echo $(git describe --tags) || echo $BRANCH_NAME-$(date +%Y-%m-%d)-$(git rev-parse --short HEAD)',
                            returnStdout: true
                        ).trim().replaceAll("/", "-")
                        env.IS_RELEASE = 'true'
                    } else {
                        env.ARTIFACT_TAG = sh(
                            script: 'echo $BRANCH_NAME-$(date +%Y-%m-%d)-$(git rev-parse --short HEAD)',
                            returnStdout: true
                        ).trim().replaceAll("/", "-")
                        env.IS_RELEASE = 'false'
                    }
                }

                echo "构建镜像：${REGISTRY}/${REPOSITORY}:${ARTIFACT_TAG}"

                script {
                    // main/release 分支额外打 latest 标签
                    def extraTag = env.IS_RELEASE == 'true'
                        ? "--tag ${REGISTRY}/${REPOSITORY}:latest"
                        : ""

                    // Dockerfile 为完整多阶段构建（前端 Next.js + 后端 FastAPI），无需预处理
                    // BACKEND_PORT 是 Dockerfile 中的 ARG，传入以优化 Next.js 静态资源构建
                    sh """
                        docker buildx build \\
                            --push \\
                            --platform ${PLATFORM_DOCKER} \\
                            --provenance=false \\
                            --target production \\
                            --build-arg BACKEND_PORT=8001 \\
                            -f ${DOCKERFILE} \\
                            --tag ${REGISTRY}/${REPOSITORY}:${ARTIFACT_TAG} \\
                            ${extraTag} \\
                            .
                    """
                }
            }
        }
    }
    post {
        success {
            echo "✅ 推送成功"
        }
        failure {
            echo "❌ 构建失败，请查看日志"
        }
    }
}
