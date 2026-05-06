"""
LAYER 6 — Data Validator & Merger
Validates all scraped CSVs, removes junk, deduplicates,
and merges interlinked data across sections.
Produces clean final CSVs ready for the dashboard.
All processing is local.
"""

import re
import pandas as pd
from pathlib import Path
from config import CSV_DIR, OUTPUT_DIR, log


FINAL_DIR = OUTPUT_DIR / "final"
FINAL_DIR.mkdir(exist_ok=True)


def is_junk_dataframe(df):
    """
    Returns True if a DataFrame is junk/useless.
    Junk = nav bars, footers, cookie banners etc.
    """
    if df is None or df.empty:
        return True

    if df.shape[0] < 2 or df.shape[1] < 2:
        return True

    total_cells = df.shape[0] * df.shape[1]
    empty_cells = df.isnull().sum().sum() + \
                  (df == '').sum().sum() + \
                  (df == 'nan').sum().sum()
    if empty_cells / total_cells > 0.8:
        return True

    if df.nunique().max() <= 1:
        return True

    return False


def clean_dataframe(df):
    """
    Clean a DataFrame:
    - Remove fully empty rows/columns
    - Strip whitespace from all string cells
    - Replace 'nan', 'None', 'NaN' strings with actual NaN
    - Remove duplicate rows
    - Fix column names
    """
    if df is None or df.empty:
        return df

    df = df.replace(['nan', 'None', 'NaN', 'N/A', 'n/a', '-', '--'],
                    pd.NA)

    for col in df.select_dtypes(include='object').columns:
        df[col] = df[col].astype(str).str.strip()
        df[col] = df[col].replace('nan', pd.NA)

    df = df.dropna(how='all').dropna(axis=1, how='all')

    df = df.drop_duplicates()

    df.columns = [
        str(c).strip().replace('\n', ' ').replace('\r', '')
        for c in df.columns
    ]

    df = df.loc[:, ~df.columns.str.match(r'^Unnamed')]

    df = df.reset_index(drop=True)
    return df


def validate_all_csvs():
    """
    Load, validate, and clean all scraped CSVs.
    Returns dict: {filename: cleaned_dataframe}
    """
    log("\nValidating all scraped CSV files...")
    csv_files = list(CSV_DIR.glob("*.csv"))
    valid = {}
    junk_count = 0

    for filepath in csv_files:
        try:
            df = pd.read_csv(filepath, encoding="utf-8-sig",
                             low_memory=False)

            if is_junk_dataframe(df):
                junk_count += 1
                log(f"  Junk removed: {filepath.name}", level="WARN")
                filepath.unlink()  # delete junk CSV
                continue

            cleaned = clean_dataframe(df)
            if not is_junk_dataframe(cleaned):
                valid[filepath.name] = cleaned
                log(f"  Valid: {filepath.name} "
                    f"({cleaned.shape[0]}r x {cleaned.shape[1]}c)")

        except Exception as e:
            log(f"  Could not read {filepath.name}: {e}", level="WARN")

    log(f"  Valid files: {len(valid)} | Junk removed: {junk_count}")
    return valid


def find_common_columns(df1, df2, min_overlap=1):
    """
    Find columns that exist in both DataFrames.
    Used to detect interlinked data.
    """
    cols1 = set(c.lower().strip() for c in df1.columns)
    cols2 = set(c.lower().strip() for c in df2.columns)
    common = cols1.intersection(cols2)
    return list(common) if len(common) >= min_overlap else []


def try_merge(df1, df2, common_cols):
    """
    Attempt to merge two DataFrames on common columns.
    Uses outer join to preserve all data.
    """
    try:
        merge_keys = []
        for col in common_cols:
            match1 = [c for c in df1.columns if c.lower().strip() == col]
            match2 = [c for c in df2.columns if c.lower().strip() == col]
            if match1 and match2:
                merge_keys.append((match1[0], match2[0]))

        if not merge_keys:
            return None

        left_key, right_key = merge_keys[0]

        df2_renamed = df2.rename(columns={right_key: left_key})

        merged = pd.merge(df1, df2_renamed,
                          on=left_key,
                          how='outer',
                          suffixes=('_section1', '_section2'))
        return merged

    except Exception as e:
        log(f"  Merge failed: {e}", level="WARN")
        return None


def group_by_section(valid_csvs):
    """
    Group CSVs by section based on filename patterns.
    Returns dict: {section_name: [dataframes]}
    """
    sections = {}
    for filename, df in valid_csvs.items():
        if "section1" in filename.lower() or "_s1_" in filename.lower():
            key = "section_1"
        elif "section2" in filename.lower() or "_s2_" in filename.lower():
            key = "section_2"
        elif filename.startswith("pdf_"):
            key = "pdf_data"
        elif filename.startswith("kpi"):
            key = "kpis"
        else:
            key = "general"

        if key not in sections:
            sections[key] = []
        sections[key].append((filename, df))

    return sections


def merge_section_data(section_dfs):
    """
    Merge all DataFrames within a section by concatenation
    (if same columns) or keep separate (if different columns).
    """
    if not section_dfs:
        return {}

    result = {}

    col_groups = {}
    for filename, df in section_dfs:
        col_sig = tuple(sorted(df.columns.tolist()))
        if col_sig not in col_groups:
            col_groups[col_sig] = []
        col_groups[col_sig].append(df)

    for i, (col_sig, dfs) in enumerate(col_groups.items()):
        if len(dfs) > 1:
            merged = pd.concat(dfs, ignore_index=True).drop_duplicates()
            result[f"merged_table_{i+1}"] = merged
            log(f"  Merged {len(dfs)} tables with same structure "
                f"→ {merged.shape[0]} total rows")
        else:
            result[f"table_{i+1}"] = dfs[0]

    return result


def save_final_csvs(final_data):
    """Save all final cleaned/merged DataFrames."""
    saved = []
    for name, df in final_data.items():
        if df is None or df.empty:
            continue
        filepath = FINAL_DIR / f"final_{name}.csv"
        df.to_csv(filepath, index=False, encoding="utf-8-sig")
        log(f"  Final saved: final_{name}.csv "
            f"({df.shape[0]} rows x {df.shape[1]} cols)")
        saved.append(str(filepath))
    return saved


def run_validation_and_merge():
    """
    Master function for Layer 6.
    Validates → Groups → Merges → Saves final clean CSVs.
    Returns dict of final DataFrames for dashboard use.
    """
    log("\n" + "="*50)
    log("LAYER 6: Validating and merging all data...")
    log("="*50)

    # Step 1 — Validate all CSVs
    valid_csvs = validate_all_csvs()
    if not valid_csvs:
        log("No valid data found to process", level="WARN")
        return {}

    # Step 2 — Group by section
    sections = group_by_section(valid_csvs)
    log(f"\nSections detected: {list(sections.keys())}")

    # Step 3 — Merge within each section
    all_final = {}
    for section_name, section_dfs in sections.items():
        log(f"\nProcessing section: {section_name}")
        merged = merge_section_data(section_dfs)
        for table_name, df in merged.items():
            key = f"{section_name}_{table_name}"
            all_final[key] = df

    # Step 4 — Try cross-section merge for interlinked data
    section_keys = [k for k in sections.keys()
                    if k.startswith("section_")]
    if len(section_keys) >= 2:
        log("\nChecking for interlinked data across sections...")
        s1_dfs = [df for _, df in sections.get("section_1", [])]
        s2_dfs = [df for _, df in sections.get("section_2", [])]

        for i, df1 in enumerate(s1_dfs):
            for j, df2 in enumerate(s2_dfs):
                common = find_common_columns(df1, df2)
                if common:
                    log(f"  Found common columns: {common}")
                    merged = try_merge(df1, df2, common)
                    if merged is not None and not merged.empty:
                        key = f"interlinked_s1t{i+1}_s2t{j+1}"
                        all_final[key] = merged
                        log(f"  Interlinked merge created: {key} "
                            f"({merged.shape[0]} rows)")

    # Step 5 — Save all final CSVs
    log("\nSaving final clean data...")
    save_final_csvs(all_final)

    log(f"\n✅ Layer 6 complete: {len(all_final)} final dataset(s) ready")
    log(f"   Location: {FINAL_DIR}")
    return all_final
