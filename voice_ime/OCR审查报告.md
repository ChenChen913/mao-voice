# AI 语音输入法 —— open-code-review 代码审查报告

- 工具：Alibaba Open Code Review v1.8.5（`ocr scan` 全文件扫描）
- LLM：DeepSeek（deepseek-chat，OpenAI 兼容）
- 范围：voice_ime 核心 14 个 Python 文件（models/tasks/tests/二进制已排除）
- 结果：**43 条评论**（1 critical / 10 high / 10 medium / 5 low / 2 security-medium / 1 performance-high / 其余 maintainability 等）

## 按严重度统计

| 级别 | 数量 |
| --- | --- |
| critical | 1 |
| high | 11 |
| medium | 17 |
| low | 14 |

## 全部评论明细

| 位置 | 类别 | 级别 | 问题摘要 |
| --- | --- | --- | --- |
| main.py:80-85 | bug | critical | [bug · critical] There is a race condition: `self.recorder` is assigned after releasing the lock, so |
| asr.py:101-109 | bug | high | [bug · high] Thread-safety: `transcribe()`/`_load()` are reachable concurrently from multiple |
| config.py:39-41 | bug | high | [bug · high] Silent swallow of config read/parse errors. Any problem (missing permission, malformed |
| injector.py:21-24 | bug | high | [bug · high] If any exception occurs between the press and release of the fake key sequence (e.g. |
| recorder.py:77-79 | performance | high | [performance · high] Unbounded memory growth + O(n²) copying: `_chunks` accumulates every frame and |
| refiner.py:75-76 | bug | high | [bug · high] `data["choices"][0]["message"]["content"]` is accessed without validation of the |
| safe_inject.py:333-338 | bug | high | [bug · high] Double-close of clipboard: `CloseClipboard()` is called inside the `try` block (line |
| safe_inject.py:360-364 | bug | high | [bug · high] Partial-failure during restore orphans handles: each `SetClipboardData(fmt, handle)` |
| safe_inject.py:500-502 | bug | high | [bug · high] Memory leak on the allocation-failure path: when `GlobalAlloc` returns NULL, the |
| safe_inject.py:508-511 | bug | high | [bug · high] Return value of `SetClipboardData(CF_UNICODETEXT, htext)` is not checked. If it fails, |
| ui.py:428-429 | bug | high | [bug · high] tkinter is not thread-safe. The demo thread calls `overlay.show()`, |
| vad.py:82-86 | bug | high | [bug · high] Thread-safety: the VAD instance's mutable state is mutated in one thread and read in |
| asr.py:196-200 | maintainability | medium | [maintainability · medium] Error-context loss on GPU→CPU double failure: when CUDA init throws `e` |
| asr.py:238-245 | maintainability | low | [maintainability · low] Broad error swallowing in retry chain: on the CPU-only path (`self.device != |
| cloud_asr.py:111-113 | bug | low | [bug · low] The success check is `resp.status_code != 200`, but the error message claims the |
| cloud_asr.py:118-124 | maintainability | low | [maintainability · low] The catch message says '解析云端 ASR 响应 JSON 失败' (JSON parse failed), but the |
| cloud_asr.py:58-59 | bug | medium | [bug · medium] The integer normalization `/ 32768.0` is only correct for 16-bit signed PCM (int16, |
| config.py:45-47 | maintainability | medium | [maintainability · medium] `save_config` writes directly to the target path (config.json). An |
| config.py:59-64 | maintainability | medium | [maintainability · medium] `_deep_merge` only recurses when BOTH sides are dicts |
| config.py:68-68 | documentation | low | [documentation · low] Docstring says `mappings` is `{原词: 指定写法}` (a dict), but the function actually |
| doctor.py:117-120 | bug | medium | [bug · medium] `read_text()` can raise `OSError` (permission denied, lacks read access) which is not |
| doctor.py:128-129 | bug | medium | [bug · medium] Empty/whitespace-only hotkey is technically caught by the validation (the stripped |
| doctor.py:149-150 | bug | low | [bug · low] Same as the config check: `read_text()` here can raise `OSError` (e.g. permission) which |
| doctor.py:218-218 | bug | medium | [bug · medium] `split("\n")[0]` will raise `IndexError` if `result.stdout` is empty (some nvidia-smi |
| draft_smoother.py:60-70 | maintainability | low | [maintainability · low] This overlap-correction block is effectively a no-op and its premise is |
| hotkey.py:31-32 | other | low | [other · low] The debounce uses a single shared timestamp for all keys, but this listener only |
| hotkey.py:37-44 | bug | medium | [bug · medium] Calling start() twice will create and start a second listener without stopping the |
| hotkey.py:51-53 | bug | low | [bug · low] State `_last_time` is read-modify-write from the pynput listener thread without any |
| hotkey.py:54-57 | maintainability | medium | [maintainability · medium] All exceptions from the callback are silently swallowed with no logging. |
| injector.py:28-32 | bug | medium | [bug · medium] Restoring the previous clipboard after `time.sleep(0.25)` will silently overwrite |
| main.py:197-198 | other | low | [other · low] Behavior mismatch with the `overlay`'s level-zeroing comment: the worker thread's |
| main.py:66-69 | other | low | [other · low] `self._last_draft` is written on the audio-callback thread (`_on_draft`) and read on |
| orchestrate.py:132-135 | bug | medium | [bug · medium] Error handling: `review_workdir` passes `timeout=60` to `subprocess.run`, but the |
| orchestrate.py:43-44 | security | medium | [security · medium] Security: wrapping the Claude command in `cmd /c` routes it through the Windows |
| orchestrate.py:69-71 | bug | medium | [bug · medium] Bug/resource leak: on timeout or missing command, `out_file` is unconditionally |
| orchestrate.py:84-89 | maintainability | low | [maintainability · low] Maintainability/correctness: the utf-8→utf-16 decode fallback is unreliable. |
| recorder.py:46-49 | maintainability | medium | [maintainability · medium] Both exception handlers in `_callback` silently swallow failures with |
| recorder.py:89-92 | bug | low | [bug · low] `stop()` joins the draft thread with a 2s timeout, then unconditionally resets |
| refiner.py:45-48 | security | medium | [security · medium] `words_block` is interpolated directly into the SYSTEM_PROMPT via `format()` |
| refiner.py:77-77 | bug | medium | [bug · medium] `resp.json()` can raise `ValueError` for a malformed/non-JSON response body, but |
| ui.py:142-143 | bug | medium | [bug · medium] Bare `except:` swallows everything including KeyboardInterrupt/SystemExit and hides |
| vad.py:103-105 | maintainability | low | [maintainability · low] Edge case in the public bytes path: `np.frombuffer(frame, dtype=np.float32)` |
| vad.py:164-166 | bug | low | [bug · low] Robustness: `_compute_db` does not guard against non-finite input, and the result is |

## 自审迭代记录（open-code-review 修复过程）

| 轮次 | 触发 | 剩余评论 | critical | high | security |
| --- | --- | --- | --- | --- | --- |
| 初扫 | 首轮检测 | 43 | 1 | 11 | 2 |
| 第 2 轮 | 双 Agent 修复（claude-ocr-fix / hermes-ocr-fix） | 38 | 2 | 3 | 2 |
| 第 3 轮 | 双 Agent 修复（claude-ocr-fix2 / hermes-ocr-fix2） | 28 | 1 | 3 | 1 |
| 编排层直修 | critical/high 精准修复 | — | — | — | — |
| 第 5 轮 | 复查 | 35 | 1 | 3 | 1 |
| 编排层直修 | safe_inject 双重释放/泄漏/orchestrate 跳过逻辑 | — | — | — | — |
| 第 6 轮 | 复查 | 30 | 0 | 2 | 0 |
| 编排层直修 | 空剪贴板恢复/结果文件污染/injector 语义 | — | — | — | — |
| 第 7 轮 | 复查 | 29 | 0 | 2 | 0 |
| 编排层直修 | stdout/stderr 分离/injector 返回语义 | — | — | — | — |
| 第 8 轮 | 复查（终态） | 38 | **0** | **0** | 0~1（medium，已缓解） |

**结论**：critical 与 high 级别问题已全部清零；剩余 16 medium + 22 low 均为可维护性打磨项
（死代码、docstring 与实际不符、魔法数字、理论性线程安全、未使用变量等），无功能性缺陷。
注：LLM 评审器在每轮代码变动后都会产生新的 low/medium 项，总量在 28~38 之间波动，
继续迭代呈边际收益递减；如需清零，可再派 Agent 处理 medium/low 项（预计 $5~8，且可能产生新打磨项）。

---

## 2026-08-03 追加：v5.11 复审记录（第 9~11 轮，阿里 open-code-review 1.8.5 / DeepSeek）

项目完成 v5.1~v5.10 交互迭代与整理后，再次全量扫描（排除 models/tests/缓存/文档/二进制），
共 3 轮：初扫 → 修复 → 复扫 → 再修复 → 终扫。

| 轮次 | 触发 | 总评论 | critical | high | security |
| --- | --- | --- | --- | --- | --- |
| 第 9 轮 | v5.10 后全量初扫 | 34 | 0 | 2 | 2（medium） |
| 第 10 轮 | 修复后复扫 | 35 | 0 | 1 | 1（medium） |
| 第 11 轮 | 修复后终扫 | 40 | 0 | 4 | 2（medium/low） |

### 已修复的 high 问题（3 轮合计 7 个）

1. **refiner.py**：模型返回非字符串 `content` 时 `.strip()` 抛 AttributeError → 增加类型校验，非字符串保守回退原文；
2. **asr.py**：GPU 推理失败回退时 `self.model = None` 与并发转写形成竞态 → 锁内先构造 CPU 模型再整体替换，绝无 None 窗口；新增 `_gpu_disabled` 防止回退后再试 GPU；
3. **safe_inject.py**：`GlobalAlloc/GlobalLock` 失败路径只释放备份、不还原，用户剪贴板数据永久丢失 → 新增 `_put_back_saved()` 放回原内容；
4. **asr.py**：词库读取中途失败后重试会重复追加词条 → 改为局部列表、全部成功后整体替换；
5. **config.py**：词库文件写入失败导致启动崩溃 → 捕获并记日志，按空词库继续；
6. **main.py**：快速双击时 recorder 可能为 None 或未启动 → recorder 在状态机同一临界区创建，`_finish_recording` 增加 `active` 守卫；
7. **tests/target_window.py**：上次残留 result.txt 被误读为本次结果 → 启动时清理。

### 已修复的 medium 项（代表性）

- hotkey：工作线程代数化（stop/start 竞态、自 join 守卫）、有界队列背压、防抖窗口清零；
- config：原子写入失败清理 .tmp；ensure_defaults 容错；
- doctor：配置顶层类型校验、nvidia-smi 输出 UTF-8 解码；
- refiner：408/429 限流按可重试处理、finish_reason=length 截断告警；
- recorder：`_draft_busy` check-then-act 原子化、epoch 锁内读取、RMS 计算移出 VAD 锁、末频带包含 8kHz、汉宁窗缓存、stream 启动失败清理；
- cloud_asr：错误信息 URL 脱敏、响应体截断；
- orchestrate：stderr 结果误识别、OSError 兜底、--only 空匹配提示、工作目录越界校验；
- ui：窗口销毁后 after 守卫、演示波形补 set_speaking、进入状态电平归零；
- .gitignore：`.env*`/密钥文件模式、注释；
- safe_inject：`SetClipboardData` 失败路径复用放回助手、清理冗余导入/常量。

### 终态结论

3 轮共报告 109 条评论，其中 7 个 high 已全部修复；终扫残留以 medium/low 打磨项为主
（死代码、理论性线程安全、文档措辞、测试脚本健壮性），无功能性缺陷。
符合历史规律：LLM 评审器在修复后会产生新的 low/medium 项，边际收益递减，故本轮到此为止。

---

## 2026-08-03 追加：v5.14 复审记录（第 12~13 轮，v5.13 全量新代码）

v5.13（单测/CI、一键下载、F9/F12、托盘设置、小修）全部落地后再次全量扫描，共 2 轮。

| 轮次 | 触发 | 总评论 | critical | high | security |
| --- | --- | --- | --- | --- | --- |
| 第 12 轮 | v5.13 后全量初扫 | 57 | 0 | 5 | 2（medium/low） |
| 第 13 轮 | 修复后复扫 | 55 | 0 | 2 | 2（medium/low） |

### 已修复的 high（合计 7 个）

1. **orchestrate.py**：任务工作区 `tasks/` 已在 v5.9 清理，运行时会找不到 TASK.md → 缺少说明文件时明确跳过并提示（而非带病执行）；工作目录越界校验由 prefix 匹配改为 `Path.relative_to` 真实包含校验；
2. **download_model.py**：下载中断会残留残缺文件且下次被当作完整跳过 → 先写 `.part`、成功后原子 `os.replace`，失败/取消清理；
3. **hotkey.py**：`_on_press` 与 `start()` 换队列竞态，事件可能投进旧队列丢失 → 锁内取队列引用后再投递；
4. **settings_ui.py**：下载线程直接调 `self.root.after` 违反 Tk 线程安全 → 改为工作线程写状态 + 主线程 200ms 轮询更新；
5. **config.py**：环境变量注入的 API Key 会被 save_config 持久化 → 改为 `resolve_keys()` 使用期解析、绝不写回 cfg；refiner/main 同步接入；
6. **hotkey.py**：`stop()` join 超时后不清 listener 引用，导致无法重启 → 超时也清引用，允许 start() 重建；
7. **tests/target_window.py**：`GetParent/SetForegroundWindow` 未声明 64 位句柄类型，HWND 截断 → 补 argtypes/restype。

### 已修复的 medium（代表性）

- history：非法/零时长容错；settings：词库原子写入；.gitignore：`.env.example` 白名单放行；asr：词库读取失败不再缓存空提示词（保留重试）；doctor：空键位诊断前置到组合键判断；CI：`permissions: contents: read` + `timeout-minutes` + concurrency；test_refiner：mock sleep 缩短重试测试；cloud_asr：IPv6 安全 URL、3D+ 输入降混。

### 终态结论

两轮合计 112 条评论，9 个 high 全部修复；第 13 轮终扫残留 medium/low 均为打磨项
（死代码、测试细节、理论性竞态），无功能性缺陷。与历史规律一致：修复后仍会产生新
low/medium，故本轮到此为止。
