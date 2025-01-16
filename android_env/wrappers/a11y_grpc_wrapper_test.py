# coding=utf-8
# Copyright 2024 DeepMind Technologies Limited.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for a11y_grpc_wrapper."""

import time
from unittest import mock

from absl.testing import absltest
from absl.testing import parameterized
from android_env import env_interface
from android_env.proto import adb_pb2
from android_env.proto.a11y import a11y_pb2
from android_env.proto.a11y import a11y_pb2_grpc
from android_env.proto.a11y import android_accessibility_forest_pb2
from android_env.wrappers import a11y_grpc_wrapper
import dm_env
import grpc
import numpy as np


def empty_forest() -> (
    android_accessibility_forest_pb2.AndroidAccessibilityForest
):
  return android_accessibility_forest_pb2.AndroidAccessibilityForest()


def one_empty_window_forest() -> (
    android_accessibility_forest_pb2.AndroidAccessibilityForest
):
  forest = android_accessibility_forest_pb2.AndroidAccessibilityForest()
  _ = forest.windows.add()
  return forest


def one_window_one_node_forest() -> (
    android_accessibility_forest_pb2.AndroidAccessibilityForest
):
  forest = android_accessibility_forest_pb2.AndroidAccessibilityForest()
  window = forest.windows.add()
  node = window.tree.nodes.add()
  node.class_name = 'foo'
  node.is_clickable = True
  node.hint_text = 'Foo hint'
  return forest


def one_window_two_nodes_forest() -> (
    android_accessibility_forest_pb2.AndroidAccessibilityForest
):
  forest = android_accessibility_forest_pb2.AndroidAccessibilityForest()
  window = forest.windows.add()
  node = window.tree.nodes.add()
  node.class_name = 'bar'
  node.is_clickable = True
  node.hint_text = 'Bar hint'
  node = window.tree.nodes.add()
  node.class_name = 'bar'
  node.is_clickable = False
  node.hint_text = 'Bar hint 2'
  return forest


def three_windows_forest() -> (
    android_accessibility_forest_pb2.AndroidAccessibilityForest
):
  forest = android_accessibility_forest_pb2.AndroidAccessibilityForest()
  _ = forest.windows.add()
  window = forest.windows.add()
  node = window.tree.nodes.add()
  node.class_name = 'foo'
  node.is_clickable = True
  node.hint_text = 'hint'
  window = forest.windows.add()
  node = window.tree.nodes.add()
  node.class_name = 'baz'
  node.is_clickable = True
  node.hint_text = 'hint'
  node = window.tree.nodes.add()
  node.class_name = 'foobar'
  node.is_clickable = False
  node.hint_text = 'hint'
  return forest


def empty_dict() -> dict[str, str]:
  return {}


def single_item_dict() -> dict[str, str]:
  return {'foo': 'bar'}


def several_long_items_dict() -> dict[str, str]:
  return {
      'first_key': 'Lorem ipsum ' * 100,
      'second_key': 'the beginning is the end is' * 100,
  }


def single_item_dict_with_special_chars() -> dict[str, str]:
  return {'foo': 'bar\r\t\nbaz'}


def _ok_response():
  return adb_pb2.AdbResponse(status=adb_pb2.AdbResponse.Status.OK)


class A11yGrpcWrapperTest(parameterized.TestCase):

  def test_server(self):
    base_env = mock.create_autospec(
        env_interface.AndroidEnvInterface, instance=True
    )
    base_env.task_extras.return_value = {}
    base_env.stats.return_value = {'relaunch_count': 0}
    base_env.execute_adb_call.return_value = _ok_response()
    wrapped_env = a11y_grpc_wrapper.A11yGrpcWrapper(base_env)
    wrapped_env.reset()
    channel_creds = grpc.local_channel_credentials()
    with grpc.secure_channel(
        f'[::]:{wrapped_env.get_port()}', channel_creds
    ) as channel:
      grpc.channel_ready_future(channel).result()
      stub = a11y_pb2_grpc.A11yServiceStub(channel)
      stub.SendForest(one_window_one_node_forest())
      stub.SendForest(one_window_two_nodes_forest())
      wrapped_env.step({})
      extras = wrapped_env.task_extras(latest_only=False)
      self.assertIn('accessibility_tree', extras)
      self.assertEqual(extras['accessibility_tree'].shape[0], 2)

  # tests of fetch_task_extras:
  # exception occurs (ensure attempt to enable networking) and recovers
  # exception occurs and enable networking doesn't help
  # exception occurs twice but with a forest sent between

  @parameterized.named_parameters(
      ('no_events_or_forests', [], []),
      (
          'no_events',
          [],
          [one_window_one_node_forest(), one_window_two_nodes_forest()],
      ),
      ('no_forests', [empty_dict(), single_item_dict()], []),
      (
          'events_and_forests',
          [empty_dict(), single_item_dict()],
          [one_window_one_node_forest(), one_window_two_nodes_forest()],
      ),
  )
  @mock.patch.object(time, 'sleep', autospec=True)
  @mock.patch.object(
      a11y_pb2_grpc, 'add_A11yServiceServicer_to_server', autospec=True
  )
  @mock.patch.object(grpc, 'server', autospec=True)
  def test_fetch_task_extras(
      self,
      received_events,
      received_forests,
      mock_server,
      mock_add_servicer,
      mock_sleep,
  ):
    del mock_server, mock_add_servicer, mock_sleep
    mock_context = mock.create_autospec(grpc.ServicerContext, instance=True)
    base_env = mock.create_autospec(
        env_interface.AndroidEnvInterface, instance=True
    )
    base_env.task_extras.return_value = {
        'foo': np.array(['bar', 'baz'], dtype='U'),
        'some_key': np.array(['some_value'], dtype='U'),
    }
    base_env.stats.return_value = {'relaunch_count': 0}
    base_env.execute_adb_call.return_value = _ok_response()
    wrapped_env = a11y_grpc_wrapper.A11yGrpcWrapper(base_env)
    wrapped_env.reset()
    for forest in received_forests:
      wrapped_env._servicer.SendForest(forest, mock_context)
    for event in received_events:
      wrapped_env._servicer.SendEvent(
          a11y_pb2.EventRequest(event=event), mock_context
      )
    with mock.patch.object(
        wrapped_env, 'attempt_enable_networking'
    ) as mock_attempt_enable_networking:
      extras = wrapped_env._fetch_task_extras()
      mock_attempt_enable_networking.assert_not_called()
    self.assertIn('foo', extras)
    np.testing.assert_array_equal(extras['foo'], ['bar', 'baz'])
    self.assertIn('some_key', extras)
    np.testing.assert_array_equal(extras['some_key'], ['some_value'])
    if received_events:
      self.assertIn('full_event', extras)
      self.assertLen(extras['full_event'], len(received_events))
      for i, event in enumerate(received_events):
        event = a11y_pb2.EventRequest(event=event)
        np.testing.assert_array_equal(extras['full_event'][i], event)
    else:
      self.assertNotIn('full_event', extras)
    if received_forests:
      self.assertIn('accessibility_tree', extras)
      self.assertLen(extras['accessibility_tree'], len(received_forests))
      for i, forest in enumerate(received_forests):
        np.testing.assert_array_equal(extras['accessibility_tree'][i], forest)
    else:
      self.assertNotIn('accessibility_tree', extras)

  @mock.patch.object(time, 'sleep', autospec=True)
  @mock.patch.object(
      a11y_pb2_grpc, 'add_A11yServiceServicer_to_server', autospec=True
  )
  @mock.patch.object(grpc, 'server', autospec=True)
  def test_fetch_task_extras_enable_networking(
      self,
      mock_server,
      mock_add_servicer,
      mock_sleep,
  ):
    del mock_server, mock_add_servicer, mock_sleep
    base_env = mock.create_autospec(
        env_interface.AndroidEnvInterface, instance=True
    )
    base_env.task_extras.return_value = {
        'foo': np.array(['bar'], dtype='U'),
        'some_key': np.array(['some_value'], dtype='U'),
        'exception': np.array(['fake exception'], dtype='U'),
    }
    base_env.stats.return_value = {'relaunch_count': 0}
    base_env.execute_adb_call.return_value = _ok_response()
    wrapped_env = a11y_grpc_wrapper.A11yGrpcWrapper(base_env)
    with mock.patch.object(
        wrapped_env, 'attempt_enable_networking'
    ) as mock_attempt_enable_networking:
      extras = wrapped_env._fetch_task_extras()
      self.assertNotIn('accessibility_tree', extras)
      self.assertNotIn('full_event', extras)
      future = wrapped_env._enabling_networking_future
      if future is not None:
        future.result()
      mock_attempt_enable_networking.assert_called_once()

  @mock.patch.object(time, 'sleep', autospec=True)
  @mock.patch.object(
      a11y_pb2_grpc, 'add_A11yServiceServicer_to_server', autospec=True
  )
  @mock.patch.object(grpc, 'server', autospec=True)
  def test_fetch_task_extras_enable_networking_twice(
      self,
      mock_server,
      mock_add_servicer,
      mock_sleep,
  ):
    del mock_server, mock_add_servicer, mock_sleep
    mock_context = mock.create_autospec(grpc.ServicerContext, instance=True)
    base_env = mock.create_autospec(
        env_interface.AndroidEnvInterface, instance=True
    )
    base_env.task_extras.return_value = {
        'foo': np.array(['bar'], dtype='U'),
        'some_key': np.array(['some_value'], dtype='U'),
    }

    base_env.stats.return_value = {'relaunch_count': 0}
    base_env.execute_adb_call.return_value = _ok_response()
    wrapped_env = a11y_grpc_wrapper.A11yGrpcWrapper(base_env)
    wrapped_env.reset()

    base_env.task_extras.return_value = {
        'foo': np.array(['bar'], dtype='U'),
        'some_key': np.array(['some_value'], dtype='U'),
        'exception': np.array(['fake exception'], dtype='U'),
    }
    with mock.patch.object(
        wrapped_env, 'attempt_enable_networking'
    ) as mock_attempt_enable_networking:
      extras = wrapped_env._fetch_task_extras()
      self.assertNotIn('accessibility_tree', extras)
      self.assertNotIn('full_event', extras)
      future = wrapped_env._enabling_networking_future
      if future is not None:
        future.result()
      mock_attempt_enable_networking.assert_called_once()
    # Fixed networking; send a forest so the wrapper knows it worked.
    wrapped_env._servicer.SendForest(one_window_one_node_forest(), mock_context)
    base_env.task_extras.return_value = {
        'foo': np.array(['bar'], dtype='U'),
        'some_key': np.array(['some_value'], dtype='U'),
    }
    extras = wrapped_env._fetch_task_extras()
    self.assertIn('accessibility_tree', extras)
    self.assertEqual(extras['accessibility_tree'].shape[0], 1)
    self.assertEqual(
        extras['accessibility_tree'][0], one_window_one_node_forest()
    )

    base_env.task_extras.return_value = {
        'foo': np.array(['bar'], dtype='U'),
        'some_key': np.array(['some_value'], dtype='U'),
        'exception': np.array(['fake exception'], dtype='U'),
    }
    with mock.patch.object(
        wrapped_env, 'attempt_enable_networking'
    ) as mock_attempt_enable_networking:
      extras = wrapped_env._fetch_task_extras()
      self.assertNotIn('accessibility_tree', extras)
      self.assertNotIn('full_event', extras)
      future = wrapped_env._enabling_networking_future
      if future is not None:
        future.result()
      mock_attempt_enable_networking.assert_called_once()

  @mock.patch.object(time, 'sleep', autospec=True)
  @mock.patch.object(
      a11y_pb2_grpc, 'add_A11yServiceServicer_to_server', autospec=True
  )
  @mock.patch.object(grpc, 'server', autospec=True)
  def test_task_extras_raises_a11y_info_exception(
      self, mock_sleep, mock_add_servicer, mock_server
  ):
    del mock_server, mock_add_servicer, mock_sleep
    base_env = mock.create_autospec(
        env_interface.AndroidEnvInterface, instance=True
    )
    base_env.task_extras.return_value = {
        'foo': np.array(['bar'], dtype='U'),
        'some_key': np.array(['some_value'], dtype='U'),
    }

    base_env.stats.return_value = {'relaunch_count': 0}
    base_env.execute_adb_call.return_value = _ok_response()
    base_env.reset.return_value = dm_env.restart(observation={'dummy': 42})
    base_env.step.return_value = dm_env.transition(
        observation={'dummy': 42}, reward=0.0
    )
    wrapped_env = a11y_grpc_wrapper.A11yGrpcWrapper(
        base_env,
        add_latest_a11y_info_to_obs=True,
        max_enable_networking_attempts=1,
    )
    wrapped_env.reset()

    base_env.task_extras.return_value = {
        'foo': np.array(['bar'], dtype='U'),
        'some_key': np.array(['some_value'], dtype='U'),
        'exception': np.array(['fake exception'], dtype='U'),
    }
    with mock.patch.object(
        wrapped_env, 'attempt_enable_networking'
    ) as mock_attempt_enable_networking:
      extras = wrapped_env._fetch_task_extras()
      self.assertNotIn('accessibility_tree', extras)
      self.assertNotIn('full_event', extras)
      # Wait for the the attempt to finish.
      future = wrapped_env._enabling_networking_future
      if future is not None:
        future.result()
      mock_attempt_enable_networking.assert_called_once()
    # The _fetch_task_extras() call inside the next step will force a restart
    self.assertRaises(
        a11y_grpc_wrapper.EnableNetworkingError, wrapped_env.step, {}
    )

  @mock.patch.object(
      a11y_pb2_grpc, 'add_A11yServiceServicer_to_server', autospec=True
  )
  @mock.patch.object(grpc, 'server', autospec=True)
  def test_configure_grpc(
      self,
      mock_server,
      mock_add_servicer,
  ):
    del mock_server, mock_add_servicer
    base_env = mock.create_autospec(
        env_interface.AndroidEnvInterface, instance=True
    )
    base_env.task_extras.return_value = {
        'foo': np.array(['bar'], dtype='U'),
        'some_key': np.array(['some_value'], dtype='U'),
    }

    base_env.stats.return_value = {'relaunch_count': 1}
    base_env.execute_adb_call.return_value = _ok_response()
    wrapped_env = a11y_grpc_wrapper.A11yGrpcWrapper(base_env)
    with mock.patch.object(
        wrapped_env, '_configure_grpc'
    ) as mock_configure_grpc:
      wrapped_env.reset()
      mock_configure_grpc.assert_called_once()

  @mock.patch.object(
      a11y_pb2_grpc, 'add_A11yServiceServicer_to_server', autospec=True
  )
  @mock.patch.object(grpc, 'server', autospec=True)
  def test_task_extras_raises_before_reset(
      self, unused_mock_server, unused_mock_add_servicer
  ):
    base_env = mock.create_autospec(
        env_interface.AndroidEnvInterface, instance=True
    )
    base_env.stats.return_value = {'relaunch_count': 0}
    base_env.execute_adb_call.return_value = _ok_response()
    wrapped_env = a11y_grpc_wrapper.A11yGrpcWrapper(base_env)
    with self.assertRaisesRegex(
        RuntimeError,
        r'You must call \.reset\(\) before calling \.task_extras\(\)',
    ):
      wrapped_env.task_extras(latest_only=False)

  @mock.patch.object(
      a11y_pb2_grpc, 'add_A11yServiceServicer_to_server', autospec=True
  )
  @mock.patch.object(grpc, 'server', autospec=True)
  def test_extras_accumulate_between_steps(
      self, mock_server, mock_add_servicer
  ):
    del mock_server, mock_add_servicer
    base_env = mock.create_autospec(
        env_interface.AndroidEnvInterface, instance=True
    )
    base_env.stats.return_value = {'relaunch_count': 0}
    base_env.execute_adb_call.return_value = _ok_response()
    base_env.reset.return_value = dm_env.restart(observation={'dummy': 42})
    base_env.step.return_value = dm_env.transition(
        observation={'dummy': 42}, reward=0.0
    )
    wrapped_env = a11y_grpc_wrapper.A11yGrpcWrapper(
        base_env, add_latest_a11y_info_to_obs=True
    )
    with mock.patch.object(wrapped_env, '_fetch_task_extras'):
      wrapped_env._fetch_task_extras.return_value = {
          'full_event': np.array(single_item_dict(), ndmin=1, dtype=object),
          'accessibility_tree': np.array(empty_forest(), ndmin=1, dtype=object),
      }
      timestep = wrapped_env.reset()
      self.assertIn('a11y_forest', timestep.observation)
      self.assertEqual(timestep.observation['a11y_forest'], empty_forest())
      wrapped_env._fetch_task_extras.return_value = {
          'full_event': np.array(empty_dict(), ndmin=1, dtype=object),
          'accessibility_tree': np.array(
              one_window_two_nodes_forest(), ndmin=1, dtype=object
          ),
      }
      timestep = wrapped_env.step({})
      self.assertIn('a11y_forest', timestep.observation)
      self.assertEqual(
          timestep.observation['a11y_forest'], one_window_two_nodes_forest()
      )
      timestep = wrapped_env.step({})
      self.assertIn('a11y_forest', timestep.observation)
      self.assertEqual(
          timestep.observation['a11y_forest'], one_window_two_nodes_forest()
      )
      wrapped_env._fetch_task_extras.return_value = {
          'full_event': np.array(single_item_dict(), ndmin=1, dtype=object),
      }
      timestep = wrapped_env.step({})
      self.assertIn('a11y_forest', timestep.observation)
      self.assertEqual(
          timestep.observation['a11y_forest'], one_window_two_nodes_forest()
      )
    expected_task_extras = {
        'full_event': np.array(
            [
                single_item_dict(),
                empty_dict(),
                empty_dict(),
                single_item_dict(),
            ],
            dtype=object,
        ),
        'accessibility_tree': np.array(
            [
                empty_forest(),
                one_window_two_nodes_forest(),
                one_window_two_nodes_forest(),
            ],
            dtype=object,
        ),
    }
    expected_task_extras_latest = {
        'full_event': np.array([single_item_dict()], dtype=object),
        'accessibility_tree': np.array(
            [one_window_two_nodes_forest()], dtype=object
        ),
    }
    task_extras = wrapped_env.task_extras(latest_only=False)
    np.testing.assert_equal(
        task_extras['full_event'], expected_task_extras['full_event']
    )
    np.testing.assert_equal(
        task_extras['accessibility_tree'],
        expected_task_extras['accessibility_tree'],
    )

    task_extras = wrapped_env.task_extras(latest_only=True)
    np.testing.assert_equal(
        task_extras['full_event'], expected_task_extras_latest['full_event']
    )
    np.testing.assert_equal(
        task_extras['accessibility_tree'],
        expected_task_extras_latest['accessibility_tree'],
    )

  @mock.patch.object(
      a11y_pb2_grpc, 'add_A11yServiceServicer_to_server', autospec=True
  )
  @mock.patch.object(grpc, 'server', autospec=True)
  def test_a11y_info_disabled(
      self,
      unused_mock_server,
      unused_mock_add_servicer,
  ):
    base_env = mock.create_autospec(
        env_interface.AndroidEnvInterface, instance=True
    )
    base_env.action_spec.return_value = {
        'action_type': dm_env.specs.Array(shape=(), dtype=np.int32)
    }
    base_env.stats.return_value = {'relaunch_count': 0}
    base_env.execute_adb_call.return_value = _ok_response()
    base_env.reset.return_value = dm_env.restart(observation={'dummy': 42})
    base_env.step.return_value = dm_env.transition(
        observation={'dummy': 42}, reward=0.0
    )
    wrapped_env = a11y_grpc_wrapper.A11yGrpcWrapper(
        base_env, add_latest_a11y_info_to_obs=False, a11y_info_timeout=1.0
    )
    with mock.patch.object(wrapped_env, '_fetch_task_extras'):
      wrapped_env._fetch_task_extras.return_value = {
          'accessibility_tree': np.array(empty_forest(), ndmin=1, dtype=object),
      }
      timestep = wrapped_env.reset()
      self.assertNotIn('a11y_forest', timestep.observation)
      timestep = wrapped_env.step({})
      self.assertNotIn('a11y_forest', timestep.observation)

  @mock.patch.object(
      a11y_pb2_grpc, 'add_A11yServiceServicer_to_server', autospec=True
  )
  @mock.patch.object(grpc, 'server', autospec=True)
  def test_a11y_info_with_timer_info_present(
      self,
      unused_mock_server,
      unused_mock_add_servicer,
  ):
    base_env = mock.create_autospec(
        env_interface.AndroidEnvInterface, instance=True
    )
    base_env.action_spec.return_value = {
        'action_type': dm_env.specs.Array(shape=(), dtype=np.int32)
    }
    base_env.stats.return_value = {'relaunch_count': 0}
    base_env.execute_adb_call.return_value = _ok_response()
    base_env.reset.return_value = dm_env.restart(observation={'dummy': 42})
    base_env.step.return_value = dm_env.transition(
        observation={'dummy': 42}, reward=0.0
    )
    wrapped_env = a11y_grpc_wrapper.A11yGrpcWrapper(
        base_env, add_latest_a11y_info_to_obs=True, a11y_info_timeout=1.0
    )
    with mock.patch.object(wrapped_env, '_fetch_task_extras'):
      wrapped_env._fetch_task_extras.side_effect = [{
          'accessibility_tree': np.array(empty_forest(), ndmin=1, dtype=object),
      }]
      timestep = wrapped_env.reset()
      self.assertIn('a11y_forest', timestep.observation)
      self.assertEqual(timestep.observation['a11y_forest'], empty_forest())

  @mock.patch.object(
      a11y_pb2_grpc, 'add_A11yServiceServicer_to_server', autospec=True
  )
  @mock.patch.object(grpc, 'server', autospec=True)
  @mock.patch.object(time, 'sleep', autospec=True)
  def test_a11y_info_with_timer_task_extra_returned(
      self, unused_mock_server, unused_mock_add_servicer, unused_mock_sleep
  ):
    base_env = mock.create_autospec(
        env_interface.AndroidEnvInterface, instance=True
    )
    base_env.action_spec.return_value = {
        'action_type': dm_env.specs.Array(shape=(), dtype=np.int32)
    }
    base_env.stats.return_value = {'relaunch_count': 0}
    base_env.execute_adb_call.return_value = _ok_response()
    base_env.reset.return_value = dm_env.restart(observation={'dummy': 42})
    base_env.step.return_value = dm_env.transition(
        observation={'dummy': 42}, reward=0.0
    )
    wrapped_env = a11y_grpc_wrapper.A11yGrpcWrapper(
        base_env, add_latest_a11y_info_to_obs=True, a11y_info_timeout=1.0
    )
    with mock.patch.object(wrapped_env, '_fetch_task_extras'):
      wrapped_env._fetch_task_extras.side_effect = [
          {
              'accessibility_tree': np.array(
                  empty_forest(), ndmin=1, dtype=object
              ),
          },
      ]
      timestep = wrapped_env.reset()
      self.assertIn('a11y_forest', timestep.observation)
      self.assertEqual(timestep.observation['a11y_forest'], empty_forest())

  @mock.patch.object(
      a11y_pb2_grpc, 'add_A11yServiceServicer_to_server', autospec=True
  )
  @mock.patch.object(grpc, 'server', autospec=True)
  @mock.patch.object(time, 'sleep', autospec=True)
  def test_a11y_info_with_timer_from_action(
      self, unused_mock_server, unused_mock_add_servicer, mock_sleep
  ):
    base_env = mock.create_autospec(
        env_interface.AndroidEnvInterface, instance=True
    )
    base_env.action_spec.return_value = {
        'action_type': dm_env.specs.Array(shape=(), dtype=np.int32)
    }
    base_env.stats.return_value = {'relaunch_count': 0}
    base_env.execute_adb_call.return_value = _ok_response()
    base_env.reset.return_value = dm_env.restart(observation={'dummy': 42})
    base_env.step.return_value = dm_env.transition(
        observation={'dummy': 42}, reward=0.0
    )
    wrapped_env = a11y_grpc_wrapper.A11yGrpcWrapper(
        base_env, add_latest_a11y_info_to_obs=True, a11y_info_timeout=0.0
    )
    with mock.patch.object(wrapped_env, '_fetch_task_extras'):
      wrapped_env._fetch_task_extras.side_effect = [
          {
              'accessibility_tree': np.array(
                  empty_forest(), ndmin=1, dtype=object
              ),
          },
      ]
      timestep = wrapped_env.step(action={'wait_time': 1.0})
      self.assertIn('a11y_forest', timestep.observation)
      mock_sleep.assert_called_once()
      self.assertEqual(timestep.observation['a11y_forest'], empty_forest())

  @mock.patch.object(
      a11y_pb2_grpc, 'add_A11yServiceServicer_to_server', autospec=True
  )
  @mock.patch.object(grpc, 'server', autospec=True)
  def test_task_extras_same_between_calls(self, mock_server, mock_add_servicer):
    del mock_server, mock_add_servicer
    base_env = mock.create_autospec(
        env_interface.AndroidEnvInterface, instance=True
    )
    base_env.stats.return_value = {'relaunch_count': 0}
    base_env.execute_adb_call.return_value = _ok_response()
    wrapped_env = a11y_grpc_wrapper.A11yGrpcWrapper(base_env)
    expected_task_extras = {
        'full_event': np.array(single_item_dict(), ndmin=1, dtype=object),
        'accessibility_tree': np.array(empty_forest(), ndmin=1, dtype=object),
    }
    with mock.patch.object(wrapped_env, '_fetch_task_extras'):
      wrapped_env._fetch_task_extras.return_value = expected_task_extras
      wrapped_env.reset()
    task_extras = wrapped_env.task_extras(latest_only=False)
    np.testing.assert_equal(
        task_extras['full_event'], expected_task_extras['full_event']
    )
    np.testing.assert_equal(
        task_extras['accessibility_tree'],
        expected_task_extras['accessibility_tree'],
    )

    task_extras = wrapped_env.task_extras(latest_only=False)
    np.testing.assert_equal(
        task_extras['full_event'], expected_task_extras['full_event']
    )
    np.testing.assert_equal(
        task_extras['accessibility_tree'],
        expected_task_extras['accessibility_tree'],
    )

    expected_task_extras = {
        'full_event': np.array(empty_dict(), ndmin=1, dtype=object),
        'accessibility_tree': np.array(
            one_window_two_nodes_forest(), ndmin=1, dtype=object
        ),
    }
    with mock.patch.object(wrapped_env, '_fetch_task_extras'):
      wrapped_env._fetch_task_extras.return_value = expected_task_extras
      wrapped_env.step({})
    task_extras = wrapped_env.task_extras(latest_only=False)
    np.testing.assert_equal(
        task_extras['full_event'], expected_task_extras['full_event']
    )
    np.testing.assert_equal(
        task_extras['accessibility_tree'],
        expected_task_extras['accessibility_tree'],
    )

    task_extras = wrapped_env.task_extras(latest_only=False)
    np.testing.assert_equal(
        task_extras['full_event'], expected_task_extras['full_event']
    )
    np.testing.assert_equal(
        task_extras['accessibility_tree'],
        expected_task_extras['accessibility_tree'],
    )

  @mock.patch.object(
      a11y_pb2_grpc, 'add_A11yServiceServicer_to_server', autospec=True
  )
  @mock.patch.object(grpc, 'server', autospec=True)
  def test_task_extras_clear_if_called_between_step(
      self, mock_server, mock_add_servicer
  ):
    del mock_server, mock_add_servicer
    base_env = mock.create_autospec(
        env_interface.AndroidEnvInterface, instance=True
    )
    base_env.stats.return_value = {'relaunch_count': 0}
    base_env.execute_adb_call.return_value = _ok_response()
    wrapped_env = a11y_grpc_wrapper.A11yGrpcWrapper(base_env)
    with mock.patch.object(wrapped_env, '_fetch_task_extras'):
      expected_task_extras = {
          'full_event': np.array(empty_dict(), ndmin=1, dtype=object),
          'accessibility_tree': np.array(empty_forest(), ndmin=1, dtype=object),
      }
      wrapped_env._fetch_task_extras.return_value = expected_task_extras
      wrapped_env.reset()
      task_extras = wrapped_env.task_extras(latest_only=False)
      np.testing.assert_equal(
          task_extras['full_event'], expected_task_extras['full_event']
      )
      np.testing.assert_equal(
          task_extras['accessibility_tree'],
          expected_task_extras['accessibility_tree'],
      )

      expected_task_extras = {
          'full_event': np.array(single_item_dict(), ndmin=1, dtype=object),
          'accessibility_tree': np.array(empty_forest(), ndmin=1, dtype=object),
      }
      wrapped_env._fetch_task_extras.return_value = expected_task_extras
      wrapped_env.step({})
      task_extras = wrapped_env.task_extras(latest_only=False)
      np.testing.assert_equal(
          task_extras['full_event'], expected_task_extras['full_event']
      )
      np.testing.assert_equal(
          task_extras['accessibility_tree'],
          expected_task_extras['accessibility_tree'],
      )
      expected_task_extras = {
          'full_event': np.array(empty_dict(), ndmin=1, dtype=object),
          'accessibility_tree': np.array(
              one_window_two_nodes_forest(), ndmin=1, dtype=object
          ),
      }
      wrapped_env._fetch_task_extras.return_value = expected_task_extras
      wrapped_env.step({})
      task_extras = wrapped_env.task_extras(latest_only=False)
      np.testing.assert_equal(
          task_extras['full_event'], expected_task_extras['full_event']
      )
      np.testing.assert_equal(
          task_extras['accessibility_tree'],
          expected_task_extras['accessibility_tree'],
      )

  @parameterized.named_parameters(
      ('none_true', False, False, False, 0),
      ('only_install', True, False, False, 1),
      ('only_start', False, True, False, 1),
      ('only_enable_a11y_tree', False, False, True, 1),
      ('install_and_start_no_a11y_tree', True, True, False, 2),
      ('install_and_a11y_tree', True, False, True, 2),
      ('start_and_a11y_tree', False, True, True, 2),
      ('all_true', True, True, True, 3),
  )
  @mock.patch.object(time, 'sleep', autospec=True)
  def test_apk_install_and_start(
      self,
      install_a11y_forwarding: bool,
      start_a11y_service: bool,
      enable_a11y_tree_logs: bool,
      expected_adb_calls: int,
      unused_mock_sleep,
  ):
    base_env = mock.create_autospec(
        env_interface.AndroidEnvInterface, instance=True
    )

    side_effects = []
    if install_a11y_forwarding:
      side_effects.append(_ok_response())  # install response
    if start_a11y_service:
      side_effects.append(_ok_response())  # start service response
    if enable_a11y_tree_logs:
      side_effects.append(_ok_response())  # enable_tree_request

    base_env.execute_adb_call.side_effect = side_effects

    _ = a11y_grpc_wrapper.A11yGrpcWrapper(
        base_env,
        install_a11y_forwarding=install_a11y_forwarding,
        start_a11y_service=start_a11y_service,
        enable_a11y_tree_info=enable_a11y_tree_logs,
    )
    self.assertEqual(base_env.execute_adb_call.call_count, expected_adb_calls)

  @mock.patch.object(time, 'sleep', autospec=True)
  def test_component_and_start(self, unused_mock_sleep):
    base_env = mock.create_autospec(
        env_interface.AndroidEnvInterface, instance=True
    )

    side_effects = []
    side_effects.append(_ok_response())  # install response
    side_effects.append(_ok_response())  # start service response
    side_effects.append(_ok_response())  # enable_tree_request

    base_env.execute_adb_call.side_effect = side_effects

    _ = a11y_grpc_wrapper.A11yGrpcWrapper(
        base_env,
        install_a11y_forwarding=True,
        start_a11y_service=True,
        enable_a11y_tree_info=True,
    )

    # call_args returns a tuple of which the first member is a tuple containing
    # the most recent args the mock was called with, and execute_adb_call only
    # has one arg (so [0][0] to access the AdbRequest).
    self.assertEqual(
        base_env.execute_adb_call.call_args[0][0].send_broadcast.component,
        'com.google.androidenv.accessibilityforwarder/com.google.androidenv.accessibilityforwarder.FlagsBroadcastReceiver',
    )


if __name__ == '__main__':
  absltest.main()
