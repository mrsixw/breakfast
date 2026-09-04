"""Run a command on a pseudo-terminal, feeding it a canned reply.

Scripts that refuse to act without an interactive terminal cannot be tested
through a pipe, and ``script(1)`` takes different arguments on macOS and Linux.
This is the portable equivalent: fork a pty, write the reply into it, echo
everything the child produced, and exit with the child's status.

Usage: run_pty.py <input> <command> [args...]
"""

import os
import pty
import select
import sys


def main() -> int:
    reply = sys.argv[1].encode()
    command = sys.argv[2:]
    if not command:
        print("run_pty.py: no command given", file=sys.stderr)
        return 2

    pid, fd = pty.fork()
    if pid == 0:  # child
        os.execvp(command[0], command)

    # The line discipline buffers this until the child actually reads, so it is
    # safe to write before the prompt appears.
    if reply:
        os.write(fd, reply if reply.endswith(b"\n") else reply + b"\n")

    chunks = []
    while True:
        try:
            ready, _, _ = select.select([fd], [], [], 30)
        except OSError:
            break
        if not ready:
            break
        try:
            data = os.read(fd, 4096)
        except OSError:  # the child closed the pty: normal at exit
            break
        if not data:
            break
        chunks.append(data)

    os.close(fd)
    _, status = os.waitpid(pid, 0)

    sys.stdout.write(b"".join(chunks).decode("utf-8", "replace"))
    sys.stdout.flush()

    if os.WIFSIGNALED(status):
        return 128 + os.WTERMSIG(status)
    return os.WEXITSTATUS(status)


if __name__ == "__main__":
    sys.exit(main())
