# AI 语音输入法（mao-voice）

按一下右 Alt 开始录音，再按一下结束，即得经过**本地语音识别 + 大模型保守纠错**的干净文本，自动注入当前输入框。

- 🎙️ **本地识别**：faster-whisper（CTranslate2，GPU 加速、离线可用），不依赖云识别
- ✨ **保守纠错**：过滤语气词、自动标点断句、修正谐音/术语（"配森"→"Python"）、词库热词
- 🔐 **安全注入**：剪贴板全格式备份恢复 + UIPI 预检 + 冲突检测，不破坏你的剪贴板
- 📦 **迷你波形胶囊**：录音时只显示一个 180×56 的小胶囊 + **15 根音乐播放器式频带波形**，全程无文字打扰——**未出声时波形平静静止，一说话就随音调/语气明显律动跳动**，不抢焦点
- ⚡ **一键部署**：`启动.bat` 双击即用，`doctor.py` 环境自检，完整步骤见部署文档

---

## 仓库结构

```
mao-voice/
├── 部署文档.md                      # 📖 完整部署指南（技术栈/原理/环境/部署/运行/维护/FAQ）
├── PRD_AI语音输入法.md              # 产品需求文档
├── SPEC_AI语音输入法_MVP.md         # 技术规格文档
├── AI语音输入法_调研与产品设计.md    # 需求调研与竞品分析
├── voice_ime/
│   ├── main.py                      # 入口：toggle 状态机 + 管线编排
│   ├── config.py / config.example.json
│   ├── hotkey.py / recorder.py / asr.py / refiner.py
│   ├── safe_inject.py / ui.py / vad.py / draft_smoother.py
│   ├── cloud_asr.py / doctor.py / orchestrate.py
│   ├── settings_ui.py / history.py / download_model.py
│   ├── 词库.txt / 启动.bat / requirements.txt
│   ├── models/                      # 模型（不入库，见部署文档 §5.5）
│   ├── tasks/ results/              # 编排工具按需生成的历史工作区/结果（不入库）
│   └── tests/                       # 注入回归测试
```

---

## 快速开始（摘要）

```powershell
cd voice_ime
pip install -r requirements.txt
copy config.example.json config.json   # 编辑填入 DeepSeek API Key
python download_model.py               # 一键下载模型（也可手动，详见部署文档 §5.5）
python doctor.py                        # 环境自检，全部 ✅ 后运行
python main.py                          # 或双击 启动.bat
```

> 📖 **完整部署文档见 [部署文档](./部署文档.md)**：技术栈与技术原理、实现逻辑、环境要求、模型下载（ModelScope）、GPU 加速、常见问题排查，一应俱全。

---

## 核心配置（config.json）

```json
{
  "hotkey": "alt_r",
  "asr": {
    "engine": "whisper",
    "model": "models/faster-whisper-medium",
    "language": null,
    "cloud": { "base_url": "", "api_key": "", "model": "whisper-1" }
  },
  "recorder": { "auto_stop_silence_sec": 0 },
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

- `hotkey`：录音开关热键，`alt_r` / `alt_l` / `ctrl_r` / `f1~f12` / `caps_lock` 等；
- `asr.model`：本地模型路径（`models/faster-whisper-medium` 等），离线识别；
- `asr.engine`：`whisper`（本地）或 `cloud`（云端兜底，OpenAI 兼容端点）；
- `asr.language`：`null` = 自动检测（中英混杂友好）；`"zh"` = 固定中文；
- `recorder.auto_stop_silence_sec`：静音超时自动结束录音（0 = 关闭）；
- `refine.level`：`conservative`（保守纠错，默认）/ `light` / `polish`；
- 不填 `refine.api_key` 时自动跳过润色，直接输出原始转写。

> ⚠️ `config.json` 含密钥，已在 `.gitignore` 中排除；仓库只提供脱敏的 `config.example.json`。

---

## 词库（voice_ime/词库.txt）

每行一条，`#` 开头为注释：

```
# 用户词库
配森=Python        # 原词=指定写法：润色时强制按指定写法输出
喵酱              # 词条：要求保持该词不被改写
Python
```

词库内容自动拼入 ASR `initial_prompt` 与 LLM 提示词（已做数据定界防注入）。

---

## 使用说明

1. 打开任意可输入文字的窗口（记事本、聊天框、文档）；
2. **按一下右 Alt** 开始录音——屏幕底部中央出现迷你波形胶囊；
3. 说完**再按一下右 Alt** 结束——悬浮窗依次显示「转写中 → 润色中 → 注入中」，文字**直接注入光标处**（v5 起不再在浮窗预览转写内容）；
4. 悬浮窗消失；
5. 退出：右键悬浮窗 → 退出，或关闭控制台窗口。

**演示检查清单**

- [ ] `config.json` 已填 DeepSeek API Key
- [ ] 麦克风可用（系统设置 > 隐私 > 麦克风 已授权）
- [ ] 模型已下载到 `voice_ime/models/`
- [ ] `python doctor.py` 全部 ✅

---

## 开发与维护

### 多 Agent 编排工具（voice_ime/orchestrate.py）

本项目由总 Agent（编排层）拆解任务、调用实体 Agent（Claude Code / Hermes）分模块实现后集成，工具化如下：

```powershell
python orchestrate.py --list      # 查看已配置的子任务
python orchestrate.py --report    # 复盘已有结果（免费，含成本/耗时/语法检查）
python orchestrate.py --noop      # 只打印将执行的命令（免费）
python orchestrate.py             # 真正派发全部子任务（会产生 API 费用！）
python orchestrate.py --only=任务名
```

子任务契约在 `tasks.json`；编排原则：子 Agent 只在独立工作区内写文件，编排层负责审查（语法检查/接口核对/功能测试）后再集成。

> 任务工作区（`tasks/`）与执行结果（`results/`）由编排工具按需自动创建，**不入库**；本地可随时删除，不影响仓库。

### 子任务池（tasks.json）

| 任务名 | Agent | 内容 |
| --- | --- | --- |
| `claude-injector` | claude | 安全剪贴板注入模块 |
| `hermes-vad` | hermes | VAD 静音检测模块 |
| `hermes-draft-smooth` | hermes | 草稿→最终文本过渡平滑模块 |
| `claude-cloud-asr` | claude | 云端 ASR 兜底引擎 |
| `hermes-doctor` | hermes | 演示前环境自检脚本 |

### 代码审查（open-code-review）

```powershell
npm install -g @alibaba-group/open-code-review
ocr scan --exclude "models/**,tasks/**,tests/**,results/**,__pycache__/**,*.png,*.json,*.txt,*.log,*.md,*.bat,*.wav"
```

历史审查与修复过程见 `voice_ime/OCR审查报告.md`。

---

## 路线图

- **P1 补全**：✅ 润色强度运行时切换（F9）、✅ 输入历史记录（F12，设置窗口可查看）
- **工程化**：✅ pytest 单测 + GitHub Actions CI、✅ 一键模型下载脚本（ModelScope）、✅ 托盘图标 + 设置窗口、⏳ PyInstaller 打包 Release
- **差异化**：自学习纠错引擎（越用越像你）、语音编辑指令、悬浮条右键菜单 + 声音反馈
- **云端兜底**：`cloud_asr.py` 已就绪，待接入 OpenAI 兼容端点实测（当前未验证）
- **跨平台**：翻译/人设模式、macOS 版（`提示词.txt` Swift 方案）

> 完整路线图与优先级分析见 `项目审核报告.md` §7~§8。

---

## 更新记录

<details>
<summary>📜 点击展开 / 收起版本记录（v2 ~ v5.15）</summary>

<!-- 新增版本请继续追加到本折叠区内，保持旧版本在上、新版本在下 -->

### v2（2026-08-02 · 交互与稳定性）
- **toggle 交互**：按一下右 Alt 开始/结束，不再长按；修复 AltGr 识别；200ms 防抖
- **转写稳定性**：模型本地化（ModelScope 下载，离线可用）；CUDA 运行库修复（GPU 转写 0.18s）；CUDA 预检防挂起；启动预热模型

### v3（2026-08-02 · 悬浮窗与准确度）
- 迷你悬浮窗（300×70，象征性提示）；默认模型升级 medium；转写参数优化（beam 8、自动语言检测、幻觉抑制、词库热词）

### v4（2026-08-02 · 波形胶囊与错位修复）
- 150×52 胶囊 + 5 根真实 RMS 波形；修复"第二次录音字体错位"（先映射窗口再读尺寸）；RMS 电平链路（recorder→main→ui 线程安全接线）

### v5（2026-08-03 · 说话声波与直注入）
- **v5.1 说话才显示声波**：录音中只有 VAD 判定"正在说话"时才绘制波形，静音/未说话时只显示「🎤 录音中…」提示，直观反馈"我正在说话"
- **v5.2 移除转写预览**：结束录音后不再在浮窗展示转写文本，润色完成直接注入当前输入框（状态提示仍保留：转写中/润色中/注入中）
- **v5.3 修复呼吸点颜色溢出**：修复转写/润色状态呼吸点动画在亮度系数超过 1.0 时 RGB 通道溢出 255、生成非法颜色名（如 `#102a511`）导致 Tkinter 回调异常的问题；亮度系数与颜色通道均钳制到合法范围
- **v5.4 注入成功不再报剪贴板错误**：文字注入成功即视为成功；"剪贴板恢复未完成"（多因其他程序在注入瞬间占用/修改剪贴板）不再弹 ERROR 提示，只在控制台留一行 `[剪贴板]` 日志供排查
- **v5.5 响应提速**：① 结束录音后立即进入转写——`Recorder.stop()` 不再等待草稿线程（原实现最长阻塞 2s），改为 epoch 守卫的即时音频收集，残留草稿线程自动隔离；② 声波响应加快——新增逐帧更新的"快速说话指示"（RMS 双阈值滞回，约 10ms 响应）替代 VAD 的 120/200ms 去抖判定，波形平滑系数 0.3→0.5，并移除每 2 秒草稿回调引起的波形状态重置
- **v5.6 有声就有波形**：声波触发阈值从约 -35dB 降至约 -44dB——轻声、气声、以及"嗯/啊"等语气词只要出声就会让波形跳动；波形显示增加平方根压缩，轻声音量也有明显可见的跳动高度，接近静音时仍正常熄灭
- **v5.7 音乐播放器式频谱波形**：声波从 5 根音量条升级为 **15 根频带波形**——录音回调对每帧音频做 FFT，按对数频带（80Hz~8kHz，覆盖人声）划分能量，音调/语气不同波形形状随之变化；采集块细化为 20ms/帧，胶囊加长加高（180×56），波形逐条平滑并带中间高两侧低的包络
- **v5.8 静音静止、说话律动**：按下热键后只显示声波、**不再显示任何汉字**；未说话时波形平静静止（一串低矮竖条），一说话波形就明显律动——响度增益加强、逐条平滑加快、新增"峰值保持-回落"（跳起后缓慢落下）与逐条摆动，动态感更强
- **v5.9 项目整理与文档完善**：删除冗余 `injector.py` 与旧注入测试（注入统一走 `safe_inject.py`）、历史 Agent 工作区/结果（`tasks/` `results/` 按需重建）、过期截图与 `__pycache__` 缓存；补充 Apache-2.0 `LICENSE` 文件；同步 README/部署文档/审核报告
- **v5.10 文档体验**：README 版本记录改为 GitHub 可折叠展示（默认收起、点击展开），后续版本持续追加到折叠区内
- **v5.11 阿里代码审查与修复**：使用 open-code-review（第 9~11 轮，DeepSeek 评审）全量扫描，修复 7 个 high——refiner 非字符串内容崩溃、ASR 并发换模型竞态、剪贴板分配失败数据丢失、词库重试重复、词库写入崩溃、快速双击 recorder 竞态、测试残留误读；另修复 20+ 项 medium（热键生命周期/有界队列、配置容错、VAD 锁外计算、错误信息脱敏等），详见 `voice_ime/OCR审查报告.md`
- **v5.12 文档补充**：README 新增"路线图"章节（P1 补全/工程化/差异化/云端兜底/跨平台）；项目审核报告新增 §8.4（云端 ASR 实测待办、OCR 残留清理清单、工程化与差异化两条推进路线）
- **v5.13.1 单测与 CI**：新增 pytest 单元测试套件（VAD/draft_smoother/refiner/config/hotkey/recorder/cloud_asr/safe_inject/ui，42 项全部通过）；新增 GitHub Actions CI（push/PR 触发，Windows + Python 3.12/3.13，跑 compileall + pytest）
- **v5.13.2 一键模型下载**：新增 `download_model.py`（ModelScope 默认/HF 备用，small/medium，支持断点跳过与 --dry-run），下载后自动更新 config.json 模型路径
- **v5.13.3 润色强度运行时切换**：按 F9 循环切换 保守纠错/轻度规整/完整规整，悬浮窗短暂提示并持久化配置
- **v5.13.4 输入历史记录**：新增 `history.py`（内存队列 + history.json 落盘），成功注入后自动记录，设置窗口可查看/清空
- **v5.13.5 托盘图标 + 设置窗口**：pystray 托盘（开始/停止、打开设置、退出，状态实时更新）；设置窗口五页签（通用/模型/LLM/词库/历史），支持麦克风设备选择与一键下载模型；F8 打开设置
- **v5.13.6 小修清单**：doctor 拒绝组合键（与单键实现对齐）；各模块自检适配 GBK 控制台；相对模型路径基于 voice_ime 解析；API Key 支持 DEEPSEEK_API_KEY 环境变量兜底
- **v5.14 阿里复审第 12~13 轮**：9 个 high 全部修复——orchestrate 工作区缺失跳过与真实路径校验、模型下载 .part 原子改名、热键队列锁、设置窗下载线程安全、环境变量密钥不落盘（resolve_keys）、热键 stop 超时可重启、测试 64 位句柄；另修 medium：词库原子写、.env.example 白名单、词库重试缓存、CI 加固等，详见 `voice_ime/OCR审查报告.md`
- **v5.15 修复 CI 失败**：Overlay 改为复用传入的 Tk 根窗口（消除双根设计，修复 GitHub Actions 下 `tcl_findLibrary` 报错）；UI 测试改用会话级共享 Tk 根，避免创建/销毁循环导致的不稳定；单测 59 项全部通过

</details>

---

## 常见问题

| 问题 | 处理 |
| --- | --- |
| 提示"未配置 API Key" | 编辑 `voice_ime/config.json` 填入 `refine.api_key` |
| 转写报"模型加载失败" | 按部署文档 §5.5 下载模型，确认 `asr.model` 路径 |
| 提示"CUDA 运行库未安装" | 安装 `nvidia-cublas-cu12` `nvidia-cudnn-cu12`（清华镜像），或忽略（自动 CPU） |
| 第一次说话慢/超时 | 首次会加载模型（medium 约 2 秒）；若未手动下载会尝试联网下载 |
| 热键没反应 | 确认 `hotkey` 配置；检查其他软件占用 |
| 注入失败 | 目标窗口为管理员权限会被 UIPI 拦截；失败时文字保留在剪贴板可手动粘贴 |
| 录音时波形不动 | 正常现象：v5.8 起未出声时显示平静的静止波形，一开口波形就会律动跳动 |
| 结束录音后没看到文字预览 | v5 起按需求移除浮窗预览，文字直接注入光标处 |
| 控制台出现「剪贴板恢复未完成」提示 | 文字已成功注入，只是原剪贴板内容未能恢复（其他程序占用/修改剪贴板所致）；不影响输入，可忽略 |
| `python` 不是内部或外部命令 | Python 未加入 PATH，重装并勾选 "Add Python to PATH" |

---

## 许可证

[Apache-2.0](./LICENSE)（个人/黑客松项目，欢迎 fork 与改进）。
