#!/usr/bin/env python
from __future__ import division
import os
import glob
import numpy as np
import tensorflow as tf
import matplotlib.pyplot as plt
from PIL import Image
from scipy import misc
from tqdm import tqdm
from random import randint
import random
import math
from concurrent.futures import ProcessPoolExecutor, as_completed
from itertools import repeat
import math
import cv2

VGG_MEAN = [103.939, 116.779, 123.68]
PI = tf.constant(math.pi)

GLEASON_MEANS = [167.312, 135.0144, 187.337]
GLEASON_STDS = [22.496, 27.958, 25.337]

GLEASON_MEAN_G = 153.85
GLEASON_MEAN_STD_G  = 25.38

def _bytes_feature(value):
  return tf.train.Feature(bytes_list = tf.train.BytesList(value=[value]))

def _int64_feature(value):
  return tf.train.Feature(int64_list = tf.train.Int64List(value=[value]))

def _float_feature(value):
  return tf.train.Feature(float_list = tf.train.FloatList(value=[value]))

def normalize(image):
  """
  Applys z-score normalization to input image
  Input: image - batch of images
  Output: image_scaled - batch of images with zscore normalization applied
  """
  image_scaled = (image - GLEASON_MEAN_G) / GLEASON_MEAN_STD_G
  return image_scaled

def tfrecord2metafilename(tfrecord_filename):
  """
  Derive associated meta filename for a tfrecord filename
  Input: /path/to/foo.tfrecord
  Output: /path/to/foo.meta
  """
  base, ext = os.path.splitext(tfrecord_filename)
  return base + '_meta.npz'

def vgg_preprocessing(image_rgb):
  """
  Preprocssing the given image for evalutaiton with vgg16 model 
  Input: image_rgb - A tensor representing an image of size [224, 224, 3]
  Output: image_bgr - A processed BGR image of size [224, 224, 3]
  """

  image_rgb_scaled = image_rgb * 255.0
  red, green, blue = tf.split(num_or_size_splits=3, axis=3, value=image_rgb_scaled)
  assert red.get_shape().as_list()[1:] == [224, 224, 1]
  assert green.get_shape().as_list()[1:] == [224, 224, 1]
  assert blue.get_shape().as_list()[1:] == [224, 224, 1]
  image_bgr = tf.concat(values = [
      blue - VGG_MEAN[0],
      green - VGG_MEAN[1],
      red - VGG_MEAN[2],
      ], axis=3)
  assert image_bgr.get_shape().as_list()[1:] == [224, 224, 3], image_bgr.get_shape().as_list()
  return image_bgr

def encode(img_path, target_label):
  """
  Encode tfrecord for img, path, label and bone type 
  Inputs: img_path - filepath to img
          target_label - label for img
  Outputs: encoded tfrecord
  """
  img = np.array(Image.open(img_path))
  img = img[:,:,:3].astype(np.float32) 

  img_raw = img.astype(np.uint8).tostring()
  path_raw = img_path.encode('utf-8')

  example = tf.train.Example(features=tf.train.Features(feature={
          'image_raw': _bytes_feature(img_raw),
          'file_path': _bytes_feature(path_raw),
          'target_label':_int64_feature(int(target_label)),

          }))
  return example

def distort_color(image, color_ordering=0, fast_mode=False, scope=None):
  """Distort the color of a Tensor image.
  Each color distortion is non-commutative and thus ordering of the color ops
  matters. Ideally we would randomly permute the ordering of the color ops.
  Rather then adding that level of complication, we select a distinct ordering
  of color ops for each preprocessing thread.
  Args:
    image: 3-D Tensor containing single image in [0, 1].
    color_ordering: Python int, a type of distortion (valid values: 0-3).
    fast_mode: Avoids slower ops (random_hue and random_contrast)
    scope: Optional scope for name_scope.
  Returns:
    3-D Tensor color-distorted image on range [0, 1]
  Raises:
    ValueError: if color_ordering not in [0, 3]
  """
  with tf.name_scope(scope, 'distort_color', [image]):
    if fast_mode:
      if color_ordering == 0:
        image = tf.image.random_brightness(image, max_delta=32. / 255.)
        image = tf.image.random_saturation(image, lower=0.5, upper=1.5)
      else:
        image = tf.image.random_saturation(image, lower=0.5, upper=1.5)
        image = tf.image.random_brightness(image, max_delta=32. / 255.)
    else:
      if color_ordering == 0:
        image = tf.image.random_brightness(image, max_delta=32. / 255.)
        image = tf.image.random_saturation(image, lower=0.5, upper=1.5)
        image = tf.image.random_hue(image, max_delta=0.2)
        image = tf.image.random_contrast(image, lower=0.5, upper=1.5)
      elif color_ordering == 1:
        image = tf.image.random_saturation(image, lower=0.5, upper=1.5)
        image = tf.image.random_brightness(image, max_delta=32. / 255.)
        image = tf.image.random_contrast(image, lower=0.5, upper=1.5)
        image = tf.image.random_hue(image, max_delta=0.2)
      elif color_ordering == 2:
        image = tf.image.random_contrast(image, lower=0.5, upper=1.5)
        image = tf.image.random_hue(image, max_delta=0.2)
        image = tf.image.random_brightness(image, max_delta=32. / 255.)
        image = tf.image.random_saturation(image, lower=0.5, upper=1.5)
      elif color_ordering == 3:
        image = tf.image.random_hue(image, max_delta=0.2)
        image = tf.image.random_saturation(image, lower=0.5, upper=1.5)
        image = tf.image.random_contrast(image, lower=0.5, upper=1.5)
        image = tf.image.random_brightness(image, max_delta=32. / 255.)
      else:
        raise ValueError('color_ordering must be in [0, 3]')

    # The random_* ops do not necessarily clamp.
    return tf.clip_by_value(image, 0.0, 1.0)

def distort_brightness_constrast(image, ordering=0):
  """
  Apply brightness contrast distortion to images
  Inputs: image - input image
          ordering - ordering whether to apply brightness augmentation or contrast augementation first
  Outputs: None
  """
  if ordering == 0:
    image = tf.image.random_brightness(image, max_delta=32. / 255.)
    image = tf.image.random_contrast(image, lower=0.5, upper=1.5)
  else:
    image = tf.image.random_contrast(image, lower=0.5, upper=1.5)
    image = tf.image.random_brightness(image, max_delta=32. / 255.)
  return tf.clip_by_value(image, 0.0, 1.0)

def create_tf_record(tfrecords_filename, file_pointers, target_labels):
  """
  Creates tfrecords using mutiple processes
  Inputs: tfrecords_filename - tfrecord filepath
          file_pointers - array of paths to image files
          target_labels - array of paths to image labels
  Otputs: None
  """
  writer = tf.python_io.TFRecordWriter(tfrecords_filename)

  print '%d files in %d categories' % (len(np.unique(file_pointers)), len(np.unique(target_labels)))

  with ProcessPoolExecutor(32) as executor:
    futures = [executor.submit(encode, f, t_l) for f, t_l in zip(file_pointers, target_labels)]

    kwargs = {
        'total': len(futures),
        'unit': 'it',
        'unit_scale': True,
        'leave': True
    }

    for f in tqdm(as_completed(futures), **kwargs):
        pass
    print "Done loading futures!"
    print "Writing examples..."
    for i in tqdm(range(len(futures))):
      try:
          example = futures[i].result()
          writer.write(example.SerializeToString())
      except Exception as e:
          print "Failed to write example!"

  meta = tfrecord2metafilename(tfrecords_filename)
  np.savez(meta, file_pointers=file_pointers, labels=target_labels, output_pointer=tfrecords_filename)

  print '-' * 100
  print 'Generated tfrecord at %s' % tfrecords_filename
  print '-' * 100

def read_and_decode(filename_queue=None, img_dims=[256,256,3], model_dims=[224,224,3], size_of_batch=32,\
                    augmentations_dic=None, num_of_threads=1, shuffle=True):
  """
  Reads, decodes and applys augmentations to batch of images
  Inputs: filename_queue - Input queue for either train, val or test tfrecords 
          img_dims - dimensions of input image
          model_dims - output dimensions for model
          size_of_batch - size of batch of images 
          augmentations_dic - dictionary with selected augmentations
          num_of_threads - number of threads selected
          shuffle - option to shuffle batch
  Outputs: img - batch of images
           t_l - batch of target labels
           b_t - batch of bone types
           f_p - batch of filepointers
  """
  reader = tf.TFRecordReader()

  _, serialized_example = reader.read(filename_queue)

  
  features = tf.parse_single_example(
    serialized_example,
  
    features={
      'image_raw': tf.FixedLenFeature([], tf.string),
      'file_path': tf.FixedLenFeature([], tf.string),
      'target_label': tf.FixedLenFeature([], tf.int64), 

      })

  image = tf.decode_raw(features['image_raw'], tf.uint8)
  target_label = tf.cast(features['target_label'], tf.int32)
  file_path = tf.cast(features['file_path'], tf.string)

  image = tf.reshape(image, img_dims)
  image = tf.cast(image, tf.float32)

  if augmentations_dic['rand_crop']:
    image = tf.random_crop(image, model_dims)
  else:
    image = tf.image.resize_image_with_crop_or_pad(image, model_dims[0],\
                                                   model_dims[1])
  if augmentations_dic['rand_flip_left_right']:
    image = tf.image.random_flip_left_right(image)

  if augmentations_dic['rand_flip_top_bottom']:
    image = tf.image.random_flip_up_down(image)

  if augmentations_dic['rand_rotate']:
    elems = tf.cast(tf.convert_to_tensor(np.deg2rad(np.array(range(360)))), dtype=tf.float32)
    sample = tf.squeeze(tf.multinomial(tf.log([ (1.0/np.repeat(360, 360)).tolist()]), 1)) 
    random_angle = elems[tf.cast(sample, tf.int32)]
    image = tf.contrib.image.rotate(image, random_angle)  

  if shuffle:
    img, t_l, f_p = tf.train.shuffle_batch([image, target_label, file_path],
                                                   batch_size=size_of_batch,
                                                   capacity=1000 + 3 * size_of_batch,
                                                   min_after_dequeue=1000,
                                                   num_threads=num_of_threads)
  else:
    img, t_l, f_p = tf.train.batch([image, target_label, file_path],
                                         batch_size=size_of_batch,
                                         capacity=5000,
                                         allow_smaller_final_batch=True,
                                         num_threads=num_of_threads)

  if augmentations_dic['warp']:

    mean = 0.0
    sigma = 1.0
    alpha = 6.0
    ksize = 128

    X = tf.random_uniform([model_dims[0], model_dims[1]])*2 - 1
    Y = tf.random_uniform([model_dims[0], model_dims[1]])*2 - 1
    X = tf.reshape(X, [1, model_dims[0],model_dims[1], 1])
    Y = tf.reshape(Y, [1, model_dims[0],model_dims[1], 1])

    x = tf.linspace(-3.0, 3.0, ksize)
    z = ((1.0 / (sigma * tf.sqrt(2.0 * PI))) * tf.exp(tf.negative(tf.pow(x - mean, 2.0) / (2.0 * tf.pow(sigma, 2.0)))))
    z_2d = tf.matmul(tf.reshape(z, [ksize, 1]), tf.reshape(z, [1, ksize]))
    z_4d = tf.reshape(z_2d, [ksize, ksize, 1, 1])

    X_convolved = tf.nn.conv2d(X, z_4d, strides=[1, 1, 1, 1], padding='SAME')
    Y_convolved = tf.nn.conv2d(Y, z_4d, strides=[1, 1, 1, 1], padding='SAME')

    X_convolved = (X_convolved / tf.reduce_max(X_convolved))*alpha
    Y_convolved = (Y_convolved / tf.reduce_max(Y_convolved))*alpha

    trans = tf.stack([X_convolved,Y_convolved], axis=-1)
    trans = tf.reshape(trans, [-1])

    batch_trans = tf.tile(trans, [size_of_batch])
    batch_trans = tf.reshape(batch_trans, [size_of_batch, model_dims[0], model_dims[1] ,2])

    img = tf.reshape(img, [size_of_batch, model_dims[0], model_dims[1], model_dims[2]])

    img = tf.contrib.image.dense_image_warp(img, batch_trans)

  if augmentations_dic['grayscale']:
    img = tf.image.rgb_to_grayscale(img)

  
  return  img, t_l, f_p


