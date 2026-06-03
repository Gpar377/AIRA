import os
import torch
from datasets import load_dataset
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, TrainingArguments
from trl import SFTTrainer

model_id = "google/gemma-4-e4b-it"
max_seq_length = 1024

print("Loading tokenizer and quantized 4-bit model...")
tokenizer = AutoTokenizer.from_pretrained(model_id)

quantization_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_use_double_quant=True,
    bnb_4bit_compute_dtype=torch.bfloat16
)

model = AutoModelForCausalLM.from_pretrained(
    model_id,
    quantization_config=quantization_config,
    attn_implementation="sdpa",
    device_map={"": 0}
)

print("Configuring LoRA with custom clippable linear child targets...")
peft_config = LoraConfig(
    r=64,
    lora_alpha=128,
    target_modules=".*language_model.*(q_proj|k_proj|v_proj|o_proj|gate_proj|up_proj|down_proj)",
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM"
)

model = get_peft_model(model, peft_config)
model.print_trainable_parameters()

dataset_path = "sft_dataset.jsonl"
if not os.path.exists(dataset_path):
    dataset_path = "/content/sft_dataset.jsonl"
if not os.path.exists(dataset_path):
    dataset_path = "/kaggle/input/sft-dataset/sft_dataset.jsonl"

print("Loading trajectory dataset...")
dataset = load_dataset("json", data_files=dataset_path, split="train")

def format_prompts(examples):
    texts = []
    for messages in examples["messages"]:
        text = tokenizer.apply_chat_template(messages, tokenize=False)
        tokens = tokenizer.encode(text, add_special_tokens=False)[:1024]
        texts.append(tokenizer.decode(tokens))
    return {"text": texts}

dataset = dataset.map(format_prompts, batched=True, remove_columns=dataset.column_names)

trainer = SFTTrainer(
    model=model,
    processing_class=tokenizer,
    train_dataset=dataset,
    args=TrainingArguments(
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,
        warmup_steps=5,
        max_steps=647,
        learning_rate=2e-4,
        fp16=False,
        bf16=True,
        gradient_checkpointing=True,
        logging_steps=1,
        optim="paged_adamw_8bit",
        weight_decay=0.01,
        lr_scheduler_type="linear",
        seed=3407,
        output_dir="outputs",
        report_to="none",
        save_strategy="no"
    )
)

print("Starting model fine-tuning...")
trainer.train()

print("Saving fine-tuned LoRA adapter weights...")
model.save_pretrained("gemma-4-e4b-aira-lora", safe_serialization=False)
tokenizer.save_pretrained("gemma-4-e4b-aira-lora")
print("Training completed and adapter saved successfully!")
