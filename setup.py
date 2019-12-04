#!/usr/bin/env python
"""Runs python setup/build/lint.
"""

import setuptools

setuptools.setup(
    install_requires=open('requirements.txt').readlines(),
)
