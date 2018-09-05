import unittest
import tensorflow as tf
import numpy as np
from tensorx.layers import *
from tensorx.init import *

from tensorx.layers import layers_to_list
from tensorx.activation import *
from tensorx.transform import sparse_tensor_value_one_hot
from tensorx.train import Model, ModelRunner
import math
import os

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'


class TestLayers(unittest.TestCase):
    # setup and close TensorFlow sessions before and after the tests (so we can use tensor.eval())
    def reset(self):
        tf.reset_default_graph()
        self.ss.close()
        self.ss = tf.InteractiveSession()

    def setUp(self):
        self.ss = tf.InteractiveSession()

    def tearDown(self):
        self.ss.close()

    def test_compose(self):
        in1 = Input(1)
        in2 = TensorLayer([[1.]], 1)

        l1 = Linear(in1, 4)
        l2 = Activation(l1, relu)

        comp = Compose(l1, l2)
        comp2 = comp.reuse_with(in2)

        tf.global_variables_initializer().run()

        res1 = l2.tensor.eval({in1.placeholder: [[1.]]})
        res2 = comp.tensor.eval({in1.placeholder: [[1.]]})

        res3 = comp2.tensor.eval()

        self.assertTrue(np.array_equal(res1, res2))
        self.assertTrue(np.array_equal(res1, res3))

    def test_fn_compose(self):
        in1 = Input(1)
        in2 = TensorLayer([[1.]], 1)

        l1 = Linear(in1, 4)
        l2 = Activation(l1, relu)

        comp = Compose(l1, l2)
        comp2 = comp.reuse_with(in2)

        fn1 = Fn(in1, 4, fn=relu, share_vars_with=l1)
        fn2 = fn1.reuse_with(in2, name="fn2")

        tf.global_variables_initializer().run()

        feed = {in1.placeholder: [[1.]]}
        res1 = l2.tensor.eval(feed)
        res2 = comp.tensor.eval(feed)
        res3 = comp2.tensor.eval()

        self.assertTrue(np.array_equal(res1, res2))
        self.assertTrue(np.array_equal(res1, res3))

        res_fn1 = fn1.tensor.eval(feed)
        res_fn2 = fn2.tensor.eval()

        self.assertTrue(np.array_equal(res_fn1, res_fn2))

        # m = Model(in1, fn1)
        # r = ModelRunner(m)
        # r.log_graph("/tmp")

    def test_compose_merge(self):
        in1 = Input(1)
        in2 = TensorLayer([[1.]], 1)
        in3 = Input(1)

        a1 = Add(in1, in2)
        l1 = Linear(a1, 4)

        comp = Compose(a1, l1)
        comp2 = comp.reuse_with(in1, in3)

        tf.global_variables_initializer().run()

        res1 = comp.tensor.eval({in1.placeholder: [[1.]]})
        res2 = comp2.tensor.eval({in1.placeholder: [[1.]], in3.placeholder: [[1.]]})

        self.assertTrue(np.array_equal(res1, res2))

    def test_highway(self):
        x = TensorLayer([[1., 1., 1., 1.]], 4)
        x2 = TensorLayer([[1., 1., 1., 1.]], 4)

        h = Fn(x, 4, fn=sigmoid)

        highway = Highway(x, h)

        with self.assertRaises(ValueError):
            Highway(x2, h)

        tf.global_variables_initializer().run()

        self.assertSequenceEqual(x.shape, highway.shape)

    def test_residual(self):
        x = TensorLayer([[1., 1., 1., 1.]], 4)
        x2 = TensorLayer([[1., 1., 1., 1.]], 4)

        h = Fn(x, 4, fn=sigmoid)
        h2 = Fn(x, 2, fn=sigmoid)

        residual = Residual(x, h)
        residual_2 = Residual(x, h2)

        with self.assertRaises(ValueError):
            Residual(x2, h)

        tf.global_variables_initializer().run()

        self.assertSequenceEqual(h.shape, residual.shape)
        self.assertTrue(residual.projection == residual.input_layers[0])
        self.assertIsInstance(residual.projection, TensorLayer)
        self.assertEqual(len(residual.variables), 0)

        self.assertTrue(residual_2.projection != residual.input_layers[0])
        self.assertIsInstance(residual_2.projection, Linear)
        self.assertEqual(len(residual_2.variables), 1)

        # m = Model(x, residual_2)
        # r = ModelRunner(m)
        # r.log_graph("/tmp")

        self.reset()

    def test_conv1d(self):
        num_filters = 2
        input_dim = 4
        seq_size = 3
        batch_size = 2
        filter_size = 2

        filter_shape = [filter_size, input_dim, num_filters]

        x = tf.ones([batch_size, seq_size, input_dim])
        x_layer = TensorLayer(x, input_dim)

        filters = tf.ones(filter_shape)
        conv_layer = Conv1D(x_layer, num_filters, filter_size, shared_filters=filters)
        conv = tf.nn.conv1d(x, filters, stride=1, padding="SAME", use_cudnn_on_gpu=True, data_format="NWC")

        tf.global_variables_initializer().run()

        self.assertSequenceEqual(conv_layer.filter_shape, (filter_size, input_dim, num_filters))
        self.assertSequenceEqual(conv_layer.shape, (batch_size, seq_size, num_filters))
        self.assertTrue(np.array_equal(conv.eval(), conv_layer.tensor.eval()))

        self.reset()

    def test_causal_conv(self):
        num_filters = 1
        input_dim = 1
        seq_size = 6
        batch_size = 2
        filter_size = 3
        dilation_rate = 2

        filter_shape = [filter_size, input_dim, num_filters]

        x = tf.ones([batch_size, seq_size, input_dim])

        x_layer = TensorLayer(x, input_dim)

        filter = tf.ones(filter_shape)
        conv_layer = CausalConv(x_layer, num_filters, filter_size,
                                shared_filters=filter,
                                dilation_rate=dilation_rate)

        left_pad = dilation_rate * (filter_size - 1)
        padding = [[0, 0], [left_pad, 0], [0, 0]]
        x = tf.pad(x, padding)

        conv = tf.nn.convolution(input=x,
                                 filter=filter,
                                 dilation_rate=(dilation_rate,),
                                 strides=(1,),
                                 padding="VALID",
                                 data_format="NWC")

        tf.global_variables_initializer().run()

        self.assertSequenceEqual(conv_layer.filter_shape, (filter_size, input_dim, num_filters))
        self.assertSequenceEqual(conv_layer.shape, (batch_size, seq_size, num_filters))
        self.assertTrue(np.array_equal(conv.eval(), conv_layer.tensor.eval()))

        self.reset()

    def test_conv2d(self):
        # simple dummy data with 10 examples of mnist digit and class data
        # digits are 28x28 data
        local_path = (os.path.dirname(__file__))

        x = np.load(local_path + "/data/mnist_10x.npy")
        y = np.load(local_path + "/data/mnist_10y.npy")

        # we only have one channel so we need to reshape the data
        x = tf.reshape(x, shape=[-1, 28, 28, 1])
        self.assertTrue(np.array_equal(tf.shape(x).eval(), (10, 28, 28, 1)))

        x_layer = TensorLayer(x, 1)
        # f = Flatten(x_layer)

        conv = Conv2D(layer=x_layer,
                      n_units=2,
                      filter_size=5,
                      stride=(1, 1),
                      dilation_rate=(1, 1),
                      same_padding=True,
                      bias=True)

        self.reset()

    def test_qrnn(self):
        num_filters = 2
        input_dim = 1000
        seq_size = 2
        batch_size = 2
        filter_size = 2
        dilation_rate = 1

        x = tf.ones([batch_size, seq_size, input_dim])
        x_layer = TensorLayer(x, input_dim)
        qrnn = QRNN(layer=x_layer,
                    n_units=num_filters,
                    filter_size=filter_size,
                    dilation_rate=dilation_rate,
                    input_gate=True)

        qrnn2 = qrnn.reuse_with(x_layer)
        qrnn_zoneout = qrnn.reuse_with(x_layer, zoneout=True)

        tf.global_variables_initializer().run()

        res1 = qrnn.tensor.eval()
        res2 = qrnn2.tensor.eval()
        res3 = qrnn_zoneout.tensor.eval()

        self.assertSequenceEqual(np.shape(res1), (batch_size, seq_size, num_filters))
        self.assertSequenceEqual(np.shape(res3), (batch_size, seq_size, num_filters))

        self.assertTrue(np.array_equal(res1, res2))
        # this might fail, zoneout is stochastic
        # self.assertFalse(np.array_equal(res1, res3))

    def test_bias_reuse(self):
        in1 = TensorLayer([[1.]], 1)
        in2 = TensorLayer([[1.]], 1)

        b1 = Bias(in1)
        b2 = b1.reuse_with(in2)

        self.assertListEqual(b1.variable_names, b2.variable_names)

    def test_reusable_layers(self):
        in1 = TensorLayer([[1.]], 1)
        in2 = TensorLayer([[1.]], 1)
        in3 = TensorLayer([[-1.]], 1)

        layer1 = Linear(in1, 2)

        layer2 = layer1.reuse_with(in2)
        layer3 = layer2.reuse_with(in3)

        self.assertListEqual(layer1.variable_names, layer2.variable_names)
        self.assertListEqual(layer2.variable_names, layer3.variable_names)

        tf.global_variables_initializer().run()

        result1 = layer1.tensor.eval()
        result2 = layer2.tensor.eval()
        result3 = layer3.tensor.eval()

        np.testing.assert_array_equal(result1, result2)

        expected = result2 * -1
        np.testing.assert_array_equal(expected, result3)

    def test_input(self):
        """ Test Input layer - creates a TensorFlow Placeholder

        this corresponds to an input layer with n_units in the input
        and a shape corresponding to [batch_size, n_units]
        """
        in_layer = Input(n_units=10)
        self.assertIsInstance(in_layer.tensor, tf.Tensor)

        ones = np.ones(shape=(2, 10))
        result = self.ss.run(in_layer.tensor, feed_dict={in_layer.tensor: ones})
        np.testing.assert_array_equal(ones, result)

        variables = in_layer.variable_names
        self.assertEqual(len(variables), 0)

        ones_wrong_shape = np.ones(shape=(2, 11))
        try:
            self.ss.run(in_layer.tensor, feed_dict={in_layer.tensor: ones_wrong_shape})
            self.fail("Should have raised an exception since shapes don't match")
        except ValueError:
            pass

    def test_flat_sparse_input(self):
        """ Create a Sparse Input by providing
        a n_active parameter
        """
        dim = 4
        index = [[0]]

        input_layer = Input(n_units=dim, n_active=1, dtype=tf.int64)
        self.assertEqual(input_layer.tensor.values.dtype, tf.int64)

        result = self.ss.run(input_layer.tensor, feed_dict={input_layer.placeholder: index})
        self.assertEqual(len(result.values), 1)

    def test_sparse_input(self):
        indices = [[0, 1], [1, 1]]
        values = [1, 1]
        dense_shape = [4, 4]
        sp_data = tf.SparseTensorValue(indices, values, dense_shape)

        sp_input = SparseInput(n_units=4)
        result = tf.sparse_tensor_to_dense(sp_input.tensor).eval({sp_input.placeholder: sp_data})

        np.testing.assert_array_equal(result[sp_data.indices], [1, 1])
        np.testing.assert_array_equal(result.shape, dense_shape)

    def test_tensor_input(self):
        indices = [[0, 1], [1, 1]]
        values = [1, 1]
        dense_shape = [4, 4]
        sp_data = tf.SparseTensorValue(indices, values, dense_shape)

        # test with sparse tensor value
        tensor_input = TensorLayer(tensor=sp_data, n_units=4)
        sparse_input = SparseInput(n_units=4)

        self.assertTrue(tensor_input.is_sparse())
        self.assertTrue(sparse_input.is_sparse())

        result_tensor = tf.sparse_tensor_to_dense(tensor_input.tensor).eval()
        result_sparse = tf.sparse_tensor_to_dense(sparse_input.tensor).eval({sparse_input.tensor: sp_data})

        np.testing.assert_array_equal(result_sparse, result_tensor)

        dense_input = TensorLayer(result_tensor, n_units=4)
        np.testing.assert_array_equal(dense_input.tensor.eval(), result_tensor)

        # np.testing.assert_array_equal(result_tensor[sp_data.indices], [1, 1])
        # np.testing.assert_array_equal(result.shape, dense_shape)

    def test_linear_equal_sparse_dense(self):
        index = 0
        dim = 10

        # x1 = dense input / x2 = sparse input / x3 = sparse input (explicit)
        x1 = Input(n_units=dim)
        x2 = Input(n_units=dim, n_active=1, dtype=tf.int64)
        x3 = SparseInput(10)

        # two layers with shared weights, one uses a sparse input layer, the other the dense one
        y1 = Linear(x1, 4, name="linear1")
        y2 = Linear(x2, 4, shared_weights=y1.weights, name="linear2")
        y3 = Linear(x3, 4, shared_weights=y1.weights, name="linear3")

        self.ss.run(tf.global_variables_initializer())

        # dummy input data
        input1 = np.zeros([1, dim])
        input1[0, index] = 1
        input2 = [[index]]
        input3 = sparse_tensor_value_one_hot(input2, [1, dim])
        self.assertIsInstance(input3, tf.SparseTensorValue)

        # one evaluation performs a embedding lookup and reduce sum, the other uses a matmul
        y1_output = y1.tensor.eval({x1.placeholder: input1})
        y2_output = y2.tensor.eval({x2.placeholder: input2})
        y3_output = y3.tensor.eval({x3.placeholder: input3})

        # the result should be the same
        np.testing.assert_array_equal(y1_output, y2_output)
        np.testing.assert_array_equal(y2_output, y3_output)

    def test_linear_variable_names(self):
        self.reset()

        inputs = TensorLayer([[1]], 1, dtype=tf.float32)
        layer = Linear(inputs, 10)
        layer2 = Linear(inputs, 10)
        layer_shared = Linear(inputs, 10, shared_weights=layer.weights)

        var_names = layer.variable_names
        var_names_2 = layer2.variable_names
        shared_names = layer_shared.variable_names

        self.assertEqual(var_names[0], shared_names[0])
        self.assertNotEqual(var_names_2[0], shared_names[0])

        self.assertNotEqual(var_names[1], var_names_2[1])
        self.assertNotEqual(var_names[1], shared_names[1])

        with tf.variable_scope("", reuse=True):
            weights1 = tf.get_variable("linear/w")
            weights2 = tf.get_variable(shared_names[0])

            self.assertIs(weights1, weights2)

    def test_linear_shared(self):
        in1 = TensorLayer([[-1.]], 1)
        in2 = TensorLayer([[2.]], 1)

        l1 = Linear(in1, 1, weight_init=ones_init())
        l2 = l1.reuse_with(in2, name="shared")
        l3 = Linear(in1, 1, weight_init=ones_init(), shared_weights=l1.weights, bias=True)
        l4 = l3.reuse_with(in2)

        self.ss.run(tf.global_variables_initializer())

        res1 = l1.tensor.eval()
        res2 = l2.tensor.eval()
        res3 = l3.tensor.eval()
        res4 = l4.tensor.eval()

        self.assertTrue(np.array_equal(res1, res3))
        self.assertTrue(np.array_equal(res2, res4))

        self.assertListEqual(l1.variable_names, l2.variable_names)

        self.assertFalse(l3.variable_names == l1.variable_names)
        self.assertListEqual(l3.variable_names, l4.variable_names)

    def test_to_sparse(self):
        index = 0
        dim = 10

        # dense input
        x1 = Input(n_units=dim)
        x2 = Input(n_units=dim, n_active=1, dtype=tf.int64)
        x3 = SparseInput(10)

        # dummy input data
        input1 = np.zeros([1, dim])
        input1[0, index] = 1
        input2 = [[index]]
        input3 = sparse_tensor_value_one_hot(input2, [1, dim])

        s1 = ToSparse(x1)
        s2 = ToSparse(x2)
        s3 = ToSparse(x3)

        y1_sp_tensor = self.ss.run(s1.tensor, {x1.placeholder: input1})

        self.assertEqual(len(y1_sp_tensor.values), 1)

        y2_sp_tensor = self.ss.run(s2.tensor, {x2.placeholder: input2})
        self.assertEqual(len(y1_sp_tensor.values), 1)
        np.testing.assert_array_equal(y1_sp_tensor.indices, y2_sp_tensor.indices)
        np.testing.assert_array_equal(y1_sp_tensor.values, y2_sp_tensor.values)

        y3_sp_tensor = self.ss.run(s3.tensor, {x3.placeholder: input3})
        self.assertEqual(len(y2_sp_tensor.values), 1)
        self.assertEqual(y2_sp_tensor.values, 1)
        np.testing.assert_array_equal(y1_sp_tensor.indices, y3_sp_tensor.indices)
        np.testing.assert_array_equal(y1_sp_tensor.values, y3_sp_tensor.values)

    def test_to_dense(self):
        dim = 10
        n_active = 1
        index = 0

        x1 = Input(n_units=dim, n_active=n_active, dtype=tf.int64)
        x2 = SparseInput(10)

        data1 = [[index]]
        data2 = sparse_tensor_value_one_hot(data1, [1, dim])

        expected = np.zeros([1, dim])
        expected[0, index] = 1

        to_dense1 = ToDense(x1)
        to_dense2 = ToDense(x2)

        result1 = to_dense1.tensor.eval({x1.placeholder: data1})
        result2 = to_dense2.tensor.eval({x2.placeholder: data2})

        np.testing.assert_array_equal(expected, result1)
        np.testing.assert_array_equal(expected, result2)

    def test_dropout_layer(self):
        dim = 100
        keep_prob = 0.5
        num_iter = 50

        dense_input = Input(dim)
        data = np.ones([1, dim], dtype=np.float32)
        dropout = Dropout(dense_input, keep_prob)

        # TEST DROPOUT WITH DENSE INPUTS
        final_count = 0
        for _ in range(0, num_iter):
            result = dropout.tensor.eval({dense_input.placeholder: data})
            final_count += np.count_nonzero(result)

            # test the scaling
            sorted_result = np.unique(np.sort(result))
            if len(sorted_result) > 1:
                np.testing.assert_allclose(1 / keep_prob, sorted_result[1])

        # Check that we are in the 10% error range
        expected_count = dim * keep_prob * num_iter
        rel_error = math.fabs(math.fabs(final_count - expected_count) / expected_count)
        self.assertLess(rel_error, 0.1)

        # TEST DROPOUT WITH keep_prob = 1
        drop_dense = Dropout(dense_input, keep_prob=1)
        result = drop_dense.tensor.eval({dense_input.placeholder: data})
        np.testing.assert_array_equal(result, data)

        # TEST FLAT INDEX SPARSE INPUT
        n_active = 2
        data = [list(range(0, n_active, 1))]
        flat_sparse = Input(dim, n_active)
        self.assertTrue(flat_sparse.is_sparse())

        dropout = Dropout(flat_sparse, keep_prob)
        self.assertTrue(dropout.is_sparse())

        result = self.ss.run(dropout.tensor, {flat_sparse.placeholder: data})
        np.testing.assert_allclose(1 / keep_prob, result.values)
        self.assertLessEqual(len(result.values), len(data[0]))

        # test for keep_prob == 1
        dropout = Dropout(flat_sparse, keep_prob=1)
        after_dropout = self.ss.run(dropout.tensor, {flat_sparse.placeholder: data})
        after_input = flat_sparse.tensor.eval({flat_sparse.placeholder: data})
        np.testing.assert_array_equal(after_input.indices, after_dropout.indices)

        # TEST DROPOUT ON SPARSE INPUT
        sparse_data = sparse_tensor_value_one_hot(data, [1, dim])
        sparse_input = SparseInput(dim)
        dropout = Dropout(sparse_input, keep_prob=keep_prob)

        # feed sparse tensor values with indices
        after_dropout = self.ss.run(dropout.tensor, {sparse_input.placeholder: sparse_data})
        np.testing.assert_allclose(1 / keep_prob, after_dropout.values)
        self.assertLessEqual(len(after_dropout.indices), len(sparse_data.indices))

        dropout = Dropout(sparse_input, keep_prob=1)
        before_dropout = self.ss.run(sparse_input.tensor, {sparse_input.placeholder: sparse_data})
        after_dropout = self.ss.run(dropout.tensor, {sparse_input.placeholder: sparse_data})
        np.testing.assert_array_equal(before_dropout.indices, after_dropout.indices)
        np.testing.assert_array_equal(before_dropout.values, after_dropout.values)

    def test_dropout_noise_mask(self):
        embed_dim = 4
        seq_size = 2
        input_dim = 1000

        tensor_input = TensorLayer(tf.constant([[0, 1], [0, 1]]), 2)

        lookup = Lookup(tensor_input, seq_size, lookup_shape=[input_dim, embed_dim], batch_padding=False)

        dropped = Dropout(lookup, keep_prob=0.5, noise_shape=[2, seq_size, embed_dim])

        var_init = tf.global_variables_initializer()

        with tf.Session() as sess:
            sess.run(var_init)

            w, d = sess.run([lookup.weights, dropped.tensor])

            print(w)
            print("=" * 10)
            print(d)

    def test_zoneout_layer(self):
        dim = 100
        batch_size = 1000
        keep_prob = 0.5

        current_data = np.full([batch_size, dim], fill_value=1.)
        previous_data = np.full([batch_size, dim], fill_value=-1.)

        current_layer = TensorLayer(tensor=current_data, n_units=dim)
        previous_layer = TensorLayer(tensor=previous_data, n_units=dim)

        zoneout = ZoneOut(current_layer, previous_layer, keep_prob=keep_prob)

        mean_sum = np.mean(np.sum(zoneout.tensor.eval(), axis=-1))
        self.assertAlmostEqual(mean_sum, 0., delta=1.0)

        # test keep_prob = 1
        keep_prob = 1.0

        current_data = np.full([batch_size, dim], fill_value=1.)
        previous_data = np.full([batch_size, dim], fill_value=-1.)

        current_layer = TensorLayer(tensor=current_data, n_units=dim)
        previous_layer = TensorLayer(tensor=previous_data, n_units=dim)

        zoneout = ZoneOut(current_layer, previous_layer, keep_prob=keep_prob)

        mean_sum = np.mean(np.sum(zoneout.tensor.eval(), axis=-1))
        self.assertEqual(mean_sum, dim)

        # test keep_prob = 0
        keep_prob = 0.0

        current_data = np.full([batch_size, dim], fill_value=1.)
        previous_data = np.full([batch_size, dim], fill_value=-1.)

        current_layer = TensorLayer(tensor=current_data, n_units=dim)
        previous_layer = TensorLayer(tensor=previous_data, n_units=dim)

        zoneout = ZoneOut(current_layer, previous_layer, keep_prob=keep_prob)

        mean_sum = np.mean(np.sum(zoneout.tensor.eval(), axis=-1))
        self.assertEqual(mean_sum, -dim)

        # test keep_prob = 0
        keep_prob = np.random.rand()

        current_data = np.full([batch_size, dim], fill_value=1.)
        previous_data = np.full([batch_size, dim], fill_value=-1.)

        current_layer = TensorLayer(tensor=current_data, n_units=dim)
        previous_layer = TensorLayer(tensor=previous_data, n_units=dim)

        zoneout = ZoneOut(current_layer, previous_layer, keep_prob=keep_prob)

        mean_sum = np.mean(np.sum(zoneout.tensor.eval(), axis=-1))
        expected = (2 * dim * keep_prob) - dim

        self.assertAlmostEqual(mean_sum, expected, delta=1.0)

    def test_gaussian_noise(self):
        dim = 1000
        # for sparse inputs
        n_active = 10

        dense_input = Input(dim)
        dense_data = np.ones([1, dim], dtype=np.float32)
        noise_layer = GaussianNoise(dense_input)

        # test that expected average tensor is approximately the same
        result = noise_layer.tensor.eval({dense_input.placeholder: dense_data})
        mean_result = np.mean(result)
        mean_data = np.mean(dense_data)
        self.assertAlmostEqual(mean_data, mean_result, delta=0.1)

        # sparse input with flat indices
        flat_indices = [list(range(0, n_active, 1))]
        flat_input = Input(dim, n_active, dtype=tf.int64)
        noise_layer = GaussianNoise(flat_input)
        result = noise_layer.tensor.eval({flat_input.placeholder: flat_indices})

        dense_input = np.zeros([1, dim])
        dense_input[0, flat_indices[0]] = 1
        mean_data = np.mean(dense_input)
        mean_result = np.mean(result)
        self.assertAlmostEqual(mean_data, mean_result, delta=0.1)

        sparse_input = SparseInput(dim)
        noise_layer = GaussianNoise(sparse_input)
        sparse_data = sparse_tensor_value_one_hot(flat_indices, [1, dim])
        result = noise_layer.tensor.eval({sparse_input.placeholder: sparse_data})
        mean_result = np.mean(result)
        self.assertAlmostEqual(mean_data, mean_result, delta=0.1)

    def test_sp_noise(self):
        # PARAMS
        noise_amount = 0.5
        batch_size = 4
        dim = 100

        dense_input = Input(dim)
        dense_data = np.zeros([batch_size, dim], dtype=np.float32)
        noise_layer = SaltPepperNoise(dense_input, noise_amount)
        result = noise_layer.tensor.eval({dense_input.placeholder: dense_data})
        mean_result = np.mean(result)
        self.assertEqual(mean_result, 0)

    def test_activation_with_params(self):
        inputs = Input(1)
        act = Activation(inputs, leaky_relu, alpha=0.)

        r0 = act.tensor.eval({inputs.tensor: [[-1]]})
        r1 = act.tensor.eval({inputs.tensor: [[1]]})
        r2 = act.tensor.eval({inputs.tensor: [[3]]})

        self.assertEqual(r0[0], 0)
        self.assertEqual(r1[0], 1)
        self.assertEqual(r2[0], 3)

    def test_layers_to_list(self):
        """ layers_to_list returns the layers without repetition using a breadth first search from the last layer
        and then reversing the layers found.
        """
        l11 = Input(1, name="in1")
        l12 = Input(1, name="in2")
        l121 = WrapLayer(l12, l12.n_units, wrap_fn=lambda x: tf.identity(x))
        l2 = Add(l11, l121)

        l3 = Linear(l2, 1)
        l4 = Add(l3, l12)

        l41 = Activation(l4, fn=sigmoid, name="act1")
        l42 = Activation(l4, fn=hard_sigmoid, name="act2")

        l5 = ToSparse(l41)

        outs = [l5, l42]
        layers = layers_to_list(outs, l3)
        # for layer in layers:
        #    print(layer)

        self.assertEqual(len(layers), 6)
        self.assertEqual(layers[0], l3)
        self.assertEqual(layers[-1], l5)
        self.assertIn(l12, layers)
        self.assertNotIn(l2, layers)
        self.assertNotIn(l11, layers)

    def test_wrap_layer(self):
        data = np.random.uniform(-1, 1, [1, 4])

        input_layer = Input(4)
        wrap_layer = WrapLayer(input_layer, 4, lambda layer: tf.multiply(layer, 2))
        self.assertIs(input_layer.placeholder, wrap_layer.placeholder)

        with tf.Session() as sess:
            t1 = sess.run(input_layer.tensor, feed_dict={input_layer.placeholder: data})
            t2 = sess.run(wrap_layer.tensor, feed_dict={wrap_layer.placeholder: data})

            np.testing.assert_array_almost_equal(t1 * 2, t2, decimal=6)

    def test_wrap_reuse(self):
        """

                     +---------------------------------------+
                     | +----------------------------+        |
                     | | +------------+             |        |
                     | | |            | WRAP        | WRAP   |
                     | | |   INPUT    |             |        |
            +--------------> LAYER    |             |        +------->
                     | | |            |             |        |
                     | | +------------+             |        |
                     | +----------------------------+        |
                     +---------------------------------------+

        """
        input1 = TensorLayer(np.array([1, 1, 1, 1]), 4)
        input2 = TensorLayer(np.array([0, 1, 0, 1]), 4)

        wrap1 = WrapLayer(input1, n_units=input1.n_units, wrap_fn=lambda x: tf.multiply(x, 2))
        wrap2 = WrapLayer(wrap1, n_units=wrap1.n_units, wrap_fn=lambda x: tf.multiply(x, 2))

        with self.assertRaises(AttributeError):
            wrap1.reuse_with(input2)
            # this will try to call reuse on wrap1 which will call reuse in TensorLayer
            wrap2.reuse_with(input2)

        """
        

                         +---------------------------------------+
                         | +----------------------------+        |
                         | | +------------+             |        |
                         | | |            | WRAP        | WRAP   |
                         | | | ACTIVATION |             |        |
           INPUT +--------------> LAYER   |             |        +------->
                         | | |            |             |        |
                         | | +------------+             |        |
                         | +----------------------------+        |
                         +---------------------------------------+

        """

        input1 = TensorLayer(np.array([1, 1, 1, 1]), 4)
        input1_act = Activation(input1, fn=lambda x: tf.identity(x))

        input2 = TensorLayer(np.array([0, 1, 0, 1]), 4)

        wrap1 = WrapLayer(input1_act, n_units=input1_act.n_units, wrap_fn=lambda x: tf.multiply(x, 2), attr_fwd="fn")
        wrap2 = WrapLayer(wrap1, n_units=wrap1.n_units, wrap_fn=lambda x: tf.multiply(x, 2))

        # this is ok because we're wrapping the activation
        wrap2_r1 = wrap2.reuse_with(input2)
        wrap2_r2 = wrap2_r1.reuse_with(input2)

        self.assertTrue(hasattr(wrap2_r2, "fn"))

        self.assertFalse(np.array_equal(sum(wrap2.eval()), sum(wrap2_r2.eval())))
        self.assertTrue(np.array_equal(sum(wrap2.eval()), sum(wrap2_r2.eval()) * 2))

    def test_lookup_sequence_dense(self):
        input_dim = 4
        embed_dim = 3
        seq_size = 2
        batch_size = 3

        inputs = Input(2, dtype=tf.int64)
        input_data = np.array([[2, 0], [1, 2]])

        tensor_input = TensorLayer(tf.constant([2]), 1)

        lookup = Lookup(inputs, seq_size, lookup_shape=[input_dim, embed_dim], batch_size=batch_size,
                        batch_padding=True)

        lookup_from_tensor = lookup.reuse_with(tensor_input)

        var_init = tf.global_variables_initializer()
        with tf.Session() as sess:
            sess.run(var_init)

            v1 = sess.run(lookup.tensor, {inputs.placeholder: input_data})
            v2 = sess.run(lookup_from_tensor.tensor)

            self.assertEqual(np.shape(v1), (batch_size, seq_size, embed_dim))
            self.assertEqual(np.shape(v2), (batch_size, seq_size, embed_dim))

    def test_lookup_sequence_sparse(self):
        input_dim = 10
        embed_dim = 3
        seq_size = 2
        batch_size = 3

        sparse_input = tf.SparseTensor([[0, 2], [1, 0], [2, 1]], [1, 1, 1], [3, input_dim])
        sparse_input_1d = tf.SparseTensor([[2], [0], [1]], [1, 1, 1], [input_dim])
        tensor_input = TensorLayer(sparse_input, input_dim)
        tensor_input_1d = TensorLayer(sparse_input_1d, input_dim)

        lookup = Lookup(tensor_input, seq_size, lookup_shape=[input_dim, embed_dim], batch_size=batch_size,
                        batch_padding=False)

        lookup_padding = Lookup(tensor_input, seq_size, lookup_shape=[input_dim, embed_dim], batch_size=batch_size,
                                batch_padding=True)

        lookup_1d = Lookup(tensor_input_1d, seq_size, lookup_shape=[input_dim, embed_dim], batch_size=batch_size,
                           batch_padding=True)

        var_init = tf.global_variables_initializer()
        with tf.Session() as sess:
            sess.run(var_init)

            result = sess.run(lookup.tensor)
            result_padding = sess.run(lookup_padding.tensor)
            result_1d = sess.run(lookup_1d.tensor)

            self.assertEqual(np.shape(result), (2, seq_size, embed_dim))
            self.assertEqual(np.shape(result_padding), (batch_size, seq_size, embed_dim))
            self.assertEqual(np.shape(result_1d), (batch_size, seq_size, embed_dim))

    def test_lookup_sparse_padding(self):
        input_dim = 6
        embed_dim = 3
        seq_size = 1

        sparse_input = tf.SparseTensor([[0, 1], [0, 3], [1, 0]], [1, 1, 1], [2, input_dim])
        sparse_input = TensorLayer(sparse_input, input_dim)

        lookup = Lookup(sparse_input,
                        seq_size=seq_size,
                        lookup_shape=[input_dim, embed_dim],
                        batch_size=None,
                        batch_padding=False)

        var_init = tf.global_variables_initializer()
        with tf.Session() as sess:
            sess.run(var_init)

            print(lookup.eval())

    def test_lookup_sequence_bias(self):
        vocab_size = 4
        n_features = 3
        seq_size = 2

        inputs = Input(seq_size, dtype=tf.int32)
        input_data = np.array([[2, 0], [1, 2], [0, 2]])
        lookup = Lookup(inputs, seq_size, lookup_shape=[vocab_size, n_features], bias=True)

        var_init = tf.global_variables_initializer()
        with tf.Session() as sess:
            sess.run(var_init)

            v1 = sess.run(lookup.tensor, {inputs.placeholder: input_data})

            self.assertEqual(np.shape(v1), (np.shape(input_data)[0], seq_size, n_features))

    def test_lookup_sequence_transform(self):
        vocab_size = 4
        embed_dim = 2
        seq_size = 2

        inputs = Input(seq_size, dtype=tf.int32)
        input_data = np.array([[2, 0], [1, 2], [0, 2]])
        lookup = Lookup(inputs, seq_size, lookup_shape=[vocab_size, embed_dim], bias=True)
        concat_lookup = lookup.as_concat()
        seq_lookup = lookup.as_seq()

        self.assertTrue(hasattr(lookup, "seq_size"))

        var_init = tf.global_variables_initializer()
        with tf.Session() as sess:
            sess.run(var_init)

            v1 = sess.run(lookup.tensor, {inputs.placeholder: input_data})
            v2 = sess.run(concat_lookup.tensor, {inputs.placeholder: input_data})
            v3 = sess.run(seq_lookup.tensor, {inputs.placeholder: input_data})

            self.assertEqual(np.shape(v1), (np.shape(input_data)[0], seq_size, embed_dim))
            self.assertEqual(np.shape(v2), (np.shape(input_data)[0], seq_size * embed_dim))

            self.assertEqual(np.shape(v3), (seq_size, np.shape(input_data)[0], embed_dim))
            self.assertTrue(np.array_equal(v1[:, 0], v3[0]))

    def test_gating(self):
        self.reset()

        vocab_size = 4
        n_features = 3
        seq_size = 2

        inputs = Input(seq_size, dtype=tf.int32)
        input_data = np.array([[2, 0], [1, 2]])

        features = Lookup(inputs, seq_size, lookup_shape=[vocab_size, n_features]).as_concat()
        sp_features = ToSparse(features)

        gate_w = Linear(features, seq_size)
        gate1 = Gate(features, gate_w)
        gate2 = gate1.reuse_with(sp_features)

        init = tf.global_variables_initializer()
        init.run()

        feed = {inputs.placeholder: input_data}

        r1 = gate1.tensor.eval(feed)
        r2 = gate2.tensor.eval(feed)

        self.assertTrue(np.array_equal(r1, r2))

    def test_coupled_gate(self):
        self.reset()

        vocab_size = 4
        n_features = 3
        seq_size = 2
        batch_size = 4

        inputs = Input(seq_size, dtype=tf.int32)
        input_data = np.array([[2, 0], [1, 2]])

        features1 = Lookup(inputs, seq_size, lookup_shape=[vocab_size, n_features]).as_concat()
        features2 = Lookup(inputs, seq_size, lookup_shape=[vocab_size, n_features]).as_concat()

        sp_features1 = ToSparse(features1)

        gate_w = Linear(features1, seq_size)
        coupled_gate = CoupledGate(features1, features2, gate_w)

        coupled_gate2 = coupled_gate.reuse_with(sp_features1, features2)

        init = tf.global_variables_initializer()
        init.run()

        feed = {inputs.placeholder: input_data}

        r1 = coupled_gate.tensor.eval(feed)
        r2 = coupled_gate2.tensor.eval(feed)

        self.assertTrue(np.array_equal(r1, r2))

    def test_rnn_cell(self):
        self.reset()

        n_inputs = 4
        n_hidden = 2
        batch_size = 2

        inputs = Input(n_inputs)
        rnn_1 = RNNCell(inputs, n_hidden)
        rnn_2 = rnn_1.reuse_with(inputs, rnn_1)

        rnn_3 = rnn_1.reuse_with(inputs)

        tf.global_variables_initializer().run()

        data = np.ones([batch_size, 4])

        res1 = rnn_1.tensor.eval({inputs.placeholder: data})
        res2 = rnn_2.tensor.eval({inputs.placeholder: data})
        res3 = rnn_3.tensor.eval({inputs.placeholder: data})

        self.assertEqual((batch_size, n_hidden), np.shape(res1))
        self.assertTrue(np.array_equal(res1, res3))
        self.assertFalse(np.array_equal(res1, res2))

        m = Model(inputs, rnn_2)
        # r = ModelRunner(m)
        # r.log_graph("/tmp")

    def test_lstm_cell(self):
        self.reset()

        n_inputs = 4
        n_hidden = 2
        batch_size = 2

        inputs = Input(n_inputs)
        rnn_1 = LSTMCell(inputs, n_hidden)
        rnn_2 = rnn_1.reuse_with(inputs,
                                 previous_state=rnn_1)

        # if we don't wipe the memory it reuses it
        rnn_3 = rnn_1.reuse_with(inputs,
                                 previous_state=None,
                                 memory_state=LSTMCell.zero_state(inputs, rnn_1.n_units))

        tf.global_variables_initializer().run()

        data = np.ones([batch_size, 4])

        res1 = rnn_1.tensor.eval({inputs.placeholder: data})
        res2 = rnn_2.tensor.eval({inputs.placeholder: data})
        res3 = rnn_3.tensor.eval({inputs.placeholder: data})

        self.assertEqual((batch_size, n_hidden), np.shape(res1))
        self.assertTrue(np.array_equal(res1, res3))
        self.assertFalse(np.array_equal(res1, res2))

        m = Model(inputs, rnn_2)
        # r = ModelRunner(m)
        # r.log_graph("/tmp")

    def test_gru_cell(self):
        self.reset()

        n_inputs = 4
        n_hidden = 2
        batch_size = 2

        inputs = Input(n_inputs)
        rnn_1 = GRUCell(inputs, n_hidden)
        rnn_2 = rnn_1.reuse_with(inputs,
                                 previous_state=rnn_1)

        # if we don't wipe the memory it reuses it
        rnn_3 = rnn_1.reuse_with(inputs,
                                 previous_state=GRUCell.zero_state(inputs, rnn_1.n_units))

        tf.global_variables_initializer().run()

        data = np.ones([batch_size, 4])

        res1 = rnn_1.tensor.eval({inputs.placeholder: data})
        res2 = rnn_2.tensor.eval({inputs.placeholder: data})
        res3 = rnn_3.tensor.eval({inputs.placeholder: data})

        self.assertEqual((batch_size, n_hidden), np.shape(res1))
        self.assertTrue(np.array_equal(res1, res3))
        self.assertFalse(np.array_equal(res1, res2))

        m = Model(inputs, rnn_2)
        r = ModelRunner(m)
        r.log_graph("/tmp")

    def test_module(self):
        l1 = Input(1, name="in1")
        l2 = Input(1, name="in2")
        l3 = Add(l1, l2)
        l4 = Add(l1, l2)
        l5 = Linear(l4, 1)
        t1 = TensorLayer([[1]], n_units=1, dtype=tf.float32)
        l6 = Add(l3, t1)
        l7 = Add(l6, l5)

        t2 = TensorLayer([[1]], n_units=1, dtype=tf.float32)
        t3 = TensorLayer([[1]], n_units=1, dtype=tf.float32)

        m = Module([l1, l2, t1], l7)
        with tf.name_scope("module_reuse"):
            m2 = m.reuse_with(t2, t3, t1)

        tf.global_variables_initializer().run()

        feed = {l1.placeholder: [[1]], l2.placeholder: [[1]]}
        res1 = m.tensor.eval(feed)
        res2 = m2.tensor.eval()

        # model = Model(m2.input_layers, m2)
        # runner = ModelRunner(model)
        # runner.log_graph("/tmp")

    def test_module_gate(self):
        l1 = Input(4, name="in1")
        l2 = Input(2, name="in2")

        gate = Gate(layer=l1, gate_input=l2)
        gate_module = Module([l1, l2], gate)

        model = Model(run_in_layers=gate_module.input_layers, run_out_layers=gate_module)
        runner = ModelRunner(model)
        runner.log_graph("/tmp")

        t1 = TensorLayer([[1, 1, 1, 1]], n_units=4, dtype=tf.float32)
        t2 = TensorLayer([[1, 1]], n_units=2, dtype=tf.float32)

        with tf.name_scope("module_reuse"):
            m2 = gate_module.reuse_with(t1, t2)

        model = Model(m2.input_layers, m2)
        runner = ModelRunner(model)
        runner.log_graph("/tmp/")

    def test_reshape(self):
        v = np.array([[[1], [2]], [[3], [4]]])
        x = TensorLayer(v, n_units=1)

        fl = Reshape(x, [-1, 2])
        fl2 = fl.reuse_with(x)

        self.assertTrue(np.array_equal(fl.eval(), fl2.eval()))

    def test_flatten(self):
        v = [[[1, 2], [3, 4], [5, 6]], [[7, 8], [9, 10], [11, 12]]]
        x = TensorLayer(v, n_units=2)
        fl = Flatten(x)
        self.assertSequenceEqual(fl.shape, [2, 6])
        rs = Reshape(fl, x.shape)
        self.assertTrue(np.array_equal(x.eval(), rs.eval()))
        fl2 = fl.reuse_with(x)

        self.assertTrue(np.array_equal(fl.eval(), fl2.eval()))

    def test_batch_norm(self):
        self.reset()

        v = np.array([[1, 1, 1, 1], [2, 2, 2, 2], [-1, 1, -1, -1]])
        x = TensorLayer(v, n_units=4, dtype=tf.float32)
        xs = ToSparse(x)

        inputs_shape = x.shape
        axis = list(range(len(inputs_shape) - 1))
        params_shape = inputs_shape[-1:]

        # during training
        decay = 0.999
        epsilon = 0.001

        # this can be params of the layer
        beta = tf.get_variable('beta',
                               shape=params_shape,
                               dtype=x.dtype,
                               initializer=tf.zeros_initializer,
                               trainable=True)

        gamma = tf.get_variable('gamma',
                                shape=params_shape,
                                dtype=x.dtype,
                                initializer=tf.ones_initializer,
                                trainable=True)

        # these are not trainable but updated each time we compute mean and variance
        moving_mean = tf.get_variable("moving_mean",
                                      shape=params_shape,
                                      initializer=tf.zeros_initializer(),
                                      trainable=False)
        moving_var = tf.get_variable("moving_var",
                                     shape=params_shape,
                                     initializer=tf.zeros_initializer(),
                                     trainable=False)

        # Calculate the moments based on the individual batch.
        mean, variance = tf.nn.moments(x.tensor, axis, shift=moving_mean)

        """Some training algorithms, such as GradientDescent and Momentum often benefit 
            from maintaining a moving average of variables during optimization. 
            Using the moving averages for evaluations often improve results significantly.
        """
        from tensorflow.python.training.moving_averages import assign_moving_average

        """  The moving average of 'variable' updated with 'value' is:
            variable * decay + value * (1 - decay)
        """

        update_mv_avg = assign_moving_average(moving_mean, mean, decay)
        update_mv_var = assign_moving_average(moving_var, variance, decay)

        with tf.control_dependencies([update_mv_avg, update_mv_var]):
            outputs = tf.nn.batch_normalization(
                x.tensor, mean, variance, beta, gamma, epsilon)

        # if not training instead of using mean and variance we use an estimate
        # for the pop ulation mean and variance computed for example from the
        # exponential moving averages

        # outputs = nn.batch_normalization(
        #    inputs, moving_mean, moving_variance, beta, gamma, epsilon)
        # outputs.set_shape(inputs.get_shape())

        bn = BatchNorm(x, beta=beta, gamma=gamma, center=True, scale=True)
        bn2 = BatchNorm(x, gamma=gamma, center=True, scale=True, beta_init=random_uniform(0, 1))
        bn3 = BatchNorm(x, beta=beta, gamma=gamma, center=True, scale=True, beta_init=random_uniform(0, 1))

        bn_simple = BatchNorm(x, scale=False, center=False)

        bn_inference = bn.reuse_with(x, training=False)

        tf.global_variables_initializer().run()

        # test updated moving avg
        before = bn.moving_mean.eval()
        bn.eval()
        after = bn.moving_mean.eval()
        self.assertFalse(np.array_equal(before, after))
        before = bn.moving_mean.eval()
        bn.eval()
        after = bn.moving_mean.eval()
        self.assertFalse(np.array_equal(before, after))

        self.assertEqual(bn.moving_mean, bn_inference.moving_mean)
        before = bn_inference.moving_mean.eval()
        bn_inference.eval()
        after = bn_inference.moving_mean.eval()
        self.assertTrue(np.array_equal(before, after))

        self.assertTrue(np.array_equal(outputs.eval(), bn.eval()))
        self.assertFalse(np.array_equal(outputs.eval(), bn_inference.eval()))
        # ignores init because we pass beta and gamma
        self.assertTrue(np.array_equal(outputs.eval(), bn3.eval()))
        self.assertFalse(np.array_equal(outputs.eval(), bn2.eval()))

        self.assertTrue(np.array_equal(outputs.eval(), bn_simple.eval()))

    def test_batch_norm_sparse(self):
        self.reset()

        v = np.array([[1, 1], [2, 3], [-1, 6]])
        x = TensorLayer(v, n_units=2, dtype=tf.float32)
        xs = ToSparse(x)

        bn = BatchNorm(x, training=False, name="bn_infer")
        bns = bn.reuse_with(xs, name="bns_infer")

        # print(bn.moving_mean.op.name)
        # print(bns.moving_mean.op.name)

        tf.global_variables_initializer().run()

        res1 = bn.eval()
        res2 = bns.eval()

        # moving average and variance should be the same
        self.assertTrue(np.array_equal(res1, res2))

        bn = bn.reuse_with(x, training=True, name="bn_train")
        bns = bn.reuse_with(xs, name="bns_train")

        moving_mean_before = bn.moving_mean.eval()
        res1 = bn.eval()
        res2 = bns.eval()
        moving_mean_after = bn.moving_mean.eval()

        # moving average and variance are updated so they can't be the same
        self.assertFalse(np.array_equal(moving_mean_before, moving_mean_after))
        self.assertTrue(np.array_equal(res1, res2))

        bn = bn.reuse_with(x, training=False)
        bns = bn.reuse_with(xs)

        res1 = bn.eval()
        res2 = bns.eval()

        # testing switching between training and inference modes in the batch norm
        self.assertTrue(np.array_equal(res1, res2))

    def test_batch_norm_mv_average(self):
        t1 = np.array([[1, 1], [2, 3], [-1, 6]])
        t2 = np.array([[5, 5], [1, 2], [-6, -10]])

        x = Input(n_units=2, dtype=tf.float32)
        xs = ToSparse(x)

        bn = BatchNorm(x, training=True, name="bn")
        bns = bn.reuse_with(xs)

        bn_infer = bn.reuse_with(x, training=False, name="bn_infer")

        tf.global_variables_initializer().run()

        r0_infer = bn_infer.eval({x.placeholder: t1})

        mv0 = bn.moving_mean.eval()
        r1 = bn.eval({x.placeholder: t1})
        mv1 = bn.moving_mean.eval()

        r1_infer = bn_infer.eval({x.placeholder: t1})

        # moving average and variance are updated so they can't be the same
        self.assertFalse(np.array_equal(mv0, mv1))

        # the result with the same data can't be the same because it uses the
        # estimate for population mean and variance which is updated by the training step
        self.assertFalse(np.array_equal(r0_infer, r1_infer))

        r2 = bn.eval({x.placeholder: t2})
        r2_infer = bn_infer.eval({x.placeholder: t1})

        rs1 = bns.eval({x.placeholder: t1})
        r3_infer = bn_infer.eval({x.placeholder: t1})
        rs2 = bns.eval({x.placeholder: t2})

        # the results should be the same because they are computed based on the current
        # mini-batch mean and variance
        self.assertTrue(np.array_equal(r1, rs1))
        self.assertTrue(np.array_equal(r2, rs2))

        # again can't be the same because the moving avg changed
        self.assertFalse(np.array_equal(r1_infer, r2_infer))

        # the reused layer should also update the moving average
        # so the inference step will give a different value again
        self.assertFalse(np.array_equal(r2_infer, r3_infer))

    if __name__ == '__main__':
        unittest.main()
