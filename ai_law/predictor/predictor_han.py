"""
预测han在大数据上全数据集的结果
"""
import tensorflow as tf
import numpy as np
from .HAN_model import HierarchicalAttention
from .data_util_test import token_string_as_list,imprisonment_mean,imprisonment_std,UNK_ID,load_word_vocab,load_label_dict_accu,load_label_dict_article,pad_truncate_list
import os
from pyltp import NamedEntityRecognizer
from pyltp import SentenceSplitter
from pyltp import Segmentor
from pyltp import Postagger
import os
os.environ["TF_CPP_MIN_LOG_LEVEL"] = '2'

class Predictor(object):
    def __init__(self):
        """
        init method required. set batch_size, and load some resources.
        """
        self.batch_size = 256


        FLAGS = tf.app.flags.FLAGS
        tf.app.flags.DEFINE_string("ckpt_dir", "predictor/checkpoint/", "checkpoint location for the model")
        tf.app.flags.DEFINE_string("ckpt_dir_accu","./all_data/han/checkpoint_accu/","checkpoint location for the model") 
        tf.app.flags.DEFINE_string("ckpt_dir_law","./all_data/han/checkpoint_law/","checkpoint location for the model") 
        tf.app.flags.DEFINE_string("ckpt_dir_imprision","./all_data/han/checkpoint_imprision/","checkpoint location for the model") 

        tf.app.flags.DEFINE_string("vocab_word_path", "predictor/word_freq.txt", "path of word vocabulary.")
        tf.app.flags.DEFINE_string("accusation_label_path", "predictor/accu.txt", "path of accusation labels.")
        tf.app.flags.DEFINE_string("article_label_path", "predictor/law.txt", "path of law labels.")
        tf.app.flags.DEFINE_string("stopwords_file", "predictor/stopword.txt", "path of stopword")

        tf.app.flags.DEFINE_float("learning_rate", 0.001, "learning rate")
        tf.app.flags.DEFINE_integer("decay_steps", 1000,"how many steps before decay learning rate.")
        tf.app.flags.DEFINE_float("decay_rate", 1.0, "Rate of decay for learning rate.")
        tf.app.flags.DEFINE_integer("sentence_len", 400, "max sentence length")
        tf.app.flags.DEFINE_integer("num_sentences", 16, "number of sentences")
        tf.app.flags.DEFINE_integer("embed_size", 300, "embedding size") #64
        tf.app.flags.DEFINE_integer("hidden_size", 256, "hidden size") #128
        tf.app.flags.DEFINE_integer("num_filters", 128, "number of filter for a filter map used in CNN.") #128

        tf.app.flags.DEFINE_integer("embed_size_dpcnn", 64, "embedding size")
        tf.app.flags.DEFINE_integer("hidden_size_dpcnn", 128, "hidden size")
        #tf.app.flags.DEFINE_integer("num_filters_big", 128, "number of filter for a filter map used in CNN.")
        tf.app.flags.DEFINE_string("model_dpcnn", "dp_cnn", "name of model:han,c_gru,c_gru2,gru,text_cnn")

        tf.app.flags.DEFINE_string("ckpt_dir_dpcnn", "./checkpoint_dpcnn_big/checkpoint/", "checkpoint location for the model")


        tf.app.flags.DEFINE_boolean("is_training", False, "is traning.true:tranining,false:testing/inference")
        tf.app.flags.DEFINE_string("model", "han", "name of model:han,c_gru,c_gru2,gru,text_cnn")
        #tf.app.flags.DEFINE_boolean("is_training_flag", False, "is traning.true:tranining,false:testing/inference")
        tf.app.flags.DEFINE_string('cws_model_path','predictor/cws.model','cws.model path')
        tf.app.flags.DEFINE_string('pos_model_path','predictor/pos.model','pos.model path')
        tf.app.flags.DEFINE_string('ner_model_path','predictor/ner.model','ner.model path')
        tf.app.flags.DEFINE_string('gpu','1','help to select gpu divice')
        os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
        os.environ["CUDA_VISIBLE_DEVICES"] = FLAGS.gpu
        segm = Segmentor()
        segm.load(FLAGS.cws_model_path) # ltp 模型
        post = Postagger()
        post.load(FLAGS.pos_model_path)
        recognizer = NamedEntityRecognizer()
        recognizer.load(FLAGS.ner_model_path)
        self.ltp_model = [segm, post, recognizer]


        filter_sizes = [2,3,4,5]#,6,7,8]#[2,3,4,5]#[6, 7, 8, 9, 10]  # [30,40,50] #8
        #filter_sizes_big= [2,3,4,5]#,6,7,8]#[2,3,4,5]#[6, 7, 8, 9, 10]  # [30,40,50] #8

        stride_length = 1

        #1.load label dict, restore model from checkpoint
        # 1.load label dict
        self.vocab_word2index=load_word_vocab(FLAGS.vocab_word_path)
        accusation_label2index=load_label_dict_accu(FLAGS.accusation_label_path)
        articles_label2index=load_label_dict_article(FLAGS.article_label_path)

        deathpenalty_label2index = {True: 1, False: 0}
        lifeimprisonment_label2index = {True: 1, False: 0}
        vocab_size = len(self.vocab_word2index);
        accusation_num_classes = len(accusation_label2index);
        article_num_classes = len(articles_label2index)
        deathpenalty_num_classes = len(deathpenalty_label2index);
        lifeimprisonment_num_classes = len(lifeimprisonment_label2index)

        # 2.restore checkpoint
        config = tf.ConfigProto()
        config.gpu_options.allow_growth = True

        graph = tf.Graph().as_default()
        with graph:
            self.model = HierarchicalAttention(accusation_num_classes, article_num_classes, deathpenalty_num_classes,lifeimprisonment_num_classes, FLAGS.learning_rate, self.batch_size,FLAGS.decay_steps, FLAGS.decay_rate, FLAGS.sentence_len, FLAGS.num_sentences,vocab_size, FLAGS.embed_size, FLAGS.hidden_size
                                    ,num_filters = FLAGS.num_filters, model = FLAGS.model, filter_sizes = filter_sizes, stride_length = stride_length)
            saver = tf.train.Saver()
            sess = tf.Session(config=config)
            saver.restore(sess, tf.train.latest_checkpoint(FLAGS.ckpt_dir_accu))
            self.sess_accu = sess

            saver_law = tf.train.Saver()
            sess_law = tf.Session(config=config)
            saver_law.restore(sess_law, tf.train.latest_checkpoint(FLAGS.ckpt_dir_law))
            self.sess_law = sess_law

        self.FLAGS=FLAGS

    def predict_with_model_batch(self,contents):
        """
        predict result use model
        :param contents:  a list. each element is a string,which represent of fact of law case.
        :return: a dict

        """
        model=self.model
        model_dpcnn=self.model
        input_X=[]
        #1.get fact, 1)tokenize,2)word to index, 3)pad &truncate
        length_contents=len(contents)
        #################################################
        contents_padded=[]
    #if length_contents<self.batch_size:
        for i in range(self.batch_size):
            if i<length_contents:
                contents_padded.append(contents[i])
            else:
                #print(str(i),".going to padd")
                contents_padded.append(contents[0]) #pad the list to batch_size,
        #################################################

        for i,fact in enumerate(contents_padded):
            input_list = token_string_as_list(fact, self.ltp_model)  # tokenize
            x = [self.vocab_word2index.get(x, UNK_ID) for x in input_list]  # transform input to index
            x = pad_truncate_list(x, self.FLAGS.sentence_len, value=0.,truncating='pre')  # padding to max length.remove sequence that longer than max length from beginning.
            input_X.append(x)
        #2.feed data and get logit
        feed_dict = {model.input_x: input_X,model.dropout_keep_prob: 1.0,model.is_training_flag:False}
        feed_dict_big = {model_dpcnn.input_x: input_X,model_dpcnn.dropout_keep_prob: 1.0,model_dpcnn.is_training_flag:False}

        logits_accusations,_,logits_deathpenaltys,logits_lifeimprisonments,logits_imprisonments= self.sess_accu.run([model.logits_accusation,model.logits_article,model.logits_deathpenalty,model.logits_lifeimprisonment,model.logits_imprisonment],feed_dict)
        _,logits_articles,_,_,_= self.sess_law.run([model.logits_accusation,model.logits_article,model.logits_deathpenalty,model.logits_lifeimprisonment,model.logits_imprisonment],feed_dict)
        # logits_accusations_big,logits_articles_big,logits_deathpenaltys_big,logits_lifeimprisonments_big,logits_imprisonments_big= self.sess_big.run([model_dpcnn.logits_accusation,model_dpcnn.logits_article,model_dpcnn.logits_deathpenalty,model_dpcnn.logits_lifeimprisonment,model_dpcnn.logits_imprisonment],feed_dict_big)

        #3.get label_index
        result_list=[]
        for i in range(length_contents):
            #add logits

            logits_accusation=logits_accusations[i] # +logits_accusations_big[i] #ADD #模型融合
            accusations_predicted= [j+1 for j in range(len(logits_accusation)) if logits_accusation[j]>=0.5]  #TODO ADD ONE e.g.[2,12,13,10]
            if len(accusations_predicted)<1:
                accusations_predicted=[np.argmax(logits_accusation)+1] #TODO ADD ONE
            logits_article=logits_articles[i] #+logits_articles_big[i] #ADD
            articles_predicted= [j+1 for j in range(len(logits_article)) if logits_article[j]>=0.5]  ##TODO ADD ONE e.g.[2,12,13,10]
            if len(articles_predicted)<1:
                articles_predicted=[np.argmax(logits_article)+1] #TODO ADD ONE
            deathpenalty_predicted=np.argmax(logits_deathpenaltys[i])#+logits_deathpenaltys_big[i]) #0 or 1
            lifeimprisonment_predicted=np.argmax(logits_lifeimprisonments[i])#+logits_lifeimprisonments_big[i]) #0 or 1
            imprisonment_predicted=int(round((logits_imprisonments[i])))
            #+logits_imprisonments_big[i])/2.0)) #*imprisonment_std)
            imprisonment=0
            if deathpenalty_predicted==1:
                imprisonment=-2
            elif lifeimprisonment_predicted==1:
                imprisonment=-1
            else:
                imprisonment=imprisonment_predicted
            dictt={}
            dictt['accusation']=accusations_predicted
            dictt['articles'] =articles_predicted
            dictt['imprisonment'] =imprisonment
            result_list.append(dictt)

        #4.return
        return result_list


    def predict(self, contents): #get facts, use model to make a prediction.
        """
        standard predict method required.
        :param content:  a list. each element is a string,which represent of fact of law case.
        :return: a dict
        """
        result_list=self.predict_with_model_batch(contents)
        return result_list
