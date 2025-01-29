#!/bin/bash


if [ "$CI" ]; then
    export POETRY_VIRTUALENVS_OPTIONS_NO_PIP=true
    export POETRY_VIRTUALENVS_OPTIONS_NO_SETUPTOOLS=true
    poetry sync --no-cache
else
    poetry sync
fi
