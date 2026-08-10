"""SSH/SFTP 传输逻辑。"""
import os
import stat

import paramiko

from config import parse_ip

# 注意: paramiko SSHClient.connect() 的参数是 timeout(建连)/auth_timeout/banner_timeout,
# 没有 connect_timeout(那是 fabric 等上层库的参数); brief 原值会导致 TypeError。
SFTP_DEFAULTS = {"timeout": 10, "auth_timeout": 10}


def pick_desktop_dir(lines: str) -> str | None:
    """从 `ls -d ~/桌面 ~/Desktop` 的输出中挑第一个存在的目录。"""
    for line in (lines or "").splitlines():
        line = line.strip()
        if line:
            return line
    return None


def build_file_list(local_path: str) -> list[tuple[str, str]]:
    """展开为 [(本地绝对路径, 相对路径)]。文件→本身;文件夹→递归全部文件。"""
    if not os.path.exists(local_path):
        raise FileNotFoundError(f"文件不存在: {local_path}")
    result = []
    if os.path.isfile(local_path):
        result.append((local_path, os.path.basename(local_path)))
    else:
        for root, dirs, files in os.walk(local_path):
            dirs.sort()
            for name in sorted(files):
                full = os.path.join(root, name)
                rel = os.path.relpath(full, local_path)
                result.append((full, rel.replace(os.sep, "/")))
    return result


def sftp_upload(sftp, local_abs: str, rel: str, remote_base: str) -> str:
    """上传单个文件,自动创建父目录,返回远程完整路径。"""
    remote_path = f"{remote_base}/{rel}"
    parent = os.path.dirname(remote_path)
    _makedirs(sftp, parent)
    sftp.put(local_abs, remote_path)
    return remote_path


def _makedirs(sftp, remote_dir: str) -> None:
    parts = [p for p in remote_dir.split("/") if p]
    path = ""
    for part in parts:
        path += "/" + part
        try:
            sftp.stat(path)
        except OSError:  # paramiko 5.x 对缺失路径抛普通 IOError(OSError),而非 FileNotFoundError
            sftp.mkdir(path)


def sftp_upload_recursive(sftp, local_path: str, remote_dir: str) -> list[str]:
    """整体递归上传(文件夹→目录;文件→直接上传),返回远程路径列表。"""
    uploaded = []
    if os.path.isfile(local_path):
        uploaded.append(sftp_upload(sftp, local_path, os.path.basename(local_path), remote_dir))
    else:
        name = os.path.basename(local_path.rstrip("/\\"))
        base = f"{remote_dir}/{name}"
        _makedirs(sftp, base)
        for local_abs, rel in build_file_list(local_path):
            uploaded.append(sftp_upload(sftp, local_abs, rel, base))
    return uploaded


def _run_remote(client: paramiko.SSHClient, cmd: str) -> str:
    _, stdout, stderr = client.exec_command(cmd, timeout=15)
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()
    return f"{out}\n{err}" if err else out


def _connect(vm: dict) -> tuple[paramiko.SSHClient, paramiko.SFTPClient]:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=parse_ip(vm["ip"]),
        username=vm.get("user", ""),
        password=vm.get("password", ""),
        **SFTP_DEFAULTS,
    )
    return client, client.open_sftp()


def transfer_to_vm(vm: dict, items: list[str], log: callable, progress: callable = None) -> bool:
    """完整传输流程,返回是否全部成功。log(msg) 追加日志;progress(done, total)。"""
    progress = progress or (lambda done, total: None)
    name = vm.get("name", "")
    log(f"=== 开始传输到 {name} ({vm.get('ip', '')}) ===")
    valid: list[tuple[str, int]] = []
    for item in items:
        try:
            file_count = len(build_file_list(item))
        except FileNotFoundError:
            log(f"✗ {item}: 文件不存在,跳过")
            continue
        valid.append((item, file_count))
    if not valid:
        log("✗ 没有可传输的文件")
        return False
    total = sum(count for _, count in valid)
    done = 0
    try:
        client, sftp = _connect(vm)
    except Exception as e:
        log(f"✗ 连接失败: {e}")
        return False
    try:
        home_output = _run_remote(client, "echo $HOME; ls -d ~/桌面 ~/Desktop 2>/dev/null")
        lines = home_output.splitlines()
        home = lines[0].strip() if lines else ""
        desktop = pick_desktop_dir("\n".join(lines[1:]))
        if not desktop and home:
            desktop = f"{home}/桌面"
            try:
                sftp.mkdir(desktop)
            except OSError:
                pass
        if not desktop:
            log("✗ 无法解析桌面目录")
            return False
        trans_dir = (vm.get("target") or f"{desktop}/trans").rstrip("/")
        _makedirs(sftp, trans_dir)
        log(f"目标目录: {trans_dir}")
        ok = True
        for item, _ in valid:
            try:
                paths = sftp_upload_recursive(sftp, item, trans_dir)
                done += len(paths)
                log(f"✓ {os.path.basename(item.rstrip('/\\\\'))}")
            except Exception as e:
                ok = False
                log(f"✗ {os.path.basename(item.rstrip('/\\\\'))}: {e}")
            progress(done, total)
        return ok
    except Exception as e:
        log(f"✗ 传输失败: {e}")
        return False
    finally:
        sftp.close()
        client.close()
