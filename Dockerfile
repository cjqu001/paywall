FROM python:3.13.7-alpine

# OCI compliant labels
LABEL org.opencontainers.image.source="https://github.com/cjqu001/paywall"
LABEL org.opencontainers.image.url="https://github.com/cjqu001/paywall"
LABEL org.opencontainers.image.description="Self-hosted paywall bypass server"
LABEL org.opencontainers.image.documentation="https://github.com/cjqu001/paywall/blob/main/README.md"
LABEL org.opencontainers.image.licenses=MIT

COPY . .
RUN pip install -r requirements.txt
WORKDIR /app
EXPOSE 5000
ENTRYPOINT [ "python" ]
CMD [ "portable.py" ]
