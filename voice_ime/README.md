# AI 语音输入法（Windows）

按一下右 Alt 开始录音，再按一下结束，即得经过**本地语音识别 + 大模型保守纠错**的干净文本，自动注入当前输入框。

- 🎙️ **本地识别**：faster-whisper（GPU 加速、离线可用），不依赖云识别
- ✨ **保守纠错**：过滤语气词、自动标点断句、修正谐音/术语（"配森"→"Python"）、词库热词
- 🔐 **安全注入**：剪贴板全格式备份恢复 + UIPI 预检，不破坏你的剪贴板
- 📦 **迷你波形胶囊**：录音时只显示一个 150×52 的小胶囊 + 真实音量波形

> 📖 **完整部署文档见 [部署文档](../部署文档.md)**（技术栈/原理、环境要求、模型下载、GPU 加速、常见问题排查，一应俱全）。

## 快速开始（摘要）

```powershell
cd voice_ime
pip install -r requirements.txt
copy config.example.json config.json   # 然后编辑填入 DeepSeek API Key
# 下载模型到 models/（详见部署文档 §5.5）
python doctor.py                        # 环境自检，全部 ✅ 后运行
python main.py                          # 或双击 启动.bat
```

首次运行自动生成 `config.json` 与 `词库.txt`；模型下载、API Key 配置、GPU 加速等完整步骤见部署文档。

## 配置（config.json）

```json
{
  "hotkey": "ctrl_r",
  "asr": { "engine": "whisper", "model": "medium", "language": "zh" },
  "refine": {
    "enabled": true,
    "base_url": "https://api.deepseek.com/v1",
    "api_key": "sk-你的key",
    "model": "deepseek-chat",
    "level": "conservative",
    "timeout_sec": 30
  },
  "ui": { "preview_sec": 1.5, "max_chars": 300 }
}
```

- `hotkey`：按住说话的按键，支持 `ctrl_r` / `f9` / `caps_lock` / `alt_l` 等；
- `asr.model`：`small` / `medium`（默认，推荐）/ `large-v3`，首次使用自动下载；
- `refine.level`：`conservative`（保守纠错，默认）/ `light`（轻度规整）/ `polish`（完整规整）；
- 不填 `api_key` 时自动跳过润色，直接输出原始转写。

## 词库（词库.txt）

每行一条，`#` 开头为注释：

```
# 用户词库
配森=Python
喵酱
```

- `原词=指定写法`：润色时强制按指定写法输出；
- 直接写词条：要求保持该词写法不被改写。

## 使用

1. 打开任意可输入文字的窗口（记事本、聊天框、文档）；
2. 按住右 Ctrl，开始说话（悬浮窗显示实时草稿）；
3. 松开右 Ctrl，等待「转写中 → 润色中 → 预览」；
4. 文字自动出现在光标处；右键悬浮窗可退出。

## 演示检查清单

- [ ] `config.json` 已填 DeepSeek API Key
- [ ] 麦克风可用（系统设置 > 隐私 > 麦克风 已授权）
- [ ] GPU 驱动正常（可选，CPU 自动回退）
- [ ] 记事本窗口已打开并聚焦

## 常见问题

| 问题 | 处理 |
| --- | --- |
| 首次运行下载模型较慢 | 需要联网下载（small ~460MB / medium ~1.5GB） |
| 提示未配置 API Key | 编辑 `config.json` 填入 `refine.api_key` |
| 注入失败 | 文本已留在剪贴板，手动 Ctrl+V 即可 |
| 热键冲突 | 修改 `config.json` 的 `hotkey` 字段 |
| Python 3.13 装不上 faster-whisper | 见 SPEC §10：切换 sherpa-onnx + SenseVoice（接口不变） |

## 子 Agent 产出模块（多 Agent 协作集成）

本项目由总 Agent（编排层）拆解任务，调用两个实体 Agent 分别实现模块后集成：

| 模块 | 实现 Agent | 功能 | 来源 |
| --- | --- | --- | --- |
| `safe_inject.py` | Claude Code | 安全剪贴板注入：全格式备份恢复、50ms 内恢复窗口、UIPI 管理员窗口预检、非文本剪贴板保护 | `tasks/claude-injector/` |
| `vad.py` | Hermes | 能量阈值 VAD：去抖状态机、静音检测、`silence_seconds()` | `tasks/hermes-vad/` |

### 新增配置项（config.json）

```json
"recorder": { "auto_stop_silence_sec": 0 }
```

- `auto_stop_silence_sec`：录音中连续静音超过该秒数自动结束录音（0 = 关闭）。开启后可实现"说完自动停"。
- 注入模块已自动切换为 `safe_inject.py`（更安全），旧的 `injector.py` 保留备用。

### 子 Agent 任务复现

```powershell
# Claude Code：安全注入模块（工作区 tasks/claude-injector）
cd tasks/claude-injector
claude -p "请先通读当前目录下的 TASK.md，严格按其中要求完成任务，实现交付物。只允许创建/修改当前目录内的文件。" --permission-mode acceptEdits --output-format json

# Hermes：VAD 模块（工作区 tasks/hermes-vad）
cd tasks/hermes-vad
hermes chat -q "请先通读当前目录下的 TASK.md，严格按其中要求完成任务，实现交付物。只允许创建/修改当前目录内的文件。" -Q --yolo
```

## 多 Agent 编排工具（orchestrate.py）

把「拆任务 → 派发 Agent → 收集结果 → 审查」固化成一条命令：

```powershell
python orchestrate.py --list      # 查看已配置的子任务
python orchestrate.py --report    # 复盘已有结果（免费，含成本/耗时/语法检查）
python orchestrate.py --noop      # 只打印将执行的命令（免费）
python orchestrate.py             # 真正派发全部子任务（会产生 API 费用！）
python orchestrate.py --only=hermes-vad   # 只跑指定任务
```

子任务契约写在 `tasks.json`（每个任务 = 独立工作区 + TASK.md + 指定 agent + 超时）。
编排原则：子 Agent 只在其独立工作区内写文件，编排层负责审查（语法检查/接口核对）后再集成，不盲目信任 Agent 产出。

## 子任务池（tasks.json，可直接派发）

| 任务名 | Agent | 内容 | 来源 |
| --- | --- | --- | --- |
| `claude-injector` | claude | 安全剪贴板注入模块（已完成） | 评审-注入风险 |
| `hermes-vad` | hermes | VAD 静音检测模块（已完成） | 评审-VAD 缺口 |
| `hermes-draft-smooth` | hermes | 草稿→最终文本过渡平滑模块 | 评审-草稿一致性 |
| `claude-cloud-asr` | claude | 云端 ASR 兜底引擎（OpenAI 兼容端点） | 评审-单点故障/GPU 风险 |
| `hermes-doctor` | hermes | 演示前环境自检脚本 doctor.py | 评审-GPU 部署风险 |

派发示例（会产生费用）：

```powershell
python orchestrate.py --only=hermes-doctor,claude-cloud-asr
```

编排层收到产出后会做：语法检查 → 接口核对 → 独立功能测试 → 集成进 voice_ime。

## 第三轮子 Agent 产出（DeepSeek v4 Flash 实测）

| 任务 | Agent | 产出 | 独立验收结果 |
| --- | --- | --- | --- |
| `hermes-draft-smooth` | hermes | `draft_smoother.py`（草稿→最终文本过渡规划） | ✅ 帧序列正确、边界安全 |
| `claude-cloud-asr` | claude | `cloud_asr.py`（OpenAI 兼容云端 ASR 兜底） | ✅ WAV 头正确、无 key 报错可读 |
| `hermes-doctor` | hermes | `doctor.py`（演示前环境自检） | ✅ 7 项检查实测通过（修 2 处集成 bug） |

已全部集成进本项目根目录。新增配置（config.json）：

```json
"asr": {
  "engine": "whisper",   // "whisper" 本地 | "cloud" 云端
  "cloud": { "base_url": "", "api_key": "", "model": "whisper-1" }
}
```

演示前自检：

```powershell
python doctor.py
```

草稿平滑已接入 main.py：录音草稿→最终文本不再突变，会先过渡显示。

## v2 更新记录（2026-08-02 · 用户反馈修复轮）

### 交互升级：单击切换（toggle）
- 不再需要按住按键：**按一下右 Alt 开始录音（可松开），再按一下结束并转写**
- 修复 Windows 上右 Alt 被识别为 AltGr 的问题（`alt_gr` 已作为 `alt_r` 的别名监听）
- 200ms 防抖，防双击误触；处理中按下会被忽略

### 转写稳定性修复（定位并解决两个根因）
- **模型不再联网下载**：small 模型已下载到 `models/faster-whisper-small/`（来自 ModelScope），完全离线可用；`config.json` 的 `asr.model` 指向本地路径
- **CUDA 已修复**：安装 `nvidia-cublas-cu12` + `nvidia-cudnn-cu12`（清华镜像），GPU 转写稳定态约 **0.18 秒**；asr.py 新增 CUDA 预检——缺 DLL 时直接走 CPU 并给出可读提示，**绝不挂起**
- 启动时后台预热模型，第一次按键不再等待加载

### 悬浮窗质感升级
- 深色渐变背景 + 圆角描边 + 两行排版（状态标题/内容）
- 录音状态底部电平条动画、窗口淡入动画
- 仍保持不抢焦点（WS_EX_NOACTIVATE）

### 实测数据（RTX 4060）
| 项目 | CPU | GPU |
| --- | --- | --- |
| small 模型加载 | 1.1s | 2.0s（含 CUDA 初始化） |
| 短句转写（稳定态） | 1.6s | 0.18s |

## v3 更新记录（2026-08-02 · 第二轮反馈优化）

### 迷你悬浮窗（用户要求：象征性提示即可）
- 状态提示胶囊缩小到 **300×70**：小圆点 + 状态文字（🎤 录音中 / ✨ 润色中），不再铺大段草稿
- 结果预览 **420×90**：小字号显示 1~2 行最终文本，确认用但不占屏
- 保留：不抢焦点、右键退出、淡入动画
- ui.py 从 502 行精简到 214 行

### 识别准确度提升（medium 模型 + 参数优化）
- **默认模型升级为 medium**（ModelScope 下载，本地 `models/faster-whisper-medium/`），GPU 实测 ~0.8s/次；对比同段语音：medium 自动断句加标点，small 输出无标点
- 转写参数优化（Claude 实现）：
  - `beam_size` 5→8（中文同音字选词更准）
  - `condition_on_previous_text=True`（整段连贯解码）
  - 语言改为**自动检测**（中英混杂友好，不再强制 zh）
  - 幻觉抑制：`no_speech_threshold` / `log_prob_threshold` / `compression_ratio_threshold`
  - **词库热词**：`词库.txt` 词条自动拼入 `initial_prompt`，专名/术语优先识别
  - 音频峰值归一化（防过小/过大声音）
- 词库已预置示例：Python / JSON / GitHub（配森=Python 等映射）

## v4 更新记录（2026-08-02 · 第三轮反馈优化）

### 悬浮窗：胶囊 + 音频波（用户要求：尽量小、象征性提示）
- 录音中：**150×52 胶囊 + 5 根音频波竖条**，随真实录音电平（RMS）跳动，无文字
- 转写/润色/注入：同尺寸胶囊 + 短文字（✍️ 转写中 / ✨ 润色中）
- 结果预览：380×80，1~2 行最终文字
- 单 Canvas 全量重绘，统一布局，不再混用绝对/相对坐标

### 修复「第二次录音字体错位」（根因：窗口未映射时 geometry 不生效）
- 根因：`show()` 在 `deiconify()` 之前读取窗口尺寸，首次显示时读到窗口自然尺寸 378×265，导致定位与绘制全错
- 修复：先 `deiconify()` 映射窗口 → 再读实际尺寸 → 再定位 → 再绘制
- 实测：第一次/第二次录音、状态切换，位置全程稳定在屏幕底部居中

### 波形数据链路（真实电平驱动）
- `recorder.py` 新增 `on_level` 回调：每帧（约 20ms）计算 RMS 并归一化（0~1）
- `main.py` 线程安全接线：录音线程写共享变量，主线程 100ms 轮询调 `overlay.set_level(rms)`
- 录音结束电平自动归零
