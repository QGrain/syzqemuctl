import ast
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = PROJECT_ROOT / "syzqemuctl" / "_version.py"


def read_package_version():
    tree = ast.parse(VERSION_FILE.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and target.id == "__version__":
            return ast.literal_eval(node.value)
    raise RuntimeError("__version__ is missing from {}".format(VERSION_FILE))


def on_config(config):
    version = read_package_version()
    channel = os.environ.get("READTHEDOCS_VERSION")
    display_version = version
    if channel in {"latest", "stable"}:
        display_version = "{} ({})".format(version, channel)

    template = config["extra"]["site_name_template"]
    config["site_name"] = template.format(version=display_version)
    return config
