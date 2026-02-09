# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Miloco Main Server Startup Script
"""

import sys
import traceback
from pathlib import Path

def setup_project_path():
    """Setup project paths to ensure miloco_server module can be found"""
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))


def main():
    setup_project_path()
    try:
        from miloco_server.main import start_server
    except ImportError as e:
        print("❌ Import Error: Please install project dependencies first!")
        print("📝 Solution: Run 'pip install -e .' in miloco_server folder")
        print(f"   Error details: {e}")
        print("\nFull traceback:")
        traceback.print_exc()
        sys.exit(1)
    
    print("🚀 Starting Miloco server...")
    print("⚡ Press Ctrl+C to stop service")
    print("-" * 60)
    
    try:
        start_server()
    except KeyboardInterrupt:
        print("\n👋 Service stopped, thank you for using!")
    except Exception as e: # pylint: disable=broad-exception-caught
        print(f"❌ Service startup failed: {e}")
        print("\nFull traceback:")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
