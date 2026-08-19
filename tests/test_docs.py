import importlib.util
import os
import re
import unittest
from pathlib import Path
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DOCS_ROOT = REPOSITORY_ROOT / "docs"
LANGUAGE_ROOTS = (DOCS_ROOT / "en", DOCS_ROOT / "zh")


def load_docs_hook():
    spec = importlib.util.spec_from_file_location(
        "syzqemuctl_docs_hook", DOCS_ROOT / "hooks.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
        self.assertIn("/en/stable/", english)
        self.assertIn("/zh-cn/stable/", chinese)
        self.assertNotIn("zh_CN", chinese)

    def test_docs_header_uses_package_version_and_rtd_channel(self):
        hook = load_docs_hook()
        version = hook.read_package_version()

        for channel, expected in (
            (None, "syzqemuctl {}".format(version)),
            ("stable", "syzqemuctl {} (stable)".format(version)),
            ("latest", "syzqemuctl {} (latest)".format(version)),
            ("v{}".format(version), "syzqemuctl {}".format(version)),
        ):
            with self.subTest(channel=channel):
                config = {
                    "site_name": "syzqemuctl",
                    "extra": {"site_name_template": "syzqemuctl {version}"},
                }
                environment = {}
                if channel is not None:
                    environment["READTHEDOCS_VERSION"] = channel
                with mock.patch.dict(os.environ, environment, clear=True):
                    hook.on_config(config)
                self.assertEqual(config["site_name"], expected)

    def test_readme_links_to_stable_documentation(self):
        readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("/en/stable/", readme)
        self.assertIn("/zh-cn/stable/", readme)
        self.assertNotIn("readthedocs.io/en/latest/", readme)
        self.assertNotIn("readthedocs.io/zh-cn/latest/", readme)

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
