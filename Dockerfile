FROM python:3-slim AS build-stage

WORKDIR /build/
COPY . ./
RUN pip install --no-cache -r requirements-build.txt && \
    python -m grpc_tools.protoc -Igenerated=proto --python_out=. --pyi_out=. --grpc_python_out=. proto/image_transform.proto


FROM python:3-slim AS runtime

WORKDIR /app

COPY . ./
COPY --from=build-stage /build/generated generated/
RUN pip install --no-cache -r requirements-runtime.txt
EXPOSE 50051

CMD ["python", "main.py", "--serve"]
