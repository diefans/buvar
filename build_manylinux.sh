#!/bin/bash
set -e -x

# defaults
: ${PLATFORM:=manylinux1_x86_64}
: ${PROJECT:=buvar}
: ${PYTHON_VERSIONS:=$(cat <<EOF
cp37-cp37m
cp36-cp36m
EOF
)}


# create wheels
for PYTHON_VERSION in ${PYTHON_VERSIONS}; do
    PIP=/opt/python/${PYTHON_VERSION}/bin/pip
    ${PIP} install cython
    ${PIP} wheel /io[tests] -w /io/wheelhouse/
done

# repair wheels
for WHL in /io/wheelhouse/*.whl; do
    auditwheel repair "${WHL}" --plat ${PLATFORM} -w /io/wheelhouse/
done

# install and test
for PYTHON_VERSION in ${PYTHON_VERSIONS}; do
    BIN=/opt/python/${PYTHON_VERSION}/bin
    "${BIN}/pip" install ${PROJECT}[tests] --no-index -f /io/wheelhouse
    (cd /io/; ${BIN}/pytest tests)
done
