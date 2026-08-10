import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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


def test_main_window_drop_text_set():
    win = main.MainWindow()
    win.add_dropped("C:/a.txt")
    win.add_dropped("C:/a.txt")  # 重复去重
    assert win.dropped_items() == ["C:/a.txt"]


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
