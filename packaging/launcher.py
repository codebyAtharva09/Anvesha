"""Entry point for the standalone executable: `ANVESHA.exe` opens the GUI;
`ANVESHA.exe bench|run|video ...` exposes the full CLI."""
import sys
from anvesha.__main__ import main

if __name__ == "__main__":
    main(sys.argv[1:] or ["gui"])
