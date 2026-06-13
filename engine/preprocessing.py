import pandas as pd

def preprocess_student_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Cleans and standardizes the exact columns from the Persian housing dataset.
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

    df_clean['noise_tolerance'] = df_clean['noise_tolerance'].apply(
        lambda x: 1 if 'پر جنب و جوش' in str(x) else 0
    )
    
    df_clean['study_habit'] = df_clean['study_habit'].apply(
        lambda x: 1 if 'سکوت کامل' in str(x) else 0
    )
    
    df_clean['cleanliness'] = df_clean['cleanliness'].apply(
        lambda x: 1 if 'نظم طلبان' in str(x) else 0
    )
    # df['cultural_group'] = df['cultural_group'].apply(
    #     lambda x: 
    # )

    df_clean['age'] = pd.to_numeric(df_clean['age'], errors='coerce').fillna(20).astype(int)

    df_clean['sleep_window'] = df_clean['sleep_window'].astype(str).str.split('-').str[0]
    df_clean['wake_window'] = df_clean['wake_window'].astype(str).str.split('-').str[0]

    df_clean = df_clean.reset_index().rename(columns={'index': 'student_idx'})
    return df_clean