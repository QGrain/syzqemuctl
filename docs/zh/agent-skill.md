# Agent Skill

仓库在
[`skills/syzqemuctl`](https://github.com/QGrain/syzqemuctl/tree/main/skills/syzqemuctl)
中提供了可移植的 Agent Skill。它为 Coding Agent 提供使用 syzqemuctl 公开 CLI
和 Python API 的精简工作流，避免依赖私有 SSH、进程或运行时实现。

## 目录内容

```text
skills/syzqemuctl/
|-- SKILL.md
|-- agents/
|   `-- openai.yaml
`-- references/
    |-- failure-handling.md
    `-- workflows.md
```

`SKILL.md` 遵循 Agent Skills 约定：YAML 元数据决定 Skill 的适用场景，Markdown
正文提供核心工作流。详细示例和恢复指导仅在需要时从 `references/` 加载。
`agents/openai.yaml` 提供可选的 Codex 展示元数据。

## 为 Coding Agent 安装

克隆仓库，然后将 `skills/syzqemuctl` 复制或链接到 Agent 的 Skill 搜索路径：

| Agent | 用户级路径 | 项目级路径 |
| --- | --- | --- |
| Codex | `~/.agents/skills/syzqemuctl` | `.agents/skills/syzqemuctl` |
| Claude Code | `~/.claude/skills/syzqemuctl` | `.claude/skills/syzqemuctl` |
| OpenCode | `~/.config/opencode/skills/syzqemuctl` | `.opencode/skills/syzqemuctl` |

例如，为所有 Codex 会话安装：

```bash
mkdir -p "$HOME/.agents/skills"
ln -s /path/to/syzqemuctl/skills/syzqemuctl \
  "$HOME/.agents/skills/syzqemuctl"
```

为所有 Claude Code 会话安装：

```bash
mkdir -p "$HOME/.claude/skills"
ln -s /path/to/syzqemuctl/skills/syzqemuctl \
  "$HOME/.claude/skills/syzqemuctl"
```

OpenCode 也会发现 `.agents/skills` 和 `.claude/skills`。如果已经在其中一个路径
安装 Skill，不要在 `.opencode/skills` 中重复安装；否则可使用其原生用户级路径：

```bash
mkdir -p "$HOME/.config/opencode/skills"
ln -s /path/to/syzqemuctl/skills/syzqemuctl \
  "$HOME/.config/opencode/skills/syzqemuctl"
```

如果 Agent 无法在当前会话发现 Skill，请在安装后重启 Agent。Agent 环境无法
跟随符号链接时应改用复制。`agents/openai.yaml` 在 Codex 之外是可选文件；
可移植行为由 `SKILL.md` 和 `references/` 定义。

## 典型触发场景

该 Skill 适用于以下请求：

- 创建镜像、启动内核并等待 SSH 就绪；
- 安全追加任务特定的内核命令行参数；
- 使用明确的命令和传输 timeout 运行 PoC；
- 清理陈旧的 `screen`、pidfile、端口或准确匹配镜像的 QEMU 运行时；
- 诊断启动、停止或删除未完成的原因；
- 替换外部代码对 `vm._ssh` 或私有清理 helper 的访问。

该 Skill 不负责安装 QEMU、构建 Linux 内核，也不判断实验是否复现目标崩溃。
这些仍属于宿主机配置和应用层职责。
