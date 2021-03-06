
# coding: utf-8

# In[1]:


import numpy as np
import tensorflow as tf


# In[2]:

TOKEN_PAD="<p>"
TOKEN_START="<s>"
TOKEN_END="</s>"

source_sentences = ["취미가 뭐예요", "만나서 반가워요", "내일 만나서 놀아요"]
target_sentences = ["what is your hobby", "nice to meet you", "meet tomorrow"]

source_vocab = [TOKEN_PAD, TOKEN_START, TOKEN_END, "취미가", "뭐예요", "만나서", "반가워요", "내일", "놀아요"]
target_vocab = [TOKEN_PAD, TOKEN_START, TOKEN_END, "what", "is", "your", "hobby", "nice", "to", "meet", "you", "tomorrow"]

source_input_idx = [
    [3,  4,  0,  0,  0], 
    [5,  6,  0,  0,  0],  
    [7,  5,  8,  0,  0]]
target_input_idx = [
    [1,  3,  4,  5,  6], 
    [1,  7,  8,  9, 10], 
    [1,  9, 11,  0,  0]]
target_output_idx = [
    [3,  4,  5,  6,  2], 
    [7,  8,  9, 10,  2], 
    [9, 11,  2,  0,  0]]

sen_num = len(source_sentences)
source_vocab_size = len(source_vocab)
target_vocab_size = len(target_vocab)
max_vocab_size = max(source_vocab_size, target_vocab_size)

source_input_one_hot = []
target_input_one_hot = []

for sen_idx in range(sen_num):
    source_input_one_hot.append(np.eye(max_vocab_size)[source_input_idx[sen_idx]])
    target_input_one_hot.append(np.eye(max_vocab_size)[target_input_idx[sen_idx]])

num_units = 12
num_layer = 2

batch_size = 3
learning_rate = 0.0002

training_steps = 20000
display_step = 100

max_sentence_length = 5
                   
source_inputs = tf.placeholder(dtype=tf.float32, shape=(batch_size, max_sentence_length, max_vocab_size), name='source_inputs')
target_inputs = tf.placeholder(dtype=tf.float32, shape=(batch_size, max_sentence_length, max_vocab_size), name='target_inputs')
target_outputs = tf.placeholder(dtype=tf.int64, shape=(batch_size, max_sentence_length), name='target_outputs')

def build_single_cell(num_units):
    cell = tf.contrib.rnn.BasicLSTMCell(num_units)
    return cell
                   
with tf.variable_scope('encoder'):
    
    encoder_cell_list = [build_single_cell(num_units) for i in range(num_layer)]
    encoder_multi_cell = tf.contrib.rnn.MultiRNNCell(encoder_cell_list)
    
    encoder_outputs, encoder_final_state = tf.nn.dynamic_rnn(cell=encoder_multi_cell,
                                                             inputs=source_inputs,
                                                             dtype=tf.float32)
    
with tf.variable_scope('decoder'):
    
    decoder_cell_list = [build_single_cell(num_units) for i in range(num_layer)]
    decoder_multi_cell = tf.contrib.rnn.MultiRNNCell(decoder_cell_list)
    
    decoder_initial_state = encoder_final_state
    decoder_outputs, decoder_final_state = tf.nn.dynamic_rnn(cell=decoder_multi_cell,
                                                             inputs=target_inputs,
                                                             initial_state=decoder_initial_state,
                                                             dtype=tf.float32)

    decoder_predict = tf.argmax(decoder_outputs, 2)
    
with tf.variable_scope("optimizer"):
    cross_entropy = tf.nn.sparse_softmax_cross_entropy_with_logits(logits=decoder_outputs,
                                                                   labels=target_outputs)
    cost = tf.reduce_mean(cross_entropy)
    
    optimizer = tf.train.AdamOptimizer(learning_rate=learning_rate)
    optimizer = optimizer.minimize(cost)
    
    correct_pred = tf.equal(tf.argmax(decoder_outputs, 2), target_outputs)
    accuracy = tf.reduce_mean(tf.cast(correct_pred, tf.float32))
    
    

# Start training
with tf.Session() as sess:

    # Run the initializer
    sess.run(tf.global_variables_initializer())

    for step in range(1, training_steps + 1):
        batch_source_input = source_input_idx
        batch_target_input = target_input_idx
        batch_target_output = target_output_idx
        
        # Run optimization op (backprop)
        sess.run(optimizer, feed_dict={source_inputs: source_input_one_hot, 
                                       target_inputs: target_input_one_hot,
                                       target_outputs: target_output_idx})
        
        if step % display_step == 0 or step == 1:
            # Calculate batch accuracy & loss
            outputs, acc, loss = sess.run([decoder_predict, accuracy, cost], 
                                              feed_dict={source_inputs: source_input_one_hot, 
                                                         target_inputs: target_input_one_hot,
                                                         target_outputs: target_output_idx})
            
            print("Step " + str(step * batch_size) + ", Minibatch Loss= " +                   "{:.6f}".format(loss) + ", Training Accuracy= " +                   "{:.5f}".format(acc))
            
        if acc >= 1:
            for sentence in outputs:
                sentence = [target_vocab[word_idx] for word_idx in sentence]
                print("           -> ", sentence)
                
            break;

    print("Optimization Finished!")
    print("Testing Accuracy:", sess.run(accuracy, feed_dict={source_inputs: source_input_one_hot, 
                                                             target_inputs: target_input_one_hot,
                                                             target_outputs: target_output_idx}))


# In[ ]:



