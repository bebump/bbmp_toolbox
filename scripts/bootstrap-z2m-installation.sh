#!/bin/sh
set -e
curl -fLO "https://raw.githubusercontent.com/bebump/bbmp_toolbox/main/scripts/pzg-install-z2m" && \
chmod +x pzg-install-z2m && \
./pzg-install-z2m
