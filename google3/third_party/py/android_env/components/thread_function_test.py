"""Tests for android_env.components.thread_function."""

from android_env.components import thread_function
from google3.testing.pybase import googletest


class ThreadFunctionTest(googletest.TestCase):

  def test_hello_world(self):

    class HelloFunction(thread_function.ThreadFunction):

      def main(self):
        v = self._read_value()
        if v:
          self._write_value('hello')
        else:
          self._write_value('world')

    hello_fn = HelloFunction(block_input=True, block_output=True, name='Hello')
    hello_fn.write(True, block=True)
    self.assertEqual(hello_fn.read(block=True), 'hello')
    hello_fn.write(False, block=True)
    self.assertEqual(hello_fn.read(block=True), 'world')
    hello_fn.kill()  # Not strictly necessary, but it's good hygiene.

  def test_class_with_state(self):
    """Derived class with internal state to change the thread output."""

    class HaveState(thread_function.ThreadFunction):

      def __init__(self, value, *args, **kwargs):
        self._value = value
        super().__init__(*args, **kwargs)

      def main(self):
        v = self._read_value()
        if v:
          self._write_value(v + self._value)

    have_state_fn = HaveState(
        value=123, block_input=True, block_output=True, name='HaveState')
    have_state_fn.write(3, block=True)
    self.assertEqual(have_state_fn.read(block=True), 126)
    have_state_fn.write(9, block=True)
    self.assertEqual(have_state_fn.read(block=True), 132)
    have_state_fn.kill()


if __name__ == '__main__':
  googletest.main()
