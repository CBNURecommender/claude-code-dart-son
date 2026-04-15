import os
from dataclasses import dataclass
from dotenv import load_dotenv


@dataclass
class Config:
    dart_api_key: str
    telegram_bot_token: str
    telegram_chat_id: str
    poll_interval: int = 30

    @classmethod
    def from_env(cls) -> "Config":
        load_dotenv()
        missing = []
        for key in ("DART_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
            if not os.getenv(key):
                missing.append(key)
        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}"
            )
        return cls(
            dart_api_key=os.environ["DART_API_KEY"],
            telegram_bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
            telegram_chat_id=os.environ["TELEGRAM_CHAT_ID"],
            poll_interval=int(os.getenv("POLL_INTERVAL", "30")),
        )
