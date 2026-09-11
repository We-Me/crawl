"""`python -m crawler` 等价于正式 CLI 入口。"""

from crawler.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
