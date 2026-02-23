# Quick Reference: Coding Agent Evaluation

## TL;DR - Key Facts

| Fact | Value |
|------|-------|
| **SOTA on SWE-bench** | Claude Opus 4.5: 80.9% (Verified) |
| **SOTA on HumanEval** | O1/O1-mini: 96.3% Pass@1 |
| **SOTA on Terminal-Bench** | GPT-5.2 + Codex: 62.9% |
| **Best benchmark to use** | SWE-bench Verified (500 tasks, human-curated) |
| **Runtime per task** | 2-5 minutes (single threaded) |
| **Total eval time** | SWE-Lite: 2-3 hours (8 workers), SWE-Verified: 6-12 hours |
| **Cost per evaluation** | $50-200 depending on model and tokens |
| **Critical metric** | Resolved Rate % (most comprehensive) |
| **Data contamination risk** | HIGH - 40% of HumanEval contaminated |
| **Most important benchmark property** | Uses real GitHub issues, real test suites |

---

## Benchmark Comparison Matrix

### Performance (SOTA scores)

```
╔═════════════════╦═════════╦═══════════╦══════════════════╗
║ Benchmark       ║ Variant ║ SOTA      ║ Key Difference   ║
╠═════════════════╬═════════╬═══════════╬══════════════════╣
║ SWE-bench       ║ Lite    ║ ~85%      ║ 534 easier tasks ║
║ SWE-bench       ║ Verified║ 80.9%     ║ 500 curated      ║
║ SWE-bench       ║ Pro     ║ 45.89%    ║ 731 GPL only     ║
║ HumanEval       ║ Base    ║ 96.3%     ║ 164 problems     ║
║ HumanEval+      ║ Plus    ║ 89%       ║ More test cases  ║
║ Terminal-Bench  ║ 2.0     ║ 62.9%     ║ 89 CLI tasks     ║
║ Aider Polyglot  ║ 6 lang  ║ ~70%      ║ Code editing     ║
║ FeatBench       ║ All     ║ 29.94%    ║ Feature impl     ║
╚═════════════════╩═════════╩═══════════╩══════════════════╝
```

### Key Characteristics

```
╔═══════════════════╦════════════╦═══════════╦═════════════╦════════════╗
║ Benchmark         ║ Task Count ║ Difficulty║ Realistic   ║ Safe to Run║
╠═══════════════════╬════════════╬═══════════╬═════════════╬════════════╣
║ SWE-bench Lite    ║ 534        ║ Medium    ║ Very High   ║ Yes        ║
║ SWE-bench Verified║ 500        ║ Medium-Hi ║ Very High   ║ Yes        ║
║ Terminal-Bench    ║ 89         ║ Very High ║ Very High   ║ Yes*       ║
║ HumanEval         ║ 164        ║ Low-Med   ║ Medium      ║ Yes        ║
║ Aider Polyglot    ║ 225        ║ Medium    ║ Medium-Hi   ║ Yes        ║
║ FeatBench         ║ 157        ║ High      ║ High        ║ Yes        ║
║ Custom/Domain     ║ Varies     ║ Varies    ║ Highest     ║ Varies     ║
╚═══════════════════╩════════════╩═══════════╩═════════════╩════════════╝
```

*Terminal-Bench safe but resource-intensive

---

## Metric Priority & Targets

### Tier 1 (Must Track)

| Metric | What It Measures | Good Target | How to Improve |
|--------|-----------------|------------|----------------|
| **Resolved Rate %** | Task completion | 60%+ | Better planning, tool use, error recovery |
| **Patch Apply Rate %** | Code quality | 90%+ | Syntax validation, format checking |
| **Cost per Task** | Efficiency | <$2 (frontier) | Token caching, early stopping |
| **Regression Rate %** | Safety | 95%+ | Test coverage, validation |

### Tier 2 (Important)

| Metric | What It Measures | Target | Note |
|--------|-----------------|--------|------|
| **P95 Latency** | Responsiveness | <300s | P50 less important than P95 |
| **Edit Accuracy %** | Code precision | 85%+ | Critical for production |
| **Error Recovery %** | Robustness | 60%+ | How often agent fixes mistakes |
| **File Localization %** | Targeting | 80%+ | Does agent edit right files? |

### Tier 3 (Diagnostic)

| Metric | Purpose | Notes |
|--------|---------|-------|
| **Token Variance** | Consistency check | High variance = planning issues |
| **Error Pattern Freq** | Problem identification | 80/20: 20% of error types cause 80% failures |
| **Retry Distribution** | Effort distribution | Should be left-skewed (most resolve quickly) |
| **Tool Call Success %** | Tool effectiveness | Baseline for tooling improvements |

---

## Running Benchmarks: Quick Commands

### SWE-bench

```bash
# Install
pip install swebench

# Run Verified (standard)
python -m swebench.harness.run_evaluation \
  --dataset_name princeton-nlp/SWE-bench_Verified \
  --predictions_path <path> \
  --max_workers 8

# Run Lite (faster, for testing)
python -m swebench.harness.run_evaluation \
  --dataset_name princeton-nlp/SWE-bench_Lite \
  --predictions_path <path> \
  --max_workers 8
```

### Terminal-Bench

```bash
# Install
pip install terminal-bench

# Run
tb.run --agent <agent_name> --output results.json
```

### Aider

```bash
# Polyglot evaluation
aider-eval polyglot --output results.json
```

---

## Common Pitfalls & Solutions

| Pitfall | Problem | Solution |
|---------|---------|----------|
| **Only using one benchmark** | Overfitting to benchmark patterns | Use 3+ benchmarks, diverse domains |
| **Ignoring token cost** | Unrealistic in production | Track cost per task, set budgets |
| **Single run per task** | High variance skews results | Run N=3+ times, report confidence intervals |
| **Optimizing for mean** | Outliers destroy production UX | Focus on P95, P99 latency |
| **No error classification** | Can't fix systematic issues | Categorize every error, rank by frequency |
| **Comparing raw scores** | Different benchmarks not comparable | Use percentile ranks or normalized scores |
| **Assuming SOTA = production ready** | Research ≠ production | Verify throughput, latency, cost, safety |
| **No regression tracking** | Silent performance death | Track metrics over time, alert on >5% drop |

---

## Statistical Significance Rules

### How Many Trials Do You Need?

- **Difference > 10%**: 3 trials sufficient
- **Difference 5-10%**: 5 trials recommended
- **Difference < 5%**: 10+ trials needed
- **Publishing results**: Always report confidence intervals

### P-Value Interpretation

| P-Value | Conclusion |
|---------|-----------|
| < 0.01 | Very strong evidence of improvement |
| < 0.05 | Strong evidence of improvement |
| < 0.10 | Weak evidence (not significant) |
| ≥ 0.10 | No statistically significant improvement |

---

## Cost Breakdown Example

### Claude Sonnet 4.5 on SWE-bench Lite

```
Input Price:   $3.00 per 1M tokens
Output Price:  $15.00 per 1M tokens

Typical Task:
  - Input tokens:  50,000 (problem + context)
  - Output tokens: 25,000 (solution)

  Cost per task: ($50 * 3 + $25 * 15) / 1,000 = $0.525

For 534 tasks (Lite):
  - Success rate: 75%
  - Total cost: 534 * $0.525 = $280
  - Cost per resolved: $280 / (534 * 0.75) = $0.70

If not resolved on first try (average 1.5 attempts):
  - Real cost per task: $0.79
```

### SWE-bench Verified (500 tasks, Claude Opus)

```
Similar to above but:
- Tokens slightly higher: 70K input, 35K output
- Success rate: 80.9%
- Cost per task: $0.82
- Total evaluation: 500 * $0.82 = $410
- Cost per resolved: $410 / (500 * 0.809) = $1.01
```

---

## Detecting Data Contamination

### Red Flags

1. **Perfect/near-perfect scores** (>95% on HumanEval)
2. **Large gaps between variants** (>15% drop on modified benchmarks)
3. **Model trained on benchmark period** (HumanEval in training data cutoff)
4. **Bigger drops on variants than expected**

### Verification Steps

1. Use template-based variants (HumanEval-T)
2. Compare to LiveCodeBench (updated, uncontaminated)
3. Test on held-out custom domain tasks
4. Check training data composition/cutoff dates

---

## Choosing Your Benchmark Strategy

### Use Case: Evaluating for Research Publication

```
Required:
✓ SWE-bench Verified (reference benchmark)
✓ HumanEval + (code generation)
✓ N ≥ 3 trials, confidence intervals
✓ Cross-validation on test set
✓ Comparison to published SOTA

Recommended:
+ Terminal-Bench (added difficulty)
+ LiveCodeBench (contamination check)
+ Custom domain benchmark
```

### Use Case: Production Deployment

```
Required:
✓ Your custom domain tasks (most realistic)
✓ Latency/throughput benchmarks
✓ Cost per task tracking
✓ Regression suite (prevent breakage)
✓ Error recovery testing

Nice to Have:
+ SWE-bench Lite (generic capability)
+ Aider (code editing quality)
+ Production monitoring (real performance)
```

### Use Case: Model Comparison

```
Use:
✓ Same benchmark on all models
✓ Fixed prompts/settings (no tuning)
✓ Same hardware/infrastructure
✓ Statistical significance testing
✓ Report mean ± std dev, 95% CI
✓ Document all parameters

Track:
+ Cost per successful task
+ Latency percentiles
+ Error patterns
+ Scaling behavior (more tokens → better?)
```

---

## Recommended Evaluation Schedule

### Initial Baseline (Week 1-2)

1. Run all 3 primary benchmarks (SWE-lite, HumanEval+, Terminal-Bench)
2. N=3 trials each
3. Establish baseline metrics
4. Calculate confidence intervals
5. Create monitoring dashboard

### Ongoing (Weekly)

- [ ] Run regression suite (5-10 custom tasks) every merge
- [ ] Monitor key metrics on dashboard
- [ ] Alert if >5% drop from baseline
- [ ] Log all errors for pattern analysis

### Monthly

- [ ] Full benchmark run (all 3 benchmarks, N=2)
- [ ] Compare to previous month
- [ ] Update cost model with actual data
- [ ] Analyze error patterns
- [ ] Plan improvements

### Quarterly

- [ ] Deep analysis of failure cases
- [ ] Benchmark against new SOTA models
- [ ] Evaluate new benchmarks (FeatBench, etc.)
- [ ] Update evaluation framework
- [ ] Publish learnings

---

## Key Resources

### Official Websites
- [SWE-bench](https://www.swebench.com/)
- [Terminal-Bench](https://www.tbench.ai/)
- [OpenHands](https://openhands.dev/)
- [Aider](https://aider.chat/)

### Leaderboards
- [SWE-bench Verified](https://llm-stats.com/benchmarks/swe-bench-verified)
- [SWE-bench Pro](https://scale.com/leaderboard/swe_bench_pro_public)
- [HumanEval](https://llm-stats.com/benchmarks/humaneval)

### Papers
- [SWE-bench: Can Language Models Resolve Real-world Github Issues?](https://arxiv.org/abs/2310.06799)
- [Terminal-Bench (2601.11868)](https://arxiv.org/html/2601.11868v1)
- [Token Consumption Analysis (1bUeVB3fov)](https://openreview.net/forum?id=1bUeVB3fov)

### Tools
- [EleutherAI LM Evaluation Harness](https://github.com/EleutherAI/lm-evaluation-harness)
- [OpenHands Evaluation Framework](https://docs.openhands.dev/openhands/usage/developers/evaluation-harness)

---

## Metrics Cheat Sheet

### Quick Calculation Examples

**Resolved Rate:**
```
(Tasks fully resolved) / (Total tasks) × 100
= 300 / 500 × 100 = 60%
```

**Cost Per Resolved Task:**
```
(Total API cost) / (Number of resolved tasks)
= $500 / (500 × 0.60) = $1.67
```

**Edit Accuracy:**
```
(Correct edits) / (Total edits) × 100
= 450 / 500 × 100 = 90%
```

**P95 Latency:**
```
Sort all latencies, take 95th percentile
[1s, 2s, 3s, ..., 300s] → take value at 0.95 × N position
```

**Error Recovery Rate:**
```
(Tasks initially failed but eventually resolved) / (Initially failed) × 100
= 150 / 200 × 100 = 75%
```

---

## When to Worry

### Red Flags (Take Action)

- ⚠️ **Resolved rate drops >5%** → Investigate regression
- ⚠️ **P95 latency >600 seconds** → Agent thrashing/planning issues
- ⚠️ **Cost per task >$10** → Token usage explosion
- ⚠️ **Regression test failures >5%** → Code quality issues
- ⚠️ **Edit accuracy <70%** → Precision problems

### Green Flags (On Track)

- ✅ Resolved rate stable or improving
- ✅ Cost per task trending down
- ✅ Error patterns decreasing
- ✅ Recovery rate >50%
- ✅ Edit accuracy >85%

---

## Last Updated

February 21, 2026 - Based on latest 2025-2026 research, Claude Opus 4.5 SOTA data, and frontier model benchmarks.

