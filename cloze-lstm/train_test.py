from model_harness import *
from net_def import *
import os

def create_config(window_size, batch_size=(1,)*3, **kwargs):
    return {
        "criterion": torch.nn.MSELoss(reduction='none'), "features": 24, "learning_rate": 0.002,
        "batch_size": batch_size, "hsize": 64, "window_size": window_size, "enc_nlayers": 6, 
        "dec_nlayers": 2, **kwargs 
    }

if __name__ == "__main__":
    # Set K = 1, 2, 4, 8, 12, and 24 for ablation
    features_per_decoder = int(os.environ.get("features_per_decoder", 1))
    # Set lookahead to 1, 2, 4, 8, 10 and 20 for different lookaheads 
    lookahead = int(os.environ.get("lookahead", 10))
    # Set sample_rate to 1, 30, 60, 120 and 240 for subsampling
    # Will run 80 epochs on full dataset, 240 on subsampled
    sample_rate = int(os.environ.get("sample_rate", 1))
    num_epochs = 80 if sample_rate == 1 else 240

    # Other parameters
    val_split, window_size, batch_size = 99438, 120, (1208,)*3
    tr_slice = slice(None, -val_split, sample_rate)
    val_slice = slice(-val_split, None, sample_rate)
    test_slice = slice(None, None, sample_rate)
    num_trials = int(os.environ.get('num_trials', 5))

    # Initialize data module for training and testing
    swat_hist = SWaTHistorianModule(
        window_size=window_size + lookahead - 1, batch_size=batch_size, num_workers=(0,0,0), 
        tr_slice=tr_slice, val_slice=val_slice, test_slice=test_slice
    )
    swat_hist.setup()
    config = create_config(
        window_size, batch_size, lookahead=lookahead, features_per_decoder=features_per_decoder
    )

    # Initialize data module with minimum supported window size (1) 
    # for measuring metrics without needing to change rest of code
    lt_hist = SWaTHistorianModule(
        window_size=1, batch_size=(1,)*3, num_workers=(0,0,0), 
        tr_slice=tr_slice, val_slice=val_slice, test_slice=test_slice
    )
    lt_hist.setup()
    config["test_metrics"] = Metrics(data_module=lt_hist, loader_type=Sources.TEST, data_range=test_slice)

    # Start
    for i in range(num_trials):
        model = ClozeLSTM(config)
        train_test(
            model=model, module=swat_hist, config=config, epochs=num_epochs, total_runs=1,
            log=False, fit=True, test=True, test_every=4, group=f"ClozeLSTM",
        );