from dataclasses import dataclass, field

import pandas as pd


@dataclass
class CsvProfile:
    path: str
    n_rows: int
    n_cols: int
    columns: list[str]
    dtypes: dict[str, str]
    null_counts: dict[str, int]
    sample_rows: list[dict[str, object]]
    numeric_summary: dict[str, dict[str, float]] = field(default_factory=dict)

    def to_prompt_text(self, max_sample_rows: int = 8) -> str:
        """Return a compact profile; raw CSV contents are never placed in full context."""
        lines = [
            f"CSV file: {self.path}",
            f"Shape: {self.n_rows} rows x {self.n_cols} columns",
            "Columns (name: dtype, nulls):",
        ]
        for column in self.columns:
            lines.append(
                f"  - {column}: {self.dtypes[column]}, {self.null_counts[column]} nulls"
            )

        if self.numeric_summary:
            lines.append("Numeric column summary (min/mean/max):")
            for column, stats in self.numeric_summary.items():
                lines.append(
                    f"  - {column}: min={stats['min']:.2f}, "
                    f"mean={stats['mean']:.2f}, max={stats['max']:.2f}"
                )

        selected_rows = self.sample_rows[:max_sample_rows]
        lines.append(f"Sample rows (first {len(selected_rows)}):")
        for row in selected_rows:
            # A single unusually long cell should not consume the prompt budget.
            lines.append(f"  {str(row)[:500]}")
        return "\n".join(lines)


def profile_csv(path: str, sample_rows: int = 10) -> CsvProfile:
    frame = pd.read_csv(path)
    dtypes = {column: str(dtype) for column, dtype in frame.dtypes.items()}
    null_counts = {column: int(frame[column].isna().sum()) for column in frame.columns}

    numeric_summary: dict[str, dict[str, float]] = {}
    for column in frame.select_dtypes(include="number").columns:
        series = frame[column].dropna()
        if not series.empty:
            numeric_summary[column] = {
                "min": float(series.min()),
                "mean": float(series.mean()),
                "max": float(series.max()),
            }

    return CsvProfile(
        path=path,
        n_rows=int(frame.shape[0]),
        n_cols=int(frame.shape[1]),
        columns=list(frame.columns),
        dtypes=dtypes,
        null_counts=null_counts,
        sample_rows=frame.head(sample_rows).to_dict(orient="records"),
        numeric_summary=numeric_summary,
    )
