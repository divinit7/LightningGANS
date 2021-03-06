import os

from argparse import ArgumentParser, Namespace
from collections import OrderedDict

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F 
import torchvision
import torchvision.transforms as transforms

from torchvision.datasets import MNIST
from torch.utils.data import DataLoader

from pytorch_lightning.core import LightningModule
from pytorch_lightning.trainer import Trainer

class Generator(nn.Module):
    def __init__(self, latent_dim, img_shape):
        super(Generator, self).__init__()
        self.img_shape = img_shape

        def block(in_feat, out_feat, normalize = True):
            layers = [nn.Linear(in_feat, out_feat)]
            if normalize:
                layers.append(nn.BatchNorm1d(out_feat, 0.8))
            layers.append(nn.LeakyReLU(0.2, inplace = True))
            return layers

        self.model = nn.Sequential(
            *block(latent_dim, 128, normalize=False),
            *block(128, 512),
            *block(512, 1024),
            nn.Linear(1024, int(np.prod(img_shape))),
            nn.Tanh()
        )
    
    def forward(self, z):
        img = self.model(z)
        img = img.view(img.shape[0], *self.img_shape)
        return img

class Discriminator(nn.Module):
    def __init__(self, img_shape):
        super(Discriminator, self).__init__()

        self.model = nn.Sequential(
            nn.Linear(int(np.prod(img_shape)), 512),
            nn.LeakyReLU(0.2, inplace = True),
            nn.Linear(512, 256),
            nn.LeakyReLU(0.2, inplace = True),
            nn.Linear(256, 1),
        )
    
    def forward(self, img):
        img_flat = img.view(img.shape[0], -1)
        validity = self.model(img_flat)
        return validity

class WGAN(LightningModule):
    def __init__(self,
                latent_dim=100,
                lr = 0.0003,
                b1 = 0.5,
                b2 = 0.999,
                batch_size = 64,
                **kwargs
                ):
        super().__init__()

        self.save_hyperparameters()

        self.latent_dim = latent_dim
        self.lr = lr
        self.b1 = b1
        self.b2 = b2
        self.batch_size = batch_size

        mnist_shape = (1, 28, 28)
        self.generator = Generator(latent_dim=self.latent_dim, img_shape=mnist_shape)

        self.discriminator = Discriminator(img_shape=mnist_shape)

        self.validation_z = torch.randn(8, self.latent_dim)

        self.example_input = torch.zeros(2, self.latent_dim)

    def forward(self, z):
        return self.generator(z)

    def training_step(self, batch, batch_idx, optimizer_idx):
        imgs, _ = batch

        z = torch.randn(imgs.shape[0], self.latent_dim)
        z = z.type_as(imgs)

        clip_value = 0.01

        # train generator
        if optimizer_idx == 0:
            self.generated_imgs = self(z)

            # log sampled imgs
            sample_imgs = self.generated_imgs[:6]
            grid = torchvision.utils.make_grid(sample_imgs)
            self.logger.experiment.add_image('generated images', grid, 0)

            # grounf truth result
            valid = torch.ones(imgs.size(0), 1)
            valid = valid.type_as(imgs)

            # adversarial loss is binary cross entropy
            g_loss = -torch.mean(self.discriminator(self(z)))
            tqdm_dict = {'g_loss': g_loss}
            output = OrderedDict(
                {
                    'loss': g_loss,
                    'progress_bar': tqdm_dict,
                    'log': tqdm_dict
                }
            )
            return output

        elif optimizer_idx == 1:
            d_loss = -torch.mean(self.discriminator(imgs) + torch.mean(self.discriminator(self(z))))

            for p in self.discriminator.parameters():
                p.data.clamp_(-clip_value, clip_value)

            tqdm_dict = {'d_loss': d_loss}
            output = OrderedDict({
                'loss': d_loss,
                'progress_bar': tqdm_dict,
                'log': tqdm_dict
            })
            return output

    def configure_optimizers(self):
        n_critic = 5

        lr = self.lr
        b1 = self.b1
        b2 = self.b2

        opt_g = torch.optim.Adam(self.generator.parameters(), lr=lr, betas=(b1, b2))
        opt_d = torch.optim.Adam(self.discriminator.parameters(), lr=lr, betas=(b1, b2))
        return (
            {'optimizer': opt_g, 'frequency': 1},
            {'optimizer': opt_d, 'frequency': n_critic}
        )

    def train_dataloader(self):
        transform = transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize([0.5], [0.5]),
        ])
        dataset = MNIST(os.getcwd(), train = True, download = True, transform = transform)
        return DataLoader(dataset, batch_size=self.batch_size)

    def on_epoch_end(self):
        z = self.validation_z.to(self.device)

        sample_imgs = self(z)
        grid = torchvision.utils.make_grid(sample_imgs)
        self.logger.experiment.add_image('generated_images', grid, self.current_epoch)


def main(args: Namespace) -> None:
    # init
    model = WGAN(**vars(args))

    trainer = Trainer(max_epochs = 20,gpus = args.gpus)

    trainer.fit(model)

if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument("--gpus", type=int, default=0, help="number of GPUs")
    parser.add_argument("--batch_size", type=int, default=64, help="size of the batches")
    parser.add_argument("--lr", type=float, default=0.0002, help="adam: learning rate")
    parser.add_argument("--b1", type=float, default=0.5,
                        help="adam: decay of first order momentum of gradient")
    parser.add_argument("--b2", type=float, default=0.999,
                        help="adam: decay of first order momentum of gradient")
    parser.add_argument("--latent_dim", type=int, default=100,
                        help="dimensionality of the latent space")

    hparams = parser.parse_args()

    main(hparams)





