import re
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPOSITORY_ROOT / "skills" / "syzqemuctl"


def parse_frontmatter(text):
    parts = text.split("---", 2)
    if len(parts) != 3 or parts[0].strip():
        raise ValueError("SKILL.md must start with YAML frontmatter")

    metadata = {}
    for line in parts[1].strip().splitlines():
        key, separator, value = line.partition(":")
        if not separator:
            raise ValueError("frontmatter entries must use key: value syntax")
        metadata[key.strip()] = value.strip()
    return metadata, parts[2]


class SkillTests(unittest.TestCase):
    def setUp(self):
        self.skill_file = SKILL_ROOT / "SKILL.md"
        self.skill_text = self.skill_file.read_text(encoding="utf-8")

    def test_frontmatter_identifies_skill(self):
        metadata, body = parse_frontmatter(self.skill_text)

        self.assertEqual(set(metadata), {"name", "description"})
        self.assertEqual(metadata["name"], SKILL_ROOT.name)
        self.assertIn("Use when", metadata["description"])
        self.assertGreater(len(metadata["description"]), 80)
        self.assertTrue(body.strip())

    def test_local_references_exist_inside_skill(self):
        _metadata, body = parse_frontmatter(self.skill_text)
        links = re.findall(r"\[[^]]+\]\(([^)]+)\)", body)
        local_links = [link for link in links if "://" not in link]

        self.assertTrue(local_links)
        for link in local_links:
            target = (SKILL_ROOT / link).resolve()
            try:
                target.relative_to(SKILL_ROOT.resolve())
            except ValueError:
                self.fail("skill reference escapes its directory: {}".format(link))
            self.assertTrue(target.is_file(), link)

    def test_openai_metadata_matches_skill(self):
        metadata_file = SKILL_ROOT / "agents" / "openai.yaml"
        text = metadata_file.read_text(encoding="utf-8")

        self.assertRegex(text, r'(?m)^interface:\s*$')
        self.assertRegex(text, r'(?m)^  display_name: "syzqemuctl"\s*$')
        description = re.search(
            r'(?m)^  short_description: "([^"]+)"\s*$', text
        )
        prompt = re.search(r'(?m)^  default_prompt: "([^"]+)"\s*$', text)
        self.assertIsNotNone(description)
        self.assertIsNotNone(prompt)
        self.assertGreaterEqual(len(description.group(1)), 25)
        self.assertLessEqual(len(description.group(1)), 64)
        self.assertIn("$syzqemuctl", prompt.group(1))

    def test_skill_has_no_placeholders(self):
        for path in SKILL_ROOT.rglob("*"):
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("TODO", text, str(path))
                self.assertNotIn("[TODO", text, str(path))


if __name__ == "__main__":
    unittest.main()
