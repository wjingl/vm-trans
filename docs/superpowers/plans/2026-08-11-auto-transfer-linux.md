# 自动传输 + Linux 版 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ① 自动传输开关(默认开启、配置记忆、排队续传、传完即清);② Linux 版(同一代码反向传输到 Windows `W:/0_temp/VM_TRAN`,install.sh 一键安装)。

**Architecture:** 功能①改 `config.py`(DEFAULT_CONFIG 加 `auto_transfer`)+ `main.py`(勾选框、drop 触发、快照清理、防重入、自动续传);功能②改 `config.py` 的 `config_path()`(Linux 分支 `~/.config/vm-trans/config.json`)+ 新增 `install.sh`/`run.sh`/桌面快捷方式 + README。`transfer.py` 不动。

**Tech Stack:** Python 3.13、PyQt5、paramiko(不变);bash(install.sh)。

## Global Constraints

- 自动传输默认开启:`auto_transfer: true`;旧配置(无字段)按默认 true 处理
- 勾选状态变化立即写入 config.json
- 自动模式:拖入即传(无进行中时);进行中拖入 → 排队,当前批传完自动续传;传完即清(仅移除本次快照项)
- 手动模式:现有行为完全不变(列表保留)
- 防重入:传输进行中 start_transfer 直接忽略
- 自动触发日志前缀「⏩ 自动传输」,手动「开始传输」
- Linux 版:config_path() 非 Windows → `~/.config/vm-trans/config.json`;frozen 分支不变
- Linux 默认配置:`user=wjl`、`ip=192.168.163.1`(VMnet8)、`target=W:/0_temp/VM_TRAN`、`auto_transfer=true`
- Windows 侧前提(文档):启用 OpenSSH Server,防火墙放行 22
- 中文界面;现有 41 测试必须保持通过;每个任务结尾 commit
- 改动文件:`config.py`、`main.py`、`tests/`、新增 `install.sh`、README.md

---

### Task 1: 配置默认值 auto_transfer

**Files:**
- Modify: `config.py`(DEFAULT_CONFIG)
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: 无
- Produces: `DEFAULT_CONFIG["auto_transfer"] = True`(Task 2 的 main.py 读取 `cfg.get("auto_transfer", True)`)

- [ ] **Step 1: 写失败测试**

在 `tests/test_config.py` 的 `test_ensure_config_creates_default` 中追加断言:

```python
    assert cfg["auto_transfer"] is True
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /w/0_proj/VM_TRAN && python -m pytest tests/test_config.py::test_ensure_config_creates_default -v`
Expected: FAIL — `KeyError: 'auto_transfer'`

- [ ] **Step 3: 实现**

`config.py` 的 DEFAULT_CONFIG 改为:

```python
DEFAULT_CONFIG = {
    "auto_transfer": True,
    "vms": [
        {
            "name": "VMware Ubuntu",
            "user": "wjl",
            "password": "114514",
            "ip": "192.168.163.130",
            "target": "",
        }
    ]
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /w/0_proj/VM_TRAN && python -m pytest tests/ -v`
Expected: 41 passed

- [ ] **Step 5: 提交**

```bash
cd /w/0_proj/VM_TRAN && git add config.py tests/test_config.py && git commit -m "feat: default auto_transfer config field"
```

---

### Task 2: 自动传输行为(main.py)

**Files:**
- Modify: `main.py`(勾选框、drop 触发、start_transfer 防重入与快照、_on_transfer_finished 清理续传)
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `DEFAULT_CONFIG["auto_transfer"]`(Task 1);`save_config`/`config_path`(config.py)
- Produces:
  - `MainWindow.auto_check: QCheckBox`(objectName 不需要,普通样式)
  - `MainWindow.start_transfer(auto: bool = False)`(手动信号连接为无参调用,默认 False)
  - `MainWindow._transfer_running() -> bool`
  - `MainWindow._drop_finished_batch()` — 移除本次快照项
  - `MainWindow._on_auto_toggled(checked: bool)` — 立即保存配置

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_main.py` 末尾:

```python
def _make_win(tmp_path, monkeypatch, cfg_extra=None):
    """构造 MainWindow,config 写入 tmp_path。"""
    import json
    from config import DEFAULT_CONFIG
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if cfg_extra:
        cfg.update(cfg_extra)
    p = tmp_path / "config.json"
    p.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(main, "config_path", lambda: str(p))
    return main.MainWindow()


def test_auto_check_default_on_and_memory(tmp_path, monkeypatch):
    win = _make_win(tmp_path, monkeypatch)  # 无 auto_transfer 字段 → 默认开
    assert win.auto_check.isChecked() is True


def test_auto_check_off_remembered(tmp_path, monkeypatch):
    win = _make_win(tmp_path, monkeypatch, {"auto_transfer": False})
    assert win.auto_check.isChecked() is False
    # 切换回开 → 立即写回配置
    win.auto_check.setChecked(True)
    assert json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))["auto_transfer"] is True


def test_drop_triggers_auto_transfer(tmp_path, monkeypatch):
    win = _make_win(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(win, "start_transfer", lambda auto=False: calls.append(auto))
    win.add_dropped("C:/a.txt")
    assert calls == [True]  # 自动触发


def test_drop_no_trigger_when_auto_off(tmp_path, monkeypatch):
    win = _make_win(tmp_path, monkeypatch, {"auto_transfer": False})
    calls = []
    monkeypatch.setattr(win, "start_transfer", lambda auto=False: calls.append(auto))
    win.add_dropped("C:/a.txt")
    assert calls == []  # 手动模式不自动触发


def test_drop_no_trigger_while_transfer_running(tmp_path, monkeypatch):
    win = _make_win(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(win, "start_transfer", lambda auto=False: calls.append(auto))
    class Running:
        def isRunning(self):
            return True
    win.worker = Running()
    win.add_dropped("C:/a.txt")  # 传输中 → 不触发,排队
    assert calls == []
    assert "C:/a.txt" in win.dropped_items()


def test_start_transfer_reentry_ignored(tmp_path, monkeypatch):
    win = _make_win(tmp_path, monkeypatch)
    class Running:
        def isRunning(self):
            return True
    win.worker = Running()
    win.add_dropped("C:/a.txt")
    win.start_transfer()  # 防重入:直接忽略
    assert win.worker is Running  # 未被替换


def test_auto_finished_clears_batch_and_continues(tmp_path, monkeypatch):
    win = _make_win(tmp_path, monkeypatch)
    win.dropped = ["C:/a.txt", "C:/b.txt"]
    win.dropped_keys = {os.path.normcase("C:/a.txt"), os.path.normcase("C:/b.txt")}
    win.dropped_list.clear()
    for i in win.dropped:
        win.dropped_list.addItem(i)
    calls = []
    monkeypatch.setattr(win, "start_transfer", lambda auto=False: calls.append(auto))
    win._batch = ["C:/a.txt"]      # 本次只传了 a
    win._auto_mode = True
    win._on_transfer_finished(True)
    assert win.dropped_items() == ["C:/b.txt"]      # a 已清,b 保留
    assert calls == [True]                          # 自动续传


def test_manual_finished_keeps_list(tmp_path, monkeypatch):
    win = _make_win(tmp_path, monkeypatch)
    win.dropped = ["C:/a.txt"]
    win.dropped_list.clear()
    win.dropped_list.addItem("C:/a.txt")
    win._batch = ["C:/a.txt"]
    win._auto_mode = False
    win._on_transfer_finished(True)
    assert win.dropped_items() == ["C:/a.txt"]      # 手动模式保留
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /w/0_proj/VM_TRAN && python -m pytest tests/test_main.py -v`
Expected: FAIL — `AttributeError: 'MainWindow' object has no attribute 'auto_check'`

- [ ] **Step 3: 实现 main.py**

3a. `__init__` 中 `self.dropped = []` 附近初始化状态(现有 `self.worker = None` 行之后):

```python
        self._auto_mode = False   # 本次传输是否自动触发
        self._batch = []          # 本次传输的快照项(自动模式传完即清)
```

3b. 按钮行(现有 `btn_row` 构建处)改为:

```python
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.auto_check = QCheckBox("自动传输(拖入后立即传输)")
        self.auto_check.setChecked(self.cfg.get("auto_transfer", True))
        self.auto_check.toggled.connect(self._on_auto_toggled)
        btn_row.addWidget(self.auto_check)
        self.transfer_btn = QPushButton("🚀 传输")
        self.transfer_btn.setObjectName("primaryBtn")
        self.transfer_btn.setMinimumHeight(44)
        self.transfer_btn.clicked.connect(self.start_transfer)
        config_btn = QPushButton("⚙ 配置")
        config_btn.setObjectName("secondaryBtn")
        config_btn.clicked.connect(self.open_config)
        btn_row.addWidget(self.transfer_btn)
        btn_row.addWidget(config_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)
```

3c. 新增方法(放在 `_set_drop_active` 之后):

```python
    def _on_auto_toggled(self, checked: bool):
        """自动传输开关:立即记忆到配置(无需点传输)。"""
        self.cfg["auto_transfer"] = checked
        try:
            save_config(config_path(), self.cfg)
        except ValueError as e:
            self.log(f"⚠ 配置保存失败: {e}")

    def _transfer_running(self) -> bool:
        return self.worker is not None and self.worker.isRunning()
```

3d. `dropEvent` 末尾追加自动触发(现有 `event.acceptProposedAction()` 之后):

```python
        event.acceptProposedAction()
        if self.auto_check.isChecked() and not self._transfer_running():
            self.start_transfer(auto=True)
```

3e. `start_transfer` 改为(整体替换):

```python
    def start_transfer(self, auto: bool = False):
        if self._transfer_running():
            return  # 防重入:传输进行中忽略(自动触发路径保护)
        vms = self._selected_vms()
        if not vms:
            self.log("✗ 请至少勾选一台虚拟机")
            return
        if not self.dropped:
            self.log("✗ 请先拖入文件或文件夹")
            return
        self._auto_mode = auto
        self._batch = list(self.dropped)
        self.transfer_btn.setEnabled(False)
        self.log_view.clear()
        prefix = "⏩ 自动传输" if auto else "开始传输"
        self.log(f"[{datetime.now():%H:%M:%S}] {prefix} {len(self.dropped)} 项 → {len(vms)} 台虚拟机")
        worker = TransferWorker(vms, self._batch)
        worker.log_signal.connect(self.log)
        worker.finished_signal.connect(self._on_transfer_finished)
        self.worker = worker
        worker.start()
```

3f. `_on_transfer_finished` 改为:

```python
    def _on_transfer_finished(self, ok: bool):
        self.transfer_btn.setEnabled(True)
        if ok:
            self.log("✅ 全部传输完成")
        else:
            self.log("⚠ 部分传输失败,详情见上方日志")
        if self._auto_mode:
            self._drop_finished_batch()
            if self.dropped:
                # 传输中拖入的新项:自动续传
                self.start_transfer(auto=True)

    def _drop_finished_batch(self):
        """自动模式:移除本次已传项(传完即清),保留传输中拖入的新项。"""
        for item in self._batch:
            if item in self.dropped:
                self.dropped.remove(item)
                self.dropped_keys.discard(os.path.normcase(item))
        self.dropped_list.clear()
        for item in self.dropped:
            self.dropped_list.addItem(item)
        self._batch = []
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /w/0_proj/VM_TRAN && python -m pytest tests/ -v`
Expected: 48 passed(41 旧 + 7 新)

- [ ] **Step 5: 提交**

```bash
cd /w/0_proj/VM_TRAN && git add main.py tests/test_main.py && git commit -m "feat: auto-transfer toggle with queue-and-clear"
```

---

### Task 3: Linux 版 config_path 分支

**Files:**
- Modify: `config.py`(`config_path()`)
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: 无
- Produces: Linux 非 frozen 时 `config_path() == os.path.expanduser("~/.config/vm-trans/config.json")`;Windows/非 frozen 与 frozen 分支不变

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_config.py` 末尾:

```python
def test_config_path_linux_branch(monkeypatch):
    """Linux(非 Windows)非 frozen:配置放 ~/.config/vm-trans/。"""
    import config
    monkeypatch.setattr(config.os, "name", "posix")
    monkeypatch.setattr(config.sys, "frozen", False, raising=False)
    expected = os.path.expanduser("~/.config/vm-trans/config.json")
    assert config_path() == expected
```

(注意:测试文件顶部需 `import os` —— 若无,添加。)

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /w/0_proj/VM_TRAN && python -m pytest tests/test_config.py::test_config_path_linux_branch -v`
Expected: FAIL — 当前返回 `W:\0_proj\VM_TRAN\config.json` 路径而非 `~/.config/...`

- [ ] **Step 3: 实现**

`config.py` 的 `config_path()` 替换为:

```python
def config_path() -> str:
    """配置文件位置:exe 同目录(frozen)/Linux 用户配置目录/脚本同目录。"""
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
        return str(base / "config.json")
    if os.name != "nt":
        return os.path.expanduser("~/.config/vm-trans/config.json")
    return str(Path(__file__).parent / "config.json")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /w/0_proj/VM_TRAN && python -m pytest tests/ -v`
Expected: 49 passed

- [ ] **Step 5: 提交**

```bash
cd /w/0_proj/VM_TRAN && git add config.py tests/test_config.py && git commit -m "feat: linux config path under ~/.config/vm-trans"
```

---

### Task 4: install.sh + 桌面快捷方式 + README

**Files:**
- Create: `install.sh`
- Modify: `README.md`(新增「Linux 版」章节)

**Interfaces:**
- Consumes: `requirements.txt`(PyQt5、paramiko);`main.py` 入口
- Produces: `install.sh`(apt 依赖 → venv → 默认 config → run.sh → .desktop 快捷方式)

- [ ] **Step 1: 写 install.sh**

创建 `install.sh`(逐字使用以下内容):

```bash
#!/usr/bin/env bash
# VM Trans Linux 版安装脚本:一条命令装好,启动即用。
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_DIR="$HOME/.config/vm-trans"
VENV_DIR="$APP_DIR/.venv"

echo "==> 安装系统依赖(PyQt5 运行库)..."
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip \
    libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-keysyms1 \
    libxcb-shape0 libxcb-render-util0 libegl1 libfontconfig1

echo "==> 创建 Python 虚拟环境并安装依赖..."
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -q PyQt5 paramiko

echo "==> 生成默认配置..."
mkdir -p "$CONFIG_DIR"
if [ ! -f "$CONFIG_DIR/config.json" ]; then
  cat > "$CONFIG_DIR/config.json" <<'EOF'
{
  "auto_transfer": true,
  "vms": [
    {
      "name": "Windows 主机",
      "user": "wjl",
      "password": "",
      "ip": "192.168.163.1",
      "target": "W:/0_temp/VM_TRAN"
    }
  ]
}
EOF
  echo "    已创建 $CONFIG_DIR/config.json —— 请编辑填入 Windows 用户密码"
else
  echo "    已有配置,保留不动"
fi

echo "==> 创建启动脚本..."
cat > "$APP_DIR/run.sh" <<EOF
#!/usr/bin/env bash
cd "$APP_DIR"
exec "$VENV_DIR/bin/python" main.py
EOF
chmod +x "$APP_DIR/run.sh"

echo "==> 创建桌面快捷方式..."
mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/vm-trans.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=VM Trans
Comment=拖拽文件传输到 Windows 主机
Exec=$APP_DIR/run.sh
Terminal=false
Categories=Utility;
EOF

echo "==> 安装完成!"
echo "    运行: $APP_DIR/run.sh  或在应用列表搜索「VM Trans」"
echo "    配置: ~/.config/vm-trans/config.json(填 Windows 用户密码)"
echo "    前提: Windows 已启用 OpenSSH Server;虚拟机与主机 VMnet8 网络互通"
```

- [ ] **Step 2: 语法检查**

Run: `cd /w/0_proj/VM_TRAN && bash -n install.sh`
Expected: 无输出(语法正确);`ls -l install.sh` 确认可执行位(如无,`chmod +x install.sh`)

- [ ] **Step 3: 更新 README**

在 README.md 的「虚拟机侧要求」之后追加:

```markdown
## Linux 版(虚拟机内反向传输到 Windows)

在 Linux 虚拟机中运行同一工具,拖入文件后自动传输到 Windows 主机的
`W:\0_temp\VM_TRAN`(自动传输开关同样适用)。

### Windows 侧准备(一次)

1. 启用 OpenSSH 服务器:设置 → 系统 → 可选功能 → 添加功能 → OpenSSH 服务器
2. 启动服务:`Start-Service sshd`;设置 → 应用 → 启动,将 OpenSSH Server 设为自动
3. 防火墙放行 22 端口(启用服务时通常自动添加规则)
4. 确认 VM 可访问主机:`ping 192.168.163.1`(VMnet8 网关地址,与虚拟机同网段)

### 虚拟机内安装

```bash
cd <解压目录>
./install.sh        # 自动装依赖、建虚拟环境、创建桌面快捷方式
```

安装后:

- 启动:应用列表「VM Trans」或 `./run.sh`
- 首次使用:编辑 `~/.config/vm-trans/config.json`,在虚拟机配置中填入 Windows
  用户密码(用户名默认 `wjl`,IP 默认 `192.168.163.1`,目标目录
  `W:/0_temp/VM_TRAN` 可改)
- 传输目标目录不存在时自动创建

> 注:Windows OpenSSH 的 SFTP 对盘符路径(W:/...)的支持,如遇失败,可把
> `target` 改为绝对 POSIX 形式(如 `/W:/0_temp/VM_TRAN`)或映射后重试。
```

- [ ] **Step 4: 提交**

```bash
cd /w/0_proj/VM_TRAN && git add install.sh README.md && git commit -m "feat: linux install script and docs"
```

---

## 自审记录

- **Spec 覆盖**:auto-transfer spec §2(配置/默认/记忆)→ Task 1 + Task 2 Step 3b/3c;§3(UI 勾选框)→ Task 2;§4(排队续传/传完即清/防重入/日志/文件夹复用)→ Task 2 Step 3d/3e/3f;§5 测试 → Task 1/2。Linux spec §3(config_path 分支、默认配置)→ Task 3 + Task 4 Step 1(默认 config 内容);§4 install.sh → Task 4;§5 验证 → Task 2/3 测试 + README 部署说明。无缺口。
- **占位检查**:无 TBD、无临时占位(初稿中的占位行已删除,自审确认)。
- **类型一致性**:`start_transfer(auto: bool = False)` 在 Task 2 Step 3e 定义,Task 2 测试与 `dropEvent`/`_on_transfer_finished` 调用一致;`_transfer_running()`/`_drop_finished_batch()`/`_on_auto_toggled(checked)` 签名在 Step 3c/3f 定义与测试一致;`config_path()` 分支行为在 Task 3 定义、Task 3 测试断言一致。
