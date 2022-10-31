from curses import window
from keras.layers import (
  Conv2D, 
  Input, 
  LeakyReLU, 
  Flatten, 
  Dense, 
  Reshape, 
  Conv2DTranspose, 
  BatchNormalization, 
  Activation, 
  ZeroPadding2D, 
  SpatialDropout2D,
  LSTM,
  Dense,
  Layer,
  Multiply,
)

import tensorflow as tf
from keras import Model, Sequential
import keras.regularizers
from librosa.filters import mel
from librosa import istft
import logging

import numpy as np
import keras.optimizers


from metrics import (
    SI_SDR,
    WB_PESQ,
    SDR,
    STOI,
    NB_PESQ
)

model_name = 'cnn'
# model_name = 'lstm'

# domain = 'freq'
domain = 'time'

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

def conv_block(x, filters, kernel_size, strides, padding='same', use_bn=True):
  x = Conv2D(filters=filters, kernel_size=kernel_size, strides=strides, padding=padding, use_bias=False,
          kernel_regularizer=keras.regularizers.l2(0.0006))(x)
  x = Activation('relu')(x)
  if use_bn:
    x = BatchNormalization()(x)
  return x

def full_pre_activation_block(x, filters, kernel_size, strides, padding='same', use_bn=True):
  shortcut = x
  in_channels = x.shape[-1]

  x = BatchNormalization()(x)
  x = Activation('relu')(x)
  x = Conv2D(filters=filters, kernel_size=kernel_size, strides=strides, padding='same')(x)

  x = BatchNormalization()(x)
  x = Activation('relu')(x)
  x = Conv2D(filters=in_channels, kernel_size=kernel_size, strides=strides, padding='same')(x)

  return shortcut + x


def build_model(l2_strength):
  inputs = Input(shape=[numFeatures, numSegments, 1])
  x = inputs
  
  # -----
  x = ZeroPadding2D(((4,4), (0,0)))(x)
  x = Conv2D(filters=18, kernel_size=[9,8], strides=[1, 1], padding='valid', use_bias=False,
              kernel_regularizer=keras.regularizers.l2(l2_strength))(x)
  x = Activation('relu')(x)
  x = BatchNormalization()(x)

  skip0 = Conv2D(filters=30, kernel_size=[5,1], strides=[1, 1], padding='same', use_bias=False,
                 kernel_regularizer=keras.regularizers.l2(l2_strength))(x)
  x = Activation('relu')(skip0)
  x = BatchNormalization()(x)

  x = Conv2D(filters=8, kernel_size=[9,1], strides=[1, 1], padding='same', use_bias=False,
              kernel_regularizer=keras.regularizers.l2(l2_strength))(x)
  x = Activation('relu')(x)
  x = BatchNormalization()(x)

  # -----
  x = Conv2D(filters=18, kernel_size=[9,1], strides=[1, 1], padding='same', use_bias=False,
              kernel_regularizer=keras.regularizers.l2(l2_strength))(x)
  x = Activation('relu')(x)
  x = BatchNormalization()(x)

  skip1 = Conv2D(filters=30, kernel_size=[5,1], strides=[1, 1], padding='same', use_bias=False,
                 kernel_regularizer=keras.regularizers.l2(l2_strength))(x)
  x = Activation('relu')(skip1)
  x = BatchNormalization()(x)

  x = Conv2D(filters=8, kernel_size=[9,1], strides=[1, 1], padding='same', use_bias=False,
              kernel_regularizer=keras.regularizers.l2(l2_strength))(x)
  x = Activation('relu')(x)
  x = BatchNormalization()(x)

  # ----
  x = Conv2D(filters=18, kernel_size=[9,1], strides=[1, 1], padding='same', use_bias=False,
              kernel_regularizer=keras.regularizers.l2(l2_strength))(x)
  x = Activation('relu')(x)
  x = BatchNormalization()(x)
  
  x = Conv2D(filters=30, kernel_size=[5,1], strides=[1, 1], padding='same', use_bias=False,
              kernel_regularizer=keras.regularizers.l2(l2_strength))(x)
  x = Activation('relu')(x)
  x = BatchNormalization()(x)

  x = Conv2D(filters=8, kernel_size=[9,1], strides=[1, 1], padding='same', use_bias=False,
              kernel_regularizer=keras.regularizers.l2(l2_strength))(x)
  x = Activation('relu')(x)
  x = BatchNormalization()(x)

  # ----
  x = Conv2D(filters=18, kernel_size=[9,1], strides=[1, 1], padding='same', use_bias=False,
              kernel_regularizer=keras.regularizers.l2(l2_strength))(x)
  x = Activation('relu')(x)
  x = BatchNormalization()(x)

  x = Conv2D(filters=30, kernel_size=[5,1], strides=[1, 1], padding='same', use_bias=False,
             kernel_regularizer=keras.regularizers.l2(l2_strength))(x)
  x = x + skip1
  x = Activation('relu')(x)
  x = BatchNormalization()(x)

  x = Conv2D(filters=8, kernel_size=[9,1], strides=[1, 1], padding='same', use_bias=False,
              kernel_regularizer=keras.regularizers.l2(l2_strength))(x)
  x = Activation('relu')(x)
  x = BatchNormalization()(x)

  # ----
  x = Conv2D(filters=18, kernel_size=[9,1], strides=[1, 1], padding='same', use_bias=False,
              kernel_regularizer=keras.regularizers.l2(l2_strength))(x)
  x = Activation('relu')(x)
  x = BatchNormalization()(x)

  x = Conv2D(filters=30, kernel_size=[5,1], strides=[1, 1], padding='same', use_bias=False,
             kernel_regularizer=keras.regularizers.l2(l2_strength))(x)
  x = x + skip0
  x = Activation('relu')(x)
  x = BatchNormalization()(x)

  x = Conv2D(filters=8, kernel_size=[9,1], strides=[1, 1], padding='same', use_bias=False,
              kernel_regularizer=keras.regularizers.l2(l2_strength))(x)
  x = Activation('relu')(x)
  x = BatchNormalization()(x)

  # ----
  x = SpatialDropout2D(0.2)(x)
  x = Conv2D(filters=1, kernel_size=[129,1], strides=[1, 1], padding='same')(x)

  model = Model(inputs=inputs, outputs=x)

  optimizer = keras.optimizers.Adam(3e-4)
  #optimizer = RAdam(total_steps=10000, warmup_proportion=0.1, min_lr=3e-4)

  model.compile(optimizer=optimizer, loss='mse', 
                metrics=[keras.metrics.RootMeanSquaredError('rmse')])
  return model


class MelSpec(Layer):
    def __init__(
        self,
        frame_length=n_fft,
        frame_step=overlap,
        fft_length=None,
        sampling_rate=16000,
        num_mel_channels=128,
        freq_min=125,
        freq_max=8000,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.frame_length = frame_length
        self.frame_step = frame_step
        self.fft_length = fft_length
        self.sampling_rate = sampling_rate
        self.num_mel_channels = num_mel_channels
        self.freq_min = freq_min
        self.freq_max = freq_max
        
        # Defining mel filter. This filter will be multiplied with the STFT output
        self.mel_filterbank = tf.signal.linear_to_mel_weight_matrix(
            num_mel_bins=self.num_mel_channels,
            num_spectrogram_bins=self.frame_length // 2 + 1,
            sample_rate=self.sampling_rate,
            lower_edge_hertz=self.freq_min,
            upper_edge_hertz=self.freq_max,
        )

    def call(self, magnitude, training=True):
        # We will only perform the transformation during training.
        mel = tf.matmul(tf.square(magnitude), self.mel_filterbank)
        return mel

    def get_config(self):
        config = super(MelSpec, self).get_config()
        config.update(
            {
                "frame_length": self.frame_length,
                "frame_step": self.frame_step,
                "fft_length": self.fft_length,
                "sampling_rate": self.sampling_rate,
                "num_mel_channels": self.num_mel_channels,
                "freq_min": self.freq_min,
                "freq_max": self.freq_max,
            }
        )
        return config

class InverseMelSpec(Layer):
    def __init__(
        self,
        frame_length=n_fft,
        frame_step=overlap,
        fft_length=None,
        sampling_rate=16000,
        num_mel_channels=128,
        freq_min=125,
        freq_max=8000,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.frame_length = frame_length
        self.frame_step = frame_step
        self.fft_length = fft_length
        self.sampling_rate = sampling_rate
        self.num_mel_channels = num_mel_channels
        self.freq_min = freq_min
        self.freq_max = freq_max
        
        # Defining mel filter. This filter will be multiplied with the STFT output
        self.mel_filterbank = tf.signal.linear_to_mel_weight_matrix(
            num_mel_bins=self.num_mel_channels,
            num_spectrogram_bins=self.frame_length // 2 + 1,
            sample_rate=self.sampling_rate,
            lower_edge_hertz=self.freq_min,
            upper_edge_hertz=self.freq_max,
        )

    def call(self, mel, training=True):
        # We will only perform the transformation during training.
        magnitude = tf.matmul(mel, tf.transpose(self.mel_filterbank, perm=[1, 0]))
        return magnitude

    def get_config(self):
        config = super(InverseMelSpec, self).get_config()
        config.update(
            {
                "frame_length": self.frame_length,
                "frame_step": self.frame_step,
                "fft_length": self.fft_length,
                "sampling_rate": self.sampling_rate,
                "num_mel_channels": self.num_mel_channels,
                "freq_min": self.freq_min,
                "freq_max": self.freq_max,
            }
        )
        return config

def get_mel_filter(samplerate, n_fft, n_mels, fmin, fmax):
    mel_basis = mel(sr=samplerate, n_fft=n_fft, n_mels=n_mels, fmin=fmin, fmax=fmax)
    return tf.convert_to_tensor(mel_basis, dtype=tf.float32)

# TODO add custom losses and metrics
# import keras.losses 
# import keras.metrics
# keras.losses.mean_absolute_error # loss = mean(abs(y_true - y_pred), axis=-1)
# keras.losses.mean_squared_error # loss = mean(square(y_true - y_pred), axis=-1)
# keras.metrics.RootMeanSquaredError # metric = sqrt(mean(square(y_true - y_pred)))

def convert_stft_from_amplitude_phase(y):
  y_amplitude = y[..., 0, :, :, :] # amp/phase, ch, frame, freq
  y_phase = y[..., 1, :, :, :]        
  y_amplitude = tf.cast(y_amplitude, dtype=tf.complex64)
  y_phase = tf.math.multiply(tf.cast(1j, dtype=tf.complex64), tf.cast(y_phase, dtype=tf.complex64))
  
  return tf.math.multiply(y_amplitude, tf.math.exp(y_phase)) 


def convert_stft_from_real_imag(y):
  y_real = y[..., 0, :, :, :] # amp/phase, ch, frame, freq
  y_imag = y[..., 1, :, :, :]        
  y_real = tf.cast(y_real, dtype=tf.complex64)
  y_imag = tf.math.multiply(tf.cast(1j, dtype=tf.complex64), tf.cast(y_imag, dtype=tf.complex64))
  
  return tf.add(y_real, y_imag)


def mean_square_error_amplitdue_phase(y_true, y_pred):
  reference_stft = convert_stft_from_amplitude_phase(y_true)
  estimation_stft = convert_stft_from_amplitude_phase(y_pred)

  return tf.keras.losses.mean_squared_error(reference_stft, estimation_stft)

def mean_absolute_error_amplitdue_phase(y_true, y_pred):
  reference_stft = convert_stft_from_amplitude_phase(y_true)
  estimation_stft = convert_stft_from_amplitude_phase(y_pred)

  return tf.keras.losses.mean_absolute_error(reference_stft, estimation_stft)


def phase_sensitive_spectral_approximation_loss(y_true, y_pred):
  """After backpropagation, estimation will be nan
    D_psa(mask) = (mask|y| - |s|cos(theta))^2
    theta = theta_s - theta_y
  """
  reference_amplitude = y_true[..., 0, :, :, :]
  reference_phase = y_true[..., 1, :, :, :]        
  estimation_amplitude = y_pred[..., 0, :, :, :]
  estimation_phase = y_pred[..., 1, :, :, :]        

  estimation = tf.math.multiply(estimation_amplitude, tf.math.cos(estimation_phase-reference_phase))

  return tf.keras.losses.mean_squared_error(reference_amplitude, estimation)


def phase_sensitive_spectral_approximation_loss_bose(y_true, y_pred):
  """[TODO] After backpropagation, evaluation is not nan, but when training it goes to nan
    Loss = norm_2(|X|^0.3-[X_bar|^0.3) + 0.113*norm_2(X^0.3-X_bar^0.3)

    Q. How complex number can be power 0.3?
      x + yi = r*e^{jtheta}
      (x + yi)*0.3 = r^0.3*e^{j*theta*0.3}


      X^0.3-X_bar^0.3 r^{0.3}*e^{j*theta*0.3} - r_bar^{0.3}*e^{j*theta_bar*0.3}
  """
  reference_amplitude = tf.cast(y_true[..., 0, :, :, :], dtype=tf.complex64)
  reference_phase = tf.cast(y_true[..., 1, :, :, :], dtype=tf.complex64)
  estimation_amplitude = tf.cast(y_pred[..., 0, :, :, :], dtype=tf.complex64)
  estimation_phase = tf.cast(y_pred[..., 1, :, :, :], dtype=tf.complex64)

  loss_absolute = tf.math.pow(tf.math.pow(reference_amplitude, 0.3) - tf.math.pow(estimation_amplitude, 0.3), 2)
  loss_phase = 0.113*tf.math.pow(tf.math.pow(reference_amplitude, 0.3)*tf.math.exp(1j*reference_phase*0.3) - tf.math.pow(estimation_amplitude, 0.3)*tf.math.exp(1j*estimation_phase*0.3) ,2)
  loss = loss_absolute + loss_phase

  return loss


class SpeechMetric(tf.keras.metrics.Metric):
  """        
    [V] SI_SDR,     pass, after function check, value check
    [V] WB_PESQ,    pass, after function check, value check
    [ ] STOI,       fail, np.matmul, (15, 257) @ (257, 74) -> OMP: Error #131: Thread identifier invalid, zsh: abort
    [ ] NB_PESQ     fail, ValueError: The truth value of an array with more than one element is ambiguous. Use a.any() or a.all()
    [ ] SDR,        fail, MP: Error #131: Thread identifier invalid. zsh: abort      python train.py -> maybe batch related?

    [TODO] Verification, compared with pytorch
  """
  def __init__(self, metric, name='sisdr', **kwargs):
    super(SpeechMetric, self).__init__(name=name, **kwargs)
    self.metric = metric 
    self.metric_name = name
    self.score = self.add_weight(name=f"{name}_value", initializer='zeros')
    self.total = self.add_weight(name='total', initializer='zeros')

  def update_state(self, y_true, y_pred, sample_weight=None):
    reference_stft_librosa = convert_stft_from_amplitude_phase(y_true)
    estimation_stft_librosa = convert_stft_from_amplitude_phase(y_pred)

    reference_stft_librosa *= 2*(reference_stft_librosa.shape[-1]-1)
    estimation_stft_librosa *= 2*(reference_stft_librosa.shape[-1]-1)

    window_fn = tf.signal.hamming_window

    reference = tf.signal.inverse_stft(
      reference_stft_librosa, frame_length=n_fft, frame_step=overlap,
      window_fn=tf.signal.inverse_stft_window_fn(
         frame_step=overlap, forward_window_fn=window_fn))
    
    estimation = tf.signal.inverse_stft(
      estimation_stft_librosa, frame_length=n_fft, frame_step=overlap,
      window_fn=tf.signal.inverse_stft_window_fn(
         frame_step=overlap, forward_window_fn=window_fn))

    self.score.assign_add(tf.py_function(func=self.metric, inp=[reference, estimation], Tout=tf.float32,  name=f"{self.metric_name}_metric")) # tf 2.x
    self.total.assign_add(1)
    
  def result(self):
    return self.score / self.total

def build_model_lstm(power=0.3):
  """
    Kernal Initialization
    Bias   Initizlization
  """
    
  # inputs_real = Input(shape=[1, numSegments, numFeatures], name='input_real')  
  # inputs_imag = Input(shape=[1, numSegments, numFeatures], name='input_imag')  

  # [TODO] Normalize
  inputs = Input(shape=[2, 1, numSegments, numFeatures], name='input')

  # inputs_amp = tf.math.sqrt(tf.math.pow(tf.math.abs(inputs[...,0, :, :, :]), 2)+tf.math.pow(tf.math.abs(inputs[...,1, :, :, :]), 2))
  inputs_amp = inputs[..., 0, :, :, :]
  inputs_phase = inputs[..., 1, :, :, :]
 
  mask = tf.squeeze(inputs_amp, axis=1) # merge channel
  mask = MelSpec()(mask)
  mask = LSTM(256, activation='tanh', return_sequences=True)(mask)
  mask = LSTM(256, activation='tanh', return_sequences=True)(mask)
  
  mask = BatchNormalization()(mask)

  mask = Dense(128, activation='relu', use_bias=True, 
        kernel_initializer='glorot_uniform', bias_initializer='zeros')(mask) # [TODO] check initialization method
  mask = Dense(128, activation='sigmoid', use_bias=True,
        kernel_initializer='glorot_uniform', bias_initializer='zeros')(mask) # [TODO] check initialization method
  
  mask = InverseMelSpec()(mask)
  mask = tf.expand_dims(mask, axis=1) # expand channel
  
  # mask = tf.expand_dims(mask, axis=1) # expand real/imag
  # inputs_clx = tf.stack([inputs_real, inputs_imag], axis=-4) # ..., real/imag, ch, num_frame, freq_bin
  # outputs_clx = Multiply()([inputs_clx, mask]) # X_bar = M (Hadamard product) |Y|exp(angle(Y)), Y is noisy

  # outputs_real = Multiply()([inputs_real, mask]) # X_bar = M (Hadamard product) |Y|exp(angle(Y)), Y is noisy
  # outputs_imag = Multiply()([inputs_imag, mask]) # X_bar = M (Hadamard product) |Y|exp(angle(Y)), Y is noisy

  outputs_amp = Multiply()([inputs_amp, mask]) # X_bar = M (Hadamard product) |Y|exp(angle(Y)), Y is noisy
  outputs = tf.stack([outputs_amp, inputs_phase], axis=-4) # ..., real/imag, ch, num_frame, freq_bin

  # [TODO] How to print a tensor while training?

  model = Model(inputs=inputs, outputs=outputs)

  # optimizer = keras.optimizers.SGD(1e-3)
  optimizer = keras.optimizers.Adam(3e-4)

  # model.compile(optimizer=optimizer, 
  #             loss= meanSquareError(), # 'mse'
  #             metrics=[keras.metrics.RootMeanSquaredError('rmse'), 
  #             ])

  model.compile(optimizer=optimizer, 
              loss= mean_absolute_error_amplitdue_phase,
              metrics=[
              # keras.metrics.RootMeanSquaredError('rmse')
              SpeechMetric(metric=SI_SDR, name='sisdr'),
              # SpeechMetric(metric=WB_PESQ, name='wb_pesq'), # no utter weight overload -> [TODO] remove a slience in data using dB scale/ normalize fft
              ])
  return model

