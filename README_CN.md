# GoPro Extractor

一款 macOS 桌面应用，用于从加密的 iPad 备份中提取 GoPro Quik 的视频和照片，并自动按拍摄日期整理到本地存储或 NAS。

## 为什么需要这个工具？

iPad 上的 GoPro Quik 将所有媒体文件存储在应用沙盒中，无法通过 iTunes 文件共享或"文件"App 访问。获取原始相机文件的唯一方式是通过**加密的 iPad 备份**——本工具自动完成整个流程：备份解密、GoPro 媒体识别、基于元数据的日期归类和去重。

## 功能特性

- **两种操作模式** — 创建新的 iPad 备份，或从已有备份中提取
- **智能文件识别** — 仅提取真正的 GoPro 相机文件（GH/GX/GOPR/GL/GP/trimmed），忽略应用缩略图和缓存
- **日期归类** — 根据拍摄日期自动整理到 `YYYY/MM/` 目录结构
- **去重检测** — 基于 SHA-256 哈希跟踪，跳过已导出的文件
- **SMB/NAS 优化** — 本地镜像策略，确保网络挂载上的备份解密可靠性
- **实时进度** — 导出过程中显示进度条和计时器
- **并发提取** — 多线程解密，对 SMB 错误自动重试

## 界面预览

```
┌─────────────────────────────────┐
│  GoPro Extractor                │
│                                 │
│  请选择操作：                     │
│                                 │
│  [+] 创建 iPad 备份              │
│  [📦] 从已有备份中提取            │
└─────────────────────────────────┘
```

## 前置条件

- **macOS**（Apple Silicon 或 Intel）
- **libimobiledevice** — 用于 iPad 通信
- **Python 3.10+** — 后端运行环境（仅开发时需要）
- **Node.js 18+** — 构建工具（仅开发时需要）
- **ffprobe**（可选）— 用于提取视频拍摄日期

### 安装依赖（开发环境）

```bash
brew install libimobiledevice
brew install python node
brew install ffmpeg  # 可选，用于视频日期元数据
```

## 快速开始（使用打包好的应用）

1. 从 Releases 下载 `GoPro Extractor-x.x.x-arm64.dmg`
2. 拖入"应用程序"文件夹并打开
3. 选择**从已有备份中提取**（如果已有 iPad 备份）或**创建 iPad 备份**（需先通过 USB 连接 iPad）
4. 输入备份加密密码
5. 选择导出目录（本地磁盘或 NAS 挂载路径）
6. 完成 — 文件已按 `<导出目录>/GoPro/YYYY/MM/` 整理

## 开发环境搭建

```bash
# 克隆项目
cd gopro-extractor

# 安装 Node.js 依赖
npm install

# 创建 Python 虚拟环境
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

# 启动开发模式
npm run dev
```

## 构建打包

```bash
# 完整构建：React 前端 + Python 后端 + macOS DMG
npm run build

# 单独构建
npm run build:renderer   # Vite 构建（React）
npm run build:python     # PyInstaller（Python 后端）
```

输出文件：
- `release/GoPro Extractor-x.x.x-arm64.dmg` — 可分发的安装包
- `release/mac-arm64/GoPro Extractor.app` — 独立应用

## 项目结构

```
gopro-extractor/
├── electron/               # Electron 主进程
│   ├── main.js             # 窗口管理、IPC 处理
│   ├── preload.js          # 上下文桥接（渲染进程 ↔ 主进程）
│   └── python-bridge.js    # 与 Python 的 JSON-RPC 通信
├── src/                    # React 前端
│   ├── App.jsx             # 主界面（模式选择、提取流程）
│   ├── components/         # StatusCard、ProgressBar
│   └── hooks/              # useBackend、useDirectoryPicker
├── backend/                # Python 后端
│   ├── main.py             # JSON-RPC 服务器（stdin/stdout）
│   ├── device.py           # iPad 检测（libimobiledevice）
│   ├── backup.py           # 备份创建（idevicebackup2）
│   ├── extractor.py        # 备份解密 + GoPro 媒体提取
│   ├── dedup.py            # SHA-256 去重数据库
│   ├── uploader.py         # NAS 文件上传
│   ├── metadata.py         # EXIF/视频日期提取
│   └── models.py           # 数据模型
├── config/
│   └── default.yaml        # 默认配置
├── scripts/
│   └── check-deps.sh       # 依赖检查脚本
└── package.json
```

## 架构设计

```
Electron (React 界面)  ←──IPC──→  Electron 主进程  ←──JSON-RPC/stdio──→  Python 后端
                                       │
                        ┌──────────────┼──────────────┐
                        ▼              ▼              ▼
                     iPad/USB     本地备份       NAS (SMB)
```

- **前端**：React + Tailwind CSS，两种独立模式（备份 / 提取）
- **IPC**：Electron IPC 桥接渲染进程与主进程
- **后端**：Python 子进程通过 stdin/stdout 的 JSON-RPC 通信
- **提取流程**：`iphone-backup-decrypt` 解密备份，按 GoPro 命名规则过滤文件，根据 EXIF/元数据日期归类

## 配置说明

编辑 `config/default.yaml`：

```yaml
backup:
  password: ""              # 备份加密密码
  reuse_existing: true      # 复用近期备份
  max_age_hours: 48         # 备份最大有效期（小时）

nas:
  mount_path: ""            # SMB 挂载路径（如 /Volumes/NAS/GoPro）
  organize_by_date: true    # 按 YYYY/MM/ 目录整理

staging:
  cleanup_after_upload: true

logging:
  level: INFO
```

## 工作原理

1. **备份解密** — 使用用户提供的密码打开加密 iPad 备份中的 `Manifest.db`
2. **媒体发现** — 查询 GoPro Quik 域中的文件（`GPCoordinatedStore-com.gopro.softtubes/Files/`）
3. **文件名过滤** — 仅保留符合 GoPro 相机命名规则的文件（`GH`、`GX`、`GOPR`、`GL`、`GP`、`trimmed`）
4. **并发提取** — 解密文件到本地临时目录，读取元数据获取日期，移动到导出目录
5. **去重处理** — 对每个文件计算 SHA-256 哈希，记录到本地 SQLite 数据库，避免重复导出

## 依赖检查

```bash
./scripts/check-deps.sh
```

## iPad 备份加密设置

首次使用前需要在 iPad 上启用加密备份：

1. 用 USB 线连接 iPad 到 Mac
2. 打开 **Finder**（macOS Catalina 及以上）
3. 在左侧栏选择 iPad
4. 勾选 **"加密本地备份"**
5. 设置一个密码（请牢记此密码，提取时需要输入）
6. 点击"立即备份"

## 常见问题

| 问题 | 解决方案 |
|------|----------|
| "Manifest.db not found" | 选择正确的备份文件夹（包含 UDID 子目录）— 应用会自动搜索最多 3 层子目录 |
| Errno 22 提取错误 | SMB 读取错误 — 应用会自动重试 3 次；部分文件在不稳定的网络连接下可能仍会失败 |
| "密码错误" | 确认在 Finder > iPad > 加密本地备份 中设置的密码 |
| 未找到 GoPro 文件 | 确保 iPad 上的 GoPro Quik 应用中有媒体文件，且备份是最近创建的 |
| 提取速度慢 | 如果备份在 NAS 上，首次解密会创建本地镜像（约需 1-2 分钟），后续提取会更快 |
| 磁盘空间不足 | 导出目录建议选择 NAS 或外置硬盘，避免本地磁盘空间不足 |

## 许可证

MIT
