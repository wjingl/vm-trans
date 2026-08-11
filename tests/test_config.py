import os
from pathlib import Path

import pytest

from config import config_path, ensure_config, load_config, parse_ip, save_config

IPA_OUTPUT = """\
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    inet 127.0.0.1/8 scope host lo
       valid_lft forever preferred_lft forever
    inet6 ::1/128 scope host noprefixroute
       valid_lft forever preferred_lft forever
2: ens33: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc fq_codel state UP group default qlen 1000
    link/ether 00:0c:29:9d:72:cf brd ff:ff:ff:ff:ff:ff
    inet 192.168.163.130/24 brd 192.168.163.255 scope global dynamic noprefixroute ens33
       valid_lft 1587sec preferred_lft 1587sec
"""


def test_parse_ip_plain():
    assert parse_ip("192.168.163.130") == "192.168.163.130"


def test_parse_ip_from_ipa_output():
    assert parse_ip(IPA_OUTPUT) == "192.168.163.130"


def test_parse_ip_output_without_v4_raises():
    with pytest.raises(ValueError):
        parse_ip("1: lo: ... inet 127.0.0.1/8 ... only loopback")


def test_parse_ip_empty_raises():
    with pytest.raises(ValueError):
        parse_ip("")


def test_ensure_config_creates_default(tmp_path):
    p = str(tmp_path / "config.json")
    cfg = ensure_config(p)
    vm = cfg["vms"][0]
    assert vm["name"] == "VMware Ubuntu"
    assert vm["user"] == "wjl"
    assert vm["password"] == "114514"
    assert vm["ip"] == "192.168.163.130"
    assert Path(p).exists()
    assert cfg["auto_transfer"] is True


def test_load_config_roundtrip(tmp_path):
    p = str(tmp_path / "config.json")
    cfg = ensure_config(p)
    cfg["vms"][0]["target"] = "/tmp/other"
    save_config(p, cfg)
    assert load_config(p)["vms"][0]["target"] == "/tmp/other"


def test_load_config_invalid_json_raises(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("{ not json", encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(str(p))


def test_ensure_config_corrupt_file_raises_valueerror(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("{ not json", encoding="utf-8")
    with pytest.raises(ValueError):
        ensure_config(str(p))


def test_ensure_config_unwritable_path_raises_valueerror(tmp_path):
    p = str(tmp_path / "no" / "such" / "dir" / "config.json")
    with pytest.raises(ValueError):
        ensure_config(p)


def test_save_config_unwritable_path_raises_valueerror(tmp_path):
    p = str(tmp_path / "no" / "such" / "dir" / "config.json")
    with pytest.raises(ValueError):
        save_config(p, {"vms": []})


def test_config_path_linux_branch(monkeypatch):
    """Linux(非 Windows)非 frozen:配置放 ~/.config/vm-trans/。"""
    import config
    monkeypatch.setattr(config.os, "name", "posix")
    monkeypatch.setattr(config.sys, "frozen", False, raising=False)
    expected = os.path.expanduser("~/.config/vm-trans/config.json")
    assert config_path() == expected
