import os, sys
import os.path
import torch
import numpy as np
import cv2  

from torch.utils import data
from torch.autograd import Variable
from davis import DAVIS
from model import generate_model
import time

import subprocess as sp
import pickle


class Object():
    pass
opt = Object()
opt.crop_size = 512
opt.double_size = True if opt.crop_size == 512 else False
# DAVIS dataloader
DAVIS_ROOT = './DAVIS_demo'
DTset = DAVIS(DAVIS_ROOT, imset='2016/demo_davis.txt', 
              size=(opt.crop_size, opt.crop_size))
DTloader = data.DataLoader(DTset, batch_size=1, shuffle=False, num_workers=1)

opt.search_range = 4 # fixed as 4: search range for flow subnetworks
opt.pretrain_path = 'results/vinet_agg_rec/save_agg_rec_512.pth'
opt.result_path = 'results/vinet_agg_rec'

opt.model = 'vinet_final'
opt.batch_norm = False
opt.no_cuda = False # use GPU
opt.no_train = True
opt.test = True
opt.t_stride = 3
opt.loss_on_raw = False
opt.prev_warp = True
opt.save_image = True
opt.save_video = True
if opt.save_video:
    import pims


def createVideoClip(clip, folder, name, size=[512,512]):


    vf = clip.shape[0]
    '''
    command = [ 'ffmpeg',
    '-y',  # overwrite output file if it exists
    '-f', 'rawvideo',
    '-s', '%dx%d'%(size[1],size[0]), #'512x512', # size of one frame
    '-pix_fmt', 'rgb24',
    '-r', '15', # frames per second
    '-an',  # Tells FFMPEG not to expect any audio
    '-i', '-',  # The input comes from a pipe
    '-vcodec', 'libx264',
    '-b:v', '1500k',
    '-vframes', str(vf), # 5*25
    '-s', '%dx%d'%(size[1],size[0]), #'256x256', # size of one frame
    folder+'/'+name ]
    #sfolder+'/'+name 
    '''
    '''
    pipe = sp.Popen( command, stdin=sp.PIPE, stderr=sp.PIPE, shell=True)
    out, err = pipe.communicate(clip.tostring())
    #out, err = pipe.communicate(clip.tobytes())
    if pipe.returncode == 0:
        print("Job done")
    else:
        print("Error")
        print(out)
    pipe.wait()
    pipe.terminate()
    print(err)
    '''
    print("NAME VIDEO: ", name)

    frame = clip[0]
    height, width, layers = frame.shape
    print("height: {}. width: {}. layers: {}".format(height, width, layers))

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    video = cv2.VideoWriter(name, fourcc, 15, (width,height))

    #video = cv2.VideoWriter(name, 0, 1, (width,height))

    for image in clip:
        print(image.shape)
        video.write(image)
    print("Todas las imagenes escritas en video")

    cv2.destroyAllWindows()
    video.release()

def to_img(x):
    tmp = (x[0,:,0,:,:].cpu().data.numpy().transpose((1,2,0))+1)/2
    tmp = np.clip(tmp,0,1)*255.
    return tmp.astype(np.uint8)

def to_var(x, volatile=False):
    if torch.cuda.is_available():
        x = x.cuda()
    return Variable(x, volatile=volatile)

model, _ = generate_model(opt)
print('Number of model parameters: {}'.format(
      sum([p.data.nelement() for p in model.parameters()])))

model.eval()
ts = opt.t_stride
folder_name = 'davis_%d'%(int(opt.crop_size))
pre_run = 30

with torch.no_grad():
    for seq, (inputs, masks, info) in enumerate(DTloader):

        idx = torch.LongTensor([i for i in range(pre_run-1, -1, -1)])
        pre_inputs = inputs[:,:,:pre_run].index_select(2, idx)
        pre_masks = masks[:,:,:pre_run].index_select(2, idx)
        inputs = torch.cat((pre_inputs, inputs), 2)
        masks = torch.cat((pre_masks, masks), 2)

        bs = inputs.size(0)
        num_frames = inputs.size(2)
        seq_name = info['name'][0]

        save_path = os.path.join(opt.result_path, folder_name, seq_name)
        if not os.path.exists(save_path) and opt.save_image:
            os.makedirs(save_path)

        inputs = 2.*inputs - 1
        inverse_masks = 1-masks
        masked_inputs = inputs.clone()*inverse_masks

        masks = to_var(masks)
        masked_inputs = to_var(masked_inputs)
        inputs = to_var(inputs)

        total_time = 0.
        in_frames = []
        out_frames = []

        lstm_state = None

        for t in range(num_frames):
        #for t in range(int(num_frames/3)): #AUXILIAR
            masked_inputs_ = []
            masks_ = []        

            if t < 2 * ts:
                masked_inputs_.append(masked_inputs[0,:,abs(t-2*ts)])
                masked_inputs_.append(masked_inputs[0,:,abs(t-1*ts)])
                masked_inputs_.append(masked_inputs[0,:,t])
                masked_inputs_.append(masked_inputs[0,:,t+1*ts])
                masked_inputs_.append(masked_inputs[0,:,t+2*ts])
                masks_.append(masks[0,:,abs(t-2*ts)])
                masks_.append(masks[0,:,abs(t-1*ts)])
                masks_.append(masks[0,:,t])
                masks_.append(masks[0,:,t+1*ts])
                masks_.append(masks[0,:,t+2*ts])
            elif t > num_frames - 2 * ts - 1:
                masked_inputs_.append(masked_inputs[0,:,t-2*ts])
                masked_inputs_.append(masked_inputs[0,:,t-1*ts])
                masked_inputs_.append(masked_inputs[0,:,t])
                masked_inputs_.append(
                    masked_inputs[0,:,-1 -abs(num_frames-1-t - 1*ts)])
                masked_inputs_.append(
                    masked_inputs[0,:,-1 -abs(num_frames-1-t - 2*ts)])
                masks_.append(masks[0,:,t-2*ts])
                masks_.append(masks[0,:,t-1*ts])
                masks_.append(masks[0,:,t])
                masks_.append(masks[0,:,-1 -abs(num_frames-1-t - 1*ts)])
                masks_.append(masks[0,:,-1 -abs(num_frames-1-t - 2*ts)])   
            else:
                masked_inputs_.append(masked_inputs[0,:,t-2*ts])
                masked_inputs_.append(masked_inputs[0,:,t-1*ts])
                masked_inputs_.append(masked_inputs[0,:,t])
                masked_inputs_.append(masked_inputs[0,:,t+1*ts])
                masked_inputs_.append(masked_inputs[0,:,t+2*ts])
                masks_.append(masks[0,:,t-2*ts])
                masks_.append(masks[0,:,t-1*ts])
                masks_.append(masks[0,:,t])
                masks_.append(masks[0,:,t+1*ts])
                masks_.append(masks[0,:,t+2*ts])            

            masked_inputs_ = torch.stack(masked_inputs_).permute(
                1,0,2,3).unsqueeze(0)
            masks_ = torch.stack(masks_).permute(1,0,2,3).unsqueeze(0)

            start = time.time()
            if not opt.double_size:
                prev_mask_ = to_var(torch.zeros(masks_[:,:,2].size())) 
                # rec given when 256
            prev_mask = masks_[:,:,2] if t==0 else prev_mask_
            prev_ones = to_var(torch.ones(prev_mask.size()))
            if t == 0:
                prev_feed = torch.cat([masked_inputs_[:,:,2,:,:], prev_ones, 
                                       prev_ones*prev_mask], dim=1)
            else:
                prev_feed = torch.cat([outputs.detach().squeeze(2), prev_ones, 
                                       prev_ones*prev_mask], dim=1)
            outputs, _, _, _, _ = model(
                masked_inputs_, masks_, lstm_state, prev_feed, t)
            if opt.double_size:
                prev_mask_ = masks_[:,:,2]*0.5 # rec given whtn 512

            lstm_state = None
            end = time.time() - start
            if lstm_state is not None:
                lstm_state = repackage_hidden(lstm_state)

            total_time += end
            if t > pre_run:
                print('{}th frame of {} is being processed'.format(
                    t - pre_run, seq_name))
                out_frame = to_img(outputs)  
                if opt.save_image:            
                    cv2.imwrite(os.path.join(
                        save_path,'%05d.png'%(t - pre_run)), out_frame)
                out_frames.append(out_frame[:,:,::-1])

        if opt.save_video:
            final_clip = np.stack(out_frames)
            print("final clip: ", final_clip)
            print("===================================")
            print("Primer frame: ", out_frames[0])
            print("finalclip shape: ", final_clip.shape)

            video_path = os.path.join(opt.result_path, folder_name)
            if not os.path.exists(video_path):
                os.makedirs(video_path)

            createVideoClip(final_clip, video_path, '%s.mp4'%(
                seq_name), [opt.crop_size, opt.crop_size])
            print('Predicted video clip {} saving'.format(folder_name))   