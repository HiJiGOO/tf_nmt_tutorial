
# coding: utf-8

# In[ ]:

import tensorflow as tf
import tflearn
import numpy as np
import re
import csv

from tensorflow.python.platform import gfile
from sklearn.utils.extmath import softmax
from sklearn.utils import shuffle

TOKENIZER_RE = re.compile(r"[A-Z]{2,}(?![a-z])|[A-Z][a-z]+(?=[A-Z])|[\'\w\-]+", re.UNICODE)
MAXLEN = 30

SAVE_DIR = "./save/self-attentive"
SAVE_FILE_PATH = SAVE_DIR + "/self-attentive.ckpt"

class SelfAttenModel(object):
    
    def __init__(self,
                 batch_size=40, 
                 vocab_size=200,
                 hidden_size=2000,
                 label_num=4,
                 layer_num=1, 
                 embedding_size=100, 
                 keep_prob=0.8, 
                 max_sequence_length=10,
                 num_units=128,
                 d_a=350,
                 r=30,
                 learning_rate=0.01,
                 p_coef=0.5,
                 use_penalization=True):
        
        self.batch_size = batch_size
        self.vocab_size = vocab_size
        self.hidden_size = hidden_size
        self.label_num = label_num
        self.layer_num = layer_num
        self.embedding_size = embedding_size
        self.keep_prob = keep_prob
        self.n = self.max_sequence_length = max_sequence_length
        self.u = self.num_units = num_units
        self.d_a = d_a
        self.r = r
        self.learning_rate = learning_rate
        self.p_coef = p_coef
        self.use_penalization = use_penalization
        
        self._build_placeholder()
        self._build_model()
        self._build_optimizer()
            
    def _build_placeholder(self):
        self.sources = tf.placeholder(name='sources', shape=[self.batch_size, self.max_sequence_length], dtype=tf.int64)
        self.labels = tf.placeholder(name='labels', shape=[self.batch_size], dtype=tf.int64)
        self.global_step = tf.Variable(0, name='global_step', trainable=False)

    def _build_single_cell(self):
        cell = tf.contrib.rnn.BasicLSTMCell(self.num_units)
        cell = tf.nn.rnn_cell.DropoutWrapper(cell, output_keep_prob=self.keep_prob)
        return cell
    
    def _build_model(self):
        # Word embedding #
        with tf.variable_scope("embedding"):
            initializer = tf.contrib.layers.xavier_initializer()
            embeddings = tf.get_variable(name="embedding_encoder",
                                                shape=[self.vocab_size, self.embedding_size], 
                                                dtype=tf.float32,
                                                initializer=initializer,
                                                trainable=True)

            input_embeddings = tf.nn.embedding_lookup(params=embeddings,
                                                      ids=self.sources)

        # Bidirectional rnn #
        with tf.variable_scope("bidirectional_rnn"):
            cell_forward = self._build_single_cell()
            cell_backward = self._build_single_cell()
            
            # outputs is state 'H'
            outputs, _ = tf.nn.bidirectional_dynamic_rnn(cell_fw=cell_forward, 
                                                              cell_bw=cell_backward, 
                                                              inputs=input_embeddings,
                                                              dtype=tf.float32)
            
            H = tf.concat(outputs, -1)
            
        # Self Attention #
        with tf.variable_scope("self_attention"):
            initializer = tf.contrib.layers.xavier_initializer()
            W_s1 = tf.get_variable(name="W_s1", shape=[self.d_a, 2*self.u], initializer=initializer)
            W_s2 = tf.get_variable(name='W_s2', shape=[self.r, self.d_a],initializer=initializer)
            
            a_prev = tf.map_fn(lambda x: tf.matmul(W_s1, tf.transpose(x)), H)
            a_prev = tf.tanh(a_prev)
            a_prev = tf.map_fn(lambda x: tf.matmul(W_s2, x), a_prev)
            
            self.A = tf.nn.softmax(a_prev)
            self.M = tf.matmul(self.A, H)
        
        # Fully connected layer #
        with tf.variable_scope("fully_connected_layer"):
            input_fc = tf.layers.flatten(self.M)
            layer_fc = tf.contrib.layers.fully_connected(inputs=input_fc, 
                                                         num_outputs=self.hidden_size,
                                                         activation_fn=tf.nn.relu)
            
            self.logits = tf.contrib.layers.fully_connected(inputs=layer_fc, 
                                                            num_outputs=self.label_num,
                                                            activation_fn=None)
            
            
            
    def _build_optimizer(self):
        with tf.variable_scope("optimizer"):
            cross_entropy = tf.nn.sparse_softmax_cross_entropy_with_logits(logits=self.logits,
                                                                           labels=self.labels)
            self.loss = tf.reduce_mean(cross_entropy)
            
            if self.use_penalization:
                A_T = tf.transpose(self.A, perm=[0, 2, 1])
                tile_eye = tf.tile(tf.eye(self.r), [self.batch_size, 1])
                tile_eye = tf.reshape(tile_eye, [-1, self.r, self.r])
                AA_T = tf.matmul(self.A, A_T) - tile_eye
                P = tf.square(tf.norm(AA_T, axis=[-2, -1], ord='fro'))
                p_loss = self.p_coef * P
                self.loss = self.loss + p_loss
            
            self.loss = tf.reduce_mean(self.loss)
            
            params = tf.trainable_variables()
            optimizer = tf.train.AdamOptimizer(self.learning_rate)
            grad_and_vars = tf.gradients(self.loss, params)
            clipped_gradients, _ = tf.clip_by_global_norm(grad_and_vars, 0.5)
            self.optimizer = optimizer.apply_gradients(zip(clipped_gradients, params), global_step=self.global_step)
            
            self.predict = tf.argmax(self.logits, -1)
            self.correct_pred = tf.equal(self.predict, self.labels)
            self.accuracy = tf.reduce_mean(tf.cast(self.correct_pred, tf.float32))
            

def load_csv(filepath, target_column=-1, data_column=None, has_header=False):
    with gfile.Open(filepath) as csv_file:
        data_file = csv.reader(csv_file)
        if has_header:
            header = next(data_file)

        data, target = [], []
        for i, row in enumerate(data_file):
            data.append([_d for _i, _d in enumerate(row) if _i == data_column])
            target.append([int(_d) for _i, _d in enumerate(row) if _i == target_column])

        return data, target

def token_parse(iterator):
    for value in iterator:
        return TOKENIZER_RE.findall(value)


def string_parser(arr, tokenizer, fit):
    if fit == False:
        return list(tokenizer.transform(arr)), tokenizer
    else:
        return list(tokenizer.fit_transform(arr)), tokenizer

def main():
    # Set mode
    is_training = False
    
    # Preparing data
    tokenizer = tflearn.data_utils.VocabularyProcessor(MAXLEN, tokenizer_fn=lambda tokens: [token_parse(x) for x in tokens])
    sources_raw, labels = load_csv('./data/ag_news_csv/train.csv', target_column=0, data_column=2)
    sources, vocab_processor = string_parser(sources_raw, tokenizer, fit=True)
    sources = tflearn.data_utils.pad_sequences(sources, maxlen=MAXLEN)
    labels = np.squeeze(labels)
        
    sources, labels = shuffle(sources, labels)
    vocab_size = len(vocab_processor.vocabulary_._mapping)
    label_num = int(np.max(labels) + 1)
    
    # Training options 
    epoch_nums = 1
    batch_size = 80
    total = len(sources)
    step_nums = int(total/batch_size)
    display_step = int(step_nums / 100)
     
    if is_training == True:
        keep_prob = 0.8
    else:
        keep_prob = 1.0
        
    model = SelfAttenModel(batch_size=batch_size,
                           vocab_size=vocab_size,
                           label_num=label_num,
                           keep_prob=keep_prob,
                           learning_rate=0.01,
                           p_coef=0.25,
                           max_sequence_length=MAXLEN)
    
    with tf.Session() as sess:
        
        # Saver
        saver = tf.train.Saver()
        ckpt_path = tf.train.latest_checkpoint(checkpoint_dir=SAVE_DIR)
        if ckpt_path: 
            saver.restore(sess, ckpt_path)
        else:
            sess.run(tf.global_variables_initializer())
            
        # train mode
        if is_training == True:
            for epoch in range(epoch_nums):
                print("%d Epoch Start" % epoch)
                display_loss = []
                display_accuracy = []
                for step in range(step_nums):

                    batch_start = step * batch_size
                    batch_end = batch_start + batch_size
                    batch_sources, batch_labels = (sources[batch_start:batch_end], labels[batch_start:batch_end])

                    loss, accuracy, predict, _= sess.run([model.loss, model.accuracy, model.predict, model.optimizer], 
                                                feed_dict={model.sources: batch_sources, 
                                                           model.labels: batch_labels})
                    display_loss.append(loss)
                    display_accuracy.append(accuracy)

                    if (step % display_step) == 0:
                        
                        print("Step " + str(step * batch_size) + ", Minibatch Loss= " +                               "{:.6f}".format(np.mean(display_loss)) + ", Training Accuracy= " +                               "{:.5f}".format(np.mean(display_accuracy)))
                        
                        display_loss.clear()
                        display_accuracy.clear()

                        saver.save(sess, SAVE_FILE_PATH)
                        
                        test_sources_raw, test_labels = load_csv('./data/ag_news_csv/test.csv', target_column=0, data_column=2)
                        test_sources, vocab_processor = string_parser(test_sources_raw, tokenizer, fit=True)
                        test_sources = tflearn.data_utils.pad_sequences(test_sources, maxlen=MAXLEN)
                        test_labels = np.squeeze(test_labels)

                        test_total = len(test_sources)
                        test_step_nums = int(test_total/batch_size)

                        accuracy_list = []
                        for step in range(test_step_nums):

                            batch_start = step * batch_size
                            batch_end = batch_start + batch_size
                            batch_sources, batch_labels = (test_sources[batch_start:batch_end], test_labels[batch_start:batch_end])

                            A, accuracy = sess.run([model.A, model.accuracy], 
                                                                feed_dict={model.sources: batch_sources,
                                                                           model.labels: batch_labels})
                            accuracy_list.append(accuracy)

                        print("Test Accuracy: {:.5f}".format(np.mean(accuracy_list)))

            print("Optimization Finished!")
        
        # test mode
        else:
            
            test_sources_raw, test_labels = load_csv('./data/ag_news_csv/test.csv', target_column=0, data_column=2)
            test_sources, vocab_processor = string_parser(test_sources_raw, tokenizer, fit=True)
            test_sources = tflearn.data_utils.pad_sequences(test_sources, maxlen=MAXLEN)
            test_labels = np.squeeze(test_labels)
            
            test_total = len(test_sources)
            test_step_nums = int(test_total/batch_size)
    
            accuracy_list = []
            step = 0 #for step in range(test_step_nums):
    
            batch_start = step * batch_size
            batch_end = batch_start + batch_size
            batch_sources, batch_labels = (test_sources[batch_start:batch_end], test_labels[batch_start:batch_end])

            A, accuracy = sess.run([model.A, model.accuracy], 
                                                feed_dict={model.sources: batch_sources,
                                                           model.labels: batch_labels})
            accuracy_list.append(accuracy)
            a_sum = np.sum(A, axis=0)
            
            print(softmax(a_sum))
            print("Test Accuracy: {:.5f}".format(np.mean(accuracy_list)))
            
            
if __name__ == '__main__':
    main()
    

