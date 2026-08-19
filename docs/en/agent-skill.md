# Agent Skill

The repository includes a portable Agent Skill at
[`skills/syzqemuctl`](https://github.com/QGrain/syzqemuctl/tree/main/skills/syzqemuctl).
It gives coding agents a concise workflow for using syzqemuctl's public CLI and
Python API without depending on private SSH, process, or runtime details.

## Contents

```text
skills/syzqemuctl/
|-- SKILL.md
|-- agents/
|   `-- openai.yaml
`-- references/
    |-- failure-handling.md
    `-- workflows.md
```

`SKILL.md` follows the Agent Skills convention: YAML metadata determines when
the skill applies, and the Markdown body provides the core workflow. Detailed
examples and recovery guidance are loaded from `references/` only when needed.
`agents/openai.yaml` supplies optional Codex-facing display metadata.

## Install for a coding agent

Clone the repository, then copy or link `skills/syzqemuctl` into one of the
agent's skill search paths:

| Agent | User-level path | Project-level path |
| --- | --- | --- |
| Codex | `~/.agents/skills/syzqemuctl` | `.agents/skills/syzqemuctl` |
| Claude Code | `~/.claude/skills/syzqemuctl` | `.claude/skills/syzqemuctl` |
| OpenCode | `~/.config/opencode/skills/syzqemuctl` | `.opencode/skills/syzqemuctl` |

For example, install the skill for all Codex sessions:

```bash
mkdir -p "$HOME/.agents/skills"
ln -s /path/to/syzqemuctl/skills/syzqemuctl \
  "$HOME/.agents/skills/syzqemuctl"
```

Install it for all Claude Code sessions with:

```bash
mkdir -p "$HOME/.claude/skills"
ln -s /path/to/syzqemuctl/skills/syzqemuctl \
  "$HOME/.claude/skills/syzqemuctl"
```

OpenCode also discovers the `.agents/skills` and `.claude/skills` locations.
If the skill is already installed there, do not install a duplicate under
`.opencode/skills`. Otherwise, its native user-level location can be used:

```bash
mkdir -p "$HOME/.config/opencode/skills"
ln -s /path/to/syzqemuctl/skills/syzqemuctl \
  "$HOME/.config/opencode/skills/syzqemuctl"
```

Restart the agent after installation if it does not discover the skill during
the current session. Use a copy instead of a symbolic link when the agent
environment cannot follow links. The `agents/openai.yaml` file is optional
outside Codex; the portable behavior is defined by `SKILL.md` and
`references/`.

## Typical triggers

The skill is intended for requests such as:

- create an image, boot a kernel, and wait for SSH;
- append a case-specific kernel command-line argument safely;
- run a PoC with explicit command and transfer timeouts;
- recover stale `screen`, pidfile, port, or exact-image QEMU runtime;
- diagnose why start, stop, or deletion did not complete;
- replace external access to `vm._ssh` or private cleanup helpers.

The skill does not install QEMU, create a Linux kernel build, or decide whether
an experiment reproduced a target crash. Those remain host setup and
application-level responsibilities.
