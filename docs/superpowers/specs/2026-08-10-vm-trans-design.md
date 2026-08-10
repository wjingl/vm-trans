# VM Trans — 拖拽文件 SSH 传输工具 设计文档

日期:2026-08-10
状态:已获用户批准(方案 A)

## 1. 目标

在 Windows 上提供一个独立 exe,启动后弹出一个小窗口。用户把文件/文件夹拖进窗口,勾选目标虚拟机,点「传输」按钮,工具通过 SSH(密码认证)将内容递归传输到每台虚拟机的**桌面/trans** 文件夹。不依赖共享文件夹。

## 2. 技术栈

- Python 3.13(Anaconda,已装)
- PyQt5(已装,原生拖拽支持)
- paramiko(需 pip 安装,SFTP 传输)
- PyInstaller(需 pip 安装,`--onefile --noconsole` 打包单 exe)

## 3. 界面(约 380×320 小窗口)

- 顶部:虚拟机列表,每台一行复选框,显示「名称 — 目标路径」,可多选
- 中部:拖放区域,接受文件/文件夹拖入(支持多选),显示已拖入项列表
- 底部:「传输」按钮 + 滚动日志区 + 「配置」按钮(打开配置编辑对话框)

## 4. 配置 config.json(exe 同目录,首次启动自动生成)

```json
{
  "vms": [
    {
      "name": "VMware Ubuntu",
      "user": "wjl",
      "password": "114514",
      "ip": "192.168.163.130",
      "target": ""
    }
  ]
}
```

- `ip`:纯 IP(如 `192.168.163.130`)或整段粘贴 `ip a` 输出文本,程序自动提取第一个非回环 IPv4(排除 127.0.0.1/169.254 链路本地)
- `user`/`password`:SSH 认证,密码认证
- `target`:留空 = 自动解析桌面目录下的 `trans`;也可显式覆盖

## 5. 传输流程(每台勾选的虚拟机)

1. SSH 连接(密码认证,`connect_timeout` 10s)
2. 远程解析桌面目录:依次探测 `~/桌面`、`~/Desktop`(适配中文/英文系统),取第一个存在的
3. 确保 `<桌面>/trans` 存在,不存在则 `mkdir -p`
4. 递归 SFTP 传输每个拖入项:文件直接传,文件夹整体递归(UTF-8 文件名安全)
5. 同名文件覆盖
6. 日志区逐项显示成功/失败及目标路径

## 6. 错误处理

- 每台虚拟机独立传输:一台失败不影响其他台
- 常见错误(连接失败、认证失败、目录解析失败)在日志区显示可读的中文提示
- 拖入重复项自动去重

## 7. 目录结构

```
W:\0_proj\VM_TRAN\
├── main.py              # 入口:PyQt5 窗口
├── config.py            # 配置读写 + IP 解析
├── transfer.py          # SSH/SFTP 传输逻辑
├── requirements.txt     # paramiko, PyQt5, pyinstaller
├── build.bat            # 打包脚本
└── docs/superpowers/specs/
```

## 8. 打包

`pyinstaller --onefile --noconsole --name vm-trans main.py`,产物 `dist/vm-trans.exe`,双击即用,config.json 生成在 exe 同目录。
