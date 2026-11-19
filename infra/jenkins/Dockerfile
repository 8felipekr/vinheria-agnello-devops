FROM jenkins/jenkins:lts-jdk21

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    python3-cryptography \
    python3-jwt \
    python3-flask \
    python3-requests \
    curl \
    jq \
    dnsutils \
    && rm -rf /var/lib/apt/lists/*

RUN git config --system --add safe.directory '*'

USER jenkins

ENV JAVA_OPTS="-Djenkins.install.runSetupWizard=false -Dhudson.plugins.git.GitSCM.ALLOW_LOCAL_CHECKOUT=true"

RUN jenkins-plugin-cli --plugins \
    workflow-aggregator \
    git

COPY --chown=jenkins:jenkins init.groovy.d/ /usr/share/jenkins/ref/init.groovy.d/
