"""
Synthetic Metric Generator
Generates training data for LSTM prediction model
"""
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import json
from pathlib import Path


class SyntheticMetricGenerator:
    """Generate synthetic Prometheus-like metrics for training"""
    
    def __init__(self, seed: int = 42):
        np.random.seed(seed)
        self.timestamp_start = datetime.now() - timedelta(days=30)
    
    def generate_memory_leak(
        self, 
        duration_hours: int = 24,
        interval_seconds: int = 15,
        base_mb: float = 100.0,
        leak_rate_mb_per_hour: float = 20.0,
        noise_std: float = 5.0
    ) -> pd.DataFrame:
        """
        Generate memory leak pattern
        
        Args:
            duration_hours: Total duration
            interval_seconds: Sampling interval
            base_mb: Starting memory usage
            leak_rate_mb_per_hour: Memory increase per hour
            noise_std: Noise standard deviation
            
        Returns:
            DataFrame with timestamp and memory_mb columns
        """
        num_points = int(duration_hours * 3600 / interval_seconds)
        timestamps = [
            self.timestamp_start + timedelta(seconds=i * interval_seconds)
            for i in range(num_points)
        ]
        
        # Linear growth with noise
        hours = np.arange(num_points) * interval_seconds / 3600
        memory = base_mb + (leak_rate_mb_per_hour * hours)
        memory += np.random.normal(0, noise_std, num_points)
        memory = np.maximum(memory, 0)  # No negative memory
        
        return pd.DataFrame({
            'timestamp': timestamps,
            'memory_mb': memory,
            'failure_type': 'memory_leak'
        })
    
    def generate_cpu_throttle(
        self,
        duration_hours: int = 12,
        interval_seconds: int = 15,
        base_percent: float = 20.0,
        spike_frequency: int = 100,
        spike_magnitude: float = 60.0,
        noise_std: float = 5.0
    ) -> pd.DataFrame:
        """Generate CPU throttling pattern with periodic spikes"""
        num_points = int(duration_hours * 3600 / interval_seconds)
        timestamps = [
            self.timestamp_start + timedelta(seconds=i * interval_seconds)
            for i in range(num_points)
        ]
        
        # Base CPU with periodic spikes
        cpu = np.full(num_points, base_percent)
        spike_indices = np.arange(0, num_points, spike_frequency)
        
        for idx in spike_indices:
            spike_width = 20
            spike_start = max(0, idx - spike_width // 2)
            spike_end = min(num_points, idx + spike_width // 2)
            cpu[spike_start:spike_end] += spike_magnitude * np.exp(
                -((np.arange(spike_end - spike_start) - spike_width // 2) ** 2) / (2 * (spike_width / 4) ** 2)
            )
        
        cpu += np.random.normal(0, noise_std, num_points)
        cpu = np.clip(cpu, 0, 100)
        
        return pd.DataFrame({
            'timestamp': timestamps,
            'cpu_percent': cpu,
            'failure_type': 'cpu_throttle'
        })
    
    def generate_cascading_timeout(
        self,
        duration_hours: int = 6,
        interval_seconds: int = 15,
        base_latency_ms: float = 100.0,
        cascade_start_hour: float = 3.0,
        cascade_rate: float = 50.0,
        noise_std: float = 20.0
    ) -> pd.DataFrame:
        """Generate cascading timeout pattern"""
        num_points = int(duration_hours * 3600 / interval_seconds)
        timestamps = [
            self.timestamp_start + timedelta(seconds=i * interval_seconds)
            for i in range(num_points)
        ]
        
        hours = np.arange(num_points) * interval_seconds / 3600
        
        # Exponential growth after cascade starts
        latency = np.where(
            hours < cascade_start_hour,
            base_latency_ms,
            base_latency_ms + cascade_rate * np.exp((hours - cascade_start_hour) / 2)
        )
        
        latency += np.random.normal(0, noise_std, num_points)
        latency = np.maximum(latency, 0)
        
        # Add timeout events
        timeout_rate = np.where(hours < cascade_start_hour, 0.01, 0.3)
        timeouts = np.random.binomial(1, timeout_rate)
        
        return pd.DataFrame({
            'timestamp': timestamps,
            'latency_ms': latency,
            'timeout_count': timeouts,
            'failure_type': 'cascading_timeout'
        })
    
    def generate_disk_pressure(
        self,
        duration_hours: int = 48,
        interval_seconds: int = 15,
        base_percent: float = 40.0,
        fill_rate_percent_per_hour: float = 2.0,
        noise_std: float = 1.0
    ) -> pd.DataFrame:
        """Generate disk pressure pattern"""
        num_points = int(duration_hours * 3600 / interval_seconds)
        timestamps = [
            self.timestamp_start + timedelta(seconds=i * interval_seconds)
            for i in range(num_points)
        ]
        
        hours = np.arange(num_points) * interval_seconds / 3600
        disk_usage = base_percent + (fill_rate_percent_per_hour * hours)
        disk_usage += np.random.normal(0, noise_std, num_points)
        disk_usage = np.clip(disk_usage, 0, 100)
        
        return pd.DataFrame({
            'timestamp': timestamps,
            'disk_usage_percent': disk_usage,
            'failure_type': 'disk_pressure'
        })
    
    def generate_all_scenarios(self, output_dir: str = "data/synthetic_metrics"):
        """Generate all failure scenarios and save to files"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        scenarios = {
            'memory_leak': self.generate_memory_leak(),
            'cpu_throttle': self.generate_cpu_throttle(),
            'cascading_timeout': self.generate_cascading_timeout(),
            'disk_pressure': self.generate_disk_pressure()
        }
        
        for name, df in scenarios.items():
            # Save as CSV
            csv_path = output_path / f"{name}.csv"
            df.to_csv(csv_path, index=False)
            
            # Save as JSON
            json_path = output_path / f"{name}.json"
            df.to_json(json_path, orient='records', date_format='iso')
            
            print(f"✅ Generated {name}: {len(df)} samples -> {csv_path}")
        
        # Generate metadata
        metadata = {
            'generated_at': datetime.now().isoformat(),
            'scenarios': list(scenarios.keys()),
            'total_samples': sum(len(df) for df in scenarios.values())
        }
        
        with open(output_path / 'metadata.json', 'w') as f:
            json.dump(metadata, f, indent=2)
        
        print(f"\n📊 Total samples generated: {metadata['total_samples']}")
        return scenarios


if __name__ == "__main__":
    generator = SyntheticMetricGenerator()
    scenarios = generator.generate_all_scenarios()
    
    # Display sample statistics
    for name, df in scenarios.items():
        print(f"\n{name.upper()}:")
        print(df.describe())
