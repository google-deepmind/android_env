# coding=utf-8
# Copyright 2026 DeepMind Technologies Limited.
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

"""FastMCP server binary entrypoint for AndroidEnv."""

from collections.abc import Sequence
from absl import app
from android_env.mcp import android_mcp_tools
import mcp.server.fastmcp


def main(argv: Sequence[str]) -> None:
  if len(argv) > 1:
    raise app.UsageError("Too many command-line arguments.")

  tools = android_mcp_tools.AndroidMcpTools()
  fastmcp_server = mcp.server.fastmcp.FastMCP("AndroidEnv")
  tools.register_tools(fastmcp_server)
  fastmcp_server.run()


if __name__ == "__main__":
  app.run(main)
