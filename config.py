"""配置读写与 IP 自动解析。"""
import ipaddress
import json
import os
import re
import sys
from pathlib import Path

DEFAULT_CONFIG = {
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

_INET_RE = re.compile(r"inet\s+(\d{1,3}(?:\.\d{1,3}){3})/")


def config_path() -> str:
    """与可执行文件(exe)或脚本同目录下的 config.json 绝对路径。"""
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).parent
    return str(base / "config.json")


def _is_usable_ipv4(ip: str) -> bool:
    if ip.startswith(("127.", "169.254.", "0.")) or ip == "255.255.255.255":
        return False
    try:
        ipaddress.IPv4Address(ip)
        return True
    except ipaddress.AddressValueError:
        return False


def parse_ip(text: str) -> str:
    """解析 IP:纯 IPv4 原样返回;否则当作 `ip a` 输出提取第一个非回环地址。"""
    text = (text or "").strip()
    if _is_usable_ipv4(text):
        return text
    for match in _INET_RE.finditer(text):
        ip = match.group(1)
        if _is_usable_ipv4(ip):
            return ip
    raise ValueError("无法从输入中解析出有效的 IPv4 地址(纯 IP 或 ip a 输出均可)")


def ensure_config(path: str) -> dict:
    if not os.path.exists(path):
        save_config(path, DEFAULT_CONFIG)
    return load_config(path)


def load_config(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise ValueError(f"配置文件 {path} 无法读取: {e}")


def save_config(path: str, cfg: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
