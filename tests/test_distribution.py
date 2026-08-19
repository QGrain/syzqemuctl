import email
import os
import tarfile
import unittest
import zipfile
from pathlib import Path


class DistributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dist_value = os.environ.get("SYZQEMUCTL_DIST_DIR")
        if not dist_value:
            raise unittest.SkipTest("SYZQEMUCTL_DIST_DIR is not set")

        cls.dist_dir = Path(dist_value)
        cls.wheel = next(cls.dist_dir.glob("syzqemuctl-*.whl"))
        cls.sdist = next(cls.dist_dir.glob("syzqemuctl-*.tar.gz"))

    def test_wheel_metadata_and_contents(self):
        with zipfile.ZipFile(str(self.wheel)) as archive:
            names = archive.namelist()
            metadata_name = next(
                name for name in names if name.endswith(".dist-info/METADATA")
            )
            entry_points_name = next(
                name
                for name in names
                if name.endswith(".dist-info/entry_points.txt")
            )
            metadata = email.message_from_bytes(archive.read(metadata_name))
            entry_points = archive.read(entry_points_name).decode("utf-8")

        self.assertEqual(metadata["Requires-Python"], ">=3.8")
        self.assertEqual(metadata["License"], "Apache-2.0")
        self.assertIn("syzqemuctl = syzqemuctl.cli:cli", entry_points)
        self.assertFalse(any(name.startswith("docs/") for name in names))
        self.assertFalse(any(name.startswith("skills/") for name in names))

    def test_sdist_contains_project_assets(self):
        with tarfile.open(str(self.sdist), "r:gz") as archive:
            names = {
                "/".join(name.split("/")[1:])
                for name in archive.getnames()
                if "/" in name
            }

        expected = {
            "LICENSE",
            "README.md",
            "pyproject.toml",
            "mkdocs.yml",
            "mkdocs.zh.yml",
            ".readthedocs.yaml",
            "docs/zh/.readthedocs.yaml",
            "docs/hooks.py",
            "docs/en/index.md",
            "docs/zh/index.md",
            "skills/syzqemuctl/SKILL.md",
        }
        self.assertTrue(expected.issubset(names), expected - names)


if __name__ == "__main__":
    unittest.main()
