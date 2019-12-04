# -*- coding: utf-8 -*-
from setuptools import dist, find_packages, setup
from setuptools.command.install import install

from build import build

# from distutils.core import setup


try:
    from wheel.bdist_wheel import bdist_wheel as _bdist_wheel

    class bdist_wheel(_bdist_wheel):
        def finalize_options(self):
            _bdist_wheel.finalize_options(self)
            # Mark us as not a pure python package
            self.root_is_pure = False

        # def get_tag(self):
        #     python, abi, plat = _bdist_wheel.get_tag(self)
        #     # We don't contain any python source
        #     python, abi = "py2.py3", "none"
        #     return python, abi, plat


except ImportError:
    bdist_wheel = None


class BinaryDistribution(dist.Distribution):
    def is_pure(self):
        return False

    def has_ext_modules(self):
        return True


class InstallPlatlib(install):
    def finalize_options(self):
        install.finalize_options(self)
        if self.distribution.has_ext_modules():
            self.install_lib = self.install_platlib


install_requires = [
    "attrs>=19.1,<20.0",
    "cattrs>=0.9,<1.0",
    "multidict>=4.5,<5.0",
    "structlog>=19.1,<20.0",
    "toml>=0.10,<0.11",
    "tomlkit>=0.5.3,<0.6.0",
    "typing_inspect>=0.4.0<0.5",
]

entry_points = {"console_scripts": ["buvar = buvar.cli:main"]}

setup_kwargs = {
    "name": "buvar",
    "version": "0.20.2",
    "description": "Asyncio plugins, components, dependency injection and configs",
    "long_description": None,
    "author": "Oliver Berger",
    "author_email": "diefans@gmail.com",
    "url": None,
    "package_dir": {"": "src"},
    "packages": find_packages("src"),
    # "package_data": {"": ["*"]},
    "install_requires": install_requires,
    "extras_require": {
        "tests": [
            "pytest>=4.6,<5.0",
            "pytest-cov>=^2.7,<3.0",
            "pytest-asyncio>=0.10.0,<0.11",
            "pytest-benchmark>=3.2.2<4.0",
            "mock>=3.0<4.0",
            "pytest-mock>=1.10<2.0",
            "pytest-watch>=4.2<5.0",
            "pytest-randomly>=3.1<4.0",
            "pdbpp",
        ],
        "orjson": ["orjson>=2.0,<3.0"],
        "all": ["aiohttp"],
    },
    "entry_points": entry_points,
    "python_requires": ">=3.6,<4.0",
    "cmdclass": {"install": InstallPlatlib, "bdist_wheel": bdist_wheel},
    "distclass": BinaryDistribution,
}
build(setup_kwargs)

setup(**setup_kwargs)
