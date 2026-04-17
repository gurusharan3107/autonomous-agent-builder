---
title: "Knowledge Base Quality Gate"
tags: ["quality", "validation", "agent", "knowledge-base"]
doc_type: "documentation"
created: "2026-04-17"
---

# Knowledge Base Quality Gate

## Overview

The knowledge base quality gate validates automatically generated documentation using **Claude Agent SDK** for intelligent, dynamic evaluation. Unlike hardcoded rules, the agent provides contextual feedback and adapts to different project types.

## Why Agent-Based?

### Traditional Rule-Based Approach ❌
- Hardcoded thresholds (e.g., "min 500 chars")
- Inflexible rules that don't adapt to context
- Can't understand semantic quality
- Misses nuanced issues
- Requires constant rule updates

### Agent-Based Approach ✅
- **Dynamic evaluation** based on content understanding
- **Contextual feedback** specific to your project
- **Semantic analysis** of documentation quality
- **Actionable recommendations** for improvement
- **Adapts automatically** to different project types

## Evaluation Criteria

The agent evaluates knowledge bases across 6 dimensions:

### 1. Completeness (25% weight)
- Are all expected document types present?
- Is critical information missing?
- Are there gaps in coverage?

**Expected Documents**:
- project-overview
- technology-stack
- dependencies
- system-architecture
- code-structure
- database-models
- api-endpoints
- business-overview
- workflows-and-orchestration
- configuration
- agent-system

### 2. Content Quality (25% weight)
- Is there sufficient detail in each document?
- Are sections well-populated (not empty or stub)?
- Is the information accurate and specific (not generic)?
- Are code examples, diagrams, or data included where appropriate?

### 3. Usefulness (20% weight)
- Would this documentation help an AI agent understand the codebase?
- Would this help a new developer onboard?
- Are the right level of abstraction and detail provided?
- Is the information actionable?

### 4. Structure & Clarity (15% weight)
- Is the documentation well-organized?
- Are headers and sections logical?
- Is the markdown properly formatted?
- Is the writing clear and concise?

### 5. Accuracy (10% weight)
- Does the information appear correct based on the content?
- Are there obvious errors or inconsistencies?
- Do technical details make sense?

### 6. Searchability (5% weight)
- Are documents properly tagged?
- Are key terms and concepts highlighted?
- Would someone be able to find information easily?

## Usage

### Run Quality Gate After Extraction

```bash
# Extract knowledge and validate (default)
builder kb extract

# Extract without validation
builder kb extract --no-validate
```

### Run Quality Gate Standalone

```bash
# Run agent-based quality gate
builder kb validate

# Run with verbose output
builder kb validate --verbose

# Use different Claude model
builder kb validate --model claude-opus-4-20250514

# Use rule-based validation (fallback)
builder kb validate --no-use-agent
```

### JSON Output

```bash
# Get structured JSON output
builder kb validate --json
```

## Output Format

### Console Output

```
🔍 Running agent-based quality gate on .agent-builder/knowledge/reverse-engineering...

✅ Quality Gate: PASSED (score: 87/100)

📊 Criteria Scores:
  ✅ Completeness: 95/100
  ✅ Content Quality: 88/100
  ✅ Usefulness: 85/100
  ✅ Structure Clarity: 90/100
  ✅ Accuracy: 82/100
  ⚠️  Searchability: 65/100

💪 Strengths:
  • All expected documents are present
  • Database models are comprehensive with ER diagrams
  • API endpoints are well-documented
  • Clear architecture diagrams

⚠️  Weaknesses:
  • Project overview is too brief
  • Some sections lack code examples
  • Tags could be more specific

💡 Recommendations:
  • Expand project overview with more context
  • Add code examples to configuration docs
  • Improve tagging for better searchability
  • Add cross-references between related docs
```

### JSON Output

```json
{
  "passed": true,
  "score": 0.87,
  "summary": "Quality Gate: PASSED (score: 87/100)",
  "evaluation": {
    "criteria_scores": {
      "completeness": 95,
      "content_quality": 88,
      "usefulness": 85,
      "structure_clarity": 90,
      "accuracy": 82,
      "searchability": 65
    },
    "strengths": [
      "All expected documents are present",
      "Database models are comprehensive with ER diagrams"
    ],
    "weaknesses": [
      "Project overview is too brief",
      "Some sections lack code examples"
    ]
  },
  "recommendations": [
    "Expand project overview with more context",
    "Add code examples to configuration docs"
  ],
  "agent_reasoning": "The knowledge base is comprehensive and well-structured..."
}
```

## Passing Criteria

**Quality Gate PASSES if**:
- Overall score ≥ 75/100
- No critical failures (completeness, accuracy)

**Quality Gate FAILS if**:
- Overall score < 75/100
- Missing critical documents
- Severe accuracy issues

## Integration with CI/CD

### GitHub Actions

```yaml
name: Knowledge Base Quality

on:
  push:
    paths:
      - 'src/**'
      - 'docs/**'

jobs:
  validate-kb:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: pip install -e .
      
      - name: Extract knowledge base
        run: builder kb extract --force
      
      - name: Validate quality
        run: builder kb validate --json > kb-quality.json
      
      - name: Upload results
        uses: actions/upload-artifact@v3
        with:
          name: kb-quality-report
          path: kb-quality.json
```

### Pre-commit Hook

```bash
#!/bin/bash
# .git/hooks/pre-commit

# Extract and validate knowledge base
builder kb extract --force --no-validate

# Run quality gate
if ! builder kb validate; then
    echo "❌ Knowledge base quality gate failed"
    echo "Fix issues or use --no-verify to skip"
    exit 1
fi

echo "✅ Knowledge base quality gate passed"
```

## Customization

### Use Different Model

```bash
# Use Opus for more thorough evaluation
builder kb validate --model claude-opus-4-20250514

# Use Haiku for faster evaluation
builder kb validate --model claude-haiku-4-20250514
```

### Adjust Passing Threshold

Edit `agent_quality_gate.py`:

```python
# Change passing threshold (default: 75)
PASSING_THRESHOLD = 80  # More strict
PASSING_THRESHOLD = 70  # More lenient
```

### Custom Evaluation Criteria

Modify the `EVALUATION_PROMPT` in `agent_quality_gate.py` to add custom criteria:

```python
EVALUATION_PROMPT = """
...existing criteria...

### 7. Custom Criterion (10%)
- Your custom evaluation logic
- Specific to your project needs
"""
```

## Comparison: Agent vs Rule-Based

| Feature | Agent-Based | Rule-Based |
|---------|-------------|------------|
| **Flexibility** | ✅ Adapts to context | ❌ Fixed rules |
| **Semantic Understanding** | ✅ Understands meaning | ❌ Pattern matching only |
| **Feedback Quality** | ✅ Actionable, specific | ⚠️ Generic |
| **Maintenance** | ✅ Self-updating | ❌ Requires manual updates |
| **Speed** | ⚠️ Slower (API call) | ✅ Fast (local) |
| **Cost** | ⚠️ API costs | ✅ Free |
| **Offline** | ❌ Requires API | ✅ Works offline |

**Recommendation**: Use agent-based by default. Fall back to rule-based for:
- Offline environments
- CI/CD with strict time limits
- Cost-sensitive scenarios

## Troubleshooting

### Quality Gate Fails

1. **Check specific criteria scores** - Focus on lowest scores
2. **Review recommendations** - Agent provides actionable fixes
3. **Re-extract with --force** - Ensure latest code is analyzed
4. **Check verbose output** - `--verbose` shows detailed reasoning

### Agent Errors

```bash
# Fall back to rule-based validation
builder kb validate --no-use-agent

# Check API connectivity
curl https://api.anthropic.com/v1/messages

# Verify API key
echo $ANTHROPIC_API_KEY
```

### Slow Evaluation

```bash
# Use faster model
builder kb validate --model claude-haiku-4-20250514

# Skip validation during extraction
builder kb extract --no-validate
```

## Best Practices

1. **Run after every extraction** - Catch issues early
2. **Review recommendations** - Agent provides specific guidance
3. **Track scores over time** - Monitor quality trends
4. **Integrate with CI/CD** - Automate quality checks
5. **Use verbose mode for debugging** - Understand agent reasoning
6. **Re-extract when code changes** - Keep docs fresh

## Future Enhancements

- **Historical tracking** - Track quality scores over time
- **Custom criteria** - Project-specific evaluation rules
- **Multi-agent evaluation** - Multiple agents for consensus
- **Auto-fix mode** - Agent suggests and applies fixes
- **Comparative analysis** - Compare against similar projects
