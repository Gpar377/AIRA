"""
AIRA test_exporter.py — Phase 3 Validation Script
================================================
Runs a validation suite over the generated SFT trajectories
to guarantee perfect ChatML schema compliance.

Usage:
    python training/test_exporter.py
"""
import sys
import os
import json
import subprocess
from pathlib import Path

# Insert AIRA root to PATH
sys.path.insert(0, str(Path(__file__).parent.parent))

TEST_OUTPUT = "training/sft_dataset_test.jsonl"

def print_check(name: str, passed: bool, detail: str = ""):
    status = "[PASS]" if passed else "[FAIL]"
    print(f"  {status:7} {name:<40} {detail}")

def test_exporter_run() -> bool:
    """Executes the exporter script to generate a test subset of SFT data."""
    try:
        cmd = [
            sys.executable,
            "training/export_trajectories.py",
            "--output", TEST_OUTPUT,
            "--augment", "50"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print_check("Exporter Execution", True, "Successfully generated 50 test samples")
        return True
    except subprocess.CalledProcessError as err:
        print_check("Exporter Execution", False, f"CLI exited with error: {err.stderr}")
        return False
    except Exception as exc:
        print_check("Exporter Execution", False, f"Unexpected error: {exc}")
        return False

def validate_chatml_dataset() -> bool:
    """Parses and validates the generated JSONL file against SFT specifications."""
    if not os.path.exists(TEST_OUTPUT):
        print_check("File Existence", False, f"Missing output file: {TEST_OUTPUT}")
        return False
        
    print_check("File Existence", True, "Found generated test SFT file")
    
    all_checks = True
    parse_errors = 0
    schema_errors = 0
    format_errors = 0
    uri_errors = 0
    total_lines = 0
    
    with open(TEST_OUTPUT, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f, 1):
            total_lines += 1
            # 1. Parse JSON
            try:
                sample = json.loads(line.strip())
            except Exception as e:
                parse_errors += 1
                all_checks = False
                continue
                
            # 2. Check ChatML schema keys
            messages = sample.get("messages", [])
            source = sample.get("source")
            if not isinstance(messages, list) or len(messages) != 3:
                schema_errors += 1
                all_checks = False
                continue
                
            if source not in ("live_ollama", "gemini_distilled", "synthetic"):
                schema_errors += 1
                all_checks = False
                continue
                
            roles = [m.get("role") for m in messages]
            if roles != ["system", "user", "assistant"]:
                schema_errors += 1
                all_checks = False
                continue
                
            # 3. Check message contents
            contents = [m.get("content", "").strip() for m in messages]
            if not all(contents):
                format_errors += 1
                all_checks = False
                continue
                
            # 4. Validate user observations URI format
            user_content = contents[1]
            if "TARGET: " in user_content:
                try:
                    target_line = [l for l in user_content.split("\n") if l.startswith("TARGET: ")][0]
                    target_uri = target_line.replace("TARGET: ", "").strip()
                    if not (target_uri.startswith("k8s://") or target_uri.startswith("web://") or target_uri.startswith("net://")):
                        uri_errors += 1
                        all_checks = False
                except Exception:
                    uri_errors += 1
                    all_checks = False
            else:
                uri_errors += 1
                all_checks = False
                
            # 5. Validate assistant thought block and action block format
            assistant_content = contents[2]
            if not (assistant_content.startswith("<thought>") and "</thought>" in assistant_content):
                format_errors += 1
                all_checks = False
                continue
                
            if "```json" not in assistant_content or "```" not in assistant_content.split("```json")[1]:
                format_errors += 1
                all_checks = False
                continue
                
            # 6. Parse and check inner action block keys
            try:
                json_part = assistant_content.split("```json")[1].split("```")[0].strip()
                action_data = json.loads(json_part)
                required_keys = ["action_type", "target_resource", "parameters"]
                if not all(k in action_data for k in required_keys):
                    format_errors += 1
                    all_checks = False
            except Exception:
                format_errors += 1
                all_checks = False

    print_check("JSONL Parseability", parse_errors == 0, f"Errors: {parse_errors}/{total_lines}")
    print_check("ChatML Schema Compliance", schema_errors == 0, f"Errors: {schema_errors}/{total_lines}")
    print_check("System/User/Assistant Roles", schema_errors == 0, "Matched expected pattern")
    print_check("Vulnerability/Metrics observations", format_errors == 0, f"Format issues: {format_errors}/{total_lines}")
    print_check("Resource URI Scheme Mapping", uri_errors == 0, f"URI issues: {uri_errors}/{total_lines}")
    
    # Clean up test output
    try:
        os.remove(TEST_OUTPUT)
    except Exception:
        pass
        
    return all_checks

def main():
    print("=" * 60)
    print("  AIRA Dataset Validator -- SFT Verification Suite")
    print("=" * 60)
    
    if test_exporter_run():
        success = validate_chatml_dataset()
        print("=" * 60)
        if success:
            print("  [SUCCESS] All SFT validation checks passed! Dataset is safe to train.")
            sys.exit(0)
        else:
            print("  [FAIL] SFT validation failed. Check details above.")
            sys.exit(1)
    else:
        print("=" * 60)
        print("  [FAIL] Exporter run failed.")
        sys.exit(1)

if __name__ == "__main__":
    main()
