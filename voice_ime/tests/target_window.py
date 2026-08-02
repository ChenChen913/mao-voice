# -*- coding: utf-8 -*-
"""目标窗口进程：创建文本框接收注入，结果写入项目根目录 result.txt"""
import ctypes, os, sys, time, tkinter as tk

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # voice_ime 根
os.chdir(BASE)
sys.path.insert(0, BASE)

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
    got = txt.get("1.0", "end").strip()
    if got:
        with open("result.txt", "w", encoding="utf-8") as f:
            f.write(got)
        root.quit()
        return
    root.after(200, check)

root.after(200, check)
root.after(10000, root.quit)
root.mainloop()
