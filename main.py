"""VM Trans 主窗口:拖拽文件 → 勾选虚拟机 → SFTP 传输。"""
import os
import sys
from datetime import datetime

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication, QCheckBox, QDialog, QDialogButtonBox, QFormLayout,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QPushButton, QScrollArea, QTextEdit, QVBoxLayout,
    QWidget,
)

import transfer
from config import DEFAULT_CONFIG, config_path, ensure_config, save_config


def compute_window_position(screen_w: int, screen_h: int, win_w: int, win_h: int, margin: int = 40) -> tuple[int, int]:
    """主屏右缘 margin 像素、垂直居中的窗口位置;屏幕小于窗口时贴左上角。"""
    x = max(0, screen_w - win_w - margin)
    y = max(0, (screen_h - win_h) // 2)
    return x, y


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


class TransferWorker(QThread):
    """后台线程执行传输,避免阻塞 UI。"""

    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool)

    def __init__(self, vms, items):
        super().__init__()
        self.vms = vms
        self.items = items

    def run(self):
        all_ok = True
        try:
            for vm in self.vms:
                ok = transfer.transfer_to_vm(vm, self.items, self.log_signal.emit)
                all_ok = all_ok and ok
        except Exception as e:
            # 传输层已兜底;此处仅防御意外异常(--noconsole 下 stderr 不可见,必须记入日志)
            all_ok = False
            self.log_signal.emit(f"✗ 未预期错误: {e}")
        finally:
            # run() 无论发生什么都必须发出 finished_signal,否则传输按钮永不恢复
            self.finished_signal.emit(all_ok)


class ConfigDialog(QDialog):
    """增删改虚拟机配置。"""

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.rows = []
        self.setWindowTitle("虚拟机配置")
        self.resize(640, 520)
        layout = QVBoxLayout(self)

        hint = QLabel("提示:IP 栏可填纯 IP(如 192.168.163.130),也可整段粘贴 `ip a` 输出,程序自动提取。\n"
                      "目标目录留空 = 自动解析桌面目录并传到其下的 trans 文件夹。")
        hint.setStyleSheet("color: #666;")
        layout.addWidget(hint)

        scroll = QScrollArea()
        container = QWidget()
        self.form_layout = QVBoxLayout(container)
        scroll.setWidget(container)
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll, 1)

        for vm in self.cfg.get("vms", []):
            self._add_row(vm)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("+ 添加虚拟机")
        add_btn.clicked.connect(lambda: self._add_row())
        btn_row.addWidget(add_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _add_row(self, vm=None):
        vm = vm or {"name": "", "user": "", "password": "", "ip": "", "target": ""}
        frame = QFrame()
        frame.setObjectName("vmCard")
        form = QFormLayout(frame)
        name = QLineEdit(vm.get("name", ""))
        user = QLineEdit(vm.get("user", ""))
        pwd = QLineEdit(vm.get("password", ""))
        pwd.setEchoMode(QLineEdit.Password)
        ip = QLineEdit(vm.get("ip", ""))
        target = QLineEdit(vm.get("target", ""))
        form.addRow("名称", name)
        form.addRow("用户名", user)
        form.addRow("密码", pwd)
        form.addRow("IP(或 ip a 输出)", ip)
        form.addRow("目标目录(留空自动)", target)
        del_btn = QPushButton("删除")
        del_btn.clicked.connect(lambda: self._delete_row(frame))
        form.addRow("", del_btn)
        self.form_layout.addWidget(frame)
        self.rows.append((frame, name, user, pwd, ip, target))

    def _delete_row(self, frame):
        """从配置对话框中移除该行(保存后才写入 config)。"""
        for i, (f, *_rest) in enumerate(self.rows):
            if f is frame:
                self.rows.pop(i)
                break
        self.form_layout.removeWidget(frame)
        frame.deleteLater()

    def _on_save(self):
        vms = []
        for frame, name, user, pwd, ip, target in self.rows:
            if not name.text().strip() and not ip.text().strip():
                continue  # 空行跳过
            vms.append({
                "name": name.text().strip(),
                "user": user.text().strip(),
                "password": pwd.text(),
                "ip": ip.text().strip(),
                "target": target.text().strip(),
            })
        if not vms:
            QMessageBox.warning(self, "提示", "至少需要一台虚拟机配置")
            return
        self.cfg["vms"] = vms
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VM Trans — 拖拽传文件到虚拟机")
        self.resize(640, 560)
        try:
            self.cfg = ensure_config(config_path())
        except (ValueError, OSError) as e:
            # --noconsole 下不能直接崩溃;提示后回退默认配置,用户仍可通过「配置」修复
            QMessageBox.critical(self, "配置错误", f"{e}\n已改用默认配置,可通过「配置」对话框修复。")
            self.cfg = DEFAULT_CONFIG
        self.dropped = []
        self.dropped_keys = set()  # Windows 下去重键(os.path.normcase)
        self.worker = None  # 传输线程;None 或已结束的线程不影响关闭

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
        self.log_view.setFont(QFont("Consolas", 10))
        layout.addWidget(self.log_view, 1)

        self._rebuild_vm_list()

    @staticmethod
    def _section_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionLabel")
        return label

    def position_on_screen(self) -> tuple[int, int]:
        geo = self.screen().availableGeometry()
        return compute_window_position(geo.width(), geo.height(), self.width(), self.height())

    # ---- 测试钩子 ----
    def count_checkboxes(self) -> int:
        return self.vm_list.count()

    def checkbox_states(self) -> set:
        return {self.vm_list.itemWidget(self.vm_list.item(i)).isChecked()
                for i in range(self.vm_list.count())}

    def dropped_items(self) -> list:
        return list(self.dropped)

    def add_dropped(self, path: str) -> None:
        # 统一为正斜杠,避免 Windows 下 normpath 产生反斜杠导致去重/测试不一致
        norm = os.path.normpath(path).replace("\\", "/")
        key = os.path.normcase(norm)  # Windows 大小写不敏感去重
        if key not in self.dropped_keys:
            self.dropped.append(norm)
            self.dropped_keys.add(key)
            self.dropped_list.addItem(norm)

    # ---- 界面逻辑 ----
    def _rebuild_vm_list(self):
        self.vm_list.clear()
        for vm in self.cfg.get("vms", []):
            target = vm.get("target") or "(自动: 桌面/trans)"
            cb = QCheckBox(f"{vm.get('name', '')}  →  {target}")
            cb.setChecked(True)
            # 注意: 不要用 addItem(str) 的返回值,该包装对象已失效(setItemWidget 会静默失效)
            item = QListWidgetItem()
            self.vm_list.addItem(item)
            self.vm_list.setItemWidget(item, cb)

    def _selected_vms(self):
        return [self.cfg["vms"][i] for i in range(self.vm_list.count())
                if self.vm_list.itemWidget(self.vm_list.item(i)).isChecked()]

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

    def open_config(self):
        dlg = ConfigDialog(self.cfg, self)
        if dlg.exec_():
            save_config(config_path(), self.cfg)
            self._rebuild_vm_list()
            self.log("配置已保存")

    def start_transfer(self):
        vms = self._selected_vms()
        if not vms:
            self.log("✗ 请至少勾选一台虚拟机")
            return
        if not self.dropped:
            self.log("✗ 请先拖入文件或文件夹")
            return
        self.transfer_btn.setEnabled(False)
        self.log_view.clear()
        self.log(f"[{datetime.now():%H:%M:%S}] 开始传输 {len(self.dropped)} 项 → {len(vms)} 台虚拟机")
        worker = TransferWorker(vms, list(self.dropped))
        worker.log_signal.connect(self.log)
        worker.finished_signal.connect(self._on_transfer_finished)
        self.worker = worker
        worker.start()

    def _on_transfer_finished(self, ok: bool):
        self.transfer_btn.setEnabled(True)
        if ok:
            self.log("✅ 全部传输完成")
        else:
            self.log("⚠ 部分传输失败,详情见上方日志")

    def closeEvent(self, event):
        """传输中关窗会销毁运行中的 QThread → 必须拦截。

        选择「是」:非阻塞等待 — 禁用窗口,传输结束后由
        finished_signal 触发 close() 完成退出(不会销毁运行中的线程)。
        """
        worker = self.worker
        if worker is not None and worker.isRunning():
            ret = QMessageBox.question(
                self, "退出确认", "传输正在进行中,确定要退出吗?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ret == QMessageBox.Yes:
                # 对话框的嵌套事件循环运行期间,传输可能已经结束
                # (finished_signal 已发出),此时再查一次:
                # 已结束 → 直接正常关闭,不延迟、不连接已发出的信号
                if not worker.isRunning():
                    event.accept()
                    return
                self.log("⏳ 传输仍在进行,完成后将自动退出…")
                worker.finished_signal.connect(self.close)
                self.setEnabled(False)
            event.ignore()
            return
        event.accept()

    def log(self, msg: str):
        self.log_view.append(msg)
        self.log_view.verticalScrollBar().setValue(
            self.log_view.verticalScrollBar().maximum())


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_QSS)
    win = MainWindow()
    x, y = win.position_on_screen()
    win.move(x, y)
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
