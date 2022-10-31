import tensorflow as tf
device_name = tf.test.gpu_device_name()
if device_name != '/device:GPU:0':
  raise SystemError('GPU device not found')
print('Found GPU at: {}'.format(device_name))

import time
import datetime

import pandas as pd
import os
import matplotlib.pyplot as plt
import numpy as np
import tensorflow as tf
import IPython.display as ipd

import glob
import numpy as np
from data_processing.feature_extractor import FeatureExtractor
from utils import prepare_input_features, stft_tensorflow, TimeHistory
from model import build_model, build_model_lstm
# Load the TensorBoard notebook extension.
# %load_ext tensorboard

from tensorflow.python.client import device_lib
import keras.models
from pathlib import Path

# 1. Set Paramter
device_lib.list_local_devices()

tf.random.set_seed(999)
np.random.seed(999)

model_name = 'cnn'
# model_name = 'lstm'

domain = 'freq'
# domain = 'time'

top_db = 80
center = True

if model_name == "cnn":
    n_fft    = 256
    win_length = n_fft
    overlap      = round(0.25 * win_length) # overlap of 75%
    inputFs      = 48e3
    fs           = 16e3
    numFeatures  = n_fft//2 + 1
    numSegments  = 8

elif model_name == "lstm":
    n_fft    = 512
    win_length = n_fft
    overlap      = round(0.5 * win_length) # overlap of 50%
    inputFs      = 48e3
    fs           = 16e3
    numFeatures  = n_fft//2 + 1
    numSegments  = 64 if center else 62 # 1.008 sec in 512 window, 256 hop, sr = 16000 Hz
else:
    NotImplementedError("Only implemented cnn and lstm")

config = {'top_db': top_db,
    'nfft': n_fft,
    'overlap': round(0.5 * win_length),
    'center': center,
    'fs': 16000,
    'audio_max_duration': 1.008,
    'numFeatures':numFeatures,
    'numSegments':numSegments,
    }

print("-"*30)
for key, value in config.items():
    print(f"{key} : {value}")
print("-"*30)

# 2. Load data 
if model_name == 'lstm':
    if domain == 'time':
        path_to_dataset = f"./records_{model_name}_time"
    else:    
        path_to_dataset = f"./records_{model_name}"
else:
    path_to_dataset = f"./records_{model_name}"

# get training and validation tf record file names
train_tfrecords_filenames = glob.glob(os.path.join(path_to_dataset, 'train_*'))
val_tfrecords_filenames = glob.glob(os.path.join(path_to_dataset, 'val_*'))

# shuffle the file names for training
np.random.shuffle(train_tfrecords_filenames)
print("Model: ", model_name)
print("Domain: ", domain)
print("Data path: ", path_to_dataset)
print("Training file names: ", train_tfrecords_filenames)
print("Validation file names: ", val_tfrecords_filenames)

def tf_record_parser(record):
    if model_name == "cnn":
        keys_to_features = {
        "noise_stft_phase": tf.io.FixedLenFeature((), tf.string, default_value=""),
        'noise_stft_mag_features': tf.io.FixedLenFeature([], tf.string),
        "clean_stft_magnitude": tf.io.FixedLenFeature((), tf.string)
        }
        features = tf.io.parse_single_example(record, keys_to_features)

        noise_stft_mag_features = tf.io.decode_raw(features['noise_stft_mag_features'], tf.float32)
        clean_stft_magnitude = tf.io.decode_raw(features['clean_stft_magnitude'], tf.float32)
        noise_stft_phase = tf.io.decode_raw(features['noise_stft_phase'], tf.float32)
        # when getting data from tfrecords, it need to transfer tensorflow api such as reshape

        # reshape input and annotation images, cnn
        noise_stft_mag_features = tf.reshape(noise_stft_mag_features, (numFeatures, numSegments, 1), name="noise_stft_mag_features")
        clean_stft_magnitude = tf.reshape(clean_stft_magnitude, (numFeatures, 1, 1), name="clean_stft_magnitude") # [TODO] Check
        noise_stft_phase = tf.reshape(noise_stft_phase, (numFeatures,), name="noise_stft_phase")

        return noise_stft_mag_features , clean_stft_magnitude
    
    elif model_name == 'lstm':
        if domain == 'time':    
            keys_to_features = {
            "noisy": tf.io.FixedLenFeature((), tf.string, default_value=""),
            'clean': tf.io.FixedLenFeature([], tf.string),
            }

            features = tf.io.parse_single_example(record, keys_to_features)

            noisy = tf.io.decode_raw(features['noisy'], tf.float32)
            clean = tf.io.decode_raw(features['clean'], tf.float32)

            noise_stft_magnitude, noise_stft_phase, noise_stft_real, noise_stft_imag = stft_tensorflow(noisy, 
                                                                                                    nfft=config['nfft'], 
                                                                                                    hop_length=config['overlap'],
                                                                                                    center=config['center'])
            clean_stft_magnitude, clean_stft_phase, clean_stft_real, clean_stft_imag = stft_tensorflow(clean, 
                                                                                                    nfft=config['nfft'], 
                                                                                                    hop_length=config['overlap'],
                                                                                                    center=config['center'])
        else:          
            keys_to_features = {
                "noisy_stft_magnitude": tf.io.FixedLenFeature([], tf.string, default_value=""),
                "clean_stft_magnitude": tf.io.FixedLenFeature((), tf.string),     
                "noise_stft_phase": tf.io.FixedLenFeature((), tf.string),
                "clean_stft_phase": tf.io.FixedLenFeature((), tf.string),
            }
            features = tf.io.parse_single_example(record, keys_to_features)

            noise_stft_magnitude = tf.io.decode_raw(features['noisy_stft_magnitude'], tf.float32) # phase scaling by clean wav
            clean_stft_magnitude = tf.io.decode_raw(features['clean_stft_magnitude'], tf.float32)
            noise_stft_phase = tf.io.decode_raw(features['noise_stft_phase'], tf.float32)
            clean_stft_phase = tf.io.decode_raw(features['clean_stft_phase'], tf.float32)
            
        noise_stft_magnitude = tf.reshape(noise_stft_magnitude/((numFeatures-1)*2), (1, numSegments, numFeatures), name="noise_stft_magnitude")
        clean_stft_magnitude = tf.reshape(clean_stft_magnitude/((numFeatures-1)*2), (1, numSegments, numFeatures), name="clean_stft_magnitude")
        noise_stft_phase = tf.reshape(noise_stft_phase, (1, numSegments, numFeatures), name="noise_stft_phase")
        clean_stft_phase = tf.reshape(clean_stft_phase, (1, numSegments, numFeatures), name="clean_stft_phase")
    
        noisy_feature = tf.stack([noise_stft_magnitude, noise_stft_phase], name="noisy")
        clean_feature = tf.stack([clean_stft_magnitude, clean_stft_phase], name="clean")

        return noisy_feature, clean_feature
    else:
        raise ValueError("Model didn't implement...")

train_dataset = tf.data.TFRecordDataset([train_tfrecords_filenames])
train_dataset = train_dataset.map(tf_record_parser)
train_dataset = train_dataset.shuffle(8192)
train_dataset = train_dataset.repeat()
train_dataset = train_dataset.batch(512)
train_dataset = train_dataset.prefetch(buffer_size=tf.data.experimental.AUTOTUNE)

# val_dataset
test_dataset = tf.data.TFRecordDataset([val_tfrecords_filenames])
test_dataset = test_dataset.map(tf_record_parser)
test_dataset = test_dataset.repeat(1)
test_dataset = test_dataset.batch(512)

# 3. Build model
if model_name == "cnn":
    model = build_model(l2_strength=0.0)
elif model_name == "lstm":
    model = build_model_lstm()
else:
    raise ValueError("Model didn't implement...")
model.summary()

# You might need to install the following dependencies: sudo apt install python-pydot python-pydot-ng graphviz
# tf.keras.utils.plot_model(model, show_shapes=True, dpi=64)

# 4. Initialize model
baseline_val_loss = model.evaluate(test_dataset)[0]
print(f"Baseline accuracy {baseline_val_loss}")


# 5. Set logging
save_path = os.path.join(f"./result/{model_name}", datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))

checkpoint_save_path = os.path.join(save_path, "checkpoint/model-{epoch:02d}-{val_loss:.4f}.hdf5")
model_save_path = os.path.join(save_path, "model")
console_log_save_path = os.path.join(save_path, "debug.txt")

early_stopping_callback = tf.keras.callbacks.EarlyStopping(monitor='val_loss', patience=50, restore_best_weights=True, baseline=None)
logdir = os.path.join(f"./logs/{model_name}", datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
tensorboard_callback = tf.keras.callbacks.TensorBoard(logdir, update_freq='batch', histogram_freq=1, write_graph=True)

# histogram_freq=0, write_graph=True: for monitoring the weight histogram

checkpoint_callback = tf.keras.callbacks.ModelCheckpoint(filepath=checkpoint_save_path, 
                                                         test='val_loss', save_best_only=True)
time_callback = TimeHistory(filepath=console_log_save_path)


# 6. Train Model
model.fit(train_dataset, # model.fit([pair_1, pair_2], labels, epochs=50)
         steps_per_epoch=800, # you might need to change this
         validation_data=test_dataset,
         epochs=200,
         callbacks=[early_stopping_callback, tensorboard_callback, checkpoint_callback, time_callback]
        )

# 7. Model Evaluate and save
val_loss = model.evaluate(test_dataset)[0]
if val_loss < baseline_val_loss:
  print("New model saved.")
  keras.models.save_model(model, model_save_path, overwrite=True, include_optimizer=True)
  # model.save('./denoiser_cnn_log_mel_generator.h5')