#!/usr/bin/env bash
# Prove the deploy log block survives the conditions that broke it.
#
# The block runs under `set -Eeuo pipefail` before git pull, so a non-zero exit
# anywhere in it ends the deploy having changed nothing - and leaves the box
# unable to pull the fix for the script that just broke it. That happened on
# 2026-09-08: exit 2, an empty log, and no error message, because the failing
# ls had its stderr sent to /dev/null.
#
# Run: bash tests/shell/test_deploy_log_pruning.sh
set -Eeuo pipefail

DEPLOY_SH="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/deployment/deploy.sh"
failures=0

check() {
  local name="$1" expected="$2" actual="$3"
  if [[ "${expected}" == "${actual}" ]]; then
    echo "  ok   ${name}"
  else
    echo "  FAIL ${name}: expected ${expected}, got ${actual}"
    failures=$((failures + 1))
  fi
}

# Extract the log block itself and run it in isolation, so this tests the
# shipped code rather than a copy of it that could drift.
extract_block() {
  sed -n '/^DEPLOY_LOG_DIR=/,/^fi$/p' "${DEPLOY_SH}"
}

run_block() {
  local dir="$1"
  local script
  script="$(mktemp)"
  {
    echo 'set -Eeuo pipefail'
    echo "DEPLOY_LOG_DIR='${dir}'"
    echo "DEPLOY_LOG_KEEP='${DEPLOY_LOG_KEEP:-50}'"
    extract_block
    echo 'echo REACHED_END'
  } > "${script}"
  bash "${script}" 2>&1
  local status=$?
  rm -f "${script}"
  return ${status}
}

echo "deploy log block:"

# The exact failure: a log directory with no previous deploy logs in it. The
# glob matches nothing, and the deploy must still continue.
empty_dir="$(mktemp -d)"
output="$(run_block "${empty_dir}" || true)"
check "first ever deploy reaches the end" "yes" \
  "$(if [[ "${output}" == *REACHED_END* ]]; then echo yes; else echo no; fi)"
check "first ever deploy writes its log" "1" \
  "$(find "${empty_dir}" -name 'deploy-*.log' | wc -l | tr -d ' ')"
rm -rf "${empty_dir}"

# With older logs present the block must still finish and must keep the cap.
full_dir="$(mktemp -d)"
for index in $(seq 1 6); do
  touch "${full_dir}/deploy-2026090${index}T000000Z.log"
done
output="$(DEPLOY_LOG_KEEP=3 run_block "${full_dir}" || true)"
check "pruning deploy reaches the end" "yes" \
  "$(if [[ "${output}" == *REACHED_END* ]]; then echo yes; else echo no; fi)"
check "keeps DEPLOY_LOG_KEEP logs in total" "3" \
  "$(find "${full_dir}" -name 'deploy-*.log' | wc -l | tr -d ' ')"
rm -rf "${full_dir}"

# An unwritable log directory must degrade to no logging, never to a failure:
# losing the log is an inconvenience, losing the deploy is an outage.
output="$(run_block "/proc/askvera-cannot-exist" || true)"
check "unwritable log directory still deploys" "yes" \
  "$(if [[ "${output}" == *REACHED_END* ]]; then echo yes; else echo no; fi)"

if ((failures > 0)); then
  echo "${failures} check(s) failed"
  exit 1
fi
echo "all checks passed"
