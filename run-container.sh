#!/bin/sh
sudo docker run \
--mount type=bind,src="$(pwd)/dataset",dst=/usr/src/app/dataset \
--mount type=bind,src="$(pwd)/logs",dst=/usr/src/app/logs \
--mount type=bind,src="$(pwd)/analytics",dst=/usr/src/app/analytics \
--mount type=bind,src="$(pwd)/cache",dst=/usr/src/app/cache \
current-events-to-kg \
python -m main $*
