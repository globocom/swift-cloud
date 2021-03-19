FROM python:2.7-stretch

RUN apt-get update \
    && apt-get install -y build-essential libssl-dev python3-dev python3-pip \
    && apt-get install -y inotify-tools git telnet curl vim \
    && python -m pip install pip --upgrade

WORKDIR /home/app

COPY . .

RUN pip install -r requirements.txt
