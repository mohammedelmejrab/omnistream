"""Scoped provider usage accounting and resource sampling for the live harness."""

import asyncio
import contextvars
import subprocess
import threading
from collections import defaultdict

stage = contextvars.ContextVar("eval_stage", default="setup")


class UsageMeter:
    def __init__(self):
        self.lock = threading.Lock()
        self.values = defaultdict(
            lambda: {"tokens": 0, "cost_usd": 0.0, "calls": 0, "cost_reported_calls": 0}
        )

    def record(self, response):
        usage = getattr(response, "usage", None)
        if not usage:
            return
        with self.lock:
            value = self.values[stage.get()]
            value["calls"] += 1
            value["tokens"] += getattr(usage, "total_tokens", 0) or 0
            cost = (getattr(usage, "model_extra", None) or {}).get("cost")
            if cost is not None:
                value["cost_usd"] += float(cost)
                value["cost_reported_calls"] += 1

    def __enter__(self):
        from openai.resources.chat.completions import AsyncCompletions, Completions

        self.sync, self.async_ = Completions.create, AsyncCompletions.create
        meter = self

        def sync(client, *args, **kwargs):
            result = meter.sync(client, *args, **kwargs)
            meter.record(result)
            return result

        async def async_(client, *args, **kwargs):
            result = await meter.async_(client, *args, **kwargs)
            meter.record(result)
            return result

        Completions.create, AsyncCompletions.create = sync, async_
        return self

    def __exit__(self, *args):
        from openai.resources.chat.completions import AsyncCompletions, Completions

        Completions.create, AsyncCompletions.create = self.sync, self.async_

    def summary(self):
        return {
            k: {
                **v,
                "cost_usd": v["cost_usd"]
                if v["calls"] and v["calls"] == v["cost_reported_calls"]
                else None,
            }
            for k, v in self.values.items()
        }


class MemorySampler:
    def __init__(self):
        self.app_peak = 0
        self.container_peak = 0
        self.peak = 0
        self.errors = []

    async def sample(self):
        import psutil

        app = psutil.Process().memory_info().rss
        self.app_peak = max(self.app_peak, app)

        def docker():
            result = subprocess.run(
                [
                    "docker",
                    "stats",
                    "omnistream-neo4j",
                    "--no-stream",
                    "--format",
                    "{{json .}}",
                ],
                capture_output=True,
                check=False,
                text=True,
                timeout=15,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode:
                raise RuntimeError("docker stats failed")
            import json
            import re

            text = json.loads(result.stdout)["MemUsage"].split("/")[0].strip()
            number, unit = re.match(r"([\d.]+)\s*(\w+)", text).groups()
            return (
                float(number)
                * {
                    "B": 1,
                    "KiB": 1024,
                    "MiB": 1024**2,
                    "GiB": 1024**3,
                    "kB": 1000,
                    "MB": 1000**2,
                    "GB": 1000**3,
                }[unit]
            )

        try:
            container = await asyncio.to_thread(docker)
            self.container_peak = max(self.container_peak, container)
            self.peak = max(self.peak, app + container)
        except Exception as exc:  # noqa: BLE001 - retain missing measurement instead of aborting evaluation
            if str(exc) not in self.errors:
                self.errors.append(str(exc))

    async def run(self):
        while True:
            await self.sample()
            await asyncio.sleep(5)

    def summary(self):
        return {
            "application_peak_rss_bytes": self.app_peak,
            "neo4j_peak_bytes": self.container_peak or None,
            "peak_memory_bytes": self.peak if not self.errors else None,
            "memory_sampling_errors": self.errors,
        }
