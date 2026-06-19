"""
eval_base_vs_finetuned.py — Phase 4 Evaluation Script
======================================================
Compares the base google/gemma-4-e4b-it model against the fine-tuned
gemma-4-e4b-aira-lora model on a held-out test set of observations.

Metrics:
  1. Parseable JSON Rate (%)
  2. Schema Adherence Rate (%) (has action_type, target_resource, parameters)
  3. Correct Action Type Rate (%) (vuln_type / defense_type is valid)
  4. Reasoning Block Presence (%) (contains <thought>...</thought>)
  5. OPA Compliance Rate (%) (passes safety policies)
  6. Inference Latency (seconds)

Usage:
  python training/eval_base_vs_finetuned.py --samples 20
"""
import os
import sys
import json
import time
import random
import re
import argparse
from typing import Dict, Any, List, Tuple
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.llm_client import AIRALLMClient
from sentinel.governance.opa_engine import evaluate_red_action

# ─────────────────────────────────────────────────────────────────────────────
# Helper Utilities
# ─────────────────────────────────────────────────────────────────────────────

def extract_namespace_from_uri(uri: str) -> str:
    """Extract namespace from a URI string (e.g., k8s://default/pod -> default)."""
    if not uri:
        return "default"
    # Match k8s://namespace/resource
    match = re.match(r"^k8s://([^/]+)/", uri)
    if match:
        return match.group(1)
    return "default"

def parse_and_validate(response_text: str, is_red: bool) -> Dict[str, Any]:
    """Parse output response and validate format, schemas, and OPA compliance."""
    if not response_text:
        return {
            "has_reasoning": False,
            "is_valid_json": False,
            "has_required_fields": False,
            "valid_action_type": False,
            "opa_allowed": False,
            "opa_reason": "Empty response",
            "action_type": "none"
        }

    # 1. Reasoning presence check
    has_reasoning = "<thought>" in response_text and "</thought>" in response_text

    # 2. Extract JSON
    parsed_json = AIRALLMClient.extract_json(response_text)
    is_valid_json = (parsed_json is not None)

    has_required_fields = False
    valid_action_type = False
    opa_allowed = True
    opa_reason = "N/A"
    action_type = "none"

    if is_valid_json:
        # Check required fields
        required_keys = {"action_type", "target_resource", "parameters"}
        has_required_fields = required_keys.issubset(parsed_json.keys())
        action_type = parsed_json.get("action_type", "none")

        # Check action type category validity
        if is_red:
            valid_action_types = {"cve", "rbac", "secret", "network", "privilege"}
        else:
            valid_action_types = {"secret_rotation", "rbac_patch", "network_policy", "pod_restart", "image_update"}

        valid_action_type = str(action_type).lower() in valid_action_types

        # Check OPA policy (only for Red actions)
        if is_red:
            params = parsed_json.get("parameters", {}) or {}
            method = params.get("method", "") if isinstance(params, dict) else ""
            blast_radius = params.get("blast_radius", 0.1) if isinstance(params, dict) else 0.1
            
            raw_action = {
                "vuln_type": action_type,
                "target_namespace": extract_namespace_from_uri(parsed_json.get("target_resource", "")),
                "target_resource": parsed_json.get("target_resource", ""),
                "method": method,
                "blast_radius": blast_radius
            }
            allowed, reason, severity = evaluate_red_action(raw_action)
            opa_allowed = allowed
            opa_reason = reason

    return {
        "has_reasoning": has_reasoning,
        "is_valid_json": is_valid_json,
        "has_required_fields": has_required_fields,
        "valid_action_type": valid_action_type,
        "opa_allowed": opa_allowed,
        "opa_reason": opa_reason,
        "action_type": action_type
    }

# ─────────────────────────────────────────────────────────────────────────────
# Evaluation Pipeline
# ─────────────────────────────────────────────────────────────────────────────

def run_evaluation(args):
    dataset_path = Path("training/sft_dataset.jsonl")
    if not dataset_path.exists():
        print(f"[-] ERROR: Dataset file not found at: {dataset_path.absolute()}")
        sys.exit(1)

    print(f"[*] Loading dataset from {dataset_path}...")
    with open(dataset_path, "r", encoding="utf-8") as f:
        lines = [json.loads(line) for line in f]

    total_samples = len(lines)
    print(f"[+] Loaded {total_samples} trajectories.")

    # Seed for reproducibility
    random.seed(args.seed)
    
    # Stratify by red/blue role (based on assistant output having attack/defense types)
    red_samples = []
    blue_samples = []
    for line in lines:
        assistant_content = line["messages"][-1]["content"]
        # Quick heuristic to separate Red and Blue
        if "remediate" in assistant_content or "remediation" in assistant_content or "patch" in assistant_content or "rotation" in assistant_content:
            blue_samples.append(line)
        else:
            red_samples.append(line)

    print(f"[+] Found {len(red_samples)} Red actions and {len(blue_samples)} Blue actions.")
    
    # Hold out 10% as test set
    test_red_count = max(1, int(len(red_samples) * 0.1))
    test_blue_count = max(1, int(len(blue_samples) * 0.1))
    
    test_red = red_samples[-test_red_count:]
    test_blue = blue_samples[-test_blue_count:]
    test_set = test_red + test_blue
    random.shuffle(test_set)
    
    eval_count = min(args.samples, len(test_set))
    eval_set = test_set[:eval_count]
    print(f"[+] Sampled {eval_count} test items for evaluation.")

    # Configure base model client
    print(f"\n[*] Initializing Base Model Client: Backend={args.base_backend}, Model={args.base_model}...")
    os.environ["AIRA_LLM_BACKEND"] = args.base_backend
    if args.base_backend == "ollama":
        os.environ["OLLAMA_MODEL"] = args.base_model
    base_client = AIRALLMClient(default_model=args.base_model)

    # Configure fine-tuned model client
    print(f"[*] Initializing Fine-tuned Model Client: Backend={args.ft_backend}, Model={args.ft_model}...")
    os.environ["AIRA_LLM_BACKEND"] = args.ft_backend
    if args.ft_backend == "ollama":
        os.environ["OLLAMA_MODEL"] = args.ft_model
    ft_client = AIRALLMClient(default_model=args.ft_model)

    base_results = []
    ft_results = []

    print("\n" + "=" * 80)
    print("  RUNNING INFERENCE COMPARISON")
    print("=" * 80)

    for idx, item in enumerate(eval_set):
        messages = item["messages"][:-1]  # Exclude expected assistant response
        system_content = next((m["content"] for m in messages if m["role"] == "system"), "")
        user_content = next((m["content"] for m in messages if m["role"] == "user"), "")
        expected_response = item["messages"][-1]["content"]

        # Parse expected to determine if Red or Blue
        is_red = not ("remediate" in expected_response or "patch" in expected_response or "rotation" in expected_response)
        role_label = "RED" if is_red else "BLUE"

        # Format prompt according to ChatML style
        prompt = (
            f"<|im_start|>system\n{system_content}<|im_end|>\n"
            f"<|im_start|>user\n{user_content}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )

        print(f"\n[{idx+1}/{eval_count}] Evaluating Prompt ({role_label} target)...")
        
        # 1. Base Model Inference
        t0 = time.time()
        base_resp = base_client.call_gemini(prompt)
        base_time = time.time() - t0
        base_metrics = parse_and_validate(base_resp, is_red)
        base_metrics["latency"] = base_time
        base_results.append(base_metrics)
        
        # 2. Fine-tuned Model Inference
        t0 = time.time()
        ft_resp = ft_client.call_gemini(prompt)
        ft_time = time.time() - t0
        ft_metrics = parse_and_validate(ft_resp, is_red)
        ft_metrics["latency"] = ft_time
        ft_results.append(ft_metrics)

        print(f"    Base Model latency: {base_time:.2f}s | Parsed JSON: {base_metrics['is_valid_json']} | OPA: {base_metrics['opa_allowed']}")
        print(f"    FT Model latency:   {ft_time:.2f}s | Parsed JSON: {ft_metrics['is_valid_json']} | OPA: {ft_metrics['opa_allowed']}")

    # ─────────────────────────────────────────────────────────────────────────────
    # Compile Results
    # ─────────────────────────────────────────────────────────────────────────────
    def compute_stats(results_list: List[Dict[str, Any]]) -> Dict[str, float]:
        n = len(results_list)
        if n == 0:
            return {}
        return {
            "reasoning_rate": sum(1 for r in results_list if r["has_reasoning"]) / n * 100,
            "parse_rate": sum(1 for r in results_list if r["is_valid_json"]) / n * 100,
            "schema_rate": sum(1 for r in results_list if r["has_required_fields"]) / n * 100,
            "correct_type_rate": sum(1 for r in results_list if r["valid_action_type"]) / n * 100,
            "opa_compliance": sum(1 for r in results_list if r["opa_allowed"]) / n * 100,
            "avg_latency": sum(r["latency"] for r in results_list) / n
        }

    base_stats = compute_stats(base_results)
    ft_stats = compute_stats(ft_results)

    # Output Markdown Report Table
    report = f"""# Model Evaluation Report: Base vs. Fine-Tuned Gemma 4

**Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}  
**Evaluation dataset size:** {eval_count} test samples stratified randomly.

| Metric | Base Model ({args.base_model}) | Fine-Tuned Model ({args.ft_model}) | Improvement |
| :--- | :---: | :---: | :---: |
| **Reasoning Blocks (`<thought>`)** | {base_stats['reasoning_rate']:.1f}% | {ft_stats['reasoning_rate']:.1f}% | {ft_stats['reasoning_rate'] - base_stats['reasoning_rate']:+.1f}% |
| **Parseable JSON Blocks** | {base_stats['parse_rate']:.1f}% | {ft_stats['parse_rate']:.1f}% | {ft_stats['parse_rate'] - base_stats['parse_rate']:+.1f}% |
| **Schema Adherence** | {base_stats['schema_rate']:.1f}% | {ft_stats['schema_rate']:.1f}% | {ft_stats['schema_rate'] - base_stats['schema_rate']:+.1f}% |
| **Action Type Validity** | {base_stats['correct_type_rate']:.1f}% | {ft_stats['correct_type_rate']:.1f}% | {ft_stats['correct_type_rate'] - base_stats['correct_type_rate']:+.1f}% |
| **OPA Governance Compliance** | {base_stats['opa_compliance']:.1f}% | {ft_stats['opa_compliance']:.1f}% | {ft_stats['opa_compliance'] - base_stats['opa_compliance']:+.1f}% |
| **Average Latency** | {base_stats['avg_latency']:.2f}s | {ft_stats['avg_latency']:.2f}s | {base_stats['avg_latency'] - ft_stats['avg_latency']:+.2f}s |
"""
    
    print("\n" + "=" * 80)
    print("  EVALUATION SUMMARY")
    print("=" * 80)
    print(report)
    print("=" * 80)

    # Save to file
    output_report_path = Path("docs/eval_report_base_vs_finetuned.md")
    with open(output_report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n[+] Saved evaluation report to: {output_report_path.absolute()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate Base vs. Fine-tuned Gemma models")
    parser.add_argument("--samples", type=int, default=20, help="Number of samples to evaluate (default: 20)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for sample stratification")
    
    # Backends
    parser.add_argument("--base-backend", type=str, default="gemini", help="Backend for Base Model (gemini | ollama | openai | claude)")
    parser.add_argument("--base-model", type=str, default="gemini-2.0-flash", help="Model name for Base Model")
    parser.add_argument("--ft-backend", type=str, default="ollama", help="Backend for Fine-Tuned Model (gemini | ollama | openai | claude)")
    parser.add_argument("--ft-model", type=str, default="aira-model", help="Model name/tag for Fine-Tuned Model")

    args = parser.parse_args()
    
    # Ensure docs directory exists
    Path("docs").mkdir(parents=True, exist_ok=True)
    
    run_evaluation(args)
