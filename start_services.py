#!/usr/bin/env python3
"""
启动脚本 - 同时启动 SportsMole API 服务和 Streamlit 应用
"""

import subprocess
import sys
import os
import time
import signal

def start_sportsmole_api():
    """启动 SportsMole API 服务"""
    sportsmole_dir = r"E:\cc-connect\sportsmole-api"
    if not os.path.exists(os.path.join(sportsmole_dir, "package.json")):
        print("[ERROR] SportsMole API directory not found!")
        return None

    print("[INFO] Starting SportsMole API server...")
    proc = subprocess.Popen(
        ["node", "src/server.js"],
        cwd=sportsmole_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0,
    )

    # 等待启动
    time.sleep(3)
    if proc.poll() is None:
        print(f"[OK] SportsMole API started (PID: {proc.pid})")
        return proc
    else:
        print("[ERROR] SportsMole API failed to start!")
        return None


def start_streamlit():
    """启动 Streamlit 应用"""
    print("[INFO] Starting Streamlit app on port 8501...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app.py",
         "--server.port", "8501",
         "--server.headless", "true"],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0,
    )
    time.sleep(5)
    if proc.poll() is None:
        print(f"[OK] Streamlit app started (PID: {proc.pid})")
        print("[OK] Open http://localhost:8501 in your browser")
        return proc
    else:
        print("[ERROR] Streamlit app failed to start!")
        return None


def main():
    print("=" * 50)
    print("  World Cup Predictor - Service Launcher")
    print("=" * 50)

    # 启动 SportsMole API
    sportsmole_proc = start_sportsmole_api()

    # 启动 Streamlit
    streamlit_proc = start_streamlit()

    if not streamlit_proc:
        print("\n[ERROR] Failed to start!")
        if sportsmole_proc:
            sportsmole_proc.terminate()
        sys.exit(1)

    print("\n" + "=" * 50)
    print("  All services started!")
    print("  SportsMole API: http://localhost:3000")
    print("  Streamlit App:  http://localhost:8501")
    print("=" * 50)
    print("\nPress Ctrl+C to stop all services...")

    # 等待用户中断
    try:
        while True:
            time.sleep(1)
            if streamlit_proc.poll() is not None:
                print("[WARN] Streamlit app exited!")
                break
    except KeyboardInterrupt:
        print("\n[INFO] Stopping services...")
    finally:
        if sportsmole_proc:
            sportsmole_proc.terminate()
        if streamlit_proc:
            streamlit_proc.terminate()
        print("[OK] All services stopped.")


if __name__ == "__main__":
    main()
