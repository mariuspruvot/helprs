#!/usr/bin/env bash
# /// script
# Smoke test for a deployed helPRs instance.
# Usage: ./scripts/smoke-test.sh https://helprs.tech https://api.helprs.tech
# ///
set -euo pipefail

WEB_URL="${1:?Usage: $0 <web-url> <api-url>}"
API_URL="${2:?Usage: $0 <web-url> <api-url>}"

passed=0
failed=0
total=0

check() {
    local name="$1"
    local result="$2"
    local expected="$3"
    total=$((total + 1))

    if [[ "$result" == *"$expected"* ]]; then
        printf "  PASS  %s\n" "$name"
        passed=$((passed + 1))
    else
        printf "  FAIL  %s (expected '%s', got '%s')\n" "$name" "$expected" "$result"
        failed=$((failed + 1))
    fi
}

printf "\n=== helPRs Smoke Test ===\n"
printf "Web: %s\n" "$WEB_URL"
printf "API: %s\n\n" "$API_URL"

# --- Health ---
printf "[Health]\n"
health=$(curl -sf "$API_URL/health" 2>/dev/null || echo "UNREACHABLE")
check "API /health responds" "$health" '"status":"ok"'
check "Database connected" "$health" '"db":"ok"'

# --- TLS ---
printf "\n[TLS]\n"
web_issuer=$(curl -sv "$WEB_URL" 2>&1 | grep -i "issuer:" | head -1 || echo "NO_TLS")
api_issuer=$(curl -sv "$API_URL/health" 2>&1 | grep -i "issuer:" | head -1 || echo "NO_TLS")
check "Web TLS valid" "$web_issuer" "Let's Encrypt"
check "API TLS valid" "$api_issuer" "Let's Encrypt"

# --- Frontend ---
printf "\n[Frontend]\n"
web_status=$(curl -so /dev/null -w "%{http_code}" "$WEB_URL" 2>/dev/null || echo "000")
web_body=$(curl -sf "$WEB_URL" 2>/dev/null || echo "")
check "Web returns 200" "$web_status" "200"
check "Web serves React app" "$web_body" "root"

# --- API routes ---
printf "\n[API Routes]\n"
auth_status=$(curl -so /dev/null -w "%{http_code}" "$API_URL/api/v1/auth/github" 2>/dev/null || echo "000")
webhook_status=$(curl -so /dev/null -w "%{http_code}" -X POST "$API_URL/api/v1/webhooks/github" 2>/dev/null || echo "000")
check "OAuth redirect works" "$auth_status" "302"
check "Webhook endpoint exists" "$webhook_status" "401"

# --- Admin ---
printf "\n[Admin]\n"
admin_status=$(curl -so /dev/null -w "%{http_code}" "$API_URL/admin" 2>/dev/null || echo "000")
check "Admin panel accessible" "$admin_status" "200"

# --- SSE headers ---
printf "\n[SSE]\n"
cors_header=$(curl -sI -H "Origin: $WEB_URL" "$API_URL/health" 2>/dev/null | grep -i "access-control" | head -1 || echo "NO_CORS")
check "CORS headers present" "$cors_header" "access-control"

# --- Docker (run on server only) ---
printf "\n[Docker (local check)]\n"
if command -v docker &>/dev/null; then
    runner_image=$(docker images --format "{{.Repository}}:{{.Tag}}" 2>/dev/null | grep "claude-runner" || echo "NOT_FOUND")
    check "claude-runner image exists" "$runner_image" "claude-runner:latest"
else
    printf "  SKIP  Docker not available (run this on the server for Docker checks)\n"
fi

# --- Summary ---
printf "\n=== Results: %d/%d passed" "$passed" "$total"
if [[ $failed -gt 0 ]]; then
    printf ", %d failed" "$failed"
fi
printf " ===\n\n"

exit "$failed"
