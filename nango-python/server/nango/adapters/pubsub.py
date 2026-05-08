from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Protocol

from nango.contracts import PubsubEventEnvelope

SubscriberCallback = Callable[[PubsubEventEnvelope], Awaitable[None] | None]


class PubsubTransport(Protocol):
    async def connect(self) -> None: ...

    async def disconnect(self) -> None: ...

    async def publish(self, event: PubsubEventEnvelope) -> None: ...

    def subscribe(
        self, *, consumer_group: str, subject: str, callback: SubscriberCallback
    ) -> None: ...


class Publisher:
    def __init__(self, transport: PubsubTransport) -> None:
        self._transport = transport

    async def publish(self, event: PubsubEventEnvelope) -> None:
        await self._transport.publish(event)


class Subscriber:
    def __init__(self, transport: PubsubTransport) -> None:
        self._transport = transport

    def subscribe(self, *, consumer_group: str, subject: str, callback: SubscriberCallback) -> None:
        self._transport.subscribe(
            consumer_group=consumer_group,
            subject=subject,
            callback=callback,
        )


class NoopPubsubTransport:
    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None

    async def publish(self, event: PubsubEventEnvelope) -> None:
        return None

    def subscribe(self, *, consumer_group: str, subject: str, callback: SubscriberCallback) -> None:
        return None


class InMemoryPubsubTransport:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[SubscriberCallback]] = defaultdict(list)
        self._lock = asyncio.Lock()
        self._connected = False

    async def connect(self) -> None:
        async with self._lock:
            self._connected = True

    async def disconnect(self) -> None:
        async with self._lock:
            self._connected = False
            self._subscribers.clear()

    async def publish(self, event: PubsubEventEnvelope) -> None:
        async with self._lock:
            if not self._connected:
                raise RuntimeError("pubsub transport is not connected")
            callbacks = list(self._subscribers.get(event.subject, ()))

        for callback in callbacks:
            result = callback(event)
            if result is not None:
                await result

    def subscribe(self, *, consumer_group: str, subject: str, callback: SubscriberCallback) -> None:
        if not self._connected:
            raise RuntimeError("pubsub transport is not connected")
        self._subscribers[subject].append(callback)


class RedisPubsubTransport:
    async def connect(self) -> None:
        raise NotImplementedError("Redis pubsub transport is not implemented yet")

    async def disconnect(self) -> None:
        raise NotImplementedError("Redis pubsub transport is not implemented yet")

    async def publish(self, event: PubsubEventEnvelope) -> None:
        raise NotImplementedError("Redis pubsub transport is not implemented yet")

    def subscribe(self, *, consumer_group: str, subject: str, callback: SubscriberCallback) -> None:
        raise NotImplementedError("Redis pubsub transport is not implemented yet")
