# Final full-dataset usage report

Run command:

```text
python3 code/main.py
```

Run scope: all 250 rows in `dataset/requests.csv`.

This solution is fully deterministic Python. It does not call an LLM, hosted model, external API, live exchange-rate service, or banking service.

| Provider | Model/name | Calls | Input tokens | Output tokens | Estimated cost |
|---|---|---:|---:|---:|---:|
| none | deterministic Python financial decision pipeline | 0 | 0 | 0 | $0.00 |
| **Total** | — | **0** | **0** | **0** | **$0.00** |

Average per request:

- Model calls: `0`
- Input tokens: `0`
- Output tokens: `0`
- Estimated cost: `$0.00`

The pipeline performs deterministic CSV loading, evidence resolution, currency conversion using supplied fixed rates, timeline forecasting, simulator validation, candidate generation, hard filtering, personalized ranking, structured explanation generation, and strict output validation. No model-provider usage or token cost is incurred.
