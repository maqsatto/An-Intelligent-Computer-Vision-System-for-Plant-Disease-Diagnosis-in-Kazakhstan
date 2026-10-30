import importlib.util
import json
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("metadata_audit", ROOT / "ml/research/audit_plantdoc_metadata.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class MetadataProvenanceTest(unittest.TestCase):
    def test_audit_uses_current_date_and_does_not_invent_a_license(self):
        with TemporaryDirectory() as temporary:
            evidence = Path(temporary)
            for repo in audit.REPOSITORIES:
                (evidence / f"{repo}-commit.json").write_text(json.dumps({"sha": "commit", "commit": {"tree": {"sha": "tree"}}}))
                (evidence / f"{repo}-tree.json").write_text(json.dumps({"sha": "tree", "truncated": False, "tree": []}))
                (evidence / f"{repo}-LICENSE.txt").write_text("Unknown license")
            for split in ("train", "test"):
                (evidence / f"PlantDoc-Object-Detection-Dataset-{split}_labels.csv").write_text("class,filename,width,height,xmin,ymin,xmax,ymax\n")
            report = audit.audit(evidence)
            self.assertEqual(report["checked_on"], date.today().isoformat())
            self.assertTrue(all(item["declared_license"] is None for item in report["repositories"].values()))


if __name__ == "__main__":
    unittest.main()
