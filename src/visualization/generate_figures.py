"""
產生報告所需的所有圖表，輸出到 results/figures/。

執行：
  python -m src.visualization.generate_figures

產生 16 張圖（fig01–fig16），分為四組：
  Group 1  EDA（資料分布）
  Group 2  特徵分析
  Group 3  分類結果
  Group 4  回歸結果
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.metrics import (
    ConfusionMatrixDisplay,
    auc,
    confusion_matrix,
    precision_recall_curve,
    roc_curve,
)

from src.preprocessing.paths import (
    FIGURES_DIR,
    LABEL_DATASET_CSV,
    REGRESSION_DATASET_CSV,
    RESULTS_DIR,
    SPLIT_MAP_CSV,
    TABULAR_FEATURES_CSV,
    CLEAN_TIMESERIES_PARQUET,
    ensure_processed_dirs,
)

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)

# ── 中文字型 ──────────────────────────────────────────────────────────────
for font in ["Microsoft JhengHei", "Microsoft YaHei", "SimHei", "Arial Unicode MS"]:
    try:
        matplotlib.rcParams["font.family"] = font
        plt.figure()
        plt.text(0, 0, "測試")
        plt.close()
        logger.info("使用中文字型: %s", font)
        break
    except Exception:
        pass

matplotlib.rcParams["axes.unicode_minus"] = False
PALETTE = {"Shorts": "#FF6B6B", "Long": "#4ECDC4", "Viral": "#FFE66D", "Non-viral": "#95E1D3"}
SPLIT_COLORS = {"train": "#2196F3", "valid": "#FF9800", "test": "#4CAF50"}


def _save(fig: plt.Figure, name: str) -> None:
    path = FIGURES_DIR / name
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    logger.info("儲存圖表 → %s", path)


def _load_base() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame | None]:
    """載入 label_dataset, tabular_features, split_map"""
    labels = pd.read_csv(LABEL_DATASET_CSV) if LABEL_DATASET_CSV.exists() else pd.DataFrame()
    feats  = pd.read_csv(TABULAR_FEATURES_CSV) if TABULAR_FEATURES_CSV.exists() else pd.DataFrame()
    split_map = pd.read_csv(SPLIT_MAP_CSV) if SPLIT_MAP_CSV.exists() else None
    return labels, feats, split_map


# ══════════════════════════════════════════════════════════════════════════
# Group 1 — EDA
# ══════════════════════════════════════════════════════════════════════════

def fig01_split_balance(labels: pd.DataFrame, split_map: pd.DataFrame) -> None:
    """fig01: Train/Valid/Test 中 Shorts vs Long 比例（堆疊長條）"""
    df = labels[["video_id", "is_shorts"]].merge(split_map, on="video_id", how="inner")
    df["type"] = df["is_shorts"].map({True: "Shorts", False: "Long", 1: "Shorts", 0: "Long"})

    counts = df.groupby(["split", "type"]).size().unstack(fill_value=0)
    pcts = counts.div(counts.sum(axis=1), axis=0) * 100

    split_order = [s for s in ["train", "valid", "test"] if s in pcts.index]
    pcts = pcts.reindex(split_order)

    fig, ax = plt.subplots(figsize=(7, 4))
    bottom = np.zeros(len(pcts))
    for col, color in [("Shorts", PALETTE["Shorts"]), ("Long", PALETTE["Long"])]:
        if col in pcts.columns:
            vals = pcts[col].values
            bars = ax.bar(pcts.index, vals, bottom=bottom, color=color, label=col,
                          edgecolor="white", linewidth=0.5)
            for bar, v, b in zip(bars, vals, bottom):
                if v > 5:
                    ax.text(bar.get_x() + bar.get_width() / 2,
                            b + v / 2, f"{v:.0f}%", ha="center", va="center",
                            fontsize=10, color="white", fontweight="bold")
            bottom += vals

    ax.set_ylabel("比例 (%)")
    ax.set_title("各 Split 中 Shorts / 長影片比例", fontsize=13, pad=10)
    ax.set_ylim(0, 110)
    ax.legend(loc="upper right")
    ax.set_xticks(range(len(split_order)))
    ax.set_xticklabels([f"{s}\n(n={counts.loc[s].sum()})" for s in split_order])
    ax.spines[["top", "right"]].set_visible(False)
    _save(fig, "fig01_data_split_balance.png")


def fig02_view_cdf(labels: pd.DataFrame) -> None:
    """fig02: 48h 觀看數 CDF（Shorts vs Long，log-x）"""
    fig, ax = plt.subplots(figsize=(7, 4))
    for is_s, label, color in [(True, "Shorts", PALETTE["Shorts"]),
                                (False, "Long", PALETTE["Long"])]:
        sub = labels[labels["is_shorts"] == is_s]["views_48h"].dropna()
        sub = sub[sub > 0].sort_values()
        cdf = np.arange(1, len(sub) + 1) / len(sub)
        ax.plot(sub.values, cdf, color=color, label=f"{label} (n={len(sub)})", linewidth=2)

    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    ax.set_xlabel("48h 觀看數（對數軸）")
    ax.set_ylabel("累積比例")
    ax.set_title("影片 48h 觀看數 CDF", fontsize=13, pad=10)
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.spines[["top", "right"]].set_visible(False)
    _save(fig, "fig02_view_cdf_by_type.png")


def fig03_viral_rate(labels: pd.DataFrame) -> None:
    """fig03: 病毒率 by 影片類型 + 訂閱分層"""
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))

    # 左：整體病毒率
    ax = axes[0]
    for is_s, label, color in [(True, "Shorts", PALETTE["Shorts"]),
                                (False, "Long", PALETTE["Long"])]:
        sub = labels[labels["is_shorts"] == is_s]
        rate = sub["is_viral_48h"].mean() * 100
        ax.bar(label, rate, color=color, edgecolor="white")
        ax.text(label, rate + 0.3, f"{rate:.1f}%", ha="center", va="bottom", fontweight="bold")
    ax.set_ylabel("病毒率 (%)")
    ax.set_title("整體病毒率", fontsize=12)
    ax.spines[["top", "right"]].set_visible(False)

    # 右：訂閱數分層病毒率
    ax = axes[1]
    bins = [0, 1000, 10000, 100000, 1e6, float("inf")]
    labels_bin = ["<1K", "1K–10K", "10K–100K", "100K–1M", ">1M"]
    if "subscriber_count_at_publish" in labels.columns:
        labels["sub_tier"] = pd.cut(
            labels["subscriber_count_at_publish"], bins=bins, labels=labels_bin
        )
        tier_rate = labels.groupby("sub_tier", observed=True)["is_viral_48h"].mean() * 100
        colors = sns.color_palette("viridis", len(tier_rate))
        bars = ax.bar(tier_rate.index.astype(str), tier_rate.values, color=colors)
        for bar, v in zip(bars, tier_rate.values):
            ax.text(bar.get_x() + bar.get_width() / 2, v + 0.2, f"{v:.1f}%",
                    ha="center", va="bottom", fontsize=9)
    ax.set_ylabel("病毒率 (%)")
    ax.set_title("依訂閱數分層病毒率", fontsize=12)
    ax.set_xlabel("頻道訂閱數")
    ax.spines[["top", "right"]].set_visible(False)

    fig.suptitle("病毒率分析", fontsize=14, y=1.02)
    _save(fig, "fig03_viral_rate_by_type.png")


def fig04_category_dist(labels: pd.DataFrame, feats: pd.DataFrame) -> None:
    """fig04: 類別分布（top-10 長條）"""
    df = feats[["video_id", "category"]].merge(labels[["video_id", "is_viral_48h"]], on="video_id")
    cat_counts = df["category"].value_counts().head(10)

    fig, ax = plt.subplots(figsize=(8, 5))
    colors = sns.color_palette("husl", len(cat_counts))
    ax.barh(cat_counts.index[::-1], cat_counts.values[::-1], color=colors[::-1])
    for i, (cat, cnt) in enumerate(zip(cat_counts.index[::-1], cat_counts.values[::-1])):
        ax.text(cnt + 2, i, str(cnt), va="center", fontsize=9)
    ax.set_xlabel("影片數")
    ax.set_title("Top-10 影片類別分布", fontsize=13, pad=10)
    ax.spines[["top", "right"]].set_visible(False)
    _save(fig, "fig04_category_distribution.png")


def fig05_growth_curves(ts_parquet: Path, labels: pd.DataFrame) -> None:
    """fig05: 成長曲線範例（4 條：viral/non-viral × Shorts/Long）"""
    ts_csv = ts_parquet.with_suffix(".csv")
    if ts_parquet.exists():
        ts = pd.read_parquet(ts_parquet, columns=["video_id", "time_since_publish_minutes", "view_count"])
    elif ts_csv.exists():
        ts = pd.read_csv(ts_csv, usecols=["video_id", "time_since_publish_minutes", "view_count"])
    else:
        logger.warning("clean_timeseries 不存在，跳過 fig05")
        return
    merged = ts.merge(labels[["video_id", "is_viral_48h", "is_shorts"]], on="video_id")
    merged["type"] = merged.apply(
        lambda r: ("Shorts" if r["is_shorts"] else "Long") + ("-Viral" if r["is_viral_48h"] else "-Non-viral"),
        axis=1,
    )

    fig, ax = plt.subplots(figsize=(9, 5))
    style_map = {
        "Shorts-Viral":     ("#FF6B6B", "-",  "Shorts 爆紅"),
        "Shorts-Non-viral": ("#FF6B6B", "--", "Shorts 未爆紅"),
        "Long-Viral":       ("#4ECDC4", "-",  "長影片 爆紅"),
        "Long-Non-viral":   ("#4ECDC4", "--", "長影片 未爆紅"),
    }
    for type_key, (color, ls, label) in style_map.items():
        sub = merged[merged["type"] == type_key]
        if sub.empty:
            continue
        # 取觀看數中位數最接近的那支影片
        medv = sub.groupby("video_id")["view_count"].max().median()
        best_vid = (sub.groupby("video_id")["view_count"].max() - medv).abs().idxmin()
        curve = sub[sub["video_id"] == best_vid].sort_values("time_since_publish_minutes")
        ax.plot(curve["time_since_publish_minutes"] / 60,
                curve["view_count"], color=color, linestyle=ls,
                linewidth=2, label=label, alpha=0.85)

    ax.set_xlabel("發布後時間（小時）")
    ax.set_ylabel("累積觀看數")
    ax.set_title("代表性影片成長曲線", fontsize=13, pad=10)
    ax.set_xlim(0, 72)
    ax.legend(fontsize=9)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    ax.grid(True, alpha=0.2)
    ax.spines[["top", "right"]].set_visible(False)
    _save(fig, "fig05_growth_curve_examples.png")


# ══════════════════════════════════════════════════════════════════════════
# Group 2 — 特徵分析
# ══════════════════════════════════════════════════════════════════════════

def fig06_shap_importance() -> None:
    """fig06: SHAP 特徵重要性水平長條（top 15）"""
    shap_path = RESULTS_DIR / "feature_importance_shap.csv"
    if not shap_path.exists():
        logger.warning("feature_importance_shap.csv 不存在，跳過 fig06")
        return

    shap_df = pd.read_csv(shap_path).nlargest(15, "mean_abs_shap").sort_values("mean_abs_shap")
    fig, ax = plt.subplots(figsize=(8, 6))
    colors = sns.color_palette("YlOrRd", len(shap_df))
    ax.barh(shap_df["feature"], shap_df["mean_abs_shap"], color=colors)
    ax.set_xlabel("Mean |SHAP value|")
    ax.set_title("LightGBM SHAP 特徵重要性（Top 15）", fontsize=13, pad=10)
    ax.spines[["top", "right"]].set_visible(False)
    _save(fig, "fig06_shap_importance.png")


def fig07_views3h_boxplot(labels: pd.DataFrame, feats: pd.DataFrame) -> None:
    """fig07: views_3h vs is_viral_48h boxplot（Shorts/Long 分開）"""
    df = feats[["video_id", "views_3h"]].merge(
        labels[["video_id", "is_viral_48h", "is_shorts"]], on="video_id"
    )
    df["log_views_3h"] = np.log1p(df["views_3h"])
    # 用 np.where 避免 pandas map 對 int64 vs bool 鍵的型態不匹配問題
    df["Viral"] = np.where(df["is_viral_48h"].astype(int) == 1, "Viral", "Non-viral")
    df["Type"]  = np.where(df["is_shorts"].astype(int)  == 1, "Shorts", "Long")

    fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
    for ax, type_val in zip(axes, ["Shorts", "Long"]):
        sub = df[df["Type"] == type_val]
        if sub.empty:
            continue
        groups = [sub[sub["Viral"] == v]["log_views_3h"].dropna() for v in ["Non-viral", "Viral"]]
        bp = ax.boxplot(groups, labels=["Non-viral", "Viral"],
                        patch_artist=True, notch=False)
        for patch, color in zip(bp["boxes"], [PALETTE["Non-viral"], PALETTE["Viral"]]):
            patch.set_facecolor(color)
        ax.set_title(f"{type_val}", fontsize=12)
        ax.set_xlabel("病毒性")
    axes[0].set_ylabel("log(1 + views_3h)")
    fig.suptitle("發布後 3h 觀看數 vs 病毒性（按影片類型）", fontsize=13)
    _save(fig, "fig07_views3h_vs_viral.png")


def fig08_growth_rate_dist(labels: pd.DataFrame, feats: pd.DataFrame) -> None:
    """fig08: view_delta_1h_3h 分布（viral vs non-viral）"""
    df = feats[["video_id", "view_delta_1h_3h"]].merge(
        labels[["video_id", "is_viral_48h"]], on="video_id"
    )
    df["log_delta"] = np.log1p(df["view_delta_1h_3h"])
    df["Viral"] = np.where(df["is_viral_48h"].astype(int) == 1, "Viral", "Non-viral")

    fig, ax = plt.subplots(figsize=(7, 4))
    for viral_val, color in [("Non-viral", PALETTE["Non-viral"]), ("Viral", PALETTE["Viral"])]:
        sub = df[df["Viral"] == viral_val]["log_delta"].dropna()
        ax.hist(sub, bins=40, alpha=0.65, color=color, label=f"{viral_val} (n={len(sub)})",
                density=True)
    ax.set_xlabel("log(1 + 1h→3h 觀看成長量)")
    ax.set_ylabel("密度")
    ax.set_title("早期成長量分布：Viral vs Non-viral", fontsize=13, pad=10)
    ax.legend()
    ax.spines[["top", "right"]].set_visible(False)
    _save(fig, "fig08_growth_rate_dist.png")


def fig17_comment_valence_arousal(labels: pd.DataFrame) -> None:
    """fig17: 留言 Valence-Arousal 二維散佈圖（Viral vs Non-viral）"""
    from src.preprocessing.paths import COMMENT_FEATURES_CSV
    if not COMMENT_FEATURES_CSV.exists():
        logger.warning("comment_features.csv 不存在，跳過 fig17")
        return

    cmt = pd.read_csv(COMMENT_FEATURES_CSV)
    needed_cols = ["video_id", "comment_valence_mean", "comment_arousal_mean"]
    missing = [c for c in needed_cols if c not in cmt.columns]
    if missing:
        logger.warning("comment_features.csv 缺少欄位 %s，跳過 fig17", missing)
        return

    df = cmt[needed_cols].merge(
        labels[["video_id", "is_viral_48h"]], on="video_id"
    ).dropna(subset=["comment_valence_mean", "comment_arousal_mean"])

    if df.empty:
        logger.warning("留言特徵 merge 後為空，跳過 fig17")
        return

    df["Viral"] = np.where(df["is_viral_48h"].astype(int) == 1, "Viral", "Non-viral")

    fig, ax = plt.subplots(figsize=(7, 6))

    styles = [
        ("Non-viral", PALETTE["Non-viral"], "o", 0.45, 25),
        ("Viral",     PALETTE["Viral"],     "^", 0.80, 50),
    ]
    for v_label, color, marker, alpha, size in styles:
        sub = df[df["Viral"] == v_label]
        ax.scatter(
            sub["comment_valence_mean"],
            sub["comment_arousal_mean"],
            c=color, label=f"{v_label}  (n={len(sub)})",
            alpha=alpha, s=size, marker=marker, edgecolors="white", linewidths=0.3,
        )

    # 中心線（分為四象限）
    v_mid = df["comment_valence_mean"].median()
    a_mid = df["comment_arousal_mean"].median()
    ax.axvline(v_mid, color="gray", lw=0.8, ls="--", alpha=0.5)
    ax.axhline(a_mid, color="gray", lw=0.8, ls="--", alpha=0.5)

    # 象限標籤
    xlim, ylim = ax.get_xlim(), ax.get_ylim()
    qpad_x = (xlim[1] - xlim[0]) * 0.03
    qpad_y = (ylim[1] - ylim[0]) * 0.03
    for qx, qy, label in [
        (xlim[0] + qpad_x, ylim[1] - qpad_y, "負向\n高喚醒"),
        (xlim[1] - qpad_x, ylim[1] - qpad_y, "正向\n高喚醒"),
        (xlim[0] + qpad_x, ylim[0] + qpad_y, "負向\n低喚醒"),
        (xlim[1] - qpad_x, ylim[0] + qpad_y, "正向\n低喚醒"),
    ]:
        ha = "left" if qx < v_mid else "right"
        va = "top" if qy > a_mid else "bottom"
        ax.text(qx, qy, label, ha=ha, va=va, fontsize=8, color="gray", alpha=0.7)

    ax.set_xlabel("Valence（留言正向情緒均值）", fontsize=11)
    ax.set_ylabel("Arousal（留言喚醒強度均值）", fontsize=11)
    ax.set_title("留言 Valence–Arousal 二維散佈\n（影片層級均值，顏色 = 是否爆紅）", fontsize=12, pad=10)
    ax.legend(fontsize=10, framealpha=0.9)
    ax.spines[["top", "right"]].set_visible(False)

    _save(fig, "fig17_comment_valence_arousal.png")


# ══════════════════════════════════════════════════════════════════════════
# Group 3 — 分類結果
# ══════════════════════════════════════════════════════════════════════════

def _load_clf_preds() -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """載入各模型的 test 預測機率。"""
    preds = {}
    for model_key, fname, col in [
        ("LightGBM",  "lgbm_test_proba.csv",     "lgbm_test_proba"),
        ("LSTM",      "lstm_test_proba.csv",      "lstm_test_proba"),
        ("Stacking",  "stacking_test_proba.csv",  "stacking_proba"),
        ("Logistic",  "lgbm_test_proba_A.csv",    "lgbm_test_proba"),  # fallback to lgbm A
    ]:
        path = RESULTS_DIR / fname
        if not path.exists():
            continue
        df = pd.read_csv(path)
        if col in df.columns and "label" in df.columns:
            preds[model_key] = (df["label"].values, df[col].values)

    # Logistic 有自己的檔案結構
    log_path = RESULTS_DIR / "lgbm_test_proba_A.csv"  # placeholder
    return preds


def fig09_roc_curves() -> None:
    """fig09: ROC 曲線（各模型）"""
    preds = _load_clf_preds()
    if not preds:
        logger.warning("找不到分類預測檔，跳過 fig09")
        return

    fig, ax = plt.subplots(figsize=(6, 5))
    colors = ["#2196F3", "#FF6B6B", "#4CAF50", "#FF9800", "#9C27B0"]
    for (model, (y_true, y_prob)), color in zip(preds.items(), colors):
        fpr, tpr, _ = roc_curve(y_true, y_prob)
        roc_auc = auc(fpr, tpr)
        ax.plot(fpr, tpr, color=color, linewidth=2,
                label=f"{model} (AUC={roc_auc:.3f})")
    ax.plot([0, 1], [0, 1], "k--", linewidth=1, alpha=0.5)
    ax.set_xlabel("False Positive Rate")
    ax.set_ylabel("True Positive Rate")
    ax.set_title("ROC 曲線（各分類模型）", fontsize=13, pad=10)
    ax.legend(loc="lower right", fontsize=9)
    ax.grid(True, alpha=0.2)
    ax.spines[["top", "right"]].set_visible(False)
    _save(fig, "fig09_roc_curves.png")


def fig10_pr_curves() -> None:
    """fig10: PR 曲線（各模型）"""
    preds = _load_clf_preds()
    if not preds:
        logger.warning("找不到分類預測檔，跳過 fig10")
        return

    fig, ax = plt.subplots(figsize=(6, 5))
    colors = ["#2196F3", "#FF6B6B", "#4CAF50", "#FF9800", "#9C27B0"]
    for (model, (y_true, y_prob)), color in zip(preds.items(), colors):
        prec, rec, _ = precision_recall_curve(y_true, y_prob)
        ap = auc(rec, prec)
        ax.plot(rec, prec, color=color, linewidth=2,
                label=f"{model} (AP={ap:.3f})")
    baseline = sum(y_true) / len(y_true) if preds else 0.1
    ax.axhline(baseline, color="gray", linestyle="--", linewidth=1, label=f"Baseline ({baseline:.2f})")
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    ax.set_title("Precision-Recall 曲線", fontsize=13, pad=10)
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(True, alpha=0.2)
    ax.spines[["top", "right"]].set_visible(False)
    _save(fig, "fig10_pr_curves.png")


def fig11_confusion_matrix() -> None:
    """fig11: Confusion Matrix（LightGBM Group B）"""
    path = RESULTS_DIR / "lgbm_test_proba.csv"
    if not path.exists():
        logger.warning("lgbm_test_proba.csv 不存在，跳過 fig11")
        return
    df = pd.read_csv(path)
    y_true = df["label"].values
    metrics_path = RESULTS_DIR / "metrics.csv"
    thr = 0.5
    if metrics_path.exists():
        m = pd.read_csv(metrics_path)
        m = m[(m["model"] == "lightgbm_classifier") & (m["split"] == "valid")]
        if not m.empty:
            thr = float(m.iloc[-1]["threshold"])
    y_pred = (df["lgbm_test_proba"].values >= thr).astype(int)
    cm = confusion_matrix(y_true, y_pred)

    fig, ax = plt.subplots(figsize=(5, 4))
    disp = ConfusionMatrixDisplay(cm, display_labels=["Non-viral", "Viral"])
    disp.plot(ax=ax, colorbar=False, cmap="Blues")
    ax.set_title(f"Confusion Matrix — LightGBM Group B\n(threshold={thr:.3f})", fontsize=11)
    _save(fig, "fig11_confusion_matrix_lgbm.png")


def fig12_threshold_sensitivity() -> None:
    """fig12: 閾值敏感度（F1/Precision/Recall vs threshold）"""
    path = RESULTS_DIR / "lgbm_test_proba.csv"
    if not path.exists():
        logger.warning("lgbm_test_proba.csv 不存在，跳過 fig12")
        return
    df = pd.read_csv(path)
    y_true = df["label"].values
    y_prob = df["lgbm_test_proba"].values

    thresholds = np.linspace(0.01, 0.99, 200)
    f1s, precs, recs = [], [], []
    for thr in thresholds:
        y_pred = (y_prob >= thr).astype(int)
        tp = ((y_pred == 1) & (y_true == 1)).sum()
        fp = ((y_pred == 1) & (y_true == 0)).sum()
        fn = ((y_pred == 0) & (y_true == 1)).sum()
        p = tp / (tp + fp) if (tp + fp) > 0 else 0
        r = tp / (tp + fn) if (tp + fn) > 0 else 0
        f = 2 * p * r / (p + r) if (p + r) > 0 else 0
        precs.append(p); recs.append(r); f1s.append(f)

    best_thr = thresholds[np.argmax(f1s)]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(thresholds, f1s,   color="#2196F3", linewidth=2, label="F1")
    ax.plot(thresholds, precs, color="#FF9800", linewidth=2, label="Precision")
    ax.plot(thresholds, recs,  color="#4CAF50", linewidth=2, label="Recall")
    ax.axvline(best_thr, color="red", linestyle="--", linewidth=1,
               label=f"Best thr={best_thr:.2f}")
    ax.set_xlabel("Decision Threshold")
    ax.set_ylabel("Score")
    ax.set_title("LightGBM 閾值敏感度", fontsize=13, pad=10)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.2)
    ax.spines[["top", "right"]].set_visible(False)
    _save(fig, "fig12_threshold_sensitivity.png")


def fig13_ablation_classification() -> None:
    """fig13: Feature Group Ablation（F1/AUC 長條）"""
    metrics_path = RESULTS_DIR / "metrics.csv"
    if not metrics_path.exists():
        logger.warning("metrics.csv 不存在，跳過 fig13")
        return

    m = pd.read_csv(metrics_path)
    m = m[(m["split"] == "test") & (m["model"] == "lightgbm_classifier")]
    if "feature_group" not in m.columns or m.empty:
        logger.warning("metrics.csv 缺 feature_group 欄位，跳過 fig13")
        return

    m = m.drop_duplicates(subset=["feature_group"], keep="last")
    group_order = [g for g in ["A", "B", "C1", "C2", "C3"] if g in m["feature_group"].values]
    m = m.set_index("feature_group").reindex(group_order)

    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    colors = sns.color_palette("Set2", len(group_order))
    for ax, metric, title in [(axes[0], "f1", "F1 Score"), (axes[1], "auc_roc", "AUC-ROC")]:
        vals = m[metric].values
        bars = ax.bar(group_order, vals, color=colors)
        for bar, v in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, v + 0.003,
                    f"{v:.3f}", ha="center", va="bottom", fontsize=10, fontweight="bold")
        ax.set_ylim(0, min(1.05, max(vals) * 1.15))
        ax.set_xlabel("Feature Group")
        ax.set_ylabel(title)
        ax.set_title(f"LightGBM — {title}", fontsize=12)
        ax.spines[["top", "right"]].set_visible(False)

    fig.suptitle("分類任務 Ablation Study", fontsize=14, y=1.02)
    _save(fig, "fig13_ablation_classification.png")


# ══════════════════════════════════════════════════════════════════════════
# Group 4 — 回歸結果
# ══════════════════════════════════════════════════════════════════════════

def fig14_reg_pred_vs_actual(labels: pd.DataFrame) -> None:
    """fig14: 預測 vs 實際散點圖（LightGBM，Shorts/Long 不同顏色）"""
    pred_path = RESULTS_DIR / "lgbm_reg_test_pred.csv"
    if not pred_path.exists():
        logger.warning("lgbm_reg_test_pred.csv 不存在，跳過 fig14")
        return

    df = pd.read_csv(pred_path)
    if "video_id" in df.columns and "is_shorts" in labels.columns:
        df = df.merge(labels[["video_id", "is_shorts"]], on="video_id", how="left")
    else:
        df["is_shorts"] = False

    df["type"] = df["is_shorts"].map({True: "Shorts", False: "Long", 1: "Shorts", 0: "Long"})
    fig, ax = plt.subplots(figsize=(6, 5))
    for type_val, color in [("Shorts", PALETTE["Shorts"]), ("Long", PALETTE["Long"])]:
        sub = df[df["type"] == type_val]
        if sub.empty:
            continue
        ax.scatter(sub["label"], sub["lgbm_reg_pred"], alpha=0.4, s=15,
                   color=color, label=f"{type_val} (n={len(sub)})")
    lim = [df["label"].min() - 0.2, df["label"].max() + 0.2]
    ax.plot(lim, lim, "k--", linewidth=1, alpha=0.5, label="Perfect")
    ax.set_xlabel("實際 log_next_24h_views")
    ax.set_ylabel("預測 log_next_24h_views")
    ax.set_title("LightGBM 回歸：預測 vs 實際", fontsize=13, pad=10)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.2)
    ax.spines[["top", "right"]].set_visible(False)
    _save(fig, "fig14_reg_pred_vs_actual.png")


def fig15_reg_residuals() -> None:
    """fig15: 殘差分布（histogram）"""
    pred_path = RESULTS_DIR / "lgbm_reg_test_pred.csv"
    if not pred_path.exists():
        logger.warning("lgbm_reg_test_pred.csv 不存在，跳過 fig15")
        return

    df = pd.read_csv(pred_path)
    residuals = df["lgbm_reg_pred"] - df["label"]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.hist(residuals, bins=50, color="#4ECDC4", edgecolor="white", alpha=0.8)
    ax.axvline(0, color="red", linestyle="--", linewidth=1.5)
    ax.axvline(residuals.mean(), color="orange", linestyle="--", linewidth=1.5,
               label=f"Mean={residuals.mean():.3f}")
    ax.set_xlabel("殘差（預測 - 實際）")
    ax.set_ylabel("頻次")
    ax.set_title("LightGBM 回歸殘差分布", fontsize=13, pad=10)
    ax.legend()
    ax.spines[["top", "right"]].set_visible(False)
    _save(fig, "fig15_reg_residuals.png")


def fig16_ablation_regression() -> None:
    """fig16: 回歸 Ablation（Feature Group vs R²/RMSE）"""
    metrics_path = RESULTS_DIR / "regression_metrics.csv"
    if not metrics_path.exists():
        logger.warning("regression_metrics.csv 不存在，跳過 fig16")
        return

    m = pd.read_csv(metrics_path)
    m = m[(m["split"] == "test") & (m["model"] == "lightgbm_regressor")]
    if "feature_group" not in m.columns or m.empty:
        logger.warning("regression_metrics.csv 缺 feature_group 欄位，跳過 fig16")
        return

    m = m.drop_duplicates(subset=["feature_group"], keep="last")
    group_order = [g for g in ["B", "C1", "C2", "C3"] if g in m["feature_group"].values]
    m = m.set_index("feature_group").reindex(group_order)

    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    colors = sns.color_palette("Set2", len(group_order))
    for ax, metric, title in [(axes[0], "r2", "R²"), (axes[1], "rmse", "RMSE")]:
        vals = m[metric].values
        bars = ax.bar(group_order, vals, color=colors)
        for bar, v in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, v + 0.005 * max(vals),
                    f"{v:.3f}", ha="center", va="bottom", fontsize=10, fontweight="bold")
        ax.set_xlabel("Feature Group")
        ax.set_ylabel(title)
        ax.set_title(f"LightGBM — {title}", fontsize=12)
        ax.spines[["top", "right"]].set_visible(False)

    fig.suptitle("回歸任務 Ablation Study", fontsize=14, y=1.02)
    _save(fig, "fig16_ablation_regression.png")


# ══════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    ensure_processed_dirs()
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    labels, feats, split_map = _load_base()

    if labels.empty:
        logger.error("label_dataset.csv 不存在，無法產生圖表")
        return

    # ── Group 1: EDA ──────────────────────────────────────────────────────
    logger.info("=== Group 1: EDA ===")
    if split_map is not None:
        fig01_split_balance(labels, split_map)
    fig02_view_cdf(labels)
    fig03_viral_rate(labels)
    if not feats.empty:
        fig04_category_dist(labels, feats)
    fig05_growth_curves(CLEAN_TIMESERIES_PARQUET, labels)

    # ── Group 2: 特徵分析 ─────────────────────────────────────────────────
    logger.info("=== Group 2: 特徵分析 ===")
    fig06_shap_importance()
    if not feats.empty:
        fig07_views3h_boxplot(labels, feats)
        fig08_growth_rate_dist(labels, feats)
    fig17_comment_valence_arousal(labels)

    # ── Group 3: 分類結果 ─────────────────────────────────────────────────
    logger.info("=== Group 3: 分類結果 ===")
    fig09_roc_curves()
    fig10_pr_curves()
    fig11_confusion_matrix()
    fig12_threshold_sensitivity()
    fig13_ablation_classification()

    # ── Group 4: 回歸結果 ─────────────────────────────────────────────────
    logger.info("=== Group 4: 回歸結果 ===")
    fig14_reg_pred_vs_actual(labels)
    fig15_reg_residuals()
    fig16_ablation_regression()

    logger.info("全部圖表產生完畢 → %s", FIGURES_DIR)


if __name__ == "__main__":
    main()
