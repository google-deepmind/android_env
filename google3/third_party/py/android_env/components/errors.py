# Lint as: python3
"""Definitions of exceptions used by AndroidEnv."""


class ReadObservationError(Exception):
  """When the environment is unable to obtain an observation from a simulator."""
  pass


class ObservationDecodingError(ReadObservationError):
  """When the environment is unable to decode the observation from a simulator."""
  pass


class PipeTimedOutError(ReadObservationError):
  """When the environment waited for too long for part of an observation."""
  pass


class RemoteControllerError(Exception):
  """Error raised by the RemoteController."""


class RemoteControllerInitError(RemoteControllerError):
  pass


class TooManyRestartsError(RemoteControllerError):
  """The number of restarts has exceeded _MAX_RESTART_TRIES."""
  pass


class NotAllowedError(Exception):
  """When the player does something that outside of the task scope."""
  pass


class PlayerExitedActivityError(NotAllowedError):
  """When the player quits the current Android activity."""
  pass


class PlayerExitedViewHierarchyError(NotAllowedError):
  """When the player quits the current Android app screen."""
  pass


class SDCardWriteError(Exception):
  """Raised when an error occurred when writing to the SD card."""
  pass


class AdbControllerError(Exception):
  """Errors that can be raised by ADBController."""
  pass


class AdbControllerShellInitError(AdbControllerError):
  """Raised when an error occurred when initializing ADB shell."""
  pass


class AdbControllerPexpectError(AdbControllerError):
  """Raise when a problem with pexpect communication occurs."""
  pass


class AdbControllerDeviceTimeoutError(AdbControllerError):
  """Raised when a device takes too long to respond."""
  pass


class AdbControllerConnectionError(AdbControllerError):
  """Error connecting to tcpip address."""
  pass


class SimulatorCrashError(Exception):
  """Raised when an AndroidSimulator crashed."""
  pass


class ConsoleConnectionError(Exception):
  """Raised when cannot connect to the emulator console."""
  pass


class SendActionError(Exception):
  """Raised when action couldn't be sent successfully."""
  pass


class StepCommandError(Exception):
  """Raised when setup step interpreter cannot process a command."""
  pass


class AdbCallError(StepCommandError):
  """Raised when the execution of an ADB call has failed."""
  pass


class WaitForAppScreenError(StepCommandError):
  """Raised when the wait_for_app_screen success check is not met."""
  pass


class CheckInstallError(StepCommandError):
  """Raised when the check_install success check is not met."""
  pass


class WaitForMessageError(StepCommandError):
  """Raised when the wait_for_message success check is not met."""
  pass
