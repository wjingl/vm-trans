# VM Trans — 拖拽传文件到虚拟机

把文件/文件夹拖进窗口,勾选目标虚拟机,点「传输」,自动通过 SSH/SFTP 传到
每台虚拟机的 `桌面/trans` 文件夹(不存在自动创建)。

## 使用

1. 运行 `dist\vm-trans\vm-trans.exe`(或 `python main.py` 以源码运行)
2. 首次启动自动生成 `config.json`(与 exe 同目录),点「⚙ 配置」编辑
3. 拖入文件/文件夹 → 勾选虚拟机 → 点「🚀 传输」

> 分发包为 `dist\vm-trans-0.4.zip`:解压后双击文件夹里的 `vm-trans.exe` 即可(启动约 0.8 秒)。

## 配置说明(config.json)

- `name` — 显示名称
- `user` / `password` — SSH 用户名和密码(密码认证)
- `ip` — 纯 IP(如 `192.168.163.130`),或整段粘贴虚拟机里 `ip a` 的输出,自动提取地址
- `target` — 目标目录;留空 = 自动解析桌面目录(`~/桌面` 或 `~/Desktop`)下的 `trans`

## 虚拟机侧要求

- 已安装并启动 openssh-server:`sudo apt install openssh-server && sudo systemctl enable ssh`
- 虚拟机需与主机网络互通(如桥接或 NAT 端口转发)

## Linux 版(虚拟机内反向传输到 Windows)

在 Linux 虚拟机中运行同一工具,拖入文件后自动传输到 Windows 主机的
`W:\0_temp\VM_TRAN`(自动传输开关同样适用)。

### Windows 侧准备(一次)

1. 启用 OpenSSH 服务器:设置 → 系统 → 可选功能 → 添加功能 → OpenSSH 服务器
2. 启动服务:`Start-Service sshd`;设置 → 应用 → 启动,将 OpenSSH Server 设为自动
3. 防火墙放行 22 端口(启用服务时通常自动添加规则)
4. 确认 VM 可访问主机:`ping 192.168.163.1`(VMnet8 网关地址,与虚拟机同网段)

### 虚拟机内安装

```bash
cd <解压目录>
./install.sh        # 自动装依赖、建虚拟环境、创建桌面快捷方式
```

安装后:

- 启动:应用列表「VM Trans」或 `./run.sh`
- 首次使用:编辑 `~/.config/vm-trans/config.json`,在虚拟机配置中填入 Windows
  用户密码(用户名默认 `wjl`,IP 默认 `192.168.163.1`,目标目录
  `W:/0_temp/VM_TRAN` 可改)
- 传输目标目录不存在时自动创建

> 注:Windows OpenSSH 的 SFTP 对盘符路径(W:/...)的支持,如遇失败,可把
> `target` 改为绝对 POSIX 形式(如 `/W:/0_temp/VM_TRAN`)或映射后重试。

## 重新打包

双击 `build.bat`。产物为 onedir 文件夹 `dist\vm-trans\`(启动快,不等待解压);
分发时将整个文件夹压缩为 zip。构建使用独立环境 `.build-venv\`(pip 版 PyQt5,
不含 conda 版 Qt 冗余组件)。
