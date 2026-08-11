#!/usr/bin/env bash
# VM Trans Linux 版安装脚本:一条命令装好,启动即用。
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_DIR="$HOME/.config/vm-trans"
VENV_DIR="$APP_DIR/.venv"

echo "==> 安装系统依赖(PyQt5 运行库)..."
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip \
    libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-keysyms1 \
    libxcb-shape0 libxcb-render-util0 libegl1 libfontconfig1

echo "==> 创建 Python 虚拟环境并安装依赖..."
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -q PyQt5 paramiko

echo "==> 生成默认配置..."
mkdir -p "$CONFIG_DIR"
if [ ! -f "$CONFIG_DIR/config.json" ]; then
  cat > "$CONFIG_DIR/config.json" <<'EOF'
{
  "auto_transfer": true,
  "vms": [
    {
      "name": "Windows 主机",
      "user": "wjl",
      "password": "",
      "ip": "192.168.163.1",
      "target": "W:/0_temp/VM_TRAN"
    }
  ]
}
EOF
  echo "    已创建 $CONFIG_DIR/config.json —— 请编辑填入 Windows 用户密码"
else
  echo "    已有配置,保留不动"
fi

echo "==> 创建启动脚本..."
cat > "$APP_DIR/run.sh" <<EOF
#!/usr/bin/env bash
cd "$APP_DIR"
exec "$VENV_DIR/bin/python" main.py
EOF
chmod +x "$APP_DIR/run.sh"

echo "==> 创建桌面快捷方式..."
mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/vm-trans.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=VM Trans
Comment=拖拽文件传输到 Windows 主机
Exec=$APP_DIR/run.sh
Terminal=false
Categories=Utility;
EOF

echo "==> 安装完成!"
echo "    运行: $APP_DIR/run.sh  或在应用列表搜索「VM Trans」"
echo "    配置: ~/.config/vm-trans/config.json(填 Windows 用户密码)"
echo "    前提: Windows 已启用 OpenSSH Server;虚拟机与主机 VMnet8 网络互通"
