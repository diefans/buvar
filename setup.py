# -*- coding: utf-8 -*-
from setuptools import setup
from build import build

# from distutils.core import setup

package_dir = {"": "src"}

packages = ["buvar", "buvar.di"]

package_data = {"": ["*"], "buvar": ["plugins/*"]}

install_requires = [
    "attrs>=19.1,<20.0",
    "cattrs>=0.9,<1.0",
    "multidict>=4.5,<5.0",
    "orjson>=2.0,<3.0",
    "structlog>=19.1,<20.0",
    "toml>=0.10,<0.11",
    "tomlkit>=0.5.3,<0.6.0",
]

entry_points = {"console_scripts": ["buvar = buvar.cli:main"]}

setup_kwargs = {
    "name": "buvar",
    "version": "0.11.0",
    "description": "General purpose config loader",
    "long_description": None,
    "author": "Oliver Berger",
    "author_email": "diefans@gmail.com",
    "url": None,
    "package_dir": package_dir,
    "packages": packages,
    "package_data": package_data,
    "install_requires": install_requires,
    "entry_points": entry_points,
    "python_requires": ">=3.6,<4.0",
}

build(setup_kwargs)

setup(**setup_kwargs)
