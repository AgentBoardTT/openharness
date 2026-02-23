# Comprehensive Research: Evaluating and Benchmarking Coding Agents

## Executive Summary

This document provides a deep research overview of how to evaluate and benchmark coding agents, covering major benchmarks (SWE-bench, HumanEval, Aider, Terminal-Bench), evaluation metrics, and frameworks. As of February 2026, Claude Opus 4.5 leads on SWE-bench Verified with 80.9%, while frontier models achieve <65% on Terminal-Bench's harder CLI tasks.

---

## 1. SWE-BENCH: The Main Benchmark for Coding Agents

### 1.1 How SWE-bench Works

[SWE-bench](https://www.swebench.com/) evaluates language models on **real-world software engineering tasks** by testing their ability to resolve GitHub issues from popular open-source Python repositories. The evaluation process:

1. **Task Setup**: Each instance contains a GitHub issue, repository context, base commit, problem statement
2. **Agent Action**: Model generates a patch/code changes
3. **Docker Isolation**: Patch is applied in a containerized Docker environment
4. **Test Validation**: Repository's test suite is executed to determine success
5. **Verification**: Tests categorized as "FAIL_TO_PASS" (should pass) and "PASS_TO_PASS" (should remain passing)

**Key Feature**: Evaluation via unit test verification using post-PR behavior as reference solution.

### 1.2 SWE-bench Dataset Variants

| Variant | Instances | Focus | Use Case |
|---------|-----------|-------|----------|
| **SWE-bench Full** | 2,294 | Comprehensive coverage across diverse repos | Research, thorough evaluation |
| **SWE-bench Lite** | 534 | Reduced subset for faster iteration | Model development, quick testing |
| **SWE-bench Verified** | 500 | Human-annotated, "expert-verified solvable" | High-quality evaluation, leaderboard ranking |
| **SWE-bench Pro** | 731 | GPL-licensed open-source only | Public reproducibility focus |

**Difference between Lite and Verified**:
- **Lite**: Subsampled the original dataset to reduce evaluation costs and enable faster iteration (EASIER tasks)
- **Verified**: Filtered the original dataset to remove infeasible/problematic samples through human review (HIGHER QUALITY)

[Dataset Documentation](https://www.swebench.com/SWE-bench/guides/datasets/)

### 1.3 SWE-bench Leaderboard Results (2025-2026)

#### SWE-bench Verified Leaders (2026)

| Model | Score | Organization | Notes |
|-------|-------|--------------|-------|
| **Claude Opus 4.5** | **80.9%** | Anthropic | New state-of-the-art, first to exceed 80% |
| Claude Sonnet 4.5 | 77.2% | Anthropic | 10 trials averaged, 200K thinking budget |
| GPT-5.1 | 76.3% | OpenAI | |
| Gemini 3 Pro | 76.2% | Google | |

#### SWE-bench Pro Leaders (January 2026)

| Model | Score | Notes |
|-------|-------|-------|
| Claude Opus 4.5 | 45.89±3.60 | More challenging (GPL-licensed only) |
| Claude 4.5 Sonnet | 43.60±3.60 | |
| Gemini 3 Pro Preview | 43.30±3.60 | |

**Key Insight**: Claude Opus 4.5 represents a 65% improvement over Claude 3.5 Sonnet (49%).

#### SWE-bench-Live with SWE-agent

Claude Sonnet 4.5 + Live-SWE-agent achieved **45.8% solve rate** on SWE-Bench Pro (November 2025).

**Recent Developments (Feb 2026)**:
- SWE-bench-Live/Windows version for testing agents in Windows PowerShell
- RepoLaunch Agent upgraded to support 8+ languages (C, C++, C#, Python, Java, Go, JS/TS, Rust) on Linux and Windows

[Leaderboards](http://www.swebench.com/) | [SWE-bench Pro](https://scale.com/leaderboard/swe_bench_pro_public) | [LLM-Stats](https://llm-stats.com/benchmarks/swe-bench-verified)

### 1.4 Running SWE-bench Evaluations

#### System Requirements

- **Storage**: 120GB+ free disk space
- **RAM**: 16GB minimum
- **CPU**: 8+ cores (use fewer than `min(0.75 * cpu_count, 24)` for workers)
- **Platform**: x86_64 architecture required

#### Installation & Setup

```bash
# Clone and install
git clone https://github.com/SWE-bench/SWE-bench.git
cd SWE-bench
pip install -e .

# Follow Docker setup guide
# https://www.swebench.com/SWE-bench/guides/docker_setup/
```

#### Basic Evaluation Command

```bash
python -m swebench.harness.run_evaluation \
  --dataset_name princeton-nlp/SWE-bench_Verified \
  --predictions_path <path_to_predictions> \
  --max_workers 8 \
  --cache_level env
```

#### Docker Caching Strategy

Cache levels available: `none`, `base` (common dependencies), `env` (Python environments), `instance` (task-specific). Use `env` or `base` for reduced disk requirements.

[Docker Setup Guide](https://www.swebench.com/SWE-bench/guides/docker_setup/) | [Evaluation Guide](https://www.swebench.com/SWE-bench/guides/evaluation/) | [One-Hour Setup](https://epoch.ai/blog/swebench-docker)

### 1.5 What Constitutes a Good SWE-bench Score?

| Score Range | Assessment | Context |
|-------------|-----------|---------|
| **75-80%** | State-of-the-art | Only Claude Opus 4.5+ achieves this |
| **70-74%** | Frontier model level | GPT-5, Gemini 3 Pro range |
| **60-70%** | Strong performance | Advanced agents with good harnesses |
| **50-60%** | Solid baseline | Competitive agent implementations |
| **<50%** | Developing capability | Earlier models or basic implementations |

**Context**: SWE-bench Verified is considered significantly harder than Lite. Most models show 20-25% lower performance on Verified vs Lite.

---

## 2. HumanEval / HumanEval+ Benchmarks

### 2.1 Overview

[HumanEval](https://llm-stats.com/benchmarks/humaneval) is a benchmark of **164 hand-written coding problems** from Python programming to evaluate LLM code generation capabilities. Each problem includes function signature, docstring, and unit tests.

**HumanEval+** (aka EvalPlus) adds **more comprehensive test cases** to catch edge cases and improve robustness evaluation.

### 2.2 Latest Results (2025)

| Model | HumanEval Pass@1 | EvalPlus Pass@1 | Notes |
|-------|------------------|-----------------|-------|
| **OpenAI O1 Preview** | 96.3% | 89% | State-of-the-art |
| **OpenAI O1 Mini** | 96.3% | 89% | |
| Claude Opus 3.5 | ~92% | ~84% | Estimated |
| GPT-4o | ~90% | ~81% | |

**Key Finding**: 234% improvement over original Codex baseline.

### 2.3 Critical Issues: Data Contamination & Memorization

**Major Concern**: Contemporary models show significant performance drops on variants due to memorization rather than true generalization.

#### Contamination Statistics

- **40% of HumanEval examples identified as contaminated** in pre-training datasets
- Pass@1 drops for HumanEval_T (template variants): **up to 14 percentage points**
- On HumanEvalNext vs HumanEval: **20-31 percentage point drops**, indicating overfitting

#### Robustness Issues

Research found:
- Top models show **19.6–47.7 percentage point pass@1 drops** on semantically transformed tasks (EvoEval)
- Memorization detected across multiple models including ChatGPT
- Models achieve ~90% on original but significantly lower on variants

#### Solutions

1. **HumanEval-T**: Uses template-based abstraction with combinatorial covering arrays
2. **LiveCodeBench**: Continuously updated, contamination-free evaluation
3. **KodCode**: Synthetic dataset with 447K triplets yielding 1.8 point improvements through test-based filtering

**Recommendation**: Use EvalPlus or dynamic benchmarks rather than relying solely on HumanEval scores.

[HumanEval Leaderboard](https://llm-stats.com/benchmarks/humaneval) | [EvalPlus](https://evalplus.github.io/leaderboard.html) | [LiveCodeBench](https://livecodebench.github.io/)

---

## 3. AIDER BENCHMARK

### 3.1 Overview

[Aider](https://aider.chat/docs/benchmarks.html) provides a **practical benchmarking framework** for measuring LLM performance at **code generation and editing tasks** using real-world exercises.

### 3.2 Benchmark Variants

#### Python Benchmark
- **Dataset**: 133 practice exercises from Exercism Python repository
- **Focus**: Basic code generation and editing in Python

#### Polyglot Benchmark
- **Languages**: C++, Go, Java, JavaScript, Python, Rust
- **Tasks**: 225 of Exercism's most challenging problems
- **Evaluation**: 2-attempt format - agents get a second chance after seeing test failures

#### Refactoring Benchmark
- **Focus**: Exposes "lazy coding" in GPT-4 Turbo models
- **Task**: Refactor existing code to improve quality while maintaining functionality

### 3.3 What It Measures

1. **Functional Code Quality**: Can the model write code that passes unit tests?
2. **Edit Capability**: Can the model edit files based on natural language requests?
3. **Format Correctness**: Can the model format edits so the tool can save them?

**Key Finding**: Success requires excelling at ALL THREE - failure in any aspect results in task failure.

### 3.4 Evaluation Methodology

- **Environment**: Docker containers for safety
- **Edit Format**: Whole-file markdown fenced code blocks most reliable (GPT-3.5), diff format for GPT-4
- **Test Execution**: Direct unit test verification

[Aider Benchmarks](https://aider.chat/docs/benchmarks.html) | [Leaderboards](https://aider.chat/docs/leaderboards/) | [Polyglot Benchmark](https://llm-stats.com/benchmarks/aider-polyglot)

---

## 4. TERMINAL-BENCH: CLI-Specific Agent Benchmark

### 4.1 Overview

[Terminal-Bench](https://www.tbench.ai/leaderboard) is a recent benchmark (May 2025) for evaluating AI agents on **real, realistic tasks in command-line environments**. It tests agents' ability to navigate, explore, and manipulate sandboxed terminal environments.

### 4.2 Benchmark Characteristics

- **Task Count**: 89 carefully curated terminal-based tasks
- **Domains**: Software engineering, system administration, scientific computing, cryptanalysis, binary reverse-engineering
- **Evaluation**: Outcome-driven - does the final container state satisfy verification tests?

### 4.3 Task Complexity Analysis

| Complexity | Percentage | Context |
|-----------|-----------|---------|
| <1 hour for expert | 48.6% | Quick tasks |
| 1-24 hours for junior engineer | 71.6% | Moderate complexity |
| 24+ hours | 28.4% | Complex, specialized tasks |

### 4.4 Terminal-Bench 2.0 Results

**Performance (Frontier Models/Agents)**:
- **Best**: GPT-5.2 with Codex CLI: **62.9% resolution rate**
- **General Performance**: Frontier closed-source models: <65% resolution
- **Open-weight models**: 3-36% resolution
- **Mini-SWE-Agent**: >74% on SWE-bench Verified (different benchmark)

**Agents Tested**: Claude Code, Codex CLI, OpenHands, Mini-SWE-Agent, Terminus 2, SWE-agent

### 4.5 Error Analysis

**Common Failure Modes**:
1. **Missing Executables**: 24.1% (most common command-level failure)
2. **Execution Errors**: Trajectory-level failures
3. **Coherence Errors**: Loss of task context
4. **Verification Errors**: Output format issues

### 4.6 Why Terminal-Bench Matters

- **Real-world relevance**: Interactive shell environment mirrors actual developer workflows
- **Tool chain complexity**: Requires navigation, file manipulation, tool invocation
- **Higher difficulty**: More challenging than SWE-bench due to open-ended nature
- **Multi-step reasoning**: Complex tasks requiring planning and error recovery

[Terminal-Bench Leaderboard](https://www.tbench.ai/leaderboard) | [Paper](https://arxiv.org/html/2601.11868v1)

---

## 5. KEY METRICS FOR EVALUATING CODING AGENTS

### 5.1 Task Success Metrics

| Metric | Definition | Good Target |
|--------|-----------|------------|
| **Resolved Rate %** | % of tasks fully completed with working feature and no regressions | 60-80% (frontier models) |
| **Patch Apply Rate %** | % of tasks where generated patches can be applied cleanly (no syntax/merge errors) | 85-95% |
| **File Localization Rate %** | % of tasks where agent edits the correct files | 80-90% |
| **Feature Validation Pass Rate %** | % of new features that work as intended | 75-90% |
| **Regression Tests Pass Rate %** | % of existing tests that still pass (no breakage) | 90-98% |

### 5.2 Code Quality Metrics

#### Functional Correctness
- **Pass@k**: Probability of at least 1 correct solution in k attempts
- **Pass^k**: Probability that ALL k attempts succeed (critical for reliability)
- **Unit Test Pass Rate**: % of generated code passing curated test suites

#### Syntactic & Semantic Quality
- **CodeBLEU**: Combines token-level similarity with AST/dataflow matching (but can be overly strict)
- **Syntax Validity**: Compilable/parseable code without errors
- **Static Analysis**: Lint errors, code complexity, security vulnerabilities

#### Edit Quality
- **Edit Accuracy**: Correct edits / total edits attempted
- **File Modification Success**: Successfully applying multiple file changes
- **Format Correctness**: Output in format tool can parse and save

### 5.3 Efficiency Metrics

#### Token Efficiency
- **Tokens per Task**: Average input + output tokens consumed
- **Token Variance**: Some tasks use 10x more tokens than others (indicate instability)
- **Cost per Resolved Task**: Total API cost / number of successfully completed tasks

**Findings**:
- Complex tasks consume more tokens (expected)
- High variance indicates need for better prompting/planning
- Input tokens dominate output tokens (even with caching)
- High-performing agents often use 10-50x more tokens

#### Operational Efficiency
- **Step Efficiency**: (minimum required steps / actual steps taken) × 100
- **Tool Call Accuracy**: Relevant tool calls / total tool calls
- **Replan Rate**: % of trajectories requiring replanning

### 5.4 Error Recovery & Robustness

| Metric | Definition | Assessment |
|--------|-----------|-----------|
| **Error Recovery Rate** | % of tasks where agent recovers from failures | High variability: 40-80% |
| **Recurrence Ratio** | Fraction of error types that recur across tasks | <0.3 ideal |
| **Affected Tasks Metric** | How widely an error type is distributed | Reveals systematic weaknesses |
| **Max Retries to Success** | How many attempts before task completion | >5 indicates poor recovery |

### 5.5 Latency & Throughput

| Metric | Target (Acceptable) | Target (Ideal) |
|--------|-------------------|----------------|
| **P50 Latency** | <2000ms | <500ms |
| **P95 Latency** | <5000ms | <1000ms |
| **Throughput** | 10+ tasks/hour | 20+ tasks/hour |
| **Total Time to Resolution** | <5 minutes | <2 minutes |

### 5.6 Production-Level Metrics

| Metric | Definition | Weight |
|--------|-----------|--------|
| **Reliability** | Consistent success rate across runs | 30% |
| **Speed** | Latency and throughput | 25% |
| **Cost** | Token/API consumption | 20% |
| **Safety** | No system damage, proper isolation | 15% |
| **Integration Fit** | Compatibility with existing tools/workflows | 10% |

---

## 6. CLAUDE CODE: Anthropic's Evaluation Approach

### 6.1 Claude Models' SWE-bench Performance

**Historical Progression**:
- Claude 3.5 Sonnet: 49% on SWE-bench Verified
- Claude Sonnet 4.5: 77.2% (averaging over 10 trials with 200K thinking budget)
- **Claude Opus 4.5: 80.9%** (first to exceed 80% threshold)

**Comparison**:
- 65% improvement from 3.5 to Opus 4.5
- Exceeds GPT-5.1 (76.3%) and Gemini 3 Pro (76.2%)

### 6.2 Anthropic's Multi-Layered Evaluation Framework

[Anthropic Engineering Post](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

#### Three Grader Types

1. **Code-based Graders** (Fast & Objective)
   - String matching
   - Static analysis
   - Outcome verification in environment
   - Used for: unit test results, file output validation

2. **Model-based Graders** (Flexible & Scalable)
   - Rubric-based scoring with LLM evaluation
   - Natural language assertions
   - Reasoning quality assessment
   - Used for: code quality, design evaluation

3. **Human Graders** (Gold Standard)
   - Expert review
   - Spot-check sampling (10-20% of failures)
   - Edge case validation

#### Key Non-Determinism Metrics

- **Pass@k**: Likelihood that agent gets ≥1 correct solution in k attempts
- **Pass^k**: Probability that ALL k attempts succeed (critical for customer-facing reliability)

#### Evaluation Structure

1. **Define Clear Tasks**: Specific, measurable objectives
2. **Create Multi-Assertion Graders**: Multiple checks per task
3. **Record Full Transcripts**: Complete interaction history
4. **Verify Environment State**: Final state meets requirements

#### Capability vs. Regression Testing

- **Capability Evals**: Start at low pass rate, target agent weaknesses
- **Regression Evals**: Maintain ~100% pass rate, prevent performance decline
- **Frequency**: Run regressions on every change, capabilities during development

#### Agent-Specific Approaches

| Agent Type | Grading Method | Key Metrics |
|-----------|---------------|------------|
| **Coding Agents** | Deterministic test suites | Pass@k, test coverage, no regressions |
| **Conversational Agents** | Multi-turn simulation + rubrics | Coherence, groundedness, topic adherence |
| **Research Agents** | Custom groundedness checks | Citation accuracy, coverage, relevance |

### 6.3 Best Practices from Anthropic

- **Early eval development**: Build evals from the start, not as afterthought
- **Continuous monitoring**: Pair evals with production monitoring and user feedback
- **Diverse eval sets**: Mix of deterministic, stochastic, and human evaluation
- **Reproducibility**: Fixed seeds, versioned test suites

---

## 7. MULTI-PROVIDER EVALUATION CHALLENGES

### 7.1 Fair Comparison Issues

#### Model Capability vs. Harness Capability

**Problem**: When comparing agents across different LLMs, hard to isolate:
- Model's inherent capabilities (reasoning, code understanding)
- Harness quality (prompting, tool design, planning)
- Implementation differences (retry logic, caching, timeouts)

**Solutions**:

1. **Standardized Evaluation Framework** (like [lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness))
   - Same exact inputs for all models
   - Unified codebase for testing
   - Reproducible results
   - Used by 100+ organizations including NVIDIA, Cohere

2. **Isolate Variables**:
   - Use same harness code for all models
   - Control for prompt engineering differences
   - Fix tool calling patterns
   - Same timeout/retry policies

3. **CLASSIC Framework** (emerging standard):
   - **C**ost
   - **L**atency
   - **A**ccuracy
   - **S**tability
   - **C**ompliance/Security

### 7.2 Benchmarking Challenges

#### Data Contamination Risk
- Models may be trained on benchmark data
- Test set leakage inflates performance
- 40% of HumanEval identified as contaminated

#### Solutions
- Use **multiple, non-overlapping benchmarks**
- Employ **dynamic benchmarks** (continuously updated)
- Create **benchmark variants** to test robustness
- Check for **memorization** vs. generalization

#### Cost-Performance Tradeoffs

| Scenario | Tokens per Task | Cost per Task | Success Rate |
|----------|-----------------|---------------|-------------|
| Basic agent | ~50K | $0.50 | 50% |
| Intermediate agent | ~150K | $1.50 | 70% |
| Advanced agent (Trae-agent) | ~500K | $5.00 | 78% |
| Agentless (efficient) | ~100K | $1.00 | 60% |

**Key Insight**: Higher success often comes at 5-10x token cost.

### 7.3 Standardization Approaches

#### EleutherAI LM Evaluation Harness
- 60+ standard academic benchmarks
- Hundreds of subtasks and variants
- Used for Hugging Face Open LLM Leaderboard
- Ensures comparability across papers

#### Stanford HELM (Holistic Evaluation)
- Multi-dimensional performance analysis
- Multiple scenarios and metrics
- Fairness and robustness assessment

---

## 8. EMERGING BENCHMARKS & FRAMEWORKS

### 8.1 FeatBench (Feature Implementation)

[FeatBench Paper](https://arxiv.org/html/2509.22237)

**Focus**: Realistic feature-level implementation scenarios ("vibe coding")

**Key Features**:
- **Realistic Inputs**: Natural language requirements only, NO code hints
- **Evolving Data**: Automated pipeline from latest repos (mitigates contamination)
- **Comprehensive Tests**: Fail-to-Pass (F2P) and Pass-to-Pass (P2P) tests
- **Current Performance**: Trae-agent with GPT-5: 29.94% resolved (challenging!)

**Task Count**: 157 tasks from 27 actively maintained repositories

### 8.2 OpenHands Framework (2025 Update)

[OpenHands](https://openhands.dev/)

**OpenHands Index** (New):
- First broad-coverage, continuously-updated leaderboard
- 5 evaluation tasks: issue resolution, greenfield apps, frontend dev, testing, information gathering
- Metrics: Ability, Cost, Runtime

**Performance Metrics**:
- SWE-Bench Verified: State-of-the-art results
- Multi-SWE-Bench: First place (8 programming languages)
- LiveSWEBench: Top performer

**Evaluation at 32x Parallel Speed**: Can evaluate SWE-bench Lite in hours vs. days

### 8.3 LiveCodeBench

[LiveCodeBench](https://livecodebench.github.io/)

**Purpose**: Contamination-free, continuously updated code generation benchmark

**Advantages**:
- Dynamic benchmark updates
- Prevents memorization exploitation
- Reflects current LLM capabilities

### 8.4 BigCodeBench & CodeXGLUE

- **BigCodeBench**: Next-generation HumanEval
- **CodeXGLUE**: Multi-task code understanding benchmark

---

## 9. IMPLEMENTING AN EFFECTIVE EVALUATION FRAMEWORK

### 9.1 Recommended Multi-Benchmark Approach

#### Tier 1: Core Benchmarks (Always Use)
1. **SWE-bench Verified**: Gold standard for issue resolution
2. **HumanEval + EvalPlus**: Code generation capability (with robustness variant)
3. **Terminal-Bench**: CLI/shell interaction realism

#### Tier 2: Specialized Benchmarks (Domain-Specific)
1. **Aider Polyglot**: Multi-language editing capability
2. **FeatBench**: Feature implementation (real-world tasks)
3. **OpenHands Index**: Broad task diversity

#### Tier 3: Custom Evaluation (Your Specific Use Case)
1. Your own domain-specific test suite
2. Real production issues/tasks
3. Cost and latency baselines

### 9.2 Evaluation Checklist

- [ ] **Correctness**: Unit tests pass, no regressions
- [ ] **Efficiency**: Measure tokens/cost per task
- [ ] **Latency**: Track P50 and P95 response times
- [ ] **Robustness**: Test on benchmark variants
- [ ] **Error Recovery**: Can agent fix its own mistakes?
- [ ] **Integration**: Works with your tool ecosystem
- [ ] **Reproducibility**: Docker/containerized, fixed seeds
- [ ] **Data Cleanliness**: Check for contamination
- [ ] **Multi-metric**: Don't optimize for single metric
- [ ] **Production Monitoring**: Track real-world performance

### 9.3 Metrics to Track Over Time

```
Weekly Monitoring:
- Resolved rate (% complete)
- Cost per task (tokens × price)
- P95 latency (max 5 seconds target)
- Error recovery rate
- Regression test pass rate

Monthly Monitoring:
- Benchmark score improvements
- Token consumption trends
- Cost per unit capability
- New failure patterns
- Model upgrade impact
```

### 9.4 Statistical Rigor

- **Multiple runs**: Run each task 3-5 times, report mean ± std dev
- **Significance testing**: Use statistical tests for <0.5% differences
- **Confidence intervals**: Report 95% CI on all metrics
- **Sample size**: Sufficient samples (N>30) for statistical validity

---

## 10. COMPARISON TABLE: All Benchmarks

| Benchmark | Type | Scale | Difficulty | Key Metric | 2025 SOTA |
|-----------|------|-------|-----------|-----------|----------|
| **SWE-bench Verified** | Issue resolution | 500 tasks | Medium-High | Resolved % | 80.9% (Opus 4.5) |
| **SWE-bench Lite** | Issue resolution | 534 tasks | Medium | Resolved % | ~85% (frontier) |
| **Terminal-Bench** | CLI tasks | 89 tasks | Very High | Resolution % | 62.9% (GPT-5.2) |
| **HumanEval** | Code generation | 164 tasks | Low-Medium | Pass@1 | 96.3% (O1) |
| **HumanEval+** | Code generation | 164 tasks + extra tests | Medium | Pass@1 | 89% (O1) |
| **Aider Polyglot** | Code editing | 225 tasks | Medium | Success % | ~70% (frontier) |
| **FeatBench** | Feature impl. | 157 tasks | Medium-High | Resolved % | 29.94% (GPT-5) |
| **LiveCodeBench** | Code generation | Dynamic | Variable | Pass@1 | Varies by update |

---

## 11. KEY TAKEAWAYS FOR HARNESS DESIGN

### 11.1 What Makes a Strong Evaluation Harness

1. **Isolation**: Use Docker containers for safety and reproducibility
2. **Determinism**: Fixed seeds, controlled environments, no randomness
3. **Transparency**: Log all agent actions, decisions, tool calls
4. **Comprehensiveness**: Multiple metrics, not just pass/fail
5. **Realism**: Real-world tasks, not synthetic/overly constrained
6. **Efficiency**: Can run evaluations in reasonable time (hours, not days)
7. **Scalability**: Can add new benchmarks/tasks easily
8. **Fairness**: Controls for model capability vs. harness quality

### 11.2 Metrics Most Correlated with Real Success

1. **Task completion rate**: Single best indicator
2. **Error recovery rate**: Indicates robustness
3. **Cost per task**: Practical viability metric
4. **Token efficiency**: Sustainability metric
5. **Regression test pass**: Safety indicator

### 11.3 Red Flags in Agent Evaluation

- ❌ **Only using one benchmark**: Risks overfitting to that benchmark
- ❌ **Not tracking cost/efficiency**: Unrealistic in production
- ❌ **Ignoring error recovery**: Agents fail regularly
- ❌ **No data contamination check**: Results not trustworthy
- ❌ **Single run per task**: High variance, unreliable
- ❌ **P50 latency focus**: Should focus on P95 for reliability
- ❌ **No reproducibility controls**: Results not repeatable

---

## RESOURCES & REFERENCES

### Primary Benchmarks
- [SWE-bench Official](https://www.swebench.com/)
- [HumanEval](https://github.com/openai/human-eval)
- [Aider Benchmarks](https://aider.chat/docs/benchmarks.html)
- [Terminal-Bench](https://www.tbench.ai/)
- [OpenHands](https://openhands.dev/)

### Leaderboards
- [SWE-bench Verified Leaderboard](https://llm-stats.com/benchmarks/swe-bench-verified)
- [SWE-bench Pro](https://scale.com/leaderboard/swe_bench_pro_public)
- [HumanEval Leaderboard](https://llm-stats.com/benchmarks/humaneval)
- [OpenHands Index](https://openhands.dev/blog/openhands-index)

### Evaluation Frameworks
- [EleutherAI lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness)
- [Anthropic Eval Principles](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- [OpenHands Evaluation Harness](https://docs.openhands.dev/openhands/usage/developers/evaluation-harness)

### Key Papers & Research
- [SWE-bench Paper](https://arxiv.org/abs/2310.06799)
- [Terminal-Bench](https://arxiv.org/html/2601.11868v1)
- [FeatBench](https://arxiv.org/html/2509.22237)
- [Token Consumption Analysis](https://openreview.net/forum?id=1bUeVB3fov)
- [Data Contamination Survey](https://arxiv.org/html/2406.04244v1)

### Related Articles
- [Machine Learning Mastery: Agent Evaluation](https://machinelearningmastery.com/agent-evaluation-how-to-test-and-measure-agentic-ai-performance/)
- [Braintrust: AI Agent Evaluation Framework](https://www.braintrust.dev/articles/ai-agent-evaluation-framework/)
- [Google Cloud: Methodical Approach to Agent Evaluation](https://cloud.google.com/blog/topics/developers-practitioners/a-methodical-approach-to-agent-evaluation)

---

## NEXT STEPS FOR YOUR EVALUATION FRAMEWORK

Based on this research, here's what you should focus on:

1. **Implement SWE-bench Integration**: Most authoritative benchmark for coding agents
2. **Add Terminal-Bench**: Test real CLI interaction capability
3. **Build Custom Metrics Dashboard**: Track efficiency, cost, latency
4. **Set up Reproducibility Controls**: Docker, fixed seeds, multiple runs
5. **Create Baseline Comparisons**: Establish performance targets
6. **Implement Error Analysis**: Understand failure patterns
7. **Monitor for Data Contamination**: Verify results aren't inflated
8. **Plan for Multi-Model Testing**: Compare across Claude, GPT, Gemini

---

**Document Generated**: February 21, 2026
**Research Scope**: SWE-bench, HumanEval, Aider, Terminal-Bench, evaluation frameworks
**Sources**: 30+ academic papers, official benchmarks, and 2025-2026 leaderboards
