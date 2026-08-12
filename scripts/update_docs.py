#!/usr/bin/env python3
"""
pre-commit 文档更新脚本
在每次 git commit 前自动向 docs/CHANGELOG.md 的 [Unreleased] 区块顶部追加条目。

用法：python scripts/update_docs.py

2026-04-23 重构：原脚本同时追加 DEV_LOG.md + 更新 PRODUCT.md 时间戳；
文档切分（DEV_LOG 归档、新建 CHANGELOG/ARCHITECTURE/AUDITS/DESIGN_DECISIONS）后，
机器流水只追 CHANGELOG，稳定区文档由人工维护，不再触碰 PRODUCT.md 时间戳。
"""

import io
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Windows 下强制 UTF-8 输出
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent
CHANGELOG = ROOT / "docs" / "CHANGELOG.md"
UNRELEASED_MARKER = "## [Unreleased]\n"


def run(cmd: list[str], **kwargs) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, **kwargs)
    return result.stdout.strip()


def get_staged_files() -> list[str]:
    output = run(["git", "diff", "--cached", "--name-only"])
    return [f for f in output.splitlines() if f] if output else []


def get_staged_diff_stat() -> str:
    return run(["git", "diff", "--cached", "--stat"])


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def update_changelog(staged_files: list[str], diff_stat: str) -> None:
    """在 CHANGELOG.md 的 [Unreleased] 区块下方插入新条目。"""
    content = CHANGELOG.read_text(encoding="utf-8")

    # 分类文件
    src_files = [f for f in staged_files if f.startswith("src/")]
    test_files = [f for f in staged_files if f.startswith("tests/")]
    config_files = [
        f for f in staged_files
        if f.startswith("config/") or f.endswith(".toml") or f.endswith(".yaml")
    ]
    doc_files = [f for f in staged_files if f.startswith("docs/")]
    other_files = [
        f for f in staged_files
        if f not in src_files + test_files + config_files + doc_files
    ]

    # 推断提交类型
    if test_files and not src_files:
        commit_type = "测试"
    elif doc_files and not src_files:
        commit_type = "文档"
    elif config_files and not src_files:
        commit_type = "配置"
    elif src_files:
        commit_type = "实现"
    else:
        commit_type = "杂项"

    # 构建条目
    file_list = ""
    if src_files:
        file_list += f"\n**源码变更** ({len(src_files)} 文件):\n"
        for f in src_files[:10]:
            file_list += f"  - `{f}`\n"
        if len(src_files) > 10:
            file_list += f"  - ...及其他 {len(src_files) - 10} 个文件\n"
    if test_files:
        file_list += f"\n**测试变更** ({len(test_files)} 文件):\n"
        for f in test_files[:5]:
            file_list += f"  - `{f}`\n"
    if config_files:
        file_list += f"\n**配置变更** ({len(config_files)} 文件):\n"
        for f in config_files[:5]:
            file_list += f"  - `{f}`\n"
    if other_files:
        file_list += f"\n**其他变更** ({len(other_files)} 文件):\n"
        for f in other_files[:5]:
            file_list += f"  - `{f}`\n"

    diff_block = ""
    if diff_stat:
        diff_block = f"\n**变更统计**:\n```\n{diff_stat}\n```\n"

    new_entry = f"""
### {today()} | {commit_type} - {now()}

**变更文件** ({len(staged_files)} 个):{file_list}{diff_block}
**待补充**: _（可在此处手动添加技术决策、反思、学习笔记）_

---
"""

    if UNRELEASED_MARKER in content:
        insert_pos = content.index(UNRELEASED_MARKER) + len(UNRELEASED_MARKER)
        content = content[:insert_pos] + new_entry + content[insert_pos:]
    else:
        content += "\n" + new_entry

    CHANGELOG.write_text(content, encoding="utf-8")
    print(f"✅ CHANGELOG.md 已更新（新增 {today()} 条目）")


def main() -> int:
    staged = get_staged_files()

    # 过滤掉文档文件自身，避免循环（但仍包含进 commit）
    non_doc_staged = [f for f in staged if not f.startswith("docs/")]

    if not non_doc_staged:
        print("ℹ️  仅文档变更，跳过 CHANGELOG 更新")
        return 0

    print(f"\n📝 更新 CHANGELOG（{len(staged)} 个文件变更中）...")

    diff_stat = get_staged_diff_stat()
    update_changelog(staged, diff_stat)

    subprocess.run(
        ["git", "add", "docs/CHANGELOG.md"],
        cwd=ROOT,
        check=True,
    )
    print("✅ docs/CHANGELOG.md 已加入暂存区\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
