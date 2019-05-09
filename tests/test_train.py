import numpy as np
import os
import tensorflow as tf

from tensorx import test_utils
from tensorx.activation import tanh, sigmoid
from tensorx.layers import Input, Linear, Activation, Add, LambdaLayer, Param
from tensorx.loss import binary_cross_entropy
from tensorx.train import *
from tensorx.callbacks import *
from pygraphviz import AGraph

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'


class ModelRunnerTest(test_utils.TestCase):

    def test_graph(self):
        data = [[1., 2.]]

        in1 = Input(2, name="in1")
        in2 = Input(2, name="in2")

        linear = Linear(in1, 1)
        graph = LayerGraph(linear)
        # graph.draw("test.pdf")

        self.assertEqual(len(graph.dependencies[linear]), 1)
        self.assertTrue(in1 in graph.dependencies[linear])

        try:
            LayerGraph(inputs=[in1, in2], outputs=linear)
            self.fail("should have raised an exception: some inputs are not connected to anything")
        except ValueError:
            pass

        try:
            LayerGraph(inputs=[in2], outputs=linear)
            self.fail("should have raised an error: inputs specified but dependencies are missing")
        except ValueError:
            pass

        with self.cached_session(use_gpu=True) as session:
            self.eval(tf.global_variables_initializer())
            w = self.eval(tf.matmul(data, linear.weights))
            result1 = graph.eval(feed={in1: data}, session=session)

            other_fetches = tf.constant(0)
            result2 = graph.eval(feed={in1: data},
                                 other_tensors=other_fetches,
                                 session=session)

            self.assertTrue(len(result2), 2)
            self.assertEqual(result2[-1], 0)
            self.assertArrayEqual(result2[0], w)
            self.assertArrayEqual(result1, w)

    def test_feed_defaults(self):
        data = [[1, 2]]

        in1 = Input(2, name="in1")
        in2 = Input(2, name="in2")

        out = Add(in1, in2)
        graph = LayerGraph(out)

        in1.value = np.array(data)

        with self.cached_session(use_gpu=True):
            self.eval(tf.global_variables_initializer())
            result = graph.eval(feed={in2: [[2, 1]]})

            self.assertArrayEqual(result, [[3, 3]])

    def test_multi_output_graph(self):
        data = [[1, 1]]
        data2 = [[2, 1]]

        in1 = Input(2, name="in1")
        in2 = Input(2, name="in2")

        linear1 = Linear(in1, 1)
        linear2 = Linear(Add(in1, in2), 1)

        graph = LayerGraph(outputs=[linear1, linear2])

        with self.cached_session(use_gpu=True) as session:
            self.eval(tf.global_variables_initializer())

            result1 = graph.eval(feed={in1: data, in2: data2}, session=session)
            self.assertEqual(len(result1), 2)

            # testing target output and defaults without feed
            # does not override default
            in2.value = data2
            result2 = graph.eval(feed={in1: data, in1: data},
                                 target_outputs=linear2,
                                 # feed={in1: data,in2: data},
                                 session=session)
            self.assertArrayEqual(result2, result1[-1])
            in2.value = None

            # fills in1 in2 by the same order
            result4 = graph.eval(feed={in1: data, in2: data},
                                 target_outputs=linear2,
                                 # feed={in1: data,in2: data},
                                 session=session)

            # not the same because we use data2
            self.assertArrayNotEqual(result4, result2)

    def test_model_session(self):
        data = [[1]]
        inputs = Input(1)
        # feed = {inputs.placeholder: data}
        linear = Linear(inputs, 1)
        model = Model(run_inputs=inputs, run_outputs=linear)

        # runner.set_session()

        # creates a new session or uses the default session
        self.assertIsNone(model.session)
        self.assertFalse(model.vars_inited())

        model.run_step({inputs: data})

        self.assertIsNotNone(model.session)
        self.assertTrue(model.vars_inited())

        # consecutive runs do not change the session
        session1 = model.session
        result1 = model.run_step({inputs: data})
        # weights1 = session1.run(linear.weights, {inputs.tensor: data})
        self.assertEqual(model.session, session1)

        with tf.Session() as new_session:
            # this creates a new session
            session2 = model.set_session()
            self.assertIsNotNone(model.session)
            self.assertNotEqual(session1, session2)
            self.assertEqual(session2, new_session)
            # setting a new session resets the variables
            self.assertFalse(model.vars_inited())

            # different sessions init the variables again
            result2 = model.run_step({inputs: data})

            self.assertFalse(np.array_equal(result1, result2))

            model.set_session()
            # explicitly initialise variables with the new session
            model.init_vars()
            self.assertTrue(model.vars_inited())
            result31 = model.run_step({inputs: data})
            # if the session doesn't change and variables are not re-initialised, the result should be the same
            result32 = model.run_step({inputs: data})
            model.init_vars()
            result33 = model.run_step({inputs: data})
            self.assertTrue(np.array_equal(result31, result32))
            self.assertFalse(np.array_equal(result31, result33))

            # to use the model in a new session, either call reset or model.set_session(session)
            model.reset_session()

        with tf.Session() as session4:
            model.run_step({inputs: data})
            self.assertEqual(model.session, session4)

        model.reset_session()
        self.assertIsNone(model.session)
        session5 = tf.InteractiveSession()
        model.run_step({inputs: data})
        self.assertEqual(model.session, session5)
        tf.reset_default_graph()

    def test_model_graphs(self):
        in1 = Input(2, name="in1")
        in2 = Input(2, name="in2")

        linear1 = Linear(in1, 1)
        linear2 = Linear(Add(in1, in2), 1)

        Model(run_inputs=[in1, in2], run_outputs=[linear1, linear2])

    def test_model_var_init(self):
        inputs = Input(1)
        linear = Linear(inputs, 2)
        model = Model(run_inputs=inputs, run_outputs=linear)

        with tf.Session() as session1:
            self.assertFalse(session1.run(tf.is_variable_initialized(linear.bias)))
            model.init_vars()
            self.assertTrue(session1.run(tf.is_variable_initialized(linear.bias)))
            model.run_step({inputs: [[1.]]})

        # if reset is not called, init vars tries to use session1
        model.reset_session()
        session2 = tf.Session()
        model.set_session(session2)
        model.init_vars()
        self.assertTrue(session2.run(tf.is_variable_initialized(linear.bias)))

        session2.close()

    def test_model_run(self):
        with self.cached_session(use_gpu=True):
            inputs = Input(4)
            linear = Linear(inputs, 2)
            h = Activation(linear, fn=tanh)
            logits = Linear(h, 4)
            out = Activation(logits, fn=sigmoid)

            model = Model(run_inputs=inputs, run_outputs=out)

            data1 = [[1, -1, 1, -1]]

            result = model.run_step({inputs: data1})
            self.assertIsInstance(result, np.ndarray)
            self.assertTrue(np.ndim(result), 2)

    def test_model_train(self):
        with self.cached_session(use_gpu=True):
            input_layer = Input(4, name="inputs")
            linear = Linear(input_layer, 2)
            h = Activation(linear, fn=sigmoid)

            # configure training
            labels = Input(2, name="labels")
            losses = LambdaLayer(labels, h, apply_fn=binary_cross_entropy)

            model = Model(run_inputs=input_layer,
                          run_outputs=h,
                          train_inputs=[input_layer, labels],
                          train_loss=losses,
                          eval_inputs=[input_layer, labels],
                          eval_score=losses)

            optimiser = tf.train.AdadeltaOptimizer(learning_rate=0.5)
            model.config_optimizer(optimiser)

            data = np.array([[1, 1, 1, 1]])
            target = np.array([[1.0, 0.0]])

            # session = runner.session
            # weights = session.run(linear.weights)
            model.init_vars()
            weights1 = model.session.run(linear.weights)

            for i in range(10):
                model.train_op({input_layer: data, labels: target})

            weights2 = model.session.run(linear.weights)

            self.assertFalse(np.array_equal(weights1, weights2))

    def test_eval_step_decay_param(self):
        input_layer = Input(4, name="inputs")
        linear = Linear(input_layer, 2)
        h = Activation(linear, fn=sigmoid)

        # configure training
        labels = Input(2, name="labels")
        losses = LambdaLayer(labels, h, apply_fn=binary_cross_entropy)

        model = Model(run_inputs=input_layer,
                      run_outputs=h,
                      train_inputs=[input_layer, labels],
                      train_loss=losses,
                      eval_inputs=[input_layer, labels],
                      eval_score=losses)

        lr = Param(value=0.5, name="lr")
        optimiser = tf.train.AdadeltaOptimizer(learning_rate=lr)
        model.config_optimizer(optimiser, optimizer_params=lr)

        # lr will be exposed as a lr (name) parameter

        # with self.cached_session(use_gpu=True):
        #
        #
        #
        #
        # v1 = 4
        # decay_rate = 0.5
        # param = EvalStepDecayParam(value=v1,
        #                            decay_rate=decay_rate,
        #                            improvement_threshold=1.0,
        #                            less_is_better=True)
        # param.update(evaluation=1)
        # v2 = param.value
        # self.assertEqual(v1, v2)
        #
        # # eval does not improve
        # param.update(evaluation=10)
        # v3 = param.value
        # self.assertNotEqual(v2, v3)
        # self.assertEqual(v3, v2 * decay_rate)
        # self.assertEqual(param.eval_improvement(), -9)
        #
        # # eval improves but not more than threshold
        # v4 = param.value
        # param.update(evaluation=9)
        # self.assertEqual(v4, v3)
        #
        # # eval does not improve
        # v5 = param.value
        # param.update(evaluation=10)
        # self.assertEqual(v5, v4 * decay_rate)
        #
        # # eval improves but within threshold
        # v6 = param.value
        # param.update(evaluation=8.9)
        # self.assertEqual(v6, v5 * decay_rate)
        #
        # # INCREASING EVAL
        # param = EvalStepDecayParam(v1, decay_rate=decay_rate, improvement_threshold=1.0, less_is_better=False)
        # param.update(evaluation=5)
        # v2 = param.value
        # self.assertEqual(v1, v2)
        #
        # # eval does not improve
        # param.update(evaluation=4)
        # v3 = param.value
        # self.assertEqual(v3, v2 * decay_rate)
        #
        # # improvement within threshold / did not improve
        # param.update(evaluation=5)
        # v4 = param.value
        # self.assertEqual(v4, v3 * decay_rate)
        #
        # # improvement more than threshold
        # param.update(evaluation=6.1)
        # v5 = param.value
        # self.assertEqual(v5, v4)

    def test_param_prop(self):
        input_layer = Input(4, name="inputs")
        linear = Linear(input_layer, 2)
        h = Activation(linear, fn=sigmoid)

        # configure training
        labels = Input(2, name="labels")
        losses = LambdaLayer(labels, h, apply_fn=binary_cross_entropy)

        model = Model(run_inputs=input_layer,
                      run_outputs=h,
                      train_inputs=[input_layer, labels],
                      train_loss=losses,
                      eval_inputs=[input_layer, labels],
                      eval_score=losses)

        lr = Param(value=1.0, name="lr")
        optimiser = tf.train.GradientDescentOptimizer(learning_rate=lr)
        model.config_optimizer(optimiser, optimizer_params=lr)

        # lr will be exposed as a lr (name) parameter

        with self.cached_session(use_gpu=True):
            # dummy dataset with 2 samples
            dataset = [{
                input_layer: np.random.uniform(size=[2, 4]),
                labels: np.random.uniform(size=[2, 2]),
                "prop1": 0
            },
                {input_layer: np.random.uniform(size=[2, 4]),
                 labels: np.random.uniform(size=[2, 2]),
                 "prop1": 1}
            ]

            # callbacks
            progress = Progress(total_steps=6 * 2, monitor=["last_loss", "train_loss"])

            lr_schedule = DecayAfter(2, decay_rate=0.5, changes="lr")

            evaluation = Eval(property="validation_ppl",
                              fn=np.exp,
                              dataset=dataset,
                              trigger=OnEveryEpoch())

            # make sure this is executed after logger for example
            early_stop = EarlyStop(3, lesser_better=True, threshold=1,
                                   target="validation_ppl",
                                   trigger=OnEveryEpoch())

            decay_plateau = PlateauDecay(monitor="validation_ppl", target="lr",
                                         improvement_threshold=0.01,
                                         decay_rate=0.5)

            logger = CSVLogger(logs=["epoch", "step", "lr", "prop1", "validation_ppl"],
                               static_logs={"id": 0},
                               out_filename="test.csv",
                               trigger=OnEveryEpoch(), priority=20)

            model.train(train_data=dataset,
                        epochs=6,
                        callbacks=[progress,
                                   evaluation,
                                   logger,
                                   decay_plateau,
                                   ])  # progress, evaluation, logger, early_stop, lr_schedule])


if __name__ == '__main__':
    test_utils.main()
