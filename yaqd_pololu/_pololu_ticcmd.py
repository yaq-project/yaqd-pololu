__all__ = ["PololuTicCMD"]

import subprocess
import yaml  # type: ignore
import asyncio

from yaqd_core import IsDaemon, HasPosition, HasLimits, HasTransformedPosition


class PololuTicCMD(HasTransformedPosition, HasLimits, HasPosition, IsDaemon):
    _kind = "pololu-ticcmd"

    def __init__(self, name, config, config_filepath):
        super().__init__(name, config, config_filepath)
        self.cmd = ["ticcmd"]
        self.cmd += [] if config["serial"] is None else ["-d", config["serial"]]

    def ticcmd(self, *args):
        try:
            out = subprocess.run(self.cmd + list(args), capture_output=True, check=True)
        except subprocess.CalledProcessError as e:
            self.logger.info(args)
            self.logger.error(e)
            return
        return out.stdout

    async def update_state(self):
        """Continually monitor and update the current daemon state."""
        self._state["hw_limits"] = [-2147483648, 2147483647]
        while True:
            status = self._get_status()
            self._state["position"] = int(status["Current position"])
            self._state["destination"] = int(status["Acting target position"])
            while self._state["position"] != self._state["destination"]:
                await asyncio.sleep(0.2)
                status = self._get_status()
                self._state["position"] = int(status["Current position"])
                self._state["destination"] = int(status["Acting target position"])
            self._busy = self.moving = False
            await self._busy_sig.wait()

    def _relative_to_transformed(self, relative_position):
        # steps to units
        return relative_position / self._config["steps_per_unit"]

    def _transformed_to_relative(self, transformed_position):
        # units to steps
        return transformed_position * self._config["steps_per_unit"]

    def _set_position(self, position):
        self.ticcmd("--resume")
        self.ticcmd("--exit-safe-start", "-p", str(int(position)))
        self.moving = True
        self._loop.create_task(self._keep_moving())

    async def _keep_moving(self):
        while self.moving:
            self.ticcmd("--reset-command-timeout")
            await asyncio.sleep(0.9)

    def _get_status(self):
        return yaml.safe_load(self.ticcmd("-s", "--full"))

    def get_status(self) -> str:
        return yaml.dump(self._get_status())
