"""RQ worker entry point."""

from redis import Redis
from rq import Queue, Worker

from .config import settings
from .logging_config import configure_logging


def main() -> None:
    configure_logging()
    connection = Redis.from_url(settings.redis_url)
    worker = Worker([Queue("optimizations", connection=connection)], connection=connection)
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
