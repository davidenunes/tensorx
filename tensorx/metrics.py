""" Metrics module

measures different properties of and between tensors
"""
from tensorflow.python.ops import math_ops, array_ops, linalg_ops, sparse_ops
from tensorflow.python.framework import ops
from tensorflow.python.framework import dtypes
from tensorflow.python.framework.ops import Tensor
from tensorflow.python.framework.sparse_tensor import convert_to_tensor_or_sparse_tensor, SparseTensor

from tensorx.transform import sparse_l2_norm, sparse_dot


def sparse_cosine_distance(sp_tensor, tensor2, dim=-1, dtype=dtypes.float32):
    """ Computes the cosine distance between two non-zero `SparseTensor` and `Tensor`

        Args:
            sp_tensor: a `SparseTensor`
            tensor2: a `Tensor`
            dim: the dimension along which the distance is computed
            dtype:

        Returns:
            a `Tensor` with the cosine distance between two tensors
        """
    tensor1 = SparseTensor.from_value(sp_tensor)
    if tensor1.values.dtype != dtype:
        tensor1.values = math_ops.cast(tensor1.values, dtype)
    tensor2 = ops.convert_to_tensor(tensor2, dtype)

    dot_prod = sparse_dot(tensor1, tensor2, dim)
    norm1 = sparse_l2_norm(tensor1, axis=dim)
    norm2 = linalg_ops.norm(tensor2, axis=dim)

    cos12 = dot_prod / (norm1 * norm2)
    distance = 1 - cos12

    distance = array_ops.where(math_ops.is_nan(distance), array_ops.zeros_like(distance), distance)
    return distance


def cosine_distance(tensor1, tensor2, dim=-1, dtype=dtypes.float32):
    """ Computes the cosine distance between two non-zero `Tensor`s

    Args:
        tensor1: a `Tensor`
        tensor2: a `Tensor`
        dim: the dimension along which the distance is computed
        dtype:

    Returns:
        a `Tensor` with the cosine distance betwen two tensors
    """
    tensor1 = ops.convert_to_tensor(tensor1, dtype)
    tensor2 = ops.convert_to_tensor(tensor2, dtype)

    dot_prod = math_ops.reduce_sum(math_ops.multiply(tensor1, tensor2), dim)
    norm1 = linalg_ops.norm(tensor1, axis=dim)
    norm2 = linalg_ops.norm(tensor2, axis=dim)

    cos12 = dot_prod / (norm1 * norm2)
    distance = 1 - cos12
    distance = array_ops.where(math_ops.is_nan(distance), array_ops.zeros_like(distance), distance)

    return distance


def euclidean_distance(tensor1, tensor2, dim):
    """ Computes the euclidean distance between two tensors.

        Args:
            tensor1: a ``Tensor``
            tensor2: a ``Tensor``
            dim: dimension along which the euclidean distance is computed

        Returns:
            ``Tensor``: a ``Tensor`` with the euclidean distances between the two tensors

        """
    tensor1 = ops.convert_to_tensor(tensor1)
    tensor2 = ops.convert_to_tensor(tensor2)

    distance = math_ops.sqrt(math_ops.reduce_sum(math_ops.square(tensor1 - tensor2), axis=dim))

    return distance
