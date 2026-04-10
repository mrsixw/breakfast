"""Generate the breakfast man page using click-man."""

import importlib.metadata

import click
from click_man.core import write_man_pages

from breakfast.cli import breakfast


@click.command()
@click.argument("target_dir", default="man1")
def main(target_dir):
    """Generate the breakfast man page into TARGET_DIR."""
    version = importlib.metadata.version("breakfast")
    write_man_pages("breakfast", breakfast, version=version, target_dir=target_dir)


if __name__ == "__main__":
    main()
