import tensorflow as tf
from tensorflow.keras.layers import Conv2D
from tensorflow.keras.models import Model
import numpy as np
import Helpers

def generate_base_anchors(stride, ratios, scales):
    center = stride // 2
    base_anchors = []
    for scale in scales:
        for ratio in ratios:
            box_area = scale ** 2
            w = round((box_area / ratio) ** 0.5)
            h = round(w * ratio)
            x_min = center - w / 2
            y_min = center - h / 2
            x_max = center + w / 2
            y_max = center + h / 2
            base_anchors.append([y_min, x_min, y_max, x_max])
    return np.array(base_anchors, dtype=np.float32)

def calculate_iou(anc, gt):
    ### Ground truth box normalized y1, x1, y2, x2
    gt_y1, gt_x1, gt_y2, gt_x2 = gt
    gt_width = gt_x2 - gt_x1
    gt_height = gt_y2 - gt_y1
    gt_area = gt_width * gt_height
    ### Anchor normalized y1, x1, y2, x2
    anc_y1, anc_x1, anc_y2, anc_x2 = anc
    anc_width = anc_x2 - anc_x1
    anc_height = anc_y2 - anc_y1
    anc_area = anc_width * anc_height
    ### Possible intersection
    x_top = max(gt_x1, anc_x1)
    y_top = max(gt_y1, anc_y1)
    x_bottom = min(gt_x2, anc_x2)
    y_bottom = min(gt_y2, anc_y2)
    ### Check intersection
    if x_bottom < x_top or y_bottom < y_top:
        return 0.0
    ### Calculate intersection area
    intersection_area = (x_bottom - x_top) * (y_bottom - y_top)
    ### Calculate union area
    union_area = gt_area + anc_area - intersection_area
    # Intersection over Union
    return intersection_area / union_area

def generate_iou_map(anchors, gt_boxes):
    anchor_count = anchors.shape[0]
    gt_box_count = len(gt_boxes)
    iou_map = np.zeros((anchor_count, gt_box_count), dtype=np.float32)
    for anc_index, anchor in enumerate(anchors):
        for gt_index, gt_box_data in enumerate(gt_boxes):
            iou = calculate_iou(anchor, gt_box_data)
            iou_map[anc_index, gt_index] = iou
    return iou_map

def get_bboxes_from_deltas(anchors, deltas):
    bboxes = np.zeros(anchors.shape, dtype=np.float32)
    #
    all_anc_width = anchors[:, 3] - anchors[:, 1]
    all_anc_height = anchors[:, 2] - anchors[:, 0]
    all_anc_ctr_x = anchors[:, 1] + 0.5 * all_anc_width
    all_anc_ctr_y = anchors[:, 0] + 0.5 * all_anc_height
    #
    all_bbox_width = np.exp(deltas[:, 3]) * all_anc_width
    all_bbox_height = np.exp(deltas[:, 2]) * all_anc_height
    all_bbox_ctr_x = (deltas[:, 1] * all_anc_width) + all_anc_ctr_x
    all_bbox_ctr_y = (deltas[:, 0] * all_anc_height) + all_anc_ctr_y
    #
    bboxes[:, 0] = all_bbox_ctr_y - (0.5 * all_bbox_height)
    bboxes[:, 1] = all_bbox_ctr_x - (0.5 * all_bbox_width)
    bboxes[:, 2] = all_bbox_height + bboxes[:, 0]
    bboxes[:, 3] = all_bbox_width + bboxes[:, 1]
    #
    return bboxes

def get_deltas_from_bboxes(anchors, gt_boxes, pos_anchors):
    bbox_deltas = np.zeros(anchors.shape, dtype=np.float32)
    anchor_indices, gt_indices = pos_anchors[:, 0], pos_anchors[:, 1]
    #
    anc_width = anchors[anchor_indices, 3] - anchors[anchor_indices, 1]
    anc_height = anchors[anchor_indices, 2] - anchors[anchor_indices, 0]
    anc_ctr_x = anchors[anchor_indices, 1] + 0.5 * anc_width
    anc_ctr_y = anchors[anchor_indices, 0] + 0.5 * anc_height
    #
    gt_width = gt_boxes[gt_indices, 3] - gt_boxes[gt_indices, 1]
    gt_height = gt_boxes[gt_indices, 2] - gt_boxes[gt_indices, 0]
    gt_ctr_x = gt_boxes[gt_indices, 1] + 0.5 * gt_width
    gt_ctr_y = gt_boxes[gt_indices, 0] + 0.5 * gt_height
    #
    delta_x = (gt_ctr_x - anc_ctr_x) / anc_width
    delta_y = (gt_ctr_y - anc_ctr_y) / anc_height
    delta_w = np.log(gt_width / anc_width)
    delta_h = np.log(gt_height / anc_height)
    #
    bbox_deltas[anchor_indices, 0] = delta_y
    bbox_deltas[anchor_indices, 1] = delta_x
    bbox_deltas[anchor_indices, 2] = delta_h
    bbox_deltas[anchor_indices, 3] = delta_w
    #
    return bbox_deltas

def get_labels_from_bboxes(anchors, gt_labels, pos_anchors, total_label_number):
    labels = np.zeros((anchors.shape[0], total_label_number+1), dtype=np.int32)
    labels[:, -1] = 1
    anchor_indices, gt_indices = pos_anchors[:, 0], pos_anchors[:, 1]
    labels[anchor_indices, gt_labels[gt_indices]] = 1
    labels[anchor_indices, -1] = 0
    return labels

def faster_rcnn_cls_loss(y_true, y_pred):
    lf = tf.losses.CategoricalCrossentropy()
    return tf.reduce_mean(lf(y_true, y_pred))

def rpn_cls_loss(y_true, y_pred):
    indices = tf.where(tf.not_equal(y_true, -1))
    target = tf.gather_nd(y_true, indices)
    output = tf.gather_nd(y_pred, indices)
    lf = tf.losses.BinaryCrossentropy()
    return tf.reduce_mean(lf(target, output))

def rpn_reg_loss(y_true, y_pred):
    indices = tf.where(tf.not_equal(y_true, 0))
    target = tf.gather_nd(y_true, indices)
    output = tf.gather_nd(y_pred, indices)
    # Same with the smooth l1 loss
    lf = tf.losses.Huber()
    return tf.reduce_mean(lf(target, output))

def get_image_params(img, stride):
    height, width, _ = img.shape
    output_height, output_width = height // stride, width // stride
    return height, width, output_height, output_width

def update_gt_boxes(gt_boxes, img_height, img_width, padding):
    padded_height = img_height + padding["top"] + padding["bottom"]
    padded_width = img_width + padding["left"] + padding["right"]
    gt_boxes[:, 0] = (np.round(gt_boxes[:, 0] * img_height) + padding["top"]) / padded_height
    gt_boxes[:, 1] = (np.round(gt_boxes[:, 1] * img_width) + padding["left"]) / padded_width
    gt_boxes[:, 2] = (np.round(gt_boxes[:, 2] * img_height) + padding["top"]) / padded_height
    gt_boxes[:, 3] = (np.round(gt_boxes[:, 3] * img_width) + padding["left"]) / padded_width
    return gt_boxes

def get_input_img(img, input_processor):
    processed_img = img.copy()
    processed_img = input_processor(processed_img)
    processed_img = np.expand_dims(processed_img, axis=0)
    return processed_img

def normalize_bboxes(bboxes, height, width):
    new_bboxes = np.zeros(bboxes.shape, dtype=np.float32)
    new_bboxes[:, 0] = bboxes[:, 0] / height
    new_bboxes[:, 1] = bboxes[:, 1] / width
    new_bboxes[:, 2] = bboxes[:, 2] / height
    new_bboxes[:, 3] = bboxes[:, 3] / width
    return new_bboxes

def get_anchors(img, anchor_ratios, anchor_scales, stride):
    anchor_count = len(anchor_ratios) * len(anchor_scales)
    height, width, output_height, output_width = get_image_params(img, stride)
    #
    grid_x = np.arange(0, output_width) * stride
    grid_y = np.arange(0, output_height) * stride
    #
    width_padding = (width - output_width * stride) / 2
    height_padding = (height - output_height * stride) / 2
    grid_x = width_padding + grid_x
    grid_y = height_padding + grid_y
    #
    grid_y, grid_x = np.meshgrid(grid_y, grid_x)
    grid_map = np.vstack((grid_y.ravel(), grid_x.ravel(), grid_y.ravel(), grid_x.ravel())).transpose()
    #
    base_anchors = generate_base_anchors(stride, anchor_ratios, anchor_scales)
    #
    output_area = grid_map.shape[0]
    anchors = base_anchors.reshape((1, anchor_count, 4)) + \
              grid_map.reshape((1, output_area, 4)).transpose((1, 0, 2))
    anchors = anchors.reshape((output_area * anchor_count, 4)).astype(np.float32)
    anchors = normalize_bboxes(anchors, height, width)
    return anchors

def non_max_suppression(pred_bboxes, pred_labels, top_n_boxes=300):
    selected_indices = tf.image.non_max_suppression(pred_bboxes, pred_labels, top_n_boxes)
    selected_boxes = tf.gather(pred_bboxes, selected_indices)
    selected_labels = tf.gather(pred_labels, selected_indices)
    return selected_boxes.numpy(), selected_labels.numpy()

def get_predicted_bboxes_and_labels(anchor_count, anchors, pred_bbox_deltas, pred_labels):
    _, output_height, output_width, _ = pred_bbox_deltas.shape
    n_row = output_height * output_width * anchor_count
    pred_bbox_deltas = pred_bbox_deltas.reshape((n_row, 4))
    pred_labels = pred_labels.reshape((n_row, ))
    pred_bboxes = get_bboxes_from_deltas(anchors, pred_bbox_deltas)
    return pred_bboxes, pred_labels

def get_positive_and_negative_anchors(anchors, gt_boxes, total_pos_anchor_number=64):
    iou_map = generate_iou_map(anchors, gt_boxes)
    # any time => iou_map.reshape(output_height, output_width, anchor_count, gt_boxes.shape[0])
    ################################################################
    total_gt_box_count = gt_boxes.shape[0]
    max_indices_each_gt_box = iou_map.argmax(axis=1)
    # IoU map has iou values for every gt boxes and we merge these values column wise
    merged_iou_map = iou_map[np.arange(iou_map.shape[0]), max_indices_each_gt_box]
    masked_merged_iou_map = np.ma.array(merged_iou_map, mask=False)
    # First we calculate max overlapped box for every ground truth box
    for n_col in range(total_gt_box_count):
        anchor_indices_for_gt_box = np.where(max_indices_each_gt_box == n_col)[0]
        if anchor_indices_for_gt_box.shape[0] == 0:
            continue
        max_anchor_index_for_gt_box = iou_map[:, n_col].argmax()
        masked_merged_iou_map.mask[max_anchor_index_for_gt_box] = True
    #
    sorted_iou_map = masked_merged_iou_map.argsort()[::-1]
    sorted_anchor_indices = sorted_iou_map[:total_pos_anchor_number]
    # We finalize pos anchors with max n anchors
    pos_anchors = np.array((sorted_anchor_indices, max_indices_each_gt_box[sorted_anchor_indices]), dtype=np.int32).transpose()
    ##########
    neg_anchors = np.where(masked_merged_iou_map < 0.3)[0]
    neg_anchors = neg_anchors[~np.isin(neg_anchors, pos_anchors[:,0])]
    neg_anchors_count = len(neg_anchors)
    pos_anchors_count = len(pos_anchors[:,0])
    # If there are more negative anchors than positive
    # randomly select negative anchors as many as positive anchor number
    if neg_anchors_count > pos_anchors_count:
        neg_anchors = np.random.choice(neg_anchors, size=pos_anchors_count, replace=False)
    #
    return pos_anchors, neg_anchors

def get_bbox_deltas_and_labels(img, anchors, gt_boxes, anchor_count, stride, img_boundaries):
    height, width, output_height, output_width = get_image_params(img, stride)
    #############################
    # Positive and negative anchors calculation
    #############################
    # Positive and negative anchor numbers are 128 in original paper
    pos_anchors, neg_anchors = get_positive_and_negative_anchors(anchors, gt_boxes, total_pos_anchor_number=64)
    #############################
    # Bbox delta calculation
    #############################
    bbox_deltas = get_deltas_from_bboxes(anchors, gt_boxes, pos_anchors)
    #############################
    # Label calculation
    #############################
    # labels => 1 object, 0 background, -1 neutral
    labels = -1 * np.ones((anchors.shape[0], ), dtype=np.float32)
    labels[neg_anchors] = 0
    labels[pos_anchors[:,0]] = 1
    ############################################################
    bbox_deltas = bbox_deltas.reshape(output_height, output_width, anchor_count * 4)
    bbox_deltas = np.expand_dims(bbox_deltas, axis=0)
    labels = labels.reshape(output_height, output_width, anchor_count)
    labels = np.expand_dims(labels, axis=0)
    return bbox_deltas, labels

def generator(data,
              anchor_ratios,
              anchor_scales,
              stride,
              input_processor,
              max_height=None,
              max_width=None,
              apply_padding=False):
    while True:
        for image_data in data:
            img = image_data["image"].numpy()
            img_height, img_width, _ = img.shape
            gt_boxes = image_data["objects"]["bbox"].numpy()
            img_boundaries = Helpers.get_image_boundaries(img)
            if apply_padding:
                img, padding = Helpers.get_padded_img(img, max_height, max_width)
                gt_boxes = update_gt_boxes(gt_boxes, img_height, img_width, padding)
                img_boundaries = Helpers.update_image_boundaries_with_padding(img_boundaries, padding)
            anchors = get_anchors(img, anchor_ratios, anchor_scales, stride)
            anchor_count = len(anchor_ratios) * len(anchor_scales)
            bbox_deltas, labels = get_bbox_deltas_and_labels(img, anchors, gt_boxes, anchor_count, stride, img_boundaries)
            input_img = get_input_img(img, input_processor)
            yield input_img, [bbox_deltas, labels]

def get_model(base_model, anchor_count):
    output = Conv2D(512, (3, 3), activation="relu", padding="same", name="rpn_conv")(base_model.output)
    rpn_cls_output = Conv2D(anchor_count, (1, 1), activation="sigmoid", name="rpn_cls")(output)
    rpn_reg_output = Conv2D(anchor_count * 4, (1, 1), activation="linear", name="rpn_reg")(output)
    rpn_model = Model(inputs=base_model.input, outputs=[rpn_reg_output, rpn_cls_output])
    return rpn_model
