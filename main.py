from concurrent import futures

import math
import cv2
import numpy
import grpc
from io import BytesIO
import pillow_heif

import generated.image_transform_pb2_grpc
from generated.image_transform_pb2 import ImageBytes
from generated.image_transform_pb2_grpc import ImageTransformServiceServicer


class ImageTransformService(ImageTransformServiceServicer):
    def traceImage(self, request, context):
        input_image_bytes = request.image
        output_image_bytes = create_trace_image(input_image_bytes)

        return ImageBytes(image=output_image_bytes)

def create_trace_image(original_image: bytes) -> bytes:
    cv_img = cv2.imdecode(numpy.frombuffer(original_image, numpy.uint8), cv2.IMREAD_COLOR)

    if cv_img is None and original_image[4:8] == b"ftyp": #HEIC/HEIF files
        heif_img = pillow_heif.open_heif(BytesIO(original_image), convert_hdr_to_8bit=False, bgr_mode=True)
        cv_img = numpy.asarray(heif_img)

    #Greyscale
    cv_img = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)

    #Blur away small artifacts
    cv_img = cv2.GaussianBlur(cv_img, (3, 3), 0)

    #Option1: Canny (Create outline - white on black)
    #cv_img = cv2.Canny(cv_img, threshold1=50, threshold2=150)

    #Tidy up
    #cv_img = cv2.morphologyEx(cv_img, cv2.MORPH_CLOSE, numpy.ones((5, 5), numpy.uint8))

    #Invert to black on white
    #cv_img = cv2.bitwise_not(cv_img)

    #Option2: Decides if a pixel should be black based on difference compared to local weighted mean
    shortest_side = min(*cv_img.shape)
    block_size = math.trunc(shortest_side / 150)
    block_size = max(3, block_size if block_size % 2 == 1 else block_size + 1) #adhere to algorithm requirements
    cv_img = cv2.adaptiveThreshold(cv_img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block_size, 2)

    #Manually perform naive removal of artifacts
    remove_blotches(cv_img)

    _, png_array = cv2.imencode(".png", cv_img)

    return numpy.array(png_array).tobytes()

def remove_blotches(image: numpy.ndarray):
    """
    Modifies the given image, removing blotches.

    :param image: a numpy.ndarray representing a cv2 image.
    :type image: numpy.ndarray
    """

    num_rows, num_cols = image.shape

    max_blotch_size = num_rows * num_cols * 0.00003

    visited = numpy.ndarray(shape=image.shape, dtype=bool)
    visited.fill(False)

    for row_index, row in enumerate(image):
        for col_index, pixel in enumerate(row):
            if pixel == 0 and not visited[row_index, col_index]:
                size, stretches = calculate_blotch((row_index, col_index), image, visited)

                if size < max_blotch_size:
                    for row, start, stop in stretches:
                        image[row, start:stop+1] = 255

def calculate_blotch(staring_point: tuple, image: numpy.ndarray, visited:numpy.ndarray) -> (int, list[tuple]):
    starting_row, starting_col = staring_point
    num_rows, num_cols = image.shape
    last_row = num_rows - 1
    last_col = num_cols - 1

    first_stretch = calculate_stretch(staring_point, image)
    stretch_start, stretch_end = first_stretch

    stretches = [(starting_row, stretch_start, stretch_end)]
    total_size = stretch_end - stretch_start

    visited[starting_row, stretch_start:stretch_end+1] = True

    remainingWork = []

    if starting_row > 0:
        remainingWork.append((starting_row - 1, stretch_start, stretch_end))
    if starting_row < last_row:
        remainingWork.append((starting_row + 1, stretch_start, stretch_end))

    while len(remainingWork) > 0:
        # check where to search next
        area = remainingWork.pop()
        row, search_start, search_end = area

        # calculate the intersecting stretches
        col = search_start
        while col <= search_end:
            if image[row, col] == 0 and not visited[row, col]:
                start, end = calculate_stretch((row, col), image)

                stretches.append((row, start, end))
                total_size += end - start
                visited[row, start:end+1] = True

                # add the segments of the rows directly above and below the current segment to the search space
                if row > 0:
                    remainingWork.append((row - 1, start, end))
                if row < last_row:
                    remainingWork.append((row + 1, start, end))

                col = end + 1
            else:
                col += 1

    return total_size, stretches

def calculate_stretch(point: tuple, image: numpy.ndarray) -> tuple[int, int]:
    """
    Calculates the stretch of black pixels around a given point.
    :param point: Point/pixel to calculate around
    :param image: Image where the point/pixel lives
    :return: Left-most and right-most columns reached from the point/pixel via black pixels.
    """
    row, col = point
    image_row = image[row]

    start = col
    end = col

    while start > 0 and image_row[start - 1] == 0:
        start -= 1

    cutoff = image.shape[1] - 1
    while end < cutoff and image_row[end + 1] == 0:
        end += 1

    return start, end

def calculate_blotch_recursive(point: tuple, image: numpy.ndarray, visited: numpy.ndarray) -> (int, list[tuple]):
    row, col = point
    num_rows, num_cols = image.shape

    if image[point] != 0 or visited[point]:
        return 0, []

    #find the connected stretch/span of pixels in the row
    left_most = col
    right_most = col

    while left_most >= 0 and image[row, left_most] == 0:
        left_most -= 1

    while right_most < num_cols and image[row, right_most] == 0:
        right_most += 1

    left_most += 1
    right_most -= 1

    visited[row, left_most:right_most+1] = True

    stretch_length = right_most - left_most + 1

    blotch_size = stretch_length
    stretches = [(row, left_most, right_most)]

    #search below, then above for more pixels
    for index in range(left_most, right_most + 1):
        if row < num_rows - 1:
            sub_blotch_size, sub_stretches = calculate_blotch_recursive((row + 1, index), image, visited)
            if sub_blotch_size > 0:
                blotch_size += sub_blotch_size
                stretches.extend(sub_stretches)

        if row > 0:
            sub_blotch_size, sub_stretches = calculate_blotch_recursive((row - 1, index), image, visited)
            if sub_blotch_size > 0:
                blotch_size += sub_blotch_size
                stretches.extend(sub_stretches)

    return blotch_size, stretches

SERVER_PORT = 50051

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8), options=[("grpc.max_receive_message_length", 1024*1024*32), ("grpc.max_send_message_length", 1024*1024*32)])
    generated.image_transform_pb2_grpc.add_ImageTransformServiceServicer_to_server(
        ImageTransformService(),
        server
    )
    server.add_insecure_port(f"[::]:{SERVER_PORT}")
    server.start()
    server.wait_for_termination()


def find_file(search_term: str, matcher) -> str | None:
    import os
    search_term = search_term.lower()

    for root, dirs, files in os.walk("."):
        img_files = [file for file in files if file.lower().endswith(".png") or file.lower().endswith(".jpg") or file.lower().endswith(".webp") or file.lower().endswith(".heic")]

        for img_file in img_files:
            if matcher(img_file.lower(), search_term):
                return os.path.join(root, img_file)

    return None


if __name__ == '__main__':
    import argparse

    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument(
        "-f",
        "--file",
        metavar="fileName",
        required=False,
        help="Provide a file name with --file."
    )
    arg_parser.add_argument(
        "--serve",
        action="store_true",
        help=f"Run as gRPC server accepting requests on port {SERVER_PORT}."
    )
    args = arg_parser.parse_args()

    if args.serve:
        serve()

    else:
        file_name = args.file

        if file_name is None:
            file_name = input("Enter image file name (PNG or JPG): ")

        exact_file_name = (find_file(file_name, lambda f1, f2 : f1 == f2 or f1[:-4] == f2) or # prioritize exact match
                           find_file(file_name, lambda f1, f2 : f1.find(f2) != -1))

        if exact_file_name is None:
            raise Exception(f"No image named or containing '{file_name}' found!")

        with open(exact_file_name, "rb") as file_bytes:
            traced_image = create_trace_image(file_bytes.read())

            with open("output.png", "wb") as output_file:
                output_file.write(traced_image)
