import torch
from torch import nn
from torch.nn import functional as F

class BasicBlock(nn.Module):
    def __init__(self, in_planes, out_planes, stride, dropRate=0.0):
        super(BasicBlock, self).__init__()
        self.bn1 = nn.BatchNorm2d(in_planes)
        self.relu1 = nn.ReLU(inplace=True)
        self.conv1 = nn.Conv2d(in_planes, out_planes, kernel_size=3, stride=stride,
                               padding=1, bias=False)
        self.bn2 = nn.BatchNorm2d(out_planes)
        self.relu2 = nn.ReLU(inplace=True)
        self.conv2 = nn.Conv2d(out_planes, out_planes, kernel_size=3, stride=1,
                               padding=1, bias=False)
        self.droprate = dropRate
        self.equalInOut = (in_planes == out_planes)
        self.convShortcut = (not self.equalInOut) and nn.Conv2d(in_planes, out_planes, kernel_size=1, stride=stride,
                                                                padding=0, bias=False) or None

    def forward(self, x):
        if not self.equalInOut:
            x = self.relu1(self.bn1(x))
        else:
            out = self.relu1(self.bn1(x))
        out = self.relu2(self.bn2(self.conv1(out if self.equalInOut else x)))
        if self.droprate > 0:
            out = F.dropout(out, p=self.droprate, training=self.training)
        out = self.conv2(out)
        return torch.add(x if self.equalInOut else self.convShortcut(x), out)


class VAE(nn.Module):
    def __init__(self, featureDim = 120*7*7, zDim = 256, dropRate = 0.0, channel = [16,60,120]):
        super(VAE, self).__init__()
        self.channel = channel
        featureDim = 7*7*channel[2]
        self.featureDim = featureDim
        self.in_layer = nn.Conv2d(1, channel[0], kernel_size=3, stride=1, padding=1, bias=False)
        self.enc_block1 = self._make_layer_encoder(2, in_planes=channel[0], out_planes=channel[1], stride=2)
        self.enc_block2 = self._make_layer_encoder(2, in_planes=channel[1], out_planes=channel[2], stride=2)
        self.norm = nn.BatchNorm2d(channel[2])
        self.encFC1 = nn.Linear(featureDim, zDim)
        self.encFC2 = nn.Linear(featureDim, zDim)

        self.decFC1 = nn.Linear(zDim, featureDim)
        self.dec_block1 = self._make_layer_decoder(2, in_planes=channel[2], out_planes=channel[1] ,stride=2)
        self.dec_block2 = self._make_layer_decoder(2, in_planes=channel[1], out_planes=channel[0], stride=2)
        self.out_layer = nn.Conv2d(channel[0], 1, kernel_size=3, stride=1, padding=1, bias=False)

        for m in self.modules():
            if isinstance(m, (nn.Conv2d)):
                nn.init.xavier_uniform_(m.weight.data)
            elif isinstance(m, nn.BatchNorm2d):
                nn.init.constant_(m.weight.data, 1)
                nn.init.constant_(m.bias.data, 0)
            elif isinstance(m, nn.Linear):
                nn.init.normal_(m.weight.data,0.0, 0.02)
                nn.init.zeros_(m.bias.data)

    def _make_layer_encoder(self, depth, in_planes, out_planes, stride, dropRate = 0.0):
        layers = []
        for i in range(depth):
            layers.append(BasicBlock(i == 0 and in_planes or out_planes, out_planes, i == 0 and stride or 1, dropRate))
        return nn.Sequential(*layers)
    
    def _make_layer_decoder(self, depth, in_planes, out_planes, stride):
        layers = []
        for i in range(depth):
            if i == 0 and stride != 1:
                layers.append(nn.ConvTranspose2d(in_planes, out_planes, kernel_size=3, stride=stride, padding=1, output_padding=1, bias=False))
                layers.append(nn.BatchNorm2d(out_planes))
                layers.append(nn.ReLU(inplace=True))
            else:
                layers.append(nn.Conv2d(i == 0 and in_planes or out_planes, out_planes, kernel_size=3, stride=1, padding=1, bias=False))
                layers.append(nn.BatchNorm2d(out_planes))
                layers.append(nn.ReLU(inplace=True))
            layers.append(nn.Conv2d(out_planes, out_planes, kernel_size=3, stride=1, padding=1, bias=False))
            layers.append(nn.BatchNorm2d(out_planes))
            layers.append(nn.ReLU(inplace=True))
        return nn.Sequential(*layers)

    def encoder(self, x):
        x = self.in_layer(x)
        x = self.enc_block1(x)
        x = self.enc_block2(x)
        x = F.relu(self.norm(x))
        x = x.view(-1, self.featureDim)
        mu = self.encFC1(x)
        logVar = self.encFC2(x)
        return mu, logVar, x

    def reparameterize(self, mu, logVar):
        #Reparameterization takes in the input mu and logVar and sample the mu + std * eps
        std = torch.exp(logVar/2)
        eps = torch.randn_like(std)
        return mu + std * eps

    def decoder(self, z):
        z = F.relu(self.decFC1(z))
        z = z.view(-1, self.channel[2], 7, 7)
        z = self.dec_block1(z)
        z = self.dec_block2(z)
        z = torch.sigmoid(self.out_layer(z))
        return z

    def forward(self, x):
        mu, logVar, x_ = self.encoder(x)
        z = self.reparameterize(mu, logVar)
        out = self.decoder(z)
        return out, mu, logVar, x_

    def re_forward(self, x):
        # x = x.view(-1, self.featureDim)
        mu = self.encFC1(x)
        logVar = self.encFC2(x)
        z = self.reparameterize(mu, logVar)
        out = self.decoder(z)
        return out

class classifier(nn.Module):
    def __init__(self, input_dim = 120, feature_dim=10):
        super(classifier, self).__init__()
        self.out_dim = input_dim*2
        self.in_layer = nn.Conv2d(input_dim, input_dim, kernel_size=3, stride=1, padding=1, bias=False)
        self.block1 = self._make_layer(2, input_dim, int(input_dim*2), 2)
        # self.block2 = self._make_layer(1, int(input_dim*2), self.out_dim, 2)
        self.bn = nn.BatchNorm2d(self.out_dim)
        self.relu = nn.ReLU(inplace=True)
        self.FC = nn.Linear(self.out_dim, 10)

        for m in self.modules():
            if isinstance(m, (nn.Conv2d)):
                nn.init.kaiming_normal_(m.weight)
                if m.bias is not None:
                    nn.init.constant_(m.bias, 0)
            elif isinstance(m, nn.BatchNorm2d):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)

    def _make_layer(self, depth, in_planes, out_planes, stride, dropRate = 0.0):
        layers = []
        for i in range(depth):
            layers.append(BasicBlock(i == 0 and in_planes or out_planes, out_planes, i == 0 and stride or 1, dropRate))
        return nn.Sequential(*layers)

    def forward(self, x):
        x = self.in_layer(x)
        x = self.block1(x)
        # x = self.block2(x)
        x = self.relu(self.bn(x))
        x = F.avg_pool2d(x, 4)
        x = x.view(-1, self.out_dim)
        x = self.FC(x)
        return x
