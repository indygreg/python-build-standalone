{% include 'base.Dockerfile' %}
RUN apt-get install \
    file \
    libc6-dev \
    make \
    perl \
    tar \
    xz-utils \
    unzip
