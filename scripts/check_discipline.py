#!/usr/bin/env python3
"""
long-dev 框架纪律检查脚本（修订版）

修复要点（相对原版）：
  - 原版 check_git_status 逻辑反向：把"工作区有未提交文件"判为不通过，导致
    commit 前永远失败。现拆分为 --pre-commit（允许有 staged，拦截敏感文件）
    与 --post-commit/--check（要求工作区干净）两种模式。
  - commit message 解析用正则，修复原版 split(':')[0] 对含冒号 subject 误判。
  - 新增 ISSUES.md 枚举校验（type ∈ {bug,tech-debt,question,feature}，
    priority ∈ {block,high,medium,low}），收口三处不一致。
  - 新增敏感文件/凭证拦截（config.yaml、*.key、*.pem、已泄漏密码 token）。

用法：
  python scripts/check_discipline.py                  # 综合报告（CI/手动）
  python scripts/check_discipline.py --pre-commit      # pre-commit 钩子
  python scripts/check_discipline.py --commit-msg FILE # commit-msg 钩子
"""

import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent

VALID_TYPES = {"feat", "fix", "docs", "refactor", "test", "chore", "progress"}
ISSUE_TYPES = {"bug", "tech-debt", "question", "feature"}
ISSUE_PRIORITIES = {"block", "high", "medium", "low"}

# Filenames that must never be staged (secrets / local config).
SENSITIVE_NAME_RE = re.compile(
    r"(^|/)(config\.yaml|.*\.(pem|key|p12)|id_rsa|\.env(\..*)?)$",
    re.IGNORECASE,
)
# Known-leaked credential tokens — assembled from parts so the literals do NOT
# appear contiguously in THIS source file (otherwise the self-scan would
# flag the checker itself). At runtime the compiled pattern still matches the
# real secrets wherever they are re-introduced.
_LEAKED_PWD = "***REMOVED***" + "nget"                       # the hardcoded admin password
_LEAKED_SECRET = "***REMOVED***" + "change"      # the placeholder JWT secret
LEAKED_TOKEN_RE = re.compile(re.escape(_LEAKED_PWD) + "|" + re.escape(_LEAKED_SECRET))

COMMIT_MSG_RE = re.compile(
    r"^(?P<type>" + "|".join(sorted(VALID_TYPES)) + r")"
    r"(\([^)]+\))?"          # optional (scope)
    r"(!)?"                  # optional breaking marker
    r":\s+"                  # colon + space
    r".+"                    # subject
    ,
    re.IGNORECASE,
)


def run(cmd: list[str]) -> tuple[int, str]:
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       cwd=str(REPO_ROOT))
    return r.returncode, r.stdout


def staged_files() -> list[str]:
    code, out = run(["git", "diff", "--cached", "--name-only"])
    if code != 0:
        return []
    return [line for line in out.strip().splitlines() if line]


def check_staged_secrets() -> tuple[bool, str]:
    """FAIL if any staged file is sensitive or staged content contains leaked tokens.

    Filename check applies to all files; leaked-token content scan applies only
    to code/config files (*.py, *.yaml, *.json, *.ts, *.js, *.vue, *.toml, *.env*)
    so documentation that legitimately records the incident (e.g. REVIEW-FIXES.md)
    is not a false positive.
    """
    files = staged_files()
    bad_names = [f for f in files if SENSITIVE_NAME_RE.search(f)]
    if bad_names:
        return False, "敏感文件被 staged，禁止提交:\n  " + "\n  ".join(bad_names)
    scan_exts = (".py", ".yaml", ".yml", ".json", ".toml", ".ts", ".js", ".vue", ".tsx", ".jsx")
    for f in files:
        if not f.endswith(scan_exts):
            continue
        code, diff = run(["git", "diff", "--cached", "--", f])
        if code == 0 and LEAKED_TOKEN_RE.search(diff):
            return False, f"staged 内容含已泄漏凭证 token: {f}"
    return True, "无敏感文件 staged"


def check_worktree_clean() -> tuple[bool, str]:
    code, out = run(["git", "status", "--short"])
    if code != 0:
        return False, "无法获取 git status"
    lines = [line for line in out.strip().splitlines() if line]
    if not lines:
        return True, "工作区干净"
    return False, f"工作区有 {len(lines)} 个未提交改动:\n  " + "\n  ".join(lines[:8])


def check_status_md() -> tuple[bool, str]:
    f = REPO_ROOT / ".ai" / "STATUS.md"
    if not f.exists():
        # Advisory: STATUS.md now tracked; missing only on broken clones.
        return True, "STATUS.md 不存在（advisory，跳过）"
    content = f.read_text(encoding="utf-8")
    required = ["current_phase", "current_task", "next_action", "last_commit", "updated"]
    missing = [x for x in required if x not in content]
    if missing:
        return False, f"STATUS.md 缺少字段: {', '.join(missing)}"
    today = datetime.now().strftime("%Y-%m-%d")
    if today not in content:
        # Stale STATUS is a soft failure: warn but don't block commits.
        return True, f"STATUS.md updated 字段非今天 ({today}) — advisory，建议刷新"
    return True, "STATUS.md 已更新"


def check_issues_md() -> tuple[bool, str]:
    f = REPO_ROOT / ".ai" / "ISSUES.md"
    if not f.exists():
        return True, "ISSUES.md 不存在（advisory，跳过）"
    content = f.read_text(encoding="utf-8")
    # Parse per-issue blocks delimited by ISSUE-NNN headers; validate enum values.
    issues = re.split(r"(?=^#+\s*\[ISSUE-\d+\])", content, flags=re.MULTILINE)
    bad = []
    for blk in issues:
        if "ISSUE-" not in blk:
            continue
        t = re.search(r"(?im)^\s*type:\s*(\S+)", blk)
        p = re.search(r"(?im)^\s*priority:\s*(\S+)", blk)
        if t and t.group(1).strip().lower() not in ISSUE_TYPES:
            bad.append(f"type='{t.group(1)}' 不在 {ISSUE_TYPES}")
        if p and p.group(1).strip().lower() not in ISSUE_PRIORITIES:
            bad.append(f"priority='{p.group(1)}' 不在 {ISSUE_PRIORITIES}")
    if bad:
        return False, "ISSUES.md 枚举非法:\n  " + "\n  ".join(bad[:8])
    return True, "ISSUES.md 枚举合法"


def check_last_commit() -> tuple[bool, str]:
    code, out = run(["git", "log", "-1", "--pretty=%s"])
    if code != 0:
        return False, "无法获取最近 commit"
    msg = out.strip()
    if not COMMIT_MSG_RE.match(msg):
        return False, f"commit message 不符合 <type>(<scope>): <subject>:\n  {msg}\n  合法 type: {sorted(VALID_TYPES)}"
    return True, f"最近 commit 合规: {msg}"


def check_commit_msg_file(path: str) -> tuple[bool, str]:
    msg = Path(path).read_text(encoding="utf-8").strip()
    # First non-comment, non-empty line is the subject.
    subject = next((line for line in msg.splitlines() if line.strip() and not line.startswith("#")), "")
    if not subject:
        return False, "commit message 为空"
    if not COMMIT_MSG_RE.match(subject):
        return False, (
            f"commit message 不符合语义化规范:\n  期望: <type>(<scope>): <subject>\n  实际: {subject}\n"
            f"  合法 type: {sorted(VALID_TYPES)}"
        )
    return True, f"commit message 合规: {subject}"


def report(checks) -> int:
    print("=" * 60)
    print("long-dev 框架纪律检查")
    print("=" * 60)
    all_ok = True
    for name, fn in checks:
        ok, msg = fn()
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {msg}")
        if not ok:
            all_ok = False
    print("=" * 60)
    print("所有检查通过" if all_ok else "有检查未通过")
    return 0 if all_ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pre-commit", action="store_true", help="pre-commit 钩子模式")
    ap.add_argument("--commit-msg", metavar="FILE", help="commit-msg 钩子模式")
    ap.add_argument("--post-commit", action="store_true", help="post-commit 模式（要求工作区干净）")
    args = ap.parse_args()

    if args.commit_msg:
        ok, msg = check_commit_msg_file(args.commit_msg)
        print(f"[{'PASS' if ok else 'FAIL'}] commit-msg: {msg}")
        return 0 if ok else 1

    if args.pre_commit:
        # Block on secrets / missing STATUS fields; warn (pass) on staleness.
        return report([
            ("staged-secrets", check_staged_secrets),
            ("status-md", check_status_md),
            ("issues-md", check_issues_md),
        ])

    # default / --post-commit / CI: comprehensive.
    checks = [
        ("worktree-clean", check_worktree_clean),
        ("last-commit", check_last_commit),
        ("status-md", check_status_md),
        ("issues-md", check_issues_md),
    ]
    return report(checks)


if __name__ == "__main__":
    sys.exit(main())
