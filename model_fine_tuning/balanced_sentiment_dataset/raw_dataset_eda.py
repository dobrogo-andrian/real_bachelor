from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    default_input = script_dir / "balanced_dataset.csv"
    default_output_dir = script_dir / "eda_plots"

    parser = argparse.ArgumentParser(
        description="EDA for raw sentiment dataset and academic-quality plots generation."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=default_input,
        help=f"Path to CSV dataset (default: {default_input})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_output_dir,
        help=f"Directory to save .png plots (default: {default_output_dir})",
    )
    return parser.parse_args()


def format_stats(series: pd.Series) -> dict[str, float]:
    return {
        "mean": float(series.mean()),
        "median": float(series.median()),
        "min": float(series.min()),
        "max": float(series.max()),
        "p95": float(series.quantile(0.95)),
    }


def print_length_stats(title: str, stats: dict[str, float]) -> None:
    print(title)
    print(f"  Mean: {stats['mean']:.2f}")
    print(f"  Median: {stats['median']:.2f}")
    print(f"  Min: {stats['min']:.0f}")
    print(f"  Max: {stats['max']:.0f}")
    print(f"  95th percentile: {stats['p95']:.2f}")


def annotate_bars(ax: plt.Axes, values: pd.Series) -> None:
    ymax = values.max() if len(values) else 0
    offset = max(ymax * 0.01, 1)
    for patch, value in zip(ax.patches, values, strict=False):
        x = patch.get_x() + patch.get_width() / 2
        y = patch.get_height()
        ax.text(x, y + offset, f"{int(value)}", ha="center", va="bottom", fontsize=10)


def main() -> None:
    args = parse_args()

    input_path = args.input.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    df = pd.read_csv(input_path)
    required_cols = {"text", "label"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    if "source" not in df.columns:
        df["source"] = "unknown"
        print("WARNING: 'source' column was not found. Filled with 'unknown'.")

    sns.set_style("whitegrid")
    sns.set_context("talk")

    print("===== DATASET OVERVIEW =====")
    print(f"Rows: {len(df):,}")
    print(f"Columns: {len(df.columns):,}")
    print(f"Total NaN values: {int(df.isna().sum().sum()):,}")
    print("NaN by key columns:")
    print(f"  text: {int(df['text'].isna().sum()):,}")
    print(f"  label: {int(df['label'].isna().sum()):,}")
    print(f"  source: {int(df['source'].isna().sum()):,}")

    duplicate_text_count = int(df.duplicated(subset=["text"]).sum())
    print(f"Full duplicates by 'text': {duplicate_text_count:,}")

    print("\n===== LABEL DISTRIBUTION =====")
    label_counts = df["label"].value_counts(dropna=False).sort_index()
    label_perc = (label_counts / len(df) * 100).round(2)
    label_table = pd.DataFrame({"count": label_counts, "percent": label_perc})
    print(label_table.to_string())

    print("\n===== SOURCE DISTRIBUTION =====")
    source_counts = df["source"].value_counts(dropna=False)
    source_perc = (source_counts / len(df) * 100).round(2)
    source_table = pd.DataFrame({"count": source_counts, "percent": source_perc})
    print(source_table.to_string())

    clean_text = df["text"].fillna("").astype(str).str.strip()
    valid_mask = clean_text.ne("")
    valid_text = clean_text[valid_mask]
    dropped_for_length = int((~valid_mask).sum())

    text_len_chars = valid_text.str.len()
    text_len_words = valid_text.str.split().str.len()

    print("\n===== TEXT LENGTH STATS =====")
    print(f"Rows excluded from length stats (empty/NaN text): {dropped_for_length:,}")
    print_length_stats("Length in characters:", format_stats(text_len_chars))
    print_length_stats("Length in words:", format_stats(text_len_words))

    plot_df = df.loc[valid_mask & df["label"].notna(), ["label"]].copy()
    plot_df["word_len"] = text_len_words.reindex(plot_df.index)
    plot_df["label"] = pd.to_numeric(plot_df["label"], errors="coerce")
    plot_df = plot_df.dropna(subset=["label", "word_len"])
    plot_df["label"] = plot_df["label"].astype(int)

    class_counts = df["label"].value_counts().reindex([0, 1, 2], fill_value=0)
    fig, ax = plt.subplots(figsize=(8, 5))
    sns.barplot(x=class_counts.index, y=class_counts.values, color="#6baed6", ax=ax)
    annotate_bars(ax, class_counts)
    ax.set_title("Class Distribution (Label Counts)")
    ax.set_xlabel("Sentiment label (0=neg, 1=neu, 2=pos)")
    ax.set_ylabel("Number of records")
    fig.tight_layout()
    fig.savefig(output_dir / "01_class_distribution.png", dpi=300, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 6))
    sns.barplot(x=source_counts.index.astype(str), y=source_counts.values, color="#74c69d", ax=ax)
    annotate_bars(ax, source_counts)
    ax.set_title("Source Distribution")
    ax.set_xlabel("Source")
    ax.set_ylabel("Number of records")
    ax.tick_params(axis="x", rotation=25)
    fig.tight_layout()
    fig.savefig(output_dir / "02_source_distribution.png", dpi=300, bbox_inches="tight")
    plt.close(fig)

    p99 = float(text_len_words.quantile(0.99))
    words_for_hist = text_len_words[text_len_words <= p99]
    fig, ax = plt.subplots(figsize=(10, 6))
    sns.histplot(words_for_hist, bins=50, kde=True, color="#2a9d8f", ax=ax)
    ax.set_title("Text Length Distribution (Words, up to 99th percentile)")
    ax.set_xlabel("Text length in words")
    ax.set_ylabel("Frequency")
    ax.set_xlim(0, p99)
    fig.tight_layout()
    fig.savefig(output_dir / "03_text_length_distribution.png", dpi=300, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 6))
    sns.boxplot(data=plot_df, x="label", y="word_len", order=[0, 1, 2], color="#bde0fe", ax=ax)
    ax.set_title("Text Length by Sentiment Class")
    ax.set_xlabel("Sentiment label (0=neg, 1=neu, 2=pos)")
    ax.set_ylabel("Text length in words")
    fig.tight_layout()
    fig.savefig(output_dir / "04_length_by_sentiment_boxplot.png", dpi=300, bbox_inches="tight")
    plt.close(fig)

    print("\nPlots saved to:")
    for name in [
        "01_class_distribution.png",
        "02_source_distribution.png",
        "03_text_length_distribution.png",
        "04_length_by_sentiment_boxplot.png",
    ]:
        print(f"  - {output_dir / name}")


if __name__ == "__main__":
    main()
