# Practical Implementation Guide: Evaluating Your Coding Agent Harness

## Overview

This guide provides actionable steps to implement a comprehensive evaluation framework for your agent harness. It covers metric design, benchmark integration, and ongoing monitoring strategies.

---

## 1. METRIC TAXONOMY & IMPLEMENTATION

### 1.1 Core Success Metrics

#### Primary Metric: Task Resolved Rate

```python
class TaskResolution:
    """
    FAIL_TO_PASS tests must pass + PASS_TO_PASS tests must remain passing
    """

    def calculate_resolved_rate(results):
        """
        Args:
            results: List of TaskResult objects

        Returns:
            float: Percentage of fully resolved tasks (0-100)
        """
        resolved = sum(1 for r in results if r.fail_to_pass_pass and r.pass_to_pass_pass)
        return (resolved / len(results)) * 100

    def calculate_patch_apply_rate(results):
        """
        Measure: Can agent's changes be applied cleanly?
        No merge conflicts, no syntax errors
        """
        applied = sum(1 for r in results if r.patch_applies_cleanly)
        return (applied / len(results)) * 100

    def calculate_regression_rate(results):
        """
        Measure: % of existing tests still passing
        Critical for safety in production
        """
        no_regressions = sum(1 for r in results if r.pass_to_pass_pass)
        return (no_regressions / len(results)) * 100
```

**Targets**:
- Resolved Rate: 60%+ (frontier), 50%+ (competitive)
- Patch Apply Rate: 85%+ (high quality control)
- Regression Rate: 95%+ (safety critical)

#### Secondary Metric: File Localization

```python
def calculate_file_localization_rate(results):
    """
    Measure: Did agent edit the RIGHT files?

    Test by comparing:
    - Files agent modified
    - Files in gold solution patch
    """
    correct_files = sum(1 for r in results
                       if r.modified_files == r.expected_files)
    return (correct_files / len(results)) * 100

def calculate_localization_precision(results):
    """
    Precision: % of modified files that were supposed to be modified
    """
    total_modified = sum(len(r.modified_files) for r in results)
    correct_modified = sum(sum(1 for f in r.modified_files
                              if f in r.expected_files)
                          for r in results)
    return (correct_modified / total_modified) * 100 if total_modified > 0 else 100
```

**Targets**:
- File Localization: 80%+ (agent finds right files)
- Precision: 85%+ (doesn't over-modify)

---

### 1.2 Efficiency Metrics

#### Token Consumption Analysis

```python
class TokenMetrics:

    def calculate_tokens_per_task(task_results):
        """
        Track both input and output tokens
        """
        metrics = {}
        for task_id, result in task_results.items():
            metrics[task_id] = {
                'input_tokens': result.input_tokens,
                'output_tokens': result.output_tokens,
                'total_tokens': result.input_tokens + result.output_tokens,
                'resolved': result.resolved
            }

        resolved_tasks = [m for m in metrics.values() if m['resolved']]
        failed_tasks = [m for m in metrics.values() if not m['resolved']]

        return {
            'mean_tokens_resolved': np.mean([m['total_tokens'] for m in resolved_tasks]),
            'mean_tokens_failed': np.mean([m['total_tokens'] for m in failed_tasks]),
            'median_tokens': np.median([m['total_tokens'] for m in metrics.values()]),
            'p95_tokens': np.percentile([m['total_tokens'] for m in metrics.values()], 95),
            'p99_tokens': np.percentile([m['total_tokens'] for m in metrics.values()], 99),
            'std_dev_tokens': np.std([m['total_tokens'] for m in metrics.values()])
        }

    def calculate_cost_per_task(tokens_per_task, input_price, output_price):
        """
        Calculate cost per task

        Args:
            tokens_per_task: Dict with token counts
            input_price: $/1K input tokens
            output_price: $/1K output tokens

        Returns:
            Dict with cost metrics
        """
        costs = {}
        for task_id, tokens in tokens_per_task.items():
            costs[task_id] = (
                (tokens['input_tokens'] / 1000 * input_price) +
                (tokens['output_tokens'] / 1000 * output_price)
            )

        return {
            'mean_cost': np.mean(list(costs.values())),
            'median_cost': np.median(list(costs.values())),
            'p95_cost': np.percentile(list(costs.values()), 95),
            'total_cost': sum(costs.values())
        }

    def calculate_cost_per_resolved(total_cost, resolved_count):
        """Cost effectiveness metric"""
        return total_cost / resolved_count if resolved_count > 0 else float('inf')
```

**Key Targets**:
- Mean tokens/task: <200K (efficient), <500K (acceptable)
- Cost per resolved task: <$2 (competitive), <$5 (acceptable)
- Token variance (std dev): Should be low (~20% of mean)
- P95 tokens: Should not exceed mean by >3x (indicating instability)

#### Token Variance Analysis

```python
def analyze_token_variance(task_results):
    """
    High variance indicates inconsistent agent behavior
    Some tasks consuming 10x more tokens suggests planning issues
    """
    token_ratios = []
    for task in task_results:
        min_tokens = 50000  # Approximate minimum
        actual = task.total_tokens
        ratio = actual / min_tokens
        token_ratios.append(ratio)

    return {
        'mean_ratio': np.mean(token_ratios),
        'max_ratio': np.max(token_ratios),
        'coefficient_of_variation': np.std(token_ratios) / np.mean(token_ratios),
        'tasks_over_2x_min': sum(1 for r in token_ratios if r > 2),
        'tasks_over_5x_min': sum(1 for r in token_ratios if r > 5)
    }
```

**Red Flags**:
- Coefficient of Variation > 0.5: Highly inconsistent
- Max ratio > 10x mean: Some tasks causing agent thrashing
- >20% tasks over 5x minimum: Process planning issues

---

### 1.3 Latency & Responsiveness

```python
class LatencyMetrics:

    def calculate_response_times(task_results):
        """
        Measure end-to-end time from task to resolution
        """
        times = [r.end_time - r.start_time for r in task_results]

        return {
            'p50_latency': np.percentile(times, 50),  # Median
            'p95_latency': np.percentile(times, 95),  # 95th percentile (key!)
            'p99_latency': np.percentile(times, 99),
            'mean_latency': np.mean(times),
            'max_latency': np.max(times),
            'timeout_rate': sum(1 for t in times if t > 300) / len(times)  # >5 min
        }

    def calculate_throughput(task_results, time_window_seconds):
        """
        Tasks completed per hour
        """
        total_tasks = len(task_results)
        hours = time_window_seconds / 3600
        return total_tasks / hours
```

**Production Targets**:
- P50 latency: <120 seconds (2 minutes)
- P95 latency: <300 seconds (5 minutes)
- Timeout rate: <5% (tasks taking >5 min)
- Throughput: 12+ tasks/hour (parallel execution)

---

### 1.4 Edit Quality Metrics

```python
class EditQualityMetrics:

    def calculate_edit_accuracy(results):
        """
        Measure: Fraction of agent edits that are correct/necessary
        """
        correct_edits = sum(r.correct_edits for r in results)
        total_edits = sum(r.total_edits for r in results)

        if total_edits == 0:
            return 100.0

        return (correct_edits / total_edits) * 100

    def calculate_edit_efficiency(results):
        """
        Measure: % of necessary edits actually made
        (Recall: did agent make all needed changes?)
        """
        necessary_made = sum(r.necessary_edits_made for r in results)
        total_necessary = sum(r.total_necessary_edits for r in results)

        if total_necessary == 0:
            return 100.0

        return (necessary_made / total_necessary) * 100

    def calculate_over_editing_rate(results):
        """
        Measure: % of edits that were unnecessary/harmful
        """
        over_edits = sum(r.total_edits - r.necessary_edits_made for r in results)
        total_edits = sum(r.total_edits for r in results)

        if total_edits == 0:
            return 0.0

        return (over_edits / total_edits) * 100
```

**Targets**:
- Edit Accuracy: 85%+ (most edits are correct)
- Edit Efficiency: 90%+ (makes most necessary edits)
- Over-editing: <15% (minimal unnecessary changes)

---

### 1.5 Error Recovery & Robustness

```python
class ErrorRecoveryMetrics:

    def calculate_error_recovery_rate(task_results):
        """
        Measure: % of tasks where agent recovered from initial failure
        """
        recovered = sum(1 for r in task_results
                       if r.initial_attempt_failed and r.final_resolved)
        failed_attempts = sum(1 for r in task_results
                             if r.initial_attempt_failed)

        if failed_attempts == 0:
            return 100.0  # No failures = 100% recovery

        return (recovered / failed_attempts) * 100

    def calculate_max_retries_needed(task_results):
        """
        Distribution of retry attempts needed
        """
        retry_counts = [r.retry_count for r in task_results if r.resolved]

        if not retry_counts:
            return {'never_resolved': len(task_results)}

        return {
            'mean_retries': np.mean(retry_counts),
            'max_retries': np.max(retry_counts),
            'p95_retries': np.percentile(retry_counts, 95),
            'resolved_on_first_try': sum(1 for r in task_results
                                         if r.resolved and r.retry_count == 0),
            'max_retries_exceeded': sum(1 for r in task_results
                                        if r.retry_count > 5)
        }

    def analyze_error_patterns(task_results):
        """
        Identify recurring error types
        """
        error_counts = {}
        error_by_task = {}

        for result in task_results:
            for error in result.errors:
                error_type = error.category
                error_counts[error_type] = error_counts.get(error_type, 0) + 1

                if error_type not in error_by_task:
                    error_by_task[error_type] = []
                error_by_task[error_type].append(result.task_id)

        return {
            'error_counts': error_counts,
            'error_frequency': {k: v/len(task_results)
                               for k, v in error_counts.items()},
            'errors_affecting_multiple_tasks': {
                k: len(set(v)) for k, v in error_by_task.items()
            }
        }
```

**Targets**:
- Error Recovery Rate: 60%+ (agent fixes own mistakes)
- Mean Retries: <2 (quick recovery)
- P95 Retries: <4 (reasonable bounds)
- Resolved on First Try: 40%+ (good initial planning)

---

## 2. BENCHMARK INTEGRATION STRATEGY

### 2.1 Multi-Benchmark Evaluation Pipeline

```python
class BenchmarkEvaluator:
    """
    Run agent against multiple benchmarks sequentially
    """

    def __init__(self):
        self.benchmarks = {
            'swe_bench_lite': SWEBenchLite(),
            'swe_bench_verified': SWEBenchVerified(),
            'terminal_bench': TerminalBench(),
            'aider_polyglot': AiderPolyglot(),
            'featbench': FeatBench(),
            'custom_domain': CustomDomainBench(),
        }
        self.results = {}

    def run_all_benchmarks(self, agent, num_trials=3):
        """
        Run each benchmark multiple times for statistical validity
        """
        for bench_name, benchmark in self.benchmarks.items():
            print(f"Running {bench_name}...")

            trial_results = []
            for trial in range(num_trials):
                results = benchmark.evaluate(agent)
                trial_results.append(results)

            # Aggregate results with statistics
            self.results[bench_name] = self._aggregate_trials(trial_results)

    def _aggregate_trials(self, trial_results):
        """
        Compute mean, std dev, confidence intervals across trials
        """
        aggregated = {}

        # Get all metrics from first trial
        metrics = trial_results[0].keys()

        for metric in metrics:
            values = [trial[metric] for trial in trial_results]

            aggregated[metric] = {
                'mean': np.mean(values),
                'std_dev': np.std(values),
                'ci_95': self._confidence_interval(values),
                'values': values
            }

        return aggregated

    def generate_report(self):
        """Generate comprehensive evaluation report"""
        report = "=== AGENT EVALUATION REPORT ===\n\n"

        for bench_name, results in self.results.items():
            report += f"\n{bench_name.upper()}\n"
            report += "-" * 40 + "\n"

            for metric, stats in results.items():
                report += f"{metric}:\n"
                report += f"  Mean: {stats['mean']:.2f}\n"
                report += f"  Std Dev: {stats['std_dev']:.2f}\n"
                report += f"  95% CI: {stats['ci_95']}\n"

        return report
```

### 2.2 Benchmark-Specific Configuration

```python
# SWE-bench Configuration
SWEBENCH_CONFIG = {
    'variant': 'verified',  # 'lite', 'verified', 'full', or 'pro'
    'dataset_name': 'princeton-nlp/SWE-bench_Verified',
    'max_workers': 8,
    'cache_level': 'env',  # 'none', 'base', 'env', 'instance'
    'docker_image_timeout': 1800,
    'test_timeout': 300,
    'num_trials': 3,
}

# Terminal-Bench Configuration
TERMINAL_BENCH_CONFIG = {
    'task_count': 89,
    'timeout_per_task': 600,  # 10 minutes
    'docker_network': 'sandboxed',
    'shell_type': 'bash',
    'num_trials': 1,  # More expensive, fewer runs
}

# Aider Configuration
AIDER_CONFIG = {
    'variant': 'polyglot',  # 'python', 'polyglot', 'refactoring'
    'languages': ['python', 'javascript', 'java', 'go', 'rust', 'cpp'],
    'attempts_per_task': 2,  # Second attempt after test failure
    'num_trials': 2,
}

# Custom Domain Benchmark
CUSTOM_BENCH_CONFIG = {
    'task_file': '/path/to/custom_tasks.json',
    'test_suite_path': '/path/to/tests',
    'timeout': 300,
    'num_trials': 5,  # Custom tasks usually smaller set
}
```

---

## 3. MONITORING & DASHBOARDING

### 3.1 Time-Series Tracking

```python
class MetricsTracker:
    """
    Track performance metrics over time to detect regressions
    """

    def __init__(self, db_path='metrics.db'):
        self.db = sqlite3.connect(db_path)
        self._init_schema()

    def _init_schema(self):
        self.db.execute("""
        CREATE TABLE IF NOT EXISTS evaluations (
            id INTEGER PRIMARY KEY,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            agent_version TEXT,
            model_name TEXT,
            benchmark_name TEXT,
            resolved_rate FLOAT,
            patch_apply_rate FLOAT,
            regression_rate FLOAT,
            mean_tokens FLOAT,
            cost_per_task FLOAT,
            p95_latency FLOAT,
            error_recovery_rate FLOAT,
            edit_accuracy FLOAT,
            num_trials INTEGER
        )
        """)

    def log_evaluation(self, eval_data):
        """Log evaluation results"""
        self.db.execute("""
        INSERT INTO evaluations (
            agent_version, model_name, benchmark_name,
            resolved_rate, patch_apply_rate, regression_rate,
            mean_tokens, cost_per_task, p95_latency,
            error_recovery_rate, edit_accuracy, num_trials
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            eval_data['agent_version'],
            eval_data['model_name'],
            eval_data['benchmark_name'],
            eval_data['resolved_rate'],
            eval_data['patch_apply_rate'],
            eval_data['regression_rate'],
            eval_data['mean_tokens'],
            eval_data['cost_per_task'],
            eval_data['p95_latency'],
            eval_data['error_recovery_rate'],
            eval_data['edit_accuracy'],
            eval_data['num_trials']
        ))
        self.db.commit()

    def detect_regressions(self, agent_version, benchmark):
        """
        Compare recent evals to baseline
        Alert if performance drops >5%
        """
        # Get baseline (previous stable version)
        baseline = self.db.execute("""
        SELECT AVG(resolved_rate), AVG(edit_accuracy)
        FROM evaluations
        WHERE agent_version = ?
        AND benchmark_name = ?
        LIMIT 10
        """, (agent_version, benchmark)).fetchone()

        # Get latest results
        latest = self.db.execute("""
        SELECT AVG(resolved_rate), AVG(edit_accuracy)
        FROM evaluations
        WHERE agent_version = ?
        AND benchmark_name = ?
        ORDER BY timestamp DESC
        LIMIT 1
        """, (agent_version, benchmark)).fetchone()

        if baseline and latest:
            resolved_drop = (baseline[0] - latest[0]) / baseline[0]
            accuracy_drop = (baseline[1] - latest[1]) / baseline[1]

            if resolved_drop > 0.05:  # 5% drop
                print(f"⚠️  REGRESSION: Resolved rate dropped {resolved_drop*100:.1f}%")
            if accuracy_drop > 0.05:
                print(f"⚠️  REGRESSION: Edit accuracy dropped {accuracy_drop*100:.1f}%")
```

### 3.2 Visualization Dashboard

```python
def create_dashboard(metrics_db_path):
    """
    Create interactive Grafana/Streamlit dashboard
    """
    import streamlit as st
    import plotly.express as px

    st.set_page_config(page_title="Agent Evaluation Dashboard", layout="wide")
    st.title("Agent Harness Evaluation Dashboard")

    # Load data
    df = pd.read_sql_query(
        "SELECT * FROM evaluations ORDER BY timestamp DESC",
        sqlite3.connect(metrics_db_path)
    )

    # Filter options
    col1, col2, col3 = st.columns(3)
    with col1:
        selected_agent = st.multiselect(
            "Agent Version",
            df['agent_version'].unique(),
            default=df['agent_version'].unique()[-1]
        )
    with col2:
        selected_benchmark = st.multiselect(
            "Benchmark",
            df['benchmark_name'].unique(),
            default=df['benchmark_name'].unique()
        )
    with col3:
        selected_model = st.multiselect(
            "Model",
            df['model_name'].unique(),
            default=df['model_name'].unique()
        )

    # Filter data
    filtered = df[
        (df['agent_version'].isin(selected_agent)) &
        (df['benchmark_name'].isin(selected_benchmark)) &
        (df['model_name'].isin(selected_model))
    ]

    # Key metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Avg Resolved Rate", f"{filtered['resolved_rate'].mean():.1f}%")
    with col2:
        st.metric("Avg Cost/Task", f"${filtered['cost_per_task'].mean():.2f}")
    with col3:
        st.metric("Avg P95 Latency", f"{filtered['p95_latency'].mean():.0f}s")
    with col4:
        st.metric("Avg Edit Accuracy", f"{filtered['edit_accuracy'].mean():.1f}%")

    # Time series chart
    st.subheader("Performance Over Time")
    fig = px.line(
        filtered.sort_values('timestamp'),
        x='timestamp',
        y='resolved_rate',
        color='agent_version',
        hover_data=['benchmark_name', 'model_name'],
        title="Resolved Rate Trend"
    )
    st.plotly_chart(fig, use_container_width=True)

    # Cost vs Performance
    st.subheader("Cost-Performance Tradeoff")
    fig = px.scatter(
        filtered,
        x='cost_per_task',
        y='resolved_rate',
        color='agent_version',
        size='mean_tokens',
        hover_name='agent_version',
        title="Cost per Task vs Resolution Rate"
    )
    st.plotly_chart(fig, use_container_width=True)
```

---

## 4. STATISTICAL RIGOR GUIDELINES

### 4.1 Sample Size Requirements

```python
def calculate_required_samples(effect_size=0.10, alpha=0.05, power=0.80):
    """
    Using power analysis to determine required samples

    Args:
        effect_size: Minimum meaningful difference (e.g., 0.10 = 10%)
        alpha: Type I error rate (false positive)
        power: Statistical power (1 - Type II error rate)

    Returns:
        Required sample size
    """
    from scipy.stats import norm

    z_alpha = norm.ppf(1 - alpha/2)
    z_beta = norm.ppf(power)

    n = ((z_alpha + z_beta)**2 * 2 * (0.5**2)) / (effect_size**2)

    return int(np.ceil(n))

# Examples
print(f"Samples for 10% effect: {calculate_required_samples(0.10)}")  # ~64
print(f"Samples for 5% effect: {calculate_required_samples(0.05)}")   # ~256
```

**Recommendation**:
- Small benchmarks (custom): N=10-20 trials
- Medium benchmarks (Aider): N=5-10 trials
- Large benchmarks (SWE-bench): N=3-5 trials

### 4.2 Statistical Testing

```python
def test_improvement(baseline_results, new_results, metric='resolved_rate'):
    """
    Perform t-test to check if improvement is statistically significant
    """
    from scipy import stats

    baseline_scores = [r[metric] for r in baseline_results]
    new_scores = [r[metric] for r in new_results]

    # Two-sample t-test
    t_stat, p_value = stats.ttest_ind(new_scores, baseline_scores)

    improvement = np.mean(new_scores) - np.mean(baseline_scores)
    percent_improvement = (improvement / np.mean(baseline_scores)) * 100

    return {
        'mean_improvement': improvement,
        'percent_improvement': percent_improvement,
        't_statistic': t_stat,
        'p_value': p_value,
        'significant_at_0_05': p_value < 0.05,
        'significant_at_0_01': p_value < 0.01
    }
```

### 4.3 Confidence Intervals

```python
def bootstrap_confidence_interval(data, metric_fn, ci=95, num_iterations=1000):
    """
    Calculate confidence interval using bootstrap resampling
    """
    bootstrap_stats = []

    for _ in range(num_iterations):
        sample = np.random.choice(data, size=len(data), replace=True)
        bootstrap_stats.append(metric_fn(sample))

    lower = np.percentile(bootstrap_stats, (100-ci)/2)
    upper = np.percentile(bootstrap_stats, 100 - (100-ci)/2)

    return {
        'lower': lower,
        'upper': upper,
        'point_estimate': metric_fn(data),
        'width': upper - lower
    }
```

---

## 5. CONTINUOUS INTEGRATION SETUP

### 5.1 Automated Evaluation Pipeline

```yaml
# .github/workflows/eval.yml
name: Agent Evaluation

on:
  pull_request:
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM

jobs:
  evaluate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: |
          pip install -e .
          pip install swebench aider-eval terminal-bench

      - name: Run SWE-bench (Lite)
        run: |
          python -m swebench.harness.run_evaluation \
            --dataset_name princeton-nlp/SWE-bench_Lite \
            --predictions_path eval_results/swe_lite.jsonl \
            --max_workers 4 \
            --cache_level env

      - name: Run Aider Polyglot
        run: |
          python -m aider_eval.run \
            --variant polyglot \
            --output eval_results/aider_polyglot.json

      - name: Generate report
        run: python scripts/generate_eval_report.py eval_results/ > eval_results/report.md

      - name: Comment on PR
        if: github.event_name == 'pull_request'
        uses: actions/github-script@v6
        with:
          script: |
            const report = require('fs').readFileSync('eval_results/report.md', 'utf8');
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: report
            });

      - name: Upload results
        uses: actions/upload-artifact@v3
        with:
          name: eval-results
          path: eval_results/
```

---

## 6. CHECKLIST FOR EVALUATION READINESS

### Before First Evaluation

- [ ] Docker properly installed and configured
- [ ] All benchmarks downloaded or accessible
- [ ] Agent harness tested on small sample (10 tasks)
- [ ] Metrics calculation functions tested
- [ ] Cost calculation verified (token prices up to date)
- [ ] Database schema created for tracking
- [ ] Baseline established for comparison

### During Evaluation

- [ ] Monitor disk space (SWE-bench needs 120GB+)
- [ ] Log all agent interactions for debugging
- [ ] Track timeout/error rates in real-time
- [ ] Verify Docker cleanup between tasks
- [ ] Confirm test isolation (no state leakage)

### After Evaluation

- [ ] Aggregate statistics across all trials
- [ ] Calculate confidence intervals
- [ ] Check for statistical significance
- [ ] Identify failure patterns
- [ ] Generate comprehensive report
- [ ] Store results in time-series database
- [ ] Compare to baseline/previous version
- [ ] Flag any regressions (>5% drop)

---

## NEXT STEPS

1. **Week 1**: Implement core metrics (Section 1)
2. **Week 2**: Integrate one benchmark (Section 2)
3. **Week 3**: Set up monitoring (Section 3)
4. **Week 4**: Run full evaluation pipeline
5. **Ongoing**: Track metrics, detect regressions, iterate

