# Build and run with:
#
# docker build -t pq-bench . && docker run -it --privileged -v $(pwd)/kex/data:/pq-bench/kex/data pq-bench
#
# This will run the server in your current shell. Open another shell and run the experiment with:
#
# docker exec $(docker ps --filter ancestor=pq-bench -q) python3 experiment.py

FROM public.ecr.aws/ubuntu/ubuntu:22.04_stable

# If running this outside of Docker, run the below apt commands in your ubuntu
# VM's shell before running install-prereqs-ubuntu.sh
RUN apt update -y
RUN apt install -y \
               git \
               autoconf \
               automake \
               build-essential \
               cmake \
               curl \
               golang-go \
               iputils-ping \
               libtool \
               libpcre3-dev \
               ninja-build \
               python3 \
               python3-pip \
               sudo

RUN mkdir /analyzer
COPY . /analyzer
WORKDIR /analyzer

RUN python3 -m pip install -r requirements.txt
