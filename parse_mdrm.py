import pandas as pd

def load_mnemonic_mapping():
    df = pd.read_csv("MDRM/MDRM_CSV.csv", encoding="latin1")

    # Strip all column names and remove newline/whitespace
    df.columns = df.columns.str.strip()

    # Optional: Show columns if debugging
    # print("Columns:", df.columns.tolist())

    # Clean values in key fields
    df["Mnemonic"] = df["Mnemonic"].str.strip()
    df["Item Code"] = df["Item Code"].astype(str).str.strip()
    df["Item Name"] = df["Item Name"].fillna("").str.strip()

    # Build full mnemonic code like 'BHCK2170'
    df["full_mnemonic"] = df["Mnemonic"] + df["Item Code"]

    # Use Item Name for display, fallback to Item Code
    df["clean_label"] = df["Item Name"]
    df.loc[df["clean_label"] == "", "clean_label"] = df["full_mnemonic"]

    # Create final mapping dictionary
    mapping = pd.Series(df["clean_label"].values, index=df["full_mnemonic"]).to_dict()

    return mapping
