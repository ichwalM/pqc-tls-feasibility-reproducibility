#!/usr/bin/env python3
"""
Uji statistik sesuai "PERSPEKTIF FINAL" §III -- TIGA interaksi dua-arah saja,
masing-masing terikat ke satu RQ/H. TIDAK ADA interaksi >=2 arah dan TIDAK ADA
interaksi dengan measurement_type (sesuai larangan eksplisit §III).

  1. tier x suite            -> H2  (subset: measurement_type == pure_handshake)
  2. concurrency x suite     -> H3  (subset: end_to_end, DI-STRATIFIKASI per tier,
                                     diuji dua kali: latency_ms mean DAN P95/P99)
  3. network x suite         -> H4  (subset: end_to_end SAJA, tidak pernah pure_handshake)

CATATAN INTERPRETASI (belum eksplisit dikonfirmasi di dokumen -- perlu masuk
decision log sebelum dianggap final):
  - H2 diisolasi ke pure_handshake supaya efek compute-tier murni tidak
    tercampur noise concurrency/jaringan.
  - H3 distratifikasi per tier (bukan satu model gabungan tiga tier) karena
    klaim H3 sendiri spesifik "di low-tier", dan model 3-arah dilarang §III.

Format wajib: F(df1,df2)=X.XX, p=0.XXX, eta^2=0.XX (Cohen: small/medium/large),
Tukey post-hoc kalau p<0.05.

Butuh: pip install pandas scipy statsmodels

Usage:
  python3 stats_tests.py --raw ../../data/raw/all_runs.csv
"""

import argparse

import pandas as pd
from scipy import stats

try:
    import statsmodels.api as sm  # noqa: F401  (dipakai implisit oleh formula api)
    import statsmodels.formula.api as smf
    from statsmodels.stats.anova import anova_lm
    from statsmodels.stats.multicomp import pairwise_tukeyhsd
except ImportError:
    raise SystemExit("Butuh statsmodels: pip install statsmodels --break-system-packages")


def eta_squared(anova_table):
    ss_total = anova_table["sum_sq"].sum()
    return anova_table["sum_sq"] / ss_total


def cohen_bucket(eta_sq):
    if pd.isna(eta_sq):
        return "n/a"
    if eta_sq < 0.01:
        return "negligible"
    if eta_sq < 0.06:
        return "small"
    if eta_sq < 0.14:
        return "medium"
    return "large"


def report_anova(table, label):
    table = table.copy()
    table["eta_sq"] = eta_squared(table)
    print(f"\n=== {label} ===")
    print(table)

    interaction_rows = [i for i in table.index if ":" in i]
    if not interaction_rows:
        print("(tidak ada baris interaksi -- cek formula model)")
        return table

    row = interaction_rows[0]
    f_val = table.loc[row, "F"]
    df1 = table.loc[row, "df"]
    df2 = table.loc["Residual", "df"] if "Residual" in table.index else float("nan")
    p_val = table.loc[row, "PR(>F)"]
    eta = table.loc[row, "eta_sq"]
    bucket = cohen_bucket(eta)

    # eta^2 sekecil 0.00002 tampil "0.000" dgn .3f -- format adaptif spy tidak
    # menyesatkan (angka bukan benar-benar nol, cuma kecil sekali).
    eta_str = f"{eta:.3f}" if eta >= 0.0005 else f"{eta:.2e}"
    print(f"\nF({df1:.0f}, {df2:.0f}) = {f_val:.2f}, p = {p_val:.4f}, "
          f"eta^2 = {eta_str} ({bucket})")

    # KESIMPULAN WAJIB pertimbangkan p-value DAN effect size bersamaan --
    # p<0.05 sendirian gampang jadi artefak N besar (lihat kasus nyata: H4
    # network x suite di data Mid n=960, p=0.025 tapi eta^2=0.00002 -- beda
    # rata2 cuma ~0.02ms, TIDAK bermakna praktis walau "signifikan" secara p).
    if p_val < 0.05 and bucket in ("negligible", "small"):
        print(f"-> Signifikan secara statistik (p<0.05) TAPI effect size "
              f"{bucket} (eta^2={eta_str}) -- kemungkinan besar ARTEFAK "
              f"ukuran sampel besar, BUKAN efek substantif. Jangan diklaim "
              f"sebagai temuan bermakna di paper tanpa qualifier ini.")
    elif p_val < 0.05:
        print(f"-> Interaksi signifikan DAN effect size {bucket} -- layak "
              f"dilaporkan sebagai temuan substantif.")
    else:
        print("-> Interaksi TIDAK signifikan dengan data ini.")
    return table


def h1_pure_handshake_ttest(df):
    """H1: apakah hybrid overhead ada di pure_handshake, per tier.
    Independent t-test (Welch, tidak asumsi variansi sama) classical vs
    hybrid -- ini uji PALING DASAR yang jadi prasyarat implisit H2/H3, tapi
    sebelumnya tidak pernah diuji langsung sendiri (cuma jadi bagian
    tersirat H2 yang butuh >=2 tier utk jalan)."""
    sub = df[df["measurement_type"] == "pure_handshake"].copy()
    sub["latency_ms"] = pd.to_numeric(sub["latency_ms"], errors="coerce")
    sub = sub.dropna(subset=["latency_ms"])

    print("\n=== H1: overhead handshake hybrid vs classical (per tier) ===")
    for tier in sorted(sub["tier"].dropna().unique()):
        tier_df = sub[sub["tier"] == tier]
        classical = tier_df[tier_df["suite"] == "classical"]["latency_ms"]
        hybrid = tier_df[tier_df["suite"] == "hybrid"]["latency_ms"]
        if len(classical) < 2 or len(hybrid) < 2:
            print(f"[{tier}] data tidak cukup (classical n={len(classical)}, "
                  f"hybrid n={len(hybrid)}), dilewati.")
            continue

        t_stat, p_val = stats.ttest_ind(hybrid, classical, equal_var=False)
        mean_c, mean_h = classical.mean(), hybrid.mean()
        diff = mean_h - mean_c
        diff_pct = (diff / mean_c) * 100 if mean_c else float("nan")

        # Cohen's d utk effect size t-test (beda dari eta^2 ANOVA)
        pooled_std = ((classical.std() ** 2 + hybrid.std() ** 2) / 2) ** 0.5
        cohens_d = diff / pooled_std if pooled_std else float("nan")
        d_bucket = ("negligible" if abs(cohens_d) < 0.2 else
                    "small" if abs(cohens_d) < 0.5 else
                    "medium" if abs(cohens_d) < 0.8 else "large")

        print(f"\n[{tier}] classical mean={mean_c:.3f}ms (n={len(classical)}), "
              f"hybrid mean={mean_h:.3f}ms (n={len(hybrid)})")
        print(f"  Selisih: {diff:+.3f}ms ({diff_pct:+.1f}%)")
        print(f"  t={t_stat:.3f}, p={p_val:.4f}, Cohen's d={cohens_d:.3f} ({d_bucket})")
        if p_val < 0.05 and d_bucket not in ("negligible",):
            print(f"  -> H1 didukung: hybrid signifikan lebih lambat, effect size {d_bucket}.")
        elif p_val < 0.05:
            print(f"  -> Signifikan (p<0.05) tapi Cohen's d negligible -- hati-hati overclaim.")
        else:
            print(f"  -> H1 TIDAK didukung di tier ini dengan data saat ini.")


def tukey_suite_within_tier(df, value_col, group_col="tier"):
    """Tukey HSD dgn label gabungan tier_suite, laporkan HANYA perbandingan
    classical vs hybrid DALAM tier yang sama -- perbandingan lintas tier
    dengan suite sama tidak relevan untuk H2/H3 dan sengaja diabaikan."""
    sub = df.dropna(subset=[value_col]).copy()
    sub["combo"] = sub[group_col].astype(str) + "_" + sub["suite"].astype(str)
    if sub["combo"].nunique() < 2:
        print("Data tidak cukup untuk Tukey post-hoc.")
        return
    result = pairwise_tukeyhsd(sub[value_col], sub["combo"])
    print("\nTukey HSD (semua pasangan tier_suite -- fokus baca baris classical vs "
          "hybrid PADA TIER YANG SAMA, abaikan baris lintas tier):")
    print(result.summary())


def h2_tier_suite(df):
    sub = df[df["measurement_type"] == "pure_handshake"].copy()
    sub["latency_ms"] = pd.to_numeric(sub["latency_ms"], errors="coerce")
    sub = sub.dropna(subset=["latency_ms"])
    if sub["tier"].nunique() < 2 or sub["suite"].nunique() < 2:
        print("H2: data pure_handshake tidak cukup (butuh >=2 tier, >=2 suite).")
        return
    model = smf.ols("latency_ms ~ C(suite) * C(tier)", data=sub).fit()
    table = anova_lm(model, typ=2)
    report_anova(table, "H2: tier x suite (subset pure_handshake)")
    tukey_suite_within_tier(sub, "latency_ms", "tier")


def h3_concurrency_suite(df):
    sub = df[df["measurement_type"] == "end_to_end"].copy()
    for col in ["latency_ms", "latency_p95_ms", "latency_p99_ms"]:
        sub[col] = pd.to_numeric(sub[col], errors="coerce")

    for tier in sorted(sub["tier"].dropna().unique()):
        tier_df = sub[sub["tier"] == tier]
        if tier_df["concurrency"].nunique() < 2 or tier_df["suite"].nunique() < 2:
            print(f"H3 [{tier}]: data tidak cukup, dilewati.")
            continue
        for metric in ["latency_ms", "latency_p95_ms", "latency_p99_ms"]:
            metric_df = tier_df.dropna(subset=[metric])
            if metric_df.empty:
                continue
            model = smf.ols(f"{metric} ~ C(suite) * C(concurrency)", data=metric_df).fit()
            table = anova_lm(model, typ=2)
            report_anova(table, f"H3 [{tier}]: concurrency x suite ({metric})")


def h4_network_suite(df, tier=None):
    sub = df[df["measurement_type"] == "end_to_end"].copy()
    if tier:
        sub = sub[sub["tier"] == tier]
    sub["latency_ms"] = pd.to_numeric(sub["latency_ms"], errors="coerce")
    sub = sub.dropna(subset=["latency_ms"])
    if sub["network"].nunique() < 2 or sub["suite"].nunique() < 2:
        print("H4: data end_to_end tidak cukup (butuh >=2 network, >=2 suite).")
        return
    model = smf.ols("latency_ms ~ C(suite) * C(network)", data=sub).fit()
    label = f"H4: network x suite (end_to_end{f', tier={tier}' if tier else ', semua tier'})"
    table = anova_lm(model, typ=2)
    report_anova(table, label)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="../../data/raw/all_runs.csv")
    ap.add_argument("--tier-for-h4", default=None)
    args = ap.parse_args()

    df = pd.read_csv(args.raw)
    n_total = len(df)
    df = df[df["group_verified"].astype(str).str.upper() == "Y"].copy()
    if n_total - len(df):
        print(f"PERINGATAN: {n_total - len(df)} baris dibuang (group_verified != Y).")

    h1_pure_handshake_ttest(df)
    h2_tier_suite(df)
    h3_concurrency_suite(df)
    h4_network_suite(df, args.tier_for_h4)

    print("\nSelesai. Larangan sesuai §III: JANGAN tambahkan interaksi >=3 arah "
          "atau interaksi dgn measurement_type -- kalau butuh itu, catat sebagai "
          "keterbatasan/future work, bukan diam-diam ditambahkan ke model.")


if __name__ == "__main__":
    main()