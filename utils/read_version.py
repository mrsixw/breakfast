#!/usr/bin/env python3
import tomllib


def main() -> None:
    with open("pyproject.toml", "rb") as handle:
        data = tomllib.load(handle)

    print(data["project"]["version"])


if __name__ == "__main__":
    main()
