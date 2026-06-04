#!/usr/bin/env python3


def main() -> None:
    with open("VERSION", "r") as handle:
        print(handle.read().strip())


if __name__ == "__main__":
    main()
