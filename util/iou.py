import torch
import numpy as np
from metric import metric
from .confusionmatrix import ConfusionMatrix


class IoU(metric.Metric):
    """Computes the intersection over union (IoU) per class and corresponding
    mean (mIoU).

    Intersection over union (IoU) is a common evaluation metric for semantic
    segmentation. The predictions are first accumulated in a confusion matrix
    and the IoU is computed from it as follows:

        IoU = true_positive / (true_positive + false_positive + false_negative).

    Keyword arguments:
    - num_classes (int): number of classes in the classification problem
    - normalized (boolean, optional): Determines whether or not the confusion
    matrix is normalized or not. Default: False.
    - ignore_index (int or iterable, optional): Index of the classes to ignore
    when computing the IoU. Can be an int, or any iterable of ints.
    """

    def __init__(self, num_classes, normalized=False, ignore_index=None):
        super().__init__()
        self.conf_metric = ConfusionMatrix(num_classes, normalized)

        if ignore_index is None:
            self.ignore_index = None
        elif isinstance(ignore_index, int):
            self.ignore_index = (ignore_index,)
        else:
            try:
                self.ignore_index = tuple(ignore_index)
            except TypeError:
                raise ValueError("'ignore_index' must be an int or iterable")

    def reset(self):
        self.conf_metric.reset()

    def add(self, predicted, target):
        """Adds the predicted and target pair to the IoU metric.

        Keyword arguments:
        - predicted (Tensor): Can be a (N, K, H, W) tensor of
        predicted scores obtained from the model for N examples and K classes,
        or (N, H, W) tensor of integer values between 0 and K-1.
        - target (Tensor): Can be a (N, K, H, W) tensor of
        target scores for N examples and K classes, or (N, H, W) tensor of
        integer values between 0 and K-1.

        """
        # Dimensions check
        assert predicted.size(0) == target.size(0), \
            'number of targets and predicted outputs do not match'
        assert predicted.dim() == 3 or predicted.dim() == 4, \
            "predictions must be of dimension (N, H, W) or (N, K, H, W)"
        assert target.dim() == 3 or target.dim() == 4, \
            "targets must be of dimension (N, H, W) or (N, K, H, W)"

        # If the tensor is in categorical format convert it to integer format
        if predicted.dim() == 4:
            _, predicted = predicted.max(1)
        if target.dim() == 4:
            _, target = target.max(1)

        self.conf_metric.add(predicted.view(-1), target.view(-1))

    def value(self):
        """Computes the IoU and mean IoU.

        The mean computation ignores NaN elements of the IoU array.

        Returns:
            Tuple: (IoU, mIoU). The first output is the per class IoU,
            for K classes it's numpy.ndarray with K elements. The second output,
            is the mean IoU.
        """
        conf_matrix = self.conf_metric.value()
        if self.ignore_index is not None:
            conf_matrix[:, self.ignore_index] = 0
            conf_matrix[self.ignore_index, :] = 0
        true_positive = np.diag(conf_matrix)
        false_positive = np.sum(conf_matrix, 0) - true_positive
        false_negative = np.sum(conf_matrix, 1) - true_positive

        # Just in case we get a division by 0, ignore/hide the error
        with np.errstate(divide='ignore', invalid='ignore'):
            iou = true_positive / (true_positive + false_positive + false_negative)

        return iou, np.nanmean(iou)

class IoU:
    def __init__(self, num_classes):
        self.num_classes = num_classes
        self.hist = np.zeros((num_classes, num_classes))

    def reset(self):
        """重置混淆矩阵"""
        self.hist = np.zeros((self.num_classes, self.num_classes))

    def add(self, pred, label):
        """添加预测和标签数据到混淆矩阵"""
        if pred.dim() == 4:
            _, pred = pred.max(1)
        if label.dim() == 4:
            _, label = label.max(1)
        if len(label.flatten()) != len(pred.flatten()):
            print('Skipping: len(gt) = {:d}, len(pred) = {:d}'.format(
                len(label.flatten()), len(pred.flatten())))
            return

        self.hist += self.fast_hist(label.flatten(), pred.flatten(), self.num_classes)

    def value(self):
        """计算并返回每个类别的IoU和平均IoU"""
        mIoUs = self.per_class_iu(self.hist)
        mPA = self.per_class_PA(self.hist)
        miou = np.nanmean(mIoUs)
        print('===> mIoU: ' + str(round(miou * 100, 4)) +
            '; mPA: ' + str(round(np.nanmean(mPA) * 100, 4)))
        return mIoUs, miou

    @staticmethod
    def fast_hist(a, b, n):
        """计算混淆矩阵"""
        a = a.cpu().numpy() if isinstance(a, torch.Tensor) else a
        b = b.cpu().numpy() if isinstance(b, torch.Tensor) else b
        k = (a >= 0) & (a < n)
        return np.bincount(n * a[k].astype(int) + b[k], minlength=n ** 2).reshape(n, n)

    @staticmethod
    def per_class_iu(hist):
        """计算每个类别的IoU"""
        print('Defect class IoU as follows:')
        print(np.diag(hist)[1:] / np.maximum((hist.sum(1) + hist.sum(0) - np.diag(hist))[1:], 1))
        return np.diag(hist)[1:] / np.maximum((hist.sum(1) + hist.sum(0) - np.diag(hist))[1:], 1)

    @staticmethod
    def per_class_PA(hist):
        """计算每个类别的准确率"""
        return np.diag(hist) / np.maximum(hist.sum(1), 1)