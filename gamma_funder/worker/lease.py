"""One fencing lease per exact H; shared Redis already used by the gateway.

Registered fixed Lua scripts never accept caller-provided Lua source. Hotkeys
are validated SS58 identities separate from this lock's random ownership token.
"""

from __future__ import annotations

import asyncio
import contextlib
import secrets
import time

RENEW_SCRIPT = "if redis.call('GET',KEYS[1])==ARGV[1] then return redis.call('EXPIRE',KEYS[1],60) else return 0 end"
RELEASE_SCRIPT = "if redis.call('GET',KEYS[1])==ARGV[1] then return redis.call('DEL',KEYS[1]) else return 0 end"


class RedisHotkeyLease:
    def __init__(self, redis, worker_id: str):
        if redis is None or not worker_id:
            raise ValueError(
                "explicit Redis transport and stable worker instance id required"
            )
        self.redis, self.worker_id = redis, worker_id
        self.tokens, self.owned = {}, {}
        self._renew = self.redis.register_script(RENEW_SCRIPT)
        self._release = self.redis.register_script(RELEASE_SCRIPT)

    async def acquire(self, hotkey: str) -> bool:
        token = secrets.token_urlsafe(32)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            acquired = await self.redis.set(
                self._key(hotkey), token, nx=True, ex=60
            )
            if acquired is True:
                self.tokens[hotkey] = token
                self.owned[hotkey] = asyncio.create_task(
                    self.keep_lease(hotkey, token)
                )
                return True
            await asyncio.sleep(0.2)
        return False

    async def keep_lease(self, hotkey: str, token: str):
        try:
            while True:
                await asyncio.sleep(20)
                if (
                    await self._renew(keys=[self._key(hotkey)], args=[token])
                    != 1
                ):
                    raise RuntimeError("worker lost reconciliation fencing")
        except asyncio.CancelledError:
            return

    def _key(self, hotkey: str) -> str:
        return "kubetee:gamma:reconciler-lease:v1:" + hotkey

    async def release(self, hotkey: str):
        task = self.owned.pop(hotkey, None)
        if task is not None:
            task.cancel()
            # Expected cancellation belongs to this release, not its caller.
            # Any other renewal failure still interrupts the accounting cycle.
            with contextlib.suppress(asyncio.CancelledError):
                await task
        token = self.tokens.pop(hotkey, None)
        if token:
            await self._release(keys=[self._key(hotkey)], args=[token])
