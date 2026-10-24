"""Module entry point for launching EvoDev desktop application via python -m evodev.gui."""

import sys
from evodev.gui.app import run_gui


def main():
    run_gui()


if __name__ == "__main__":
    main()
