import itertools

from setuptools import dist, find_packages, setup
from setuptools.command.install import install

from build import build


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


with open("README.rst") as f:
    description = f.read()


install_requires = [
    "attrs>=19.1,<20.0",
    "cattrs>=1.0,<2.0",
    "multidict>=4.5,<5.0",
    "structlog>=20.1.0",
    "toml>=0.10,<0.11",
    "tomlkit>=0.5.3,<0.6.0",
    "typing_inspect>=0.4.0<0.5",
    "aiofile<2",
    "cached_property<2",
]
extras_require = {
    "tests": [
        "pytest>=4.6",
        "pytest-cov>=^2.7,<3.0",
        "pytest-asyncio>=0.11.0",
        "pytest-benchmark>=3.2.2<4.0",
        "mock>=3.0<4.0",
        "pytest-mock>=1.10<2.0",
        "pytest-watch>=4.2<5.0",
        "pytest-randomly>=3.1<4.0",
        "pytest-doctestplus>=0.5<1.0",
        "pytest-anything",
        "pdbpp",
    ],
}
extras_require["all"] = list(itertools.chain(extras_require.values()))


entry_points = {"pytest11": ["buvar = buvar.testing"]}

setup_kwargs = {
    "name": "buvar",
    "version": "0.40.0",
    "description": "Asyncio plugins, components, dependency injection and configs",
    "long_description": description,
    "long_description_content_type": "text/x-rst",
    "author": "Oliver Berger",
    "author_email": "diefans@gmail.com",
    "url": "https://gitlab.com/diefans/buvar",
    "package_dir": {"": "src"},
    "packages": find_packages("src"),
    "include_package_data": True,
    # "package_data": {"": ["*"]},
    "install_requires": install_requires,
    "extras_require": extras_require,
    "entry_points": entry_points,
    "python_requires": ">=3.7,<4.0",
    "classifiers": [
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Framework :: AsyncIO",
        "License :: OSI Approved :: Apache Software License",
        "License :: OSI Approved :: MIT License",
    ],
    "cmdclass": {"install": InstallPlatlib},
    "distclass": BinaryDistribution,
}
build(setup_kwargs)

setup(**setup_kwargs)
