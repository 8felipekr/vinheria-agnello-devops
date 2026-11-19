pipeline {
    agent any

    environment {
        PUBLISH_DIR = '/var/www/vinheria-agnello'
        APP_NAME    = 'Vinheria Agnello - Microsservicos IoT & Notificacao'
    }

    stages {
        stage('Checkout') {
            steps {
                echo '=== [STAGE 1] Checkout do Repositorio Git ==='
                sh '''
                    git log -n 3 --oneline
                    git rev-parse --short HEAD > .git_commit
                '''
            }
        }

        stage('Build') {
            steps {
                echo '=== [STAGE 2] Build dos Microsservicos ==='
                sh '''
                    echo "Deploy da Vinheria"
                    python3 -m py_compile services/quality-iot-service/app.py
                    python3 -m py_compile services/notification-service/app.py
                    python3 -m py_compile infra/esp32-sim/simulate_esp32.py
                    mkdir -p dist
                    tar -czf "dist/vinheria-agnello-build-${BUILD_NUMBER}.tar.gz" \
                        services/quality-iot-service/app.py \
                        services/quality-iot-service/requirements.txt \
                        services/notification-service/app.py \
                        services/notification-service/requirements.txt \
                        infra/gateway/nginx.conf \
                        infra/dns-dhcp/dnsmasq.conf \
                        infra/dns-dhcp/hosts.vinheria
                    ls -lh dist/
                '''
            }
        }

        stage('Testes & DevSecOps') {
            steps {
                echo '=== [STAGE 3] Testes Unitarios e Verificacao DevSecOps ==='
                sh '''
                    python3 -m unittest discover -s tests -v

                    echo "[DevSecOps] Verificando se nenhuma chave privada foi versionada no Git..."
                    if git ls-files | grep -E '[.](key|pem)$'; then
                        echo "FALHA DEVSECOPS: Chave privada encontrada no repositorio Git!"
                        exit 1
                    fi

                    echo "[DevSecOps] Verificando enforcement de RS256 no Notification Service..."
                    grep -Fq 'algorithms=["RS256"]' services/notification-service/app.py
                    echo "[DevSecOps] Todas as verificacoes de seguranca passaram."
                '''
            }
        }

        stage('Deploy para Pasta de Publicacao (Simulacao IIS)') {
            steps {
                echo '=== [STAGE 4] Publicacao em /var/www/vinheria-agnello ==='
                sh '''
                    COMMIT_SHA=$(cat .git_commit)
                    DEPLOY_TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

                    mkdir -p "${PUBLISH_DIR}/releases/build-${BUILD_NUMBER}"
                    cp "dist/vinheria-agnello-build-${BUILD_NUMBER}.tar.gz" "${PUBLISH_DIR}/releases/"
                    cp -r services "${PUBLISH_DIR}/releases/build-${BUILD_NUMBER}/"

                    cat > "${PUBLISH_DIR}/release.json" <<EOF
{
  "project": "Vinheria Agnello - Arquitetura DevOps & DevSecOps",
  "student": "Felipe Castro Lima (rm554976)",
  "buildNumber": "${BUILD_NUMBER}",
  "gitCommit": "${COMMIT_SHA}",
  "deployedAtUtc": "${DEPLOY_TS}",
  "publishRoot": "${PUBLISH_DIR}",
  "simulatedEnvironment": "IIS wwwroot (Nginx Container)",
  "services": [
    {"name": "quality-iot-service", "fqdn": "quality.vinheria.local", "auth": "JWT-RS256"},
    {"name": "notification-service", "fqdn": "notification.vinheria.local", "auth": "JWT-RS256+RBAC"}
  ],
  "artifact": "/releases/vinheria-agnello-build-${BUILD_NUMBER}.tar.gz",
  "status": "PUBLISHED"
}
EOF

                    cat > "${PUBLISH_DIR}/index.html" <<EOF
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <title>Vinheria Agnello - Portal de Publicacao (Build #${BUILD_NUMBER})</title>
  <style>
    body { font-family: system-ui, sans-serif; background: #141218; color: #f1edf5; max-width: 820px; margin: 40px auto; padding: 24px; }
    .card { background: #201c28; border: 1px solid #3c334a; border-radius: 10px; padding: 20px; margin-bottom: 18px; }
    h1 { color: #d8a7b1; margin-top: 0; }
    code { background: #2d2638; padding: 2px 6px; border-radius: 4px; color: #b7e4c7; }
    .badge { display: inline-block; background: #2d6a4f; color: #fff; padding: 4px 10px; border-radius: 999px; font-size: 0.85rem; }
  </style>
</head>
<body>
  <div class="card">
    <span class="badge">DEPLOY CONCLUIDO</span>
    <h1>Vinheria Agnello &mdash; Pasta de Publicacao (Simulacao IIS)</h1>
    <p><strong>Mensagem de Build:</strong> <code>Deploy da Vinheria</code></p>
    <p><strong>Build Jenkins:</strong> <code>#${BUILD_NUMBER}</code> &nbsp;|&nbsp; <strong>Commit Git:</strong> <code>${COMMIT_SHA}</code></p>
    <p><strong>Publicado em (UTC):</strong> <code>${DEPLOY_TS}</code></p>
    <p><strong>Aluno / Grupo:</strong> Felipe Castro Lima (RM554976) &mdash; Grupo 55 / Turma Online</p>
  </div>
  <div class="card">
    <h2>Microsservicos Publicados (DNS: vinheria.local)</h2>
    <ul>
      <li><code>quality.vinheria.local</code> &mdash; Quality &amp; IoT Service (ESP32 DHT22/LDR + Emissor JWT RS256)</li>
      <li><code>notification.vinheria.local</code> &mdash; Notification Service (Validacao RS256 + RBAC + Deduplicacao)</li>
      <li><code>gateway.vinheria.local</code> &mdash; API Gateway (HTTP :8081 demo insegura / HTTPS TLS 1.3 :8443)</li>
    </ul>
    <p>Manifesto JSON: <a href="/release.json" style="color:#d8a7b1">/release.json</a> | Artefatos: <a href="/releases/" style="color:#d8a7b1">/releases/</a></p>
  </div>
</body>
</html>
EOF
                    ls -la "${PUBLISH_DIR}"
                '''
            }
        }

        stage('Validacao Pos-Deploy (Smoke Test)') {
            steps {
                echo '=== [STAGE 5] Smoke Test via DNS Interno (vinheria.local) ==='
                sh '''
                    echo "[DNS] Resolvendo prod-site.vinheria.local e gateway.vinheria.local..."
                    dig +short @172.28.0.53 prod-site.vinheria.local
                    dig +short @172.28.0.53 gateway.vinheria.local

                    echo "[HTTP] Validando site publicado (simulacao IIS)..."
                    curl -sf http://prod-site.vinheria.local/release.json | jq .

                    echo "[HTTPS] Validando API Gateway com CA interna..."
                    curl -sf --cacert /certs/ca.crt https://gateway.vinheria.local/health | jq .
                '''
            }
        }
    }

    post {
        success {
            echo "Pipeline #${env.BUILD_NUMBER} da Vinheria Agnello finalizado com SUCESSO!"
        }
        failure {
            echo "Pipeline #${env.BUILD_NUMBER} FALHOU. Verifique os logs."
        }
    }
}
