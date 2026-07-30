#!/usr/bin/env python3
"""
JPT Sales Toolkit - Startup Script
跨平台启动脚本，支持 Windows 和 macOS
"""
import argparse
import importlib.util
import os
import sys
import webbrowser
from pathlib import Path
import time

# 确保能找到backend模块
APP_ROOT = Path(__file__).parent
sys.path.insert(0, str(APP_ROOT))


def check_dependencies():
    """Fail clearly without mutating the user's Python environment."""
    required = {
        "fastapi": "fastapi",
        "uvicorn": "uvicorn",
        "python-multipart": "multipart",
        "cryptography": "cryptography",
        "httpx": "httpx",
        "requests": "requests",
        "certifi": "certifi",
    }
    missing = [
        package for package, module in required.items()
        if importlib.util.find_spec(module) is None
    ]
    if missing:
        raise SystemExit(
            "Missing runtime dependencies: "
            + ", ".join(missing)
            + f"\nInstall the locked project requirements first:\n"
            + f'  "{sys.executable}" -m pip install -r "{APP_ROOT / "requirements.txt"}"'
        )


def main():
    parser = argparse.ArgumentParser(description='JPT Sales Toolkit')
    parser.add_argument('--host', default='127.0.0.1', help='Host to bind to')
    parser.add_argument('--port', type=int, default=8000, help='Port to bind to')
    parser.add_argument('--data-dir', help='Custom data directory path')
    parser.add_argument('--no-browser', action='store_true', help='Do not open browser')
    args = parser.parse_args()

    # 检查依赖
    check_dependencies()

    # 设置数据目录
    if args.data_dir:
        os.environ['JPT_DATA_DIR'] = args.data_dir
        print(f"Using custom data directory: {args.data_dir}")

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                    JPT Sales Toolkit                         ║
║                                                              ║
║  Starting server at http://{args.host}:{args.port}                   ║
║                                                              ║
║  Press Ctrl+C to stop the server                             ║
╚══════════════════════════════════════════════════════════════╝
    """)

    # 打开浏览器
    if not args.no_browser:
        def open_browser():
            time.sleep(1.5)
            webbrowser.open(f'http://{args.host}:{args.port}')

        import threading
        threading.Thread(target=open_browser, daemon=True).start()

    # 启动服务器
    import uvicorn
    uvicorn.run(
        "backend.app_v2:app",
        host=args.host,
        port=args.port,
        reload=False,
        log_level="info"
    )


if __name__ == '__main__':
    main()
