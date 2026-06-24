"""
World Cup Predictor - 2026世界杯比分预测模型

四层融合架构：Elo + Dixon-Coles泊松 + 蒙特卡洛 + 贝叶斯
"""

from setuptools import setup, find_packages

setup(
    name="worldcup-predictor",
    version="1.0.0",
    description="2026世界杯比分预测模型 - Elo + 泊松 + 蒙特卡洛 + 贝叶斯融合",
    author="worldcup-predictor",
    author_email="",
    url="https://github.com/caohaoyuan12138/worldcup-predictor",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "numpy>=1.24.0",
        "scipy>=1.10.0",
        "pandas>=2.0.0",
        "requests>=2.28.0",
        "feedparser>=6.0.10",
    ],
    extras_require={
        "web": ["streamlit>=1.28.0"],
        "dev": ["pytest>=7.4.0"],
    },
    entry_points={
        "console_scripts": [
            "worldcup-predictor=cli:main",
        ],
    },
    python_requires=">=3.8",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Sports",
        "License :: MIT",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
)