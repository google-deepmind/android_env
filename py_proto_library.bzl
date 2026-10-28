"""Pure Python Proto generation macro using prebuilt wheel binaries.

RATIONALE & PERFORMANCE CONSIDERATIONS:
----------------------------------------
This macro invokes `protoc_runner` (which wraps `grpc_tools.protoc` from
`@pip//grpcio_tools`) via a lightweight Bazel `genrule` instead of compiling
protobuf `protoc` C++ source dependencies on cold checkouts.

By using the hermetic `//:protoc_runner` tool (`@pip//grpcio_tools`), proto
code generation completes in under 1 second without compiling any C++ code.
"""

load("@rules_python//python:defs.bzl", "py_library")

def _dedup(seq):
    seen = {}
    return [x for x in seq if not (x in seen or seen.update({x: 1}))]

def py_proto_library(name, srcs, proto_srcs = [], deps = [], visibility = ["//visibility:public"]):
    """Generates _pb2.py message files for srcs using hermetic protoc_runner.

    Avoids compiling C++ protobuf source dependencies to keep cold build times fast.

    Args:
      name: Target name for the generated py_library.
      srcs: List of primary .proto files to generate _pb2.py for.
      proto_srcs: Additional .proto files needed in the Bazel sandbox for imports.
      deps: Additional Python library dependencies.
      visibility: Visibility specifier for the generated py_library.
    """
    outs = [s[:-6] + "_pb2.py" if s.endswith(".proto") else s + "_pb2.py" for s in srcs]
    pkg_parts = native.package_name().split("/")
    depth = "../" * len(pkg_parts)
    root_import = "/".join([".."] * len(pkg_parts))
    gen_name = name + "_gen"

    all_srcs = _dedup(srcs + proto_srcs)

    native.genrule(
        name = gen_name,
        srcs = all_srcs,
        outs = outs,
        cmd = "$(location //:protoc_runner) -I. --python_out=$(RULEDIR)/" + depth + " " + " ".join(["$(location " + s + ")" for s in srcs]),
        tools = ["//:protoc_runner"],
    )

    py_library(
        name = name,
        srcs = [":" + gen_name],
        imports = [root_import, "."],
        deps = ["@pip//protobuf"] + deps,
        visibility = visibility,
    )
