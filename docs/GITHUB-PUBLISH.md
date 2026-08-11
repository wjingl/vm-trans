# GitHub 发布 SOP(VM Trans 项目)

> 用途:把本项目的源码和发行版发布到 GitHub。其他 agent 执行发布任务时按本文档操作。
> 最后验证:2026-08-11(v0.4 发布成功,仓库 wjingl/vm-trans)。

## 0. 前置条件

| 项目 | 位置/值 |
|---|---|
| GitHub token | 明文保存在 `C:\Users\wjl\Desktop\快捷配置信息.txt`,形如 `github_pat_...`(第一行以 `github_pat_` 开头) |
| gh CLI | `C:\Program Files\GitHub CLI\gh.exe`(winget 安装,但在 Git Bash 的 PATH 中**不可用**,必须用完整路径调用) |
| git | 项目内 `git` 命令可用(remote 已配置为 origin) |
| 发行版资产 | `dist\vm-trans-0.4.zip`(Windows)、`dist\vm-trans-linux.zip`(Linux),打包脚本见 `build.bat` |

**为什么需要 gh CLI(而不是只用 git):**
- `git push` 只能推代码;创建仓库(`gh repo create`)、创建 Release、上传发行版资产都需要 GitHub API
- gh 是官方 CLI,内部处理认证,比手写 curl API 简单
- 本机 gh 用 winget 安装后 PATH 未生效 → 统一用完整路径 `"/c/Program Files/GitHub CLI/gh.exe"`

## 1. 认证

```bash
GH="/c/Program Files/GitHub CLI/gh.exe"
TOKEN=$(grep -o 'github_pat_[A-Za-z0-9_]*' "C:/Users/wjl/Desktop/快捷配置信息.txt" | head -1)
printf '%s' "$TOKEN" | "$GH" auth login --with-token
"$GH" auth status   # 应显示 Logged in to github.com account wjingl
```

注意:token 只经管道传给 gh,不要 echo 到终端或写进任何文件。

## 2. 创建仓库并推送源码(首次)

```bash
cd /w/0_proj/VM_TRAN
"$GH" repo create vm-trans --public --source . --remote origin --push \
  --description "VM Trans — 拖拽文件经 SSH/SFTP 传输到虚拟机(Windows exe + Linux 版)"
```

- 已有 remote 时去掉 `--remote origin`
- 仓库已存在时用 `"$GH" repo view wjingl/vm-trans` 确认
- 源码本身随 git push 发布(`dist/` 已被 .gitignore 排除,这是预期的)

## 3. 创建 Release 并上传发行版

### 3a. Release 说明文件

写说明到项目内任意文件(注意:gh.exe 是 Windows 程序,**不认 Git Bash 的 `/tmp/...` 虚拟路径**,必须用 Windows 路径,如 `W:/0_proj/VM_TRAN/.superpowers/sdd/release-notes.md`)。

### 3b. 创建 Release 本体(不带资产)

```bash
"$GH" release create v0.4 \
  --title "v0.4" \
  --notes-file "W:/0_proj/VM_TRAN/.superpowers/sdd/release-notes.md" \
  --target master   # 必须显式指定!默认 main,本仓库默认分支是 master
```

### 3c. 上传资产 —— 网络特殊处理(关键!)

**网络环境**:本机对 GitHub 存在中间设备干扰:
- `api.github.com` 直连正常(HTTP 200)
- `uploads.github.com` 默认解析到新加坡节点(20.205.243.161),**gh 直接上传会报 HTTP 400**
- 实测 `uploads.github.com` 强制解析到 **20.205.243.161** 后上传成功(HTTP 201)

因此**不要用 `gh release upload`**,改用 curl + `--resolve` 指定可用 IP:

```bash
TOKEN=$(grep -o 'github_pat_[A-Za-z0-9_]*' "C:/Users/wjl/Desktop/快捷配置信息.txt" | head -1)
REL_ID=$("$GH" api repos/wjingl/vm-trans/releases/tags/v0.4 --jq .id)
# 每个资产一条命令;Content-Type 与文件类型对应
curl -s -X POST "https://uploads.github.com/repos/wjingl/vm-trans/releases/$REL_ID/assets?name=vm-trans-0.4.zip" \
  --resolve "uploads.github.com:443:20.205.243.161" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/zip" \
  -T dist/vm-trans-0.4.zip -w "HTTP %{http_code}\n"
```

成功标志:HTTP 201。若 20.205.243.161 失效,按「4. 网络故障排查」重新探测。

## 4. 网络故障排查(当 400/超时出现时)

```bash
# 1) 测各端点
curl -sI https://api.github.com -w "api: %{http_code}\n" -o /dev/null
# 2) 探测 uploads 的候选 IP(返回 401 表示是真实 GitHub 服务器;400 表示中间干扰;405 表示 Pages CDN 不可用)
for ip in 20.205.243.161 20.205.243.166 140.82.113.6; do
  curl -s -X POST "https://uploads.github.com/..." --resolve "uploads.github.com:443:$ip" \
    -H "Authorization: Bearer x" -w "IP $ip: HTTP %{http_code}\n" -o /dev/null
done
# 3) 找到 401 的 IP 后,用 --resolve 上传(见 3c)
```

经验值(2026-08-11 实测):
- `20.205.243.161`(官方解析):401 正常 / 201 上传成功 ✅
- `20.205.243.166`:301(不是上传端点)
- `185.199.108.133`(Pages CDN):405,不能上传
- `140.82.x.x`:400(中间干扰)

## 5. 验证清单

```bash
"$GH" release view v0.4        # 应列出 asset: vm-trans-0.4.zip / vm-trans-linux.zip
"$GH" repo view wjingl/vm-trans
git ls-remote --tags origin    # 应有 v0.4 tag
```

浏览器访问 https://github.com/wjingl/vm-trans/releases/tag/v0.4 确认资产可下载。

## 6. 常见坑速查

| 坑 | 表现 | 解决 |
|---|---|---|
| gh 找不到 | `gh: command not found` | 用完整路径 `"/c/Program Files/GitHub CLI/gh.exe"` |
| `--attach` 报 unknown flag | 新版本语法 | 资产是位置参数:`gh release create v0.4 file1.zip file2.zip` |
| release 建在 main | 默认 target 分支 | 显式加 `--target master` |
| notes 文件读不到 | `/tmp/xxx.md` 无效 | 用 Windows 路径(如 `W:/0_proj/VM_TRAN/...`) |
| 上传 400 | uploads 域名被干扰 | curl `--resolve` 指定 20.205.243.161(见 3c/4) |
| 上传 405 | 用错 IP(Pages CDN) | 换 401/201 的 IP(见 4) |
| 中文编码乱码 | PowerShell 读 UTF-8 无 BOM 脚本 | 部署类脚本用纯英文写(见 Windows 部署文档) |

## 7. 安全提醒

- token 权限较广且明文存于桌面文件,发布完成后建议轮换
- token 只经管道/env 使用,不落盘、不打印
