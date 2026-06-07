import os
import torch

try:
    from safetensors.torch import load_file as load_safetensors
except ImportError:
    load_safetensors = None

def inspect_keys():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    adapter_dir = os.path.join(current_dir, "gemma-4-e4b-aira-lora")
    
    # Try finding the files in priority order
    safetensors_path = os.path.join(adapter_dir, "adapter_model.safetensors")
    bin_path = os.path.join(adapter_dir, "adapter_model.bin")
    bin_bak_path = os.path.join(adapter_dir, "adapter_model.bin.bak")
    
    adapter_path = None
    is_safetensors = False
    
    if os.path.exists(safetensors_path):
        adapter_path = safetensors_path
        is_safetensors = True
    elif os.path.exists(bin_path):
        adapter_path = bin_path
    elif os.path.exists(bin_bak_path):
        adapter_path = bin_bak_path
        
    print("=" * 60)
    print("  AIRA LoRA Adapter Key Inspector")
    print(f"  Target Adapter: {adapter_path or safetensors_path}")
    print("=" * 60)
    
    if not adapter_path:
        print(f"[-] ERROR: No adapter model file found in: {adapter_dir}")
        print("    Please ensure adapter_model.safetensors or adapter_model.bin exists.")
        return
        
    try:
        if is_safetensors:
            if load_safetensors is None:
                print("[-] ERROR: safetensors package not installed but adapter_model.safetensors found.")
                return
            weights = load_safetensors(adapter_path, device="cpu")
        else:
            # Load weights on CPU
            weights = torch.load(adapter_path, map_location="cpu")
            
        total_keys = len(weights)
        lm_keys = [k for k in weights.keys() if "language_model" in k]
        
        print(f"[+] Successfully loaded {total_keys} total weight keys.")
        print(f"[+] Language Model decoder keys: {len(lm_keys)}")
        
        if len(lm_keys) > 0:
            print("\n[SUCCESS] text decoder keys are successfully trained and present in the adapter!")
            print("Sample keys:")
            for k in lm_keys[:5]:
                print(f"  * {k}")
            if len(lm_keys) > 5:
                print(f"  ... and {len(lm_keys) - 5} more")
        else:
            print("\n[FAIL] 0 language_model keys found! The LoRA target modules config was incorrect.")
            print("       Ensure target_modules in training config targets: .*language_model.*")
            
    except Exception as e:
        print(f"[-] ERROR loading weights file: {e}")
    print("=" * 60)

if __name__ == "__main__":
    inspect_keys()
