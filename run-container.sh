#!/bin/sh
sudo docker run \
--mount type=bind,src="$(pwd)/currenteventstokg/dataset",dst=/usr/src/app/currenteventstokg/dataset \
--mount type=bind,src="$(pwd)/currenteventstokg/logs",dst=/usr/src/app/currenteventstokg/logs \
--mount type=bind,src="$(pwd)/currenteventstokg/analytics",dst=/usr/src/app/currenteventstokg/analytics \
--mount type=bind,src="$(pwd)/currenteventstokg/cache",dst=/usr/src/app/currenteventstokg/cache \
current-events-to-kg \
python -m currenteventstokg $*
