import os
from pathlib import Path

import pytest

from transfer import build_file_list, pick_desktop_dir


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
