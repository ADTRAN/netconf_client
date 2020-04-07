#!/usr/bin/python

import os
from setuptools import setup, find_packages

package = "netconf_client"
setup_dir = os.path.dirname(os.path.abspath(__file__))
version_file = os.path.join(setup_dir, package, "VERSION")

with open(version_file) as version_file:
    version = version_file.read().strip()

requirements = open(os.path.join(setup_dir, "requirements.txt")).read().splitlines()
required = [line for line in requirements if not line.startswith("-")]

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name=package,
    version=version,
    description="A Python NETCONF client",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/ADTRAN/netconf_client",
    author="ADTRAN, Inc.",
    packages=find_packages(),
    install_requires=[required],
    include_package_data=True,
    keywords="netconf",
    classifiers=(
        "Development Status :: 5 - Production/Stable",
        "Operating System :: OS Independent",
        "Intended Audience :: Telecommunications Industry",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
    ),
)
