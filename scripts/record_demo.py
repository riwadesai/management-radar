"""Record a scripted demo of the running app to a video file.

    python scripts/record_demo.py            # app must be running on :8000

Timings follow DEMO_SCRIPT.md so narration can be read over the top.
Output: demo/demo.webm (+ demo.mp4 if ffmpeg is installed).
"""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8000"
OUT = Path(__file__).resolve().parent.parent / "demo"
W, H = 1440, 900


T0 = time.time()
MARKS: list[tuple[str, float]] = []


def mark(label: str) -> None:
    MARKS.append((label, time.time() - T0))


def hold(s: float) -> None:
    time.sleep(s)


def ask(page, question: str) -> None:
    box = page.locator("#q")
    box.click()
    box.type(question, delay=35)
    hold(0.6)
    page.keyboard.press("Enter")
    # answered, or an error bubble: either way the typing indicator goes away
    page.locator(".msg.typing").wait_for(state="detached", timeout=180_000)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for f in OUT.glob("*.webm"):
        f.unlink()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": W, "height": H},
                                  record_video_dir=str(OUT),
                                  record_video_size={"width": W, "height": H})
        page = ctx.new_page()
        global T0
        T0 = time.time()
        page.goto(URL)
        page.wait_for_selector(".item")
        # 0:00 Maruti timeline
        page.get_by_role("tab", name="Maruti Suzuki").click()
        page.wait_for_selector(".summary")
        mark("Maruti timeline")
        hold(22)
        # 0:30 scroll the timeline
        mark("scrolling timeline")
        for _ in range(4):
            page.mouse.wheel(0, 260); hold(2.2)
        hold(3)
        for _ in range(4):
            page.mouse.wheel(0, -260); hold(0.4)
        # 0:45 promise tracker
        page.get_by_role("tab", name="Promise tracker").click()
        mark("promise tracker")
        hold(10)
        for _ in range(3):
            page.mouse.wheel(0, 260); hold(3)
        hold(5)
        page.mouse.wheel(0, -2000); hold(1)
        page.get_by_role("tab", name="Timeline").click()
        # 1:10 chat: expansion
        mark("typing expansion question")
        ask(page, "What has management said about expansion plans?")
        mark("expansion answer shown")
        hold(6)
        cite = page.locator(".cite").first
        if cite.count():
            cite.hover(); hold(4)
        hold(6)
        # 1:50 trap
        mark("typing Brazil trap")
        ask(page, "What did Maruti say about its plans to build cars in Brazil?")
        mark("not-found answer shown")
        hold(12)
        # 2:15 Infosys
        page.get_by_role("tab", name="Infosys").click()
        page.wait_for_selector(".summary")
        mark("Infosys timeline")
        hold(3)
        ask(page, "Who is the new CEO designate and when does Salil Parekh step down?")
        mark("CEO answer shown")
        hold(6)
        cite = page.locator(".cite").last
        if cite.count():
            cite.hover(); hold(4)
        hold(6)
        # 2:50 close on the timeline
        page.mouse.wheel(0, 300)
        mark("closing")
        hold(10)
        ctx.close()
        browser.close()
    webm = next(OUT.glob("*.webm"))
    final = OUT / "demo.webm"
    webm.rename(final)
    print("wrote", final)
    (OUT / "marks.txt").write_text("\n".join(f"{int(s)//60}:{int(s)%60:02d}  {l}" for l, s in MARKS) + "\n")
    print((OUT / "marks.txt").read_text())
    if shutil.which("ffmpeg"):
        mp4 = OUT / "demo.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(final),
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "22", str(mp4)], check=True)
        print("wrote", mp4)


if __name__ == "__main__":
    main()
