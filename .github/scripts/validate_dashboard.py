import argparse
import json
import math
from pathlib import Path

DISTRICTS = ("池子", "小坪", "久木", "山の根", "沼間", "桜山", "新宿", "逗子")
PERIODS = [f"{year}-{half}" for year in range(2019, 2027) for half in ("H1", "H2")]


def validate_auxiliary_data(data):
    series_by_district = data.get("timeSeries")
    if not isinstance(series_by_district, dict):
        raise ValueError("時系列データがありません。既存データの上書きを中止してください。")
    for district in DISTRICTS:
        series = series_by_district.get(district)
        if not isinstance(series, list) or [row.get("period") for row in series if isinstance(row, dict)] != PERIODS or len(series) != len(PERIODS):
            raise ValueError(f"{district}: 2019-H1〜2026-H2の16期間が必要です。")
        for row in series:
            for key in ("ndvi", "ndmi"):
                value = row.get(key)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not -1 <= value <= 1:
                    raise ValueError(f"{district}/{row['period']}: {key}の有効な観測値がありません。")
    metadata = data.get("asfSlc")
    if not isinstance(metadata, list) or not metadata:
        raise ValueError("SAR観測メタデータが空です。既存データの上書きを中止してください。")
    for row in metadata:
        if not isinstance(row, dict) or any(not isinstance(row.get(key), str) or not row[key].strip() for key in ("granule", "orbit", "date", "beam")):
            raise ValueError("SAR観測メタデータの必須項目が欠けています。")


def main():
    parser = argparse.ArgumentParser(description="地図の時系列・SAR観測一覧が欠落していないか検証します。")
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    source = args.path.read_text(encoding="utf-8")
    prefix = "window.EXTERNAL_DASHBOARD_DATA ="
    if not source.startswith(prefix):
        raise ValueError("想定したdata.js形式ではありません。")
    data = json.loads(source[len(prefix):].strip().removesuffix(";"))
    validate_auxiliary_data(data)
    print("OK: 8地区×16期間のNDVI/NDMIとSAR観測メタデータ")


if __name__ == "__main__":
    main()
