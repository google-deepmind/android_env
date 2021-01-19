"""Prepares and launches vanadium."""

import json
import os
import signal
import threading
import time

from absl import flags
from absl import logging
from android_env.components import errors
from android_env.components import gce_pseudo_metadataserver
from pexpect.popen_spawn import PopenSpawn
import portpicker

from google3.pyglib import gfile
from google3.pyglib import resources
from google3.quality.malware.vm import vanadium_lib

FLAGS = flags.FLAGS

_MAX_SSH_TUNNEL_TRIES = 6
_SSH_TUNNEL_RETRY_SLEEP_SEC = 20
RESOURCE_DIR = 'google3/third_party/py/andorid_env/components/resources'


class VanadiumLauncher():
  """Handles launching vanadium."""

  def __init__(
      self,
      image_path,
      local_tmp_dir,
      ssh_port,
      metadata_attrs='',
      adb_local_port: int = 55555,
      vnc_local_port: int = 6444,
      run_headless: bool = False,
      startup_wait_time_sec: float = 30,
      num_cpus: int = 4,
      kvm_device: str = '/dev/kvm',
  ):
    self._image = image_path
    self._metadata_attrs = metadata_attrs
    self._metadata_server_port = portpicker.pick_unused_port()
    self._vmm_port = portpicker.pick_unused_port()
    self._ssh_port = ssh_port
    self._local_tmp_dir = local_tmp_dir
    self._adb_local_port = adb_local_port
    self._vnc_local_port = vnc_local_port
    self._vm = None
    self._metadata_server_thread = None
    self._ssh_tun_proc = None
    self._run_headless = run_headless
    self._startup_wait_time_sec = startup_wait_time_sec
    self._num_cpus = num_cpus
    self._kvm_device = kvm_device
    self._local_private_key_file = None
    self._boot_msg = 'GceBootReporter: VIRTUAL_DEVICE_BOOT_COMPLETED'

  def launch(self):
    """Launch VMM and metadata server."""
    vanadium_config = vanadium_lib.VanadiumConfig(
        vmm_mac_address='00:23:45:67:89:01',
        # This specific address required by DHCP responder.
        guest_mac_address='42:01:0a:00:02:0f',
        num_cpus=self._num_cpus,
        enable_graphics=False)
    vanadium_config.path_to_image_file = self._image
    vanadium_config.guest_memory_file = os.path.join(self._local_tmp_dir,
                                                     'guest_memory_file')
    vanadium_config.snapshot = None
    vanadium_config.mem_size = 7680
    vanadium_config.cpuid = None
    vanadium_config.hostnet = True
    vanadium_config.vmm_port = self._vmm_port

    logging.info('Launching Metadata Server.')
    # Metadata Server
    metadata_path = self._metadata_attrs
    if metadata_path:
      metadata = json.load(metadata_path)
    else:
      metadata = resources.GetResource(
          os.path.join(RESOURCE_DIR,
                       'gce_x86_metadata-320x480.json')).decode('utf-8')
    public_key = resources.GetResource(
        os.path.join(RESOURCE_DIR, 'cloud_android_local.pub')).decode('utf-8')
    logging.info('metadata: %r', metadata)
    logging.info('public_key: %r', public_key)
    if self._metadata_server_thread is None:
      self._mds = gce_pseudo_metadataserver.MetadataServer(
          metadata, public_key, ('::1', self._metadata_server_port),
          gce_pseudo_metadataserver.MetadataRequestHandler)
      self._metadata_server_thread = threading.Thread(
          name='MetadataServer', target=self._mds.serve_forever)
      self._metadata_server_thread.daemon = True
      self._metadata_server_thread.start()
      logging.info('Launching Metadata Server Done.')

    vanadium_config.net_forwards.append(
        ('169.254.169.254', '255.255.255.255', '80', '::1',
         self._metadata_server_port))
    # For logging.
    vanadium_config.tcp_sink_address = '::1'
    vanadium_config.tcp_sink_port = 9  # discard

    # SSH inbound
    vanadium_config.local_tcp_redirs.append((self._ssh_port, '10.0.2.15', 22))

    logging.info('Launching VMM.')
    FLAGS.kvm_device = self._kvm_device
    self._vm = vanadium_lib.VanadiumVm(
        self._image, qemu_config=vanadium_config, new_vmm=True)
    self._vm.Start()
    self._wait_for_boot()
    self._open_ssh_tunnel()

  def _open_ssh_tunnel(self):
    """Set up SSH tunnel."""
    logging.info('Opening SSH tunnel.')
    private_key = resources.GetResource(
        os.path.join(RESOURCE_DIR, 'cloud_android_local'))
    self._local_private_key_file = os.path.join(self._local_tmp_dir,
                                                'cloud_android_local')

    # Creating a tmp private key file. We need to set the permissions as only
    # readable/writeable for the user, otherwise SSH will not accept the file.
    # Clearing the default user mask (0o022) which makes files readable by all.
    os.umask(0)
    with open(
        os.open(self._local_private_key_file, os.O_CREAT | os.O_WRONLY, 0o600),
        'wb') as f:
      f.write(private_key)

    # Port forwarding for ADB.
    tunnels = ['-L' + str(self._adb_local_port) + ':[::1]:5555']
    if not self._run_headless:
      # Port forwarding for VNC.
      tunnels.extend(['-L' + str(self._vnc_local_port) + ':[::1]:6444'])
    ssh_tun_cmd = [
        'ssh', 'localhost', '-p', str(self._ssh_port)
    ] + tunnels + [
        '-o', 'UserKnownHostsFile=/dev/null', '-o', 'StrictHostKeyChecking=no',
        '-i', self._local_private_key_file
    ]
    logging.info(' '.join(ssh_tun_cmd))
    ssh_tun_logfile = os.path.join(self._local_tmp_dir, 'ssh_tun_output')
    self._ssh_tun_output = gfile.Open(ssh_tun_logfile, 'w')

    num_tries = 0
    while num_tries < _MAX_SSH_TUNNEL_TRIES:

      num_tries += 1

      self._ssh_tun_proc = PopenSpawn(
          ssh_tun_cmd, logfile=self._ssh_tun_output, env=os.environ.copy())
      return_code = self._ssh_tun_proc.proc.poll()
      if return_code is None:
        logging.info('SSH Tunnel is running. self._ssh_tun_proc.pid = %s',
                     self._ssh_tun_proc.pid)
        return
      else:
        logging.warning('Could not establish SSH tunnel. Try %d of %d.',
                        num_tries, _MAX_SSH_TUNNEL_TRIES)
        logging.warning('Return code: %r', return_code)
        time.sleep(_SSH_TUNNEL_RETRY_SLEEP_SEC)

    raise errors.SimulatorCrashError('Could not establish SSH tunnel.')

  def get_vm(self):
    return self._vm

  def close(self):
    """Clean up threads, processes, files and servers."""
    if self._ssh_tun_proc is not None:
      self._ssh_tun_proc.kill(signal.SIGKILL)
      self._ssh_tun_output.close()
      self._ssh_tun_output = None
    if self._vm is not None:
      self._vm.Stop()
      self._vm = None
    if self._local_private_key_file is not None:
      os.remove(self._local_private_key_file)

  def _wait_for_boot(self):
    """Listens to updates to logging.info for the boot completed message."""
    # This is the default when running on Borg.
    cpp_logging = logging.is_using_cpp_logging()

    if cpp_logging:
      # cpp_logging ignores start_logging_to_file, so we use python.
      logging.info('Switching to python logging.')
      logging.use_python_logging()

    # Since we intercept the logs, we want to dump them back in the default
    # stream once we are done.
    log_cache = []

    def restore_cpp_logging():
      if cpp_logging:
        logging.use_cpp_logging()
        if log_cache:
          logging.info('Forwarding captured logs:')
          for log in log_cache:
            logging.info(log)
        logging.info('Restored cpp logging.')

    handler = logging.get_absl_handler()
    handler.flush()
    handler.start_logging_to_file()
    filename = logging.get_log_file_name()

    start_time = time.time()
    if filename:
      with open(filename, 'r') as logs:
        logs.seek(0, 2)  # Start from the end of the log file
        while time.time() - start_time < self._startup_wait_time_sec:
          where = logs.tell()
          line = logs.readline()
          if not line:
            # There was no new line. Wait a bit then flush and try again.
            time.sleep(1)
            handler.flush()
            logs.seek(where)
          elif self._boot_msg in line:
            if cpp_logging:
              log_cache.append(line)
            restore_cpp_logging()
            logging.info('Boot completed')
            return
          elif cpp_logging:
            log_cache.append(line)
      restore_cpp_logging()
      logging.error(
          'Timed out waiting for boot message. We will assume the VM is ready.')
    else:
      restore_cpp_logging()
      logging.error('Unable to watch VM logs. Falling back to a fixed sleep.')
      logging.info('Sleeping for %r secs.', self._startup_wait_time_sec)
      time.sleep(self._startup_wait_time_sec)
