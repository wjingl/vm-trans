import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtGui import QCloseEvent
from PyQt5.QtWidgets import QApplication, QPushButton

import main

app = QApplication.instance() or QApplication([])


def test_main_window_builds(tmp_path, monkeypatch):
    cfg = {"vms": [{"name": "A", "user": "u", "password": "p",
                    "ip": "192.168.1.1", "target": ""}]}
    monkeypatch.setattr(main, "config_path", lambda: str(tmp_path / "config.json"))
    win = main.MainWindow()
    assert win.count_checkboxes() == 1
    assert win.checkbox_states() == {True}  # 默认勾选


def test_main_window_drop_text_set(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "config_path", lambda: str(tmp_path / "config.json"))
    win = main.MainWindow()
    win.add_dropped("C:/a.txt")
    win.add_dropped("C:/a.txt")  # 重复去重
    assert win.dropped_items() == ["C:/a.txt"]


class _RunningWorker(main.TransferWorker):
    """模拟运行中的传输线程(isRunning 恒真,直到手动停止)。"""

    def __init__(self):
        super().__init__([], [])
        self._running = True

    def isRunning(self):
        return self._running


def test_main_window_close_without_worker(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "config_path", lambda: str(tmp_path / "config.json"))
    win = main.MainWindow()
    event = QCloseEvent()
    win.closeEvent(event)
    assert event.isAccepted()  # 无传输 → 直接关闭


def test_main_window_close_with_running_worker(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "config_path", lambda: str(tmp_path / "config.json"))
    win = main.MainWindow()
    worker = _RunningWorker()
    win.worker = worker
    monkeypatch.setattr(main.QMessageBox, "question",
                        lambda *a, **k: main.QMessageBox.No)
    event = QCloseEvent()
    win.closeEvent(event)
    assert not event.isAccepted()  # 选「否」→ 取消关闭
    monkeypatch.setattr(main.QMessageBox, "question",
                        lambda *a, **k: main.QMessageBox.Yes)
    event = QCloseEvent()
    win.closeEvent(event)
    assert not event.isAccepted()  # 选「是」→ 延迟到传输结束后关闭
    worker._running = False
    event = QCloseEvent()
    win.closeEvent(event)
    assert event.isAccepted()  # 线程已结束 → 正常关闭


def test_close_race_finish_during_dialog(tmp_path, monkeypatch):
    """回归:确认对话框打开期间传输结束(选「是」),应正常关闭而非卡死。"""
    monkeypatch.setattr(main, "config_path", lambda: str(tmp_path / "config.json"))
    win = main.MainWindow()
    worker = _RunningWorker()
    win.worker = worker
    monkeypatch.setattr(main.QMessageBox, "question",
                        lambda *a, **k: main.QMessageBox.Yes)
    # 进对话框前第一次 isRunning() 返回 True(进入对话框分支);
    # 对话框返回后第二次 isRunning() 返回 False → 模拟传输在嵌套事件循环中完成
    state = {"n": 0}
    def fake_is_running():
        state["n"] += 1
        return state["n"] == 1
    monkeypatch.setattr(worker, "isRunning", fake_is_running)
    event = QCloseEvent()
    win.closeEvent(event)
    assert event.isAccepted()  # 传输已在对话框期间完成 → 直接关闭,不延迟
    assert state["n"] == 2  # 确认确实走了「对话框后复查」路径


def test_config_dialog_delete_row():
    cfg = {"vms": [
        {"name": "A", "user": "u", "password": "p", "ip": "192.168.1.1", "target": ""},
        {"name": "B", "user": "u", "password": "p", "ip": "192.168.1.2", "target": ""},
    ]}
    dlg = main.ConfigDialog(cfg)
    assert len(dlg.rows) == 2
    frame = dlg.rows[0][0]
    del_btn = frame.findChild(QPushButton)
    assert del_btn is not None and del_btn.text() == "删除"
    del_btn.click()
    assert len(dlg.rows) == 1
    assert dlg.rows[0][1].text() == "B"
