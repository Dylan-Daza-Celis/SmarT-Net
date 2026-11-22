import random
import time
from .config import AgentError
from .tailer import Tailer
from .transport import Retry


class Agent:
    def __init__(self, store, transport, emit=lambda **item: None):
        self.store, self.transport, self.emit = store, transport, emit
        self.tailer = Tailer(store)
        self.last_observation = None

    def step(self):
        if self.store.get('blocked'): raise AgentError('checkpoint_blocked')
        batch = self.tailer.poll()
        if batch is None:
            if self.tailer.observation != self.last_observation and self.tailer.observation:
                self.emit(code=self.tailer.observation); self.last_observation = self.tailer.observation
            return self.store.config.poll_seconds
        delay = batch['next_attempt']-time.time()
        if delay > 0: return delay
        self.store.attempt(batch)
        if hasattr(self.transport, 'on_event'):
            def transport_event(code):
                with self.store.db: self.store.note(code, batch['id'])
                self.emit(code=code, batch_id=batch['id'])
            self.transport.on_event = transport_event
        try:
            report = self.transport.send(batch)
        except Retry as exc:
            # Persist the deadline so a process restart cannot bypass Retry-After.
            exponential = min(60, 2**min(batch['attempts'], 6))
            delay = max(exc.delay or 0, min(60, exponential+random.SystemRandom().uniform(0, exponential*.2)))
            self.store.retry(batch, exc.code, delay)
            self.emit(code=exc.code, batch_id=batch['id'], retry_seconds=round(delay, 3))
            return delay
        except AgentError as exc:
            self.store.block(exc.code, batch['id'])
        self.store.accept(batch, report, self.transport.actor_id)
        self.emit(code='accepted', batch_id=batch['id'], imported=report['imported'],
                  duplicates=report['duplicates'], discarded=report['discarded'])
        return 0
