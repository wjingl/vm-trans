# VM Trans — 拖拽传文件到虚拟机

把文件/文件夹拖进窗口,勾选目标虚拟机,点「传输」,自动通过 SSH/SFTP 传到
每台虚拟机的 `桌面/trans` 文件夹(不存在自动创建)。

## 使用

1. 运行 `dist\vm-trans.exe`(或 `python main.py` 以源码运行)
2. 首次启动自动生成 `config.json`(与 exe 同目录),点「⚙ 配置」编辑
3. 拖入文件/文件夹 → 勾选虚拟机 → 点「🚀 传输」

## 配置说明(config.json)

- `name` — 显示名称
- `user` / `password` — SSH 用户名和密码(密码认证)
- `ip` — 纯 IP(如 `192.168.163.130`),或整段粘贴虚拟机里 `ip a` 的输出,自动提取地址
- `target` — 目标目录;留空 = 自动解析桌面目录(`~/桌面` 或 `~/Desktop`)下的 `trans`

## 虚拟机侧要求

- 已安装并启动 openssh-server:`sudo apt install openssh-server && sudo systemctl enable ssh`
- 虚拟机需与主机网络互通(如桥接或 NAT 端口转发)

## 重新打包

双击 `build.bat`。
