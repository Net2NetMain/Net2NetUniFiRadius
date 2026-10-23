FROM net2net-unifi-radius:local
RUN apt-get update && apt-get install -y --no-install-recommends eapoltest && rm -rf /var/lib/apt/lists/*
COPY tests/smoke_radius.py /tests/smoke_radius.py
ENV EAPOL_TEST=/usr/bin/eapol_test
ENTRYPOINT ["python", "/tests/smoke_radius.py"]
