"""Simple package definition for using with `pip`."""

from setuptools import setup

description = """AndroidEnv
Read the README at https://github.com/deepmind/android_env for more information.
"""

setup(
    name='AndroidEnv',
    version='1.0.0',
    description='AndroidEnv environment and library for training agents.',
    long_description=description,
    author='DeepMind',
    license='Apache License, Version 2.0',
    keywords='Android OS',
    url='https://github.com/deepmind/android_env',
    packages=[
        'android_env',
        'android_env.components',
        'android_env.proto',
    ],
    install_requires=[
        'absl-py>=0.1.0',
        'dm_env',
        'mock',
        'numpy>=1.10',
        'portpicker>=1.2.0',
        'protobuf>=2.6',
        'pexpect',
        'pygame',
    ],
)
