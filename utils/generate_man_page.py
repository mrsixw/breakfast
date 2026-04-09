"""Generate the breakfast man page using click-man."""

import importlib.metadata
import sys

from click_man.core import write_man_pages

from breakfast.cli import breakfast

target_dir = sys.argv[1] if len(sys.argv) > 1 else "man1"
version = importlib.metadata.version("breakfast")
write_man_pages("breakfast", breakfast, version=version, target_dir=target_dir)
