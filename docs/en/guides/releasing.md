# Release process

This page is for project maintainers. User installations should continue to
use the published PyPI package.

## Build distributions

Start from a clean checkout after updating the package version and changelog:

```bash
python -m pip install --upgrade build twine
rm -rf build dist syzqemuctl.egg-info
python -m build
python -m twine check --strict dist/*
```

Do not invoke `setup.py` directly. The project uses the PEP 517 entry point
declared in `pyproject.toml` while retaining setuptools and Python 3.8 source
build compatibility.

## Validate the release

Before creating a tag:

1. run the full unit-test matrix on Python 3.8, 3.11, and 3.13;
2. install and smoke-test both the wheel and source distribution;
3. build the English and Chinese documentation with strict warnings;
4. push the release commit and wait for GitHub Actions;
5. verify both Read the Docs `latest` builds and the language switcher.

Create and push the release tag only after these checks pass. Confirm both
Read the Docs `stable` builds before uploading the distributions:

```bash
python -m twine upload dist/*
```

## Read the Docs project settings

The English project is the parent. The Chinese project uses
`docs/zh/.readthedocs.yaml` and is registered as a translation of the parent.
Keep Traffic Analytics enabled under `Settings > Addons > Analytics` for both
projects. Analytics are configured on Read the Docs rather than in repository
JavaScript.

The documentation header reads the package version from
`syzqemuctl/_version.py`. Read the Docs adds the `stable` or `latest` channel
label through its build environment: `stable` resolves to the latest release
tag, while `latest` tracks `main`. Keep `stable` as the default version for
user-facing documentation links.
