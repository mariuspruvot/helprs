"""Docker transport for runner containers.

The Protocol is the seam tests plug into: a hand-written double implements it
without pulling in the Docker SDK.
"""

import base64
from collections.abc import AsyncIterator
from typing import Protocol

CLAUDE_RUNNER_IMAGE = "claude-runner:latest"

CONTAINER_MEMORY_BYTES = 512 * 1024 * 1024
CONTAINER_NANO_CPUS = 1_000_000_000
# Generous for a git clone plus a node process, tight enough that a runaway
# fork loop hits the cap instead of the host's process table.
CONTAINER_PIDS_LIMIT = 512

# The entrypoint reads newline-terminated commands from this FIFO.
_INPUT_FIFO = "/tmp/claude-input"


class DockerClient(Protocol):
    """What the container module needs from a Docker daemon."""

    async def create_container(
        self,
        image: str,
        environment: dict[str, str],
        volumes: list[str],
        labels: dict[str, str],
    ) -> str:
        """Create a container with stdin enabled and return its id."""
        ...

    async def start_container(self, container_id: str) -> None: ...

    async def stop_container(self, container_id: str) -> None: ...

    async def remove_container(self, container_id: str, force: bool = False) -> None: ...

    # Not ``async def``: this returns an async iterator, it is not a coroutine
    # that resolves to one. Declaring it ``async`` made every implementation
    # fail the Protocol and would deadlock a double written to match it.
    def container_logs(self, container_id: str, follow: bool = False) -> AsyncIterator[str]:
        """Stream the container's stdout, line chunks as they arrive."""
        ...

    async def write_to_container(self, container_id: str, data: str) -> None:
        """Write one message to the container's input FIFO."""
        ...

    async def wait_container(self, container_id: str) -> int:
        """Block until the container exits; return its exit code."""
        ...

    async def close(self) -> None: ...


class AioDockerClient:
    """Production client wrapping aiodocker."""

    def __init__(self) -> None:
        import aiodocker

        self._docker = aiodocker.Docker()

    async def create_container(
        self,
        image: str,
        environment: dict[str, str],
        volumes: list[str],
        labels: dict[str, str],
    ) -> str:
        container = await self._docker.containers.create(
            {
                "Image": image,
                "Env": [f"{k}={v}" for k, v in environment.items()],
                "Labels": labels,
                "OpenStdin": True,
                # This is the one container in the system that executes
                # untrusted input: `claude --dangerously-skip-permissions`
                # against PR content written by whoever opened the PR. Memory
                # and CPU alone do not bound that -- a fork bomb exhausts PIDs
                # long before it exhausts a 512 MB cap.
                "HostConfig": {
                    "Binds": volumes,
                    "Memory": CONTAINER_MEMORY_BYTES,
                    "NanoCPUs": CONTAINER_NANO_CPUS,
                    "NetworkMode": "bridge",
                    "PidsLimit": CONTAINER_PIDS_LIMIT,
                    "CapDrop": ["ALL"],
                    "SecurityOpt": ["no-new-privileges"],
                },
            }
        )
        return container.id

    async def start_container(self, container_id: str) -> None:
        container = await self._docker.containers.get(container_id)
        await container.start()

    async def stop_container(self, container_id: str) -> None:
        container = await self._docker.containers.get(container_id)
        await container.stop()

    async def remove_container(self, container_id: str, force: bool = False) -> None:
        container = await self._docker.containers.get(container_id)
        await container.delete(force=force)

    async def container_logs(self, container_id: str, follow: bool = False) -> AsyncIterator[str]:
        """Yield the container's stdout.

        stdout only: Claude Code writes stream-json there, while stderr
        carries diagnostics that would duplicate events. aiodocker returns a
        list when not following and an async iterator when following, so the
        two cases are spelled out rather than passed a dynamic flag.
        """
        container = await self._docker.containers.get(container_id)
        if follow:
            async for line in container.log(stdout=True, stderr=False, follow=True):
                yield line
            return
        for line in await container.log(stdout=True, stderr=False, follow=False):
            yield line

    async def write_to_container(self, container_id: str, data: str) -> None:
        """Deliver one message to the entrypoint's read loop.

        The payload is base64-encoded so no shell metacharacter in user text
        can be interpreted, and newline-terminated so ``read`` returns it as a
        complete line.
        """
        container = await self._docker.containers.get(container_id)
        encoded = base64.b64encode((data + "\n").encode()).decode()
        exec_obj = await container.exec(cmd=["sh", "-c", f"echo {encoded} | base64 -d > {_INPUT_FIFO}"])
        await exec_obj.start(detach=True)

    async def wait_container(self, container_id: str) -> int:
        container = await self._docker.containers.get(container_id)
        result = await container.wait()
        return result["StatusCode"]

    async def close(self) -> None:
        await self._docker.close()
