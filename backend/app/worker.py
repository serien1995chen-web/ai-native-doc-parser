from arq.connections import RedisSettings


async def startup(ctx):
    print("worker startup")


async def shutdown(ctx):
    print("worker shutdown")


async def test_task(ctx, name):
    print(f"hello {name}")
    return f"done {name}"


class WorkerSettings:
    functions = [
        test_task,
    ]

    redis_settings = RedisSettings(
        host="redis",
        port=6379,
    )

    on_startup = startup
    on_shutdown = shutdown