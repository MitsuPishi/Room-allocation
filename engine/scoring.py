# engine/scoring.py
import pandas as pd
import numpy as np

class CompatibilityEngine:
    def __init__(self, weights: dict):
        self.weights = weights

    def compute_matrix(self, df_students: pd.DataFrame) -> np.ndarray:
        """Vectorized compatibility matrix computation for O(n²) performance with n² factor reduced."""
        n = len(df_students)
        matrix = np.zeros((n, n))
        
        # Extract arrays once for vectorized operations
        cleanliness = df_students['cleanliness'].values
        noise_tol = df_students['noise_tolerance'].values
        study = df_students['study_habit'].values
        sleep = df_students['sleep_window'].values
        wake = df_students['wake_window'].values
        faculty = df_students['faculty'].values
        
        w_clean = self.weights.get('cleanliness', 40)
        w_noise = self.weights.get('noise', 30)
        w_study = self.weights.get('study', 30)
        w_schedule = self.weights.get('schedule', 20)
        
        # Vectorized pairwise comparisons using broadcasting
        for i in range(n):
            # Compare student i with all students j > i
            j_range = np.arange(i + 1, n)
            
            # Cleanliness match
            match_clean = (cleanliness[i] == cleanliness[j_range])
            score_clean = np.where(match_clean, w_clean, -w_clean * 0.5)
            
            # Noise tolerance match
            score_noise = np.where(noise_tol[i] == noise_tol[j_range], w_noise, 0)
            
            # Study habit match
            score_study = np.where(study[i] == study[j_range], w_study, 0)
            
            # Sleep window match
            score_sleep = np.where(sleep[i] == sleep[j_range], w_schedule, 0)
            
            # Wake window match
            score_wake = np.where(wake[i] == wake[j_range], w_schedule, 0)
            
            # Faculty bonus (soft)
            score_faculty = np.where(faculty[i] == faculty[j_range], 10, 0)
            
            # Combine all scores
            scores = score_clean + score_noise + score_study + score_sleep + score_wake + score_faculty
            
            # Fill matrix symmetrically
            matrix[i, j_range] = scores
            matrix[j_range, i] = scores
        
        return matrix