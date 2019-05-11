"""
********************************
*   Created by mohammed-alaa   *
********************************
Here I'm training motion stream CNN in the following steps:
1. load configs from configs.motion_configs (indicating architecture/optimizer/lr/pretrained..)
2. initialize your dataloader >> feeding the data efficiently to the model
3. load the latest snapshot of the model from drive (It's public and will be downloaded for you)..
note: folders are identified on my drive with their experiment_identifier
      for example heavy-mot-xception-adam-1e-05-imnet is (heavy augmentation,motion stream,xception architecture,adam optimizer with lr = 1e-05 pretrained on imagenet)
      this long experiment_identifier is given to drive manager and downloaded automatically and continue training from that checkpoint
      view my experiments :https://drive.google.com/drive/folders/1B82anWV8Mb4iHYmOp9tIR9aOTlfllwsD
      to make your own experiments on your drive you will need to modify DriveManager at utils.drive_manager and use some other long experiment_identifier
      for example make this personal.heavy-mot-xception-adam-1e-05-imnet as suffix at line 31

4. As the checkpoint is downloaded or not found the trainer will start from scratch or to continue from where it stopped (the checkpoint)

note: validation is done by MotionValidationCallback which validates on the given dataset evaluation section
"""
from functools import partial
from time import time
from keras.callbacks import TensorBoard
import frame_dataloader
import utils.training_utils as eval_globals
from configs.motion_configs import *
from evaluation import legacy_load_model, get_batch_size
from evaluation.evaluation import *
from models.motion_models import *
from utils import log, get_augmenter_text
from utils.drive_manager import DriveManager

################################################################################
"""Files, paths & identifier"""
suffix = "hater"  # put your name or anything(your crush :3) :D
experiment_identifier = suffix + ("" if suffix == "" else "-") + get_augmenter_text(augmenter_level) + "-mot-" + model_name + "-" + ("adam" if is_adam else "SGD") + "-" + str(lr) + "-" + ("imnet" if pretrained else "scrat")
log_file = "motion.log"
log_stream = open("motion.log", "a")
h5py_file = "motion.h5"
pred_file = "motion.preds"
################################################################################
"""Checking latest"""
print(experiment_identifier)
num_actions = 10
print("Number of workers:", workers, file=log_stream)
drive_manager = DriveManager(experiment_identifier)
checkpoint_found, zip_file_name = drive_manager.get_latest_snapshot()
################################################################################
# you need to send it as callback before keras reduce on plateau
MotionValidationCallback = partial(eval_globals.get_validation_callback,
                                   log_stream=log_stream,
                                   validate_every=validate_every,
                                   testing_samples_per_video=testing_samples_per_video,
                                   pred_file=pred_file, h5py_file=h5py_file, drive_manager=drive_manager, log_file=log_file)

data_loader = partial(frame_dataloader.MotionDataLoader,
                      testing_samples_per_video=testing_samples_per_video,
                      augmenter_level=augmenter_level,
                      log_stream=log_stream, stacked_frames=stacked_frames)

if checkpoint_found:
    # restore the model from the checkpoint
    log("Model restored")
    eval_globals.best_video_level_accuracy_1 = float(zip_file_name.split("-")[1])
    log("Current Best", eval_globals.best_video_level_accuracy_1)

    motion_model_restored = legacy_load_model(filepath=h5py_file, custom_objects={'sparse_categorical_cross_entropy_loss': sparse_categorical_cross_entropy_loss, "acc_top_1": acc_top_1, "acc_top_5": acc_top_5})
    # init data loader
    train_loader, test_loader, test_video_level_label = data_loader(width=int(motion_model_restored.inputs[0].shape[1]),
                                                                    height=int(motion_model_restored.inputs[0].shape[2]),
                                                                    batch_size=get_batch_size(motion_model_restored,
                                                                                              spatial=False)).run()
    tensorboard = TensorBoard(log_dir="./logs/{}".format(time()))
    # training
    motion_model_restored.fit_generator(train_loader,
                                        steps_per_epoch=len(train_loader),  # generates a batch per step
                                        epochs=epochs,
                                        use_multiprocessing=True, workers=workers,
                                        # validation_data=gen_test(), validation_steps=len(test_loader.dataset)
                                        callbacks=[tensorboard , MotionValidationCallback(model=motion_model_restored, test_loader=test_loader, test_video_level_label=test_video_level_label),  # returns callback instance
                                                   keras.callbacks.ReduceLROnPlateau(monitor='val_loss', patience=validate_every, verbose=1)],
                                        initial_epoch=int(zip_file_name.split("-")[0]))  # get epoch number

else:
    # init the model from scratch
    log("Starting from scratch")

    if model_name == "resnet":
        model = ResNet50MotionCNN(num_classes=num_actions,
                                  is_tesla_k80=is_tesla_k80,
                                  pre_trained=True if pretrained else False,
                                  stacked_frames=stacked_frames)
    elif model_name == "xception":
        model = XceptionMotionCNN(num_classes=num_actions,
                                  is_tesla_k80=is_tesla_k80,
                                  pre_trained=True if pretrained else False,
                                  stacked_frames=stacked_frames)

    # noinspection PyUnboundLocalVariable
    keras_motion_model = model.get_keras_model()

    # init data loader
    train_loader, test_loader, test_video_level_label = data_loader(**model.get_loader_configs()).run()  # batch_size, width , height)

    keras_motion_model.compile(optimizer=keras.optimizers.Adam(lr=lr) if is_adam else keras.optimizers.SGD(lr=lr, momentum=0.9),
                               loss=sparse_categorical_cross_entropy_loss,
                               metrics=[acc_top_1, acc_top_5])

    keras_motion_model.summary(print_fn=lambda *args: print(args, file=log_stream))
    keras_motion_model.summary()
    log_stream.flush()
    tensorboard = TensorBoard(log_dir="./logs/{}".format(time()))
    # training
    keras_motion_model.fit_generator(train_loader,
                                     steps_per_epoch=len(train_loader),  # generates a batch per step
                                     epochs=epochs,
                                     use_multiprocessing=True, workers=workers,
                                     # validation_data=gen_test(), validation_steps=len(test_loader.dataset)
                                     callbacks=[tensorboard , MotionValidationCallback(model=keras_motion_model, test_loader=test_loader, test_video_level_label=test_video_level_label),  # returns callback instance
                                                keras.callbacks.ReduceLROnPlateau(monitor='val_loss', patience=validate_every * 10, verbose=1)],
                                     )
