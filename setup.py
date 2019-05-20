import setuptools


with open("README.rst", "r") as fh:
    long_description = fh.read()


setuptools.setup(
    name="buvar",
    version="0.3.0",
    author="Oliver Berger",
    author_email="diefans@gmail.com",
    description="General purpose config loader",
    long_description=long_description,
    long_description_content_type="text/x-rst",
    url="https://gitlab.com/diefans/buvar",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
    zip_safe=False,
    include_package_data=True,
    package_dir={'': 'src'},
    # https://setuptools.readthedocs.io/en/latest/setuptools.html#find-namespace-packages
    packages=setuptools.find_namespace_packages(where='src'),
    entry_points={
        'console_scripts': []
    },
    install_requires=[],
)
