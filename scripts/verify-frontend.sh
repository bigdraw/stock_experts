#!/usr/bin/env bash
# 前端验证脚本（固化测试标准）：
#   1. vue-tsc -b（类型检查）
#   2. npm run build（含 CSS/PostCSS 解析，catch 语法错）
# 退出码 0=全过，非 0=有错，pre-commit 据此阻断 commit。
# 不用 tail 截断输出、不靠 && 链吞退出码——独立检查每步 exit code。

set -u
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
cd "$REPO_ROOT/frontend" || exit 0

FAIL=0

echo "--- vue-tsc type-check ---"
npx vue-tsc -b 2>&1
TSC_RC=$?
if [ $TSC_RC -ne 0 ]; then
  echo "FAIL: vue-tsc exit $TSC_RC" >&2
  FAIL=1
else
  echo "PASS: vue-tsc"
fi

echo "--- vite build (含 CSS/PostCSS 语法检查) ---"
npm run build 2>&1
BUILD_RC=$?
if [ $BUILD_RC -ne 0 ]; then
  echo "FAIL: npm run build exit $BUILD_RC" >&2
  FAIL=1
else
  # 确认输出含 "✓ built"（不只是 exit 0）
  if ! npm run build 2>&1 | grep -q "built"; then
    echo "WARN: build exit 0 but no 'built' in output"
  fi
  echo "PASS: npm run build"
fi

if [ $FAIL -ne 0 ]; then
  echo ""
  echo "❌ 前端验证失败——修完再 commit。（跳过: git commit --no-verify）" >&2
fi
exit $FAIL
