# Harness: State-of-the-Art Agent Harness Research

> Comprehensive research for building an open-source, multi-provider coding agent CLI and SDK.

## Documents

| Document | Description |
|----------|-------------|
| [01-landscape.md](./01-landscape.md) | Market landscape: OpenClaw/pi-mono, Anthropic Agent SDK, competitors |
| [02-architecture.md](./02-architecture.md) | Deep architecture analysis of reference implementations |
| [03-harness-plan.md](./03-harness-plan.md) | Our CLI + SDK implementation plan |
| [04-evaluation.md](./04-evaluation.md) | Evaluation framework and benchmarking strategy |
| [05-evaluation-deep-dive.md](./05-evaluation-deep-dive.md) | Deep technical reference on benchmarks (25 pages) |
| [06-evaluation-quick-ref.md](./06-evaluation-quick-ref.md) | One-page cheat sheet: metrics, targets, commands |
| [07-sources.md](./07-sources.md) | Complete bibliography (97+ verified sources) |
| [08-eval-implementation.md](./08-eval-implementation.md) | Code examples & implementation guide for evaluation |

## Quick Summary

**Goal**: Build an open-source coding agent harness (CLI + SDK) that works with any LLM provider (Claude, Gemini, OpenAI, local models) while matching Claude Code's performance through superior harness design.

**Key Insight**: The agent harness contributes +36% performance over baseline (CORE benchmark: same Opus 4.5 scored 78% with Claude Code harness vs 42% with smolagents). **The harness is as important as the model.**

**Design Principles**: Performance-first, design simplicity, provider-agnostic, MCP-native, extensible via Skills.
