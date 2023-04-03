import warnings
import matplotlib.pyplot as plt
import torch, wandb, enum
import plotly.express as px, pandas as pd
import numpy as np, pandas as pd, sklearn.metrics as metrics
import pytorch_lightning as pl
import torch.nn as nn
from typing import Union
from pathlib import Path
from pytorch_lightning.callbacks.model_checkpoint import ModelCheckpoint
from torch.utils.data import Dataset, DataLoader

use_cuda = 1 if torch.cuda.is_available() else 0
if(use_cuda):
    torch.cuda.init()

def historian_collate(data):
    x, y = zip(*data)
    return torch.stack(x, 1), torch.stack(y, 0).squeeze()
    
def patched_on_validation_epoch_start(self):
    self._validation_started = self._test_started = False
    print(f"Epoch: {self.current_epoch}, test_every_n: {self.test_every_n}")

def patched_validation_step(self, batch, batch_idx, dataloader_idx):
    if dataloader_idx == 0:
        if not self._validation_started:
            self.do_on_validation_epoch_start()
            self._validation_started = True
        return self.do_validation(batch, batch_idx)
    elif dataloader_idx == 1 and self.current_epoch % self.test_every_n == 0:
        if not self._test_started:
            self.on_test_epoch_start()
            self._test_started = True
        return self.test_step(batch, batch_idx)

def patched_validation_epoch_end(self, results):
    val_loop, test_loop = results
    on_vend = self.validation_end(val_loop)
    if len(test_loop):
        self.test_epoch_end(test_loop)
    return on_vend

def wrap_model(model, test_every=None):
    """Wraps a model so that it can be tested every N epochs"""

    if test_every:
        model.test_every_n = test_every
        model.do_validation = model.validation_step
        model.validation_end = model.validation_epoch_end
        model.do_on_validation_epoch_start = model.on_validation_epoch_start

        model.validation_step = patched_validation_step.__get__(model, model.__class__)
        model.validation_epoch_end = patched_validation_epoch_end.__get__(model, model.__class__)
        model.on_validation_epoch_start = patched_on_validation_epoch_start.__get__(model, model.__class__)
    return model

def unwrap_model(model):
    """Undoes the wrapping caused by `wrap_model`"""

    try:
        model.validation_step = model.do_validation
        model.validation_epoch_end = model.validation_end
        model.on_validation_epoch_start = model.do_on_validation_epoch_start
        del model.test_every_n, model._validation_started, model._test_started
    except AttributeError:
        pass
    return model

class TVTEnum(enum.IntEnum):
    TRAIN = 0
    VALIDATE = 1
    TEST = 2

class Projects(enum.Enum):
    DEFAULT = "swat_experiments"
    def __str__(self):
        return str(self.value)

class Sources(enum.Enum):
    TRAIN = "train"
    VALIDATION = "validation"
    TEST = "test"
    def __str__(self):
        return str(self.value)
    
class WindowUtils:
    @staticmethod
    def get_total_wsz(window_size):
        return torch.sum(window_size[:2]) - 1

    @staticmethod
    def parse_window_params(window_size):
        if(isinstance(window_size, slice)):
            out_window_size = [window_size.start, window_size.stop, window_size.step or 1]
        elif(isinstance(window_size, (list, torch.Tensor, np.ndarray))):
            out_window_size = window_size[:3]
        else:
            out_window_size = [int(window_size), 1, 1]
        return torch.as_tensor(out_window_size)
    
    @staticmethod
    def windowize(x, window_size):
        return x.unfold(0, WindowUtils.get_total_wsz(window_size)+1, window_size[2]).transpose(-2, -1)
    
    @staticmethod
    def parse_slice(data_range, data_len):
        if data_range is None:
            pass
        elif isinstance(data_range, slice):
            data_range = (
                data_range.start or 0, 
                data_range.stop if data_range.stop and data_range.stop > 0 else data_len + (data_range.stop or 0),
                data_range.step or 1
            )
        elif isinstance(data_range, (float, int)):
            data_range = [data_range, data_len, 1]
        else:
            data_range = (data_range[:3] + (data_len, 1))[:3] #defaults to [start, stop, step] of (start, len(), 1)
            data_range = (data_range[0] or 0, data_range[1] or data_len, data_range[2] or 1)
            
        if data_range is None:
            offset, step = 0, 1
        else:
            offset, step = data_range[0], data_range[2]
            if offset < 0:
                offset += data_len
            data_len = max(min(data_range[1], data_len) - offset, 0)
            
        return offset, data_len, step
    
class Metrics:
    def __init__(self, data_module, loader_type:Union['validation', 'test']=Sources.VALIDATION, data_range=None, use_actuals=True):
        # Validation metrics: uses same semantics but ground_truth is all 0s
        data_module.setup()
        if loader_type == Sources.TEST:
            loader = data_module.test_dataloader()
        elif loader_type == Sources.VALIDATION:
            loader = data_module.val_dataloader()
        
        self.mode = loader_type
        offset, data_len, data_step = WindowUtils.parse_slice(data_range, data_len=len(loader.dataset))
        ground_truth = data_module.get_attack_flags(self.mode).squeeze()
        window_size = data_module.get_window_size(loader_type)
        start_offset = offset + window_size[0]
        self.actuals = torch.cat([y for x, y in data_module.get_actuals()], 0) if use_actuals else None
        self.ground_truth = torch.as_tensor(ground_truth, dtype=torch.int)
        
    def get_prroc(self, model, preds, is_losses=False, loss_padding=0):
        """
        Gets the PR and ROC AUC for a model's predictions in the shape [batch, features].
        Returns the [(ROC, PR AUC), (FPR, TPR), (precision, recall) and num_elements]
        If is_losses is True, the predictions are assumed to be losses instead with shape [losses] or []
        """
        
        numel = len(preds)
        ground_truth = self.ground_truth[:numel] == 1
        if ground_truth.all() or not ground_truth.any(): #no attacks, or full of attacks - cannot compute ROC
            return (0, 0), (0, 0), (0, 0), numel
        losses = preds if is_losses else self.get_losses(preds.cpu(), self.actuals[:numel], model.criterion)
        roc_auc, (fpr, tpr) = self.generate_roc(losses, loss_padding=loss_padding)
        pr_auc, (pr, re) = self.generate_prc(losses, loss_padding=loss_padding)
        return (roc_auc, pr_auc), (fpr, tpr), (pr, re), numel
    
    def plot_prroc(self, pr_roc, model_name, return_plots=False, backend="px", log=True):
        """Plots the PR and ROC curves for a model's predictions in the shape [batch, features]"""
        
        (auc_roc, auc_prc), (fpr, tpr), (prec, recall), numel = pr_roc
        
        if (isinstance(fpr, int) and isinstance(tpr, int)) or (isinstance(prec, int) and isinstance(recall, int)):
            return
        
        ground_truth = self.ground_truth[:numel]
        no_skill = len(ground_truth[ground_truth == 1]) / len(ground_truth) # precision-recall for no-skill classifier
        if backend == "px":
            roc_curve = px.area(
                x=fpr, y=tpr, 
                title=f'{model_name} ROC Curve (AUC={auc_roc:.3f})',
                labels={"x":'False Positive Rate', "y":'True Positive Rate'}
            )
            roc_curve.add_shape(type='line', line={"dash":'dash'}, x0=0, x1=1, y0=0, y1=1)
            roc_curve.update_yaxes(scaleanchor="x", scaleratio=1)
            roc_curve.update_xaxes(constrain='domain')

            pr_curve = px.area(
                x=recall, y=prec,
                title=f'{model_name} PR Curve (AUC={auc_prc:.3f})',
                labels={"x":'Recall', "y":'Precision'}
            )
            pr_curve.add_shape(type='line', line={"dash":'dash'}, x0=0, x1=1, y0=no_skill, y1=no_skill)
            pr_curve.update_yaxes(scaleanchor="x", scaleratio=1)
            pr_curve.update_xaxes(constrain='domain')
            if log:
                try:
                    wandb.log({f"{self.mode} ROC": roc_curve})
                    wandb.log({f"{self.mode} PRC": pr_curve})
                    wandb.log({f"{self.mode} AUROC": auc_roc})
                    wandb.log({f"{self.mode} AUPRC": auc_prc})
                except:
                    warnings.warn("WandB was not initialized for this run.", RuntimeWarning)
        elif backend == "plt":
            # method II, use in Jupyter/interactive session
            fig, axes = plt.subplots(1, 2, figsize=(16, 4))
            roc_curve = axes[0]
            roc_curve.set_title(f"{model_name} ROC Curve (AUC={auc_roc:.3f})")
            roc_curve.plot(fpr, tpr)
            roc_curve.set_ylabel("True Positive Rate")
            roc_curve.set_xlabel("False Positive Rate")
            roc_curve.plot([0, 1], [0, 1],'r--')
            roc_curve.set_xlim([0, 1])
            roc_curve.set_ylim([0, 1])
            
            pr_curve = axes[1]
            pr_curve.set_title(f"{model_name} PR Curve (AUC={auc_prc:.3f})")
            pr_curve.plot(recall, prec)
            pr_curve.set_ylabel("Precision")
            pr_curve.set_xlabel("Recall")
            pr_curve.plot([0, 1], [no_skill, no_skill],'r--')
            pr_curve.set_xlim([0, 1])
            pr_curve.set_ylim([0, 1])
        else:
            return
        
        if return_plots:
            return pr_curve, roc_curve
        elif backend == "px":
            pr_curve.show()
            roc_curve.show()
        elif backend == "plt":
            plt.show()
    
    def get_losses(self, preds, acts, criterion=nn.MSELoss()):
        """Gets a list of losses based on the criterion, across time"""
    
        return torch.mean(self.get_multi_losses(preds, acts, criterion), dim=1)
    
    def get_multi_losses(self, preds, acts, criterion=nn.MSELoss()):
        """Gets a list of losses based on the criterion, across time for each feature"""
        
        old_reduction = criterion.reduction
        criterion.reduction = 'none'
        output = criterion(preds, acts)
        criterion.reduction = old_reduction
        
        return output
    
    def generate_roc(self, losses, loss_padding=0):
        ground_truth = self.ground_truth[:losses.shape[0]].clone()
        minlen = min(len(losses), len(ground_truth))
        ground_truth = ground_truth[:minlen]
        losses = losses[:minlen]
        if loss_padding > 0:
            ground_truth[:loss_padding] = 0
        fpr, tpr, threshold = metrics.roc_curve(ground_truth, losses)
        auc = np.abs(np.trapz(tpr, fpr))
        return auc, (fpr, tpr)

    def generate_prc(self, losses, loss_padding=0):
        ground_truth = self.ground_truth[:losses.shape[0]]
        minlen = min(len(losses), len(ground_truth))
        ground_truth = ground_truth[:minlen]
        losses = losses[:minlen]
        if loss_padding > 0:
            ground_truth[:loss_padding] = 0
        precision, recall, threshold = metrics.precision_recall_curve(ground_truth, losses)
        auc = np.abs(np.trapz(precision, recall))
        return auc, (precision, recall)

class WindowedDataset(Dataset):
    """Base window dataset class. Not meant to be instantiated directly."""
    
    def __init__(self, dataset, window_size, **kwargs):
        self.dataset = dataset
        self.set_window_size(window_size)
        self.use_float = kwargs.get("use_float", True)
        self.return_x, self.return_y = kwargs.get("return_x", True), kwargs.get("return_y", True)
        self.dlen = int((1 + (len(self.dataset) - torch.sum(self.window_size[:-1])) / self.window_size[-1]).long())
        
    def set_window_size(self, new_size):
        self.window_size = WindowUtils.parse_window_params(new_size)
    
    def _tensorize(self, data, use_float=False):
        if(isinstance(data, torch.Tensor)):
            return data
        elif(isinstance(data, pd.DataFrame)):
            #convert from dataframe
            return torch.as_tensor(data.to_numpy(dtype=np.float32 if use_float else np.float64))
        else:
            #create new tensor (requires more memory)
            return torch.as_tensor(data, dtype=torch.float if use_float else torch.double)
    
    def __getitem__(self, index):
        """Returns a tuple containing the idx-th window and its corresponding label"""
        
        if index < self.dlen:
            return self.get_window_at(index, self.window_size)
        raise StopIteration
    
    def __len__(self) -> int:
        return self.dlen
    
    def get_window_at(self, index, window_size):
        win, wout, wstep = self.window_size
        start = (index * wstep)
        in_end = (start + win)
        if self.return_x and self.return_y:
            return (
                self._tensorize(data=self.dataset[start:in_end], use_float=self.use_float), 
                self._tensorize(data=self.dataset[in_end:in_end + wout], use_float=self.use_float)
            )
        elif self.return_x:
            return (self._tensorize(data=self.dataset[start:in_end], use_float=self.use_float), None)
        elif self.return_y:
            return (None, self._tensorize(data=self.dataset[in_end:(in_end + wout)], use_float=self.use_float))
        return None
    
class HDFDataset(Dataset):
    def __init__(self, source_type, h5_path="~/data", use_float=True):
        """
        Parameters:
        -----------
        source_type: The dataset type (train, test, validation)
        
        h5_path: The default hdf5 path. Default "~/data/"
        
        Other Parameters:
        -----------------
        use_float: Whether to convert data to float after reading or not. Default True.
        """
        
        self.h5_path = h5_path
        self.use_float = use_float
        if(source_type == Sources.TEST):
            self.file_path = f"{self.h5_path}/test_dat.h5"
        else:
            self.file_path = f"{self.h5_path}/train_dat.h5"
            
class SWaTHistorianDataset(HDFDataset):
    def __init__(self, source_type, h5_path, **kwargs):
        use_float, use_diff = kwargs.get("use_float", True), kwargs.get("use_diff", False)
        super().__init__(source_type=source_type, h5_path=h5_path, use_float=use_float)
        
        window_size, range_slice = kwargs.get("window_size", None), kwargs.get("range_slice", None)
        pre_scaler = kwargs.get("pre_scaler", None)
        data_slice = kwargs.get("data_slice", None)
        self.att_flags = pd.read_hdf(self.file_path, key="att_flag").to_numpy(dtype=bool)
        self.data = pd.read_hdf(self.file_path, key="hist_data")
        self.return_label = None
        
        diff = int(use_diff)
        if data_slice is not None:
            self.data = self.data.iloc[data_slice]
            self.att_flags = self.att_flags.iloc[data_slice]
            
        if diff:
            self.data = self.data.diff(diff).dropna()
            self.att_flags = self.att_flags[diff:]
        self.data = self.data.to_numpy(dtype=np.float32 if self.use_float else np.float64)
        if range_slice:
            self.data = self.data[range_slice]
            self.att_flags = self.att_flags[range_slice]
            
        self.scaler = None
        if pre_scaler is not None:
            self.data = pre_scaler.transform(self.data)
        
        self.raw_data = self.data
        self.data = torch.as_tensor(self.data)
        self.att_flags = torch.as_tensor(self.att_flags)
        if window_size:
            self.set_window_size(window_size)
        
    def get_scaler(self):
        return self.scaler
    
    def set_window_size(self, window_size):
        self.return_label = True
        self.window_size = WindowUtils.parse_window_params(window_size)
        self.data, self.label = WindowUtils.windowize(self.data, self.window_size).split(self.window_size[:2].tolist(), dim=1)
        self.att_flags = WindowUtils.windowize(self.att_flags, self.window_size).squeeze()
        
    def __len__(self):
        return self.data.shape[0]
    
    def __getitem__(self, index):
        if self.return_label:
            return self.data[index], self.label[index]
        return self.data[index]
    
class SWaTHistorianModule(pl.LightningDataModule):
    """A DataModule containing historian data"""
    
    def __init__(self, root="~/data", **kwargs):        
        super().__init__()
        self._setup_train = self._setup_test = False
        self.root = root or kwargs.get("root", "~/data")
        self.use_cuda = torch.cuda.is_available()
        self.window_size = kwargs.pop("window_size")
        self.batch_size = list(kwargs.get("batch_size", (1,)*3))
        self.train_range_slice = kwargs.get("tr_slice", None)
        self.val_range_slice = kwargs.get("val_slice", None)
        self.test_range_slice = kwargs.get("test_slice", None)
        self.train_set = self.validation_set = self.test_set = None
        self.train_num_workers, self.val_num_workers, self.test_num_workers = kwargs.get("num_workers", (0, 0, 0))
        self.data_slice = kwargs.get("data_slice", None)
        self.drop_last = kwargs.get("drop_last", False)
        self.test_every = kwargs.get("test_every", None)
        self.use_diff = kwargs.get("use_diff", 0)
        
    def set_window_size(self, source, size):
        if self._setup_train and source == Sources.TRAIN:
            self.train_set.set_window_size(size)
        elif self._setup_train and source == Sources.VALIDATION:
            self.validation_set.set_window_size(size)
        elif self._setup_test and source == Sources.TEST:
            self.test_set.set_window_size(size)
    
    def get_window_size(self, source):
        if source == Sources.TRAIN:
            return self.train_set.window_size
        elif source == Sources.VALIDATION:
            return self.validation_set.window_size
        elif source == Sources.TEST:
            return self.test_set.window_size
        
    def get_actuals(self):
        if self._setup_test:
            return self.test_set
        
    def get_attack_flags(self, source):
        if self._setup_train and source == Sources.VALIDATION:
            return self.validation_set.att_flags
        elif self._setup_test and source == Sources.TEST:
            return self.test_set.att_flags
      
    def setup(self, stage=None):
        if not self._setup_train and (stage == 'fit' or stage is None):
            self.train_set = SWaTHistorianDataset(h5_path=self.root, use_diff=self.use_diff, source_type=Sources.TRAIN, data_slice=self.data_slice, window_size=self.window_size, range_slice=self.train_range_slice)
            self.batch_size[TVTEnum.TRAIN] = min(len(self.train_set), self.batch_size[TVTEnum.TRAIN])
            if self.val_range_slice is not None:
                self.validation_set = SWaTHistorianDataset(h5_path=self.root, use_diff=self.use_diff, source_type=Sources.VALIDATION, data_slice=self.data_slice, window_size=self.window_size, range_slice=self.val_range_slice, pre_scaler=self.train_set.get_scaler())
                self.batch_size[TVTEnum.VALIDATE] = min(len(self.validation_set), self.batch_size[TVTEnum.VALIDATE])
            self._setup_train = True

        if not self._setup_test and (stage == 'test' or stage is None):
            self.test_set = SWaTHistorianDataset(h5_path=self.root, use_diff=self.use_diff, source_type=Sources.TEST, data_slice=self.data_slice, window_size=self.window_size, range_slice=self.test_range_slice, pre_scaler=self.train_set.get_scaler())
            self.batch_size[TVTEnum.TEST] = min(len(self.test_set), self.batch_size[TVTEnum.TEST])
            self._setup_test = True
    
    def train_dataloader(self):
        if self.train_set is not None:
            return DataLoader(dataset=self.train_set, batch_size=self.batch_size[TVTEnum.TRAIN], collate_fn=historian_collate, pin_memory=self.use_cuda, drop_last=self.drop_last, num_workers=self.train_num_workers)
    
    def val_dataloader(self):
        val_dataloaders = []
        if self.validation_set is not None:
            val_dataloaders.append(DataLoader(dataset=self.validation_set, batch_size=self.batch_size[TVTEnum.VALIDATE], collate_fn=historian_collate, pin_memory=self.use_cuda, drop_last=self.drop_last, num_workers=self.val_num_workers))
        
        if self.test_every and self.test_set is not None:
            val_dataloaders.append(self.test_dataloader())
        
        return val_dataloaders
    
    def test_dataloader(self):
        if self.test_set is not None:
            return DataLoader(dataset=self.test_set, batch_size=self.batch_size[TVTEnum.TEST], collate_fn=historian_collate, pin_memory=self.use_cuda, drop_last=self.drop_last, num_workers=self.test_num_workers)
        
def train_test(model, module, config:dict, epochs:int, **kwargs):
    log = kwargs.get("log", False)
    silent = kwargs.get("silent", False)
    precision = kwargs.get("precision", 32)
    resume_id = kwargs.get("resume_id", None)
    project, fit, test = str(kwargs.get("project", Projects.DEFAULT)), kwargs.get("fit", True), kwargs.get("test", True)
    group = kwargs.get("group", "test" if log else None)
    save_every, test_every = kwargs.get("save_every", kwargs.get("save_every_n", 16)), kwargs.get("test_every", kwargs.get("test_every_n", 20))
    if test_every:
        if not silent:
            print(f"Wrapped model to test every {test_every} epochs")
        module.test_every = test_every
        model = wrap_model(model, test_every)
    extra_callbacks = kwargs.get("callbacks", [])
    resume_checkpoint = kwargs.get("resume_checkpoint", None)
    epoch_offset = torch.load(resume_checkpoint, map_location='cpu')['epoch'] if resume_checkpoint else 0
    filename = f"{model.model_name}_" + "{epoch}"
    catch_interrupts = kwargs.get("catch_interrupt", True)
    if kwargs.get("version", None):
        filename += f"_{kwargs['version']}"
    try:
        wandb_logger, experiment = None, None
        checkpoint, wandb_checkpoint = [], []
        if log:
            experiment = wandb.init(
                project=project, group=group, config=config, reinit=True, id=resume_id,
                resume="must" if resume_id else None
            )
            wandb_checkpoint = [ModelCheckpoint(
                dirpath=wandb.run.dir, filename=f"{model.model_name}_" + "{epoch}",
                save_top_k=-1, every_n_val_epochs=int(save_every//8), save_weights_only=True
            )]
            wandb_logger = pl.loggers.WandbLogger(experiment=experiment)
        if fit:
            checkpoint = [ModelCheckpoint(
                dirpath=f"{Path.home()}/models/checkpoints/{model.model_name}", filename=filename,
                save_top_k=-1, every_n_val_epochs=save_every, save_weights_only=True
            )]

        trainer = pl.Trainer(
            logger=wandb_logger, max_epochs=epochs+epoch_offset, num_sanity_val_steps=config.get("sanity_steps", 0),
            truncated_bptt_steps=config.get("truncated_bptt_steps", None), log_every_n_steps=3,
            flush_logs_every_n_steps=60, precision=precision, gpus=-1 if use_cuda else 0,
            amp_level=kwargs.get("amp_level", 'O2' if precision == 16 else None), progress_bar_refresh_rate=0 if silent else None, 
            weights_summary=None if silent else 'top', resume_from_checkpoint=resume_checkpoint, 
            callbacks=checkpoint + extra_callbacks + wandb_checkpoint
        )
        if fit:
            trainer.fit(model, datamodule=module)
        if test:
            trainer.test(model, datamodule=module)
        if experiment:
            experiment.finish()
    except KeyboardInterrupt:
        if not silent:
            print("Cancelling...")
        if not catch_interrupts:
            raise KeyboardInterrupt
        
    model = unwrap_model(model)
    if not silent:
        print("Unwrapped model successfully.")
    return model
