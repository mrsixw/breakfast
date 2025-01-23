from platform import python_version

from setuptools import setup
from setuptools.config.expand import entry_points

with open("requirements.txt") as f:
    requirements = f.read().splitlines()

setup(
    name="breakfast",
    version="0.1.0",
    description="A tool to help you start your day",
    py_modules=["breakfast"],
    entry_points={
        "console_scripts": ["breakfast=breakfast:breakfast"]
    },
    install_requires=requirements,
    license_files=["LICENSE"],
    author="Steve Williams",
    python_version=">=3.12"
)