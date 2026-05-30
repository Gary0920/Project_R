import tempfile
import unittest
from pathlib import Path

import api.prompts as prompts_api


class PromptPresetTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.prompt_root = Path(self.temp_dir.name)
        self.company_dir = self.prompt_root / "company"

        self.original_prompt_dir = prompts_api.PROMPT_PRESET_DIR
        self.original_company_dir = prompts_api.COMPANY_PROMPT_DIR

        prompts_api.PROMPT_PRESET_DIR = self.prompt_root
        prompts_api.COMPANY_PROMPT_DIR = self.company_dir

    def tearDown(self):
        prompts_api.PROMPT_PRESET_DIR = self.original_prompt_dir
        prompts_api.COMPANY_PROMPT_DIR = self.original_company_dir
        self.temp_dir.cleanup()

    def test_loads_company_prompts_from_markdown_files(self):
        self.company_dir.mkdir(parents=True)
        (self.company_dir / "work-message-polish.md").write_text(
            """---
id: "company-work-message-polish"
title: "工作沟通改写助手"
version: "1.0.0"
date: "2026-05-26"
author: "Gary"
scope: "工作沟通"
tags: ["工作沟通"]
description: "用于改写工作沟通文本。"
---

# 工作沟通改写助手

## 使用说明
- 直接复制下方「提示词内容」即可使用。

## 提示词内容
你是一个专业的企业工作沟通文本改写助手。

请输出 3 个版本。

## 输入示例（可选）
请明天反馈。
""",
            encoding="utf-8",
        )
        (self.prompt_root / "global-base-prompt.md").write_text(
            """---
id: "global-base-prompt"
title: "全局底层规则"
description: "不应进入公司预设。"
---

## 提示词内容
公司全局规则。
""",
            encoding="utf-8",
        )

        prompts = prompts_api._load_company_prompts()

        self.assertEqual(len(prompts), 1)
        self.assertEqual(prompts[0].id, "company-work-message-polish")
        self.assertEqual(prompts[0].name, "工作沟通改写助手")
        self.assertEqual(prompts[0].description, "用于改写工作沟通文本。")
        self.assertIn("请输出 3 个版本。", prompts[0].content)
        self.assertNotIn("输入示例", prompts[0].content)

    def test_returns_empty_list_when_no_markdown_prompts_exist(self):
        self.prompt_root.mkdir(parents=True, exist_ok=True)

        prompts = prompts_api._load_company_prompts()

        self.assertEqual(prompts, [])
        self.assertFalse((self.prompt_root / "company-prompts.json").exists())


if __name__ == "__main__":
    unittest.main()
