# VM Trans Linux 版(反向传输) 设计文档

日期:2026-08-11
状态:已获用户批准

## 1. 目标

在 Linux 虚拟机中运行同一套代码,拖入文件/文件夹后通过 SSH/SFTP 传输到 Windows 主机的 `W:\0_temp\VM_TRAN`。安装脚本一键安装,启动迅捷(venv 直接运行,约 1s),含自动传输开关(与 Windows 版一致)。

## 2. 网络与主机侧前提

- VM 在 VMnet8 NAT 网段(192.168.163.x),访问主机的地址为 **192.168.163.1**(VMnet8 适配器;192.168.0.123 为物理网卡,NAT 下 VM 不可达)
- Windows 需启用 OpenSSH Server(设置 → 系统 → 可选功能 → OpenSSH 服务器),确保 22 端口监听、防火墙放行
- Windows 用户:`wjl`;密码由部署时设置;SFTP 目标路径形式 `W:/0_temp/VM_TRAN` 部署时实测(若 OpenSSH sftp-server 不支持,备用方案写入部署文档)

## 3. 代码改动(最小化)

- `config.py`:
  - `config_path()`:非 frozen 且非 Windows(或 `os.name != "nt"`)时,返回 `~/.config/vm-trans/config.json`(Linux 惯例)
  - 默认配置新增 `"auto_transfer": true`(自动传输 spec,与 Linux 版共用)
- `transfer.py`:不动(显式 target 直接使用,桌面自动解析仅用于留空)
- `main.py`:自动传输功能(见 auto-transfer spec)天然跨平台,无额外改动
- 默认 config.json(Linux):`user=wjl`、`ip=192.168.163.1`、`target=W:/0_temp/VM_TRAN`

## 4. 安装脚本 install.sh

1. `apt install -y` PyQt5 运行依赖(libxcb-cursor0、libxkbcommon-x11-0、libegl1、libfontconfig1 等,按发行版补充)
2. `python3 -m venv .venv` → `pip install PyQt5 paramiko`
3. 生成默认 config.json(~/.config/vm-trans/)与启动脚本 `run.sh`
4. 创建桌面快捷方式 `vm-trans.desktop`(Exec=run.sh)

## 5. 验证

- Windows 上跑全部 41 测试(跨平台代码同一套)
- 端到端验证(VM 在线时):VM 拖文件 → Windows `W:\0_temp\VM_TRAN` 出现文件;OpenSSH 路径形式确认

## 6. 不做的事

- 不做 deb/AppImage 打包
- 不做 Windows 侧自定义接收端(用系统 OpenSSH Server)
