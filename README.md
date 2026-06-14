语音控制绘图工具 - 部署文档
环境要求
Python 3.8 或更高版本
操作系统：Windows / macOS / Linux
麦克风设备
推荐内存 >= 4GB
安装步骤
1. 创建虚拟环境（推荐）
激活虚拟环境：
Windows: venv\Scripts\activate
macOS/Linux: source venv/bin/activate
2. 安装依赖
注意：
pyaudio 在某些系统上需要额外安装系统依赖：
Windows: 直接 pip install pyaudio 即可，如果失败请下载 whl 文件安装
Ubuntu: sudo apt-get install portaudio19-dev
macOS: brew install portaudio
torch 如果已有安装可跳过，也可安装 CPU 版本节省空间： pip install torch --index￾url https://download.pytorch.org/whl/cpu
3. 安装 Ollama（本地 AI 理解引擎）
本项目支持使用 Ollama 本地大模型（Qwen3.5）理解语音指令，提供更准确的解析能力。
3.1 安装 Ollama
Windows（推荐）：
或从官网下载安装：https://ollama.com/download
macOS：
Linux：
conda create -n draw python=3.8.8
pip install -r requirements.txt
winget install Ollama.Ollama
brew install ollama
3.2 启动 Ollama 服务
安装完成后 Ollama 会自动启动为后台服务。如需手动启动：
注意：如果提示端口已被占用，说明 Ollama 服务已在运行中，无需重复启动。
3.3 下载 Qwen3.5 模型
该模型约 1GB，首次下载后可永久离线使用。
3.4 验证安装
应显示已下载的模型列表。
降级策略：如果 Ollama 服务未启动或连接失败，程序自动回退到规则引擎，不影响正常使用。
自定义 Ollama 地址：若 Ollama 部署在远程服务器、非默认端口（如 11434 被占用）、或通过
WSL/Docker 运行，请修改 voice_drawing/ai_understanding.py 中的 OLLAMA_URL 配置
（默认 http://localhost:11434/api/generate ），将 localhost:11434 替换为实际的 IP
和端口即可。
4. 运行程序
程序启动流程：
1. 自动检测麦克风设备和采样率
2. 加载 FunASR 语音识别模型（首次运行需下载模型）
3. 模型加载完成后进入语音监听状态
4. 对麦克风说出绘图指令即可
语音指令
完整指令集请参考：commands.md
快速入门
curl -fsSL https://ollama.com/install.sh | sh
ollama serve
ollama pull qwen3.5:0.8b
ollama list
python main.py
#也可以放在pycharm2024中运行main.py
指令类型 示例指令
绘制圆形 "画一个圆"、"画一个半径50的圆"、"画个红色的圆"
绘制矩形 "画一个矩形"、"画一个宽100高80的矩形"
绘制三角形 "画一个三角形"、"画一个边长60的三角形"
组合命令 "画一个圆和一个三角形"、"绘制一个圆和三角形以及长方形"
指定坐标 "在坐标50,100位置画一个圆"
变色 "把圆形改为红色"、"图形3改为蓝色"
填充 "给三角形填充黄色"
移动 "把圆形向右移动30"、"图形3向右移动50"
旋转 "长方形旋转45度"、"图形3旋转90度"
缩放 "放大圆形"、"把图形一缩小百分之五十"
属性修改 "把图形1半径改为100"、"图形2宽改为80"
删除 "删除长方形"、"删除图形3"
撤销/重做 "撤销"、"重做"
保存 "保存"
退出 "退出"
项目架构
技术栈
voice_drawing/
├── main.py # 主程序入口
├── requirements.txt # Python 依赖
├── voice_drawing/
│ ├── voice_recognizer.py # 语音识别（FunASR）
│ ├── ai_understanding.py # AI 理解（Ollama + 规则引擎回退）
│ ├── command_parser.py # 命令解析
│ └── drawing_engine.py # 绘图引擎（Tkinter）
└── docs/
├── commands.md # 完整指令集
└── deploy.md # 部署文档
模块 技术选型 说明
语音识别 FunASR (Paraformer) 阿里达摩院中文语音模型，自动转换数字、添加标点
AI 理解 Ollama + Qwen3.5:0.8b 本地大模型，规则引擎作为回退方案
绘图引擎 Tkinter Python 标准库，跨平台 GUI
音频处理 PyAudio + scipy 录音和重采样
图像处理 Pillow 画布截图保存
常见问题
Q: FunASR 模型下载很慢怎么办？
A: 模型下载速度取决于网络情况。模型会缓存到 ~/.cache/modelscope/hub/ 目录，下载完成后永久
离线使用。
Q: Ollama 服务启动失败怎么办？
A: 如果 Ollama 不可用，程序自动回退到规则引擎，不影响基本功能。如需排查 Ollama 问题：
检查服务是否运行： ollama list
检查端口是否被占用（默认 11434）
Q: 麦克风无法使用怎么办？
A: 请检查麦克风是否被其他程序占用，并在系统设置中允许 Python 访问麦克风。程序启动时会自动检
测可用的麦克风设备并打印设备信息。
Q: 能否完全离线使用？
A: 可以！FunASR 模型和 Ollama 模型首次下载后均可完全离线使用。
Q: 如何查看当前有哪些图形层？
A: 每个图形绘制后会在上方显示红色编号标签（如 [1] ），可通过"隐藏编号"指令隐藏标签。
Q: 语音识别不准确怎么办？
A: FunASR 使用 Paraformer 模型，中文识别业界领先。程序内置了同音词纠正、中文数字转换、意图
消歧等功能。说话清晰、语速适中可获得最佳效果。
Q: 如何加速 FunASR 识别？
A: 如果系统有 NVIDIA GPU 并已安装 CUDA，FunASR 会自动使用 GPU 加速。CPU 模式下识别速度也
足够日常使用。
Q: 如何管理 Ollama 模型？
A:
查看已安装模型： ollama list
删除模型： ollama rm 模型名
查看运行状态： ollama ps
