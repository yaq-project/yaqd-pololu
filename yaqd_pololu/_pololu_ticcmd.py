__all__ = ["PololuTicCMD"]

import subprocess
import yaml  # type: ignore
import asyncio

from yaqd_core import IsDaemon, HasPosition, IsHomeable, HasLimits, HasTransformedPosition


class PololuTicCMD(HasTransformedPosition, HasLimits, IsHomeable, HasPosition, IsDaemon):
    _kind = "pololu-ticcmd"

    def __init__(self, name, config, config_filepath):
        super().__init__(name, config, config_filepath)
        self.cmd = ["ticcmd"]
        if config["serial"]:
            self.cmd += ["-d", config["serial"]]

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
                self.ticcmd("--reset-command-timeout")
                status = self._get_status()
                self._state["position"] = int(status["Current position"])
                self._state["destination"] = int(status["Acting target position"])
            self._busy = False
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

    def home(self):
        if (not self._config["is_homeable"]):
            msg = "this daemon is not configured for homing"
            self.logger.error(msg)
            raise NotImplementedError(msg)
        try:
            return_to = self.get_destination()
            self._state["destination"] = 0
            self._busy = True
            asyncio.get_running_loop().create_task(self._home(return_to))
        except Exception as e:
            self.logger.error(e, stack_info=True)

    async def _home(self, return_to):
        self.ticcmd("--exit-safe-start")
        self.ticcmd("--home", self._config["home_dir"])
        await self._not_busy_sig.wait()
        self.set_position(return_to)

    def _get_status(self):
        return yaml.safe_load(self.ticcmd("-s", "--full"))

    def get_status(self) -> str:
        return yaml.dump(self._get_status())

    def close(self):
        self.ticcmd("deenergize")

