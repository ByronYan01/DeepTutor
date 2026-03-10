pipeline {
    agent any
    options {
        gitLabConnection('xzinfra-gitlab')
        skipDefaultCheckout()
    }
    triggers {
        gitlab(triggerOnPush: true, triggerOnMergeRequest: true, branchFilterType: 'All')
    }
    // 关键修改1：将核心变量移到 pipeline 级别的 environment，让 post 阶段能访问
    environment {
        PLATFORM_DOCKER = 'linux/amd64'
        DOCKERFILE      = 'Dockerfile'
        REGISTRY        = 'harbor.xzinfra.com/spiritx-app'
        REPOSITORY      = 'deeptutor'
        // 初始化空变量，避免后续引用时报错
        ARTIFACT_TAG    = ''
        IS_RELEASE      = 'false'
    }
    stages {
        stage('Build & Push Docker Image') {
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

                echo "构建镜像：${env.REGISTRY}/${env.REPOSITORY}:${env.ARTIFACT_TAG}"

                script {
                    // main/release 分支额外打 latest 标签
                    def extraTag = env.IS_RELEASE == 'true'
                        ? "--tag ${env.REGISTRY}/${env.REPOSITORY}:latest"
                        : ""

                    // Dockerfile 为完整多阶段构建（前端 Next.js + 后端 FastAPI），无需预处理
                    // BACKEND_PORT 是 Dockerfile 中的 ARG，传入以优化 Next.js 静态资源构建
                    sh """
                        docker buildx build \\
                            --push \\
                            --platform ${env.PLATFORM_DOCKER} \\
                            --provenance=false \\
                            --target production \\
                            --build-arg BACKEND_PORT=8001 \\
                            -f ${env.DOCKERFILE} \\
                            --tag ${env.REGISTRY}/${env.REPOSITORY}:${env.ARTIFACT_TAG} \\
                            ${extraTag} \\
                            .
                    """
                }
            }
        }
    }
    post {
        success {
            // 关键修改2：统一使用 env.XXX 形式引用全局变量
            echo "✅ 推送成功：${env.REGISTRY}/${env.REPOSITORY}:${env.ARTIFACT_TAG}"
        }
        failure {
            echo "❌ 构建失败，请查看日志"
        }
    }
}