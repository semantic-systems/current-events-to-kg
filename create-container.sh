#!/bin/sh

# build 
sudo docker build -t current-events-to-kg .

# create mount sources for container
mkdir -p ./dataset
mkdir -p ./logs
mkdir -p ./analytics
mkdir -p ./cache
