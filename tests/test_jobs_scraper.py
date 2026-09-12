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
    def test_scraped_at_timestamp(self):
        meta = get_job_metadata()
        self.assertEqual(list(meta), ["scraped_at"])
        self.assertTrue(meta["scraped_at"].endswith("Z"))


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
            mock.patch("time.sleep"),
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
        with (
            mock.patch("requests.get", return_value=resp),
            mock.patch("time.sleep"),
        ):
            self.assertEqual(
                gh.fetch_company_jobs_greenhouse("nope"), ("nope", [], 404)
            )

    def test_retries_then_succeeds(self):
        import midnight.jobs.scraper.fetchers.greenhouse as gh

        bad = mock.Mock(status_code=429, headers={})
        good = mock.Mock(status_code=200)
        good.json.return_value = {"jobs": []}
        with (
            mock.patch("requests.get", side_effect=[bad, good]) as get,
            mock.patch("time.sleep"),
        ):
            self.assertEqual(
                gh.fetch_company_jobs_greenhouse("acme"), ("acme", [], 200)
            )
        self.assertEqual(get.call_count, 2)

    def test_retry_after_honored(self):
        import midnight.jobs.scraper.fetchers.greenhouse as gh

        bad = mock.Mock(status_code=503, headers={"Retry-After": "7"})
        good = mock.Mock(status_code=200)
        good.json.return_value = {"jobs": []}
        with (
            mock.patch("requests.get", side_effect=[bad, good]),
            mock.patch("time.sleep") as sleep,
        ):
            gh.fetch_company_jobs_greenhouse("acme")
        sleep.assert_any_call(7.0)


class TestLeverFetcher(unittest.TestCase):
    def test_retries_then_succeeds(self):
        import midnight.jobs.scraper.fetchers.lever as lv

        bad = mock.Mock(status_code=429, headers={})
        good = mock.Mock(status_code=200)
        good.json.return_value = []
        with (
            mock.patch("requests.get", side_effect=[bad, good]) as get,
            mock.patch("time.sleep"),
        ):
            self.assertEqual(lv.fetch_company_jobs_lever("acme"), ("acme", [], 200))
        self.assertEqual(get.call_count, 2)


class TestRetryHelpers(unittest.TestCase):
    def test_is_retryable_status(self):
        from midnight.jobs.scraper.http import is_retryable_status

        self.assertTrue(is_retryable_status(429))
        self.assertTrue(is_retryable_status(503))
        self.assertFalse(is_retryable_status(404))
        self.assertFalse(is_retryable_status(200))
        self.assertFalse(is_retryable_status(None))

    def test_compute_backoff_bounds(self):
        from midnight.jobs.scraper.http import compute_backoff

        with mock.patch("random.uniform", return_value=1.0):
            self.assertEqual(compute_backoff(0), 2.0)
            self.assertEqual(compute_backoff(2), 5.0)

    def test_parse_retry_after_seconds(self):
        from midnight.jobs.scraper.http import parse_retry_after

        self.assertEqual(
            parse_retry_after(mock.Mock(headers={"Retry-After": "5"})), 5.0
        )
        # Clamped to the ceiling
        self.assertEqual(
            parse_retry_after(mock.Mock(headers={"Retry-After": "3600"})), 60.0
        )

    def test_parse_retry_after_missing_or_invalid(self):
        from midnight.jobs.scraper.http import parse_retry_after

        self.assertIsNone(parse_retry_after(mock.Mock(headers={})))
        self.assertIsNone(parse_retry_after(mock.Mock(headers={"Retry-After": "soon"})))

    def test_parse_retry_after_http_date(self):
        from datetime import UTC, datetime, timedelta

        from midnight.jobs.scraper.http import parse_retry_after

        now = datetime.now(UTC)
        future = (now + timedelta(seconds=30)).strftime("%a, %d %b %Y %H:%M:%S GMT")
        delay = parse_retry_after(mock.Mock(headers={"Retry-After": future}), now=now)
        self.assertIsNotNone(delay)
        self.assertGreater(delay, 0)
        self.assertLessEqual(delay, 30.0)

    def test_retry_delay_prefers_header(self):
        from midnight.jobs.scraper.http import retry_delay

        resp = mock.Mock(headers={"Retry-After": "4"})
        self.assertEqual(retry_delay(resp, 0), 4.0)
        fallback = retry_delay(mock.Mock(headers={}), 0)
        self.assertGreaterEqual(fallback, 1.5)


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


def _fixture_profile():
    from midnight.profile import (
        Profile,
        ProfileLocation,
        ProfileSchedule,
        ProfileUser,
    )

    return Profile(
        user=ProfileUser(
            name="T",
            email="t@x",
            years_of_experience=3,
            location=ProfileLocation(
                city="Benin", state="Edo", country="Nigeria", remote=True
            ),
            tech_stack=["Python", "React"],
            interests=["AI/ML"],
        ),
        opportunities=["jobs"],
        schedule=ProfileSchedule(send_time="00:00", timezone="Africa/Lagos"),
    )


def _job(title, url, company="acme", **overrides):
    base = {"title": title, "url": url, "company": company}
    base.update(overrides)
    return base


class TestJobPost(unittest.TestCase):
    def test_normalization_fallbacks(self):
        from midnight.jobs.scraper.models import JobPost, normalize_jobs

        post = JobPost(absolute_url="http://x/1", company_slug="acme")
        self.assertEqual((post.url, post.company), ("http://x/1", "acme"))
        self.assertEqual(JobPost(skill_level="wizard").skill_level, "entry")
        # extras are preserved, non-dicts skipped
        posts = normalize_jobs(
            [{"title": "E", "url": "http://x", "ats": "Greenhouse"}, "nope"]
        )
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].ats, "Greenhouse")


class TestRankJobs(unittest.TestCase):
    def _rank(self, jobs, seen):
        import midnight.jobs.scraper.results as res

        saved = {}

        def fake_save(key, urls):
            saved[key] = list(urls)

        with (
            mock.patch.object(res, "load_profile", return_value=_fixture_profile()),
            mock.patch.object(res, "load_seen", return_value=list(seen)),
            mock.patch.object(res, "save_seen", side_effect=fake_save),
        ):
            top = res._rank_jobs_from_profile(jobs)
        return top, saved

    def test_picks_best_seven_skips_seen(self):
        jobs = [
            _job(
                "Senior Python Engineer",
                "http://u/j1",
                company="zeta",
                remote=True,
                skill_level="senior",
            ),
            _job(
                "Python Developer",
                "http://u/j2",
                location="Lagos, Nigeria",
                skill_level="entry",
            ),
            _job("React Frontend", "http://u/j3", remote=True, skill_level="mid"),
            _job("Accountant", "http://u/j4", location="Benin, Edo", skill_level="mid"),
            _job(
                "Python Engineer",
                "http://u/j5",
                company="talent-agency",
                remote=True,
                skill_level="mid",
            ),
            _job(
                "ML Engineer",
                "http://u/j6",
                company="acme",
                remote=True,
                skill_level="mid",
            ),
            _job(
                "Java Developer", "http://u/j7", location="Berlin", skill_level="senior"
            ),
            _job("Python Intern", "http://u/j8", remote=True, skill_level="intern"),
            _job(
                "Go Developer", "http://u/j9", location="Berlin", skill_level="senior"
            ),
            _job("Python Guru", "http://seen", remote=True, skill_level="mid"),
        ]
        top, saved = self._rank(jobs, ["http://seen"])
        urls = [job["url"] for job in top]
        self.assertEqual(
            urls,
            [
                "http://u/j2",  # 8: stack + developer-alias + country + entry
                "http://u/j8",  # 7: stack + remote + intern
                "http://u/j3",  # 6: stack + remote + mid
                "http://u/j6",  # 5: ml/engineer aliases + remote + mid
                "http://u/j5",  # 5, tiebreak before zeta
                "http://u/j1",  # 5
                "http://u/j4",  # 3: location + mid only
            ],
        )
        # same dict shape as normalized input
        self.assertTrue(all(isinstance(job, dict) for job in top))
        self.assertIn("skill_level", top[0])
        # seen-bound urls recorded after the pre-existing ones
        self.assertEqual(saved["jobs"][0], "http://seen")
        self.assertEqual(len(saved["jobs"]), 8)

    def test_fewer_than_seven(self):
        top, _ = self._rank([_job("Python Dev", "http://u/1", remote=True)], [])
        self.assertEqual([job["url"] for job in top], ["http://u/1"])

    def test_description_breaks_title_tie(self):
        jobs = [
            _job("Engineer", "http://u/a", remote=True, skill_level="mid"),
            _job(
                "Engineer",
                "http://u/b",
                remote=True,
                skill_level="mid",
                description="We use Python and React daily",
            ),
        ]
        top, _ = self._rank(jobs, [])
        self.assertEqual([job["url"] for job in top], ["http://u/b", "http://u/a"])
        self.assertIn("Python", top[0]["description"])


class TestSaveResults(unittest.TestCase):
    def test_returns_ranked_and_appends_manifest(self):
        import midnight.jobs.scraper.results as res
        from midnight.jobs.scraper import config

        jobs = [
            _job("Python Dev", f"http://u/{i}", remote=True, skill_level="mid")
            for i in range(3)
        ]
        jobs.append({"title": "", "url": "http://u/bad", "company": "a"})
        with tempfile.TemporaryDirectory() as tmp:
            log = os.path.join(tmp, "manifest.log")
            with (
                mock.patch.object(res, "load_profile", return_value=_fixture_profile()),
                mock.patch.object(res, "load_seen", return_value=[]),
                mock.patch.object(res, "save_seen"),
                mock.patch.object(config, "MANIFEST_LOG", log),
            ):
                top = res.save_results(jobs)
                res.save_results(jobs)
            self.assertEqual(len(top), 3)
            self.assertTrue(all(isinstance(job, dict) for job in top))
            with open(log, encoding="utf-8") as f:
                lines = f.read().strip().split("\n")
            self.assertEqual(len(lines), 2)  # append-only: one line per run
            entry = json.loads(lines[0])
            self.assertEqual(
                (entry["total_jobs"], entry["selected"], len(entry["urls"])),
                (3, 3, 3),
            )
            # no JSON output files written
            self.assertEqual(
                [name for name in os.listdir(tmp) if name.endswith(".json")], []
            )


class TestCleanDescription(unittest.TestCase):
    def test_strips_html_and_whitespace(self):
        from midnight.jobs.scraper.models import clean_description

        self.assertEqual(
            clean_description("<p>Hello  <b>World</b></p>\n\nBye"),
            "Hello World Bye",
        )

    def test_truncates(self):
        from midnight.jobs.scraper.models import (
            DESCRIPTION_MAX_LEN,
            clean_description,
        )

        self.assertEqual(len(clean_description("x" * 9000)), DESCRIPTION_MAX_LEN)

    def test_blank_inputs(self):
        from midnight.jobs.scraper.models import clean_description

        self.assertIsNone(clean_description(None))
        self.assertIsNone(clean_description("   "))
        self.assertIsNone(clean_description(123))

    def test_jobpost_cleans_description(self):
        from midnight.jobs.scraper.models import JobPost

        post = JobPost(description="<p>Python role</p>")
        self.assertEqual(post.description, "Python role")


class TestAshbyPostingApi(unittest.TestCase):
    def _posting(self, **overrides):
        base = {
            "id": "abc",
            "title": "Python Engineer",
            "location": "Remote",
            "descriptionPlain": "We use Python daily. " * 10,
            "isRemote": True,
            "workplaceType": "Remote",
            "publishedAt": "2026-01-01T00:00:00.000+00:00",
            "jobUrl": "https://jobs.ashbyhq.com/acme/abc",
        }
        base.update(overrides)
        return base

    def test_posting_api_used(self):
        import midnight.jobs.scraper.fetchers.ashby as ab

        resp = mock.Mock(status_code=200)
        resp.json.return_value = {"jobs": [self._posting()]}
        with (
            mock.patch("requests.get", return_value=resp),
            mock.patch("requests.post") as post,
            mock.patch("time.sleep"),
        ):
            slug, jobs, status = ab.fetch_company_jobs_ashby("acme")
        self.assertEqual((slug, status), ("acme", 200))
        post.assert_not_called()
        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertTrue(job["remote"])
        self.assertIn("Python", job["description"])
        self.assertNotIn("<", job["description"])
        self.assertEqual(job["updated_at"], "2026-01-01T00:00:00.000+00:00")

    def test_graphql_fallback_on_404(self):
        import midnight.jobs.scraper.fetchers.ashby as ab

        posting_404 = mock.Mock(status_code=404)
        gql = mock.Mock(status_code=200)
        gql.json.return_value = {
            "data": {
                "jobBoard": {
                    "jobPostings": [{"id": "1", "title": "Dev", "locationName": "NYC"}]
                }
            }
        }
        with (
            mock.patch("requests.get", return_value=posting_404),
            mock.patch("requests.post", return_value=gql) as post,
            mock.patch("time.sleep"),
        ):
            slug, jobs, status = ab.fetch_company_jobs_ashby("acme")
        # legacy GraphQL loop re-posts per attempt (max_retries + 1)
        self.assertEqual(post.call_count, 3)
        self.assertEqual((slug, status, len(jobs)), ("acme", 200, 1))
        self.assertNotIn("description", jobs[0])


class TestGreenhouseContent(unittest.TestCase):
    def test_content_param_and_description(self):
        import midnight.jobs.scraper.fetchers.greenhouse as gh

        payload = {
            "jobs": [
                {
                    "title": "Engineer",
                    "location": {"name": "Remote"},
                    "absolute_url": "http://jobs/1",
                    "departments": [],
                    "id": 1,
                    "updated_at": "2026-01-01",
                    "content": "<p>Python role</p>",
                }
            ]
        }
        resp = mock.Mock(status_code=200)
        resp.json.return_value = payload
        with (
            mock.patch("requests.get", return_value=resp) as get,
            mock.patch.object(gh, "enrich_location", return_value=(True, None)),
            mock.patch("time.sleep"),
        ):
            _slug, jobs, status = gh.fetch_company_jobs_greenhouse("acme")
        self.assertIn("content=true", get.call_args[0][0])
        self.assertEqual(status, 200)
        self.assertEqual(jobs[0]["description"], "<p>Python role</p>")


class TestLeverDescription(unittest.TestCase):
    def test_description_plain_stored(self):
        import midnight.jobs.scraper.fetchers.lever as lv

        payload = [
            {
                "text": "Engineer",
                "categories": {"location": "Remote"},
                "hostedUrl": "http://jobs/1",
                "descriptionPlain": "Python role. " * 20,
            }
        ]
        resp = mock.Mock(status_code=200)
        resp.json.return_value = payload
        with (
            mock.patch("requests.get", return_value=resp),
            mock.patch.object(lv, "enrich_location", return_value=(True, None)),
            mock.patch("time.sleep"),
        ):
            _slug, jobs, status = lv.fetch_company_jobs_lever("acme")
        self.assertEqual(status, 200)
        self.assertIn("Python role", jobs[0]["description"])


class TestDetails(unittest.TestCase):
    def test_workday_detail(self):
        from midnight.jobs.scraper.fetchers.details import _workday_description
        from midnight.jobs.scraper.models import JobPost

        resp = mock.Mock(status_code=200)
        resp.json.return_value = {
            "jobPostingInfo": {"jobDescription": "<p>Python job</p>"}
        }
        post = JobPost(
            title="E",
            url="https://acme.wd1.myworkdayjobs.com/acme/site/job/X_REQ_1",
            company_slug="acme|wd1|site",
            ats="Workday",
        )
        with (
            mock.patch("requests.get", return_value=resp) as get,
            mock.patch("time.sleep"),
        ):
            self.assertEqual(_workday_description(post), "Python job")
        self.assertIn("/wday/cxs/acme/site/job/X_REQ_1", get.call_args[0][0])

    def test_page_selector_and_og_fallback(self):
        from midnight.jobs.scraper.fetchers.details import _page_description

        html = (
            "<html><head>"
            '<meta property="og:description" content="OG text here">'
            "</head><body>"
            '<div class="job-preview-details"><p>Full posting text. '
            + "Detail. "
            * 60
            + "</p></div>'"
            "</body></html>"
        )
        resp = mock.Mock(status_code=200, text=html)
        with mock.patch("requests.get", return_value=resp):
            self.assertTrue(
                _page_description("http://x", ["div.job-preview-details"]).startswith(
                    "Full posting text."
                )
            )
            self.assertEqual(
                _page_description("http://x", ["div.missing"]), "OG text here"
            )
            # no selector hit and no og tag
            resp.text = "<html><body><p>hi</p></body></html>"
            self.assertIsNone(_page_description("http://x", ["div.missing"]))

    def test_enrich_skips_and_caches(self):
        from midnight.jobs.scraper.fetchers import details
        from midnight.jobs.scraper.models import JobPost

        details._detail_cache.clear()
        with_desc = JobPost(title="E", url="http://x/1", description="Hi")
        unknown = JobPost(title="E", url="http://x/2", ats="unknown")
        bamboo = JobPost(title="E", url="http://x/3", ats="BambooHR")
        resp = mock.Mock(status_code=200, text="<html><body><p>hi</p></body></html>")
        with mock.patch("requests.get", return_value=resp) as get:
            details.enrich_finalists([with_desc, unknown, bamboo])
            details.enrich_finalists([bamboo])
        # with_desc + unknown need no HTTP; bamboo fetched once then cached
        self.assertEqual(get.call_count, 1)
        self.assertIsNone(bamboo.description)
        details._detail_cache.clear()


class TestMatching(unittest.TestCase):
    def _score(self, title, **overrides):
        import midnight.jobs.scraper.results as res
        from midnight.jobs.scraper.models import JobPost

        base = {"title": title, "url": "http://u/x", "skill_level": "mid"}
        base.update(overrides)
        return res._score_job(JobPost(**base), _fixture_profile())

    def test_alias_matches(self):
        # "Machine Learning Engineer" matches the AI/ML interest via alias
        self.assertEqual(
            self._score("Machine Learning Engineer", remote=True), 4.0
        )  # alias +1, remote +2, mid +1

    def test_word_boundaries_block_false_positives(self):
        # "ai" must not match inside "retail"; "react" must not match
        # inside "interaction"
        self.assertEqual(
            self._score("Retail Associate", skill_level="entry"), 2.0
        )  # entry bonus only
        self.assertEqual(
            self._score("Customer Interaction Specialist"), 1.0
        )  # mid bonus only

    def test_location_word_boundaries(self):
        # "Edo" (profile state) must not match inside "Laredo" or "Toledo"
        self.assertEqual(
            self._score("Sales Associate", location="Laredo, TX", skill_level="entry"),
            2.0,  # entry bonus only
        )
        self.assertEqual(
            self._score(
                "Support Officer",
                location="Benin City, Edo",
                skill_level="mid",
            ),
            3.0,  # location +2, mid +1
        )

    def test_mobile_matches_mobiles(self):
        import midnight.jobs.scraper.results as res
        from midnight.jobs.scraper.models import JobPost

        profile = _fixture_profile()
        profile.user.interests = ["Mobiles"]
        post = JobPost(title="Mobile Developer", url="http://u/x")
        self.assertEqual(res._score_job(post, profile), 2.0)  # alias +1, mid +1

    def test_description_score_capped(self):
        post_desc = "Python React AI ML machine learning data science LLM deep learning"
        self.assertEqual(
            self._score("Clerk", description=post_desc), 7.0
        )  # mid +1, desc capped at +6


if __name__ == "__main__":
    unittest.main()
