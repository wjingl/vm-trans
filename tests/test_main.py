import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QMimeData, QPoint, Qt, QUrl
from PyQt5.QtGui import QCloseEvent, QDragEnterEvent, QDropEvent
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
    win.auto_check.setChecked(False)  # 自动传输会启动真实传输线程;此测试只验证拖放链路本身
    win.add_dropped("C:/a.txt")
    win.add_dropped("C:/a.txt")  # 重复去重
    assert win.dropped_items() == ["C:/a.txt"]


def test_main_window_drop_dedups_case_insensitively(tmp_path, monkeypatch):
    """Windows 下去重应为大小写不敏感(case-sensitive 会重复传输同一文件)。"""
    monkeypatch.setattr(main, "config_path", lambda: str(tmp_path / "config.json"))
    win = main.MainWindow()
    win.auto_check.setChecked(False)  # 自动传输会启动真实传输线程;此测试只验证去重逻辑
    win.add_dropped("C:/Data/a.txt")
    win.add_dropped("c:/data/A.TXT")  # 仅大小写/反斜杠不同
    assert win.dropped_items() == ["C:/Data/a.txt"]


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


def test_main_window_falls_back_on_corrupt_config(tmp_path, monkeypatch):
    """回归:配置文件损坏时窗口必须仍能打开(默认配置),而不是静默崩溃。"""
    p = tmp_path / "config.json"
    p.write_text("{ not json", encoding="utf-8")
    monkeypatch.setattr(main, "config_path", lambda: str(p))
    monkeypatch.setattr(main.QMessageBox, "critical", lambda *a, **k: None)
    win = main.MainWindow()
    assert win.cfg == main.DEFAULT_CONFIG
    assert win.count_checkboxes() == 1


def test_worker_emits_finished_signal_on_unexpected_error(monkeypatch):
    """回归:transfer_to_vm 意外抛异常时 finished_signal 仍必须发出(传输按钮才能恢复)。"""

    import transfer  # main 延迟导入 transfer,测试直接 monkeypatch 模块本身

    def boom(vm, items, log, progress=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(transfer, "transfer_to_vm", boom)
    received: list[bool] = []
    worker = main.TransferWorker([{"name": "A", "ip": "10.0.0.1"}], ["x"])
    worker.finished_signal.connect(received.append)
    worker.run()
    assert received == [False]


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
    # 偏移几何原点:屏幕不在原点(多显示器)时绝对坐标必须包含 geo.x()/geo.y()
    assert x == geo.x() + geo.width() - win.width() - 40
    assert y == geo.y() + (geo.height() - win.height()) // 2


def test_main_window_drop_through_event_mechanism(tmp_path, monkeypatch):
    """回归:日志区不吞拖放,drop 经事件机制冒泡到 MainWindow 生效。"""
    monkeypatch.setattr(main, "config_path", lambda: str(tmp_path / "config.json"))
    win = main.MainWindow()
    win.auto_check.setChecked(False)  # 自动传输会启动真实传输线程;此测试只验证拖放事件链路
    assert win.log_view.acceptDrops() is False  # 日志区不得吞掉拖拽
    assert "font-family: Consolas" in main.APP_QSS  # 日志区等宽字体不被全局 QSS 覆盖
    src = str(tmp_path / "a.txt")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(src)])
    pos = QPoint(10, 10)
    QApplication.sendEvent(win, QDragEnterEvent(pos, Qt.CopyAction, mime,
                                                Qt.LeftButton, Qt.NoModifier))
    QApplication.sendEvent(win, QDropEvent(pos, Qt.CopyAction, mime,
                                           Qt.LeftButton, Qt.NoModifier))
    assert win.dropped_items() == [os.path.normpath(src).replace("\\", "/")]


def test_drop_area_active_property_toggles(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "config_path", lambda: str(tmp_path / "config.json"))
    win = main.MainWindow()
    assert win.drop_area.property("active") in (None, False)
    win._set_drop_active(True)
    assert win.drop_area.property("active") is True
    win._set_drop_active(False)
    assert win.drop_area.property("active") is False


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
    """回归:一次多文件拖入只触发一次自动传输(整体批次,而非逐文件触发)。"""
    win = _make_win(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(win, "start_transfer", lambda auto=False: calls.append(auto))
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(tmp_path / "a.txt")),
                  QUrl.fromLocalFile(str(tmp_path / "b.txt"))])
    pos = QPoint(10, 10)
    QApplication.sendEvent(win, QDragEnterEvent(pos, Qt.CopyAction, mime,
                                                Qt.LeftButton, Qt.NoModifier))
    QApplication.sendEvent(win, QDropEvent(pos, Qt.CopyAction, mime,
                                           Qt.LeftButton, Qt.NoModifier))
    assert calls == [True]  # 两个文件 → 只在拖放结束时触发一次
    assert len(win.dropped_items()) == 2  # 两项整体入队,未被拆分成两次传输


def test_drop_no_trigger_when_auto_off(tmp_path, monkeypatch):
    win = _make_win(tmp_path, monkeypatch, {"auto_transfer": False})
    calls = []
    monkeypatch.setattr(win, "start_transfer", lambda auto=False: calls.append(auto))
    win.add_dropped("C:/a.txt")
    win._maybe_auto_start()  # 拖放结束触发点
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
    win._maybe_auto_start()  # 拖放结束触发点
    assert calls == []
    assert "C:/a.txt" in win.dropped_items()


def test_start_transfer_reentry_ignored(tmp_path, monkeypatch):
    win = _make_win(tmp_path, monkeypatch)
    class Running:
        def isRunning(self):
            return True
    running = Running()
    win.worker = running
    win.add_dropped("C:/a.txt")
    win.start_transfer()  # 防重入:直接忽略
    assert win.worker is running  # 未被替换


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
