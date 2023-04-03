from model_harness import *

class ClozeDecoder(pl.LightningModule):
    def __init__(self, config):
        super().__init__()
        # Parameters
        features_per_decoder = config.get("features_per_decoder", 1)
        features, hsize = config.get("features", 24), config.get("hsize", 64)
        self.dec_nlayers = config.get("dec_nlayers", 2)
        self.num_decoders = num_decoders = features // features_per_decoder
        self.excess_features = features % features_per_decoder
        
        # Setup
        decoders, slices = [], []
        for k in range(num_decoders - 1):
            decoders.append(nn.LSTM(
                input_size=features - features_per_decoder, hidden_size=hsize,
                num_layers=self.dec_nlayers, dropout=0
            ))
            # Generate clozing slices - equivalent to running `torch.cat([x[:, :, :i], x[:, :, i+1:]], 2)`
            slices.append(torch.as_tensor([
                i for i in range(features) if i not in range(k * features_per_decoder, (k + 1) * features_per_decoder)
            ]))
        self.num_last_features = features - (features_per_decoder + self.excess_features)
        if self.num_last_features == 0:
            decoders.append(nn.LSTM(input_size=1, hidden_size=hsize, num_layers=self.dec_nlayers, dropout=0))
        else:
            decoders.append(nn.LSTM(
                input_size=self.num_last_features, hidden_size=hsize, num_layers=self.dec_nlayers, dropout=0
            ))
            slices.append(torch.as_tensor(list(range(0, self.num_last_features))))
        self.decoders = nn.ModuleList(decoders)
        self.slices = slices

    def forward(self, x, hiddens, mean_std, all_std):
        all_outs, num_layers = [], self.dec_nlayers
        # Use last layers of hidden and cell states from encoder for each decoder
        curr_hstate, curr_cstate = hiddens
        mod_cstate = curr_cstate[-num_layers:]
        for curr_decoder, curr_slice in zip(self.decoders, self.slices):
            if self.num_last_features == 0:
                # Since all features will be clozed and noise added to tensor of zeros,
                # initialize noise tensor here to save adding later
                corrupt_input = torch.normal(
                    torch.zeros(*x.shape[:2], 1).to(device=self.device), all_std.mean()
                )
            else:
                corrupt_input = x[:, :, curr_slice]
            
            mod_hstate = curr_hstate[-num_layers:] 
            corrupt_input = x[:, :, curr_slice].contiguous()
            if self.training:
                # Corrupt input when training
                mod_hstate = mod_hstate + torch.zeros_like(mod_hstate).normal_(0, mean_std)
                # Preconditioning corruption; cloze noise to match input shape
                # If last decoder is entirely clozed, do not add (more) noise to input
                if self.num_last_features != 0:
                    corrupt_input = corrupt_input + torch.normal(
                        torch.zeros_like(corrupt_input), all_std[:, curr_slice]
                    ).to(self.device)

            dec_out, _ = curr_decoder(corrupt_input, (mod_hstate, mod_cstate))
            # Add last timestep of current feature to feature list
            all_outs.append(dec_out[-1])

        # Combine all predicted features together
        return torch.cat(all_outs, 1)

class ClozeLSTM(pl.LightningModule):
    def __init__(self, config):
        super().__init__()
        
        # Parameters
        self.mode = TVTEnum.TEST
        features = config.get("features", 24)
        features_per_decoder = config.get("features_per_decoder", 1)
        self.batch_size = config.get("batch_size", (1208,)*3)
        self.learning_rate = config.get("learning_rate", 0.002)
        self.test_metrics = config.get("test_metrics", None)
        self.lookahead = config.get("lookahead", 10)
        self.window_size = config.get("window_size", 120)
        self.version = config.get("version", 0)
        self.hsize = config.get("hsize", 64)
        self.enc_nlayers = config.get("enc_nlayers", 6)
        
        self.encoder = nn.LSTM(
            input_size=features, hidden_size=self.hsize, num_layers=self.enc_nlayers, dropout=0
        )
        self.decoder = ClozeDecoder(config)
        self.output = nn.Sequential(
            nn.Linear(self.hsize * (features // features_per_decoder), features), nn.Tanh(), nn.Linear(features, features)
        )

        self.train_criterion = config.get("train_criterion", nn.MSELoss())
        self.criterion = config.get("test_criterion", config.get("criterion", nn.MSELoss(reduction='none')))
        self.model_name = config.get("model_name", f"ClozeLSTM")

    def reset_hidden_states(self, size=None):
        self.hiddens = (torch.zeros(size or (self.enc_nlayers, self.batch_size[self.mode], self.hsize), device=self.device),
                        torch.zeros(size or (self.enc_nlayers, self.batch_size[self.mode], self.hsize), device=self.device))
    
    def forward(self, enc_input, dec_input, mean_std, all_std):
        _, self.hiddens = self.encoder(enc_input, self.hiddens)
        return self.output(self.decoder(dec_input, self.hiddens, mean_std, all_std))
    
    def shared_step(self, batch):
        x, y = batch
        x = x[:self.window_size]
        self.reset_hidden_states(size=(self.enc_nlayers, x.shape[1], self.hsize))

        mean_std = x.detach().std(unbiased=True)
        all_std = x.detach().mean(1).std(0, unbiased=True).unsqueeze(0)
        self.hiddens = tuple(i.normal_(0, mean_std) for i in self.hiddens)
        y_hat = self.forward(x, x, mean_std, all_std)
        
        loss = self.train_criterion(y_hat, y) if self.training else self.criterion(y_hat, y)
        return loss, y_hat
    
    def on_train_epoch_start(self):
        self.mode = TVTEnum.TRAIN
    
    def training_step(self, batch, batch_idx):
        loss, _ = self.shared_step(batch)
        self.log('train_loss', loss.mean())
        return loss
       
    def on_validation_epoch_start(self):
        self.mode = TVTEnum.VALIDATE
    
    def validation_step(self, batch, batch_idx):
        loss, y_hat = self.shared_step(batch)
        self.log('val_loss', loss.mean())
        return loss

    def on_test_epoch_start(self):
        self.mode = TVTEnum.TEST
        
    def test_step(self, batch, batch_idx):
        return self.shared_step(batch)
    
    def test_epoch_end(self, outputs):
        losses, outs = zip(*outputs)
        outs = torch.cat(outs, 0).float().cpu()
        losses = torch.cat(losses, 0).float().cpu()
        # Ignore initial window by setting losses that occurred during 
        # it to 0; equivalent to no predictions during this period
        padding = torch.zeros(self.window_size + self.lookahead - 2, losses.shape[-1])
        losses = torch.cat([padding, losses], 0).mean(-1)
        ground_truth = self.test_metrics.ground_truth[:len(losses)]
        pr_roc = self.test_metrics.get_prroc(self, losses, is_losses=True, loss_padding=len(padding))
        self.test_metrics.plot_prroc(pr_roc, self.model_name, return_plots=False)
        
    def configure_optimizers(self):
        return torch.optim.Adam(self.parameters(), lr=self.learning_rate)