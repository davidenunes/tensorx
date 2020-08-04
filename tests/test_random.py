import os

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

import unittest
import tensorx as tx
import tensorflow as tf
import numpy as np


class MyTestCase(unittest.TestCase):
    def assertArrayEqual(self, actual, desired, verbose=True):
        if isinstance(actual, tx.Layer):
            actual = actual.tensor()
        if isinstance(desired, tx.Layer):
            desired = desired.tensor()

        self.assertTrue(np.array_equal(actual, desired))

    def assertArrayNotEqual(self, actual, desired):
        if isinstance(actual, tx.Layer):
            actual = actual.tensor()
        if isinstance(desired, tx.Layer):
            desired = desired.tensor()

        self.assertFalse(np.array_equal(actual, desired))

    def test_gumbel_sample(self):
        shape = [4, 10]
        logits = tf.random.uniform(shape)
        sample = tx.gumbel_top(logits, 2)
        all_unique = tf.map_fn(lambda x: tf.equal(tf.unique(x)[0].shape[-1], 2), sample, dtype=tf.bool)
        all_unique = tf.reduce_all(all_unique, axis=0)
        self.assertTrue(all_unique)
        self.assertEqual(sample.shape, [4, 2])


if __name__ == '__main__':
    unittest.main()
