import os
"""lod2roofs: a measured record fills what the map leaves out of the footprint it stands in; the map's own values stay,
nothing is asked for outside Germany, and a missing shard means the predicted roofs."""
import importlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import buildings as bld  # noqa: E402
import geodesy  # noqa: E402
import lod2roofs as lr  # noqa: E402
import netfetch  # noqa: E402
import polandlod1  # noqa: E402

LAT, LON = 50.9, 9.1


def shard(rows, ridge=None):
    """npz bytes of [(lat, lon, code, height m, roof m)]; ridge: [degrees true 0..179 or None] per row (a shard
    without the field, as published before it, when not given)."""
    a = np.array(rows, np.float64)
    buf = io.BytesIO()
    extra = {} if ridge is None else {"ridge": np.array([255 if r is None else r for r in ridge], np.uint8)}
    np.savez_compressed(buf, lat=np.round(a[:, 0] * 1e6).astype(np.int32), lon=np.round(a[:, 1] * 1e6).astype(np.int32),
                        code=a[:, 2].astype(np.int16), height=np.round(a[:, 3] * 10).astype(np.uint16),
                        roof=np.round(a[:, 4] * 10).astype(np.uint16), **extra)
    return buf.getvalue()


class Body:
    def __init__(self, body):
        self.body = body


class Fetcher:
    def __init__(self, body=None, error=None):
        self.body, self.error, self.urls = body, error, []

    def get(self, url, kind="demand", **_):
        self.urls.append(url)
        if self.error:
            raise self.error
        return Body(self.body)


def ring(cx, cy, r=6.0):
    return np.array([cx - r, cx + r, cx + r, cx - r]), np.array([cy - r, cy - r, cy + r, cy + r])


class Base(unittest.TestCase):
    def records(self, rows):
        frame = geodesy.EnuFrame(LAT, LON)
        src = lr.Source(None, Fetcher(shard(rows)))
        return src.tile(frame, -200, -200, 200, 200), src


class FillTest(Base):
    def test_a_measured_roof_fills_an_unknown_building(self):
        rec, _ = self.records([(LAT, LON, 3300, 9.4, 3.2)])
        at = rec.fill({"roof_shape": None, "height": None}, *ring(0, 0))
        self.assertEqual(at["roof_shape"], "half-hipped")
        self.assertAlmostEqual(at["height"], 9.4, 3)
        self.assertAlmostEqual(at["roof_height"], 3.2, 3)

    def test_the_maps_own_values_stay(self):
        rec, _ = self.records([(LAT, LON, 3100, 9.4, 3.2)])
        at = rec.fill({"roof_shape": "hipped", "height": 12.0, "roof_height": 2.0}, *ring(0, 0))
        self.assertEqual((at["roof_shape"], at["height"], at["roof_height"]), ("hipped", 12.0, 2.0))

    def test_a_mixed_roof_gives_its_height_but_no_shape(self):
        rec, _ = self.records([(LAT, LON, 5000, 8.0, 3.0)])
        at = rec.fill({"roof_shape": None, "height": None}, *ring(0, 0))
        self.assertIsNone(at["roof_shape"])
        self.assertAlmostEqual(at["height"], 8.0, 3)

    def test_a_record_beside_the_footprint_does_not_join(self):
        rec, _ = self.records([(LAT, LON, 3100, 9.4, 3.2)])
        at = rec.fill({"roof_shape": None, "height": None}, *ring(40, 0))
        self.assertIsNone(at["roof_shape"])

    def test_the_tallest_part_says_what_the_building_is(self):
        d = 2e-5
        rec, _ = self.records([(LAT, LON, 1000, 4.0, 0.0), (LAT + d, LON, 3200, 11.0, 4.0)])
        at = rec.fill({"roof_shape": None, "height": None}, *ring(0, 0))
        self.assertEqual(at["roof_shape"], "hipped")
        self.assertAlmostEqual(at["height"], 11.0, 3)

    def test_plan_draws_the_filled_shape(self):
        rec, _ = self.records([(LAT, LON, 3400, 9.0, 3.5)])
        e, n = ring(0, 0)
        at = rec.fill({"class": "house", "roof_shape": None, "height": None, "seed_id": "a"}, e, n)
        spec = bld.plan(np.stack([e, n], 1), at)
        self.assertEqual(spec.roof, "mansard")


class ShardTest(Base):
    def test_every_code_in_the_table_is_a_shape_plan_knows(self):
        known = {"gabled", "hipped", "flat", "pyramidal", "half-hipped", "mansard", "skillion", "round"} | set(bld.DOME_ROOFS)
        self.assertLessEqual(set(lr.SHAPES.values()), known)

    def test_nothing_is_asked_for_outside_germany(self):
        self.assertEqual(lr.tiles_over(40.0, -3.0, 40.2, -2.8), [])
        f = Fetcher(shard([(LAT, LON, 3100, 9.0, 3.0)]))
        self.assertIsNone(lr.Source(None, f).tile(geodesy.EnuFrame(40.0, -3.0), -200, -200, 200, 200))
        self.assertEqual(f.urls, [])

    def test_a_missing_shard_means_the_predicted_roofs_and_is_remembered(self):
        f = Fetcher(error=netfetch.NotFound("none"))
        src = lr.Source(None, f)
        frame = geodesy.EnuFrame(LAT, LON)
        self.assertIsNone(src.tile(frame, -200, -200, 200, 200))
        asked = len(f.urls)
        self.assertGreater(asked, 0)
        self.assertIsNone(src.tile(frame, -200, -200, 200, 200))
        self.assertEqual(len(f.urls), asked)

    def test_a_missing_shard_kept_on_disk_is_asked_again_after_a_week(self):
        """A 404 is kept as an empty file (no asking again every session), but not for good: before the shards were
        published every German tile answered 404, and those players would never have got the roofs."""
        import os, tempfile, time
        with tempfile.TemporaryDirectory() as d:
            f = Fetcher(error=netfetch.NotFound("none"))
            frame = geodesy.EnuFrame(LAT, LON)
            self.assertIsNone(lr.Source(d, f).tile(frame, -200, -200, 200, 200))
            kept = [os.path.join(dp, n) for dp, _, ns in os.walk(d) for n in ns if n.endswith(".npz")]
            self.assertTrue(kept and all(os.path.getsize(p) == 0 for p in kept))
            asked = len(f.urls)
            lr.Source(d, f).tile(frame, -200, -200, 200, 200)
            self.assertEqual(len(f.urls), asked, "a fresh miss on disk: not asked again")
            old = time.time() - lr.MISS_TTL_S - 60
            for p in kept:
                os.utime(p, (old, old))
            lr.Source(d, f).tile(frame, -200, -200, 200, 200)
            self.assertGreater(len(f.urls), asked, "a week-old miss: asked again")

    def test_offline_asks_again_only_after_a_while(self):
        f = Fetcher(error=OSError("offline"))
        src = lr.Source(None, f)
        frame = geodesy.EnuFrame(LAT, LON)
        self.assertIsNone(src.tile(frame, -200, -200, 200, 200))
        asked = len(f.urls)
        self.assertIsNone(src.tile(frame, -200, -200, 200, 200))
        self.assertEqual(len(f.urls), asked)

    def test_a_shard_on_disk_is_not_fetched_again(self):
        with tempfile.TemporaryDirectory() as d:
            f = Fetcher(shard([(LAT, LON, 3100, 9.0, 3.0)]))
            frame = geodesy.EnuFrame(LAT, LON)
            self.assertIsNotNone(lr.Source(d, f).tile(frame, -200, -200, 200, 200))
            asked = len(f.urls)
            self.assertIsNotNone(lr.Source(d, f).tile(frame, -200, -200, 200, 200))
            self.assertEqual(len(f.urls), asked)

    def test_shards_from_the_host_the_folders_manifest_names(self):
        import json
        body = shard([(LAT, LON, 3100, 9.0, 3.0)])

        class Site(Fetcher):
            def get(self, url, kind="demand", **_):
                self.urls.append(url)
                if url.endswith("/manifest.json"):
                    return Body(json.dumps({"built": "2026-11-09", "data": "https://tiles.test/data/lod2/k1"}).encode())
                return Body(body)
        with tempfile.TemporaryDirectory() as d:
            f = Site()
            self.assertIsNotNone(lr.Source(d, f).tile(geodesy.EnuFrame(LAT, LON), -200, -200, 200, 200))
            x, y = lr.tile_of(LAT, LON)
            self.assertIn(f"https://tiles.test/data/lod2/k1/{x}/{y}.npz", f.urls)
            self.assertFalse([u for u in f.urls if u.endswith(".npz") and u.startswith(lr.railtags.PAGES)])

    def test_a_broken_shard_reads_as_none(self):
        self.assertEqual(lr.decode(b"not a shard"), {})


if __name__ == "__main__":
    unittest.main()


class CreditTest(unittest.TestCase):
    def test_credited_only_with_a_shard_on_disk(self):
        import tempfile, credits
        d = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, d, True)
        lat, lon = 52.52, 13.405                    # (Berlin)
        self.assertFalse(lr.credited_near(d, lat, lon, 500.0))
        x, y = lr.tile_of(lat, lon)
        os.makedirs(os.path.join(d, "pagesdata", "lod2"))
        path = os.path.join(d, "pagesdata", "lod2", f"{x}_{y}.npz")
        open(path, "wb").close()                    # (a 404 kept as an empty file: no records, no credit)
        self.assertFalse(lr.credited_near(d, lat, lon, 500.0))
        with open(path, "wb") as fh:
            fh.write(b"x")
        self.assertTrue(lr.credited_near(d, lat, lon, 500.0))
        self.assertFalse(lr.credited_near(d, 48.85, 2.35, 500.0))     # (Paris: outside Germany)
        self.assertEqual(lr.credited_near(d, lat, lon, 500.0), {"roof:lod2-de"})
        self.assertIn("GeoBasis-DE", credits.full_label("roof:lod2-de"))
        self.assertIn("roof:lod2-de", credits.ORDER)


class CountriesTest(unittest.TestCase):
    """Several countries' shards, each in its own folder and box; a local folder (BNE_LOD2_DIR) instead of the site."""

    def folders(self, lat, lon):
        f = Fetcher(error=netfetch.NotFound("none"))
        lr.Source(None, f).tile(geodesy.EnuFrame(lat, lon), -200, -200, 200, 200)
        return {u.split(f"{lr.railtags.PAGES}/", 1)[1].split("/")[0] for u in f.urls}

    def test_each_place_asks_only_the_countries_whose_box_it_is_in(self):
        self.assertEqual(self.folders(59.437, 24.7536), {"lod2-ee"})                 # (Tallinn)
        self.assertEqual(self.folders(46.948, 7.4474), {"lod2-ch"})                  # (Bern)
        self.assertEqual(self.folders(47.3769, 8.5417), {"lod2", "lod2-ch"})         # (Zurich: in both boxes)
        self.assertEqual(self.folders(52.52, 13.405), {"lod2"})                      # (Berlin)
        self.assertEqual(self.folders(48.2082, 16.3738), {"lod2-wien"})              # (Vienna)
        self.assertEqual(self.folders(47.07, 15.44), set())                          # (Graz: Austria, not Vienna)
        self.assertEqual(self.folders(48.85, 2.35), set())                           # (Paris)

    def local(self, d, folder, lat, lon, rows):
        x, y = lr.tile_of(lat, lon)
        os.makedirs(os.path.join(d, folder, str(x)), exist_ok=True)
        with open(os.path.join(d, folder, str(x), f"{y}.npz"), "wb") as fh:
            fh.write(shard(rows))

    def test_a_local_folder_is_read_and_nothing_fetched(self):
        lat, lon = 59.437, 24.7536
        with tempfile.TemporaryDirectory() as d:
            self.local(d, "lod2-ee", lat, lon, [(lat, lon, 3200, 12.0, 4.0)])
            f = Fetcher(error=AssertionError("fetched"))
            rec = lr.Source(None, f, local=d).tile(geodesy.EnuFrame(lat, lon), -200, -200, 200, 200)
            self.assertEqual(f.urls, [])
            at = rec.fill({"roof_shape": None, "height": None}, *ring(0, 0))
            self.assertEqual((at["roof_shape"], at["height"]), ("hipped", 12.0))

    def test_a_border_tile_joins_both_countries_records(self):
        lat, lon = 47.3769, 8.5417
        with tempfile.TemporaryDirectory() as d:
            self.local(d, "lod2", lat, lon, [(lat, lon + 0.002, 3100, 9.0, 3.0)])
            self.local(d, "lod2-ch", lat, lon, [(lat, lon, 3300, 14.0, 5.0)])
            frame = geodesy.EnuFrame(lat, lon)
            rec = lr.Source(None, None, local=d).tile(frame, -400, -400, 400, 400)
            self.assertEqual(rec.fill({"roof_shape": None, "height": None}, *ring(0, 0))["roof_shape"], "half-hipped")
            e, _, _ = frame.geodetic_to_enu(np.array([lat]), np.array([lon + 0.002]), 0.0)
            self.assertEqual(rec.fill({"roof_shape": None}, *ring(float(e[0]), 0))["roof_shape"], "gabled")

    def test_each_country_credited_near_its_own_shards(self):
        import credits
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(lr.credited_near(None, 59.437, 24.7536, 500.0, local=d), set())
            self.local(d, "lod2-ee", 59.437, 24.7536, [(59.437, 24.7536, 3100, 9.0, 3.0)])
            self.local(d, "lod2-ch", 46.948, 7.4474, [(46.948, 7.4474, 3100, 9.0, 3.0)])
            self.assertEqual(lr.credited_near(None, 59.437, 24.7536, 500.0, local=d), {"roof:lod2-ee"})
            self.assertEqual(lr.credited_near(None, 46.948, 7.4474, 500.0, local=d), {"roof:lod2-ch"})
            self.assertEqual(lr.credited_near(None, 52.52, 13.405, 500.0, local=d), set())
        for c in lr.SOURCES:
            self.assertIn(c.credit, credits.ORDER)
        self.assertIn("swisstopo", credits.full_label("roof:lod2-ch"))
        self.assertIn("Land and Spatial Development Board", credits.full_label("roof:lod2-ee"))


PL_LAT, PL_LON = 51.77695, 19.45468     # (Lodz)
GORLITZ = (51.15, 14.99)                # (Germany's and Poland's boxes overlap here)


class PolandCase(unittest.TestCase):
    """BNE_PL_LOD2=1 for the test: lod2roofs re-read with it, and again without it afterwards."""

    def setUp(self):
        p = mock.patch.dict("os.environ", {"BNE_PL_LOD2": "1"})
        p.start()
        importlib.reload(lr)

        def restore():
            p.stop()
            importlib.reload(lr)
        self.addCleanup(restore)

    def records(self, rows, ridge=None, lat=PL_LAT, lon=PL_LON):
        src = lr.Source(None, Fetcher(shard(rows, ridge)))
        return src.tile(geodesy.EnuFrame(lat, lon), -200, -200, 200, 200), src


class PolandSwitchTest(unittest.TestCase):
    def tearDown(self):
        importlib.reload(lr)

    def test_unset_changes_nothing(self):
        with mock.patch.dict("os.environ", clear=False):
            os.environ.pop("BNE_PL_LOD2", None)
            importlib.reload(lr)
            self.assertEqual([c.key for c in lr.SOURCES], ["de", "ch", "ee", "wien"])
            f = Fetcher(error=netfetch.NotFound("none"))
            self.assertIsNone(lr.Source(None, f).tile(geodesy.EnuFrame(PL_LAT, PL_LON), -200, -200, 200, 200))
            self.assertEqual(f.urls, [])        # (Poland: nothing asked for)

    def test_set_adds_poland(self):
        with mock.patch.dict("os.environ", {"BNE_PL_LOD2": "1"}):
            importlib.reload(lr)
            self.assertEqual([c.key for c in lr.SOURCES], ["de", "ch", "ee", "wien", "pl"])
            pl = lr.SOURCES[-1]
            self.assertEqual((pl.folder, pl.credit), ("lod2-pl", "roof:lod2-pl"))
            import credits
            self.assertIn("roof:lod2-pl", credits.ORDER)
            self.assertIn("GUGiK", credits.full_label("roof:lod2-pl"))
            f = Fetcher(error=netfetch.NotFound("none"))
            lr.Source(None, f).tile(geodesy.EnuFrame(PL_LAT, PL_LON), -200, -200, 200, 200)
            self.assertEqual({u.split(f"{lr.railtags.PAGES}/", 1)[1].split("/")[0] for u in f.urls}, {"lod2-pl"})


class PolandHeightTest(PolandCase):
    def test_lod2_height_replaces_a_lod1_buildings(self):
        rec, _ = self.records([(PL_LAT, PL_LON, 3100, 9.4, 3.2)])
        at = rec.fill({"src_dataset": polandlod1.DATASET, "height": 6.0, "roof_shape": None}, *ring(0, 0))
        self.assertAlmostEqual(at["height"], 9.4, 3)
        self.assertEqual(at["roof_shape"], "gabled")

    def test_an_overture_buildings_own_height_stays(self):
        rec, _ = self.records([(PL_LAT, PL_LON, 3100, 9.4, 3.2)])
        at = rec.fill({"src_dataset": "OpenStreetMap", "height": 6.0, "roof_shape": None}, *ring(0, 0))
        self.assertEqual(at["height"], 6.0)
        self.assertEqual(at["roof_shape"], "gabled")
        at = rec.fill({"src_dataset": "Microsoft ML Buildings", "height": None}, *ring(0, 0))
        self.assertAlmostEqual(at["height"], 9.4, 3)         # (none to keep: filled, as ever)

    def test_only_polands_records_replace(self):
        """A German record on a building that says it is LOD1 (it cannot be, but the rule is the source's)."""
        src = lr.Source(None, Fetcher(shard([(LAT, LON, 3100, 9.4, 3.2)])))
        rec = src.tile(geodesy.EnuFrame(LAT, LON), -200, -200, 200, 200)
        at = rec.fill({"src_dataset": polandlod1.DATASET, "height": 6.0}, *ring(0, 0))
        self.assertEqual(at["height"], 6.0)

    def test_buildings_carries_src_dataset_to_fill(self):
        import inspect
        self.assertIn('"src_dataset"', inspect.getsource(bld.tile_buildings))


class RidgeTest(PolandCase):
    def test_a_ridge_gives_the_slope_direction_across_it(self):
        rec, _ = self.records([(PL_LAT, PL_LON, 3100, 9.0, 3.0)], [30])
        at = rec.fill({"roof_shape": None, "height": None}, *ring(0, 0))
        self.assertEqual(at["roof_direction"], 120.0)
        rec, _ = self.records([(PL_LAT, PL_LON, 3200, 9.0, 3.0)], [170])
        self.assertEqual(rec.fill({"roof_shape": None}, *ring(0, 0))["roof_direction"], 260.0)   # (170 + 90) % 360

    def test_a_known_direction_stays(self):
        rec, _ = self.records([(PL_LAT, PL_LON, 3100, 9.0, 3.0)], [30])
        at = rec.fill({"roof_shape": None, "roof_direction": 45.0}, *ring(0, 0))
        self.assertEqual(at["roof_direction"], 45.0)

    def test_none_for_flat_skillion_pyramid_dome_or_no_ridge(self):
        for code in (1000, 2100, 3500, 3700):
            rec, _ = self.records([(PL_LAT, PL_LON, code, 9.0, 3.0)], [30])
            self.assertIsNone(rec.fill({"roof_shape": None}, *ring(0, 0)).get("roof_direction"), code)
        rec, _ = self.records([(PL_LAT, PL_LON, 3100, 9.0, 3.0)], [None])
        self.assertIsNone(rec.fill({"roof_shape": None}, *ring(0, 0)).get("roof_direction"))

    def test_a_mapped_shape_with_no_direction_gets_the_ridge_too(self):
        rec, _ = self.records([(PL_LAT, PL_LON, 3100, 9.0, 3.0)], [90])
        at = rec.fill({"roof_shape": "gabled", "height": 7.0}, *ring(0, 0))
        self.assertEqual(at["roof_direction"], 180.0)

    def test_a_shard_without_the_field_still_decodes(self):
        d = lr.decode(shard([(LAT, LON, 3100, 9.0, 3.0)]))
        self.assertEqual(len(d["lat"]), 1)
        self.assertTrue(np.isnan(d["ridge"]).all())
        rec, _ = self.records([(PL_LAT, PL_LON, 3100, 9.0, 3.0)])
        at = rec.fill({"roof_shape": None}, *ring(0, 0))
        self.assertEqual(at["roof_shape"], "gabled")
        self.assertIsNone(at.get("roof_direction"))

    def test_the_ridge_round_trips(self):
        row = (LAT, LON, 3100, 9.0, 3.0)
        d = lr.decode(shard([row, row, row], [0, 179, None]))
        self.assertEqual(d["ridge"][:2].tolist(), [0.0, 179.0])
        self.assertTrue(np.isnan(d["ridge"][2]))


class FolderRetryTest(PolandCase):
    def test_a_folder_that_fails_does_not_stop_the_others(self):
        body = shard([(GORLITZ[0], GORLITZ[1], 3100, 9.0, 3.0)])

        class Half(Fetcher):
            def get(self, url, kind="demand", **_):
                self.urls.append(url)
                if "/lod2-pl/" in url:
                    raise OSError("not published")
                return Body(body)
        f = Half()
        src = lr.Source(None, f)
        frame = geodesy.EnuFrame(*GORLITZ)
        rec = src.tile(frame, -200, -200, 200, 200)
        self.assertIsNotNone(rec)
        self.assertEqual(rec.fill({"roof_shape": None}, *ring(0, 0))["roof_shape"], "gabled")
        self.assertEqual(set(src.down_at), {"lod2-pl"})
        asked = len([u for u in f.urls if "/lod2-pl/" in u])
        src.tile(frame, -200, -200, 200, 200)
        self.assertEqual(len([u for u in f.urls if "/lod2-pl/" in u]), asked, "the failing folder waits its RETRY_S")
