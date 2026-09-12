import asyncio
import json
from time import perf_counter

from midnight.hackathons.index import get_hackathon_data
from midnight.jobs.scraper.index import main as get_jobs_data


def main():
    # =========================================================
    # HACKATHONS AGGREGATOR
    # =========================================================
    start = perf_counter()
    hackathon_data = asyncio.run(get_hackathon_data())

    end = perf_counter()
    print("=" * 80)
    print(
        f"Found {len(hackathon_data):,} hackathons in {round(end - start, 1)} seconds"
    )
    print("=" * 80 + "\n")

    # =========================================================
    # JOB AGGREGATOR
    # =========================================================
    start = perf_counter()
    job_data = get_jobs_data()

    end = perf_counter()
    print("=" * 80)
    print(f"Found {len(job_data):,} jobs in {round(end - start, 1)} seconds")
    print("=" * 80 + "\n")

    print("=" * 80)
    print("Final Results")
    print("=" * 80 + "\n")

    print("=" * 80)
    print("HACKATHONS")
    print("=" * 80)
    print(json.dumps(hackathon_data, indent=4))

    print("=" * 80)
    print("JOBS")
    print("=" * 80)
    print(json.dumps(job_data, indent=4))


if __name__ == "__main__":
    _ = main()
