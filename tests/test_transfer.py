import os
from pathlib import Path

import pytest

import transfer
from transfer import (
    _makedirs,
    build_file_list,
    pick_desktop_dir,
    sftp_upload,
    sftp_upload_recursive,
)


def test_pick_desktop_chinese_first(tmp_path):
    # 注意: 远端 `ls -d` 输出恒用 "/" 分隔; 此处对 tmp_path 统一转 "/" 保持平台无关
    base = str(tmp_path).replace("\\", "/")
    lines = f"/home/wjl/桌面\n/home/wjl/Desktop\n".replace("/home/wjl", base)
    assert pick_desktop_dir(lines) == f"{base}/桌面"


def test_pick_desktop_english_only(tmp_path):
    lines = str(tmp_path / "Desktop")
    assert pick_desktop_dir(lines) == str(tmp_path / "Desktop")


def test_pick_desktop_none():
    assert pick_desktop_dir("") is None


def test_build_file_list_single_file(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("hello", encoding="utf-8")
    result = build_file_list(str(f))
    assert result == [(str(f), "a.txt")]


def test_build_file_list_directory_recursive(tmp_path):
    (tmp_path / "sub" / "deep").mkdir(parents=True)
    (tmp_path / "top.txt").write_text("t", encoding="utf-8")
    (tmp_path / "sub" / "inner.txt").write_text("i", encoding="utf-8")
    (tmp_path / "sub" / "deep" / "leaf.bin").write_bytes(b"\x00\x01")
    result = sorted(build_file_list(str(tmp_path)))
    rels = [rel for _, rel in result]
    assert rels == ["sub/deep/leaf.bin", "sub/inner.txt", "top.txt"]


def test_build_file_list_nonexistent_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_file_list(str(tmp_path / "missing"))


# ---------- review 修复后追加:mock SFTP 测试(不打开真实网络连接) ----------


class FakeStream:
    def __init__(self, data: bytes):
        self._data = data

    def read(self):
        return self._data


class FakeSSHClient:
    """exec_command 返回可读伪流;默认远端输出 HOME + 桌面目录。"""

    def __init__(self, output: str = "/home/wjl\n/home/wjl/桌面"):
        self.output = output
        self.closed = False

    def exec_command(self, cmd, timeout=15):
        return (None, FakeStream(self.output.encode("utf-8")), FakeStream(b""))

    def open_sftp(self):
        return FakeSFTP()

    def close(self):
        self.closed = True


class FakeSFTP:
    """记录 mkdir/put 调用;stat 一律视为目录不存在。"""

    def __init__(self):
        self.mkdirs: list[str] = []
        self.puts: list[tuple[str, str]] = []

    def stat(self, path):
        raise FileNotFoundError(path)

    def mkdir(self, path):
        self.mkdirs.append(path)

    def put(self, local_abs, remote_path):
        self.puts.append((local_abs, remote_path))

    def close(self):
        pass


def test_makedirs_creates_each_missing_segment():
    fake = FakeSFTP()
    _makedirs(fake, "/a/b/c")
    assert fake.mkdirs == ["/a", "/a/b", "/a/b/c"]


def test_makedirs_catches_paramiko_style_ioerror():
    # paramiko 5.x 对缺失的远端路径抛 IOError(errno.ENOENT)(普通 OSError,非 FileNotFoundError)
    class ParamikoStyleSFTP(FakeSFTP):
        def stat(self, path):
            raise IOError(2, "No such file")

    fake = ParamikoStyleSFTP()
    _makedirs(fake, "/a/b")
    assert fake.mkdirs == ["/a", "/a/b"]


def test_sftp_upload_creates_parent_dirs_and_puts(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("hello", encoding="utf-8")
    fake = FakeSFTP()
    remote = sftp_upload(fake, str(f), "sub/inner.txt", "/home/wjl/桌面/trans")
    assert remote == "/home/wjl/桌面/trans/sub/inner.txt"
    assert fake.puts == [(str(f), "/home/wjl/桌面/trans/sub/inner.txt")]
    assert fake.mkdirs == [
        "/home",
        "/home/wjl",
        "/home/wjl/桌面",
        "/home/wjl/桌面/trans",
        "/home/wjl/桌面/trans/sub",
    ]


def test_sftp_upload_recursive_preserves_structure(tmp_path):
    proj = tmp_path / "proj"
    (proj / "sub").mkdir(parents=True)
    (proj / "top.txt").write_text("t", encoding="utf-8")
    (proj / "sub" / "inner.txt").write_text("i", encoding="utf-8")
    fake = FakeSFTP()
    uploaded = sftp_upload_recursive(fake, str(proj), "/home/wjl/桌面/trans")
    assert uploaded == [
        "/home/wjl/桌面/trans/proj/top.txt",
        "/home/wjl/桌面/trans/proj/sub/inner.txt",
    ]
    assert "/home/wjl/桌面/trans/proj" in fake.mkdirs  # 基础目录由 _makedirs 创建
    assert [r for _, r in fake.puts] == [
        "/home/wjl/桌面/trans/proj/top.txt",
        "/home/wjl/桌面/trans/proj/sub/inner.txt",
    ]


def test_transfer_to_vm_success_uploads_to_desktop_trans(tmp_path, monkeypatch):
    f = tmp_path / "hello.txt"
    f.write_text("hi", encoding="utf-8")
    fake_sftp = FakeSFTP()
    fake_client = FakeSSHClient()  # HOME=/home/wjl,桌面=/home/wjl/桌面
    monkeypatch.setattr(transfer, "_connect", lambda vm: (fake_client, fake_sftp))
    vm = {"name": "test", "ip": "10.0.0.1", "target": ""}
    logs: list[str] = []
    assert transfer.transfer_to_vm(vm, [str(f)], logs.append) is True
    assert fake_sftp.puts == [(str(f), "/home/wjl/桌面/trans/hello.txt")]
    assert "/home/wjl/桌面/trans" in fake_sftp.mkdirs
    assert any("目标目录: /home/wjl/桌面/trans" in line for line in logs)
    assert fake_client.closed


def test_transfer_to_vm_no_desktop_returns_false(tmp_path, monkeypatch):
    f = tmp_path / "x.txt"
    f.write_text("x", encoding="utf-8")
    fake_sftp = FakeSFTP()
    fake_client = FakeSSHClient(output="")  # 远端无任何输出
    monkeypatch.setattr(transfer, "_connect", lambda vm: (fake_client, fake_sftp))
    vm = {"name": "test", "ip": "10.0.0.1", "target": ""}
    logs: list[str] = []
    assert transfer.transfer_to_vm(vm, [str(f)], logs.append) is False
    assert any("✗ 无法解析桌面目录" in line for line in logs)


def test_transfer_to_vm_missing_item_skipped_others_continue(tmp_path, monkeypatch):
    f = tmp_path / "ok.txt"
    f.write_text("ok", encoding="utf-8")
    missing = str(tmp_path / "gone.txt")
    fake_sftp = FakeSFTP()
    fake_client = FakeSSHClient()
    monkeypatch.setattr(transfer, "_connect", lambda vm: (fake_client, fake_sftp))
    vm = {"name": "test", "ip": "10.0.0.1", "target": ""}
    logs: list[str] = []
    assert transfer.transfer_to_vm(vm, [missing, str(f)], logs.append) is True
    assert any(f"✗ {missing}: 文件不存在,跳过" in line for line in logs)
    assert fake_sftp.puts == [(str(f), "/home/wjl/桌面/trans/ok.txt")]


def test_transfer_to_vm_all_missing_returns_false_before_connect(tmp_path, monkeypatch):
    def fail_connect(vm):
        raise AssertionError("所有项目不存在时不应建立连接")

    monkeypatch.setattr(transfer, "_connect", fail_connect)
    vm = {"name": "test", "ip": "10.0.0.1", "target": ""}
    logs: list[str] = []
    assert (
        transfer.transfer_to_vm(
            vm, [str(tmp_path / "a"), str(tmp_path / "b")], logs.append
        )
        is False
    )
    assert any("✗ 没有可传输的文件" in line for line in logs)


def test_transfer_to_vm_remote_failure_returns_false(tmp_path, monkeypatch):
    f = tmp_path / "ok.txt"
    f.write_text("ok", encoding="utf-8")

    class BoomClient(FakeSSHClient):
        def exec_command(self, cmd, timeout=15):
            raise RuntimeError("远程命令失败")

    fake_sftp = FakeSFTP()
    monkeypatch.setattr(transfer, "_connect", lambda vm: (BoomClient(), fake_sftp))
    vm = {"name": "test", "ip": "10.0.0.1", "target": ""}
    logs: list[str] = []
    assert transfer.transfer_to_vm(vm, [str(f)], logs.append) is False
    assert any("✗ 传输失败: 远程命令失败" in line for line in logs)
