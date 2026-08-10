"""VM Trans 主窗口:拖拽文件 → 勾选虚拟机 → SFTP 传输。"""
import os
import sys
from datetime import datetime

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication, QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QPushButton, QScrollArea, QTextEdit, QVBoxLayout,
    QWidget,
)

import transfer
from config import config_path, ensure_config, load_config, save_config


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
        for vm in self.vms:
            ok = transfer.transfer_to_vm(vm, self.items, self.log_signal.emit)
            all_ok = all_ok and ok
        self.finished_signal.emit(all_ok)


class ConfigDialog(QDialog):
    """增删改虚拟机配置。"""

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.rows = []
        self.setWindowTitle("虚拟机配置")
        self.resize(560, 420)
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
        frame.setFrameShape(QFrame.StyledPanel)
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
        self.resize(420, 380)
        self.cfg = ensure_config(config_path())
        self.dropped = []

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # 虚拟机多选列表
        layout.addWidget(QLabel("目标虚拟机:"))
        self.vm_list = QListWidget()
        self.vm_list.setMaximumHeight(90)
        layout.addWidget(self.vm_list)

        # 拖放区域
        self.drop_area = QLabel("把文件/文件夹拖到这里\n(支持多选)", self)
        self.drop_area.setAlignment(Qt.AlignCenter)
        self.drop_area.setMinimumHeight(80)
        self.drop_area.setStyleSheet(
            "QLabel { border: 2px dashed #888; border-radius: 6px; background: #f8f8f8; }"
        )
        self.drop_area.setAcceptDrops(True)
        layout.addWidget(self.drop_area)

        self.dropped_list = QListWidget()
        self.dropped_list.setMaximumHeight(80)
        layout.addWidget(self.dropped_list)

        btn_row = QHBoxLayout()
        self.transfer_btn = QPushButton("🚀 传输")
        self.transfer_btn.clicked.connect(self.start_transfer)
        config_btn = QPushButton("⚙ 配置")
        config_btn.clicked.connect(self.open_config)
        btn_row.addWidget(self.transfer_btn)
        btn_row.addWidget(config_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("Consolas", 9))
        layout.addWidget(self.log_view, 1)

        self._rebuild_vm_list()

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
        if norm not in self.dropped:
            self.dropped.append(norm)
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
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.add_dropped(url.toLocalFile())

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

    def log(self, msg: str):
        self.log_view.append(msg)
        self.log_view.verticalScrollBar().setValue(
            self.log_view.verticalScrollBar().maximum())


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
