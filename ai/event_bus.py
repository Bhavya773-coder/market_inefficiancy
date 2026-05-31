import redis
import time


class EventBus:

    def __init__(self):
        self.r = redis.Redis(
            host="localhost",
            port=6379,
            decode_responses=True
        )

    def publish(self, stream, data: dict):
        self._ensure_redis()
        return self.r.xadd(stream, data)

    def read(self, stream, group, consumer):
        self._ensure_redis()
        self.create_group(stream, group)

        try:
            return self.r.xreadgroup(
                groupname=group,
                consumername=consumer,
                streams={stream: ">"},
                count=10,
                block=1000
            )

        except redis.exceptions.ResponseError as e:
            if "NOGROUP" in str(e):
                self.create_group(stream, group)
                return []

            raise e

    def create_group(self, stream, group):
        self._ensure_redis()

        try:
            self.r.xgroup_create(
                stream,
                group,
                id="0",
                mkstream=True
            )

        except redis.exceptions.ResponseError as e:
            if "BUSYGROUP" in str(e):
                pass
            else:
                raise e

    def _ensure_redis(self):
        try:
            self.r.ping()

        except redis.exceptions.ConnectionError:
            print("Redis not reachable. Retrying...")
            time.sleep(1)
            self.r.ping()
