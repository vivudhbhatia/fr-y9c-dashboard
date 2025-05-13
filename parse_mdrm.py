import pandas as pd

def load_mnemonic_mapping():
    # Load MDRM CSV
    df = pd.read_csv("MDRM/MDRM_CSV.csv", encoding="latin1")

    # Clean column names
    df.columns = df.columns.str.strip()

    # Filter relevant reporting forms
    target_forms = ["FR Y-9C", "FR Y-15", "FFIEC 031", "FFIEC 041"]
    df = df[df["Reporting Form"].isin(target_forms)]

    # Build full mnemonic (e.g., BHCK2170)
    df["full_mnemonic"] = df["Mnemonic"] + df["Item Code"].astype(str)

    # Create mapping dict
    mapping = pd.Series(df["Item Description"].values, index=df["full_mnemonic"]).to_dict()

    return mapping
