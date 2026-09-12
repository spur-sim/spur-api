from arq.connections import RedisSettings

from spur_api.config import settings
from spur_api.db.session import get_session_factory
from spur_api.worker.tasks import run_simulation


async def startup(ctx) -> None:
    ctx["session_factory"] = get_session_factory()


class WorkerSettings:
    functions = [run_simulation]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    on_startup = startup
    # v1 default: one simulation run at a time per worker process (each
    # run is CPU-bound Python, not I/O-bound, so in-process concurrency
    # just adds GIL contention rather than throughput). Scale out by
    # running more worker processes/containers against the same queue.
    max_jobs = 1
