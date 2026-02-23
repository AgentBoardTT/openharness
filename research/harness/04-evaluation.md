# 04 - Evaluation Framework & Benchmarking Strategy

## Executive Summary

Agent evaluation requires measuring both the **model capability** and the **harness quality** together. Our evaluation framework must demonstrate that Harness's multi-provider approach achieves competitive results against Claude Code's single-provider optimization.

**Key insight**: The CORE benchmark proved that the same Opus 4.5 model scored 78% with Claude Code's harness but only 42% with smolagents — the harness contributes +36 percentage points. Our goal is to build a harness that maximizes every model's potential.

---

## 1. Benchmark Landscape

### Primary Benchmarks

| Benchmark | What It Measures | Tasks | Current Leaders |
|-----------|-----------------|-------|-----------------|
| **SWE-bench Verified** | Bug fixing in real repos | 500 curated issues | Opus 4.5: 80.9%, GPT-5.1: 76.3% |
| **SWE-bench Full** | Bug fixing (broader) | 2,294 issues | Varies by harness |
| **Terminal-Bench 2.0** | CLI agent competence | Terminal operations | Opus 4.6: 65.4%, Gemini 3 Pro: 54.2% |
| **CORE** | Scientific reproducibility | Research tasks | Opus 4.5 + Claude Code: 78% |
| **HumanEval** | Code generation | 164 problems | Saturated (>95% for top models) |
| **FeatBench** | Feature implementation | 157 tasks from 27 repos | Trae-agent + GPT-5: 29.94% |

### SWE-bench Details

**SWE-bench Verified** (our primary target):
- 500 human-validated issues from 12 Python repositories
- Each issue has a failing test and a ground-truth patch
- Agent must: read the issue → find the bug → write a fix → pass the tests
- Evaluated in Docker containers replicating the original runtime

**How it works**:
1. Agent receives issue description + full repository
2. Agent explores code, identifies the bug
3. Agent writes a patch (diff)
4. Patch is applied and tests are run
5. Pass/fail based on test results

**Scoring**: `Resolved%` = percentage of issues where the agent's patch passes all tests.

### Terminal-Bench 2.0

Tests practical CLI agent capabilities:
- File manipulation
- System administration
- Development workflows
- Multi-step terminal operations

**Key finding**: pi-mono's minimal 4-tool approach is competitive with heavily-tooled agents, validating our design philosophy.

### FeatBench (Newer, Harder)

- Natural language feature requirements (no code hints)
- Fail-to-Pass (F2P) + Pass-to-Pass (P2P) tests
- Automated pipeline for creating new benchmark versions
- Mitigates data contamination
- Even GPT-5 with Trae-agent only achieves 29.94%

---

## 2. Key Metrics for Harness Evaluation

### 2.1 Task Completion Metrics

| Metric | Definition | Target |
|--------|-----------|--------|
| **Resolved%** | % of tasks where agent produces correct solution | ≥70% on SWE-bench Verified |
| **Pass@1** | Probability of correct solution in 1 attempt | Primary metric |
| **Pass@5** | Probability of ≥1 correct solution in 5 attempts | Secondary metric |
| **Pass^5** | Probability of all 5 trials succeeding | Reliability metric |

### 2.2 Efficiency Metrics

| Metric | Definition | Why It Matters |
|--------|-----------|---------------|
| **Tokens per task** | Total input + output tokens consumed | Cost efficiency |
| **Cost per task** | Dollar cost per resolved task | ROI comparison |
| **Turns per task** | Number of LLM calls per task | Loop efficiency |
| **Tool calls per task** | Number of tool invocations | Tool selection quality |
| **Time to completion** | Wall clock time per task | User experience |
| **Token waste ratio** | Tokens on failed attempts / total tokens | Error recovery quality |

### 2.3 Quality Metrics

| Metric | Definition | Measurement |
|--------|-----------|-------------|
| **Edit accuracy** | Correct edits / total edit attempts | Log analysis |
| **Tool selection accuracy** | Optimal tool chosen / total tool calls | Expert annotation |
| **Context utilization** | Relevant context used / context available | Automated analysis |
| **Error recovery rate** | Tasks recovered after initial failure | Log analysis |
| **Code quality** | Linting score of generated code | Ruff/pylint scoring |

### 2.4 Harness-Specific Metrics

| Metric | Definition | Why It's Unique |
|--------|-----------|----------------|
| **Provider-normalized score** | Score relative to model's theoretical max | Isolates harness quality from model quality |
| **Harness overhead** | Tokens consumed by harness (system prompt, tools) vs user context | Efficiency of harness design |
| **Cross-provider consistency** | Score variance across providers for same task set | Multi-provider quality |
| **Compaction quality** | Task success rate with vs without compaction | Context management quality |

---

## 3. Evaluation Framework Design

### 3.1 Multi-Provider Evaluation Matrix

To fairly compare harness quality across providers, we run the same benchmark with each provider:

```
┌──────────────────────────────────────────────────────┐
│                  SWE-bench Verified                   │
│                                                       │
│  Provider        │ Model             │ Harness Score  │
│  ─────────────── │ ────────────────  │ ────────────── │
│  Anthropic       │ claude-opus-4-6   │ ??.?%          │
│  Anthropic       │ claude-sonnet-4-6 │ ??.?%          │
│  OpenAI          │ gpt-5.1           │ ??.?%          │
│  OpenAI          │ gpt-4o            │ ??.?%          │
│  Google          │ gemini-3-pro      │ ??.?%          │
│  Google          │ gemini-3-flash    │ ??.?%          │
│  Local           │ llama-3.3-70b     │ ??.?%          │
│                                                       │
│  Comparison: Claude Code (baseline)  │ 80.9%          │
│  Comparison: Aider (baseline)        │ ??.?%          │
│                                                       │
└──────────────────────────────────────────────────────┘
```

### 3.2 Harness Quality Isolation

To measure harness quality separately from model quality:

```python
# Concept: Provider-Normalized Score (PNS)
# PNS = (Harness Score / Model Theoretical Max) * 100
#
# If Opus 4.6 theoretically maxes at 85% on SWE-bench:
# - Claude Code achieves 80.9% → PNS = 95.2%
# - Our Harness achieves 75.0% → PNS = 88.2%
#
# This isolates harness quality from model capability.

def provider_normalized_score(harness_score: float, model_max: float) -> float:
    return (harness_score / model_max) * 100
```

### 3.3 Evaluation Pipeline

```python
class EvalPipeline:
    """Automated evaluation pipeline for Harness."""

    async def run_swebench(
        self,
        provider: str,
        model: str,
        split: str = "verified",  # "lite", "verified", "full"
        max_tasks: int | None = None,
    ) -> EvalResults:
        """Run SWE-bench evaluation."""
        results = []

        for task in self._load_tasks(split, max_tasks):
            # 1. Set up Docker environment with the repository
            env = await self._setup_environment(task)

            # 2. Run Harness agent on the task
            trajectory = await self._run_agent(
                prompt=task.issue_description,
                cwd=env.repo_path,
                provider=provider,
                model=model,
            )

            # 3. Apply the agent's patch
            patch = self._extract_patch(trajectory)
            await env.apply_patch(patch)

            # 4. Run tests
            test_result = await env.run_tests(task.test_commands)

            # 5. Record metrics
            results.append(TaskResult(
                task_id=task.id,
                resolved=test_result.passed,
                tokens_used=trajectory.total_tokens,
                cost=trajectory.total_cost,
                turns=trajectory.turns,
                tool_calls=trajectory.tool_calls,
                time_seconds=trajectory.duration,
                error_count=trajectory.errors,
            ))

            # 6. Cleanup
            await env.cleanup()

        return EvalResults(
            benchmark="swe-bench",
            split=split,
            provider=provider,
            model=model,
            results=results,
        )
```

### 3.4 Custom Harness-Bench

Our own benchmark testing harness-specific capabilities:

```python
HARNESS_BENCH_TASKS = [
    # Multi-file editing
    {"category": "multi_file", "task": "Rename a function and update all callers across 10 files"},

    # Error recovery
    {"category": "recovery", "task": "Fix a bug where first attempt fails due to wrong file"},

    # Context management
    {"category": "context", "task": "Work with a 500-file repo without running out of context"},

    # Tool efficiency
    {"category": "tools", "task": "Find and fix a typo using minimum tool calls"},

    # MCP integration
    {"category": "mcp", "task": "Query a database via MCP and update code accordingly"},

    # Sub-agent coordination
    {"category": "subagents", "task": "Review + test + fix cycle using specialized sub-agents"},

    # Permission compliance
    {"category": "permissions", "task": "Complete task respecting deny rules on production paths"},

    # Session continuity
    {"category": "sessions", "task": "Resume a previous session and continue where left off"},

    # Cross-provider consistency
    {"category": "consistency", "task": "Same task produces similar quality across 3 providers"},

    # Long-running task
    {"category": "long_running", "task": "Implement a feature requiring 20+ tool calls"},
]
```

---

## 4. Comparison Methodology: Harness vs Claude Code

### 4.1 Fair Comparison Framework

Since Claude Code only works with Claude models, we compare on equal footing:

```
┌────────────────────────────────────────────────────────┐
│           Comparison: Same Model, Different Harness     │
│                                                         │
│  Task Set: SWE-bench Verified (500 tasks)               │
│  Model: Claude Opus 4.6                                 │
│                                                         │
│  ┌──────────────┐      ┌──────────────┐                │
│  │  Claude Code  │      │   Harness    │                │
│  │  (baseline)   │      │   (ours)     │                │
│  │              │      │              │                │
│  │  Score: X%    │      │  Score: Y%   │                │
│  │  Tokens: A    │      │  Tokens: B   │                │
│  │  Cost: $C     │      │  Cost: $D    │                │
│  │  Time: E min  │      │  Time: F min │                │
│  └──────────────┘      └──────────────┘                │
│                                                         │
│  Quality Gap: |X - Y| percentage points                 │
│  Efficiency Gap: B/A token ratio                        │
│  Cost Gap: D/C cost ratio                               │
│                                                         │
└────────────────────────────────────────────────────────┘
```

### 4.2 Multi-Provider Advantage Measurement

Our unique value proposition is multi-provider support:

```
┌──────────────────────────────────────────────────────┐
│          Multi-Provider Value Proposition              │
│                                                       │
│  "Best model for each task" routing:                  │
│                                                       │
│  Task Category    │ Best Provider  │ Score │ Cost     │
│  ──────────────── │ ────────────── │ ───── │ ──────── │
│  Complex bugs     │ Claude Opus    │ 82%   │ $2.50    │
│  Simple refactor  │ Claude Haiku   │ 75%   │ $0.10    │
│  API integration  │ GPT-5.1        │ 78%   │ $1.20    │
│  Large codebase   │ Gemini 3 Pro   │ 73%   │ $0.80    │
│  Local/private    │ Llama 3.3      │ 55%   │ $0.00    │
│                                                       │
│  Blended score: 72.6%                                 │
│  Blended cost: $0.92/task                             │
│                                                       │
│  vs Claude Code (Opus only):                          │
│  Score: 80.9%, Cost: $2.50/task                       │
│                                                       │
│  Trade-off: -8.3% score, -63% cost                   │
│  Or: Match score by using Opus for hard tasks only    │
│                                                       │
└──────────────────────────────────────────────────────┘
```

### 4.3 Evaluation Dimensions

```
                         Quality
                           ▲
                           │
                      ●    │    ●
                  Claude   │  Harness+Opus
                   Code    │
                           │
               ●           │         ●
          Harness+Gemini   │    Harness+GPT
                           │
                           │
          ─────────────────┼─────────────────→ Cost Efficiency
                           │
               ●           │
          Harness+Llama    │
          (free, local)    │
                           │
```

---

## 5. Data Contamination & Fair Evaluation

### The HumanEval Problem

- **40% of HumanEval examples are contaminated** in modern LLMs
- Models show 20-31% score drops on HumanEval variants vs original
- This means HumanEval scores are unreliable for comparison

### Our Mitigation Strategy

1. **Use SWE-bench Verified** (primary) — real-world bugs, harder to memorize
2. **Use FeatBench** (secondary) — automated pipeline generates fresh tasks
3. **Use Terminal-Bench** (tertiary) — practical CLI operations
4. **Our Harness-Bench** — custom tasks we design, never published as training data
5. **Dynamic evaluation** — periodically refresh our custom benchmark tasks

### Cross-Provider Fairness

```python
class FairEvalConfig:
    """Ensure fair comparison across providers."""

    # Same temperature for all providers
    temperature: float = 0.0

    # Same max tokens
    max_tokens: int = 4096

    # Same system prompt (harness prompt, not provider-specific)
    system_prompt: str = HARNESS_SYSTEM_PROMPT

    # Same tool set
    tools: list[str] = ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]

    # Same timeout
    timeout_seconds: int = 600

    # Same max turns
    max_turns: int = 100

    # Run each task N times for statistical significance
    runs_per_task: int = 5
```

---

## 6. Metrics Dashboard

### Automated Reporting

```python
@dataclass
class EvalReport:
    # Identity
    harness_version: str
    provider: str
    model: str
    benchmark: str
    timestamp: datetime

    # Primary metrics
    resolved_pct: float         # Task completion rate
    pass_at_1: float           # Single-attempt success
    pass_at_5: float           # 5-attempt success

    # Efficiency metrics
    avg_tokens_per_task: int
    avg_cost_per_task: float
    avg_turns_per_task: float
    avg_tool_calls_per_task: float
    avg_time_per_task_sec: float

    # Quality metrics
    edit_accuracy: float        # Correct edits / total
    error_recovery_rate: float  # Recovered tasks / failed tasks
    tool_selection_accuracy: float

    # Harness metrics
    harness_overhead_tokens: int  # System prompt + tool defs
    compaction_triggered_pct: float
    provider_normalized_score: float

    def to_markdown(self) -> str:
        """Generate markdown report."""
        return f"""
## Evaluation Report: {self.benchmark}

| Metric | Value |
|--------|-------|
| Provider/Model | {self.provider}/{self.model} |
| Resolved% | {self.resolved_pct:.1f}% |
| Pass@1 | {self.pass_at_1:.1f}% |
| Pass@5 | {self.pass_at_5:.1f}% |
| Avg Tokens/Task | {self.avg_tokens_per_task:,} |
| Avg Cost/Task | ${self.avg_cost_per_task:.3f} |
| Avg Turns/Task | {self.avg_turns_per_task:.1f} |
| Avg Tool Calls | {self.avg_tool_calls_per_task:.1f} |
| Avg Time | {self.avg_time_per_task_sec:.0f}s |
| Edit Accuracy | {self.edit_accuracy:.1f}% |
| Error Recovery | {self.error_recovery_rate:.1f}% |
| Harness Overhead | {self.harness_overhead_tokens:,} tokens |
| Provider-Normalized | {self.provider_normalized_score:.1f}% |
"""
```

### CI/CD Integration

```yaml
# .github/workflows/eval.yml
name: Harness Evaluation
on:
  push:
    branches: [main]
  schedule:
    - cron: '0 0 * * 0'  # Weekly

jobs:
  swebench-lite:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        provider: [anthropic, openai, google]
    steps:
      - uses: actions/checkout@v4
      - run: uv sync
      - run: uv run python -m harness.eval.swebench --split lite --provider ${{ matrix.provider }}
      - uses: actions/upload-artifact@v4
        with:
          name: eval-results-${{ matrix.provider }}
          path: eval-results/
```

---

## 7. Performance Targets

### Phase 1 Targets (MVP)

| Metric | Target | Rationale |
|--------|--------|-----------|
| SWE-bench Verified (Opus) | ≥70% | Within 10pp of Claude Code's 80.9% |
| SWE-bench Verified (GPT-5.1) | ≥65% | Reasonable for non-Claude harness |
| Avg tokens/task | ≤50K | Efficient context usage |
| Avg cost/task (Sonnet) | ≤$0.50 | Affordable for regular use |
| Edit accuracy | ≥90% | Reliable file modifications |

### Phase 2 Targets (Mature)

| Metric | Target | Rationale |
|--------|--------|-----------|
| SWE-bench Verified (Opus) | ≥75% | Within 5pp of Claude Code |
| Terminal-Bench (Opus) | ≥55% | Practical CLI competence |
| Cross-provider variance | ≤5pp | Consistent harness quality |
| Provider-normalized score | ≥90% | Harness extracts most of model capability |
| Error recovery rate | ≥60% | Robust self-correction |

### Stretch Goals

| Metric | Target | What It Means |
|--------|--------|--------------|
| SWE-bench Verified (Opus) | ≥80% | Match Claude Code |
| FeatBench (any model) | ≥35% | Beat Trae-agent's 29.94% |
| Harness-Bench | ≥85% | Excellent on our own benchmark |
| "Best-of-provider" routing | ≥82% | Exceed any single-provider score |

---

## 8. Evaluation Infrastructure

### Docker-based Task Isolation

```python
class EvalEnvironment:
    """Isolated evaluation environment for each task."""

    async def setup(self, task: BenchmarkTask) -> None:
        """Create Docker container with task repository."""
        self.container = await docker.create(
            image=task.docker_image,
            volumes={task.repo_path: "/workspace"},
            network_mode="none",  # No network access during eval
        )

    async def run_agent(self, prompt: str, provider: str, model: str) -> Trajectory:
        """Run Harness agent inside container."""
        return await harness.run(
            prompt=prompt,
            provider=provider,
            model=model,
            cwd="/workspace",
            permission_mode="bypass",  # Full access in eval
            max_turns=100,
        )

    async def apply_patch(self, patch: str) -> None:
        """Apply agent's generated patch."""
        await self.container.exec(f"git apply --allow-empty <<'EOF'\n{patch}\nEOF")

    async def run_tests(self, test_commands: list[str]) -> TestResult:
        """Run task's test suite."""
        for cmd in test_commands:
            result = await self.container.exec(cmd, timeout=300)
            if result.returncode != 0:
                return TestResult(passed=False, output=result.stderr)
        return TestResult(passed=True)
```

### Trajectory Logging

```python
@dataclass
class Trajectory:
    """Complete record of an agent run for analysis."""

    task_id: str
    provider: str
    model: str
    messages: list[dict]          # Full conversation
    tool_calls: list[ToolCallRecord]
    total_tokens: int
    total_cost: float
    turns: int
    duration: float
    errors: list[str]
    final_patch: str | None

    def save(self, path: Path) -> None:
        """Save trajectory for post-hoc analysis."""
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=2)
```

---

## 9. Continuous Improvement Loop

```
┌─────────────────────────────────────────┐
│         Evaluation-Driven Development    │
│                                          │
│  1. Run benchmarks (weekly)              │
│           ↓                              │
│  2. Identify failure patterns            │
│           ↓                              │
│  3. Categorize failures:                 │
│     - Tool selection errors              │
│     - Context overflow                   │
│     - Edit accuracy issues               │
│     - Permission/safety issues           │
│     - Provider-specific bugs             │
│           ↓                              │
│  4. Fix highest-impact category          │
│           ↓                              │
│  5. Re-run benchmarks                    │
│           ↓                              │
│  6. Publish updated results              │
│           ↓                              │
│  7. Repeat                               │
│                                          │
└─────────────────────────────────────────┘
```

### Failure Analysis Categories

```python
class FailureCategory(Enum):
    WRONG_TOOL = "wrong_tool"           # Used grep when should use glob
    WRONG_FILE = "wrong_file"           # Edited wrong file
    WRONG_EDIT = "wrong_edit"           # Edit didn't achieve intent
    CONTEXT_OVERFLOW = "context_overflow" # Ran out of context
    LOOP_STUCK = "loop_stuck"           # Agent loops without progress
    PERMISSION_DENIED = "permission"     # Blocked by permissions
    PROVIDER_ERROR = "provider_error"    # API error or timeout
    INCOMPLETE = "incomplete"           # Gave up too early
    OVERCOMPLETE = "overcomplete"       # Changed too much
```

---

## 10. Summary: Evaluation Strategy

1. **Primary benchmark**: SWE-bench Verified — industry standard, real-world bugs
2. **Secondary benchmarks**: Terminal-Bench, FeatBench, Harness-Bench (custom)
3. **Multi-provider matrix**: Test every provider × model combination
4. **Fair comparison**: Same harness config, temperature 0, 5 runs per task
5. **Metrics**: Resolved%, token efficiency, cost, edit accuracy, error recovery
6. **Unique metric**: Provider-Normalized Score (isolates harness quality from model quality)
7. **CI/CD**: Weekly automated evaluation runs with published results
8. **Continuous improvement**: Failure categorization → targeted fixes → re-evaluate

**Target**: Achieve ≥90% Provider-Normalized Score (meaning our harness extracts ≥90% of each model's theoretical maximum performance).
