from __future__ import print_function

from pdb import set_trace as st

from glob import glob
import itertools
import os.path
import re
import tarfile
import time

import numpy as np
import matplotlib.pyplot as plt
from matplotlib import rcParams

from sklearn.externals.six.moves import html_parser
from sklearn.externals.six.moves.urllib.request import urlretrieve
from sklearn.datasets import get_data_home
from sklearn.feature_extraction.text import HashingVectorizer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier
from sklearn.linear_model import PassiveAggressiveClassifier
from sklearn.linear_model import Perceptron
from sklearn.naive_bayes import MultinomialNB
from sklearn.svm import SVC

import csv
import argparse
import os
from Wisse.wisse import *
#from Wisse.wisse import streamer

# parser = argparse.ArgumentParser(description="""...""")
#
# parser.add_argument("--idfmodel", help = """Input file containing IDF
#                                     pre-trained weights. If not provided,
#                                     all word vector weights will be set to
#                                     1.0. If 'local' tf-idf weights will be
#                                     computed locally from the input file
#                                     (pickled sklearn object).""",
#                                     default = None)
# parser.add_argument("--embedmodel", help = """Input file containing word
#                                         embeddings model (binary and text
#                                         are allowed).""", required = True)
#
# parser.add_argument("--localw", help = """TFIDF word vector weights
#                                 computed locally from the input file of
#                                 sentences {freq, binary, sublinear}
#                                 (default='none').""", default = "none")
#
# parser.add_argument("--format", help = """The format of the embedding model
#                                  file: {binary, text, wisse}.
#                                 default = 'binary'""", default = "binary")
# args = parser.parse_args()

def rm_zeros(X_train, y_train):
    zs = [i for i, v in enumerate(X_train) if not v.any()]
    if zs != []:
        return np.delete(X_train, zs, axis=0), np.delete(y_train, zs, axis=0)
    else:
        return X_train, y_train

localw = "bin"
stop = False

embedmodel = "../data/fastText/fstx_50d_indexed/"
#embedmodel = "../data/dependency_word2vec/indexed_d2v_En_300d"

TFIDFvectorizer = TfidfVectorizer(min_df=1,
                encoding="latin-1",
                decode_error="replace",
                lowercase=True,
                binary=True if localw.startswith("bin") else False,
                sublinear_tf=True if localw.startswith("subl") else False,
                stop_words="english" if stop else None)

with open("data/agr_en_train.csv") as r:
    TFIDFvectorizer.fit([x['body'] for x in csv.DictReader(r, 
                                        fieldnames=('title', 'body','topics'))])

embeddings = vector_space(embedmodel, sparse=False)

f0 = open("data/agr_en_train.csv")
stream_train = csv.DictReader(f0, fieldnames=('title', 'body', 'topics'))

f1 = open("data/agr_en_dev.csv")
stream_dev = csv.DictReader(f1, fieldnames=('title', 'body', 'topics'))

vectorizer = wisse(embeddings=embeddings, vectorizer=TFIDFvectorizer, 
                                                 tf_tfidf=True, combiner='sum')
all_classes = np.array([0, 1])
positive_class = 'CAG'

partial_fit_classifiers = {
    'SGD': SGDClassifier(),
    'Perceptron': Perceptron(),
#    'Support-Vector-Machine': SVC(C=50.0),
#    'NB Multinomial': MultinomialNB(alpha=0.01),
    'Passive-Aggressive': PassiveAggressiveClassifier(),
}


def get_minibatch(doc_iter, size, pos_class=positive_class):
    """Extract a minibatch of examples, return a tuple X_text, y.
    Note: size is before excluding invalid docs with no topics assigned.
    """
    data = [(u'{title}\n\n{body}'.format(**doc), pos_class in doc['topics'])
            for doc in itertools.islice(doc_iter, size) if doc['topics']]
    if not len(data):
        return np.asarray([], dtype=int), np.asarray([], dtype=int)
    X_text, y = zip(*data)
    return X_text, np.asarray(y, dtype=int)


def iter_minibatches(doc_iter, minibatch_size):
    """Generator of minibatches."""
    X_text, y = get_minibatch(doc_iter, minibatch_size)
    while len(X_text):
        yield X_text, y
        X_text, y = get_minibatch(doc_iter, minibatch_size)


test_stats = {'n_test': 0, 'n_test_pos': 0}
n_test_documents =  4118
tick = time.time()
X_test_text, y_test = get_minibatch(stream_dev, n_test_documents)

parsing_time = time.time() - tick
tick = time.time()
X_test = vectorizer.transform(X_test_text)
X_test, y_test = rm_zeros(X_test, y_test)
vectorizing_time = time.time() - tick
test_stats['n_test'] += len(y_test)
test_stats['n_test_pos'] += sum(y_test)
print("Test set is %d documents (%d positive)" % (len(y_test), sum(y_test)))

def progress(cls_name, stats):
    """Report progress information, return a string."""
    duration = time.time() - stats['t0']
    s = "%20s classifier : \t" % cls_name
    s += "%(n_train)6d train docs (%(n_train_pos)6d positive) " % stats
    s += "%(n_test)6d test docs (%(n_test_pos)6d positive) " % test_stats
    s += "accuracy: %(accuracy).3f " % stats
    s += "in %.2fs (%5d docs/s)" % (duration, stats['n_train'] / duration)
    return s

cls_stats = {}

for cls_name in partial_fit_classifiers:
    stats = {'n_train': 0, 'n_train_pos': 0,
             'accuracy': 0.0, 'accuracy_history': [(0, 0)], 't0': time.time(),
             'runtime_history': [(0, 0)], 'total_fit_time': 0.0}
    cls_stats[cls_name] = stats

#get_minibatch(data_stream, n_test_documents)

minibatch_size = 50

minibatch_iterators = iter_minibatches(stream_train, minibatch_size)
total_vect_time = 0.0


for i, (X_train_text, y_train) in enumerate(minibatch_iterators):

    tick = time.time()
    X_train = vectorizer.transform(X_train_text)
    total_vect_time += time.time() - tick

    for cls_name, cls in partial_fit_classifiers.items():
        tick = time.time()
        X_train, y_train = rm_zeros(X_train, y_train)
        cls.partial_fit(X_train, y_train, classes=all_classes)


        cls_stats[cls_name]['total_fit_time'] += time.time() - tick
        cls_stats[cls_name]['n_train'] += X_train.shape[0]
        cls_stats[cls_name]['n_train_pos'] += sum(y_train)
        tick = time.time()
        cls_stats[cls_name]['accuracy'] = cls.score(X_test, y_test)
        cls_stats[cls_name]['prediction_time'] = time.time() - tick
        acc_history = (cls_stats[cls_name]['accuracy'],
                       cls_stats[cls_name]['n_train'])
        cls_stats[cls_name]['accuracy_history'].append(acc_history)
        run_history = (cls_stats[cls_name]['accuracy'],
                       total_vect_time + cls_stats[cls_name]['total_fit_time'])
        cls_stats[cls_name]['runtime_history'].append(run_history)

        if i % 3 == 0:
            print(progress(cls_name, cls_stats[cls_name]))
    if i % 3 == 0:
        print('\n')


###############################################################################
# Plot results
# ------------


def plot_accuracy(x, y, x_legend):
    """Plot accuracy as a function of x."""
    x = np.array(x)
    y = np.array(y)
    plt.title('Classification accuracy as a function of %s' % x_legend)
    plt.xlabel('%s' % x_legend)
    plt.ylabel('Accuracy')
    plt.grid(True)
    plt.plot(x, y)


rcParams['legend.fontsize'] = 10
cls_names = list(sorted(cls_stats.keys()))

# Plot accuracy evolution
plt.figure()
for _, stats in sorted(cls_stats.items()):
    # Plot accuracy evolution with #examples
    accuracy, n_examples = zip(*stats['accuracy_history'])
    plot_accuracy(n_examples, accuracy, "training examples (#)")
    ax = plt.gca()
    ax.set_ylim((0.6, 1))
plt.legend(cls_names, loc='best')

plt.figure()
for _, stats in sorted(cls_stats.items()):
    # Plot accuracy evolution with runtime
    accuracy, runtime = zip(*stats['runtime_history'])
    plot_accuracy(runtime, accuracy, 'runtime (s)')
    ax = plt.gca()
    ax.set_ylim((0.6, 1))
plt.legend(cls_names, loc='best')

# Plot fitting times
plt.figure()
fig = plt.gcf()
cls_runtime = []
for cls_name, stats in sorted(cls_stats.items()):
    cls_runtime.append(stats['total_fit_time'])

cls_runtime.append(total_vect_time)
cls_names.append('Vectorization')
bar_colors = ['b', 'g', 'r', 'c', 'm', 'y']

ax = plt.subplot(111)
rectangles = plt.bar(range(len(cls_names)), cls_runtime, width=0.5,
                     color=bar_colors)

ax.set_xticks(np.linspace(0.25, len(cls_names) - 0.75, len(cls_names)))
ax.set_xticklabels(cls_names, fontsize=10)
ymax = max(cls_runtime) * 1.2
ax.set_ylim((0, ymax))
ax.set_ylabel('runtime (s)')
ax.set_title('Training Times')


def autolabel(rectangles):
    """attach some text vi autolabel on rectangles."""
    for rect in rectangles:
        height = rect.get_height()
        ax.text(rect.get_x() + rect.get_width() / 2.,
                1.05 * height, '%.4f' % height,
                ha='center', va='bottom')

autolabel(rectangles)
plt.show()

# Plot prediction times
plt.figure()
cls_runtime = []
cls_names = list(sorted(cls_stats.keys()))
for cls_name, stats in sorted(cls_stats.items()):
    cls_runtime.append(stats['prediction_time'])
cls_runtime.append(parsing_time)
cls_names.append('Read/Parse\n+Feat.Extr.')
cls_runtime.append(vectorizing_time)
cls_names.append('Hashing\n+Vect.')

ax = plt.subplot(111)
rectangles = plt.bar(range(len(cls_names)), cls_runtime, width=0.5,
                     color=bar_colors)

ax.set_xticks(np.linspace(0.25, len(cls_names) - 0.75, len(cls_names)))
ax.set_xticklabels(cls_names, fontsize=8)
plt.setp(plt.xticks()[1], rotation=30)
ymax = max(cls_runtime) * 1.2
ax.set_ylim((0, ymax))
ax.set_ylabel('runtime (s)')
ax.set_title('Prediction Times (%d instances)' % n_test_documents)
autolabel(rectangles)
plt.show()
