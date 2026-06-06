import os
import torch

def inspect_keys():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    adapter_path = os.path.join(current_dir, "gemma-4-e4b-aira-lora", "adapter_model.bin")
    
    print("=" * 60)
    print("  AIRA LoRA Adapter Key Inspector")
    print(f"  Path: {adapter_path}")
    print("=" * 60)
    
    if not os.path.exists(adapter_path):
        print(f"[-] ERROR: Adapter model file not found at: {adapter_path}")
        print("    Please download the adapter_model.bin from your Colab run and place it there.")
        return
        
    try:
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
