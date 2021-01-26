"""Definitions of exceptions used by AndroidEnv."""


class ReadObservationError(Exception):
  """When the environment is unable to obtain an observation from a simulator."""


class ObservationDecodingError(ReadObservationError):
  """When the environment is unable to decode the observation from a simulator."""


class PipeTimedOutError(ReadObservationError):
  """When the environment waited for too long for part of an observation."""


class RemoteControllerError(Exception):
  """Error raised by the RemoteController."""


class RemoteControllerInitError(RemoteControllerError):
  """Raised when RemoteController was not initialized correctly."""


class TooManyRestartsError(RemoteControllerError):
  """The number of restarts has exceeded _MAX_RESTART_TRIES."""


class NotAllowedError(Exception):
  """When the player does something that outside of the task scope."""


class PlayerExitedActivityError(NotAllowedError):
  """When the player quits the current Android activity."""


class PlayerExitedViewHierarchyError(NotAllowedError):
  """When the player quits the current Android app screen."""


class SDCardWriteError(Exception):
  """Raised when an error occurred when writing to the SD card."""


class AdbControllerError(Exception):
  """Errors that can be raised by ADBController."""


class AdbControllerShellInitError(AdbControllerError):
  """Raised when an error occurred when initializing ADB shell."""


class AdbControllerPexpectError(AdbControllerError):
  """Raise when a problem with pexpect communication occurs."""


class AdbControllerDeviceTimeoutError(AdbControllerError):
  """Raised when a device takes too long to respond."""


class AdbControllerConnectionError(AdbControllerError):
  """Error connecting to tcpip address."""


class SimulatorCrashError(Exception):
  """Raised when an AndroidSimulator crashed."""


class ConsoleConnectionError(Exception):
  """Raised when cannot connect to the emulator console."""


class SendActionError(Exception):
  """Raised when action couldn't be sent successfully."""


class StepCommandError(Exception):
  """Raised when setup step interpreter cannot process a command."""


class AdbCallError(StepCommandError):
  """Raised when the execution of an ADB call has failed."""


class WaitForAppScreenError(StepCommandError):
  """Raised when the wait_for_app_screen success check is not met."""


class CheckInstallError(StepCommandError):
  """Raised when the check_install success check is not met."""


class WaitForMessageError(StepCommandError):
  """Raised when the wait_for_message success check is not met."""
