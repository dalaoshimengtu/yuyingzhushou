

```markdown
 🎙️ 语音控制绘图工具

通过麦克风说出自然语言指令，即可完成绘图、修改、删除等操作。系统采用管道式架构，支持图形层记忆机制，可对每个图形进行独立持久化管理。

 📋 环境要求

- Python 3.8 或更高版本
- 操作系统：Windows / macOS / Linux
- 麦克风设备
- 推荐内存 ≥ 4GB

## 🚀 安装步骤

### 1. 克隆仓库并创建虚拟环境

```bash
git clone <你的仓库地址>
cd voice-drawing
python -m venv venv
```

激活虚拟环境：

- Windows: `venv\Scripts\activate`
- macOS/Linux: `source venv/bin/activate`

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

> **注意**：
> - `pyaudio` 在某些系统上需要额外安装系统依赖：
>   - Windows: 通常直接 `pip install pyaudio` 即可，若失败可下载 `.whl` 文件安装
>   - Ubuntu: `sudo apt-get install portaudio19-dev`
>   - macOS: `brew install portaudio`
> - `torch` 如果已有安装可跳过，也可安装 CPU 版本节省空间：
>   `pip install torch --index-url https://download.pytorch.org/whl/cpu`

### 3. 安装 Ollama（本地 AI 理解引擎）

本工具使用 Ollama 运行本地大模型（Qwen3.5）理解语音指令，提供更准确的解析能力。若 Ollama 不可用，程序会自动回退到规则引擎。

#### 安装 Ollama

- **Windows**：`winget install Ollama.Ollama` 或从 [官网](https://ollama.com/download) 下载安装
- **macOS**：`brew install ollama`
- **Linux**：`curl -fsSL https://ollama.com/install.sh | sh`

#### 启动服务并下载模型

```bash
ollama serve          # 启动服务（通常安装后已自动启动）
ollama pull qwen3.5:0.8b   # 下载模型（约 1GB）
ollama list           # 验证安装
```

> **自定义 Ollama 地址**：若 Ollama 部署在远程服务器或非默认端口，请修改 `voice_drawing/ai_understanding.py` 中的 `OLLAMA_URL` 配置。

### 4. 运行程序

```bash
python main.py
```

首次运行时，FunASR 语音识别模型会自动下载（约 300MB），之后可完全离线使用。

## 🎤 语音指令示例

| 类别 | 示例指令 |
|------|----------|
| 绘制圆形 | “画一个圆”、“画一个半径50的圆”、“画个红色的圆” |
| 绘制矩形 | “画一个矩形”、“画一个宽100高80的矩形” |
| 绘制三角形 | “画一个三角形”、“画一个边长60的三角形” |
| 组合命令 | “画一个圆和一个三角形”、“绘制一个圆和三角形以及长方形” |
| 指定坐标 | “在坐标50,100位置画一个圆” |
| 变色 | “把圆形改为红色”、“图形3改为蓝色” |
| 填充 | “给三角形填充黄色” |
| 移动 | “把圆形向右移动30”、“图形3向右移动50” |
| 旋转 | “长方形旋转45度”、“图形3旋转90度” |
| 缩放 | “放大圆形”、“把图形一缩小百分之五十” |
| 属性修改 | “把图形1半径改为100”、“图形2宽改为80” |
| 删除 | “删除长方形”、“删除图形3” |
| 撤销/重做 | “撤销”、“重做” |
| 保存 | “保存” |
| 退出 | “退出” |

> 📖 **完整指令集** 请查看 [docs/commands.md](docs/commands.md)

## 🏗️ 项目架构

### 数据流

```
语音输入 → 语音识别(FunASR) → AI理解(Ollama/规则引擎) → 命令解析 → 绘图执行(Tkinter) → 画布窗口
```

### 模块说明

| 模块 | 文件 | 职责 |
|------|------|------|
| 主程序 | `main.py` | 协调各模块，管理主循环 |
| 语音识别 | `voice_drawing/voice_recognizer.py` | 麦克风录音 + FunASR 语音转文字 |
| AI 理解 | `voice_drawing/ai_understanding.py` | 自然语言 → 标准化命令（Ollama + 规则引擎回退） |
| 命令解析 | `voice_drawing/command_parser.py` | 标准化命令 → 可执行动作列表 |
| 绘图引擎 | `voice_drawing/drawing_engine.py` | Tkinter 窗口管理、图形绘制/修改/删除、层记忆 |

### 技术栈

| 用途 | 技术 | 选型理由 |
|------|------|----------|
| 语音识别 | FunASR (Paraformer) | 中文识别最佳，自动数字转换，完全离线 |
| AI 理解 | Ollama + Qwen3.5:0.8b | 本地大模型，无需联网，中文理解强 |
| 绘图 GUI | Tkinter | Python 内置，零依赖 |
| 图像处理 | Pillow | 轻量级截图保存 |
| 音频采集 | PyAudio + scipy | 跨平台录音与重采样 |

## ❓ 常见问题

### Q: FunASR 模型下载很慢怎么办？
模型会缓存到 `~/.cache/modelscope/hub/` 目录，下载完成后永久离线使用。

### Q: Ollama 服务启动失败怎么办？
程序会自动回退到规则引擎，不影响基本功能。如需排查：`ollama list` 检查服务，默认端口 11434。

### Q: 麦克风无法使用怎么办？
检查麦克风是否被其他程序占用，并在系统设置中允许 Python 访问麦克风。程序启动时会自动检测可用设备。

### Q: 能否完全离线使用？
**可以**。FunASR 模型和 Ollama 模型首次下载后均可完全离线运行。

### Q: 如何查看当前有哪些图形？
每个图形绘制后会在上方显示红色编号标签（如 `[1]`），可通过“隐藏编号”指令隐藏标签。

### Q: 语音识别不准确怎么办？
FunASR 中文识别业界领先，程序内置了同音词纠正（40+组）、中文数字转换、意图消歧等功能。说话清晰、语速适中可获得最佳效果。

### Q: 如何加速 FunASR 识别？
如果系统有 NVIDIA GPU 并已安装 CUDA，FunASR 会自动使用 GPU 加速。CPU 模式下识别速度也足够日常使用。

## 📄 许可证

（请根据你的实际情况添加许可证，例如 MIT）

## 🙏 致谢

- [FunASR](https://github.com/alibaba-damo-academy/FunASR) - 阿里达摩院语音识别模型
- [Ollama](https://ollama.com) - 本地大模型运行框架
- [Qwen](https://github.com/QwenLM/Qwen) - 通义千问大模型
```
通过网盘分享的文件：QQ20260614-142008.mp4
链接: https://pan.baidu.com/s/195mZGLMOCWDj_Efktlbu1Q 提取码: 1111

