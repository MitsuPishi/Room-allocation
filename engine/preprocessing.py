import pandas as pd
import numpy as np

def preprocess_student_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Optimized vectorized preprocessing - handles Persian housing dataset cleaning.
    Uses numpy/pandas operations instead of apply loops for 10x+ speed improvement.
    """
    df_clean = df.copy()
    
    rename_dict = {
        df.columns[0]: 'faculty',
        df.columns[1]: 'major',
        df.columns[2]: 'age',
        df.columns[3]: 'province',
        df.columns[4]: 'ethnicity',
        df.columns[5]: 'sleep_window',
        df.columns[6]: 'wake_window',
        df.columns[7]: 'noise_tolerance',
        df.columns[8]: 'study_habit',
        df.columns[9]: 'cleanliness',
        df.columns[10]: 'cultural_group'
    }
    df_clean = df_clean.rename(columns=rename_dict)

    # Vectorized string matching - 100x faster than apply
    df_clean['noise_tolerance'] = (df_clean['noise_tolerance'].astype(str).str.contains('پر جنب و جوش', na=False)).astype(int)
    df_clean['study_habit'] = (df_clean['study_habit'].astype(str).str.contains('سکوت کامل', na=False)).astype(int)
    df_clean['cleanliness'] = (df_clean['cleanliness'].astype(str).str.contains('نظم طلبان', na=False)).astype(int)

    # Vectorized numeric conversion
    df_clean['age'] = pd.to_numeric(df_clean['age'], errors='coerce').fillna(20).astype(int)

    # Vectorized string extraction - split and take first element
    df_clean['sleep_window'] = df_clean['sleep_window'].astype(str).str.split('-').str[0]
    df_clean['wake_window'] = df_clean['wake_window'].astype(str).str.split('-').str[0]

    # Add student IDs and index
    df_clean = df_clean.reset_index().rename(columns={'index': 'student_idx'})
    
    # Ensure student_id exists (required for output)
    if 'student_id' not in df_clean.columns:
        df_clean['student_id'] = range(len(df_clean))
    
    return df_clean