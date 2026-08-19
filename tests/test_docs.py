import re
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DOCS_ROOT = REPOSITORY_ROOT / "docs"
LANGUAGE_ROOTS = (DOCS_ROOT / "en", DOCS_ROOT / "zh")


class DocumentationTests(unittest.TestCase):
    def test_language_pages_match(self):
        pages = [
            {
                path.relative_to(root)
                for path in root.rglob("*.md")
            }
            for root in LANGUAGE_ROOTS
        ]

        self.assertEqual(pages[0], pages[1])
        self.assertTrue(pages[0])

    def test_local_markdown_links_resolve(self):
        link_pattern = re.compile(r"\[[^]]+\]\(([^)]+)\)")

        for language_root in LANGUAGE_ROOTS:
            for page in language_root.rglob("*.md"):
                text = page.read_text(encoding="utf-8")
                for link in link_pattern.findall(text):
                    target = link.split("#", 1)[0]
                    if not target or "://" in target:
                        continue
                    resolved = (page.parent / target).resolve()
                    self.assertTrue(
                        resolved.is_file(),
                        "{} links to missing {}".format(page, target),
                    )

    def test_mkdocs_configs_use_language_directories(self):
        english = (REPOSITORY_ROOT / "mkdocs.yml").read_text(encoding="utf-8")
        chinese = (REPOSITORY_ROOT / "mkdocs.zh.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("docs_dir: docs/en", english)
        self.assertIn("docs_dir: docs/zh", chinese)
        self.assertIn("language: zh", chinese)
        self.assertIn("/zh-cn/latest/", chinese)
        self.assertNotIn("zh_CN", chinese)

    def test_agent_skill_paths_are_current(self):
        guides = [
            (root / "agent-skill.md").read_text(encoding="utf-8")
            for root in LANGUAGE_ROOTS
        ]

        for guide in guides:
            self.assertNotIn(".codex/skills", guide)
            self.assertIn(".agents/skills/syzqemuctl", guide)
            self.assertIn(".claude/skills/syzqemuctl", guide)
            self.assertIn(".opencode/skills/syzqemuctl", guide)


if __name__ == "__main__":
    unittest.main()
