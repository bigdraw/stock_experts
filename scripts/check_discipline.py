#!/usr/bin/env python3
"""
long-dev 框架纪律检查脚本

用于检查当前工作区是否符合 long-dev 框架的纪律要求。
可在 commit 前运行，确保所有检查点都已通过。
"""

import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime

# 设置控制台编码为 UTF-8
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')


def run_command(cmd: list[str]) -> tuple[int, str, str]:
    """运行命令并返回 (returncode, stdout, stderr)"""
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    return result.returncode, result.stdout, result.stderr


def check_git_status() -> tuple[bool, str]:
    """检查 git status"""
    code, stdout, _ = run_command(['git', 'status', '--short'])
    if code != 0:
        return False, "无法获取 git status"
    
    lines = [l for l in stdout.strip().split('\n') if l]
    if not lines:
        return True, "工作区干净，无待提交文件"
    
    return False, f"有 {len(lines)} 个文件待提交:\n" + '\n'.join(lines[:10])


def check_status_md() -> tuple[bool, str]:
    """检查 STATUS.md 是否已更新"""
    status_file = Path('.ai/STATUS.md')
    if not status_file.exists():
        return False, "STATUS.md 不存在"
    
    content = status_file.read_text(encoding='utf-8')
    
    # 检查必要字段
    required_fields = ['current_phase', 'current_task', 'next_action', 'last_commit', 'updated']
    missing = [f for f in required_fields if f not in content]
    if missing:
        return False, f"STATUS.md 缺少字段: {', '.join(missing)}"
    
    # 检查 updated 是否为今天
    today = datetime.now().strftime('%Y-%m-%d')
    if today not in content:
        return False, f"STATUS.md 的 updated 字段不是今天 ({today})"
    
    return True, "STATUS.md 已更新"


def check_issues_md() -> tuple[bool, str]:
    """检查 ISSUES.md 是否存在"""
    issues_file = Path('.ai/ISSUES.md')
    if not issues_file.exists():
        return False, "ISSUES.md 不存在"
    
    return True, "ISSUES.md 存在"


def check_last_commit() -> tuple[bool, str]:
    """检查最近的 commit message 是否符合语义化规范"""
    code, stdout, _ = run_command(['git', 'log', '-1', '--pretty=%s'])
    if code != 0:
        return False, "无法获取最近 commit"
    
    message = stdout.strip()
    
    # 语义化规范: <type>(<scope>): <subject>
    # type: feat, fix, docs, refactor, test, chore, progress
    valid_types = ['feat', 'fix', 'docs', 'refactor', 'test', 'chore', 'progress']
    
    if ':' not in message:
        return False, f"commit message 不符合语义化规范: {message}"
    
    type_part = message.split(':')[0].strip()
    if '(' in type_part:
        type_part = type_part.split('(')[0].strip()
    
    if type_part not in valid_types:
        return False, f"commit type '{type_part}' 不在有效列表中: {', '.join(valid_types)}"
    
    return True, f"最近 commit: {message}"


def main():
    """主函数"""
    print("=" * 60)
    print("long-dev 框架纪律检查")
    print("=" * 60)
    print()
    
    checks = [
        ("Git 状态", check_git_status),
        ("STATUS.md", check_status_md),
        ("ISSUES.md", check_issues_md),
        ("最近 Commit", check_last_commit),
    ]
    
    all_passed = True
    for name, check_func in checks:
        passed, message = check_func()
        status = "✓" if passed else "✗"
        print(f"{status} {name}: {message}")
        if not passed:
            all_passed = False
        print()
    
    print("=" * 60)
    if all_passed:
        print("✓ 所有检查通过，可以 commit")
        return 0
    else:
        print("✗ 有检查未通过，请先修复再 commit")
        print()
        print("修复建议:")
        print("1. 更新 .ai/STATUS.md")
        print("2. 确保所有修改的文件已 git add")
        print("3. 使用语义化 commit message")
        print("4. 如有遗留问题，记录到 .ai/ISSUES.md")
        return 1


if __name__ == '__main__':
    sys.exit(main())
