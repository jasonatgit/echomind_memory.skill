from setuptools import setup

setup(
    name="echomind-memory",
    version="1.1.1",
    description="EchoMind Memory — AI Persistent Memory System (SQLite, 6 memory types, RL optimization)",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="jasonatgit",
    license="MIT",
    url="https://github.com/jasonatgit/echomind_memory.skill",
    py_modules=["main", "__init__"],
    packages=[
        "core", "core.models", "core.storage", "core.learning", "core.agents",
        "adapters", "code_format",
    ],
    package_data={
        "code_format": ["memory.schema.json"],
    },
    python_requires=">=3.10",
    install_requires=[
        "pydantic>=2.7",
        "python-dotenv>=1.0",
        "numpy>=1.26",
        "PyYAML>=6.0",
    ],
    extras_require={
        "http": ["fastapi>=0.100", "uvicorn>=0.20"],
    },
    entry_points={
        "console_scripts": [
            "echomind=code_format.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries",
    ],
)