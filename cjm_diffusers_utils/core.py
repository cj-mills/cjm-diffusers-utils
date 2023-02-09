# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/00_core.ipynb.

# %% auto 0
__all__ = ['pil_to_latent', 'latent_to_pil', 'text_to_emb', 'prepare_noise_scheduler', 'prepare_depth_mask', 'denoise_depth2img']

# %% ../nbs/00_core.ipynb 3
# Import necessary modules from the standard library
from pathlib import Path  # For working with file paths

from PIL import Image  # For working with images

import torch  # PyTorch module for deep learning
from torchvision import transforms  # PyTorch module for image transformations

# Import diffusers AutoencoderKL
from diffusers import AutoencoderKL

# %% ../nbs/00_core.ipynb 6
def pil_to_latent(image:'Image', # The image to be converted to latents.
                  vae:'AutoencoderKL' # The VAE model used to convert the image to latents.
                 ):
    """
    This function converts an image to latents using a VAE model.
    
    Returns:
    latents (torch.Tensor): The latents generated from the image.
    """
    
    # Convert the image to a tensor
    img_tensor = transforms.ToTensor()(image)[None]
    
    # Normalize the tensor
    img_tensor = (img_tensor - img_tensor.min()) / (img_tensor.max() - img_tensor.min())*2 - 1
    
    # Move the tensor to the correct device and type
    img_tensor = img_tensor.to(vae.device).type(vae.dtype)
    
    # Encode the image tensor to latents using the VAE model
    with torch.no_grad():
        latent = vae.encode(img_tensor)
    
    # Return the latents
    return 0.18215 * latent.latent_dist.sample()

# %% ../nbs/00_core.ipynb 16
def latent_to_pil(latents:'torch.Tensor', # The latents to be converted to an image.
                  vae:'AutoencoderKL' # The VAE model used to convert the latents to an image.
                 ):
    """
    This function converts latents to an image using a VAE model.
    
    Returns:
    image (PIL.Image): The image generated from the latents.
    """
    
    # Decode the latents using the VAE model
    with torch.no_grad(): 
        img_tensor = vae.decode(1 / 0.18215 * latents).sample.squeeze()
    
    # Convert the tensor to a numpy array
    image = (img_tensor/2+0.5).clamp(0,1).detach().cpu().permute(1, 2, 0).numpy()

    # Convert the numpy array to a PIL image
    return Image.fromarray((image*255).round().astype("uint8"))

# %% ../nbs/00_core.ipynb 20
# Import the `CLIPTextModel`, `CLIPTokenizer`
from transformers import CLIPTextModel, CLIPTokenizer

# %% ../nbs/00_core.ipynb 21
def text_to_emb(prompt:str, # The text prompt to be encoded.
                tokenizer:CLIPTokenizer, # The tokenizer to be used.
                text_encoder:CLIPTextModel, # The text encoder to be used.
                negative_prompt:str="", # The negative text prompt to be encoded.
                maxlen:int=None # The maximum length of the encoded text. Default is None.
               ):
    """Encodes the provided text prompts using the specified text encoder.
    
    Returns:
        torch.Tensor: The encoded text.
    """
    
    # Set the maximum length to the maximum length supported by the tokenizer if not specified
    if maxlen is None: maxlen = tokenizer.model_max_length
        
    # Tokenize the prompts
    inp = tokenizer(
        [negative_prompt, prompt],
        padding="max_length",
        max_length=maxlen,
        truncation=True,
        return_tensors="pt",
    )
    
    # Move the input IDs to the device used by the text encoder
    input_ids = inp.input_ids.to(text_encoder.device)
    
    # Encode the text using the specified text encoder
    return text_encoder(input_ids)[0]

# %% ../nbs/00_core.ipynb 31
from diffusers import DEISMultistepScheduler

# %% ../nbs/00_core.ipynb 32
def prepare_noise_scheduler(noise_scheduler, # The noise scheduler object to be modified
                            max_steps:int=50, # The maximum number of steps
                            noise_strength:float=1.0 # The strength of the noise
                           ):
    
    """
    Prepare the noise scheduler by setting the timesteps and adjusting the noise strength.
    
    Returns:
    noise_scheduler (object): The modified noise scheduler object
    """
    
    # Initialize the timestep by calculating the maximum number of steps minus the minimum value between
    # the product of max_steps and noise_strength and max_steps
    init_timestep = max(max_steps - min(int(max_steps * noise_strength), max_steps), 0)
    
    # Set the timesteps of the noise scheduler to the max_steps
    noise_scheduler.set_timesteps(max_steps)

    # Assign the remaining timesteps to the noise scheduler
    noise_scheduler.timesteps = noise_scheduler.timesteps[init_timestep:]
    
    # Return the modified noise scheduler
    return noise_scheduler

# %% ../nbs/00_core.ipynb 38
def prepare_depth_mask(depth_map, # The depth map image
                       divisor=8  # The divisor value used to resize the depth map
                      ):
    """
    Prepare the depth mask by resizing and normalizing the depth map.
    
    Returns:
    depth_mask (torch.Tensor): The normalized and resized depth mask
    """
    # Convert the depth map image to grayscale
    depth_mask = depth_map.convert("L")
    
    # Resize the depth map by dividing the width and height by the divisor
    depth_mask = depth_mask.resize([d//divisor for d in depth_map.size], resample=Image.Resampling.NEAREST)
    
    # Convert the image to a tensor and add batch dimension
    depth_mask = transforms.ToTensor()(depth_mask)[None]
    
    # Normalize the depth mask values to a range of -1 to 1
    depth_mask = (depth_mask - depth_mask.min()) / (depth_mask.max() - depth_mask.min())*2 - 1
    
    return depth_mask

# %% ../nbs/00_core.ipynb 43
from diffusers import UNet2DConditionModel
from tqdm.auto import tqdm

# %% ../nbs/00_core.ipynb 44
def denoise_depth2img(latents:torch.Tensor, # The initial image latents
                      depth_mask:torch.Tensor, # The image depth mask
                      text_emb:torch.Tensor, # The embedded text prompt and negative prompt 
                      unet:UNet2DConditionModel, # The Unet denoiser
                      noise_scheduler, # The noise scheduler
                      guidance_scale:float=8.0): # The guidance scale
        
    """
    Generate an image from a given initial image, depth map and prompt.
    """
    
    # Denoising loop
    for i,ts in enumerate(tqdm(noise_scheduler.timesteps)):
        
        # Scale latents
        inp = noise_scheduler.scale_model_input(torch.cat([latents] * 2), ts)
        # Add depth mask
        inp = torch.cat([inp, torch.cat([depth_mask]*2)], dim=1)
              
        # Get model output
        with torch.no_grad(): 
            noise_pred_uncond, noise_pred_text = unet(inp, ts, encoder_hidden_states=text_emb).sample.chunk(2)
        
        # Apply guidance
        noise_pred = noise_pred_uncond + guidance_scale*(noise_pred_text-noise_pred_uncond)
        
        # Update latents
        latents = noise_scheduler.step(noise_pred, ts, latents).prev_sample
        
        # Releases all unoccupied cached memory
        if unet.device.type == 'cuda': torch.cuda.empty_cache()
    
    return latents
