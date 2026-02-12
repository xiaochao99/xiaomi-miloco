# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Setup script for miloco-server with built-in model support.
Uses setuptools for package distribution.
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README
readme_path = Path(__file__).parent / "README.md"
long_description = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""

setup(
    name="miloco-server",
    version="0.0.1",
    description="High-performance microservice system built on FastAPI",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Miloco team",
    author_email="xiaomi-miloco@xiaomi.com",
    python_requires=">=3.11",
    packages=find_packages(),
    package_data={
        "miloco_server.detection.models": ["*.onnx", "README.md"],
    },
    include_package_data=True,
    zip_safe=False,  # Required for accessing package data files
    install_requires=[
        "fastapi>=0.115.3",
        "uvicorn[standard]>=0.24.0",
        "jinja2>=3.1.6",
        "python-multipart>=0.0.18",
        "pydantic>=2.4.0",
        "PyJWT>=2.8.0",
        "openai>=1.3.0",
        "opencv-python-headless>=4.8.0",
        "numpy>=1.24.0",
        "pillow>=10.3.0",
        "imagehash>=4.3.0",
        "fastmcp>=2.11",
        "aiohttp>=3.12.14",
        "thespian>=3.10.0",
        "aiofiles>=23.2.0",
        "aiocache>=0.12.0",
        "cachetools>=5.3.0",
        "croniter>=1.4.0",
        "sqlalchemy>=1.4.42,<2.0.0",
        "alembic>=1.12.0",
        "python-dotenv>=1.0.0",
        "httpx>=0.25.0",
        "websockets>=12.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.21.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
        ],
        "detection": [
            "onnxruntime>=1.16.0",
        ],
        "detection-gpu": [
            "onnxruntime-gpu>=1.16.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "miloco-server=miloco_server.main:start_server",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
