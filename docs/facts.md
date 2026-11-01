# facts.md

> README 的唯一事实来源。A 部分由脚本/命令扫描生成后人工核对；B 部分取自仓库内用户文档，无法溯源的留 TODO。
> 更新时间：2026-11-01（v5.19 文档整理后重新核对）

## A. 可自动提取的事实

1. **项目类型**：Windows 桌面 AI 语音输入工具（个人效率工具 / 实验性项目）
2. **版本号**：`voice_ime/version.py` → `5.19.1`（启动日志、设置标题、托盘提示均取此处）；版本策略：5.19.1 为最后一个 5.x，日常提交不递增，仅在发布时更新，首个客户端正式版从 6.0.0 开始
3. **主语言 / 运行时 / 最低版本**：Python；doctor.py 要求 >= 3.10，CI 在 3.12 / 3.13 测试（`.github/workflows/ci.yml` matrix）
4. **安装命令**：`pip install -r voice_ime/requirements.txt`（requirements.txt 存在，2026-11-01 实跑 doctor 通过）
5. **运行命令**：`python main.py`（Tk 版）或双击 `voice_ime/启动.bat`；Qt 客户端预览：`python client_main.py` 或 `启动客户端.bat`
6. **测试命令**：`python -m pytest voice_ime/tests -q` → 实跑结果 **147 passed in 22.33s**（2026-11-01，Python 3.13.3）
7. **静态检查**：`python -m ruff check voice_ime`（CI 同款，2026-11-01 实跑通过）
8. **构建命令**：`python packaging/build_exe.py`（Tk 版，可选 `--cpu-only`）；`python packaging/build_exe.py --client` 打包 Qt 客户端（预览）
9. **环境自检**：`python doctor.py`（7 项；源码首次运行前未建 config.json 时会有 2 项提示，属预期）
10. **真机端到端冒烟**：`python voice_ime/tests/e2e_live.py --no-asr` → 2026-11-01 实跑 **PASS**；`python voice_ime/tests/client_smoke.py` → 2026-11-01 实跑 **PASS**（Qt 客户端 + 假录音/假注入）
11. **目录结构**：
    - `voice_ime/` — 运行时代码，**28 个 .py 模块，7866 行**（2026-11-01 统计，含 `qt_ui/`，不含 tests/）
    - `voice_ime/qt_ui/` — Qt 客户端外壳：主窗口、胶囊、托盘、引擎适配
    - `voice_ime/client_main.py` — Qt 客户端入口（预览）
    - `voice_ime/tests/` — 26 个测试相关 .py（147 项用例 + 手动脚本）
    - `packaging/` — PyInstaller 打包脚本与图标
    - `docs/` — 部署文档、PRD/SPEC/调研、更新记录、`docs/audits/` 审核报告、`docs/images/` 实机截图、`docs/plans/`
    - `.github/workflows/` — `ci.yml`（测试）、`package.yml`（tag 触发打包发布，CPU 版）
12. **主要依赖**（requirements.txt，10 个）：faster-whisper、ctranslate2、sounddevice、pynput、numpy、requests、onnxruntime、pystray、Pillow、PySide6（客户端预览）
13. **环境变量**：`DEEPSEEK_API_KEY`（纠错 Key 兜底）、`ASR_API_KEY`（云端 ASR Key 兜底，其次回退 DEEPSEEK_API_KEY）
14. **模型实测大小**（2026-09-28 记录，未变更）：medium = 1.5G，small = 464M
15. **许可证**：Apache-2.0（LICENSE 存在）
16. **文档清单**：README.md / README_EN.md；docs/ 下：部署文档、PRD、SPEC、调研与产品设计、客户端架构与界面调研、更新记录、`audits/` 四份审核报告 + OCR 审查报告、facts.md
17. **演示素材**：`docs/images/overlay-*.png`（Tk 胶囊）、`client-home.png`、`client-history.png`、`client-settings.png`、`client-settings-model.png`、`client-dictionary.png`、`client-wizard.png`、`client-overlay-recording.png`（Qt 客户端，2026-11-01 真实渲染截取，2 倍像素）；`logo-256.png` 为项目 logo
18. **Qt 客户端状态**：主窗口/托盘/胶囊/录音管线已接通；首次向导（隐私/麦克风试录/模型/热键与 Key）可跳过并保存；设置页可保存并立即生效（模型切换重建引擎、热键重载监听、开机自启、音频设备与录音上限）；词库支持增删改/导入导出/清空学习记录；历史支持重新注入、删除与清空；诊断信息可导出；按应用模式、统计页、更新检查、浅色主题仍待做；最小 Qt 原型包 117.9MB，完整客户端包 733.7MB（含引擎依赖，待裁剪）
19. **模型格式**：仅支持 faster-whisper/CTranslate2 目录（`model.bin` + `config.json` + `tokenizer.json` + `vocabulary.json`）；本机已有 large-v3 与 large-v3-turbo 两个 CT2 目录可直接使用，turbo 完整链路实测通过；详见 `docs/语音模型方案.md`

## B. 需人工确认的事实（已核对）

- **一句话描述**：「按一下热键开始录音，再按一下结束：本地 Whisper 识别 + 大模型保守纠错，干净文本直接注入当前输入框的 Windows 工具。」
- **为什么做这个项目**：见 README「为什么做这个项目」；动机源自 PRD §1 与调研文档 §3 竞品分析
- **隐私边界**：音频不出本机；只有开启纠错时识别文本发往用户配置的 OpenAI 兼容端点（默认 DeepSeek）；不填 Key 零联网
- **与同类方案的差异**：详见 README「与同类工具的差别」；CapsWriter-Offline 的 star 数（7046）与「按住 CapsLock、FunASR 离线、热词 + LLM 润色」取自其 GitHub 仓库页（2026-11-01 查询）
- **已知限制**：见 README「已知限制」，含右侧 Alt 在部分布局等于 AltGr、云端 ASR 未真机联调、管理员窗口 UIPI 拦截、历史/学习明文落盘、长录音内存线性增长、打包版 GPU 未在 CI 验证
- **AI 参与声明**：README 原文——「由 AI 辅助开发（多 Agent 分模块实现，经多轮 AI 代码审查与三轮人工抽验）」

## 核对记录（2026-11-01）

- [x] pytest 实跑 127 passed；doctor 实跑（依赖/麦克风/GPU 通过，config.json 未建时按预期提示）
- [x] `ruff check`、`compileall` 实跑通过
- [x] `tests/e2e_live.py --no-asr` 实跑 PASS（真实注入 + 剪贴板恢复）
- [x] 模块数（16）、行数（4389）、测试数（127）均以命令输出为准
- [x] 演示截图为真实 Overlay 渲染结果的截屏，未做 UI 像素修改
- [x] 仓库内无明文密钥（`sk-` / `ghp_` 仅出现在测试假 key）
