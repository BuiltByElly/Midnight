"""Minimal tests for the core job-scraping logic.

All tests are hermetic: no network, no real data files. HTTP and the
geolocation tables are stubbed; filesystem access is limited to
temporary directories. Run with::

    python -m unittest discover -s tests -v
"""

import json
import os
import tempfile
import unittest
from unittest import mock

from midnight.jobs.scraper import config
from midnight.jobs.scraper.classify import (
    clean_job_data,
    is_recruiter_company,
    job_tier_classification,
    parse_workday_posted_on,
    paylocity_location,
)
from midnight.jobs.scraper.companies import load_companies, load_paylocity
from midnight.jobs.scraper.dead_slugs import load_dead_slugs, save_dead_slugs
from midnight.jobs.scraper.models import get_job_metadata


class TestTiers(unittest.TestCase):
    def test_intern(self):
        self.assertEqual(job_tier_classification("Software Engineer Intern"), "intern")

    def test_entry(self):
        self.assertEqual(job_tier_classification("Junior Developer"), "entry")

    def test_mid(self):
        self.assertEqual(job_tier_classification("Software Engineer"), "mid")

    def test_senior(self):
        self.assertEqual(job_tier_classification("Senior Engineer"), "senior")


class TestRecruiter(unittest.TestCase):
    def test_recruiter_slug(self):
        self.assertTrue(is_recruiter_company("acme-recruiting"))

    def test_regular_slug(self):
        self.assertFalse(is_recruiter_company("acme"))


class TestCleanJobs(unittest.TestCase):
    def test_drops_invalid_keeps_valid(self):
        jobs = [
            {"title": "", "url": "http://x", "company": "c"},  # no title
            {"title": "Eng", "url": None, "company": "c"},  # no url
            {"title": "Eng", "url": "http://x", "company": None},  # no company
            {"title": "Eng", "url": "http://x", "company": "c"},  # valid
        ]
        self.assertEqual(len(clean_job_data(jobs)), 1)


class TestWorkdayDates(unittest.TestCase):
    def test_today(self):
        from datetime import UTC, datetime

        self.assertEqual(
            parse_workday_posted_on("Posted Today"),
            datetime.now(UTC).date().isoformat(),
        )

    def test_unparsable(self):
        self.assertIsNone(parse_workday_posted_on("nonsense"))
        self.assertIsNone(parse_workday_posted_on(None))


class TestPaylocityLocation(unittest.TestCase):
    def test_city_state(self):
        job = {"JobLocation": {"City": "Chicago", "State": "IL"}}
        self.assertEqual(paylocity_location(job), "Chicago, IL")

    def test_fallbacks(self):
        self.assertEqual(paylocity_location({"LocationName": "Main"}), "Main")
        self.assertEqual(paylocity_location({}), "Not specified")


class TestMetadata(unittest.TestCase):
    def test_source_label(self):
        old = config.SOURCE_TYPE
        try:
            config.set_source_type("manual")
            meta = get_job_metadata()
            self.assertEqual(meta["source"], "manual")
            self.assertTrue(meta["scraped_at"].endswith("Z"))
        finally:
            config.set_source_type(old)


class TestCompanies(unittest.TestCase):
    def test_load_companies(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "c.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(["a", "b", "a"], f)
            self.assertEqual(load_companies(path), {"a", "b"})

    def test_load_companies_missing(self):
        self.assertEqual(load_companies("/nonexistent/x.json"), set())

    def test_load_paylocity(self):
        from midnight.jobs.scraper import companies

        old = dict(companies.PAYLOCITY_NAMES)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, "p.json")
                rows = [
                    {"guid": "g1", "name": "Acme"},
                    {"guid": "", "name": "Skip"},
                    {"guid": "g2", "name": None},
                ]
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(rows, f)
                self.assertEqual(load_paylocity(path), {"g1", "g2"})
                self.assertEqual(companies.PAYLOCITY_NAMES["g1"], "Acme")
        finally:
            companies.PAYLOCITY_NAMES.clear()
            companies.PAYLOCITY_NAMES.update(old)


class TestDeadSlugs(unittest.TestCase):
    def test_roundtrip_and_missing(self):
        import midnight.jobs.scraper.dead_slugs as ds

        self.assertEqual(load_dead_slugs("definitely-not-a-platform"), set())
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(ds, "DEAD_SLUG_DIR", tmp),
        ):
            save_dead_slugs("fake", {"a", "b"})
            self.assertEqual(load_dead_slugs("fake"), {"a", "b"})


class TestEnrichLocation(unittest.TestCase):
    def test_remote_and_unknown(self):
        from midnight.jobs.scraper import geo

        maps = {
            "city_admin_country": {},
            "city_country": {"springfield|US": [1.0, 2.0]},
            "city_admin": {},
            "city": {},
        }
        with mock.patch.object(geo, "get_location_maps", return_value=maps):
            self.assertEqual(geo.enrich_location("Remote - US"), (True, None))
            self.assertEqual(
                geo.enrich_location("Springfield, US"), (False, [1.0, 2.0])
            )
            self.assertEqual(geo.enrich_location("Not specified"), (False, None))


class TestGreenhouseFetcher(unittest.TestCase):
    def test_normalizes_jobs(self):
        import midnight.jobs.scraper.fetchers.greenhouse as gh

        payload = {
            "jobs": [
                {
                    "title": "Software Engineer",
                    "location": {"name": "Springfield, US"},
                    "absolute_url": "http://jobs/1",
                    "departments": [{"name": "Eng"}],
                    "id": 1,
                    "updated_at": "2026-01-01",
                }
            ]
        }
        resp = mock.Mock(status_code=200)
        resp.json.return_value = payload
        with (
            mock.patch("requests.get", return_value=resp),
            mock.patch.object(gh, "enrich_location", return_value=(False, [1.0, 2.0])),
        ):
            _slug, jobs, status = gh.fetch_company_jobs_greenhouse("acme")
        self.assertEqual(status, 200)
        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertEqual(
            (job["company"], job["ats"], job["skill_level"], job["coords"]),
            ("acme", "Greenhouse", "mid", [1.0, 2.0]),
        )

    def test_non_200(self):
        import midnight.jobs.scraper.fetchers.greenhouse as gh

        resp = mock.Mock(status_code=404)
        with mock.patch("requests.get", return_value=resp):
            self.assertEqual(
                gh.fetch_company_jobs_greenhouse("nope"), ("nope", [], 404)
            )


class TestWorkdayFetcher(unittest.TestCase):
    def test_malformed_slug_no_http(self):
        from midnight.jobs.scraper.fetchers.workday import fetch_company_jobs_workday

        with mock.patch("requests.post") as post:
            result = fetch_company_jobs_workday("not-a-triple")
            post.assert_not_called()
        self.assertEqual(result, ("not-a-triple", [], None))


class TestRunner(unittest.TestCase):
    def test_fans_out_and_caches_dead(self):
        import midnight.jobs.scraper.dead_slugs as ds
        from midnight.jobs.scraper.runner import fetch_all_jobs

        def stub(slug):
            if slug == "dead":
                return slug, [], 404
            return slug, [{"title": "E", "url": "http://x", "company": slug}], 200

        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(ds, "DEAD_SLUG_DIR", tmp),
        ):
            active, jobs = fetch_all_jobs({"dead", "live"}, stub, platform="t")
            self.assertEqual(active, {"live": 1})
            self.assertEqual(len(jobs), 1)
            self.assertEqual(load_dead_slugs("t"), {"dead"})


class TestResults(unittest.TestCase):
    def test_writes_output_files(self):
        import midnight.jobs.scraper.results as res

        with tempfile.TemporaryDirectory() as tmp:
            chunks = os.path.join(tmp, "chunks")
            with (
                mock.patch.object(res, "OUTPUT_DIR", tmp),
                mock.patch.object(res, "CHUNKS_DIR", chunks),
                mock.patch.object(res, "ensure_dirs", lambda: None),
            ):
                res.save_results(
                    {"a", "b"},
                    {"a": 2},
                    [
                        {"title": "Eng", "url": "http://x", "company": "a"},
                        {"title": "", "url": "http://x", "company": "a"},
                    ],
                )
            for name in (
                "all_companies.json",
                "active_companies.json",
                "all_jobs.json",
                "metadata.json",
            ):
                self.assertTrue(os.path.exists(os.path.join(tmp, name)), name)
            with open(os.path.join(tmp, "metadata.json"), encoding="utf-8") as f:
                meta = json.load(f)
            self.assertEqual((meta["total_jobs"], meta["total_companies"]), (1, 2))


if __name__ == "__main__":
    unittest.main()
