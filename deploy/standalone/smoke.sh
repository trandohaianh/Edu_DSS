#!/usr/bin/env bash
# Kiểm tra nhanh bản standalone qua Caddy: health của Streamlit, HTTPS và security header.
# Dùng: bash smoke.sh https://edudss.localhost:8443   (thêm -k cho chứng chỉ nội bộ: INSECURE=1)
set -euo pipefail
URL="${1:?Dùng: smoke.sh https://<APP_DOMAIN>[:port]}"
K=(); [ "${INSECURE:-0}" = "1" ] && K=(-k)
curl -fsS "${K[@]}" "${URL}/_stcore/health" | grep -q ok && echo "OK  /_stcore/health"
H="$(curl -fsSI "${K[@]}" "${URL}/")"
for h in strict-transport-security x-content-type-options content-security-policy; do
  grep -qi "^${h}:" <<<"$H" && echo "OK  header ${h}" || { echo "THIẾU header ${h}"; exit 1; }
done
