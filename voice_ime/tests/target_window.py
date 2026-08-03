# -*- coding: utf-8 -*-
"""目标窗口进程：创建文本框接收注入，结果写入项目根目录 result.txt"""
import ctypes, os, sys, time, tkinter as tk

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # voice_ime 根
os.chdir(BASE)
sys.path.insert(0, BASE)

# v5.11：清理上次运行残留的结果文件，避免误读旧结果
if os.path.exists("result.txt"):
    os.remove("result.txt")

user32 = ctypes.windll.user32
root = tk.Tk()
txt = tk.Text(root)
txt.pack()
root.geometry("500x300+100+100")
root.update()
root.lift()
root.attributes("-topmost", True)
hwnd = user32.GetParent(root.winfo_id())
user32.SetForegroundWindow(hwnd)
root.update()
time.sleep(0.3)
root.update()
txt.focus_set()
root.update()

with open("target_ready.txt", "w", encoding="utf-8") as f:
    f.write("ready")

def check():
    # v5.11：连续两轮内容一致才落盘，避免轮询时输入尚未完成导致截断
    got = txt.get("1.0", "end").strip()
    if got:
        if got == last_content[0]:
            stable_count[0] += 1
            if stable_count[0] >= 2:
                with open("result.txt", "w", encoding="utf-8") as f:
                    f.write(got)
                root.quit()
                return
        else:
            stable_count[0] = 0
        last_content[0] = got
    root.after(200, check)


last_content = [""]
stable_count = [0]
root.after(200, check)
root.after(30000, root.quit)  # v5.11：30s 超时，注入稍慢时不再误杀
root.mainloop()
