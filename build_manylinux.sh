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
    BIN=/opt/python/${PYTHON_VERSION}/bin
    PIP=${BIN}/pip
    PYTHON=${BIN}/python

    ${PIP} wheel -w ./wheelhouse cython pip
    ${PIP} install -U cython pip -f ./wheelhouse
    ${PYTHON} setup.py bdist_wheel -d wheels

    auditwheel repair ./wheels/${PROJECT}*${PYTHON_VERSION}*.whl --plat ${PLATFORM} -w ./dist

	${PIP} install ./dist/${PROJECT}*${PYTHON_VERSION}*.whl
    ${PIP} install ${PROJECT}[tests] -f ./dist -f ./wheelhouse
    ${BIN}/pytest tests
done
