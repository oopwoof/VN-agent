#!/usr/bin/env python3
"""
pre-commit 文档更新脚本
在每次 git commit 前自动更新 DEV_LOG.md 和 PRODUCT.md

用法：python scripts/update_docs.py
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
DEV_LOG = ROOT / "docs" / "DEV_LOG.md"
PRODUCT = ROOT / "docs" / "PRODUCT.md"


def run(cmd: list[str], **kwargs) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, **kwargs)
    return result.stdout.strip()


def get_staged_files() -> list[str]:
    output = run(["git", "diff", "--cached", "--name-only"])
    return [f for f in output.splitlines() if f] if output else []


def get_staged_diff_stat() -> str:
    return run(["git", "diff", "--cached", "--stat"])


def get_staged_diff_summary() -> str:
    """返回简短的 diff 摘要（每个文件改动行数）"""
    stat = get_staged_diff_stat()
    return stat if stat else "（无变更）"


def get_recent_commits(n: int = 3) -> str:
    return run(["git", "log", f"-{n}", "--oneline", "--no-decorate"])


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def update_dev_log(staged_files: list[str], diff_stat: str) -> None:
    """在 DEV_LOG.md 的"开发记录"区块顶部插入新条目"""
    content = DEV_LOG.read_text(encoding="utf-8")

    # 分类文件
    src_files = [f for f in staged_files if f.startswith("src/")]
    test_files = [f for f in staged_files if f.startswith("tests/")]
    config_files = [f for f in staged_files if f.startswith("config/") or f.endswith(".toml") or f.endswith(".yaml")]
    doc_files = [f for f in staged_files if f.startswith("docs/")]
    other_files = [f for f in staged_files if f not in src_files + test_files + config_files + doc_files]

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

    # 插入到"开发记录"标题之后
    marker = "## 开发记录\n"
    if marker in content:
        insert_pos = content.index(marker) + len(marker)
        content = content[:insert_pos] + new_entry + content[insert_pos:]
    else:
        content += "\n" + new_entry

    # 更新底部时间戳
    if "_最后更新:" in content:
        lines = content.splitlines()
        for i in range(len(lines) - 1, -1, -1):
            if "_最后更新:" in lines[i]:
                lines[i] = f"_最后更新: {today()}_"
                break
        content = "\n".join(lines)

    DEV_LOG.write_text(content, encoding="utf-8")
    print(f"✅ DEV_LOG.md 已更新（新增 {today()} 条目）")


def update_product_doc(staged_files: list[str]) -> None:
    """更新 PRODUCT.md 的最后更新时间和进行中的状态"""
    content = PRODUCT.read_text(encoding="utf-8")

    # 更新底部时间戳
    if "_最后更新:" in content:
        lines = content.splitlines()
        for i in range(len(lines) - 1, -1, -1):
            if "_最后更新:" in lines[i]:
                lines[i] = f"_最后更新: {today()}_"
                break
        content = "\n".join(lines)

    PRODUCT.write_text(content, encoding="utf-8")
    print(f"✅ PRODUCT.md 时间戳已更新")


def main() -> int:
    staged = get_staged_files()

    # 过滤掉文档文件自身，避免循环（但仍包含进 commit）
    non_doc_staged = [f for f in staged if not f.startswith("docs/")]

    if not non_doc_staged:
        # 只有文档变更，不触发更新（避免无限循环）
        print("ℹ️  仅文档变更，跳过文档更新")
        return 0

    print(f"\n📝 更新项目文档（{len(staged)} 个文件变更中）...")

    diff_stat = get_staged_diff_stat()
    update_dev_log(staged, diff_stat)
    update_product_doc(staged)

    # 将文档加入本次 commit
    subprocess.run(
        ["git", "add", "docs/DEV_LOG.md", "docs/PRODUCT.md"],
        cwd=ROOT,
        check=True,
    )
    print("✅ docs/ 已加入暂存区\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
