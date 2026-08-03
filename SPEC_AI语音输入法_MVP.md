# SPEC — AI 语音输入法 MVP 技术规格

| 项目 | 内容 |
| --- | --- |
| 关联文档 | PRD_AI语音输入法.md |
| 版本 | v1.0 |
| 目标 | 一天内可运行、可演示的 Windows MVP |
| 语言/运行时 | Python 3.13（本机已装），依赖见 §2 |

---

## 1. 系统架构

```
┌──────────────────────────── 主线程 (tkinter) ───────────────────────────┐
│ 悬浮窗 UI (无边框/置顶)  ◄─── queue.Queue ──── 状态/草稿/结果事件        │
└─────────────────────────────────────────────────────────────────────────┘
                        ▲ 状态事件
┌──────────────────────────── Controller (App) ───────────────────────────┐
│ 状态机: IDLE→RECORDING→TRANSCRIBING→REFINING→PREVIEW→INJECT→IDLE        │
└───────┬──────────────────────┬──────────────────────┬───────────────────┘
        │ 热键事件              │ 录音数据              │ 处理结果
┌───────▼─────────┐  ┌─────────▼────────┐   ┌─────────▼───────────────┐
│ HotkeyListener  │  │ Recorder         │   │ Pipeline (worker 线程)   │
│ pynput 全局监听  │  │ sounddevice 16k  │   │ ASR → Refiner → Inject  │
└─────────────────┘  │ mono PCM         │   └─────────┬───────────────┘
                     └─────────┬────────┘             │
                               │ 增量草稿(每~2s)       ▼
                     ┌─────────▼────────┐   ┌─────────────────────────┐
                     │ ASREngine        │   │ LLM Refiner (DeepSeek)  │
                     │ faster-whisper   │   │ OpenAI 兼容 chat API    │
                     │ GPU→CPU 回退     │   │ 三档强度 + 词库约束      │
                     └──────────────────┘   └────────────┬────────────┘
                                                         ▼
                                              Injector: 剪贴板+Ctrl+V
```

**线程模型**（关键）：
- **主线程**：tkinter 事件循环（悬浮窗 + 控制面板）；
- **热键线程**：pynput 回调，仅发事件到主线程/管道；
- **工作线程**（每次录音启动一个）：录音期间负责增量草稿转写；松开后执行 完整转写 → LLM 润色 → 注入，全程通过 `queue.Queue` 向 UI 推送状态。

**状态机**：

| 状态 | 触发 | UI 文案 |
| --- | --- | --- |
| IDLE | 空闲 | 隐藏 |
| RECORDING | 热键按下 | 🎤 录音中… + 草稿 |
| TRANSCRIBING | 热键松开 | ✍️ 转写中… |
| REFINING | 转写完成 | ✨ 润色中… |
| PREVIEW | 润色完成 | 结果预览（1.5s） |
| INJECTING | 预览结束 | 注入中… |
| ERROR | 任一环节失败 | ⚠️ 错误信息 |

---

## 2. 技术选型与依赖

| 用途 | 库 | 备注 |
| --- | --- | --- |
| 全局热键 | `pynput` | 监听 `Key.ctrl_r` 按下/松开 |
| 录音 | `sounddevice` + `numpy` | 16kHz mono float32 |
| ASR | `faster-whisper` | CTranslate2 推理；GPU(cuda) 失败自动回退 CPU |
| LLM | `requests` | 直调 OpenAI 兼容 `/chat/completions` |
| 注入 | `pyperclip` + `pynput` | 剪贴板 + 模拟 Ctrl+V |
| UI | `tkinter`（标准库） | 无边框置顶悬浮窗 |
| 配置 | `json`（标准库） | `config.json` |
| 模型下载 | faster-whisper 内置（HuggingFace） | 首次运行下载，默认 `medium` |

`requirements.txt`：
```
pynput>=1.7
sounddevice>=0.4.6
numpy>=1.26
faster-whisper>=1.0
pyperclip>=1.8
requests>=2.31
```

> 风险提示：`ctranslate2`（faster-whisper 依赖）对 Python 3.13 的 wheel 支持若异常，备选方案为切换到 `sherpa-onnx`（onnxruntime 支持 3.13）跑 SenseVoice；接口已抽象（见 §3.4），不影响其他模块。

---

## 3. 模块设计

### 3.1 入口 `main.py`
- 加载配置 → 初始化 ASR（懒加载：首次录音时才加载模型，加快启动）→ 启动热键监听 → 启动 tkinter 主循环；
- 捕获全局异常并写入 `logs/app.log`。

### 3.2 热键模块 `hotkey.py`
- `HotkeyListener(key)`：pynput `Listener`，`on_press` / `on_release` 只做**去抖**（避免重复触发）与事件转发；
- 按下：`on_start()`；松开：`on_stop()`；回调由主线程通过 `queue` 消费（避免跨线程直接操作 UI）。

### 3.3 录音模块 `recorder.py`
- `Recorder.start()`：打开 `InputStream(samplerate=16000, channels=1, dtype='float32')`，持续累积音频到 `numpy.ndarray`；
- 每积累 ≥2s 音频触发一次"增量草稿"回调（异步转写，队列忙则跳过）；
- `Recorder.stop() -> np.ndarray`：返回整段音频；
- `Recorder.is_too_short(0.5s)`：过短则丢弃。

### 3.4 ASR 模块 `asr.py`
- 接口：
  ```python
  class ASREngine:
      def transcribe(self, audio: np.ndarray, language: str = "zh") -> str
  ```
- `WhisperEngine`（faster-whisper）：
  - 初始化：`WhisperModel(model_size, device="cuda", compute_type="float16")`，CUDA 初始化失败回退 `device="cpu", compute_type="int8"`；
  - `transcribe`：`beam_size=5`，`language="zh"`（语言自动检测兜底），拼接所有 segment 文本；
  - 模型大小默认 `medium`，config 可改 `small/large-v3`；
- 预留 `CloudASREngine` 接口（P1），配置 `asr.engine = "whisper" | "cloud"`。

### 3.5 LLM 后处理模块 `refiner.py`
- `Refiner.refine(raw_text, level, words) -> str`：
  - 请求 DeepSeek：`POST {base_url}/chat/completions`，`model=deepseek-chat`，`temperature=0`，`max_tokens=4096`；
  - **不启用润色**（`refine.enabled=false` 或未配 key）时直接返回 `raw_text`。
- **Prompt 模板**（system）：
  ```
  你是语音识别结果的后处理助手。你的任务：只修复明显的语音识别错误，不要改写、润色或删除看起来正确的内容。
  必须执行：
  1. 过滤语气词和口头禅：嗯、啊、呃、那个、然后、就是说、对吧、你懂吧 等；
  2. 根据语义补全或修正标点符号与断句；
  3. 修正明显的谐音/音译错误：如 "配森"→"Python"、"杰森"→"JSON"、"吉特哈布"→"GitHub"；
  4. 保持原意与信息完整性，不添加、不删除、不概括任何事实内容。
  禁止：改写用户原话的意思、调整语序（除非明显错误）、把口语强行改成书面语、添加原文没有的信息。
  以下词汇必须按指定写法输出（用户词库）：
  {words_block}
  输出：只输出处理后的文本，不要任何解释、引号或格式标记。
  ```
- **强度档位**（`config.refine.level`）：
  | level | 行为 |
  | --- | --- |
  | `conservative`（默认） | 上述模板（语气词+标点+明显错误） |
  | `light` | 在保守基础上允许"口语→书面语"的轻度转化 |
  | `polish` | 允许理顺语序、删除冗余、合理分段 |
- 三档通过追加一行指令实现（prompt 可替换，见 §5）。

### 3.6 注入模块 `injector.py`
- `Injector.inject(text) -> bool`：
  1. 保存当前剪贴板 → `pyperclip.copy(text)`；
  2. `pynput` 模拟 `Ctrl+V`（`Key.ctrl` + `'v'`），间隔 50ms；
  3. 延迟 300ms 后恢复原剪贴板（若内容为文本）；
  4. 注入失败/异常 → 返回 False（文本保留在剪贴板）。
- 兼容性说明：Windows 中文输入法一般不拦截系统级 `Ctrl+V`；个别应用（终端、微信特殊窗口）可能失败，走"已复制"降级提示。

### 3.7 悬浮窗 UI `ui.py`
- `Overlay(tk.Toplevel)`：`overrideredirect(True)`、`attributes('-topmost', True)`、深色圆角（`tk.Frame` + 深色背景，圆角用简单矩形/留白），屏幕底部中央；
- 元素：状态图标+文案（Label）、草稿/结果文本（Label，自动换行，max width 60 字）、迷你音量条（`tk.Canvas`，可选）；
- `update_state(state, text)` 由主线程消费 queue 调用；
- ESC 或点击可关闭本次预览（提前注入）。

### 3.8 配置与词库
- `config.json` 默认生成（见 §4.1）；
- `词库.txt`：每行一条，支持 `原词=指定写法` 或纯词条；`#` 注释；空行忽略；加载后写入 `words_block`。

---

## 4. 数据格式

### 4.1 config.json（首次运行自动生成）

```json
{
  "hotkey": "ctrl_r",
  "asr": { "engine": "whisper", "model": "medium", "language": "zh" },
  "refine": {
    "enabled": true,
    "base_url": "https://api.deepseek.com/v1",
    "api_key": "",
    "model": "deepseek-chat",
    "level": "conservative",
    "timeout_sec": 30
  },
  "ui": { "preview_sec": 1.5 }
}
```

### 4.2 词库.txt

```
# 用户词库：原词=指定写法，或直接写词条
Python
配森=Python
喵酱
JSON
```

### 4.3 Prompt 模板文件 `prompts/refine.md`

```
{level} 对应三段指令之一（替换 LEVEL_RULE）：
- conservative: "只修复明显的语音识别错误与语气词，保持原话意思与语序不变。"
- light: "在保守修正基础上，可将明显口语转为书面语，不得改变原意。"
- polish: "在轻度基础上，允许理顺语序、删除冗余、合理分段，仍不得增删事实信息。"
```

---

## 5. 接口定义（内部）

| 函数 | 签名 | 说明 |
| --- | --- | --- |
| `App.on_hotkey_down()` / `on_hotkey_up()` | `() -> None` | 状态机入口，线程安全（内部走 queue） |
| `Recorder.start()/stop()` | `() / () -> np.ndarray` | 录音控制 |
| `ASREngine.transcribe(audio, language) -> str` | 见上 | 粗转写 |
| `Refiner.refine(raw, level, words) -> str` | 见上 | 后处理 |
| `Injector.inject(text) -> bool` | 见上 | 注入 |
| `Overlay.show_state(state, text)` | `(str, str) -> None` | UI 更新 |

---

## 6. 错误处理与降级

| 场景 | 行为 |
| --- | --- |
| API Key 未配置 | 跳过润色，直接注入粗转写，悬浮窗提示"未配置 API Key，已输出原始转写" |
| DeepSeek 请求超时/失败 | 重试 1 次（3s），仍失败则注入粗转写 + 提示 |
| CUDA 不可用 | 自动回退 CPU（int8），首次加载提示 |
| 录音过短（<0.5s） | 忽略，不产生输出 |
| 注入失败 | 文本保留剪贴板，悬浮窗提示"已复制到剪贴板，请手动 Ctrl+V" |
| 词库文件不存在 | 视为空词库，不报错 |

---

## 7. 性能目标

| 指标 | 目标（RTX 4060） |
| --- | --- |
| 整段转写（30s 音频, medium） | < 1.5s |
| LLM 润色（≤500 字） | < 3s |
| 松开 → 注入完成 | < 5s |
| 首次启动（含模型加载） | < 10s（模型加载延迟至首次录音） |
| 悬浮窗更新频率 | ≥ 10Hz（音量条） |

---

## 8. 测试用例

| # | 用例 | 预期 |
| --- | --- | --- |
| T1 | 无 API Key 口述 | 注入粗转写，提示未配置 |
| T2 | 正常口述含语气词 | 输出无"嗯/啊/那个" |
| T3 | "配森"音译 | 输出"Python" |
| T4 | 词库词条 | 按词库写法输出 |
| T5 | 注入到记事本 | 光标处出现文本 |
| T6 | 录音 <0.5s | 无输出 |
| T7 | 断网 + 润色关闭 | 本地转写+注入正常 |
| T8 | 长文本（3 分钟口述） | 完整输出，无截断（max_tokens 4096） |

---

## 9. 运行与交付

- 运行：`python main.py`（首次自动生成 config.json 与 词库.txt）；
- 交付物：`main.py`、`hotkey.py`、`recorder.py`、`asr.py`、`refiner.py`、`injector.py`、`ui.py`、`config.py`、`requirements.txt`、`README.md`、`词库.txt`、`config.json`、`prompts/refine.md`；
- 演示前检查清单：麦克风权限、GPU 驱动、API Key 已填、词库已配置、记事本窗口已打开。

---

## 10. 风险与备选

| 风险 | 备选方案 |
| --- | --- |
| ctranslate2 不支持 Python 3.13 | 切 `sherpa-onnx` + SenseVoice（接口不变，仅换 ASR 实现） |
| 增量草稿转写排队积压 | 草稿是"尽力而为"，队列忙则跳过，不影响最终结果 |
| DeepSeek 限流/慢 | 重试 1 次 + 超时降级注入粗转写 |
| pynput 热键被占用 | config 可换键（如 f9、caps_lock） |

---

## 11. 实现变更记录（截至 2026-08-03 v5）

本文档为 v1.0 原始技术规格，实际实现与其存在以下已确认差异（以代码与 README/部署文档为准）：

- **交互**：按住说话 → 单击 toggle（按一下开始/再按一下结束），默认热键 `alt_r`（兼容 AltGr，200ms 防抖）；
- **模型**：默认使用本地路径 `models/faster-whisper-medium`（ModelScope 下载，离线可用），不依赖 HuggingFace；
- **转写参数**：`beam_size=8`、语言自动检测（`None`）、幻觉抑制三阈值、词库热词拼入 `initial_prompt`、峰值归一化；
- **注入**：以 `safe_inject.py` 为准（剪贴板全格式备份恢复、UIPI 预检、序列号冲突检测）；`injector.py` 冗余实现已于 v5.9 删除；
- **悬浮窗**：150×52 波形胶囊；v5 起**声波仅在 VAD 判定说话时显示**，静音时只显示「🎤 录音中…」；
- **管线**：v5 起**移除 PREVIEW 浮窗预览**，润色完成后直接注入输入框；
- **新增模块**：`cloud_asr.py`（云端 ASR 兜底）、`doctor.py`（环境自检）、`orchestrate.py`（多 Agent 编排）、`draft_smoother.py`（草稿平滑，v5 起未接线，保留备用）；
- **配置**：新增 `recorder.auto_stop_silence_sec`、`ui.max_chars`、`asr.cloud`；无 `prompts/refine.md`（提示词内嵌于 `refiner.py`）；无 `logs/app.log` 文件日志。
