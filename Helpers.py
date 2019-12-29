import os
from PIL import Image, ImageDraw
import xml.etree.ElementTree as ET
import tensorflow as tf
import matplotlib.pyplot as plt
import numpy as np

###########################################
## Pascal VOC
###########################################
VOC = {
    "person": ["person"],
    "animals": ["bird", "cat", "cow", "dog", "horse", "sheep"],
    "vehicles": ["aeroplane", "bicycle", "boat", "bus", "car", "motorbike", "train"],
    "indoors": ["bottle", "chair", "diningtable", "pottedplant", "sofa", "tvmonitor"],
    "datatypes": ["train", "val", "trainval", "test"]
}
VOC["classes"] = sorted(VOC["person"] + VOC["animals"] + VOC["vehicles"] + VOC["indoors"])

def get_pascal_VOC_data(datatype, classes):
    assert datatype in VOC["datatypes"]
    main_path = os.path.join("data", "VOCdevkit", "VOC2007")
    images_path = os.path.join(main_path, "JPEGImages")
    annotations_path = os.path.join(main_path, "Annotations")
    classes_path = os.path.join(main_path, "ImageSets", "Main")
    filenames = []
    for classname in classes:
        assert classname in VOC["classes"]
        path = os.path.join(classes_path, classname + "_" + datatype + ".txt")
        with open(path) as file:
            for line in file:
                holder = line.strip().split(" ")
                if int(holder[-1]) > -1 and holder[0] not in filenames:
                    filenames.append(holder[0])
            #End of for
        #End of with open
    #End of for
    dataset = []
    for filename in filenames:
        annotation_path = os.path.join(annotations_path, filename + ".xml")
        annotation_data = handle_pascal_VOC_annotation(annotation_path, classes)
        annotation_data["image_path"] = os.path.join(images_path, annotation_data["filename"])
        dataset.append(annotation_data)
    #End of for
    return dataset

def handle_pascal_VOC_annotation(path, classes):
    tree = ET.parse(path)
    root = tree.getroot()
    size = root.find("size")
    objects = []
    for obj in root.findall("object"):
        bbox = obj.find("bndbox")
        name = obj.find("name").text
        if name not in classes:
            continue
        objects.append({
            "name": name,
            "obj_id": VOC["classes"].index(name),
            "bbox": {
                "x_min": int(bbox.find("xmin").text),
                "y_min": int(bbox.find("ymin").text),
                "x_max": int(bbox.find("xmax").text),
                "y_max": int(bbox.find("ymax").text),
            }
        })
    return {
        "filename": root.find("filename").text,
        "width": int(size.find("width").text),
        "height": int(size.find("height").text),
        "depth": int(size.find("depth").text),
        "objects": objects
    }

def get_image(path, as_array=False):
    image = Image.open(path)
    return array_from_img(image) if as_array else image

def img_from_array(array):
    return Image.fromarray(array)

def array_from_img(image):
    return np.array(image)

def get_model_path():
    main_path = "models"
    if not os.path.exists(main_path):
        os.makedirs(main_path)
    model_path = os.path.join(main_path, "rpn_model.h5")
    return model_path

def handle_gpu_compatibility():
    # For tf2 GPU compatibility
    try:
        gpus = tf.config.experimental.list_physical_devices('GPU')
        for gpu in gpus:
            tf.config.experimental.set_memory_growth(gpu, True)
    except Exception as e:
        print(e)