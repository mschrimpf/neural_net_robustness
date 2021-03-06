import argparse
import glob
import os
import pickle
import shutil
import tarfile
import xml.etree.ElementTree as xml
from urllib.request import urlretrieve

import functools

from net import vgg16, vgg19, resnet50, inceptionv3


def __retrieve_tarred_content(remote_url, local_path):
    assert remote_url.endswith(".tar.gz") or remote_url.endswith(".tar")
    if os.path.exists(local_path):
        print("Not downloading %s - local path %s already exists" % (remote_url, local_path))
        return
    tar_path = "%s.%s" % (local_path, "tar.gz" if remote_url.endswith(".tar.gz") else "tar")
    __download_if_needed(tar_path, functools.partial(__download_from_url, url=remote_url))
    __extract_tar(tar_path, local_path)


def __download_if_needed(local_path, retrieve):
    download_needed = not os.path.isfile(local_path)
    if download_needed:
        print("Retrieving %s..." % local_path)
        retrieve(local_path=local_path)
    else:
        print("Not downloading %s (exists already)" % local_path)
    return download_needed


def __download_from_url(url, local_path):
    filepart_path = "%s.filepart" % local_path
    urlretrieve(url, filepart_path)
    shutil.move(filepart_path, local_path)


def __find_keras_weights(weights_prefix):
    weights_directory = os.path.expanduser("~/.keras/models")
    weights_files = [f for f in os.listdir(weights_directory) if f.startswith(weights_prefix)]
    assert len(weights_files) is 1
    return os.path.join(weights_directory, weights_files[0])


def __load_keras_model(model_builder, local_path):
    model = model_builder(weights='imagenet')
    weights_path = __find_keras_weights(model.name)
    shutil.move(weights_path, local_path)


def __extract_tar(filepath, target_directory="."):
    print("Untarring %s to %s..." % (filepath, target_directory))
    tar = tarfile.open(filepath, "r:gz" if filepath.endswith(".tar.gz") else "r:")
    tar.extractall(target_directory)
    tar.close()
    os.remove(filepath)


def __download_dataset(dataset, data_urls, convert_truths, collect_image_files, datasets_directory="datasets"):
    dataset_directory = os.path.join(datasets_directory, dataset)
    os.makedirs(dataset_directory, exist_ok=True)
    for data_type, data_url in data_urls.items():
        datatype_directory = os.path.join(dataset_directory, data_type)
        truths_filepath = os.path.join(datatype_directory, "ground_truths.p")
        images_directory = os.path.join(datatype_directory, "images")
        if os.path.isfile(truths_filepath) and os.path.isdir(images_directory):
            print("Skipping %s/%s - truths file and images directory exist" % (dataset, data_type))
            continue
        print("Retrieving %s/%s..." % (dataset, data_type))
        compressed_directory = os.path.join(datasets_directory, dataset, data_type + "_compressed")
        __retrieve_tarred_content(data_url, compressed_directory)

        # truths
        if os.path.isfile(truths_filepath):
            print("Skipping truths for %s/%s - file %s already exists" % (dataset, data_type, truths_filepath))
        else:
            print("Converting truths for %s/%s" % (dataset, data_type))
            truths = convert_truths(compressed_directory, data_type)
            assert truths, "No truths converted"
            os.makedirs(datatype_directory, exist_ok=True)
            pickle.dump(truths, open(truths_filepath, 'wb'))

        # images
        if os.path.isdir(images_directory):
            print("Skipping images for %s/%s - directory %s already exists" % (dataset, data_type, images_directory))
        else:
            print("Collecting images for %s/%s" % (dataset, data_type))
            images_source_directory, image_files = collect_image_files(compressed_directory)
            assert image_files, "No images found"
            assert len(image_files) == len(truths), \
                "Number of images (%d) differs from truths (%d)" % (len(image_files), len(truths))
            images_truths_diffs = set(image_files) - set(truths.keys())
            truths_images_diffs = set(truths.keys()) - set(image_files)
            assert not images_truths_diffs and not truths_images_diffs, \
                "image files and truths keys differ: only in images %s | only in truths %s" % (
                    ', '.join(images_truths_diffs), ', '.join(truths_images_diffs))
            os.makedirs(images_directory)
            for image_file in image_files:
                shutil.move(os.path.join(images_source_directory, image_file),
                            os.path.join(images_directory, image_file))
            shutil.rmtree(compressed_directory)


def __collect_images(images_directory, filetype):
    images_directory = os.path.realpath(images_directory)
    image_files = glob.glob(os.path.join(images_directory, "*." + filetype))
    return images_directory, [filepath[len(images_directory) + 1:] for filepath in image_files]


def __collect_imagenet2012_images(dataset_directory):
    _, data_type = os.path.split(dataset_directory)
    if data_type.startswith("train"):
        tarred_images = glob.glob(os.path.join(dataset_directory, "*.tar"))
        assert tarred_images, "No tarred images found"
        for tar in tarred_images:
            __extract_tar(tar, dataset_directory)
    return __collect_images(dataset_directory, "JPEG")


def __convert_voc_truths(dataset_directory):
    assert os.path.isdir(dataset_directory)
    xml_files = glob.glob("%s/*.xml" % dataset_directory)
    truths = {}
    for file in xml_files:
        contents = xml.parse(file)
        filename = contents.find("filename").text
        object_name = contents.find("./object/name").text
        truths[filename] = object_name
    return truths


def __convert_imagenet2012_truths(dataset_directory, data_type):
    parent_directory, _ = os.path.split(dataset_directory)
    _, dataset = os.path.split(parent_directory)
    assert dataset == 'ILSVRC2012'
    assert data_type in ['train', 'val', 'test']
    annotations_path = os.path.join(parent_directory, "annotations")
    __retrieve_tarred_content("http://dl.caffe.berkeleyvision.org/caffe_ilsvrc12.tar.gz", annotations_path)
    truths = {}
    with open(os.path.join(annotations_path, data_type + ".txt")) as annotations_file:
        for line in annotations_file.readlines():
            filename, truth = line.split(" ")
            truths[filename] = truth
    return truths


if __name__ == '__main__':
    # params - command line
    parser = argparse.ArgumentParser(description='Neural Net Robustness - Download Data')
    parser.add_argument('--datasets_directory', type=str, default='datasets',
                        help='The directory for the datasets')
    parser.add_argument('--weights_directory', type=str, default='weights',
                        help='The directory for the weights')
    args = parser.parse_args()
    print('Running with args', args)

    # weights
    __download_if_needed(os.path.join(args.weights_directory, "alexnet.h5"),
                         functools.partial(__download_from_url,
                                           url="http://files.heuritech.com/weights/alexnet_weights.h5"))
    for model_builder in [vgg16, vgg19, resnet50, inceptionv3]:
        __download_if_needed(os.path.join(args.weights_directory, model_builder.__name__ + ".h5"),
                             functools.partial(__load_keras_model, model_builder=model_builder))

    # datasets
    imagenet_urls = pickle.load(open(os.path.join(args.datasets_directory, 'ILSVRC2012_image_urls.p'), 'rb'))
    if not imagenet_urls:
        print("Due to copyright constraints, ILSVRC2012 image urls must not be distributed. "
              "Please pickle-dump a dictionary of the form {'train': <train_images_url.tar>, 'val': ..., 'test': ...} "
              "to datasets/ILSVRC2012_image_urls.p")
    else:
        __download_dataset("ILSVRC2012", datasets_directory=args.datasets_directory,
                           data_urls=imagenet_urls,
                           convert_truths=__convert_imagenet2012_truths,
                           collect_image_files=__collect_imagenet2012_images)

    __download_dataset("VOC2012", datasets_directory=args.datasets_directory,
                       data_urls={
                           'train': 'http://host.robots.ox.ac.uk/pascal/VOC/voc2012/VOCtrainval_11-May-2012.tar',
                           'val': 'http://host.robots.ox.ac.uk/pascal/VOC/voc2012/VOCtrainval_11-May-2012.tar'},
                       convert_truths=lambda dataset_directory, _:
                       __convert_voc_truths(os.path.join(dataset_directory, "VOCdevkit", "VOC2012", "Annotations")),
                       collect_image_files=lambda dataset_directory:
                       __collect_images(os.path.join(dataset_directory, "VOCdevkit", "VOC2012", "JPEGImages"), "jpg"))
