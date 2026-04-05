#!/bin/bash

SELF_DIR="$(cd "$(dirname "$0")"; pwd)"

cat << HERE_DOCUMENT_MARK
In order to test the scripts first add their containing directory to your path:

export PATH="\$PATH:/$SELF_DIR/scripts"
HERE_DOCUMENT_MARK
