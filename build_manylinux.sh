#!/bin/bash
set -e -x

# defaults
: ${PLATFORM:=manylinux1_x86_64}
: ${PROJECT:=buvar}
: ${PYTHON_VERSIONS:=$(cat <<EOF
cp37-cp37m
cp38-cp38
EOF
)}


# create wheels
for PYTHON_VERSION in ${PYTHON_VERSIONS}; do
    PIP=/opt/python/${PYTHON_VERSION}/bin/pip
    ${PIP} install cython
    ${PIP} wheel .[tests] -w ./wheelhouse/
done

# repair wheels
for WHL in ./wheelhouse/${PROJECT}-*.whl; do
    auditwheel repair "${WHL}" --plat ${PLATFORM} -w ./wheelhouse/
done

# install and test
for PYTHON_VERSION in ${PYTHON_VERSIONS}; do
    BIN=/opt/python/${PYTHON_VERSION}/bin
    "${BIN}/pip" install ${PROJECT}[tests] --no-index -f ./wheelhouse
    ${BIN}/pytest tests
done
