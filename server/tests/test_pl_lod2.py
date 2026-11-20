"""tools/build_lod2_roofs.py for Poland (GUGiK's LoD2 CityGML, EPSG:2180): the powiats' download list, the roofType
codelist turned into AdV codes (and only for Poland), a "mixed" roof read from its faces, Polish coordinates through
server/pl1992, and the ridge's azimuth kept in the shards in degrees from true north."""
import csv
import gzip
import importlib.util
import io
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "tools"))
import lod2roofs  # noqa: E402

E0, N0, Z0 = 531359.4, 434606.6, 200.0          # (Lodz: EPSG:2180 easting, northing; PL-KRON86-NH height)
SRS = "urn:ogc:def:crs,crs:EPSG::2180,crs:PL-KRON86-NH"


def gabled(w=10.0, d=8.0, h=3.0, wall=6.0):
    """Ridge along x (east-west, grid azimuth 90), eaves wall m above the ground."""
    r = d / 2
    return [[(0, 0, wall), (w, 0, wall), (w, r, wall + h), (0, r, wall + h)],
            [(0, r, wall + h), (w, r, wall + h), (w, d, wall), (0, d, wall)]]


def ring_xml(r, x, y):
    pts = r + [r[0]]
    return ("<gml:LinearRing>" + "".join(f'<gml:pos srsDimension="3">{x + px:.2f} {y + py:.2f} {Z0 + pz:.2f}</gml:pos>'
                                         for px, py, pz in pts) + "</gml:LinearRing>")


def surface(kind, r, x, y):
    return (f"<bldg:boundedBy><bldg:{kind}><bldg:lod2MultiSurface><gml:MultiSurface><gml:surfaceMember>"
            f"<gml:Polygon><gml:exterior>{ring_xml(r, x, y)}</gml:exterior></gml:Polygon></gml:surfaceMember>"
            f"</gml:MultiSurface></bldg:lod2MultiSurface></bldg:{kind}></bldg:boundedBy>")


def building(roof_type, roofs, x, y, w=10.0, d=8.0, uid="a"):
    ground = [(0, 0, 0), (0, d, 0), (w, d, 0), (w, 0, 0)]
    return (f'<core:cityObjectMember><bldg:Building>'
            f'<gen:stringAttribute name="buildingId"><gen:value>{uid}</gen:value></gen:stringAttribute>'
            f'<gen:stringAttribute name="zrodloDach"><gen:value>ALS_II</gen:value></gen:stringAttribute>'
            + (f"<bldg:roofType>{roof_type}</bldg:roofType>" if roof_type else "")
            + surface("GroundSurface", ground, x, y) + "".join(surface("RoofSurface", r, x, y) for r in roofs)
            + "</bldg:Building></core:cityObjectMember>")


def citygml(*buildings, srs=SRS):
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<core:CityModel xmlns:core="http://www.opengis.net/citygml/2.0" '
            'xmlns:bldg="http://www.opengis.net/citygml/building/2.0" xmlns:gml="http://www.opengis.net/gml" '
            'xmlns:gen="http://www.opengis.net/citygml/generics/2.0">'
            f'<gml:boundedBy><gml:Envelope srsName="{srs}" srsDimension="3">'
            f'<gml:lowerCorner>{E0} {N0} {Z0}</gml:lowerCorner><gml:upperCorner>{E0 + 99} {N0 + 99} {Z0 + 9}'
            f'</gml:upperCorner></gml:Envelope></gml:boundedBy>' + "".join(buildings) + "</core:CityModel>").encode()


class ToolCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import lxml  # noqa: F401
            import pyproj  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("the builder needs lxml and pyproj")
        s = importlib.util.spec_from_file_location("build_lod2_roofs", ROOT / "tools" / "build_lod2_roofs.py")
        cls.B = importlib.util.module_from_spec(s)
        s.loader.exec_module(cls.B)

    def rows(self, xml, source="PL"):
        return list(self.B.parse(io.BytesIO(xml), None, source))


class EpsgTest(ToolCase):
    def test_2180_is_read_from_the_polish_srs_name(self):
        self.assertEqual(self.B.EPSG.search(SRS).group(1), "2180")
        r = self.rows(citygml(building("1030", gabled(), E0, N0)))
        self.assertEqual(r[0]["epsg"], 2180)
        self.assertAlmostEqual(r[0]["x"], E0 + 5.0, 1)           # (easting first)
        self.assertAlmostEqual(r[0]["y"], N0 + 4.0, 1)


class CodesTest(ToolCase):
    def test_the_codelist_becomes_the_adv_codes(self):
        flat = [[(0, 0, 6), (10, 0, 6), (10, 8, 6), (0, 8, 6)]]
        xml = citygml(building("1030", gabled(), E0, N0), building("1000", flat, E0 + 50, N0),
                      building("1040", gabled(), E0 + 100, N0))
        self.assertEqual([r["roof"] for r in self.rows(xml)], ["3100", "1000", "3200"])
        self.assertEqual(self.B.PL_ROOF[1130], 5000)
        self.assertEqual(sorted(self.B.PL_ROOF), list(range(1000, 1150, 10)))

    def test_the_other_sources_keep_their_codes(self):
        """A German roofType 3100 stays 3100 and the codelist's 1030 is not turned into anything outside Poland."""
        xml = citygml(building("3100", gabled(), E0, N0), building("1030", gabled(), E0 + 50, N0))
        self.assertEqual([r["roof"] for r in self.rows(xml, None)], ["3100", "1030"])
        self.assertEqual([r["roof"] for r in self.rows(xml, "HE")], ["3100", "1030"])
        # (in Poland 1030 is the CityGML gabled roof, and 3100 no codelist value: the faces say what it is)
        self.assertEqual([r["roof"] for r in self.rows(xml, "PL")], ["3100", "3100"])

    def test_a_polish_code_outside_the_list_says_nothing_and_the_faces_decide(self):
        r = self.rows(citygml(building("1999", gabled(), E0, N0)))
        self.assertEqual(r[0]["roof"], "3100")

    def test_a_mixed_roof_is_read_from_its_faces(self):
        xml = citygml(building("1130", gabled(), E0, N0))
        r = self.rows(xml)[0]
        self.assertEqual(r["roof"], "3100")
        self.assertAlmostEqual(r["zt"] - r["zr"], 3.0, 1)       # (the roof's rise, not the span of the faces)
        self.assertAlmostEqual(r["zt"] - r["z0"], 9.0, 1)

    def test_a_mixed_roof_the_faces_cannot_tell_stays_mixed(self):
        wall = [[(0, 0, 6), (10, 0, 6), (10, 0, 9), (0, 0, 9)]]       # (upright only: no roof plane)
        r = self.rows(citygml(building("1130", wall, E0, N0)))[0]
        self.assertEqual(r["roof"], "5000")

    def test_a_typed_roof_is_not_read_again(self):
        flat_faces_typed_gabled = [[(0, 0, 6), (10, 0, 6), (10, 8, 6), (0, 8, 6)]]
        r = self.rows(citygml(building("1030", flat_faces_typed_gabled, E0, N0)))[0]
        self.assertEqual(r["roof"], "3100")

    def test_a_flat_building(self):
        flat = [[(0, 0, 6), (10, 0, 6), (10, 8, 6), (0, 8, 6)]]
        r = self.rows(citygml(building("1000", flat, E0, N0)))[0]
        self.assertEqual(r["roof"], "1000")
        self.assertAlmostEqual(r["zt"] - r["z0"], 6.0, 1)

    def test_every_adv_code_it_gives_is_one_the_server_reads_or_skips(self):
        for code in self.B.PL_ROOF.values():
            self.assertTrue(code in lod2roofs.SHAPES or code in (5000, 9999))


class JobsTest(ToolCase):
    class Index:
        names = ["1661_M-33.bld", "1661_M-34.bld", "1261_M-34.bld", "1061_M-34.bld", "0201_M-33.bld", "0401_N-33.bld",
                 "2801_M-34.bld", "1001_M-34.bld"]

    def jobs(self, env):
        with mock.patch.object(self.B, "pl_index", return_value=self.Index()), mock.patch.dict("os.environ", env):
            if "BNE_LOD2_PL_POWIATS" not in env:
                os.environ.pop("BNE_LOD2_PL_POWIATS", None)
            return self.B.jobs("PL")

    def test_the_powiats_of_the_voivodeships_with_lod2(self):
        j = self.jobs({})
        self.assertEqual([c for c, _ in j], ["0401", "1261", "1661", "2801"])        # (not 02, 10 Lodz, 1061)
        self.assertEqual(j[0][1], "https://opendata.geoportal.gov.pl/InneDane/Budynki3D/LOD2/0401_gml.zip")

    def test_the_powiat_list_restricts_it(self):
        self.assertEqual([c for c, _ in self.jobs({"BNE_LOD2_PL_POWIATS": "1661, 1261"})], ["1261", "1661"])
        self.assertEqual(self.jobs({"BNE_LOD2_PL_POWIATS": "1061"}), [])        # (a restriction cannot add a powiat)


class SpoolTest(ToolCase):
    def spooled(self, epsg, rows):
        with tempfile.TemporaryDirectory() as d:
            self.B.spool(d, epsg, rows)
            out = [np.fromfile(os.path.join(d, n), self.B.RECORD) for n in sorted(os.listdir(d))]
        return np.concatenate(out)

    def test_polish_coordinates_go_through_pl1992(self):
        r = self.spooled(2180, [(531359.4, 434606.6, 3100, 9.0, 3.0, math.nan)])
        self.assertAlmostEqual(r["lat"][0] / 1e6, 51.77695, 5)
        self.assertAlmostEqual(r["lon"][0] / 1e6, 19.45468, 5)
        self.assertEqual(r["ridge"][0], self.B.NO_RIDGE)
        import pl1992
        with mock.patch.object(self.B.pl1992, "to_lonlat", wraps=pl1992.to_lonlat) as m:
            self.spooled(2180, [(531359.4, 434606.6, 3100, 9.0, 3.0, math.nan)])
        self.assertTrue(m.called)

    def test_other_crs_are_unchanged(self):
        from pyproj import Transformer
        x, y = Transformer.from_crs(4326, 25832, always_xy=True).transform(9.1, 50.9)
        with mock.patch.object(self.B.pl1992, "to_lonlat", side_effect=AssertionError("pl1992 for UTM")):
            r = self.spooled(25832, [(x, y, 3100, 9.0, 3.0, math.nan)])
        self.assertAlmostEqual(r["lat"][0] / 1e6, 50.9, 5)
        self.assertAlmostEqual(r["lon"][0] / 1e6, 9.1, 5)

    def test_the_ridge_is_turned_to_true_north(self):
        """An east-west ridge in the grid at 24 E (5 degrees east of the central meridian) at 52 N: the grid's north
        leans east of true north by (lon - 19) * sin(lat) = 3.9 degrees, so the ridge is 93.9 true, not 90."""
        from pyproj import Transformer
        x, y = Transformer.from_crs(4326, 2180, always_xy=True).transform(24.0, 52.0)
        r = self.spooled(2180, [(x, y, 3100, 9.0, 3.0, 90.0), (x, y, 3100, 9.0, 3.0, 0.0)])
        gamma = 5.0 * math.sin(math.radians(52.0))
        want = sorted([round(90 + gamma) % 180, round(gamma) % 180])
        self.assertEqual(sorted(int(v) for v in r["ridge"]), want)
        near_cm = self.spooled(2180, [(500000.0, 500000.0, 3100, 9.0, 3.0, 45.0)])
        self.assertEqual(int(near_cm["ridge"][0]), 45)          # (on the central meridian: no convergence)

    def test_any_crs_is_corrected(self):
        """UTM 32 at 6 E (the central meridian), 9 E at 50 N (3 degrees east): gamma = 3 * sin(50)."""
        from pyproj import Transformer
        x, y = Transformer.from_crs(4326, 25832, always_xy=True).transform(12.0, 50.0)
        r = self.spooled(25832, [(x, y, 3100, 9.0, 3.0, 0.0)])
        self.assertEqual(int(r["ridge"][0]), round(3.0 * math.sin(math.radians(50.0))) % 180)

    def test_the_ridge_stays_in_range(self):
        r = self.spooled(2180, [(E0, N0, 3100, 9.0, 3.0, 179.0), (E0, N0, 3100, 9.0, 3.0, 0.0)])
        self.assertTrue(all(0 <= int(v) < 180 for v in r["ridge"]))


class ShardRoundTripTest(ToolCase):
    """csv rows -> build() -> the server's decode: where a building stands, its code, heights and ridge."""

    def build(self, rows):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "out"))
            with gzip.open(os.path.join(d, "out", "PL.csv.gz"), "wt", newline="") as f:
                w = csv.writer(f, lineterminator="\n")
                for r in rows:
                    w.writerow([r[k] for k in self.B.FIELDS])
            dest = os.path.join(d, "dest")
            with mock.patch.object(self.B, "ROOT", d):
                self.B.build(dest, ["PL"])
            out = []
            for x in os.listdir(dest):
                if x.isdigit():
                    for n in os.listdir(os.path.join(dest, x)):
                        with open(os.path.join(dest, x, n), "rb") as fh:
                            out.append(lod2roofs.decode(fh.read()))
        return out

    def test_a_polish_building_round_trips_with_its_ridge(self):
        rows = self.rows(citygml(building("1030", gabled(), E0, N0)))
        self.assertEqual(rows[0]["ridge"], 90)
        sh = self.build(rows)
        self.assertEqual(len(sh), 1)
        s = sh[0]
        import pl1992
        lon, lat = pl1992.to_lonlat(E0 + 5.0, N0 + 4.0)          # (the building's middle)
        self.assertAlmostEqual(float(s["lat"][0]), float(lat), 5)
        self.assertAlmostEqual(float(s["lon"][0]), float(lon), 5)
        self.assertEqual(int(s["code"][0]), 3100)
        self.assertAlmostEqual(float(s["height"][0]), 9.0, 1)
        self.assertAlmostEqual(float(s["roof"][0]), 3.0, 1)
        gamma = (19.45468 - 19.0) * math.sin(math.radians(51.77695))
        self.assertAlmostEqual(float(s["ridge"][0]), 90 + gamma, delta=1.0)
        self.assertEqual(self.B.RECORD.names[-1], "ridge")

    def test_a_building_without_a_ridge_decodes_as_none(self):
        flat = [[(0, 0, 6), (10, 0, 6), (10, 8, 6), (0, 8, 6)]]
        sh = self.build(self.rows(citygml(building("1000", flat, E0, N0))))
        self.assertTrue(np.isnan(sh[0]["ridge"][0]))


if __name__ == "__main__":
    unittest.main()
