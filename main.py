#!/usr/bin/env python3
import logging
import sys
import os
import warnings
from logging.handlers import RotatingFileHandler

# Set UTF-8 encoding for console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Suppress SSL warnings for development
warnings.filterwarnings("ignore", message="Unverified HTTPS request")

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config  # noqa: E402
from cli.commands import build_parser, COMMANDS  # noqa: E402


def setup_logging():
    """Configure logging with rotating file handler + console output."""
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "dart-noti-bot.log")

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler
    file_handler = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)


def main():
    setup_logging()
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        config = Config.from_env()
    except ValueError as e:
        print(f"❌ 설정 오류: {e}")
        sys.exit(1)

    cmd_func = COMMANDS.get(args.command)
    if cmd_func:
        cmd_func(args, config)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
