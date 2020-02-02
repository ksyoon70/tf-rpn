import os
import argparse
from PIL import Image, ImageDraw
import xml.etree.ElementTree as ET
import tensorflow as tf
import tensorflow_datasets as tfds
import matplotlib.pyplot as plt
import numpy as np

###########################################
## Pascal VOC
###########################################
VOC = {
    "max_height": 500,
    "max_width": 500,
}

def get_VOC_data(split):
    assert split in ["train", "validation", "test"]
    dataset, info = tfds.load("voc", split=split, with_info=True)
    data_len = info.splits[split].num_examples
    return dataset, data_len

def get_image(path, as_array=False):
    image = Image.open(path)
    return array_from_img(image) if as_array else image

# Normalized [y1, x1, y2, x2] => Denormalized [x1, y1, x2, y2]
def denormalize_bboxes(bboxes, height, width):
    new_bboxes = np.zeros(bboxes.shape, dtype=np.float32)
    new_bboxes[:, 0] = np.round(bboxes[:, 1] * width)
    new_bboxes[:, 1] = np.round(bboxes[:, 0] * height)
    new_bboxes[:, 2] = np.round(bboxes[:, 3] * width)
    new_bboxes[:, 3] = np.round(bboxes[:, 2] * height)
    return new_bboxes

# Denormalized [x1, y1, x2, y2] => Normalized [y1, x1, y2, x2]
def normalize_bboxes(bboxes, height, width):
    new_bboxes = np.zeros(bboxes.shape, dtype=np.float32)
    new_bboxes[:, 0] = bboxes[:, 1] / height
    new_bboxes[:, 1] = bboxes[:, 0] / width
    new_bboxes[:, 2] = bboxes[:, 3] / height
    new_bboxes[:, 3] = bboxes[:, 2] / width
    return new_bboxes

def get_image_boundaries(img):
    img_height, img_width, _ = img.shape
    return {
        "top": 0,
        "left": 0,
        "right": img_width,
        "bottom": img_height
    }

def update_image_boundaries_with_padding(img_boundaries, padding):
    img_boundaries["top"] = padding["top"]
    img_boundaries["left"] = padding["left"]
    img_boundaries["bottom"] += padding["top"]
    img_boundaries["right"] += padding["left"]
    return img_boundaries

def img_from_array(array):
    return Image.fromarray(array)

def array_from_img(image):
    return np.array(image)

def get_model_path(stride):
    main_path = "models"
    if not os.path.exists(main_path):
        os.makedirs(main_path)
    model_path = os.path.join(main_path, "stride_" + str(stride) + "_rpn_model_weights.h5")
    return model_path

def draw_grid_map(img, grid_map, stride):
    image = img_from_array(img)
    draw = ImageDraw.Draw(image)
    counter = 0
    for grid in grid_map:
        draw.rectangle((
            grid[0] + stride // 2 - 2,
            grid[1] + stride // 2 - 2,
            grid[2] + stride // 2 + 2,
            grid[3] + stride // 2 + 2), fill=(255, 255, 255, 0))
        counter += 1
    plt.figure()
    plt.imshow(image)
    plt.show()

def draw_anchors(img, anchors, padding=200):
    image = img_from_array(img)
    padded_img = add_padding(image, padding, padding, padding, padding)
    for anchor in anchors:
        padded_anchor = anchor + padding
        draw = ImageDraw.Draw(padded_img)
        draw.rectangle(padded_anchor.tolist(), outline=(255, 0, 0))
    plt.figure()
    plt.imshow(padded_img)
    plt.show()

def resize_image(image, max_allowed_size):
    width, height = image.size
    max_image_size = max(height, width)
    if max_allowed_size < max_image_size:
        if height > width:
            new_height = max_allowed_size
            new_width = int(round(new_height * (width / height)))
        else:
            new_width = max_allowed_size
            new_height = int(round(new_width * (height / width)))
        image = image.resize((new_width, new_height), Image.ANTIALIAS)
    return image

# image param => pillow image
def add_padding(image, top, right, bottom, left):
    width, height = image.size
    new_width = width + left + right
    new_height = height + top + bottom
    result = Image.new(image.mode, (new_width, new_height), (0, 0, 0))
    result.paste(image, (left, top))
    return result

# img param => numpy array
def get_padded_img(img, max_height, max_width):
    height, width, _ = img.shape
    assert height <= max_height
    assert width <= max_width
    padding_height = max_height - height
    padding_width = max_width - width
    top = padding_height // 2
    bottom = padding_height - top
    left = padding_width // 2
    right = padding_width - left
    padding = {
        "top": top,
        "bottom": bottom,
        "left": left,
        "right": right,
    }
    return np.pad(img, ((top, bottom), (left, right), (0,0)), mode='constant'), padding

# It take images as numpy arrays and return max height, max width values
def calculate_max_height_width(imgs):
    h_w_map = np.zeros((len(imgs), 2), dtype=np.int32)
    for index, img in enumerate(imgs):
        h_w_map[index, 0], h_w_map[index, 1], _ = img.shape
    max_val = h_w_map.argmax(axis=0)
    max_height, max_width = h_w_map[max_val[0], 0], h_w_map[max_val[1], 1]
    return max_height, max_width

def handle_args():
    parser = argparse.ArgumentParser(description="Region Proposal Network Implementation")
    parser.add_argument('-handle-gpu', action='store_true', help="Tensorflow 2 GPU compatibility flag")
    args = parser.parse_args()
    return args

def handle_gpu_compatibility():
    # For tf2 GPU compatibility
    try:
        gpus = tf.config.experimental.list_physical_devices("GPU")
        for gpu in gpus:
            tf.config.experimental.set_memory_growth(gpu, True)
    except Exception as e:
        print(e)
