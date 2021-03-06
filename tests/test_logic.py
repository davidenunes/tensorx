import os

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

import tensorflow as tf
import tensorx as tx


def test_tensor_equal():
    t1 = tf.random.uniform([2, 2], dtype=tf.float32)
    t2 = tf.ones_like(t1)
    t3 = tf.random.uniform([3, 2], dtype=tf.float32)

    assert tx.tensor_equal(t1, t1)
    assert not tx.tensor_equal(t1, t2)
    assert not tx.tensor_equal(t1, t3)

    idx = tx.gumbel_top(tf.random.uniform([8, 8]), 2)
    idx = tx.matrix_indices(idx)
    sp1 = tf.SparseTensor(idx, values=tf.random.uniform([tf.shape(idx)[0]]), dense_shape=[8, 8])
    sp2 = tx.sparse_ones(idx, dense_shape=[8, 8])

    assert tx.tensor_equal(sp1, sp1)
    assert not tx.tensor_equal(sp1, sp2)


def test_shape_equal():
    t1 = tf.random.uniform([2, 2], dtype=tf.float32)
    t2 = tf.random.uniform([2, 3], dtype=tf.float32)

    assert tx.same_shape(t1, t1)
    assert not tx.same_shape(t1, t2)


def test_tensor_close():
    t1 = tf.ones([2], dtype=tf.float32)
    t2 = tf.constant([1., 1. + 1e-5])

    assert not tx.tensor_all_close(t1, t2)
    assert tx.tensor_all_close(t1, t2, atol=1e-5)
    assert not tx.tensor_all_close(t1, t2, rtol=1e-5)
    assert tx.tensor_all_close(t1, t2, rtol=1e-4)
