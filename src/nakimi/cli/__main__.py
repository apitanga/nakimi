"""Entry point for python -m nakimi.cli"""
import sys
import io

# Force UTF-8 encoding for stdout/stderr
# This ensures emoji and Unicode work in pipes, redirects, and Kimi CLI
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from .main import main

if __name__ == "__main__":
    main()
