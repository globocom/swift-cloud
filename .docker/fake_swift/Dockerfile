FROM python:2.7-stretch

RUN apt-get update \
    && apt-get install -y build-essential libssl-dev liberasurecode-dev inotify-tools \
    && apt-get install -y git telnet curl vim \
    && python -m pip install pip --upgrade

WORKDIR /home/app

COPY . .

RUN pip install -r requirements.txt
