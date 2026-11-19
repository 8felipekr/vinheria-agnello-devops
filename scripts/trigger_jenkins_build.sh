#!/usr/bin/env bash
set -euo pipefail

JENKINS_URL="${JENKINS_URL:-http://localhost:8080}"
JENKINS_USER="${JENKINS_USER:-admin}"
JENKINS_PASS="${JENKINS_PASS:-vinheria2026}"
JOB_NAME="${JOB_NAME:-vinheria-agnello-deploy}"

COOKIE_JAR="$(mktemp)"
trap 'rm -f "$COOKIE_JAR"' EXIT

echo "[Jenkins] Aguardando Jenkins ficar pronto em ${JENKINS_URL}..."
for i in $(seq 1 60); do
  if curl -sf -u "${JENKINS_USER}:${JENKINS_PASS}" "${JENKINS_URL}/api/json" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

echo "[Jenkins] Obtendo CSRF crumb..."
CRUMB_JSON="$(curl -sf -c "$COOKIE_JAR" -u "${JENKINS_USER}:${JENKINS_PASS}" "${JENKINS_URL}/crumbIssuer/api/json")"
CRUMB_FIELD="$(echo "$CRUMB_JSON" | jq -r '.crumbRequestField')"
CRUMB_VALUE="$(echo "$CRUMB_JSON" | jq -r '.crumb')"

PREV_BUILD="$(curl -sf -u "${JENKINS_USER}:${JENKINS_PASS}" "${JENKINS_URL}/job/${JOB_NAME}/api/json" | jq -r '.lastBuild.number // 0')"
TARGET_BUILD=$((PREV_BUILD + 1))

echo "[Jenkins] Disparando job '${JOB_NAME}' (build esperado #${TARGET_BUILD})..."
curl -sf -X POST -b "$COOKIE_JAR" \
  -u "${JENKINS_USER}:${JENKINS_PASS}" \
  -H "${CRUMB_FIELD}: ${CRUMB_VALUE}" \
  "${JENKINS_URL}/job/${JOB_NAME}/build"

echo "[Jenkins] Aguardando inicio do build #${TARGET_BUILD}..."
for i in $(seq 1 45); do
  if curl -sf -u "${JENKINS_USER}:${JENKINS_PASS}" "${JENKINS_URL}/job/${JOB_NAME}/${TARGET_BUILD}/api/json" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

echo "[Jenkins] Acompanhando execucao do build #${TARGET_BUILD}..."
RESULT="null"
for i in $(seq 1 90); do
  INFO="$(curl -sf -u "${JENKINS_USER}:${JENKINS_PASS}" "${JENKINS_URL}/job/${JOB_NAME}/${TARGET_BUILD}/api/json")"
  BUILDING="$(echo "$INFO" | jq -r '.building')"
  RESULT="$(echo "$INFO" | jq -r '.result')"
  if [ "$BUILDING" = "false" ] && [ "$RESULT" != "null" ]; then
    break
  fi
  sleep 2
done

echo "================ CONSOLE LOG JENKINS (BUILD #${TARGET_BUILD}) ================"
curl -sf -u "${JENKINS_USER}:${JENKINS_PASS}" "${JENKINS_URL}/job/${JOB_NAME}/${TARGET_BUILD}/consoleText"
echo "==============================================================================="
echo "[Jenkins] Resultado final do build #${TARGET_BUILD}: ${RESULT}"

if [ "$RESULT" != "SUCCESS" ]; then
  exit 1
fi
