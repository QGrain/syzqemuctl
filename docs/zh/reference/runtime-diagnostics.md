# 运行时诊断

`VM.runtime_diagnostics()` 返回一个稳定、只读的视图，描述一个镜像所拥有的
运行时资源。它不会断开 SSH、终止进程、关闭 screen 会话或删除文件。

```python
diagnostics = vm.runtime_diagnostics(timeout=5, check_port=True)
print(diagnostics.summary())
record = diagnostics.to_dict()
```

CLI 提供相同数据：

```bash
syzqemuctl diagnose my-image --timeout 5 --json
```

## 字段

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `image_path` | `str` | 规范化的镜像目录。 |
| `screen_sessions` | `Optional[List[str]]` | 准确匹配的会话 ID；检查失败时为 `None`。 |
| `qemu_pids` | `Optional[List[int]]` | 准确匹配镜像的 QEMU PID；检查失败时为 `None`。 |
| `pidfile_exists` | `bool` | `vm.pid` 是否存在。 |
| `pidfile_pid` | `Optional[int]` | 从 pidfile 解析出的值。 |
| `pidfile_pid_valid` | `Optional[bool]` | pidfile PID 是否为准确匹配镜像的 QEMU 进程；`None` 表示未验证。 |
| `port` | `Optional[int]` | 从已保存启动配置解析出的 SSH 宿主机转发端口。 |
| `port_open` | `Optional[bool]` | 端口探测结果；跳过或不可用时为 `None`。 |
| `port_checked` | `bool` | 是否尝试执行端口探测。 |
| `log_file_exists` | `bool` | `vm.log` 是否存在。 |
| `runtime_clean` | `Optional[bool]` | 干净、残留或未知的运行时状态。 |
| `errors` | `List[str]` | 检查失败和格式错误的运行时文件。 |

类型使用 Python 3.8 可用的 `typing.Optional` 和 `typing.List` 表示。

## 三态清洁度

- `True`：所有已检查的运行时资源都不存在，且请求的端口检查未发现开放端口。
- `False`：至少存在一个已知运行时资源，例如 screen 会话、QEMU PID、pidfile
  或开放的已保存端口。
- `None`：没有发现已知残留资源，但至少一个必要检查失败或无法完成。

已知残留状态优先于未知检查。例如，即使 screen 检查失败，只要 pidfile 存在，
`runtime_clean` 仍为 `False`。

## 建议记录的失败信息

当 `start()` 或 `cleanup_runtime()` 返回 `False` 时，应立即持久化 `to_dict()`
输出。该快照通过顺序检查获得，不是宿主机原子事务，因此应尽量靠近待分析的失败
时刻采集。

外部项目不要根据镜像 basename 推断运行时归属，也不要重新构造 screen 名称。
这些规则属于 syzqemuctl 内部实现。
