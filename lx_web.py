"""Compatibility wrapper for the lx_web Flask application.

The real Web application lives in :mod:`lx_web.app`. Keep this file thin so
older commands such as ``python lx_web.py`` still start the same Blueprint-based
application instead of a second, divergent Flask app.
"""

from lx_web.app import create_app, main

app = create_app()


if __name__ == "__main__":
    main()
