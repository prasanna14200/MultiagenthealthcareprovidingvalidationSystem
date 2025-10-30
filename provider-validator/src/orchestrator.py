# src/orchestrator.py
import asyncio
import csv
import json
import pandas as pd

from src.db import init_db,insert_provider
from src.agents.validation_agent import ValidationAgent
from src.agents.qa_agent import QAAgent
from src.agents.enrichment_agent import EnrichmentAgent
from src.agents.reconciliation_agent import ReconciliationAgent
from src.agents.outreach_agent import OutreachAgent
from src.utils import fuzzy_ratio


async def run_batch(csv_path, concurrency=8, limit=None):
    """Main orchestrator: runs all agents on CSV provider data concurrently."""

    # ✅ Step 1: Initialize DB
    init_db()

    # ✅ Step 2: Load CSV data
    rows = []
    with open(csv_path, newline='') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            row['id'] = int(row.get('id', i + 1))
            rows.append(row)

    if limit:
        rows = rows[:limit]

    # ✅ Step 3: Initialize all agents
    val_agent = ValidationAgent(name="validation_agent")
    qa_agent = QAAgent(name="qa_agent")
    enrich_agent = EnrichmentAgent(name="enrichment_agent")
    recon_agent = ReconciliationAgent(name="reconciliation_agent")
    outreach_agent = OutreachAgent(name="outreach_agent")

    # ✅ Concurrency setup
    sem = asyncio.Semaphore(concurrency)
    results = []

    # ✅ Step 4: Define per-row pipeline
    async def process(row):
        async with sem:
            try:
                # --- Phase 1: Validation ---
                val_res = await val_agent.run(row)

                # --- Phase 2: Quality Assessment ---
                qa_res = await qa_agent.run({**row, "validation_result": val_res})

                # --- Phase 3: Enrichment ---
                enrich_res = await enrich_agent.run(row)

                # --- Phase 4: Reconciliation ---
                combined_res = {
                    **row,
                    "validation_result": val_res,
                    "qa": qa_res,
                    "enrichment": enrich_res,
                }
                recon_res = await recon_agent.run(combined_res)

                # --- Phase 5: Outreach ---
                outreach_res = await outreach_agent.run(recon_res)

                # --- Step 6: Prepare DB entry ---
                profile = recon_res.get("profile", {})
                insert_row = {
                    "source_id": row.get("id"),
                    "name": profile.get("name", {}).get("value", row.get("name")),
                    "npi": row.get("npi"),
                    "phone": row.get("phone"),
                    "address": row.get("address"),
                    "website": row.get("website"),
                    "specialty": row.get("specialty"),
                    "source_json": json.dumps({
                        "validation": val_res,
                        "qa": qa_res,
                        "enrichment": enrich_res,
                        "reconciliation": recon_res,
                        "outreach": outreach_res
                    }),
                    "confidence": profile.get("final_confidence", 0.0),
                    "flags": json.dumps(profile.get("flags", [])),
                    "status": "manual_review" if profile.get("flags") else "confirmed"
                }

                # --- Step 7: Insert into DB ---
                insert_provider(insert_row)

                # --- Step 8: Collect results for CSV ---
                results.append({**row, **profile})
                print(
                    f"[INFO] Processed id={row.get('id')} "
                    f"conf={profile.get('final_confidence', 0.0):.3f} "
                    f"flags={profile.get('flags', [])}"
                )

            except Exception as e:
                print(f"[ERROR] Failed processing row id={row.get('id')}: {e}")

    # ✅ Step 9: Run all tasks concurrently
    await asyncio.gather(*[process(r) for r in rows])

    # ✅ Step 10: Export final results to CSV
    pd.DataFrame(results).to_csv("data/validated_providers.csv", index=False)
    print("[INFO] ✅ Results written to data/validated_providers.csv")


# ✅ Entry point
if __name__ == "__main__":
    import sys

    csv_path = sys.argv[1] if len(sys.argv) > 1 else "data/providers_sample.csv"
    concurrency = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else None

    asyncio.run(run_batch(csv_path, concurrency=concurrency, limit=limit))
