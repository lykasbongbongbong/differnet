import os
import torch
from torch.utils.data import DataLoader
from torchvision import datasets, transforms
from torchvision.transforms.functional import rotate
import config as c
from multi_transform_loader import ImageFolderMultiTransform


def get_random_transforms():
    augmentative_transforms = []
    if c.transf_rotations:
        augmentative_transforms += [transforms.RandomRotation(180)]
    if c.transf_brightness > 0.0 or c.transf_contrast > 0.0 or c.transf_saturation > 0.0:
        augmentative_transforms += [transforms.ColorJitter(brightness=c.transf_brightness, contrast=c.transf_contrast,
                                                           saturation=c.transf_saturation)]

    tfs = [transforms.Resize(c.img_size)] + augmentative_transforms + [transforms.ToTensor(),
                                                                       transforms.Normalize(c.norm_mean, c.norm_std)]

    transform_train = transforms.Compose(tfs)
    return transform_train


def get_fixed_transforms(degrees):
    cust_rot = lambda x: rotate(x, degrees, False, False, None)
    augmentative_transforms = [cust_rot]
    if c.transf_brightness > 0.0 or c.transf_contrast > 0.0 or c.transf_saturation > 0.0:
        augmentative_transforms += [
            transforms.ColorJitter(brightness=c.transf_brightness, contrast=c.transf_contrast,
                                   saturation=c.transf_saturation)]
    tfs = [transforms.Resize(c.img_size)] + augmentative_transforms + [transforms.ToTensor(),
                                                                       transforms.Normalize(c.norm_mean,
                                                                                            c.norm_std)]
    return transforms.Compose(tfs)


def t2np(tensor):
    '''pytorch tensor -> numpy array'''
    return tensor.cpu().data.numpy() if tensor is not None else None


def get_loss(z, jac):
    '''check equation 4 of the paper why this makes sense - oh and just ignore the scaling here'''
    return torch.mean(0.5 * torch.sum(z ** 2, dim=(1,)) - jac) / z.shape[1]

def get_con_loss(y_pred, y_true):
    confidence_margin = 5.
    ref = torch.normal(mean=0., std=torch.full([5000], 1.)).cuda()
    dev = (y_pred - torch.mean(ref)) / torch.std(ref)
    inlier_loss = torch.abs(dev)
    outlier_loss = torch.abs((confidence_margin - dev).clamp_(min=0.))
    return torch.mean((1-y_true) * inlier_loss + y_true*outlier_loss)

def load_datasets(dataset_path, class_name):
    '''
    Expected folder/file format to find anomalies of class <class_name> from dataset location <dataset_path>:

    train data:

            dataset_path/class_name/train/good/any_filename.png
            dataset_path/class_name/train/good/another_filename.tif
            dataset_path/class_name/train/good/xyz.png
            [...]

    test data:

        'normal data' = non-anomalies

            dataset_path/class_name/test/good/name_the_file_as_you_like_as_long_as_there_is_an_image_extension.webp
            dataset_path/class_name/test/good/did_you_know_the_image_extension_webp?.png
            dataset_path/class_name/test/good/did_you_know_that_filenames_may_contain_question_marks????.png
            dataset_path/class_name/test/good/dont_know_how_it_is_with_windows.png
            dataset_path/class_name/test/good/just_dont_use_windows_for_this.png
            [...]

        anomalies - assume there are anomaly classes 'crack' and 'curved'

            dataset_path/class_name/test/crack/dat_crack_damn.png
            dataset_path/class_name/test/crack/let_it_crack.png
            dataset_path/class_name/test/crack/writing_docs_is_fun.png
            [...]

            dataset_path/class_name/test/curved/wont_make_a_difference_if_you_put_all_anomalies_in_one_class.png
            dataset_path/class_name/test/curved/but_this_code_is_practicable_for_the_mvtec_dataset.png
            [...]
    '''

    def target_transform(target):
        return class_perm[target]
    def train_target_transform(target):
        return train_class_perm[target]

    data_dir_train = os.path.join(dataset_path, class_name, 'train')
    data_dir_test = os.path.join(dataset_path, class_name, 'test')

    # 處理train底下的normal和anomalies(few-shot)  
    train_classes = os.listdir(data_dir_train)    # good, few_shot
    train_classes.sort()
    train_class_perm = list()
    train_class_idx = 1
    for cl in train_classes:
        if cl == "good":
            train_class_perm.append(0)
        else:
            train_class_perm.append(train_class_idx)
            train_class_idx += 1

    

    # 處理 test 底下不同的defect types
    classes = os.listdir(data_dir_test)
    if 'good' not in classes:
        print('There should exist a subdirectory "good". Read the doc of this function for further information.')
        exit()
    classes.sort()
    class_perm = list()
    class_idx = 1
    for cl in classes:
        if cl == 'good':
            class_perm.append(0)
        else:
            class_perm.append(class_idx)
            class_idx += 1

    transform_train = get_random_transforms()
    trainset = ImageFolderMultiTransform(data_dir_train, transform=transform_train, target_transform=train_target_transform, 
                                        n_transforms=c.n_transforms)
    testset = ImageFolderMultiTransform(data_dir_test, transform=transform_train, target_transform=target_transform,
                                        n_transforms=c.n_transforms_test)
    return trainset, testset


def make_dataloaders(trainset, testset):
    trainloader = torch.utils.data.DataLoader(trainset, pin_memory=True, batch_size=c.batch_size, shuffle=True,
                                              drop_last=False)
    testloader = torch.utils.data.DataLoader(testset, pin_memory=True, batch_size=c.batch_size_test, shuffle=True,
                                             drop_last=False)
    return trainloader, testloader


def preprocess_batch(data):
    '''move data to device and reshape image'''
    inputs, labels = data
    inputs, labels = inputs.to(c.device), labels.to(c.device)
    inputs = inputs.view(-1, *inputs.shape[-3:])
    return inputs, labels
