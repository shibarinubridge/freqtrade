User-supplied autonomous research

Sources are registered by SHA256; duplicates do not create new analysis jobs.
research_loop.py provides durable leases, timestamped analysis validation and
append-only experiment memory. RESEARCH-WORKER.md is the scheduled agent contract.

The executor is an hourly scheduled ChatGPT agent with inherited conversation
environment selection, not a local LLM daemon. Local Codex CLI cannot initialize
on this read-only configuration home. A successful scheduled run still requires
workspace access and available model quota; scheduling alone proves neither
completed analysis nor persistent service availability. Status must be explicit.

Learning means retaining rules, assumptions, failed hypotheses, results and
parent-child experiments. It does not train model weights. Optimizing on consumed
validation data is rejected; at most three experiments per source lineage.
Automatic active-strategy rewriting and deployment are not implemented.
Only a separately staged, tested dry-run candidate may progress to deployment.
No real-money trading is part of this research worker.
