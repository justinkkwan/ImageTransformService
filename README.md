# ImageTransformService

ImageTransformService can be run as a script or a service. It accepts image files and and uses OpenCV to create a trace/outline of the image.

## Instructions

### Prerequisites

* Install Docker (https://www.docker.com/get-started/)
* Create docker image

    ```
    docker build -t <image-name> .
    ```

or

* Install Python3 (https://www.python.org/downloads/)
* Install pip (https://pip.pypa.io/en/stable/installation/)
* Install dependencies:
    * Create a virtual environment (venv):

        ```
        python3 -m venv .venv
        ```
    * Install dependencies to venv

        ```
        # use venv
        source .venv/bin/activate

        # install dependencies listed
        python3 -m pip install -r requirements-build.txt
        python3 -m pip install -r requirements-runtime.txt

        # if you are making changes to the project you may wish to 
        # install opencv-python with gui support
        python3 -m pip install opencv-python
        ```

* Generate gRPC code

    ```
    python3 -m grpc_tools.protoc -Igenerated=proto --python_out=. --pyi_out=. --grpc_python_out=. proto/image_transform.proto
    ```

## Usage (Python)

For one-off use:

```
python3 main.py --file <file-name>
```

To start the gRPC server (on port 50051)

```
python3 main.py --serve
```

# Usage (Docker)

To start the gRPC server (on port 50051)

```
docker run -p 50051:50051 <image-name>
```

For subsequent runs, if you didn't prune the container, you can use:

```
# find the container name
docker ps -a

# start the container again
docker start <container-name>
```