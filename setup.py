from setuptools import setup, find_packages

setup(
    name="fieldstation42",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[],  # base CLI has no deps
    entry_points={
        "console_scripts": [
            "fs42=fs42.cli:main"
        ]
    },
)

