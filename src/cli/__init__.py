"""
wayland-debug - A command line tool to help debug Wayland clients and servers.

This package provides tools for viewing, filtering, and setting breakpoints
on Wayland protocol messages.
"""

__version__ = "0.1.0"
__author__ = "Sophie Winter"
__email__ = "git@phie.me"

from .main import run

__all__ = ["run"]
