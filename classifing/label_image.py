# Original file from:
#   - https://www.tensorflow.org/hub/tutorials/image_retraining
#
# Copyright 2017 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import argparse

import numpy as np
import tensorflow as tf
import textwrap
import time

import os, glob, sys
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
sys.path.append( '..' )
from utils import ops_file as rw
from utils import ops_data as ops
from utils.ops_thread import worker

# parameter settings ------------------------------------------------------------
file_name = "tensorflow/examples/label_image/data/grace_hopper.jpg"
model_file = "tensorflow/examples/label_image/data/inception_v3_2016_08_28_frozen.pb"
graph = None
label_file = "tensorflow/examples/label_image/data/imagenet_slim_labels.txt"
input_height = 299
input_width = 299
input_mean = 0
input_std = 255
input_layer = "input"
output_layer = "InceptionV3/Predictions/Reshape_1"

start = 4760
concurrent = 100
partition = 100

labels = []
# ------------------------------------------------------------ parameter settings

def load_graph(model_file):
    graph = tf.Graph()
    graph_def = tf.GraphDef()

    with open(model_file, "rb") as f:
        graph_def.ParseFromString(f.read())
    with graph.as_default():
        tf.import_graph_def(graph_def)

    return graph

def read_tensor_from_image_file(file_name,
                                input_height=299,
                                input_width=299,
                                input_mean=0,
                                input_std=255):
    input_name = "file_reader"
    output_name = "normalized"
    file_reader = tf.read_file(file_name, input_name)
    if file_name.endswith(".png"):
        image_reader = tf.image.decode_png( file_reader, channels=3, name="png_reader")
    elif file_name.endswith(".gif"):
        image_reader = tf.squeeze( tf.image.decode_gif(file_reader, name="gif_reader"))
    elif file_name.endswith(".bmp"):
        image_reader = tf.image.decode_bmp(file_reader, name="bmp_reader")
    else:
        image_reader = tf.image.decode_jpeg( file_reader, channels=3, name="jpeg_reader")

    float_caster = tf.cast(image_reader, tf.float32)
    dims_expander = tf.expand_dims(float_caster, 0)
    resized = tf.image.resize_bilinear(dims_expander, [input_height, input_width])
    normalized = tf.divide(tf.subtract(resized, [input_mean]), [input_std])
    sess = tf.Session()
    result = sess.run(normalized)

    return result

def load_labels(label_file):
    label = []
    proto_as_ascii_lines = tf.gfile.GFile(label_file).readlines()
    for l in proto_as_ascii_lines:
        label.append(l.rstrip())
    return label


def work( f ):
    t = read_tensor_from_image_file(
        f,
        input_height=input_height,
        input_width=input_width,
        input_mean=input_mean,
        input_std=input_std)

    input_name = "import/" + input_layer
    output_name = "import/" + output_layer
    input_operation = graph.get_operation_by_name(input_name)
    output_operation = graph.get_operation_by_name(output_name)

    with tf.Session(graph=graph) as sess:
        results = sess.run(output_operation.outputs[0], {
            input_operation.outputs[0]: t
        })
    results = np.squeeze(results)
    top_k = results.argsort()[-5:][::-1]

    data = {}
    for i in top_k: data[ labels[ i ] ] = results[ i ]

    # create csv row
    row = "'" + ops.find_numeric( f ) + "',"
    for l in labels: row += '{},'.format( float(data[ l ]) )
    row += f + '\n' # append the filename

    return [ row ]

# creates the worker class and performs action
def trigger( header, files ):
    # create worker class
    W = worker( concurrent=concurrent )

    # timing
    t_s = time.time()

    for i in range( start, len(files), partition ):
        if( i > len( files) ): break

        tail = (i + partition)
        if( tail >= len(files) ): tail = len(files)

        print( textwrap.dedent( f'''
            Status Report:
                Remaining jobs: {len(files) - i}
                Percentage: {100 * i / len(files):.2f}%
                Executed for {time.time() - t_s} seconds
        ''' ) )

        # run by multi-threaded worker
        W.init()
        W.name_with( 'work_g_{}'.format( i ) )
        W.input( files[i:tail] ).output( 'genderized_g_{}'.format( i ), 'csv' )\
            .output_header( header ).work_with( work ).run()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--img_dir", required=True, help="dir of images")
    parser.add_argument("--data_file", required=True, help="images to be processed")
    parser.add_argument("--graph", help="graph/model to be executed")
    parser.add_argument("--labels", help="name of file containing labels")
    parser.add_argument("--input_height", type=int, help="input height")
    parser.add_argument("--input_width", type=int, help="input width")
    parser.add_argument("--input_mean", type=int, help="input mean")
    parser.add_argument("--input_std", type=int, help="input std")
    parser.add_argument("--input_layer", help="name of input layer")
    parser.add_argument("--output_layer", help="name of output layer")
    args = parser.parse_args()

    if args.graph:          graph = load_graph( args.graph )
    if args.data_file:      data_file = args.data_file
    if args.img_dir:        img_folder = args.img_dir
    if args.labels:         label_file = args.labels
    if args.input_height:   input_height = args.input_height
    if args.input_width:    input_width = args.input_width
    if args.input_mean:     input_mean = args.input_mean
    if args.input_std:      input_std = args.input_std
    if args.input_layer:    input_layer = args.input_layer
    if args.output_layer:   output_layer = args.output_layer

    # the csv header
    header = ''
    if( os.path.isdir( img_folder ) and os.path.exists( img_folder ) ):
        # load the label
        labels = load_labels(label_file)
        # creating csv header
        if( header == '' ):
            header += 'id,'
            for l in labels: header += '{},'.format( l )
            header += 'path'

        files = glob.glob( r'{}/{}'.format( img_folder, data_file ) )
        trigger( header, files )
    else:
        print( 'Image folder not specified!' )
        sys.exit( 1 )
