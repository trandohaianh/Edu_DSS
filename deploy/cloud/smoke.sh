#!/usr/bin/env bash
# Kiểm tra nhanh một bản EduDSS đang chạy: UI, /metrics có khoá, Google OIDC (nếu cấu hình).
set -euo pipefail
BASE="${1:?usage: smoke.sh https://domain}"
fail() { echo "SMOKE FAIL: $*" >&2; exit 1; }
code() { curl -s -o /dev/null -w '%{http_code}' --max-time 20 "$@"; }

[ "$(code "$BASE/_stcore/health")" = 200 ] || fail "Streamlit health"
curl -fsS --max-time 20 "$BASE/" | grep -qi "<title>" || fail "trang chủ"
[ "$(code "$BASE/metrics")" = 401 ] || fail "/metrics phải yêu cầu token"
if [ -n "${EDUDSS_METRICS_TOKEN:-}" ]; then
  curl -fsS --max-time 20 -H "Authorization: Bearer ${EDUDSS_METRICS_TOKEN}" "$BASE/metrics" | grep -q '^edudss_exporter_up 1' \
    || fail "/metrics với token"
fi
if [ -n "${EDUDSS_GOOGLE_CLIENT_ID:-}" ]; then
  loc="$(curl -s -o /dev/null -w '%{redirect_url}' --max-time 20 "$BASE/auth/login?provider=google")"
  case "$loc" in
    https://accounts.google.com/*) ;;
    *) echo "WARN: /auth/login không chuyển sang Google ($loc) — kiểm tra EDUDSS_GOOGLE_* và redirect URI" >&2;;
  esac
fi
echo "SMOKE OK: $BASE"
