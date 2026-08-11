# VM Trans UI 改进 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 主窗口改浅色简洁风格(纯 QSS)、加大到 640×560、启动时定位在主屏右缘 40px 垂直居中。

**Architecture:** 仅修改 `main.py` + `tests/test_main.py`。位置计算抽成纯函数 `compute_window_position`(可测);全局 QSS 常量 `APP_QSS` 在 `main()` 中应用到 QApplication;拖放高亮用 dynamic property + QSS 状态选择器。

**Tech Stack:** Python 3.13、PyQt5 5.15(QSS、dynamic property、QWidget.screen())、paramiko(不变)、PyInstaller(重新打包)。

## Global Constraints

- 不改变任何功能逻辑、传输流程、配置格式;不新增依赖
- 主窗口 `resize(640, 560)`;配置对话框 `resize(640, 520)`
- 启动位置:主屏 `availableGeometry`,`x = 屏宽 - 640 - 40`,`y = (屏高 - 560) // 2`,不足时 clamp 到 0
- 浅色简洁配色(设计文档 §3.2):主色蓝 `#4a90d9`、拖放区底 `#f0f6ff`、悬停 `#e0eefd`、卡片灰 `#f7f8fa`、边框 `#e0e4ea`
- 中文界面;公共接口(测试钩子、transfer_to_vm 等)不变;现有 36 个测试必须保持通过
- 重新打包 `dist/vm-trans.exe`(PyInstaller --onefile --noconsole)

---

### Task 1: 窗口尺寸 + 启动位置函数

**Files:**
- Modify: `main.py`(`__init__` 中 resize;新增模块级函数 `compute_window_position`;MainWindow 新增 `position_on_screen`;`main()` 中 move)
- Test: `tests/test_main.py`(新增 2 个测试)

**Interfaces:**
- Consumes: 无(纯新增 + 尺寸常量)
- Produces:
  - `compute_window_position(screen_w: int, screen_h: int, win_w: int, win_h: int, margin: int = 40) -> tuple[int, int]`
  - `MainWindow.position_on_screen() -> tuple[int, int]` — 用 `self.screen().availableGeometry()` 计算

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_main.py` 末尾:

```python
def test_compute_window_position_right_middle():
    x, y = main.compute_window_position(1920, 1080, 640, 560)
    assert x == 1920 - 640 - 40
    assert y == (1080 - 560) // 2


def test_compute_window_position_clamps_small_screen():
    x, y = main.compute_window_position(600, 400, 640, 560)
    assert x == 0
    assert y == 0


def test_position_on_screen_uses_available_geometry(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "config_path", lambda: str(tmp_path / "config.json"))
    win = main.MainWindow()
    x, y = win.position_on_screen()
    geo = win.screen().availableGeometry()
    assert x == geo.width() - win.width() - 40
    assert y == (geo.height() - win.height()) // 2
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /w/0_proj/VM_TRAN && python -m pytest tests/test_main.py -v`
Expected: FAIL — `AttributeError: module 'main' has no attribute 'compute_window_position'`

- [ ] **Step 3: 实现**

在 `main.py` 中 `TransferWorker` 类之前(模块级)添加:

```python
def compute_window_position(screen_w: int, screen_h: int, win_w: int, win_h: int, margin: int = 40) -> tuple[int, int]:
    """主屏右缘 margin 像素、垂直居中的窗口位置;屏幕小于窗口时贴左上角。"""
    x = max(0, screen_w - win_w - margin)
    y = max(0, (screen_h - win_h) // 2)
    return x, y
```

`MainWindow.__init__` 中把 `self.resize(420, 380)` 改为 `self.resize(640, 560)`。

`MainWindow` 类中(测试钩子区之前)添加:

```python
def position_on_screen(self) -> tuple[int, int]:
    geo = self.screen().availableGeometry()
    return compute_window_position(geo.width(), geo.height(), self.width(), self.height())
```

`main()` 改为:

```python
def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    x, y = win.position_on_screen()
    win.move(x, y)
    win.show()
    sys.exit(app.exec_())
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /w/0_proj/VM_TRAN && python -m pytest tests/ -v`
Expected: 39 passed(36 旧 + 3 新)

- [ ] **Step 5: 提交**

```bash
cd /w/0_proj/VM_TRAN && git add main.py tests/test_main.py && git commit -m "feat: larger window positioned at screen right edge"
```

---

### Task 2: 浅色简洁 QSS 美化 + 拖放高亮 + 打包

**Files:**
- Modify: `main.py`(APP_QSS 常量、布局调整、objectName/dynamic property、dragEnter/Leave/drop 高亮、ConfigDialog 尺寸与卡片)
- Test: `tests/test_main.py`(新增 1 个拖放高亮属性测试)
- Create(临时,不提交):`ui-screenshot.png`(冒烟截图,放 `.superpowers/sdd/`)

**Interfaces:**
- Consumes: `compute_window_position`(Task 1,已存在)
- Produces: 无新公共接口;`drop_area` 有 `active` dynamic property(`True`/`False`/`None`)

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_main.py` 末尾:

```python
def test_drop_area_active_property_toggles(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "config_path", lambda: str(tmp_path / "config.json"))
    win = main.MainWindow()
    assert win.drop_area.property("active") in (None, False)
    win._set_drop_active(True)
    assert win.drop_area.property("active") is True
    win._set_drop_active(False)
    assert win.drop_area.property("active") is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /w/0_proj/VM_TRAN && python -m pytest tests/test_main.py::test_drop_area_active_property_toggles -v`
Expected: FAIL — `AttributeError: 'MainWindow' object has no attribute '_set_drop_active'`

- [ ] **Step 3: 实现 QSS 与布局**

3a. 在 `main.py` 模块级(`compute_window_position` 之后)添加全局样式常量:

```python
APP_QSS = """
* { font-family: "Microsoft YaHei"; font-size: 10pt; }
QMainWindow, QDialog { background: #ffffff; }
#titleLabel { font-size: 16pt; font-weight: bold; color: #2b3a4a; }
#subtitleLabel { color: #8a94a6; font-size: 9.5pt; }
#sectionLabel { font-weight: bold; color: #4a5568; }
QListWidget {
    background: #f7f8fa; border: 1px solid #e0e4ea; border-radius: 8px;
    padding: 4px; font-size: 10.5pt;
}
QListWidget::item { padding: 6px; }
QListWidget::item:selected { background: #e0eefd; color: #1a2733; }
#dropArea {
    background: #f0f6ff; border: 2px dashed #4a90d9; border-radius: 12px;
    color: #4a90d9; font-size: 11pt; padding: 24px;
}
#dropArea[active="true"] { background: #e0eefd; border: 2px solid #4a90d9; }
QPushButton#primaryBtn {
    background: #4a90d9; color: white; border: none; border-radius: 8px;
    font-size: 12pt; font-weight: bold; padding: 10px 24px;
}
QPushButton#primaryBtn:hover { background: #3d7ec2; }
QPushButton#primaryBtn:pressed { background: #356faa; }
QPushButton#primaryBtn:disabled { background: #b8c6d6; color: #f0f3f7; }
QPushButton#secondaryBtn {
    background: white; color: #4a90d9; border: 1px solid #4a90d9;
    border-radius: 8px; padding: 8px 20px;
}
QPushButton#secondaryBtn:hover { background: #eef5fc; }
QTextEdit#logView {
    background: #f7f8fa; border: 1px solid #e0e4ea; border-radius: 8px;
    padding: 6px; color: #333333;
}
QCheckBox { spacing: 8px; font-size: 10.5pt; }
QFrame#vmCard {
    background: #f7f8fa; border: 1px solid #e0e4ea; border-radius: 10px; padding: 8px;
}
QScrollBar:vertical { background: transparent; width: 8px; }
QScrollBar::handle:vertical { background: #c8d2e0; border-radius: 4px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: #a8b6c8; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
"""
```

3b. `MainWindow.__init__` 布局重排(替换 `self.dropped = []` 之后到 `self._rebuild_vm_list()` 之前的整段布局代码):

```python
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 14, 16, 14)

        title = QLabel("VM Trans")
        title.setObjectName("titleLabel")
        subtitle = QLabel("拖拽传文件到虚拟机")
        subtitle.setObjectName("subtitleLabel")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        layout.addWidget(self._section_label("目标虚拟机"))
        self.vm_list = QListWidget()
        self.vm_list.setMaximumHeight(100)
        layout.addWidget(self.vm_list)

        self.drop_area = QLabel("把文件/文件夹拖到这里\n(支持多选)", self)
        self.drop_area.setObjectName("dropArea")
        self.drop_area.setAlignment(Qt.AlignCenter)
        self.drop_area.setMinimumHeight(150)
        self.drop_area.setAcceptDrops(True)
        layout.addWidget(self.drop_area)

        layout.addWidget(self._section_label("已拖入文件"))
        self.dropped_list = QListWidget()
        self.dropped_list.setMaximumHeight(110)
        layout.addWidget(self.dropped_list)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
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

        self.log_view = QTextEdit()
        self.log_view.setObjectName("logView")
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("Consolas", 9.5))
        layout.addWidget(self.log_view, 1)

        self._rebuild_vm_list()
```

`_section_label` 静态方法(放在 `__init__` 之后):

```python
    @staticmethod
    def _section_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionLabel")
        return label
```

3c. 拖放高亮(替换现有 `dragEnterEvent`/`dropEvent`,新增 `dragLeaveEvent`/`_set_drop_active`):

```python
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            self._set_drop_active(True)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._set_drop_active(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self._set_drop_active(False)
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.add_dropped(url.toLocalFile())
        event.acceptProposedAction()

    def _set_drop_active(self, active: bool):
        """切换拖放区高亮(dynamic property + QSS [active="true"] 选择器)。"""
        if self.drop_area.property("active") != active:
            self.drop_area.setProperty("active", active)
            style = self.drop_area.style()
            style.unpolish(self.drop_area)
            style.polish(self.drop_area)
```

3d. `ConfigDialog.__init__` 中 `self.resize(560, 420)` 改为 `self.resize(640, 520)`;`_add_row` 中 `frame.setFrameShape(QFrame.StyledPanel)` 改为:

```python
        frame.setObjectName("vmCard")
```

(删除 `setFrameShape` 一行,加 `setObjectName("vmCard")`。)

3e. `main()` 应用全局样式(在 `app = QApplication(sys.argv)` 之后):

```python
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_QSS)
```

- [ ] **Step 4: 运行全部测试确认通过**

Run: `cd /w/0_proj/VM_TRAN && python -m pytest tests/ -v`
Expected: 40 passed

- [ ] **Step 5: 冒烟 + 截图**

生成截图(offscreen 平台,不弹窗):

```bash
cd /w/0_proj/VM_TRAN && python - <<'EOF'
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PyQt5.QtWidgets import QApplication
import main
app = QApplication([])
app.setStyleSheet(main.APP_QSS)
win = main.MainWindow()
win.add_dropped("C:/test/a.txt")
win.add_dropped("C:/test/folder")
win._set_drop_active(False)
win.resize(640, 560)
win.show()
app.processEvents()
win.grab().save(".superpowers/sdd/ui-screenshot.png")
print("saved")
EOF
```

Expected: 输出 `saved`,`.superpowers/sdd/ui-screenshot.png` 存在。再生成一张拖放高亮对比图:

```bash
cd /w/0_proj/VM_TRAN && python - <<'EOF'
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PyQt5.QtWidgets import QApplication
import main
app = QApplication([])
app.setStyleSheet(main.APP_QSS)
win = main.MainWindow()
win._set_drop_active(True)
win.resize(640, 560)
win.show()
app.processEvents()
win.grab().save(".superpowers/sdd/ui-screenshot-active.png")
print("saved")
EOF
```

Expected: 输出 `saved`,高亮图存在。**不要删除这两张图**,控制器会查看验证美观度。

- [ ] **Step 6: 手动运行验证窗口位置**

```bash
cd /w/0_proj/VM_TRAN && python main.py &
sleep 4
tasklist | grep -i python
taskkill //IM python.exe //F
```

Expected: 进程存活(窗口已打开)。位置数值由 Task 1 的测试保证;如需肉眼确认可截图,但非必须。

- [ ] **Step 7: 提交**

```bash
cd /w/0_proj/VM_TRAN && git add main.py tests/test_main.py && git commit -m "feat: modern light theme with drag-drop highlight"
```

- [ ] **Step 8: 重新打包**

```bash
cd /w/0_proj/VM_TRAN && python -m PyInstaller --onefile --noconsole --name vm-trans main.py
```

Expected: `dist/vm-trans.exe` 生成,无报错。

- [ ] **Step 9: 更新 README(仅打包产物相关一行,如无变化则跳过)**

README 中无尺寸/位置承诺,预计无需改动。若打包命令有变化才更新。

---

## 自审记录

- **Spec 覆盖**:§3.1 尺寸/位置 → Task 1;§3.2 QSS 配色、布局、高亮、按钮 → Task 2 Step 3;§3.3 测试(位置单测、现有测试保持、拖放高亮属性测试) → Task 1 Step 1 + Task 2 Step 1/4;§4 打包 → Task 2 Step 8;§5 不做的事 → 无对应任务(正确)。无缺口。
- **占位检查**:所有步骤含完整代码;无 TBD。
- **类型一致性**:`compute_window_position(screen_w, screen_h, win_w, win_h, margin=40)` 在 Task 1 定义、Task 1 测试与 `position_on_screen` 中使用一致;`_set_drop_active(active: bool)` 在 Task 2 定义、Task 2 测试与拖放事件中使用一致;`APP_QSS` 在 Task 2 Step 3a 定义、Step 3e/5 使用一致。objectName 值(`dropArea`/`primaryBtn`/`secondaryBtn`/`logView`/`vmCard`/`titleLabel`/`subtitleLabel`/`sectionLabel`)在 QSS 与代码中一一对应。
