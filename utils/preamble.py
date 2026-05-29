import sys

if sys.version_info < (3, 11):
    sys.stderr.write(
        "Error: breakfast requires Python 3.11 or later.\n"
        f"Currently running with Python {sys.version.split()[0]} "
        f"(at {sys.executable}).\n"
        "Please run breakfast in an environment with Python >= 3.11,\n"
        "or activate a virtualenv with Python 3.11+ before running.\n"
    )
    sys.exit(1)
