#!/usr/bin/env python
from __future__ import division
import argparse
import tensorflow as tf
import glob
import numpy as np
from scipy import misc
import os
from tfrecord import create_tf_record
from concurrent.futures import ProcessPoolExecutor, as_completed
from itertools import repeat
from tqdm import tqdm 
import random

def compute_mean(file):
    grey_img = misc.imread(file, mode='L')
    mean = np.mean(grey_img)
    return mean

def calculate_img_stats(main_data_dir, dataset):

    files = glob.glob(os.path.join(main_data_dir, dataset) + '/*.png')
    resulting_means = []

    with ProcessPoolExecutor(32) as executor:
        futures = [executor.submit(compute_mean, f) for f in files]
        kwargs = {
              'total': len(futures),
              'unit': 'it',
              'unit_scale': True,
              'leave': True
        }

        for f in tqdm(as_completed(futures), **kwargs):
            pass
        print "Done loading futures!"
        for i in tqdm(range(len(futures))):
            try:
                example = futures[i].result()
                resulting_means.append(example)
            except Exception as e:
                print "Failed to compute means"

    print np.mean(resulting_means)
    print np.std(resulting_means)

def calculate_class_ratios(main_data_dir, dataset):

    files = glob.glob(os.path.join(main_data_dir, dataset) + '/*.png')

    targe_label_dic = {0:0 ,1:0, 2:0, 3:0}

    for img in files:

        file_name = img.split('/')[-1].split('_')
        class_name = file_name[0].lower() + '_' + file_name[1] 

        if class_name == "gleason_5":
            targe_label_dic[3] += 1
        elif class_name == "gleason_4":
            targe_label_dic[2] += 1
        elif class_name == "gleason_3":
            targe_label_dic[1] += 1
        else:
            targe_label_dic[0] += 1

    values = [targe_label_dic[k] for k in range(4)]
    f_i = [sum(values)/v for v in values]
    class_weights = [f/sum(f_i) for f in f_i]
    print "class ratios:", [v/sum(values) for v in values]
    print "class weights:", class_weights
    np.save(dataset + '_class_weights.npy', class_weights)

def calculate_mean_std(main_data_dir, dataset):
    pass


def build_tfrecords(main_data_dir, main_tfrecords_dir, dataset):
    
    files = glob.glob(os.path.join(main_data_dir, dataset) + '/*.png')
    
    target_labels = [] 

    for img in files:

        file_name = img.split('/')[-1].split('_')
        class_name = file_name[0].lower() + '_' + file_name[1] 

        if class_name == "gleason_5":
            target_labels.append(3)
        elif class_name == "gleason_4":
            target_labels.append(2)
        elif class_name == "gleason_3":
            target_labels.append(1)
        else:
            target_labels.append(0)

    create_tf_record(os.path.join(main_tfrecords_dir, dataset +'.tfrecords'), files, target_labels)

if __name__ == '__main__':
    main_data_dir = '/media/data_cifs/andreas/pathology/gleason_training_patches/'
    main_tfrecords_dir = '/media/data_cifs/andreas/pathology/gleason_training_patches/tfrecords'

    # build_tfrecords(main_data_dir, main_tfrecords_dir, 'train')
    # build_tfrecords(main_data_dir, main_tfrecords_dir, 'val')
    # build_tfrecords(main_data_dir, main_tfrecords_dir, 'test')

    # calculate_class_ratios(main_data_dir, 'train')
    calculate_img_stats(main_data_dir, 'train')



