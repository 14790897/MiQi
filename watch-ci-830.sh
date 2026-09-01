#!/bin/bash
# 轮询 PR #830 的 validate + test + quick 结论，全部非 pending 即退出
cd /d/Desktop/all_code/hermes-miqi || exit 1
for i in $(seq 1 90); do
  out=$(gh pr checks 830 2>/dev/null)
  done_count=$(echo "$out" | grep -cE "^\S+\s+(pass|fail|error|success)" )
  pending=$(echo "$out" | grep -c "pending")
  echo "[$i] done=$done_count pending=$pending"
  # validate / test(ubuntu) / quick 有结论即报告
  for name in "validate" "test (ubuntu-latest)" "quick" "electron-e2e"; do
    line=$(echo "$out" | grep -F "$name" | head -1)
    if [ -n "$line" ]; then echo ">> $line"; fi
  done
  if [ "$pending" -eq 0 ]; then echo "ALL_CHECKS_DONE"; exit 0; fi
  sleep 20
done
echo "TIMEOUT_WAITING"
exit 1
