# 萌灵摄像头管理 (mengLing Camera Management)

基于 Python 的监控设备管理 Web 系统，支持设备发现、RTSP 配置、HLS 实时预览与监控大屏。

## 功能

- **设备管理** — 添加、编辑、删除摄像头，支持品牌预设（海康威视 / 大华 / 宇视）
- **设备发现** — ONVIF WS-Discovery + TCP 端口扫描，SSE 实时推送扫描结果
- **实时预览** — HLS（hls.js）播放，支持暂停/播放/全屏，自动切换主/子码流
- **在线检测** — TCP 连通性检测，实时显示在线/离线状态
- **监控大屏** — 创建分享链接，无需登录即可查看多路摄像头画面
- **密码管理** — 默认密码首次登录强制修改

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.9+, Flask, Flask-Login |
| 前端 | Jinja2, hls.js |
| 流媒体 | FFmpeg (HLS 切片) |
| 存储 | JSON 文件 (data/*.json) |
| 发现 | ONVIF WS-Discovery, TCP 端口扫描 |

## 快速开始

```bash
# 克隆
git clone git@github.com:mgodex/camera-management-python.git
cd camera-management-python

# 安装依赖
pip install -r requirements.txt

# 启动（确保已安装 FFmpeg）
python run.py
```

打开 http://localhost:5500 ，默认账号 `admin` / `no-password`。

## 项目结构

```
camera-management-python/
├── backend/
│   ├── api/           # Flask 路由
│   │   ├── auth.py         # 登录/登出/改密
│   │   ├── cameras.py      # 摄像头 CRUD + 扫描
│   │   ├── dashboard.py    # 监控大屏 CRUD
│   │   ├── pages.py        # 页面路由
│   │   └── stream.py       # HLS/MJPEG 流
│   ├── services/      # 业务逻辑
│   │   ├── auth_service.py       # 用户认证
│   │   ├── camera_service.py     # 摄像头 + 发现
│   │   ├── dashboard_service.py  # 大屏管理
│   │   └── stream_service.py     # HLS/MJPEG 流管理
│   └── utils/
│       ├── response.py  # 统一响应格式
│       └── storage.py   # JSON 文件存储
├── frontend/
│   ├── templates/  # Jinja2 模板
│   └── static/css/ # 样式
├── data/            # JSON 数据文件
├── run.py           # 入口
└── requirements.txt
```

## 品牌预设

| 品牌 | 主码流 | 子码流 |
|---|---|---|
| 海康威视 | `/stream2` | `/stream1` |
| 大华 | `subtype=0` | `subtype=1` |
| 宇视 | `/live/main` | `/live/sub` |

## 链接

- 萌灵工具软件: https://mengling.meng.me/
- 作者博客: https://www.meng.me/
- GitHub: https://github.com/mgodex/camera-management-python
