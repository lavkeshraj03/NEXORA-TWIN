"""Infrastructure worker. Tenant jobs will be registered with authorization in later phases."""
from redis import Redis
from rq import Queue, Worker
from app.core.config import get_settings


def main():
    connection = Redis.from_url(get_settings().redis_url.get_secret_value())
    worker = Worker([Queue("nexora", connection=connection)], connection=connection)
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
