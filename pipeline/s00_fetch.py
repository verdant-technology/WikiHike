"""Stage 0: fetch raw play-by-play archives from the shufinskiy/nba_data mirror.

The mirror republishes stats.nba.com playbyplayv3 per season. Raw archives are
immutable once cached; a manifest records sha256 so later stages can verify.
Season label N means the N-(N+1) regular season.
"""
import hashlib, json, pathlib, sys, time, urllib.request

SEASONS = range(2019, 2026)
URL = "https://raw.githubusercontent.com/shufinskiy/nba_data/main/datasets/nbastatsv3_{s}.tar.xz"
RAW = pathlib.Path(__file__).resolve().parent.parent / "data" / "raw"


def fetch(season: int) -> dict:
    dest = RAW / f"nbastatsv3_{season}.tar.xz"
    if not dest.exists():
        for attempt in range(4):
            try:
                tmp = dest.with_suffix(".part")
                urllib.request.urlretrieve(URL.format(s=season), tmp)
                tmp.rename(dest)
                break
            except Exception as e:  # network flake: back off and retry
                print(f"{season}: attempt {attempt + 1} failed: {e}", file=sys.stderr)
                time.sleep(2 ** attempt)
        else:
            raise RuntimeError(f"could not fetch {season}")
    digest = hashlib.sha256(dest.read_bytes()).hexdigest()
    return {"season": season, "file": dest.name, "sha256": digest, "bytes": dest.stat().st_size}


if __name__ == "__main__":
    RAW.mkdir(parents=True, exist_ok=True)
    manifest = [fetch(s) for s in SEASONS]
    (RAW / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))
    for m in manifest:
        print(m)
