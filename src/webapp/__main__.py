"""Enable `python -m src.webapp serve ...`."""
from src.webapp.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
