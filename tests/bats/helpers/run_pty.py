"""Run a command on a pseudo-terminal, feeding it a canned reply.

Scripts that refuse to act without an interactive terminal cannot be tested
through a pipe, and ``script(1)`` takes different arguments on macOS and Linux.
This is the portable equivalent: fork a pty, write the reply into it, echo
everything the child produced, and exit with the child's status.

Usage: run_pty.py <input> <command> [args...]

A regression that adds a prompt, or hangs while still chattering, must fail the
test rather than wedge CI, so the whole run is under a deadline. Override it
with RUN_PTY_TIMEOUT (seconds).
"""

import os
import pty
import select
import signal
import sys
import time

TIMEOUT = float(os.environ.get("RUN_PTY_TIMEOUT", "60"))
TIMED_OUT = 124  # the exit status timeout(1) uses


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

    deadline = time.monotonic() + TIMEOUT
    chunks = []
    timed_out = False

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            timed_out = True
            break
        try:
            ready, _, _ = select.select([fd], [], [], min(remaining, 1.0))
        except OSError:
            break
        if not ready:
            # Quiet, but the child may simply be working. Only the deadline
            # ends the run; a silent gap does not.
            if _reaped(pid):
                break
            continue
        try:
            data = os.read(fd, 4096)
        except OSError:  # the child closed the pty: normal at exit
            break
        if not data:
            break
        chunks.append(data)

    os.close(fd)

    if timed_out:
        _kill(pid)
        sys.stdout.write(b"".join(chunks).decode("utf-8", "replace"))
        print(f"\nrun_pty.py: timed out after {TIMEOUT:g}s", file=sys.stderr)
        sys.stdout.flush()
        return TIMED_OUT

    _, status = os.waitpid(pid, 0)

    sys.stdout.write(b"".join(chunks).decode("utf-8", "replace"))
    sys.stdout.flush()

    if os.WIFSIGNALED(status):
        return 128 + os.WTERMSIG(status)
    return os.WEXITSTATUS(status)


def _reaped(pid: int) -> bool:
    """Has the child exited? Non-blocking."""
    try:
        done, _ = os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        return True
    return done == pid


def _kill(pid: int) -> None:
    """Stop the child, politely then not."""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            return
        for _ in range(20):
            if _reaped(pid):
                return
            time.sleep(0.05)


if __name__ == "__main__":
    sys.exit(main())
