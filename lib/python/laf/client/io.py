"""Input / Output functions."""

import sys
import yaml

__all__ = ['read_stdin']


def read_stdin(message=None, ask_tty=False):
    """
    Display message on STDERR and read STDIN until Ctrl-D (i.e. EOF)
    @type message: string
    @param message: Message to display before reading the input.
    """
    if sys.stdin.isatty() != ask_tty:
        return None

    if message and ask_tty:
        # W0104(pointless-statement), read_stdin]
        # pylint: disable=W0104
        print(message, file=sys.stderr)

    stdin_input = sys.stdin.read()
    return yaml.load(stdin_input)
