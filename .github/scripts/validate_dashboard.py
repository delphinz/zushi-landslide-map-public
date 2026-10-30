import argparse
import json
import math
from datetime import date
from pathlib import Path

DISTRICTS = ("池子", "小坪", "久木", "山の根", "沼間", "桜山", "新宿", "逗子")
PERIODS = [f"{year}-{half}" for year in range(2019, 2027) for half in ("H1", "H2")]


def validate_auxiliary_data(data):
    if not isinstance(data, dict):
        raise ValueError("地図データはオブジェクトである必要があります。")
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
    validate_sar_metadata(data.get("asfSlc"))


def validate_sar_metadata(metadata):
    if not isinstance(metadata, list) or not metadata:
        raise ValueError("SAR観測メタデータが空です。既存データの上書きを中止してください。")
    for row in metadata:
        if not isinstance(row, dict) or any(not isinstance(row.get(key), str) or not row[key].strip() for key in ("granule", "orbit", "date", "beam")):
            raise ValueError("SAR観測メタデータの必須項目が欠けています。")
        try:
            if date.fromisoformat(row["date"]).isoformat() != row["date"]:
                raise ValueError("invalid date format")
        except ValueError:
            raise ValueError("SAR観測日付はYYYY-MM-DD形式の実在する日付が必要です。") from None
        if row["orbit"] not in ("ASCENDING", "DESCENDING"):
            raise ValueError("SAR軌道方向が不正です。")


def require_number(value, name, minimum=-math.inf, maximum=math.inf):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"{name}: 有限かつ範囲内の数値が必要です。")


def validate_dashboard_data(data, root=None):
    validate_auxiliary_data(data)
    grid = data.get("grid")
    if not isinstance(grid, dict):
        raise ValueError("地図グリッドがありません。")
    rows, cols = grid.get("rows"), grid.get("cols")
    for name, value in (("rows", rows), ("cols", cols)):
        if type(value) is not int or value <= 0:
            raise ValueError(f"grid.{name}: 正の整数が必要です。")
    for name, lower, upper in (("west", -180, 180), ("east", -180, 180), ("south", -90, 90), ("north", -90, 90)):
        require_number(grid.get(name), f"grid.{name}", lower, upper)
    if grid["west"] >= grid["east"] or grid["south"] >= grid["north"]:
        raise ValueError("地図グリッドの境界が不正です。")
    if data.get("bounds") != [[grid["south"], grid["west"]], [grid["north"], grid["east"]]]:
        raise ValueError("地図画像とグリッドの境界が一致しません。")
    ranges = {
        "elev": (-1000, 10000), "slope": (0, 90), "tpi": (-math.inf, math.inf),
        "twi": (-math.inf, math.inf), "curv": (-math.inf, math.inf), "pcurv": (-math.inf, math.inf),
        "rock": (0, 100), "form": (0, 4), "bdist": (0, math.inf), "insar": (0, 100),
        "lband": (-math.inf, math.inf), "ndvi": (-1, 1), "mswing": (-2, 2),
        "prob": (0, 100), "rf": (0, 100), "gtb": (0, 100), "haz": (0, 255),
    }
    for key, (lower, upper) in ranges.items():
        matrix = grid.get(key)
        if not isinstance(matrix, list) or len(matrix) != rows or any(not isinstance(row, list) or len(row) != cols for row in matrix):
            raise ValueError(f"grid.{key}: グリッド寸法が一致しません。")
        for row in matrix:
            for value in row:
                require_number(value, f"grid.{key}", lower, upper)
                if key in ("form", "haz") and (type(value) is not int or value not in ((0, 1, 2, 3, 4) if key == "form" else (0, 1, 2, 255))):
                    raise ValueError(f"grid.{key}: 区分値が不正です。")
    if "valid" in grid:
        valid = grid["valid"]
        if not isinstance(valid, list) or len(valid) != rows or any(not isinstance(row, list) or len(row) != cols or any(type(v) is not bool for v in row) for row in valid):
            raise ValueError("grid.valid: 有効性マスクが不正です。")
        if any(valid[r][c] != (grid["form"][r][c] != 0) for r in range(rows) for c in range(cols)):
            raise ValueError("有効性マスクと地質の対象範囲が一致しません。")
    if any(grid["form"][r][c] != 0 and grid["haz"][r][c] == 255 for r in range(rows) for c in range(cols)):
        raise ValueError("評価対象に法指定データの欠損があります。")
    if "asfSlcSource" in data and (not isinstance(data["asfSlcSource"], str) or not data["asfSlcSource"].strip()):
        raise ValueError("SAR観測一覧の出典表示が不正です。")
    districts = data.get("districts")
    if not isinstance(districts, list) or len(districts) != 8 or any(not isinstance(d, dict) for d in districts) or {d.get("地区名") for d in districts} != set(DISTRICTS):
        raise ValueError("地区集計は重複のない8地区が必要です。")
    for d in districts:
        for key in ("調査対象エリア", "推奨対応ランク"):
            if not isinstance(d.get(key), str) or not d[key].strip():
                raise ValueError(f"地区集計の{key}がありません。")
        for key, lower, upper in (("地区番号", 1, 8), ("中心緯度", -90, 90), ("中心経度", -180, 180), ("AI相対リスクスコア_斜面平均", 0, 100), ("AI相対リスクスコア_最大", 0, 100), ("警戒斜面面積_スコア70以上(ha)", 0, math.inf), ("区域外_隠れAI高リスク面積(ha)", 0, math.inf), ("InSAR変位擾乱指数_最大", 0, 100)):
            require_number(d.get(key), key, lower, upper)
    events = data.get("historicalEvents")
    if not isinstance(events, list) or len(events) != 9 or any(not isinstance(ev, dict) for ev in events):
        raise ValueError("既往災害9事案が必要です。")
    if len({ev.get("event_id") for ev in events}) != 9:
        raise ValueError("既往災害IDが重複しています。")
    for ev in events:
        for key in ("event_id", "date", "title", "address", "source", "dimensions", "trigger", "geology_mechanism", "damage_impact", "gsj_formation", "in_statutory_hazard_zone"):
            if not isinstance(ev.get(key), str) or not ev[key].strip():
                raise ValueError(f"既往災害の{key}がありません。")
        for key, lower, upper in (("lat", -90, 90), ("lon", -180, 180), ("ai_max_prob_pct", 0, 100), ("ai_mean_prob_pct", 0, 100), ("insar_max_creep_idx", 0, 100), ("site_max_slope_deg", 0, 90), ("boundary_dist_m", 0, math.inf), ("volume_m3", 0, math.inf), ("weight_ton", 0, math.inf), ("site_max_profile_curv", -math.inf, math.inf), ("site_moisture_swing", -2, 2), ("site_min_dndvi", -2, 2)):
            require_number(ev.get(key), key, lower, upper)
    require_number(data.get("auc"), "auc", 0, 1)
    require_number(data.get("totalHiddenHa"), "totalHiddenHa", 0)
    for threshold in range(40, 95, 5):
        area = data.get("globalAreaByThresh", {}).get(str(threshold), {})
        for key in ("m2", "ha"):
            require_number(area.get(key), f"面積{threshold}/{key}", 0)
    for key, fields in (("roc", (("x", 0, 1), ("y", 0, 1))), ("importances", (("importance", 0, 100),))):
        values = data.get(key)
        if not isinstance(values, list) or not values or any(not isinstance(v, dict) for v in values):
            raise ValueError(f"{key}がありません。")
        for value in values:
            for field, lower, upper in fields:
                require_number(value.get(field), f"{key}.{field}", lower, upper)
            if key == "importances" and not isinstance(value.get("factor"), str):
                raise ValueError("特徴量名がありません。")
    layers = data.get("layers")
    required = {"hillshade", "s2_rgb", "slope", "tpi", "curvature", "barerock", "miura_geology", "insar_creep", "alos2_lband", "mswing", "dndvi", "hazard_zones", "prob", "highrisk", "hidden_risk"}
    if not isinstance(layers, dict) or not required <= layers.keys():
        raise ValueError("必須地図レイヤーが不足しています。")
    for name, value in layers.items():
        if not isinstance(value, str) or not value:
            raise ValueError(f"レイヤー{name}の参照がありません。")
        if root is not None:
            base = Path(root).resolve()
            path = (base / value).resolve()
            if not path.is_relative_to(base) or path.suffix != ".webp" or not path.is_file():
                raise ValueError(f"レイヤー{name}の画像参照が不正です。")
            with path.open("rb") as f:
                header = f.read(12)
            if header[:4] != b"RIFF" or header[8:12] != b"WEBP" or path.stat().st_size <= 12:
                raise ValueError(f"レイヤー{name}の画像が不正です。")


def main():
    parser = argparse.ArgumentParser(description="地図の時系列・SAR観測一覧が欠落していないか検証します。")
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    source = args.path.read_text(encoding="utf-8")
    prefix = "window.EXTERNAL_DASHBOARD_DATA ="
    if not source.startswith(prefix):
        raise ValueError("想定したdata.js形式ではありません。")
    data = json.loads(source[len(prefix):].strip().removesuffix(";"))
    validate_dashboard_data(data, args.path.parent)
    print("OK: 時系列・SAR・地図グリッド・地区・事案・画像参照")


if __name__ == "__main__":
    main()
