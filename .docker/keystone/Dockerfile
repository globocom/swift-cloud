FROM python:2.7-stretch

ENV VERSION=12.0.3

RUN set -x \
    && apt-get -y update \
    && apt-get install -y libffi-dev python-dev libssl-dev netcat default-libmysqlclient-dev \
    && apt-get -y clean all \
    %% pip install --upgrade pip setuptools pytz

RUN curl -fSL https://tarballs.openstack.org/keystone/keystone-${VERSION}.tar.gz -o keystone-${VERSION}.tar.gz \
    && tar xvf keystone-${VERSION}.tar.gz \
    && cd keystone-${VERSION} \
    && pip install -r requirements.txt \
    && PBR_VERSION=${VERSION} pip install . \
    && cp -r etc /etc/keystone \
    && cd - \
    && rm -rf keystone-${VERSION}*

COPY keystone.conf /etc/keystone/keystone.conf
COPY bootstrap_fn.sh /etc/bootstrap_fn.sh
COPY bootstrap.sh /etc/bootstrap.sh
COPY create_db.py /etc/create_db.py
COPY requirements.txt /etc/requirements.txt

RUN pip install -r /etc/requirements.txt \
    && pip install python-openstackclient==3.12.0

RUN chown root:root /etc/bootstrap.sh && chmod a+x /etc/bootstrap.sh

ENTRYPOINT ["/etc/bootstrap.sh"]

EXPOSE 5000 35357
