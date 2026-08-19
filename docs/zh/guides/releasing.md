# 发布流程

本页供项目维护者使用。普通用户应继续安装 PyPI 已发布的软件包。

## 构建发行包

更新软件包版本和 changelog 后，从干净的 checkout 开始：

```bash
python -m pip install --upgrade build twine
rm -rf build dist syzqemuctl.egg-info
python -m build
python -m twine check --strict dist/*
```

不要直接调用 `setup.py`。项目通过 `pyproject.toml` 声明的 PEP 517 入口构建，
同时保留 setuptools 和 Python 3.8 源码构建兼容性。

## 验证发行版本

创建 tag 前完成以下检查：

1. 在 Python 3.8、3.11 和 3.13 上运行完整单元测试；
2. 分别安装并冒烟测试 wheel 和源码发行包；
3. 严格构建中英文文档；
4. 推送发行 commit 并等待 GitHub Actions；
5. 验证中英文 Read the Docs `latest` 构建和语言切换。

以上检查通过后再创建并推送发行 tag。确认中英文 Read the Docs `stable` 构建
成功后上传发行包：

```bash
python -m twine upload dist/*
```

## Read the Docs 项目设置

英文项目是父项目。中文项目使用 `docs/zh/.readthedocs.yaml`，并注册为父项目的
翻译项目。两个项目都应在 `Settings > Addons > Analytics` 中启用 Traffic
Analytics。流量统计由 Read the Docs 配置，不在仓库 JavaScript 中植入。

文档页眉从 `syzqemuctl/_version.py` 读取软件包版本。Read the Docs 通过构建
环境附加 `stable` 或 `latest` 渠道标识：`stable` 指向最新发行 tag，`latest`
跟随 `main`。面向用户的文档链接应以 `stable` 为默认版本。
